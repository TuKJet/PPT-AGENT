from __future__ import annotations

import importlib.util
import os
import shutil
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
        self.output_root = Path(self.tmpdir.name) / "output-root"
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.run_dir = self.output_root / "review-flow"
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
        if self.previous_output_dir is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output_dir
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


class WorkflowHelperRunDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmpdir.name) / "output-root"
        self.repo_root = Path(__file__).resolve().parents[1]
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)

    def tearDown(self) -> None:
        if self.previous_output_dir is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output_dir
        for name in ("deck-run-relative", "deck-run-preview"):
            accidental = self.repo_root / name
            if accidental.exists():
                shutil.rmtree(accidental, ignore_errors=True)
        self.tmpdir.cleanup()

    def test_init_places_relative_run_dir_under_output_root(self) -> None:
        relative = "deck-run-relative"
        expected = self.output_root / relative
        accidental = self.repo_root / relative

        self.workflow.cmd_init(
            Namespace(
                topic="Test Topic",
                audience="Test Audience",
                pages="3",
                research="",
                run_dir=relative,
            )
        )

        self.assertTrue((expected / "workflow-state.json").exists())
        self.assertFalse(accidental.exists())

    def test_preview_uses_same_relative_run_dir_mapping(self) -> None:
        relative = "deck-run-preview"
        expected = self.output_root / relative
        outline = {
            "pages": [
                {
                    "title": "Intro",
                    "sections": ["One"],
                }
            ]
        }

        self.workflow.cmd_init(
            Namespace(
                topic="Test Topic",
                audience="Test Audience",
                pages="3",
                research="",
                run_dir=relative,
            )
        )
        self.workflow.write_json(expected / "outline.json", outline)

        self.workflow.cmd_preview(Namespace(run_dir=relative, artifact="outline"))

        self.assertTrue((expected / "outline-preview.md").exists())
