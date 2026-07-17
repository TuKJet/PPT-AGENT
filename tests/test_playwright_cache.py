from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = (
    ROOT
    / ".codex"
    / "skills"
    / "ppt-deck-workflow"
    / "scripts"
    / "playwright_cache.py"
)


def load_helper():
    spec = importlib.util.spec_from_file_location("playwright_cache_for_tests", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PlaywrightCacheTests(unittest.TestCase):
    def add_linked_runtime(
        self,
        root: Path,
        cache: Path,
        *,
        name: str,
        version: str,
        revision: str,
        browser_installed: bool = True,
    ) -> None:
        site_packages = root / name / "site-packages"
        package_root = site_packages / "playwright" / "driver" / "package"
        package_root.mkdir(parents=True)
        (package_root / "browsers.json").write_text(
            json.dumps(
                {
                    "browsers": [
                        {
                            "name": "chromium-headless-shell",
                            "revision": revision,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        metadata = site_packages / f"playwright-{version}.dist-info" / "METADATA"
        metadata.parent.mkdir()
        metadata.write_text(
            f"Name: playwright\nVersion: {version}\n",
            encoding="utf-8",
        )
        links = cache / ".links"
        links.mkdir(parents=True, exist_ok=True)
        (links / name).write_text(str(package_root), encoding="utf-8")
        if browser_installed:
            browser_root = cache / f"chromium_headless_shell-{revision}"
            browser_root.mkdir()
            (browser_root / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")

    def test_prefers_highest_compatible_version_with_complete_cached_browser(self) -> None:
        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            self.add_linked_runtime(
                root,
                cache,
                name="older-compatible",
                version="1.55.0",
                revision="1200",
            )
            self.add_linked_runtime(
                root,
                cache,
                name="best-compatible",
                version="1.60.0",
                revision="1223",
            )
            self.add_linked_runtime(
                root,
                cache,
                name="below-minimum",
                version="1.30.0",
                revision="900",
            )
            self.add_linked_runtime(
                root,
                cache,
                name="browser-incomplete",
                version="1.61.0",
                revision="1228",
                browser_installed=False,
            )

            selected = helper.compatible_cached_playwright(
                cache,
                minimum_version="1.40.0",
            )

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.version, "1.60.0")
            self.assertEqual(selected.revision, "1223")
            self.assertTrue((selected.browser_root / "INSTALLATION_COMPLETE").is_file())

    def test_returns_none_without_a_reliable_revision_mapping(self) -> None:
        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            cache.mkdir()
            (cache / "chromium_headless_shell-1223").mkdir()

            self.assertIsNone(helper.compatible_cached_playwright(cache))


if __name__ == "__main__":
    unittest.main()
