from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from unittest import mock
import zipfile
from xml.etree import ElementTree as ET

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/skills/ppt-deck-workflow/scripts/workflow.py"


def load_workflow():
    spec = importlib.util.spec_from_file_location("delivery_workflow_forward", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def slide_plan() -> dict:
    return {
        "version": 2,
        "deck_strategy": {
            "primary_audience": "management",
            "decision_context": "Approve the delivery path",
            "first_questions": ["Why now?"],
            "evidence_order": ["Conclusion", "Evidence"],
            "presentation_posture": "Decision-led",
        },
        "design_system": {
            "theme_name": "Forward test",
            "audience_fit": "Clear management communication",
            "palette": {"background": "#FFFFFF", "surface": "#FFFFFF", "primary": "#1358A8",
                        "accent": "#F2A900", "text_primary": "#132238", "text_muted": "#5F6F82"},
            "typography": {"title": "28pt"},
            "component_rules": {"spacing": "8px"},
            "chart_treatment": {"style": "direct"},
            "illustration_policy": "Use source visuals when supplied",
            "design_genes": ["clean"],
        },
        "slides": [{
            "index": 1, "title": "Forward test", "material": "One source page", "page_role": "content",
            "plan": {
                "core_message": "A source page becomes an editable page",
                "layout_structure": "Title above one process line",
                "visual_hierarchy": ["Title", "Process"],
                "required_elements": ["title", "process line"],
                "palette_tokens": ["background", "primary", "text_primary"],
                "style_controls": {"density": "medium"},
                "audience_controls": {"technical_depth": "decision-relevant"},
                "renderer_neutral_constraints": ["Keep the arrow visible"],
            },
        }],
    }


class DeliveryWorkflowForwardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmp.name) / "output"
        self.output_root.mkdir()
        self.previous_output = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.w = load_workflow()
        self.run = self.output_root / "forward"
        self.w.init_state(self.run, topic="Forward", audience="management", pages="1", research="")
        self.w.write_json(self.run / ".workflow/task-brief.json", {
            "objective": "Validate direct IMG to PPTD delivery",
            "constraints": ["Use local test images", "Do not start the interactive editor"],
            "source_paths": [], "pending_work": [], "next_action": "export",
        })
        self._approve("outline", {"pages": [{"title": "Forward test", "page_role": "content"}]})
        self._approve("contents", {"Forward test": "One source page"})
        self._approve("slide_plans", slide_plan())

    def tearDown(self):
        if self.previous_output is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output
        self.tmp.cleanup()

    def _approve(self, artifact: str, value: dict):
        self.w.write_json(self.run / self.w.ARTIFACT_FILES[artifact], value)
        self.w.preview_artifact(self.run, artifact)
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact=artifact))

    def test_img_to_pptd_cli_delivery_resume_and_restore(self):
        # Generate one local source image and the actual IMG PPTX.
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.run), renderer="img", source="plans"))
        self.w.prepare_render_jobs(self.run, "img")
        img_path = self.w.render_target_path(self.run, "img", 1, "Forward test")
        img_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (960, 540), "#650773").save(img_path)
        original_img = img_path.read_bytes()
        img_pptx = self.w.export_img(self.run)
        self.assertTrue(img_pptx.is_file())

        # Reconstruct a PPTD page with native text and a canonical arrow line.
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.run), renderer="pptd", source="img"))
        self.w.prepare_render_jobs(self.run, "pptd")
        pptd = self.run / "pptd"
        (pptd / "deck.pptd").write_text(json.dumps({"version": "v2", "title": "工程验证", "size": [960, 540],
            "pages": ["pages/01_Forward_test.page"]}, ensure_ascii=False), encoding="utf-8")
        page = {"pageType": "content", "elements": [
            {"elementId": "title", "elementType": "text", "bounds": [40, 40, 800, 70],
             "content": {"fontSize": 30, "text": "工程设计验证"}},
            {"elementId": "flow", "elementType": "line", "bounds": [100, 240, 700, 40],
             "viewBox": [700, 40], "points": "0,20 700,20", "curve": "round",
             "arrow": [None, "arrow"], "border": {"style": "solid", "width": 3, "color": "#1358A8"}},
        ]}
        (pptd / "pages/01_Forward_test.page").write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
        self.w.validate_pptd_project(self.run)

        # QA can be mocked; the delivery export must still use the real Node/WASM path.
        with mock.patch("pptd_visual.export_images", return_value={"visual_review": "pending"}) as qa:
            self.w.cmd_export_pptd_images(Namespace(run_dir=str(self.run), force=False))
            qa.assert_called_once()
        with mock.patch('pptd_runtime.serve_editor', side_effect=AssertionError('interactive editor must not start')):
            pptd_pptx = self.w.export_pptd(self.run)
        self.assertTrue(pptd_pptx.is_file())
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        with zipfile.ZipFile(pptd_pptx) as archive:
            xml = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
            arrows = xml.findall(".//a:tailEnd", ns) + xml.findall(".//a:headEnd", ns)
            self.assertTrue(any(e.get('type') not in (None, 'none') for e in arrows))
            self.assertIn('工程设计验证', ''.join(xml.itertext()))

        # Finalization leaves canonical planning files, both PPTX files and necessary PPTD files.
        from delivery import finalize_delivery, restore_img_sources
        report = finalize_delivery(self.run, apply=True)
        self.assertTrue(report["applied"])
        self.assertEqual({p.name for p in self.run.iterdir()}, {
            "outline.json", "contents.json", "slide-plans.json", img_pptx.name, pptd_pptx.name, "pptd"
        })
        restored = restore_img_sources(self.run, img_pptx)
        self.assertEqual(restored[0].read_bytes(), original_img)

        # A post-delivery PPTX mutation is detected on resume through recorded hashes.
        with pptd_pptx.open("ab") as handle:
            handle.write(b"mutation")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.w.cmd_resume(Namespace(run_dir=str(self.run)))
        resumed = json.loads(output.getvalue())
        self.assertEqual(resumed["state"], "needs_verification")

        # A scoped follow-up retains source mode and constraints without re-initialization.
        self.w.preview_artifact(self.run, 'slide_plans')
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact='slide_plans'))
        self.w.prepare_render_jobs(self.run, 'pptd')
        job = self.w.read_json(self.run / 'render-jobs/pptd/slide-01.json')
        self.assertEqual(job['source'], 'img')
        self.assertIn('Do not start the interactive editor', job['task_brief']['constraints'])


if __name__ == "__main__":
    unittest.main()
