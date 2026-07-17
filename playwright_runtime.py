from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

def playwright_cache() -> Path:
    explicit = os.getenv("PLAYWRIGHT_BROWSERS_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return (Path(local_app_data) / "ms-playwright").resolve()
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Caches" / "ms-playwright").resolve()
    return (Path.home() / ".cache" / "ms-playwright").resolve()


def configure_global_playwright() -> None:
    """Use one OS-level browser cache across repositories and global skills."""
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(playwright_cache()))


def global_chromium_executable() -> str | None:
    explicit = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if explicit:
        executable = Path(explicit).expanduser().resolve()
        if not executable.is_file():
            raise RuntimeError(
                "PLAYWRIGHT_CHROMIUM_EXECUTABLE does not point to a file: "
                f"{executable}"
            )
        return str(executable)
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
    # Without an explicit override, let Playwright select the exact browser
    # revision required by the installed Python package from the shared cache.
    return playwright.chromium.launch(**kwargs)
