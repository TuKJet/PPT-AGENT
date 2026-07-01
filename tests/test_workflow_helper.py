from __future__ import annotations

import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


def load_workflow_module():
    path = Path(__file__).resolve().parents[1] / ".codex" / "skills" / "ppt-deck-workflow" / "scripts" / "workflow.py"
    spec = importlib.util.spec_from_file_location("workflow_helper", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WorkflowHelperReviewFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmpdir.name)
        self.workflow.init_state(
            self.run_dir,
            topic="Test Topic",
            audience="Test Audience",
            pages="3",
            research="",
        )
        slide_plans = {
            "version": 1,
            "slides": [
                {
                    "index": 1,
                    "title": "Intro",
                    "material": "A",
                    "plan": "B",
                    "page_role": "cover",
                }
            ],
        }
        self.workflow.write_json(self.run_dir / "slide-plans.json", slide_plans)
        self.workflow.write_plans_preview(slide_plans, self.run_dir / "slide-plans-preview.md")
        state = self.workflow.load_state(self.run_dir)
        self.workflow.mark_artifact(
            self.run_dir,
            state,
            "slide_plans",
            self.run_dir / "slide-plans.json",
            self.run_dir / "slide-plans-preview.md",
        )
        self.workflow.cmd_approve(Namespace(run_dir=str(self.run_dir), artifact="slide_plans"))

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_html_renderer_requires_explicit_review_choice(self) -> None:
        self.workflow.cmd_choose_renderer(Namespace(run_dir=str(self.run_dir), renderer="html"))

        with self.assertRaisesRegex(RuntimeError, "review preference"):
            self.workflow.ensure_render_ready(self.run_dir, "html")

    def test_review_on_requires_completion_before_export(self) -> None:
        self.workflow.cmd_choose_renderer(Namespace(run_dir=str(self.run_dir), renderer="svg"))
        self.workflow.cmd_choose_review(Namespace(run_dir=str(self.run_dir), mode="on"))

        with self.assertRaisesRegex(RuntimeError, "review subflow"):
            self.workflow.ensure_render_ready(self.run_dir, "svg")

    def test_review_off_allows_render_readiness(self) -> None:
        self.workflow.cmd_choose_renderer(Namespace(run_dir=str(self.run_dir), renderer="html"))
        self.workflow.cmd_choose_review(Namespace(run_dir=str(self.run_dir), mode="off"))

        self.workflow.ensure_render_ready(self.run_dir, "html")


if __name__ == "__main__":
    unittest.main()
