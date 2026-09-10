from __future__ import annotations

import json
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from tests import test_workflow_helper as helpers


class ImgSvgProtocolTests(unittest.TestCase):
    setUp = helpers.WorkflowHelperImgSvgFlowTests.setUp
    tearDown = helpers.WorkflowHelperImgSvgFlowTests.tearDown
    export_img = helpers.WorkflowHelperImgSvgFlowTests.export_img
    prepare_img_svg_text_and_crops = helpers.WorkflowHelperImgSvgFlowTests.prepare_img_svg_text_and_crops
    fake_render_review = helpers.WorkflowHelperImgSvgFlowTests.fake_render_review
    complete_img_svg_after_review = helpers.WorkflowHelperImgSvgFlowTests.complete_img_svg_after_review

    def start_page(self):
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = self.workflow.read_json(self.run_dir / "render-jobs/img-svg/manifest.json")
        page = manifest["slides"][0]
        Path(page["target_path"]).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
            '<rect width="1280" height="720" fill="white"/>'
            '<text x="80" y="120">Opening</text></svg>', encoding="utf-8")
        page["visible_text"] = [{"id": "opening", "text": "Opening"}]
        self.workflow.write_json(self.run_dir / "render-jobs/img-svg/manifest.json", manifest)
        return page

    def ready_page(self):
        page = self.start_page()
        self.prepare_img_svg_text_and_crops(page)
        self.complete_img_svg_after_review(page)
        return page

    def test_export_rejects_modified_svg_after_review(self):
        page = self.ready_page()
        path = Path(page["target_path"])
        path.write_text(path.read_text().replace("Opening", "Changed"), encoding="utf-8")
        with mock.patch("pptx_builder.build_native_svg_pptx") as builder:
            with self.assertRaisesRegex((ValueError, RuntimeError), "review|changed|stale"):
                self.workflow.export_img_svg(self.run_dir)
            builder.assert_not_called()

    def test_export_rejects_modified_source_after_review(self):
        page = self.ready_page()
        from PIL import Image
        Image.new("RGB", (2, 2), "red").save(page["source_image_path"])
        with mock.patch("pptx_builder.build_native_svg_pptx") as builder:
            with self.assertRaisesRegex((ValueError, RuntimeError), "review|changed|stale"):
                self.workflow.export_img_svg(self.run_dir)
            builder.assert_not_called()

    def test_export_rejects_extra_page_after_review(self):
        page = self.ready_page()
        Path(page["target_path"]).with_name("extra.svg").write_bytes(Path(page["target_path"]).read_bytes())
        with mock.patch("pptx_builder.build_native_svg_pptx") as builder:
            with self.assertRaisesRegex((ValueError, RuntimeError), "mismatch|pages"):
                self.workflow.export_img_svg(self.run_dir)
            builder.assert_not_called()

    def test_no_crop_page_needs_no_crop_or_self_attestation_file(self):
        page = self.start_page()
        self.assertNotIn("conversion_evidence_path", page)
        self.assertFalse(Path(page["crop_manifest_path"]).exists())
        with mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review):
            self.assertEqual(self.workflow.complete_img_svg_generation(self.run_dir), [])

    def test_unchanged_review_reuses_preview(self):
        page = self.ready_page()
        with mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review) as render:
            self.workflow.complete_img_svg_generation(self.run_dir)
            render.assert_not_called()

    def test_force_render_invalidates_pass(self):
        page = self.ready_page()
        with mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review) as render:
            self.assertEqual(self.workflow.complete_img_svg_generation(self.run_dir, force_render=True), [])
            self.assertEqual(render.call_count, 1)
        self.assertEqual(self.workflow.read_json(Path(page["fidelity_review_path"]))["status"], "pending_visual_review")

    def test_changed_preview_invalidates_pass(self):
        page = self.ready_page()
        Path(page["rendered_preview_path"]).write_bytes(b"changed preview")
        with mock.patch("pptx_builder.build_native_svg_pptx") as builder:
            with self.assertRaisesRegex(ValueError, "preview"):
                self.workflow.export_img_svg(self.run_dir)
            builder.assert_not_called()

    def test_repeated_words_require_repeated_svg_occurrences(self):
        items = [{"id": "a", "text": "Opening"}, {"id": "b", "text": "Opening"}]
        with self.assertRaisesRegex(ValueError, "missing"):
            self.workflow._require_text_occurrences(items, ["Opening"])
        self.workflow._require_text_occurrences(items, ["Opening", "Opening"])
        with self.assertRaisesRegex(ValueError, "extra text"):
            self.workflow._require_text_occurrences([], ["Opening"])
        self.workflow._require_text_occurrences([{"id": "line", "text": "Two pieces"}], ["Two", "pieces"])

    def test_render_environment_change_invalidates_only_cached_review(self):
        page = self.ready_page()
        with mock.patch.object(self.workflow, "img_svg_render_environment", return_value="new fonts"), \
             mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review) as render:
            self.assertEqual(self.workflow.complete_img_svg_generation(self.run_dir), [])
            self.assertEqual(render.call_count, 1)

    def test_external_css_event_handlers_and_animations_are_rejected(self):
        page = self.start_page()
        for content in ['<rect style="fill:url( &quot;https://example.com/a.svg&quot; )"/>',
                        '<rect onload="alert(1)"/>', '<animate attributeName="x"/>']:
            with self.subTest(content=content):
                Path(page["target_path"]).write_text(
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">' + content + '</svg>', encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.workflow.validate_ppt_compatible_svg(Path(page["target_path"]))

    def test_legacy_job_can_be_reviewed_without_regenerating_svg(self):
        page = self.start_page()
        svg_bytes = Path(page["target_path"]).read_bytes()
        manifest_path = self.run_dir / "render-jobs/img-svg/manifest.json"
        manifest = self.workflow.read_json(manifest_path)
        legacy = dict(page)
        legacy.pop("visible_text")
        job_path = manifest_path.with_name("slide-01.json")
        self.workflow.write_json(job_path, legacy)
        manifest["version"] = 2
        manifest["slides"] = [{**page, "job_path": str(job_path)}]
        self.workflow.write_json(manifest_path, manifest)
        self.workflow.write_json(Path(page["crop_manifest_path"]), {
            "version": 3, "source_image_path": page["source_image_path"], "svg_path": page["target_path"],
            "visible_text_inventory": {"complete": True, "items": [{"id": "opening", "text": "Opening"}]}, "crops": [],
        })
        self.workflow.write_json(Path(page["fidelity_review_path"]), {"version": 1, "status": "pass"})
        with mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review):
            self.assertEqual(self.workflow.complete_img_svg_generation(self.run_dir), [])
        review = self.workflow.read_json(Path(page["fidelity_review_path"]))
        self.assertEqual(review["version"], 2)
        self.assertEqual(review["status"], "pending_visual_review")
        self.assertEqual(Path(page["target_path"]).read_bytes(), svg_bytes)

    def start_two_pages(self):
        self.workflow.write_json(self.run_dir / "slide-plans.json", helpers.valid_slide_plans(
            ("Opening", "A", "cover"), ("Closing", "B", "ending")))
        second_source = self.run_dir / "img/slide-02-closing.png"
        second_source.write_bytes((self.run_dir / "img/slide-01-opening.png").read_bytes())
        first = self.start_page()
        manifest_path = self.run_dir / "render-jobs/img-svg/manifest.json"
        manifest = self.workflow.read_json(manifest_path)
        second = manifest["slides"][1]
        Path(second["target_path"]).write_text(Path(first["target_path"]).read_text().replace("Opening", "Closing"), encoding="utf-8")
        second["visible_text"] = [{"id": "closing", "text": "Closing"}]
        self.workflow.write_json(manifest_path, manifest)
        return manifest

    def test_page_mapping_order_must_match_sources(self):
        manifest = self.start_two_pages()
        manifest["slides"].reverse()
        self.workflow.write_json(self.run_dir / "render-jobs/img-svg/manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "mapping/order"):
            self.workflow.complete_img_svg_generation(self.run_dir)

    def test_legacy_missing_text_metadata_is_seeded_for_review(self):
        page = self.start_page()
        page.pop("visible_text")
        items = self.workflow.img_svg_text_items(page)
        self.assertEqual([item["text"] for item in items], ["Opening"])

    def test_crop_geometry_matches_declared_target(self):
        from xml.etree import ElementTree
        manifest = {"crops": [{"id": "photo", "source_box": [0, 0, 10, 10], "target_box": [20, 20, 10, 10]}]}
        root = ElementTree.fromstring('<svg xmlns="http://www.w3.org/2000/svg"><image data-crop-id="photo" x="20" y="20" width="10" height="10"/></svg>')
        self.workflow.validate_crop_entries(manifest, root, embedded=True)
        root[0].set("x", "30")
        with self.assertRaisesRegex(ValueError, "geometry"):
            self.workflow.validate_crop_entries(manifest, root, embedded=True)

    def test_only_modified_page_is_rendered_again(self):
        manifest = self.start_two_pages()
        with mock.patch.object(self.workflow, "render_img_svg_review", side_effect=self.fake_render_review) as render:
            self.workflow.complete_img_svg_generation(self.run_dir)
            self.assertEqual(render.call_count, 2)
            for page in manifest["slides"]:
                path = Path(page["fidelity_review_path"])
                review = self.workflow.read_json(path)
                review.update(status="pass", text_checked=True, reviewer="test", notes="Both pages match their synthetic sources.")
                self.workflow.write_json(path, review)
            self.assertEqual(len(self.workflow.complete_img_svg_generation(self.run_dir)), 2)
            render.reset_mock()
            path = Path(manifest["slides"][1]["target_path"])
            path.write_text(path.read_text().replace('x="80"', 'x="81"'), encoding="utf-8")
            self.assertEqual(self.workflow.complete_img_svg_generation(self.run_dir), [])
            self.assertEqual(render.call_count, 1)
            first_review = self.workflow.read_json(Path(manifest["slides"][0]["fidelity_review_path"]))
            self.assertEqual(first_review["status"], "pass")


if __name__ == "__main__":
    unittest.main()
