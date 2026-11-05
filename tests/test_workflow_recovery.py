from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_workflow():
    path = ROOT / ".codex/skills/ppt-deck-workflow/scripts/workflow.py"
    spec = importlib.util.spec_from_file_location("workflow_recovery", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def plans(workflow):
    # Reuse the canonical test fixture without coupling production code to it.
    fixture = ROOT / "tests/test_workflow_helper.py"
    spec = importlib.util.spec_from_file_location("workflow_fixture", fixture)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.valid_slide_plans(("Intro", "A", "cover"))


class WorkflowRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.w = load_workflow()
        self.tmp = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmp.name) / "output"
        self.output_root.mkdir()
        self.previous_output = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.run = self.output_root / "deck"
        self.w.init_state(self.run, topic="Test", audience="management", pages="1", research="")
        self.w.write_json(self.run / "slide-plans.json", plans(self.w))
        self.preview = self.w.preview_artifact(self.run, "slide_plans")
        self.w.write_json(self.run / ".workflow/task-brief.json", {
            "objective": "test", "constraints": [], "source_paths": [], "pending_work": []
        })
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact="slide_plans"))

    def tearDown(self):
        if self.previous_output is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output
        self.tmp.cleanup()

    def test_changed_plan_invalidates_approval_and_same_preview_does_not(self):
        self.w.preview_artifact(self.run, "slide_plans")
        self.assertTrue(self.w.load_state(self.run)["approvals"]["slide_plans"])
        data = self.w.read_json(self.run / "slide-plans.json")
        data["slides"][0]["title"] = "Changed"
        self.w.write_json(self.run / "slide-plans.json", data)
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.w.require_approved(self.run, "slide_plans")

    def test_direct_approve_rejects_changed_plan_or_preview(self):
        data = self.w.read_json(self.run / "slide-plans.json")
        data["slides"][0]["title"] = "Direct change"
        self.w.write_json(self.run / "slide-plans.json", data)
        with self.assertRaises(RuntimeError):
            self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact="slide_plans"))
        self.w.preview_artifact(self.run, "slide_plans")
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact="slide_plans"))
        preview = self.run / self.w.PREVIEW_FILES["slide_plans"]
        preview.write_text(preview.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.w.require_approved(self.run, "slide_plans")

    def test_reinit_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "already initialized"):
            self.w.init_state(self.run, topic="Other", audience="x", pages="1", research="")

    def test_nonempty_run_without_state_cannot_be_reinitialized(self):
        target = self.output_root / "orphan"
        target.mkdir()
        (target / "outline.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.w.init_state(target, topic="Other", audience="x", pages="1", research="")

    def test_legacy_boolean_approval_without_hashes_is_rejected(self):
        state = self.w.load_state(self.run)
        state["approvals"]["slide_plans"] = True
        state["artifacts"]["slide_plans"].pop("sha256", None)
        state["artifacts"]["slide_plans"].pop("preview_sha256", None)
        self.w.save_state(self.run, state)
        with self.assertRaises(RuntimeError):
            self.w.require_approved(self.run, "slide_plans")

    def test_render_jobs_record_hashes_and_prune_obsolete(self):
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.run), renderer="pptd", source="plans"))
        jobs = self.w.prepare_render_jobs(self.run, "pptd")
        extra = jobs.parent / "slide-99.json"
        extra.write_text("{}", encoding="utf-8")
        self.w.prepare_render_jobs(self.run, "pptd")
        self.assertFalse(extra.exists())
        manifest = self.w.read_json(jobs)
        self.assertEqual(manifest["plan_sha256"], self.w.file_sha256(self.run / "slide-plans.json"))
        self.assertEqual(manifest["task_brief_sha256"], self.w.task_brief_hash(self.run))

    def test_upstream_raw_change_invalidates_downstream_approval(self):
        self.w.write_json(self.run / "outline.json", {"pages": [{"title": "Intro"}]})
        self.w.preview_artifact(self.run, "outline")
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact="outline"))
        self.w.write_json(self.run / "contents.json", {"pages": [{"title": "Intro", "body": "A"}]})
        self.w.preview_artifact(self.run, "contents")
        self.w.cmd_approve(Namespace(run_dir=str(self.run), artifact="contents"))
        self.w.write_json(self.run / "outline.json", {"pages": [{"title": "Changed"}]})
        self.w.preview_artifact(self.run, "outline")
        with self.assertRaises(RuntimeError):
            self.w.require_approved(self.run, "contents")

    def test_brief_constraint_change_stales_jobs_but_pending_work_does_not(self):
        self.w.cmd_choose_renderer(Namespace(run_dir=str(self.run), renderer="pptd", source="plans"))
        self.w.prepare_render_jobs(self.run, "pptd")
        brief = self.run / "brief.json"
        brief.write_text(json.dumps({"objective": "x", "constraints": ["cost"], "source_paths": [], "pending_work": []}), encoding="utf-8")
        self.w.cmd_checkpoint(Namespace(run_dir=str(self.run), file=str(brief)))
        state = self.w.load_state(self.run)
        self.assertEqual(state["renderers"]["pptd"]["jobs"]["status"], "stale")
        self.w.prepare_render_jobs(self.run, "pptd")
        brief.write_text(json.dumps({"objective": "x", "constraints": ["cost"], "source_paths": [], "pending_work": ["review"]}), encoding="utf-8")
        self.w.cmd_checkpoint(Namespace(run_dir=str(self.run), file=str(brief)))
        self.assertNotEqual(self.w.load_state(self.run)["renderers"]["pptd"]["jobs"].get("status"), "stale")

    def test_checkpoint_rejects_secret_and_resume_is_compact(self):
        brief = self.run / "brief.json"
        brief.write_text(json.dumps({"objective": "Make deck", "constraints": [], "source_paths": [], "pending_work": [], "next_action": "review"}), encoding="utf-8")
        self.w.cmd_checkpoint(Namespace(run_dir=str(self.run), file=str(brief)))
        saved = self.w.read_json(self.run / ".workflow/task-brief.json")
        self.assertEqual(saved["objective"], "Make deck")
        bad = self.run / "bad.json"
        bad.write_text(json.dumps({"objective": "x", "constraints": ["API_KEY=abc"], "source_paths": [], "pending_work": []}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.w.cmd_checkpoint(Namespace(run_dir=str(self.run), file=str(bad)))

        # Ensure the resume output is JSON and points at the canonical previews.
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.cmd_resume(Namespace(run_dir=str(self.run)))
        resumed = json.loads(out.getvalue())
        self.assertEqual(resumed["previews"]["slide_plans"].replace("\\", "/").split("/")[-2], ".workflow")

    def test_resume_reads_finalized_delivery_metadata_without_granting_approval(self):
        finalized = self.output_root / "finalized"
        finalized.mkdir()
        data = plans(self.w)
        data["_delivery"] = {"version": 1, "renderer": "img", "exports": [{"path": "deck.pptx"}]}
        self.w.write_json(finalized / "slide-plans.json", data)
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.w.cmd_resume(Namespace(run_dir=str(finalized)))
        resumed = json.loads(out.getvalue())
        self.assertNotEqual(resumed["state"], "delivered")


if __name__ == "__main__":
    unittest.main()
