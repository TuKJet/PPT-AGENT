from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_installer_module():
    path = (
        Path(__file__).resolve().parents[1]
        / ".codex"
        / "skills"
        / "ppt-deck-workflow"
        / "scripts"
        / "install_global_skill.py"
    )
    spec = importlib.util.spec_from_file_location("install_global_skill", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_installed_workflow(path: Path):
    spec = importlib.util.spec_from_file_location("installed_workflow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class GlobalSkillInstallTests(unittest.TestCase):
    def test_installed_skill_is_self_contained_and_uses_current_workspace(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "skills" / "ppt-deck-workflow"
            workspace = root / "workspace"
            workspace.mkdir()

            installed = installer.install_skill(target)

            self.assertEqual(installed, target.resolve())
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "agents" / "openai.yaml").is_file())
            self.assertIn(
                "$ppt-deck-workflow",
                (installed / "agents" / "openai.yaml").read_text(encoding="utf-8"),
            )
            self.assertTrue((installed / "scripts" / "workflow.py").is_file())
            self.assertTrue((installed / "scripts" / "embed_img_crops.py").is_file())
            self.assertTrue((installed / "scripts" / "playwright_cache.py").is_file())
            self.assertTrue((installed / "scripts" / "update_global_skill.py").is_file())
            self.assertTrue((installed / "runtime" / "pyproject.toml").is_file())
            self.assertTrue((installed / "runtime" / "filename_utils.py").is_file())
            self.assertTrue((installed / "runtime" / "pptx_builder.py").is_file())
            self.assertTrue(
                (
                    installed
                    / "runtime"
                    / "vendor_presentation_core"
                    / "export"
                    / "dom-to-pptx.bundle.js"
                ).is_file()
            )
            state = json.loads(
                (installed / ".install-state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["skill_name"], "ppt-deck-workflow")
            self.assertIn("scripts/update_global_skill.py", state["managed_files"])
            self.assertIn("runtime/playwright_runtime.py", state["managed_hashes"])

            previous_workspace = os.environ.get("PPT_AGENT_WORKSPACE")
            previous_output = os.environ.get("OUTPUT_DIR")
            os.environ["PPT_AGENT_WORKSPACE"] = str(workspace)
            os.environ.pop("OUTPUT_DIR", None)
            try:
                workflow = load_installed_workflow(installed / "scripts" / "workflow.py")
                self.assertTrue(workflow.GLOBAL_SKILL_MODE)
                self.assertEqual(
                    workflow.resolved_output_root(),
                    (workspace / "output").resolve(),
                )
            finally:
                if previous_workspace is None:
                    os.environ.pop("PPT_AGENT_WORKSPACE", None)
                else:
                    os.environ["PPT_AGENT_WORKSPACE"] = previous_workspace
                if previous_output is None:
                    os.environ.pop("OUTPUT_DIR", None)
                else:
                    os.environ["OUTPUT_DIR"] = previous_output

            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(installed / "scripts" / "workflow.py"),
                    "--help",
                ],
                cwd=workspace,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("choose-img-svg", result.stdout)

    def test_force_is_required_to_replace_an_existing_skill(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills" / "ppt-deck-workflow"
            installer.install_skill(target)
            with self.assertRaises(FileExistsError):
                installer.install_skill(target)
            installer.install_skill(target, force=True)
            self.assertTrue((target / "runtime" / "pptx_builder.py").is_file())

    def test_browser_bootstrap_uses_shared_cache_and_headless_shell(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills" / "ppt-deck-workflow"
            installer.install_skill(target)
            commands: list[tuple[list[str], dict[str, str] | None]] = []

            def capture(command, *, cwd=None, env=None):
                commands.append((command, env))

            with mock.patch.object(installer, "run_checked", side_effect=capture):
                installer.bootstrap_runtime(target, install_browser=True)

            self.assertEqual(commands[0][0][:3], ["uv", "sync", "--project"])
            self.assertIn("--only-shell", commands[1][0])
            self.assertEqual(commands[1][0][-1], "chromium")
            self.assertTrue(commands[0][1])
            assert commands[0][1] is not None
            self.assertIn("PLAYWRIGHT_BROWSERS_PATH", commands[0][1])

    def test_install_prefers_a_compatible_cached_playwright_version(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "skills" / "ppt-deck-workflow"
            cached = installer.CachedPlaywright(
                version="1.60.0",
                revision="1223",
                package_root=root / "package",
                browser_root=root / "chromium_headless_shell-1223",
            )

            with mock.patch.object(
                installer,
                "compatible_cached_playwright",
                return_value=cached,
            ):
                installer.install_skill(target)

            pyproject = (target / "runtime" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
            state = json.loads(
                (target / ".install-state.json").read_text(encoding="utf-8")
            )
            self.assertIn('"playwright==1.60.0"', pyproject)
            self.assertEqual(
                state["runtime"]["playwright_requirement"],
                "playwright==1.60.0",
            )
            self.assertTrue(state["runtime"]["reused_browser_cache"])
            self.assertEqual(state["runtime"]["browser_revision"], "1223")

    def test_install_keeps_open_minimum_without_a_reliable_cached_pair(self) -> None:
        installer = load_installer_module()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills" / "ppt-deck-workflow"
            with mock.patch.object(
                installer,
                "compatible_cached_playwright",
                return_value=None,
            ):
                installer.install_skill(target)

            pyproject = (target / "runtime" / "pyproject.toml").read_text(
                encoding="utf-8"
            )
            state = json.loads(
                (target / ".install-state.json").read_text(encoding="utf-8")
            )
            self.assertIn('"playwright>=1.40.0"', pyproject)
            self.assertFalse(state["runtime"]["reused_browser_cache"])
            self.assertIsNone(state["runtime"]["browser_revision"])


if __name__ == "__main__":
    unittest.main()
