from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def load_runtime():
    path = Path(__file__).resolve().parents[1] / "playwright_runtime.py"
    spec = importlib.util.spec_from_file_location("playwright_runtime_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeChromium:
    def __init__(self) -> None:
        self.kwargs = None

    def launch(self, **kwargs):
        self.kwargs = kwargs
        return "browser"


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeChromium()


class PlaywrightRuntimeTests(unittest.TestCase):
    def test_shared_cache_override_is_used_without_scanning_revisions(self) -> None:
        runtime = load_runtime()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {"PLAYWRIGHT_BROWSERS_PATH": tmp},
                clear=False,
            ):
                self.assertEqual(runtime.playwright_cache(), Path(tmp).resolve())
                playwright = FakePlaywright()
                self.assertEqual(runtime.launch_global_chromium(playwright), "browser")
                self.assertEqual(playwright.chromium.kwargs, {})

    def test_explicit_browser_path_is_the_only_executable_override(self) -> None:
        runtime = load_runtime()
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "chrome.exe"
            executable.write_bytes(b"test")
            with mock.patch.dict(
                os.environ,
                {"PLAYWRIGHT_CHROMIUM_EXECUTABLE": str(executable)},
                clear=False,
            ):
                playwright = FakePlaywright()
                runtime.launch_global_chromium(playwright)
                self.assertEqual(
                    playwright.chromium.kwargs,
                    {"executable_path": str(executable.resolve())},
                )


if __name__ == "__main__":
    unittest.main()
