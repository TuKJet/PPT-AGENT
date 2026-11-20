import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from test_workflow_helper import load_workflow_module, valid_slide_plans


class StyleCheckpointTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "preview"
        env = patch.dict(os.environ, OUTPUT_DIR=temp.name)
        env.start()
        self.addCleanup(env.stop)
        self.w = load_workflow_module()
        self.cmd("init", "--topic", "研发评审", "--audience", "研发总监", "--pages", "2")

    def cmd(self, name, *options):
        args = self.w.build_parser().parse_args([name, "--run-dir", str(self.root), *options])
        with redirect_stdout(io.StringIO()) as buf:
            args.func(args)
        return buf.getvalue()

    def approve_content(self, titles):
        for artifact, value in (("outline", {"pages": [{"title": t} for t in titles]}),
                                ("contents", {t: "已批准的材料" for t in titles})):
            self.w.write_json(self.root / self.w.ARTIFACT_FILES[artifact], value)
            self.cmd("preview", "--artifact", artifact)
            self.cmd("approve", "--artifact", artifact)

    def sample_record(self, pages):
        path = self.root / ".workflow/style-samples/manifest.json"
        styles = []
        for i, letter in enumerate("ABCD"):
            records = []
            for p in pages:
                image = path.parent / f"{letter}-{p}.png"
                image.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (128, 72), (i * 61, 60 * p, 80)).save(image)
                records.append({"page": p, "path": str(image), "plan": "结论在上，两方案按同一指标对齐"})
            styles.append({"id": letter, "pages": records})
        self.w.write_json(path, {"styles": styles})
        return path

    def test_real_checkpoint_and_freeform_combination_survive_resume(self):
        self.approve_content(["决策依据", "试验记录"])
        self.cmd("choose-plan-mode", "--mode", "samples")
        plans = valid_slide_plans(("决策依据", "A", "content"), ("试验记录", "B", "content"))
        self.w.write_json(self.root / "slide-plans.json", plans)
        self.assertIn("generate-and-record", json.loads(self.cmd("resume"))["next_action"])
        with self.assertRaisesRegex(RuntimeError, "four-style-samples"):
            self.cmd("preview", "--artifact", "slide_plans")
        manifest = self.sample_record((1, 2))
        self.cmd("record-style-samples", "--file", str(manifest))
        waiting = json.loads(self.cmd("resume"))
        self.assertEqual(waiting["next_action"], "ask-user-for-style-preference")
        for board in waiting["style_samples"]["comparisons"]:
            with Image.open(board) as image:
                self.assertEqual(image.size, (1600, 988))
        with self.assertRaisesRegex(RuntimeError, "preference"):
            self.cmd("preview", "--artifact", "slide_plans")
        choice = "用 B 的构图、C 的配色，按截图圈出的地方加粗。"
        self.cmd("choose-style", "--preference", choice)
        self.assertEqual(json.loads(self.cmd("resume"))["design_choice"]["preference"], choice)
        self.cmd("preview", "--artifact", "slide_plans")
        self.cmd("approve", "--artifact", "slide_plans")
        self.cmd("choose-style", "--preference", "保留配色，改用 A 的版式")
        with self.assertRaisesRegex(RuntimeError, "preview"):
            self.cmd("approve", "--artifact", "slide_plans")

    def test_two_pages_per_style_from_approved_contents(self):
        self.approve_content(["A", "B", "C"])
        self.cmd("choose-plan-mode")
        with self.assertRaisesRegex(ValueError, "2 representative pages"):
            self.cmd("record-style-samples", "--file", str(self.sample_record((1,))))
        manifest = self.sample_record((1, 2))
        data = self.w.read_json(manifest)
        data["styles"][-1]["pages"][-1]["page"] = 3
        self.w.write_json(manifest, data)
        with self.assertRaisesRegex(ValueError, "same representative"):
            self.cmd("record-style-samples", "--file", str(manifest))

    def test_single_page_and_legacy_resume(self):
        self.approve_content(["唯一一页"])
        self.cmd("choose-plan-mode")
        self.cmd("record-style-samples", "--file", str(self.sample_record((1,))))
        self.assertEqual(len(json.loads(self.cmd("resume"))["style_samples"]["comparisons"]), 1)
        state = self.w.load_state(self.root)
        for key in ("plan_mode", "style_samples", "design_choice"):
            del state[key]
        self.w.write_json(self.root / self.w.STATE_FILE, state)
        self.assertIn("slide_plans", json.loads(self.cmd("resume"))["next_action"])

    def test_contents_approval_pauses_for_plan_mode_and_direct_path_needs_no_samples(self):
        self.approve_content(["决策页", "证据页"])
        resumed = json.loads(self.cmd("resume"))
        self.assertEqual(resumed["next_action"], "ask-how-to-plan-slides")

        first = self.cmd("choose-plan-mode", "--mode", "direct")
        self.assertIn("plan_mode=direct", first)
        self.assertIn("next=write-and-preview-slide-plans", first)
        self.assertEqual(json.loads(self.cmd("resume"))["plan_mode"], "direct")
        plans = valid_slide_plans(("决策页", "A", "content"), ("证据页", "B", "content"))
        self.w.write_json(self.root / "slide-plans.json", plans)
        self.cmd("preview", "--artifact", "slide_plans")
        self.cmd("approve", "--artifact", "slide_plans")

        plans["slides"][0]["plan"]["core_message"] = "修订后的决策结论"
        self.w.write_json(self.root / "slide-plans.json", plans)
        self.cmd("preview", "--artifact", "slide_plans")
        self.cmd("approve", "--artifact", "slide_plans")
        state = self.w.load_state(self.root)
        self.assertEqual(state["plan_mode"], "direct")
        self.assertNotEqual((state.get("style_samples") or {}).get("status"), "ready")

    def test_samples_mode_is_default_and_repeated_choice_is_idempotent(self):
        self.approve_content(["决策页", "证据页"])
        resumed = json.loads(self.cmd("resume"))
        self.assertEqual(resumed["next_action"], "ask-how-to-plan-slides")
        self.assertIn("plan_mode=samples", self.cmd("choose-plan-mode"))
        first = self.w.load_state(self.root)
        self.cmd("choose-plan-mode", "--mode", "samples")
        second = self.w.load_state(self.root)
        self.assertEqual(second.get("plan_mode"), "samples")
        self.assertEqual(second.get("style_samples"), first.get("style_samples"))
        self.assertEqual(second.get("design_choice"), first.get("design_choice"))
        manifest = self.sample_record((1, 2))
        self.cmd("record-style-samples", "--file", str(manifest))
        waiting = json.loads(self.cmd("resume"))
        self.assertEqual(waiting["next_action"], "ask-user-for-style-preference")
