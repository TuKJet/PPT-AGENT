from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


def load_delivery():
    path = Path(__file__).resolve().parents[1] / '.codex/skills/ppt-deck-workflow/scripts/delivery.py'
    spec = importlib.util.spec_from_file_location('delivery', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'deck'
        self.root.mkdir()
        self.delivery = load_delivery()
        for name, value in {
            'outline.json': {'pages': [{'title': 'Intro', 'page_role': 'cover'}]},
            'contents.json': {'Intro': 'Approved text'},
            'slide-plans.json': {'version': 2, 'slides': [{'index': 1, 'title': 'Intro'}]},
            'workflow-state.json': {'renderer': 'img', 'status': 'completed'},
        }.items():
            (self.root / name).write_text(json.dumps(value), encoding='utf-8')
        from PIL import Image
        from pptx import Presentation
        (self.root / 'img').mkdir()
        self.image = self.root / 'img/01_Intro.png'
        Image.new('RGB', (160, 90), 'purple').save(self.image)
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_picture(str(self.image), 0, 0, width=deck.slide_width, height=deck.slide_height)
        deck.save(self.root / 'deck-img.pptx')
        for folder in ('.workflow', 'render-jobs', 'img-prompts'):
            (self.root / folder).mkdir()
            (self.root / folder / 'temporary.txt').write_text('scratch')

    def test_finalization_is_preview_by_default_and_cleans_only_after_apply(self):
        report = self.delivery.finalize_delivery(self.root)
        self.assertFalse(report['applied'])
        self.assertTrue((self.root / 'img').exists())
        report = self.delivery.finalize_delivery(self.root, apply=True)
        self.assertTrue(report['applied'])
        self.assertEqual(set(p.name for p in self.root.iterdir()), {
            'outline.json', 'contents.json', 'slide-plans.json', 'deck-img.pptx'})
        metadata = json.loads((self.root / 'slide-plans.json').read_text())['_delivery']
        self.assertEqual(metadata['exports'][0]['path'], 'deck-img.pptx')
        self.assertEqual(metadata['artifact_sha256']['slide_plans'], self.delivery.artifact_digest(self.root / 'slide-plans.json'))
        self.delivery.finalize_delivery(self.root, apply=True)  # idempotent

    def test_unknown_inputs_block_mutation_and_are_not_silently_deleted(self):
        (self.root / 'user-notes.md').write_text('original input')
        report = self.delivery.finalize_delivery(self.root)
        self.assertEqual(report['unclassified'], ['user-notes.md'])
        with self.assertRaisesRegex(ValueError, 'unclassified'):
            self.delivery.finalize_delivery(self.root, apply=True)
        self.assertTrue((self.root / 'workflow-state.json').exists())
        self.assertTrue((self.root / 'user-notes.md').exists())

    def test_explicit_generated_scratch_discard_is_bounded(self):
        (self.root / 'ad-hoc-report.md').write_text('generated scratch')
        self.delivery.finalize_delivery(self.root, apply=True, discard=['ad-hoc-report.md'])
        self.assertFalse((self.root / 'ad-hoc-report.md').exists())
        for unsafe in ('../outside', 'outline.json', 'deck-img.pptx', '.'):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                self.delivery.finalize_delivery(self.root, discard=[unsafe])

    def test_incomplete_or_corrupt_export_preserves_working_files(self):
        (self.root / 'deck-img.pptx').write_bytes(b'not a zip')
        with self.assertRaises(ValueError):
            self.delivery.finalize_delivery(self.root, apply=True)
        self.assertTrue((self.root / 'img').exists())

    def test_pending_work_blocks_finalization(self):
        (self.root / '.workflow/task-brief.json').write_text(json.dumps({'pending_work': ['Fix arrows']}))
        with self.assertRaisesRegex(ValueError, 'pending_work'):
            self.delivery.finalize_delivery(self.root, apply=True)

    def test_missing_canonical_artifact_blocks_cleanup(self):
        (self.root / 'contents.json').unlink()
        with self.assertRaisesRegex(ValueError, 'contents.json'):
            self.delivery.finalize_delivery(self.root, apply=True)
        self.assertTrue((self.root / 'img').exists())

    def test_original_pixels_can_be_restored_after_cleanup(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        original = self.image.read_bytes()
        self.delivery.finalize_delivery(self.root, apply=True)
        restored = self.delivery.restore_img_sources(self.root, self.root / 'deck-img.pptx')
        self.assertEqual(restored[0].read_bytes(), original)
        restored[0].write_bytes(b'manual change')
        with self.assertRaisesRegex(ValueError, 'refusing overwrite'):
            self.delivery.restore_img_sources(self.root, self.root / 'deck-img.pptx')

    def test_img_without_identical_backup_is_preserved(self):
        from PIL import Image
        Image.new('RGB', (160, 90), 'red').save(self.image)
        with self.assertRaisesRegex(ValueError, 'byte-identical'):
            self.delivery.finalize_delivery(self.root, apply=True)
        self.assertTrue(self.image.exists())

    def test_resume_detects_missing_or_changed_final_artifacts(self):
        self.delivery.finalize_delivery(self.root, apply=True)
        self.assertEqual(self.delivery.inspect_delivery(self.root), [])
        (self.root / 'contents.json').write_text('{}')
        self.assertIn('contents.json missing or changed', self.delivery.inspect_delivery(self.root))
        (self.root / 'deck-img.pptx').unlink()
        self.assertIn('deck-img.pptx missing or changed', self.delivery.inspect_delivery(self.root))

    def test_recovery_rejects_unrecorded_source(self):
        self.delivery.finalize_delivery(self.root, apply=True)
        source = self.root / 'deck-img.pptx'
        source.write_bytes(source.read_bytes() + b'changed source')
        with self.assertRaisesRegex(ValueError, 'recorded export'):
            self.delivery.restore_img_sources(self.root, source)
        self.assertFalse((self.root / 'img').exists())

    def test_explicit_extra_deliverable_can_be_kept(self):
        (self.root / 'requested.svg').write_text('<svg/>')
        self.delivery.finalize_delivery(self.root, apply=True, retain=['requested.svg'])
        self.assertTrue((self.root / 'requested.svg').is_file())
        self.assertEqual(self.delivery.inspect_delivery(self.root), [])


if __name__ == '__main__':
    unittest.main()
