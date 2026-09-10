from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree


def load_workflow_module():
    path = Path(__file__).resolve().parents[1] / ".codex" / "skills" / "ppt-deck-workflow" / "scripts" / "workflow.py"
    spec = importlib.util.spec_from_file_location("workflow_helper", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_slide_plans(*slides: tuple[str, str, str]) -> dict:
    slide_items = slides or (("Opening", "Alpha", "cover"),)
    return {
        "version": 2,
        "deck_strategy": {
            "primary_audience": "management",
            "decision_context": "Approve the recommended delivery path",
            "first_questions": ["Why now?", "What changes?", "What decision is needed?"],
            "evidence_order": ["Conclusion", "Evidence", "Risk", "Decision"],
            "presentation_posture": "Decision-led, confident, and evidence-bounded",
        },
        "design_system": {
            "theme_name": "Confident Blue",
            "audience_fit": "Polished management communication with disciplined density",
            "palette": {
                "background": "#F5F8FC",
                "surface": "#FFFFFF",
                "primary": "#1358A8",
                "accent": "#F2A900",
                "text_primary": "#132238",
                "text_muted": "#5F6F82",
            },
            "typography": {"title": "32pt semibold", "body": "18pt regular"},
            "component_rules": {"cards": "12px radius", "spacing": "8px rhythm"},
            "chart_treatment": {"style": "Direct labels with restrained grid lines"},
            "illustration_policy": "Use purposeful editorial illustrations when they improve comprehension.",
            "design_genes": ["Blue brand-led contrast", "Thin amber emphasis"],
        },
        "slides": [
            {
                "index": index,
                "title": title,
                "material": material,
                "page_role": page_role,
                "plan": {
                    "core_message": f"Core message for {title}",
                    "layout_structure": "Title band above a two-region main composition and quiet footer",
                    "visual_hierarchy": ["Title", "Primary evidence", "Supporting detail", "Footer"],
                    "required_elements": ["title", "main visual", "supporting card", "footer"],
                    "palette_tokens": ["background", "surface", "primary", "accent", "text_primary"],
                    "style_controls": {
                        "density": "medium",
                        "typography": "clear management hierarchy",
                        "visual_motif": "thin directional line",
                    },
                    "audience_controls": {
                        "technical_depth": "decision-relevant only",
                        "decision_orientation": "high",
                    },
                    "renderer_neutral_constraints": [
                        "Keep the title to two lines",
                        "Do not use renderer-specific implementation terms",
                    ],
                },
            }
            for index, (title, material, page_role) in enumerate(slide_items, start=1)
        ],
    }


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
        slide_plans = valid_slide_plans(("Intro", "A", "cover"))
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

    def test_slide_plan_approval_recommends_img_renderer(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.workflow.cmd_approve(
                Namespace(run_dir=str(self.run_dir), artifact="slide_plans")
            )

        self.assertIn("next=choose-renderer", output.getvalue())
        self.assertIn("recommended_renderer=img", output.getvalue())


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
        slide_plans = valid_slide_plans(
            ("Opening", "Alpha", "cover"),
            ("Roadmap", "Beta", "summary"),
        )
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
        self.assertEqual(shared["deck_strategy"], slide_job["deck_strategy"])
        self.assertEqual(shared["design_system"], slide_job["design_system"])
        self.assertEqual(shared["design_system"]["palette"]["primary"], "#1358A8")
        self.assertEqual(slide_job["renderer"], "html")
        self.assertEqual(
            Path(slide_job["target_path"]).resolve(),
            self.workflow.render_target_path(self.run_dir, "html", 1, "Opening").resolve(),
        )
        self.assertEqual(Path(slide_job["shared_context_path"]).resolve(), (jobs_root / "shared-context.json").resolve())

    def test_slide_plan_preview_exposes_deck_strategy_and_design_system(self) -> None:
        preview = (self.run_dir / "slide-plans-preview.md").read_text(encoding="utf-8")

        self.assertIn("# 幻灯片规划预览", preview)
        self.assertIn("## 全局叙事策略", preview)
        self.assertIn("## 全局设计规范", preview)
        self.assertIn("Confident Blue", preview)
        self.assertIn("#1358A8", preview)
        self.assertIn("| 主色 | `primary` | `#1358A8` |", preview)
        self.assertIn("## 第 01 页｜Opening", preview)
        self.assertIn("> **核心信息**", preview)
        self.assertIn("### 页面布局", preview)
        self.assertIn("### 本页配色", preview)
        self.assertIn("受众控制与渲染通用约束已通过校验", preview)
        self.assertNotIn("### 受众与表达控制", preview)
        self.assertNotIn("### 渲染通用约束", preview)
        self.assertNotIn("```json", preview)
        self.assertNotIn('"primary_audience"', preview)
        self.assertNotIn('"layout_structure"', preview)

    def test_fresh_one_page_slide_plan_smoke_flow_is_human_readable(self) -> None:
        smoke_run = self.output_root / "fresh-one-page-preview-smoke"
        self.workflow.init_state(
            smoke_run,
            topic="客服知识库稳定运营价值",
            audience="业务负责人",
            pages="1",
            research="No external research; preview formatting smoke test",
        )
        smoke_plans = valid_slide_plans(("知识库持续更新，把重复答疑转化为稳定服务能力", "Fresh", "content"))
        smoke_plans["deck_strategy"] = {
            "primary_audience": "客服与运营负责人",
            "decision_context": "确认知识库运营岗位的持续投入价值",
            "first_questions": [
                "日常维护解决了什么业务问题？",
                "岗位缺位会怎样影响响应效率？",
            ],
            "evidence_order": [
                "稳定服务价值",
                "缺位损失链",
                "管理结论",
            ],
            "presentation_posture": "结论先行、业务语言、风险与价值平衡",
        }
        smoke_plans["design_system"].update({
            "theme_name": "稳定服务蓝",
            "audience_fit": "用企业蓝表达稳定，用橙色提示知识过期风险",
            "design_genes": ["单一结论焦点", "价值与风险双栏", "低噪声信息卡"],
        })
        smoke_plans["slides"][0]["plan"].update({
            "core_message": "持续维护让知识可复用；岗位缺位会迅速放大重复答疑与口径不一致。",
            "layout_structure": "顶部结论标题；左侧价值卡；右侧缺位损失链；底部管理结论条。",
            "visual_hierarchy": [
                "标题建立岗位判断",
                "左侧稳定服务价值",
                "右侧缺位风险",
                "底部管理结论",
            ],
            "required_elements": [
                "标题与一句副标题",
                "知识沉淀价值卡",
                "缺位损失三步链",
                "管理结论条",
            ],
        })
        self.workflow.write_json(smoke_run / "slide-plans.json", smoke_plans)

        self.workflow.cmd_preview(
            Namespace(run_dir=str(smoke_run), artifact="slide_plans")
        )

        preview_path = smoke_run / "slide-plans-preview.md"
        preview = preview_path.read_text(encoding="utf-8")
        state = self.workflow.load_state(smoke_run)
        self.assertEqual(state["artifacts"]["slide_plans"]["status"], "pending_review")
        self.assertIn("客服与运营负责人", preview)
        self.assertIn("## 第 01 页｜知识库持续更新", preview)
        self.assertIn("岗位缺位会迅速放大重复答疑", preview)
        self.assertIn("| 页面背景 | `background` | `#F5F8FC` |", preview)
        self.assertIn("页面背景 `#F5F8FC` · 卡片/表面 `#FFFFFF`", preview)
        self.assertNotIn("```", preview)
        self.assertNotIn('{"', preview)

    def test_version_two_slide_plans_require_complete_palette_tokens(self) -> None:
        invalid = valid_slide_plans()
        invalid["design_system"]["palette"] = {"primary": "#1358A8"}

        with self.assertRaisesRegex(ValueError, "missing required tokens"):
            self.workflow.validate_slide_plans(invalid)

    def test_legacy_version_one_slide_plans_are_rejected(self) -> None:
        invalid = {
            "version": 1,
            "slides": [
                {
                    "index": 1,
                    "title": "Opening",
                    "material": "Alpha",
                    "plan": "Only a free-form core message",
                    "page_role": "cover",
                }
            ],
        }

        with self.assertRaisesRegex(ValueError, "legacy version 1/free-form plans"):
            self.workflow.validate_slide_plans(invalid)

    def test_slide_plan_requires_structured_layout_and_style_fields(self) -> None:
        invalid = valid_slide_plans()
        invalid["slides"][0]["plan"] = {"core_message": "Only the core message survived"}

        with self.assertRaisesRegex(ValueError, "layout_structure"):
            self.workflow.validate_slide_plans(invalid)

    def test_version_two_free_form_slide_plan_is_rejected(self) -> None:
        invalid = valid_slide_plans()
        invalid["slides"][0]["plan"] = "Core message plus loosely embedded layout prose"

        with self.assertRaisesRegex(ValueError, r"slides\[0\]\.plan must be an object"):
            self.workflow.validate_slide_plans(invalid)

    def test_slide_plan_rejects_palette_aliases_not_defined_by_design_system(self) -> None:
        invalid = valid_slide_plans()
        invalid["slides"][0]["plan"]["palette_tokens"].append("brand_blue")

        with self.assertRaisesRegex(ValueError, "unknown design_system.palette tokens: brand_blue"):
            self.workflow.validate_slide_plans(invalid)


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
        slide_plans = valid_slide_plans(("Opening", "Alpha", "cover"))
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

    def prepare_img_svg_text_and_crops(
        self,
        page: dict,
        *,
        crops: list[dict] | None = None,
        visible_text_items: list[dict] | None = None,
    ) -> dict:
        crop_items = list(crops or [])
        if visible_text_items is None:
            svg_root = ElementTree.fromstring(Path(page["target_path"]).read_text(encoding="utf-8"))
            visible_text_items = [
                {"id": f"text-{index}", "text": "".join(node.itertext())}
                for index, node in enumerate(
                    (item for item in svg_root.iter() if item.tag.rsplit("}", 1)[-1] == "text"),
                    start=1,
                )
            ]
        crop_manifest = {
            "version": 3,
            "source_image_path": page["source_image_path"],
            "svg_path": page["target_path"],
            "canvas": {"width": 1280, "height": 720},
            "visible_text": list(visible_text_items or []),
            "crops": crop_items,
        }
        if not crop_items:
            crop_manifest["no_crops_reason"] = "No raster crop is needed for this synthetic slide."
        crop_path = Path(page["crop_manifest_path"])
        if crop_items:
            self.workflow.write_json(crop_path, crop_manifest)
        elif crop_path.exists():
            crop_path.unlink()
        page["visible_text"] = list(visible_text_items or [])
        jobs_manifest_path = self.run_dir / "render-jobs" / "img-svg" / "manifest.json"
        jobs_manifest = json.loads(jobs_manifest_path.read_text(encoding="utf-8"))
        jobs_manifest["slides"][int(page["index"]) - 1] = page
        self.workflow.write_json(jobs_manifest_path, jobs_manifest)
        return page

    def fake_render_review(self, source_path: Path, svg_path: Path, preview_path: Path) -> dict:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(Path(source_path).read_bytes())
        return {
            "pixel_similarity": 1.0,
            "edge_similarity": 1.0,
            "combined_similarity": 1.0,
            "recommended_minimum": 0.0,
        }

    def complete_img_svg_after_review(self, page: dict) -> None:
        with mock.patch.object(
            self.workflow,
            "render_img_svg_review",
            side_effect=self.fake_render_review,
        ):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

            review_path = Path(page["fidelity_review_path"])
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review.update({
                "status": "pass",
                "text_checked": True,
                "reviewer": "unit-test-reviewer",
                "notes": "Source and rendered preview match for the synthetic test slide.",
            })
            self.workflow.write_json(review_path, review)
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

    def test_img_svg_choice_is_rejected_before_img_export(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "only available after"):
            self.workflow.cmd_choose_img_svg(
                Namespace(run_dir=str(self.run_dir), mode="on")
            )

    def test_img_export_completes_and_leaves_svg_as_optional_opt_in(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            pptx_path = self.export_img()

        state = self.workflow.load_state(self.run_dir)
        conversion = state["renderers"]["img"]["svg_conversion"]
        self.assertTrue(pptx_path.exists())
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["renderers"]["img"]["status"], "completed")
        self.assertEqual(conversion["status"], "available")
        self.assertTrue(conversion["requires_explicit_opt_in"])
        self.assertTrue(conversion["additional_model_usage_required"])
        self.assertIn("completed=", output.getvalue())
        self.assertIn("workflow_complete=yes", output.getvalue())
        self.assertIn("user_reply_required=no", output.getvalue())
        self.assertIn("offer_img_svg=yes", output.getvalue())
        self.assertIn("img_svg_conversion=available_on_explicit_request", output.getvalue())
        self.assertIn("img_svg_editability=powerpoint-convert-to-shape", output.getvalue())
        self.assertIn("img_svg_additional_model_usage=yes", output.getvalue())
        self.assertNotIn("next=ask-user-img-svg", output.getvalue())

    def test_legacy_img_svg_off_remains_a_noop_compatibility_path(self) -> None:
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

    def test_legacy_pending_choice_state_normalizes_to_completed_available(self) -> None:
        self.export_img()
        raw_state = json.loads(
            (self.run_dir / "workflow-state.json").read_text(encoding="utf-8")
        )
        raw_state["version"] = 5
        raw_state["status"] = "img_svg_choice_pending"
        raw_state["renderers"]["img"]["status"] = "img_svg_choice_pending"
        raw_state["renderers"]["img"]["svg_conversion"]["status"] = "pending_choice"
        self.workflow.write_json(self.run_dir / "workflow-state.json", raw_state)

        state = self.workflow.load_state(self.run_dir)
        conversion = state["renderers"]["img"]["svg_conversion"]
        self.assertEqual(state["version"], 6)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["renderers"]["img"]["status"], "completed")
        self.assertEqual(conversion["status"], "available")
        self.assertTrue(conversion["requires_explicit_opt_in"])
        self.assertTrue(conversion["additional_model_usage_required"])

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
        self.assertEqual(
            Path(page["crop_manifest_path"]).name,
            "slide-01-crops.json",
        )
        self.assertFalse(Path(page["crop_manifest_path"]).exists())

        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            "<text x='80' y='120'>Opening</text></svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(page)
        self.complete_img_svg_after_review(page)

        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "img_svg_export_ready")
        self.assertEqual(state["renderers"]["img"]["svg_conversion"]["status"], "completed")

        export_output = io.StringIO()
        with redirect_stdout(export_output):
            self.workflow.cmd_export_img_svg(Namespace(run_dir=str(self.run_dir)))
        state = self.workflow.load_state(self.run_dir)
        vector_pptx = self.run_dir / self.workflow.renderer_pptx_name(self.run_dir, "img-svg")
        self.assertTrue(vector_pptx.exists())
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["renderers"]["img"]["svg_conversion"]["status"], "exported")
        self.assertIn(
            "post_export_guidance=office-convert-svg-to-shape",
            export_output.getvalue(),
        )
        self.assertIn(
            "office_editability=vector-shapes-not-semantic-text-or-charts",
            export_output.getvalue(),
        )
        self.assertEqual(
            Path(state["renderers"]["img"]["artifacts"]["svg_pptx"]["path"]).resolve(),
            vector_pptx.resolve(),
        )

    def test_img_svg_accepts_embedded_crop_images(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="on")
        )
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        Path(manifest["slides"][0]["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            "<image data-crop-id='icon' x='100' y='100' width='64' height='64' "
            "href='data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='/>"
            "</svg>",
            encoding="utf-8",
        )
        page = manifest["slides"][0]
        self.prepare_img_svg_text_and_crops(
            page,
            crops=[{
                "id": "icon",
                "source_box": [100, 100, 64, 64],
                "content_type": "decorative_symbol",
                "contains_text": False,
                "text_exclusion_boxes": [],
                "preserve_aspect_ratio": "none",
            }],
        )
        self.complete_img_svg_after_review(page)

        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "img_svg_export_ready")

    def test_img_svg_accepts_text_scrubbed_complex_backplate(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="on")
        )
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            f"<image data-crop-id='rank-plaque' x='100' y='100' width='200' height='100' href='data:image/png;base64,{png}'/>"
            "<text x='140' y='150' font-size='28'>第1名</text>"
            "</svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            visible_text_items=[{
                "id": "tier-1-rank",
                "text": "第1名",
                "source_box": [140, 125, 80, 35],
            }],
            crops=[{
                "id": "rank-plaque",
                "source_box": [100, 100, 200, 100],
                "content_type": "complex_backplate",
                "source_contains_text": True,
                "contains_text": False,
                "text_removal_boxes": [[135, 120, 100, 45]],
                "replacement_text_ids": ["tier-1-rank"],
                "text_removal_mode": "light_neutral",
                "text_removal_dilation": 2,
                "text_exclusion_boxes": [],
                "preserve_aspect_ratio": "none",
            }],
        )
        self.complete_img_svg_after_review(page)

        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "img_svg_export_ready")

    def test_img_svg_rejects_backplate_when_replacement_text_is_below_image(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            "<text x='140' y='150' font-size='28'>第1名</text>"
            f"<image data-crop-id='rank-plaque' x='100' y='100' width='200' height='100' href='data:image/png;base64,{png}'/>"
            "</svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            visible_text_items=[{
                "id": "tier-1-rank",
                "text": "第1名",
                "source_box": [140, 125, 80, 35],
            }],
            crops=[{
                "id": "rank-plaque",
                "source_box": [100, 100, 200, 100],
                "content_type": "complex_backplate",
                "source_contains_text": True,
                "contains_text": False,
                "text_removal_boxes": [[135, 120, 100, 45]],
                "replacement_text_ids": ["tier-1-rank"],
                "text_removal_mode": "light_neutral",
                "text_removal_dilation": 2,
                "text_exclusion_boxes": [],
            }],
        )
        with self.assertRaisesRegex(ValueError, "replacement text must appear after"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

    def test_img_svg_rejects_visible_text_missing_from_svg_text_nodes(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/></svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            visible_text_items=[{
                "id": "opening-title",
                "text": "Opening",
                "source_box": [80, 80, 180, 50],
            }],
        )
        with self.assertRaisesRegex(ValueError, "visible text missing from SVG text nodes"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

    def _prepare_backplate_case(
        self,
        *,
        text_removal_boxes: list[list[float]],
        text_removal_mode: str = "light_neutral",
    ) -> dict:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            f"<image data-crop-id='rank-plaque' x='100' y='100' width='200' height='100' href='data:image/png;base64,{png}'/>"
            "<text x='140' y='150' font-size='28'>第1名</text></svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            visible_text_items=[{"id": "tier-1-rank", "text": "第1名", "source_box": [140, 125, 80, 35]}],
            crops=[{
                "id": "rank-plaque",
                "source_box": [100, 100, 200, 100],
                "content_type": "complex_backplate",
                "source_contains_text": True,
                "contains_text": False,
                "text_removal_boxes": text_removal_boxes,
                "replacement_text_ids": ["tier-1-rank"],
                "text_removal_mode": text_removal_mode,
                "text_removal_dilation": 2,
            }],
        )
        return page

    def test_img_svg_rejects_backplate_removal_box_outside_crop(self) -> None:
        self._prepare_backplate_case(text_removal_boxes=[[90, 120, 100, 45]])
        with self.assertRaisesRegex(ValueError, "text_removal_box must stay inside"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

    def test_img_svg_rejects_invalid_backplate_removal_parameter(self) -> None:
        self._prepare_backplate_case(
            text_removal_boxes=[[135, 120, 100, 45]],
            text_removal_mode="unsupported",
        )
        with self.assertRaisesRegex(ValueError, "text_removal_mode is invalid"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))

    def test_img_svg_accepts_a_no_crop_page_without_crop_manifest_requirements(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/><text x='80' y='120'>Opening</text></svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            visible_text_items=[{"id": "opening", "text": "Opening"}],
        )
        self.complete_img_svg_after_review(page)
        state = self.workflow.load_state(self.run_dir)
        self.assertEqual(state["status"], "img_svg_export_ready")

    def test_img_svg_accepts_faithful_vector_icon_without_source_crop(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/><path d='M100 100h40v40z' fill='#1358a8'/></svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(page)
        self.complete_img_svg_after_review(page)
        self.assertEqual(self.workflow.load_state(self.run_dir)["status"], "img_svg_export_ready")

    def test_img_svg_accepts_a_legal_large_photo_crop(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(Namespace(run_dir=str(self.run_dir), mode="on"))
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        page = manifest["slides"][0]
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        Path(page["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            f"<image data-crop-id='photo' x='100' y='100' width='500' height='300' href='data:image/png;base64,{png}'/>"
            "</svg>",
            encoding="utf-8",
        )
        self.prepare_img_svg_text_and_crops(
            page,
            crops=[{"id": "photo", "source_box": [100, 100, 500, 300], "content_type": "photo", "contains_text": False}],
        )
        self.complete_img_svg_after_review(page)
        self.assertEqual(self.workflow.load_state(self.run_dir)["status"], "img_svg_export_ready")

    def test_img_svg_rejects_a_full_slide_raster_wrapper(self) -> None:
        self.export_img()
        self.workflow.cmd_choose_img_svg(
            Namespace(run_dir=str(self.run_dir), mode="on")
        )
        manifest = json.loads(
            (self.run_dir / "render-jobs" / "img-svg" / "manifest.json").read_text(encoding="utf-8")
        )
        Path(manifest["slides"][0]["target_path"]).write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect width='1280' height='720' fill='#ffffff'/>"
            "<image x='0' y='0' width='1280' height='720' "
            "href='data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='/>"
            "</svg>",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "full-page <image>"):
            self.workflow.cmd_complete_img_svg(Namespace(run_dir=str(self.run_dir)))
