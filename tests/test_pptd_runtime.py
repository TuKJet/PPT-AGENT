from __future__ import annotations

import importlib.util
import io
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

from test_workflow_helper import load_workflow_module, valid_slide_plans

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/ppt-deck-workflow/scripts"
spec = importlib.util.spec_from_file_location("pptd_runtime", SCRIPTS / "pptd_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
sys.modules["pptd_runtime"] = runtime


def make_project(root: Path):
    (root / "pages").mkdir(parents=True)
    manifest = {"version": "v2", "title": "可编辑验证", "size": [960, 540],
                "pages": ["pages/01.page"]}
    page = {"pageType": "content", "elements": [
        {"elementId": "title", "elementType": "text", "bounds": [40, 40, 800, 90],
         "content": {"fontSize": 36, "text": "团队编辑验证"}},
        {"elementId": "box", "elementType": "shape", "bounds": [40, 150, 300, 200],
         "shapeName": "rect", "fill": {"type": "solid", "color": "#1358A8"}},
    ]}
    (root / "deck.pptd").write_text(json.dumps(manifest, ensure_ascii=False))
    (root / "pages/01.page").write_text(json.dumps(page, ensure_ascii=False))
    return manifest, page


class PPTDRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "pptd"
        self.manifest, self.page = make_project(self.project)

    def tearDown(self):
        self.temp.cleanup()

    def test_validation_rejects_missing_assets_duplicate_ids_and_page_mismatch(self):
        runtime.validate_project(self.project, expected_pages=1)
        with self.assertRaisesRegex(ValueError, "page count"):
            runtime.validate_project(self.project, expected_pages=2)
        self.page["elements"].append(self.page["elements"][0])
        (self.project / "pages/01.page").write_text(json.dumps(self.page))
        with self.assertRaisesRegex(ValueError, "elementId"):
            runtime.validate_project(self.project)
        self.page["elements"][-1] = {"elementId": "photo", "elementType": "image",
                                     "bounds": [0, 0, 100, 100], "src": "media/missing.png"}
        (self.project / "pages/01.page").write_text(json.dumps(self.page))
        with self.assertRaisesRegex(ValueError, "missing local media"):
            runtime.validate_project(self.project)

    def test_paths_reject_traversal_remote_and_symlink_escape(self):
        for path in ("../outside.page", "/tmp/a.page", "https://example.com/a.png", "C:/a.png"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runtime.project_path(self.project, path)
        outside = self.root / "outside.page"
        outside.write_text("{}")
        (self.project / "escape.page").symlink_to(outside)
        with self.assertRaises(ValueError):
            runtime.project_path(self.project, "escape.page")

    @unittest.skipUnless(shutil.which("node"), "Node is required for actual WASM export")
    def test_real_export_preserves_native_text_and_shapes_and_latest_edits(self):
        target = self.root / "deck.pptx"
        report = runtime.export_project(self.project, target)
        self.assertEqual(report["zip_integrity"], "passed")
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
              "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
        with zipfile.ZipFile(target) as z:
            slide = ET.fromstring(z.read("ppt/slides/slide1.xml"))
            self.assertIn("团队编辑验证", [n.text for n in slide.findall(".//a:t", ns)])
            self.assertEqual(len(slide.findall(".//p:sp", ns)), 2)
            self.assertEqual(len(slide.findall(".//p:pic", ns)), 0)
        self.page["elements"][0]["content"]["text"] = "人工保存后的文字"
        (self.project / "pages/01.page").write_text(json.dumps(self.page))
        runtime.export_project(self.project, target)
        with zipfile.ZipFile(target) as z:
            self.assertIn("人工保存后的文字", z.read("ppt/slides/slide1.xml").decode())

    def test_server_serves_local_editor_and_wasm_not_project_or_other_paths(self):
        with runtime.create_editor_server() as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(base + "/") as response:
                    self.assertIn(b"local-bridge.js", response.read())
                with urllib.request.urlopen(base + "/neo-ppt/assets/" + runtime.WASM.name) as response:
                    self.assertEqual(response.read(4), b"\x00asm")
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + "/%2e%2e/SKILL.md")
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + "/deck.pptd")
            finally:
                server.shutdown()
                thread.join()

    def test_browser_loads_project_and_renders_chinese_without_network(self):
        from playwright_runtime import sync_playwright, launch_global_chromium
        with runtime.create_editor_server() as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = launch_global_chromium(playwright, headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1440, "height": 1000})
                        page.route("**/*", lambda route: route.continue_()
                                   if route.request.url.startswith("http://127.0.0.1:")
                                   else route.abort())
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(f"http://127.0.0.1:{server.server_port}/")
                        page.wait_for_function("document.querySelector('#nd-status')?.textContent.includes('项目文件夹')", timeout=30000)
                        self.assertEqual(page.locator("#nd-title").inner_text(), "未打开文稿")
                        page.locator("#nd-folder").set_input_files(str(self.project))
                        page.get_by_text("团队编辑验证", exact=True).first.wait_for(timeout=20000)
                        self.assertEqual(page.locator("#nd-title").inner_text(), "可编辑验证")
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                thread.join()

    def test_workflow_gate_export_and_cleanup(self):
        workflow = load_workflow_module()
        with mock.patch.dict("os.environ", {"OUTPUT_DIR": str(self.root)}):
            workflow.init_state(self.root, topic="Test", audience="Team", pages="1", research="")
            workflow.write_json(self.root / "slide-plans.json", valid_slide_plans())
            with self.assertRaises(RuntimeError):
                workflow.cmd_choose_renderer(Namespace(run_dir=str(self.root), renderer="pptd"))
            state = workflow.load_state(self.root)
            state["approvals"]["slide_plans"] = True
            workflow.save_state(self.root, state)
            with mock.patch.object(runtime, "serve_editor") as serve:
                with self.assertRaises(RuntimeError):
                    workflow.cmd_open_pptd_editor(Namespace(run_dir=str(self.root), port=0, open=False))
                serve.assert_not_called()
                workflow.cmd_choose_renderer(Namespace(run_dir=str(self.root), renderer="pptd"))
                workflow.cmd_open_pptd_editor(Namespace(run_dir=str(self.root), port=0, open=False))
                serve.assert_called_once()
            workflow.cmd_prepare_render_jobs(Namespace(run_dir=str(self.root), renderer="pptd"))
            if shutil.which("node"):
                workflow.cmd_export(Namespace(run_dir=str(self.root), renderer=None))
                status = workflow.load_state(self.root)
                self.assertEqual(status["renderers"]["pptd"]["status"], "completed")
                self.assertTrue((self.root / "slide-status-pptd.json").is_file())
            workflow.clean_render_outputs(self.root)
            self.assertTrue((self.project / "deck.pptd").is_file())
            self.assertTrue((self.project / "pages/01.page").is_file())


if __name__ == "__main__":
    unittest.main()
