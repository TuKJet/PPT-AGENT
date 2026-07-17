from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


MIN_PLAYWRIGHT_VERSION = "1.40.0"
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[.+-].*)?$")


@dataclass(frozen=True)
class CachedPlaywright:
    version: str
    revision: str
    package_root: Path
    browser_root: Path


def shared_playwright_cache() -> Path:
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


def version_key(version: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.fullmatch(version.strip())
    if not match:
        return None
    return tuple(int(value) for value in match.groups())


def _python_distribution_version(package_root: Path) -> str | None:
    try:
        site_packages = package_root.parents[2]
    except IndexError:
        return None
    for metadata in sorted(site_packages.glob("playwright-*.dist-info/METADATA")):
        try:
            for line in metadata.read_text(encoding="utf-8").splitlines():
                if line.startswith("Version:"):
                    return line.partition(":")[2].strip() or None
        except OSError:
            continue
    return None


def _node_distribution_version(package_root: Path) -> str | None:
    package_json = package_root / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    version = data.get("version")
    return str(version).strip() if version else None


def package_version(package_root: Path) -> str | None:
    return _python_distribution_version(package_root) or _node_distribution_version(
        package_root
    )


def headless_shell_revision(package_root: Path) -> str | None:
    browsers_json = package_root / "browsers.json"
    try:
        data = json.loads(browsers_json.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    browsers = data.get("browsers")
    if not isinstance(browsers, list):
        return None
    for browser in browsers:
        if not isinstance(browser, dict):
            continue
        if browser.get("name") == "chromium-headless-shell" and browser.get(
            "revision"
        ):
            return str(browser["revision"])
    return None


def linked_package_roots(cache: Path) -> list[Path]:
    links = cache / ".links"
    if not links.is_dir():
        return []
    roots: list[Path] = []
    for link in sorted(links.iterdir()):
        if not link.is_file():
            continue
        try:
            value = link.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not value:
            continue
        root = Path(value).expanduser()
        if root.is_dir():
            roots.append(root.resolve())
    return roots


def compatible_cached_playwright(
    cache: Path | None = None,
    *,
    minimum_version: str = MIN_PLAYWRIGHT_VERSION,
) -> CachedPlaywright | None:
    cache_root = (cache or shared_playwright_cache()).resolve()
    minimum_key = version_key(minimum_version)
    if minimum_key is None:
        raise ValueError(f"invalid minimum Playwright version: {minimum_version}")

    candidates: dict[tuple[str, str], CachedPlaywright] = {}
    for package_root in linked_package_roots(cache_root):
        version = package_version(package_root)
        revision = headless_shell_revision(package_root)
        key = version_key(version or "")
        if version is None or revision is None or key is None or key < minimum_key:
            continue
        browser_root = cache_root / f"chromium_headless_shell-{revision}"
        if not (browser_root / "INSTALLATION_COMPLETE").is_file():
            continue
        candidates[(version, revision)] = CachedPlaywright(
            version=version,
            revision=revision,
            package_root=package_root,
            browser_root=browser_root,
        )

    if not candidates:
        return None
    return max(
        candidates.values(),
        key=lambda candidate: version_key(candidate.version) or (0, 0, 0),
    )
