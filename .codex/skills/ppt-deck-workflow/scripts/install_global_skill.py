from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SKILL_NAME = "ppt-deck-workflow"
SKILL_ROOT = Path(__file__).resolve().parents[1]
try:
    LOCAL_REPO_ROOT = Path(__file__).resolve().parents[4]
except IndexError:
    LOCAL_REPO_ROOT = SKILL_ROOT
GLOBAL_RUNTIME_ROOT = SKILL_ROOT / "runtime"
INSTALL_STATE_FILE = ".install-state.json"
DEFAULT_SOURCE_REPOSITORY = "https://github.com/TuKJet/PPT-AGENT.git"
DEFAULT_SOURCE_REF = "codex/all-logic-in-skills"

RUNTIME_FILES = (
    "filename_utils.py",
    "playwright_runtime.py",
    "pptx_builder.py",
)
RUNTIME_DIRS = (
    "html_pipeline",
    "vendor_presentation_core",
)
SKILL_COPY_DIRS = (
    "agents",
    "references",
    "scripts",
)
SKILL_COPY_FILES = ("SKILL.md",)

RUNTIME_PYPROJECT = """\
[project]
name = "ppt-deck-workflow-skill-runtime"
version = "0.1.0"
description = "Self-contained runtime for the globally installed ppt-deck-workflow skill."
requires-python = ">=3.11"
dependencies = [
    "pillow>=10.0.0",
    "python-pptx>=1.0.0",
    "playwright>=1.40.0",
    "pywin32>=306; sys_platform == 'win32'",
]

[tool.uv]
package = false
"""


def codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME") or (Path.home() / ".codex")).resolve()


def default_target() -> Path:
    return codex_home() / "skills" / SKILL_NAME


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


def runtime_environment(runtime: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(runtime / ".uv-cache"))
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(shared_playwright_cache()))
    return env


def source_runtime_root() -> Path:
    return GLOBAL_RUNTIME_ROOT if (GLOBAL_RUNTIME_ROOT / "filename_utils.py").is_file() else LOCAL_REPO_ROOT


def git_output(*args: str, cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def detected_source_info() -> dict[str, object]:
    existing_state = SKILL_ROOT / INSTALL_STATE_FILE
    if existing_state.is_file():
        try:
            state = json.loads(existing_state.read_text(encoding="utf-8"))
            source = state.get("source")
            if isinstance(source, dict):
                return {
                    "repository": str(source.get("repository") or DEFAULT_SOURCE_REPOSITORY),
                    "ref": str(source.get("ref") or DEFAULT_SOURCE_REF),
                    "commit": source.get("commit"),
                    "dirty": bool(source.get("dirty", False)),
                }
        except (OSError, ValueError, TypeError):
            pass

    repository = git_output("remote", "get-url", "origin", cwd=LOCAL_REPO_ROOT)
    ref = git_output("branch", "--show-current", cwd=LOCAL_REPO_ROOT)
    commit = git_output("rev-parse", "HEAD", cwd=LOCAL_REPO_ROOT)
    dirty_output = git_output("status", "--porcelain", cwd=LOCAL_REPO_ROOT)
    return {
        "repository": repository or DEFAULT_SOURCE_REPOSITORY,
        "ref": ref or DEFAULT_SOURCE_REF,
        "commit": commit,
        "dirty": bool(dirty_output),
    }


def ignore_generated(_: str, names: list[str]) -> set[str]:
    ignored = {
        name
        for name in names
        if name in {"__pycache__", ".venv", ".uv-cache", ".ms-playwright", ".git", "output"}
        or name.endswith((".pyc", ".pyo"))
        or name == "README.md"
    }
    return ignored


def copy_global_skill(staging: Path) -> None:
    runtime_source = source_runtime_root()
    staging.mkdir(parents=True, exist_ok=False)

    for file_name in SKILL_COPY_FILES:
        source = SKILL_ROOT / file_name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, staging / file_name)

    for directory_name in SKILL_COPY_DIRS:
        source = SKILL_ROOT / directory_name
        if source.exists():
            shutil.copytree(
                source,
                staging / directory_name,
                ignore=ignore_generated,
            )

    runtime_target = staging / "runtime"
    runtime_target.mkdir()
    for file_name in RUNTIME_FILES:
        source = runtime_source / file_name
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, runtime_target / file_name)

    for directory_name in RUNTIME_DIRS:
        source = runtime_source / directory_name
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(
            source,
            runtime_target / directory_name,
            ignore=ignore_generated,
        )

    (runtime_target / "pyproject.toml").write_text(RUNTIME_PYPROJECT, encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_file_hashes(skill_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_root).as_posix()
        if relative == INSTALL_STATE_FILE:
            continue
        if any(part in {".venv", ".uv-cache", ".ms-playwright", "__pycache__"} for part in path.relative_to(skill_root).parts):
            continue
        if path.suffix in {".pyc", ".pyo"}:
            continue
        hashes[relative] = file_sha256(path)
    return hashes


def write_install_state(skill_root: Path, source: dict[str, object]) -> dict[str, object]:
    hashes = managed_file_hashes(skill_root)
    state: dict[str, object] = {
        "schema_version": 1,
        "skill_name": SKILL_NAME,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "repository": str(source.get("repository") or DEFAULT_SOURCE_REPOSITORY),
            "ref": str(source.get("ref") or DEFAULT_SOURCE_REF),
            "commit": source.get("commit"),
            "dirty": bool(source.get("dirty", False)),
        },
        "managed_files": sorted(hashes),
        "managed_hashes": hashes,
    }
    (skill_root / INSTALL_STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


def install_skill(
    target: Path,
    force: bool = False,
    *,
    source: dict[str, object] | None = None,
) -> Path:
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.name != SKILL_NAME:
        raise ValueError(f"target directory must end with {SKILL_NAME}: {target}")
    if target.exists() and not force:
        raise FileExistsError(
            f"skill already exists: {target}. Re-run with --force to replace it."
        )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{SKILL_NAME}-", dir=str(target.parent))
    )
    shutil.rmtree(staging)
    try:
        copy_global_skill(staging)
        write_install_state(staging, source or detected_source_info())
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def run_checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    print("running=" + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def bootstrap_runtime(target: Path, install_browser: bool) -> None:
    runtime = target / "runtime"
    env = runtime_environment(runtime)
    run_checked(["uv", "sync", "--project", str(runtime)], env=env)
    if install_browser:
        run_checked(
            [
                "uv",
                "run",
                "--project",
                str(runtime),
                "playwright",
                "install",
                "--only-shell",
                "chromium",
            ],
            env=env,
        )


def verify_install(target: Path) -> None:
    runtime = target / "runtime"
    workflow = target / "scripts" / "workflow.py"
    env = runtime_environment(runtime)
    run_checked(
        [
            "uv",
            "run",
            "--project",
            str(runtime),
            "python",
            "-B",
            str(workflow),
            "--help",
        ],
        env=env,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install ppt-deck-workflow as a self-contained global Codex skill. "
            "The installed copy includes its deterministic PPT runtime and no longer "
            "depends on this repository directory."
        )
    )
    parser.add_argument("--target", default=str(default_target()))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Run uv sync for the installed runtime and verify workflow.py.",
    )
    parser.add_argument(
        "--install-browser",
        action="store_true",
        help="With --bootstrap, also install the Playwright Chromium headless shell.",
    )
    parser.add_argument("--source-repo")
    parser.add_argument("--source-ref")
    parser.add_argument("--source-commit")
    parser.add_argument("--source-dirty", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.install_browser and not args.bootstrap:
        parser.error("--install-browser requires --bootstrap")
    detected = detected_source_info()
    source = {
        "repository": args.source_repo or detected["repository"],
        "ref": args.source_ref or detected["ref"],
        "commit": args.source_commit if args.source_commit is not None else detected["commit"],
        "dirty": args.source_dirty or bool(detected["dirty"]),
    }
    target = install_skill(Path(args.target), force=args.force, source=source)
    print(f"installed_skill={target}", flush=True)
    print(f"runtime={target / 'runtime'}", flush=True)
    print(f"source_repo={source['repository']}", flush=True)
    print(f"source_ref={source['ref']}", flush=True)
    print(f"source_commit={source['commit'] or 'unknown'}", flush=True)
    if args.bootstrap:
        bootstrap_runtime(target, install_browser=args.install_browser)
        verify_install(target)
        print("bootstrap=completed", flush=True)
    else:
        print("next=run-installer-with---bootstrap", flush=True)
    print(
        "usage=uv run --project "
        f"\"{target / 'runtime'}\" python -u \"{target / 'scripts' / 'workflow.py'}\" --help",
        flush=True,
    )


if __name__ == "__main__":
    main()
