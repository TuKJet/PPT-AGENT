import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl9dS4AAAAASUVORK5CYII="
)


class ImgRendererTests(unittest.TestCase):
    def test_env_example_only_exposes_minimal_krill_settings(self):
        env_example = Path("D:/work/PPT-AGENT/.env.example").read_text(encoding="utf-8")
        krill_keys = [
            line.split("=", 1)[0].strip()
            for line in env_example.splitlines()
            if line.startswith("KRILL_IMAGE_")
        ]

        self.assertEqual(
            ["KRILL_IMAGE_API_URL", "KRILL_IMAGE_API_KEY", "KRILL_IMAGE_MODEL"],
            krill_keys,
        )

    def test_skill_documents_img_generate_then_page_specific_edit_flow(self):
        skill_text = Path("D:/work/PPT-AGENT/.codex/skills/ppt-deck-workflow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("generate_image", skill_text)
        self.assertIn("edit_image", skill_text)
        self.assertIn("specific page", skill_text.lower())

    def test_skill_documents_compare_and_html_retry_guardrails(self):
        skill_text = Path("D:/work/PPT-AGENT/.codex/skills/ppt-deck-workflow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("archive", skill_text.lower())
        self.assertIn("compare", skill_text.lower())
        self.assertIn("HTML_USE_MIGRATED_CORE=false", skill_text)
        self.assertIn("playwright install chromium", skill_text)
        self.assertIn("provider/model", skill_text.lower())

    def test_compile_img_prompt_preserves_visible_text_and_strips_placeholders(self):
        from img_renderer import compile_img_prompt

        slide_job = {
            "index": 3,
            "title": "AI商业化路径",
            "material": "核心结论：行业进入以场景ROI驱动的落地阶段。",
            "plan": "\n".join([
                "左侧主标题：AI商业化路径",
                "右侧放三阶段路径图",
                "保留数字：2026、35%",
                "占位：后续补客户Logo",
                "TODO: 插入案例截图",
                "[图片]",
                "TBD",
            ]),
            "page_role": "summary",
        }

        prompt = compile_img_prompt(slide_job)

        self.assertIn("Slide title: AI商业化路径", prompt)
        self.assertIn("Page role: summary", prompt)
        self.assertIn("2026、35%", prompt)
        self.assertIn("行业进入以场景ROI驱动的落地阶段", prompt)
        self.assertNotIn("TODO", prompt)
        self.assertNotIn("TBD", prompt)
        self.assertNotIn("[图片]", prompt)
        self.assertNotIn("占位", prompt)

    def test_ensure_img_renderer_configured_raises_with_actionable_message(self):
        from img_renderer import ensure_img_renderer_configured

        with patch("img_renderer.missing_krill_image_settings", return_value=["KRILL_IMAGE_API_URL", "KRILL_IMAGE_API_KEY"]):
            with self.assertRaises(RuntimeError) as ctx:
                ensure_img_renderer_configured()

        message = str(ctx.exception)
        self.assertIn("KRILL_IMAGE_API_URL", message)
        self.assertIn("KRILL_IMAGE_API_KEY", message)
        self.assertIn("html", message)
        self.assertIn("svg", message)

    def test_render_img_generates_one_image_per_slide_and_exports_pptx(self):
        from img_renderer import render_img

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "demo-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "slide-plans.json").write_text(json.dumps({
                "version": 1,
                "slides": [
                    {
                        "index": 1,
                        "title": "封面",
                        "material": "企业级AI平台发展判断",
                        "plan": "主标题+副标题，右侧抽象视觉",
                        "page_role": "cover",
                    },
                    {
                        "index": 2,
                        "title": "商业化路径",
                        "material": "三阶段落地路径与关键指标",
                        "plan": "左文右图，保留数字 35%",
                        "page_role": "summary",
                    },
                ],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "workflow-state.json").write_text(json.dumps({
                "version": 1,
                "topic": "Demo Deck",
                "audience": "企业管理层",
                "provider": "openai",
                "status": "slide_plans_approved",
                "renderer": "img",
                "approvals": {"slide_plans": True},
                "artifacts": {},
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            captured_prompts = []

            class FakeClient:
                def generate_image(self, prompt: str, output_path: Path):
                    captured_prompts.append(prompt)
                    output_path.write_bytes(MINIMAL_PNG)
                    return output_path

            def fake_build_pptx_from_images(image_dir: Path, output_path: Path):
                output_path.write_bytes(b"pptx")
                return output_path

            with patch("img_renderer.ensure_img_renderer_configured", return_value=None), \
                 patch("img_renderer.KrillImageClient", return_value=FakeClient()), \
                 patch("img_renderer.build_pptx_from_images", side_effect=fake_build_pptx_from_images):
                pptx_path = render_img(run_dir)

            self.assertEqual(2, len(captured_prompts))
            self.assertTrue((run_dir / "img" / "01_封面.png").exists())
            self.assertTrue((run_dir / "img" / "02_商业化路径.png").exists())
            self.assertTrue((run_dir / "slide-status.json").exists())
            self.assertTrue(pptx_path.exists())

            state = json.loads((run_dir / "workflow-state.json").read_text(encoding="utf-8"))
            self.assertEqual("completed", state["status"])
            self.assertEqual("img", state["renderer"])
            self.assertIn("image_pptx", state["artifacts"])

    def test_revise_img_slide_uses_edit_image_and_updates_status(self):
        from img_renderer import revise_img_slide

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "demo-run"
            run_dir.mkdir(parents=True, exist_ok=True)
            img_dir = run_dir / "img"
            img_dir.mkdir(parents=True, exist_ok=True)
            original_image = img_dir / "02_商业化路径.png"
            original_image.write_bytes(MINIMAL_PNG)
            prompt_path = img_dir / "02_商业化路径.prompt.txt"
            prompt_path.write_text("original prompt", encoding="utf-8")
            (run_dir / "slide-plans.json").write_text(json.dumps({
                "version": 1,
                "slides": [
                    {
                        "index": 2,
                        "title": "商业化路径",
                        "material": "三阶段落地路径与关键指标",
                        "plan": "左文右图，保留数字 35%",
                        "page_role": "summary",
                    },
                ],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "workflow-state.json").write_text(json.dumps({
                "version": 1,
                "topic": "Demo Deck",
                "audience": "企业管理层",
                "provider": "openai",
                "status": "completed",
                "renderer": "img",
                "approvals": {"slide_plans": True},
                "artifacts": {"image_pptx": {"path": str(run_dir / "Demo_Deck.pptx"), "status": "completed"}},
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "slide-status.json").write_text(json.dumps({
                "slides": {
                    "02": {
                        "title": "商业化路径",
                        "page_role": "summary",
                        "validation_status": "pass",
                        "final_issues_count": 0,
                        "review_status": "SKIPPED",
                        "review_rounds": 0,
                        "export_ready": True,
                        "image_path": str(original_image),
                        "prompt_path": str(prompt_path),
                    }
                }
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            captured = {}

            class FakeClient:
                def edit_image(self, prompt: str, image_path: Path, output_path: Path, *, mask_path=None):
                    captured["prompt"] = prompt
                    captured["image_path"] = image_path
                    captured["output_path"] = output_path
                    output_path.write_bytes(MINIMAL_PNG)
                    return output_path

            def fake_build_pptx_from_images(image_dir: Path, output_path: Path):
                output_path.write_bytes(b"pptx")
                return output_path

            with patch("img_renderer.ensure_img_renderer_configured", return_value=None), \
                 patch("img_renderer.KrillImageClient", return_value=FakeClient()), \
                 patch("img_renderer.build_pptx_from_images", side_effect=fake_build_pptx_from_images):
                revised_path = revise_img_slide(run_dir, page_index=2, feedback="把右侧路径图改得更克制，增强标题层级")

            self.assertTrue(revised_path.exists())
            self.assertEqual(original_image, captured["image_path"])
            self.assertEqual(original_image, captured["output_path"])
            self.assertIn("更克制", captured["prompt"])
            self.assertIn("商业化路径", captured["prompt"])

            slide_status = json.loads((run_dir / "slide-status.json").read_text(encoding="utf-8"))
            self.assertEqual("REVISED", slide_status["slides"]["02"]["review_status"])
            self.assertEqual(1, slide_status["slides"]["02"]["review_rounds"])


class KrillImageClientTests(unittest.TestCase):
    def test_client_uses_openai_sdk_with_expected_defaults(self):
        from krill_image_client import KRILL_IMAGE_DEFAULT_QUALITY, KRILL_IMAGE_DEFAULT_SIZE, KRILL_IMAGE_TIMEOUT_SECONDS, KrillImageClient

        captured = {}

        class FakeImages:
            def generate(self, **kwargs):
                captured["generate_kwargs"] = kwargs
                class Result:
                    data = [type("ImageData", (), {"b64_json": base64.b64encode(MINIMAL_PNG).decode("utf-8")})()]
                return Result()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured["init_kwargs"] = kwargs
                self.images = FakeImages()

        with tempfile.TemporaryDirectory() as tmp, \
             patch("krill_image_client.OpenAI", FakeOpenAI), \
             patch("krill_image_client.KRILL_IMAGE_API_URL", "https://api.krill-ai.com/v1"), \
             patch("krill_image_client.KRILL_IMAGE_API_KEY", "test-krill-key"), \
             patch("krill_image_client.KRILL_IMAGE_MODEL", "gpt-image-2"), \
             patch("krill_image_client.missing_krill_image_settings", return_value=[]):
            out = Path(tmp) / "slide.png"
            client = KrillImageClient()
            result = client.generate_image("hello", out)
            self.assertTrue(result.exists())

        self.assertEqual("1280x720", KRILL_IMAGE_DEFAULT_SIZE)
        self.assertEqual("high", KRILL_IMAGE_DEFAULT_QUALITY)
        self.assertEqual(300, KRILL_IMAGE_TIMEOUT_SECONDS)
        self.assertEqual("https://api.krill-ai.com/v1", captured["init_kwargs"]["base_url"])
        self.assertEqual("test-krill-key", captured["init_kwargs"]["api_key"])
        self.assertEqual("gpt-image-2", captured["generate_kwargs"]["model"])
        self.assertEqual("hello", captured["generate_kwargs"]["prompt"])
        self.assertEqual("1280x720", captured["generate_kwargs"]["size"])
        self.assertEqual("high", captured["generate_kwargs"]["quality"])

    def test_edit_image_uses_openai_sdk_images_edit(self):
        from krill_image_client import KrillImageClient

        captured = {}

        class FakeImages:
            def edit(self, **kwargs):
                captured["edit_kwargs"] = kwargs
                class Result:
                    data = [type("ImageData", (), {"b64_json": base64.b64encode(MINIMAL_PNG).decode("utf-8")})()]
                return Result()

        class FakeOpenAI:
            def __init__(self, **kwargs):
                self.images = FakeImages()

        with tempfile.TemporaryDirectory() as tmp, \
             patch("krill_image_client.OpenAI", FakeOpenAI), \
             patch("krill_image_client.KRILL_IMAGE_API_URL", "https://api.krill-ai.com/v1"), \
             patch("krill_image_client.KRILL_IMAGE_API_KEY", "test-krill-key"), \
             patch("krill_image_client.KRILL_IMAGE_MODEL", "gpt-image-2"), \
             patch("krill_image_client.missing_krill_image_settings", return_value=[]):
            image_path = Path(tmp) / "input.png"
            image_path.write_bytes(MINIMAL_PNG)
            mask_path = Path(tmp) / "mask.png"
            mask_path.write_bytes(MINIMAL_PNG)
            out = Path(tmp) / "edited.png"
            client = KrillImageClient()
            client.edit_image("revise", image_path, out, mask_path=mask_path)

        self.assertEqual("gpt-image-2", captured["edit_kwargs"]["model"])
        self.assertEqual("revise", captured["edit_kwargs"]["prompt"])
        self.assertEqual("1280x720", captured["edit_kwargs"]["size"])
        self.assertEqual("high", captured["edit_kwargs"]["quality"])
        self.assertIn("image", captured["edit_kwargs"])
        self.assertIn("mask", captured["edit_kwargs"])


if __name__ == "__main__":
    unittest.main()
