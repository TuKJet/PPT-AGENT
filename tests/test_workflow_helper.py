from __future__ import annotations

import importlib.util
import base64
import json
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


class WorkflowHelperMultiRendererStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmpdir.name) / "output-root"
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.run_dir = self.output_root / "multi-render"
        self.workflow.init_state(
            self.run_dir,
            topic="Compare Topic",
            audience="Test Audience",
            pages="4",
            research="",
        )

    def tearDown(self) -> None:
        if self.previous_output_dir is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output_dir
        self.tmpdir.cleanup()

    def test_completed_renderer_artifacts_are_tracked_without_overwriting_peers(self) -> None:
        html_pptx = self.run_dir / "compare-topic-html.pptx"
        img_pptx = self.run_dir / "compare-topic-img.pptx"

        self.workflow.mark_completed(self.run_dir, "html", {"pptx": html_pptx})
        self.workflow.mark_completed(self.run_dir, "img", {"pptx": img_pptx})

        state = self.workflow.load_state(self.run_dir)

        self.assertIn("renderers", state)
        self.assertEqual(state["renderers"]["html"]["artifacts"]["pptx"]["path"], str(html_pptx))
        self.assertEqual(state["renderers"]["img"]["artifacts"]["pptx"]["path"], str(img_pptx))
        self.assertEqual(state["renderer"], "img")


class WorkflowHelperRenderJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmpdir.name) / "output-root"
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.run_dir = self.output_root / "render-jobs"
        self.workflow.init_state(
            self.run_dir,
            topic="Subagent Topic",
            audience="Management",
            pages="2",
            research="",
        )
        slide_plans = {
            "version": 1,
            "slides": [
                {
                    "index": 1,
                    "title": "Opening",
                    "material": "Alpha",
                    "plan": "Use a focused cover layout",
                    "page_role": "cover",
                },
                {
                    "index": 2,
                    "title": "Roadmap",
                    "material": "Beta",
                    "plan": "Use a two-column summary layout",
                    "page_role": "summary",
                },
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

    def test_prepare_render_jobs_writes_shared_and_per_slide_context(self) -> None:
        self.workflow.cmd_prepare_render_jobs(Namespace(run_dir=str(self.run_dir), renderer="html"))

        jobs_root = self.run_dir / "render-jobs" / "html"
        manifest = json.loads((jobs_root / "manifest.json").read_text(encoding="utf-8"))
        shared = json.loads((jobs_root / "shared-context.json").read_text(encoding="utf-8"))
        slide_job = json.loads((jobs_root / "slide-01.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["renderer"], "html")
        self.assertEqual(manifest["slide_count"], 2)
        self.assertEqual(shared["topic"], "Subagent Topic")
        self.assertEqual(len(shared["slides"]), 2)
        self.assertEqual(slide_job["renderer"], "html")
        self.assertEqual(
            Path(slide_job["target_path"]).resolve(),
            self.workflow.render_target_path(self.run_dir, "html", 1, "Opening").resolve(),
        )
        self.assertEqual(Path(slide_job["shared_context_path"]).resolve(), (jobs_root / "shared-context.json").resolve())


class WorkflowHelperImgSvgFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = load_workflow_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.output_root = Path(self.tmpdir.name) / "output-root"
        self.previous_output_dir = os.environ.get("OUTPUT_DIR")
        os.environ["OUTPUT_DIR"] = str(self.output_root)
        self.run_dir = self.output_root / "img-svg-flow"
        self.workflow.init_state(
            self.run_dir,
            topic="IMG SVG Topic",
            audience="Management",
            pages="1",
            research="",
        )
        slide_plans = {
            "version": 1,
            "slides": [
                {
                    "index": 1,
                    "title": "Opening",
                    "material": "Alpha",
                    "plan": "A focused page",
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
        self.workflow.cmd_choose_renderer(Namespace(run_dir=str(self.run_dir), renderer="img"))
        img_dir = self.run_dir / "img"
        img_dir.mkdir(parents=True)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        (img_dir / "slide-01-opening.png").write_bytes(png)

    def tearDown(self) -> None:
        if self.previous_output_dir is None:
            os.environ.pop("OUTPUT_DIR", None)
        else:
            os.environ["OUTPUT_DIR"] = self.previous_output_dir
        self.tmpdir.cleanup()

    def export_img(self) -> Path:
        self.workflow.cmd_export(
            Namespace(run_dir=str(self.run_dir), renderer=None, editable_engine=None)
        )
        return self.run_dir / self.workflow.renderer_pptx_name(self.run_dir, "img")

    def test_img_svg_choice_is_rejected_before_img_export(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "only allowed after"):
            self.workflow.cmd_choose_img_svg(
                Namespace(run_dir=str(self.run_dir), mode="on")
            )

    def test_img_export_stops_at_required_svg_choice(self) -> None:
        pptx_path = self.export_img()

        state = self.workflow.load_state(self.run_dir)
        conversion = state["renderers"]["img"]["svg_conversion"]
        self.assertTrue(pptx_path.exists())
        self.assertEqual(state["status"], "img_svg_choice_pending")
        self.assertEqual(conversion["status"], "pending_choice")
        self.assertTrue(conversion["requested_after_img_export"])

    def test_img_svg_off_completes_with_original_img_ppt(self) -> None:
        pptx_path = self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="off")
        )

        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["renderers"]["img"]["svg_conversion"]["status"], "skipped")
        self.assertEqual(
            Path(state["renderers"]["img"]["artifacts"]["pptx"]["path"]).resolve(),
            pptx_path.resolve(),
        )

    def test_img_svg_on_creates_direct_image_model_jobs_and_validates_outputs(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="on")
        )

        manifest_path = self.run_dir / "render-jobs" / "img-svg" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        page = manifest["slides"][0]
        self.assertEqual(
            Path(page["source_image_path"]).resolve(),
            (self.run_dir / "img" / "slide-01-opening.png").resolve(),
        )
        self.assertEqual(
            Path(page["target_path"]).parent.resolve(),
            (self.run_dir / "img-svg").resolve(),
        )

        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            "<text x='80' y='120'>Opening</text></svg>",
            encoding="utf-8",
        )
        self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "img_svg_export_ready")
        self.assertEqual(state["renderers"]["img"]["svg_conversion"]["status"], "completed")

        self.workflow.cmd_export_img_svg(Namespace(run_dir=str(self.run_dir)))
        state = self.workflow.load_state(self.run_dir)
        vector_pptx = self.run_dir / self.workflow.renderer_pptx_name(self.run_dir, "img-svg")
        self.assertTrue(vector_pptx.exists())
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["renderers"]["img"]["svg_conversion"]["status"], "exported")
        self.assertEqual(
            Path(state["renderers"]["img"]["artifacts"]["svg_pptx"]["path"]).resolve(),
            vector_pptx.resolve(),
        )

    def test_img_svg_rejects_raster_wrapped_as_svg(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="on")
        )
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        Path(manifest["slides"][0]["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<image href='data:image/png;base64,abc'/></svg>",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "forbidden <image>"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))
