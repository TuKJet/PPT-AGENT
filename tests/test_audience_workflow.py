import contextlib
import io
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pptx import Presentation
from test_workflow_helper import load_workflow_module, valid_slide_plans


class AudienceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = load_workflow_module()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(patch.dict(os.environ, {"OUTPUT_DIR": tmp.name}))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.run_dir = Path(tmp.name) / "roi"
        self.workflow.cmd_init(Namespace(topic="经营决策", audience="经营层", pages="1", research="",
                                         run_dir=str(self.run_dir)))
        self.plan = valid_slide_plans(("先试行中等投入", "仅供核对的原始素材", "content"))
        self.plan["version"] = 3
        self.plan["deck_strategy"]["use_context"] = "live"
        self.layers = {"on_screen": ["先试行中等投入", "年投入 46.5 万元"],
                       "talk_track": ["例会引导提问"], "reference": ["核算底稿编号 R19"]}
        self.plan["slides"][0]["plan"]["copy_layers"] = self.layers

    def preview(self):
        self.workflow.write_json(self.run_dir / "slide-plans.json", self.plan)
        return self.workflow.preview_artifact(self.run_dir, "slide_plans")

    def test_page_jobs_and_speaker_notes_use_their_respective_copy_layers(self):
        preview = self.preview().read_text(encoding="utf-8")
        for part in ("现场讲解", "上屏原文", "讲解", "备查", "例会引导提问", "核算底稿编号 R19"):
            self.assertIn(part, preview)
        self.workflow.cmd_approve(Namespace(run_dir=str(self.run_dir), artifact="slide_plans"))
        for renderer in ("pptd", "img"):
            self.workflow.cmd_choose_renderer(Namespace(run_dir=str(self.run_dir), renderer=renderer))
            jobs = self.workflow.prepare_render_jobs(self.run_dir, renderer).parent
            payload = self.workflow.read_json(jobs / "slide-01.json")
            self.assertEqual(payload["plan"]["copy_layers"], {"on_screen": self.layers["on_screen"]})
            for path in (jobs / "slide-01.json", jobs / "shared-context.json"):
                raw = path.read_text(encoding="utf-8")
                for private in ("例会引导提问", "核算底稿编号 R19", "仅供核对的原始素材"):
                    self.assertNotIn(private, raw)
        image = self.workflow.render_target_path(self.run_dir, "img", 1, self.plan["slides"][0]["title"])
        Image.new("RGB", (64, 36), "white").save(image)
        output = self.workflow.export_img(self.run_dir)
        slide = Presentation(output).slides[0]
        notes = slide.notes_slide.notes_text_frame.text
        self.assertIn("讲解\n例会引导提问", notes)
        self.assertIn("备查\n核算底稿编号 R19", notes)

    def test_new_run_requires_setting_and_copy_layers(self):
        self.plan["version"] = 2
        with self.assertRaisesRegex(ValueError, "New runs"):
            self.preview()
        self.plan["version"] = 3
        del self.plan["deck_strategy"]["use_context"]
        with self.assertRaisesRegex(ValueError, "use_context"):
            self.preview()
        self.plan["deck_strategy"]["use_context"] = "standalone"
        del self.plan["slides"][0]["plan"]["copy_layers"]
        with self.assertRaisesRegex(ValueError, "copy_layers"):
            self.preview()
