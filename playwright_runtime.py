from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_PLAYWRIGHT_CACHE = PROJECT_ROOT / ".ms-playwright"
GLOBAL_PLAYWRIGHT_CACHE = Path.home() / "Library" / "Caches" / "ms-playwright"
WINDOWS_PLAYWRIGHT_CACHE = Path(os.getenv("LOCALAPPDATA", "")) / "ms-playwright"


def playwright_cache() -> Path:
    if LOCAL_PLAYWRIGHT_CACHE.exists():
        return LOCAL_PLAYWRIGHT_CACHE
    return GLOBAL_PLAYWRIGHT_CACHE


def configure_global_playwright() -> None:
    """Prefer the project-local Playwright browser cache for every render."""
    cache = playwright_cache()
    if cache.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(cache))


def global_chromium_executable() -> str | None:
    explicit = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return explicit

    cache = playwright_cache()
    candidates = [
        cache / "chromium-1223" / "chrome-mac-arm64" / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing",
        cache / "chromium_headless_shell-1223" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell",
    ]
    candidates.extend(sorted(cache.glob("chromium-*/chrome-mac-*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")))
    candidates.extend(sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell")))
    if WINDOWS_PLAYWRIGHT_CACHE.exists():
        candidates.extend(sorted(WINDOWS_PLAYWRIGHT_CACHE.glob("chromium_headless_shell-*/chrome-headless-shell-win*/chrome-headless-shell.exe"), reverse=True))
        candidates.extend(sorted(WINDOWS_PLAYWRIGHT_CACHE.glob("chromium-*/chrome-win*/chrome.exe"), reverse=True))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def sync_playwright():
    configure_global_playwright()
    try:
        from playwright.sync_api import sync_playwright as _sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Python Playwright package is required to drive the globally installed Playwright browser. "
            "Run with `uv sync` or install the Python package, then the project will use the global browser cache."
        ) from exc
    return _sync_playwright()


def launch_global_chromium(playwright: Any, **kwargs: Any):
    configure_global_playwright()
    executable_path = global_chromium_executable()
    if executable_path:
        kwargs.setdefault("executable_path", executable_path)
    return playwright.chromium.launch(**kwargs)
