from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterator


SKILL_NAME = "ppt-deck-workflow"
SKILL_ROOT = Path(__file__).resolve().parents[1]
INSTALL_STATE_FILE = ".install-state.json"
DEFAULT_SOURCE_REPOSITORY = "https://github.com/TuKJet/PPT-AGENT.git"
DEFAULT_SOURCE_REF = "codex/all-logic-in-skills"


def codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME") or (Path.home() / ".codex")).resolve()


def state_root() -> Path:
    return codex_home() / "skill-state" / SKILL_NAME


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


def run_checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("running=" + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture_output,
        check=True,
    )


def load_state(skill_root: Path = SKILL_ROOT) -> dict[str, object]:
    path = skill_root / INSTALL_STATE_FILE
    if not path.is_file():
        raise RuntimeError(
            f"global install state is missing: {path}. "
            "Run install_global_skill.py before using GitHub updates."
        )
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("skill_name") != SKILL_NAME:
        raise RuntimeError(f"unexpected skill state in {path}")
    if not isinstance(state.get("source"), dict):
        raise RuntimeError(f"source metadata is missing from {path}")
    return state


def safe_relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError(f"unsafe managed path: {value}")
    return Path(*pure.parts)


def managed_files(state: dict[str, object]) -> list[str]:
    values = state.get("managed_files")
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise RuntimeError("install state has no valid managed_files list")
    for value in values:
        safe_relative(value)
    return list(values)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_changes(skill_root: Path, state: dict[str, object]) -> list[str]:
    expected = state.get("managed_hashes")
    if not isinstance(expected, dict):
        return ["managed_hashes-missing"]
    changed: list[str] = []
    for relative in managed_files(state):
        path = skill_root / safe_relative(relative)
        expected_hash = expected.get(relative)
        if not path.is_file():
            changed.append(f"missing:{relative}")
        elif not isinstance(expected_hash, str) or file_sha256(path) != expected_hash:
            changed.append(f"modified:{relative}")
    return changed


def source_values(
    state: dict[str, object],
    repository: str | None = None,
    ref: str | None = None,
) -> tuple[str, str, str | None, bool]:
    source = state["source"]
    assert isinstance(source, dict)
    return (
        repository or str(source.get("repository") or DEFAULT_SOURCE_REPOSITORY),
        ref or str(source.get("ref") or DEFAULT_SOURCE_REF),
        str(source["commit"]) if source.get("commit") else None,
        bool(source.get("dirty", False)),
    )


def remote_commit(repository: str, ref: str) -> str:
    result = run_checked(
        ["git", "ls-remote", "--exit-code", repository, f"refs/heads/{ref}"],
        capture_output=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"could not resolve one branch head for {repository} {ref}")
    commit, remote_ref = lines[0].split(maxsplit=1)
    if remote_ref != f"refs/heads/{ref}":
        raise RuntimeError(f"unexpected remote ref: {remote_ref}")
    return commit


@contextmanager
def update_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "update.lock"
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.write(f"created_at={datetime.now(timezone.utc).isoformat()}\n")
    except FileExistsError as exc:
        raise RuntimeError(f"another update may be active: {lock}") from exc
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def clone_branch(repository: str, ref: str, destination: Path) -> None:
    run_checked(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--single-branch",
            "--branch",
            ref,
            repository,
            str(destination),
        ]
    )


def materialize_candidate(
    checkout: Path,
    destination: Path,
    *,
    repository: str,
    ref: str,
    commit: str,
) -> Path:
    installer = (
        checkout
        / ".codex"
        / "skills"
        / SKILL_NAME
        / "scripts"
        / "install_global_skill.py"
    )
    if not installer.is_file():
        raise RuntimeError(f"branch does not contain the global installer: {installer}")
    candidate = destination / SKILL_NAME
    run_checked(
        [
            sys.executable,
            "-B",
            str(installer),
            "--target",
            str(candidate),
            "--source-repo",
            repository,
            "--source-ref",
            ref,
            "--source-commit",
            commit,
        ],
        cwd=checkout,
    )
    return candidate


def validate_candidate(candidate: Path, expected_commit: str) -> dict[str, object]:
    required = (
        candidate / "SKILL.md",
        candidate / "scripts" / "workflow.py",
        candidate / "scripts" / "install_global_skill.py",
        candidate / "scripts" / "update_global_skill.py",
        candidate / "runtime" / "pyproject.toml",
    )
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"candidate is missing required file: {path}")
    skill_text = (candidate / "SKILL.md").read_text(encoding="utf-8")
    if "name: ppt-deck-workflow" not in skill_text:
        raise RuntimeError("candidate SKILL.md has the wrong skill name")
    state = load_state(candidate)
    _, _, installed_commit, dirty = source_values(state)
    if installed_commit != expected_commit or dirty:
        raise RuntimeError("candidate source metadata does not match the remote branch head")
    changes = local_changes(candidate, state)
    if changes:
        raise RuntimeError("candidate managed-file validation failed: " + ", ".join(changes[:10]))
    result = run_checked(
        [sys.executable, "-B", str(candidate / "scripts" / "workflow.py"), "--help"],
        cwd=candidate,
        capture_output=True,
    )
    if "choose-img-svg" not in result.stdout:
        raise RuntimeError("candidate workflow smoke check did not expose expected commands")
    return state


def copy_managed_files(source: Path, destination: Path, files: list[str]) -> None:
    for relative in files:
        relative_path = safe_relative(relative)
        source_path = source / relative_path
        if not source_path.is_file():
            raise RuntimeError(f"managed source file is missing: {source_path}")
        destination_path = destination / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination_path.with_name(destination_path.name + ".ppt-update-tmp")
        shutil.copy2(source_path, temporary)
        os.replace(temporary, destination_path)


def remove_managed_files(skill_root: Path, files: set[str]) -> None:
    parents: set[Path] = set()
    for relative in sorted(files, reverse=True):
        path = skill_root / safe_relative(relative)
        path.unlink(missing_ok=True)
        parents.add(path.parent)
    for parent in sorted(parents, key=lambda value: len(value.parts), reverse=True):
        current = parent
        while current != skill_root:
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent


def write_state_atomic(skill_root: Path, state: dict[str, object]) -> None:
    target = skill_root / INSTALL_STATE_FILE
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def create_backup(
    skill_root: Path,
    state: dict[str, object],
    backups_root: Path,
    *,
    label: str,
) -> Path:
    source = state["source"]
    assert isinstance(source, dict)
    commit = str(source.get("commit") or "unknown")[:12]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backups_root / f"{stamp}-{label}-{commit}"
    payload = backup / "payload"
    try:
        payload.mkdir(parents=True, exist_ok=False)
        copy_managed_files(skill_root, payload, managed_files(state))
        (backup / INSTALL_STATE_FILE).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        shutil.rmtree(backup, ignore_errors=True)
        raise
    return backup


def load_backup_state(backup: Path) -> dict[str, object]:
    path = backup / INSTALL_STATE_FILE
    if not path.is_file():
        raise RuntimeError(f"backup state is missing: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    managed_files(state)
    return state


def restore_backup(
    skill_root: Path,
    backup: Path,
    *,
    extra_managed_files: list[str] | None = None,
) -> dict[str, object]:
    backup_state = load_backup_state(backup)
    try:
        current_state = load_state(skill_root)
        current_files = set(managed_files(current_state))
    except Exception:
        current_files = set()
    restore_files = set(managed_files(backup_state))
    extra_files = set(extra_managed_files or [])
    for relative in extra_files:
        safe_relative(relative)
    remove_managed_files(skill_root, current_files | restore_files | extra_files)
    copy_managed_files(backup / "payload", skill_root, managed_files(backup_state))
    write_state_atomic(skill_root, backup_state)
    return backup_state


def apply_candidate(
    skill_root: Path,
    current_state: dict[str, object],
    candidate: Path,
    candidate_state: dict[str, object],
) -> None:
    old_files = set(managed_files(current_state))
    new_files = set(managed_files(candidate_state))
    copy_managed_files(candidate, skill_root, sorted(new_files))
    remove_managed_files(skill_root, old_files - new_files)
    write_state_atomic(skill_root, candidate_state)


def bootstrap_runtime(skill_root: Path, *, install_browser: bool) -> None:
    runtime = skill_root / "runtime"
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
    result = run_checked(
        [
            "uv",
            "run",
            "--project",
            str(runtime),
            "python",
            "-B",
            str(skill_root / "scripts" / "workflow.py"),
            "--help",
        ],
        env=env,
        capture_output=True,
    )
    if "choose-img-svg" not in result.stdout:
        raise RuntimeError("installed workflow verification failed")


def prune_backups(backups_root: Path, keep: int) -> None:
    if keep < 1 or not backups_root.is_dir():
        return
    backups = sorted((path for path in backups_root.iterdir() if path.is_dir()), reverse=True)
    for backup in backups[keep:]:
        shutil.rmtree(backup)


def status_command(skill_root: Path) -> None:
    state = load_state(skill_root)
    repository, ref, commit, dirty = source_values(state)
    changes = local_changes(skill_root, state)
    backups_root = state_root() / "backups"
    backup_count = len([path for path in backups_root.iterdir() if path.is_dir()]) if backups_root.is_dir() else 0
    print(f"skill={SKILL_NAME}")
    print(f"skill_root={skill_root}")
    print(f"source_repo={repository}")
    print(f"source_ref={ref}")
    print(f"installed_commit={commit or 'unknown'}")
    print(f"installed_from_dirty_source={'yes' if dirty else 'no'}")
    print(f"local_managed_changes={len(changes)}")
    for change in changes[:20]:
        print(f"local_change={change}")
    print(f"playwright_cache={shared_playwright_cache()}")
    print(f"backups={backup_count}")


def check_command(
    skill_root: Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
) -> bool:
    state = load_state(skill_root)
    repository_value, ref_value, installed, dirty = source_values(state, repository, ref)
    remote = remote_commit(repository_value, ref_value)
    available = installed != remote or dirty
    print(f"source_repo={repository_value}")
    print(f"source_ref={ref_value}")
    print(f"installed_commit={installed or 'unknown'}")
    print(f"remote_commit={remote}")
    print(f"update_available={'yes' if available else 'no'}")
    return available


def upgrade_command(
    skill_root: Path,
    *,
    repository: str | None = None,
    ref: str | None = None,
    force: bool = False,
    allow_local_changes: bool = False,
    bootstrap: bool = True,
    install_browser: bool = True,
    keep_backups: int = 2,
) -> bool:
    current_state = load_state(skill_root)
    changes = local_changes(skill_root, current_state)
    if changes and not allow_local_changes:
        raise RuntimeError(
            "managed Skill files have local changes; update stopped. "
            "Review them or use --allow-local-changes explicitly. First changes: "
            + ", ".join(changes[:10])
        )
    repository_value, ref_value, installed, dirty = source_values(
        current_state, repository, ref
    )
    remote = remote_commit(repository_value, ref_value)
    if installed == remote and not dirty and not force:
        print("update=not-needed")
        print(f"installed_commit={installed}")
        return False

    root = state_root()
    backups_root = root / "backups"
    with update_lock(root):
        with tempfile.TemporaryDirectory(prefix=f"{SKILL_NAME}-update-") as temporary:
            temporary_root = Path(temporary)
            checkout = temporary_root / "checkout"
            build_root = temporary_root / "candidate"
            build_root.mkdir()
            clone_branch(repository_value, ref_value, checkout)
            candidate = materialize_candidate(
                checkout,
                build_root,
                repository=repository_value,
                ref=ref_value,
                commit=remote,
            )
            candidate_state = validate_candidate(candidate, remote)
            backup = create_backup(
                skill_root,
                current_state,
                backups_root,
                label="pre-upgrade",
            )
            try:
                apply_candidate(skill_root, current_state, candidate, candidate_state)
                if bootstrap:
                    bootstrap_runtime(skill_root, install_browser=install_browser)
            except Exception:
                restore_backup(
                    skill_root,
                    backup,
                    extra_managed_files=managed_files(candidate_state),
                )
                if bootstrap:
                    try:
                        bootstrap_runtime(skill_root, install_browser=False)
                    except Exception as rollback_error:
                        print(f"rollback_bootstrap_warning={rollback_error}", flush=True)
                raise

    prune_backups(backups_root, keep_backups)
    print("update=completed")
    print(f"previous_commit={installed or 'unknown'}")
    print(f"installed_commit={remote}")
    print("activation=next-turn")
    return True


def rollback_command(
    skill_root: Path,
    *,
    backup_name: str | None = None,
    bootstrap: bool = True,
    install_browser: bool = True,
    keep_backups: int = 2,
) -> Path:
    root = state_root()
    backups_root = root / "backups"
    backups = sorted((path for path in backups_root.iterdir() if path.is_dir()), reverse=True) if backups_root.is_dir() else []
    if backup_name:
        selected = backups_root / backup_name
        if selected not in backups or not selected.is_dir():
            raise RuntimeError(f"backup not found: {backup_name}")
    elif backups:
        selected = backups[0]
    else:
        raise RuntimeError("no rollback backup is available")

    current_state = load_state(skill_root)
    selected_state = load_backup_state(selected)
    with update_lock(root):
        safety = create_backup(
            skill_root,
            current_state,
            backups_root,
            label="pre-rollback",
        )
        try:
            restored_state = restore_backup(skill_root, selected)
            if bootstrap:
                bootstrap_runtime(skill_root, install_browser=install_browser)
        except Exception:
            restore_backup(
                skill_root,
                safety,
                extra_managed_files=managed_files(selected_state),
            )
            if bootstrap:
                try:
                    bootstrap_runtime(skill_root, install_browser=False)
                except Exception as rollback_error:
                    print(f"rollback_bootstrap_warning={rollback_error}", flush=True)
            raise

    prune_backups(backups_root, keep_backups)
    source = restored_state["source"]
    assert isinstance(source, dict)
    print("rollback=completed")
    print(f"restored_backup={selected.name}")
    print(f"installed_commit={source.get('commit') or 'unknown'}")
    print("activation=next-turn")
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check, upgrade, or roll back a globally installed ppt-deck-workflow "
            "Skill from its recorded GitHub branch."
        )
    )
    parser.add_argument("--skill-root", default=str(SKILL_ROOT))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    check = subparsers.add_parser("check")
    check.add_argument("--repo")
    check.add_argument("--ref")

    upgrade = subparsers.add_parser("upgrade")
    upgrade.add_argument("--repo")
    upgrade.add_argument("--ref")
    upgrade.add_argument("--force", action="store_true")
    upgrade.add_argument("--allow-local-changes", action="store_true")
    upgrade.add_argument("--skip-bootstrap", action="store_true")
    upgrade.add_argument("--skip-browser", action="store_true")
    upgrade.add_argument("--keep-backups", type=int, default=2)

    rollback = subparsers.add_parser("rollback")
    rollback.add_argument("--backup")
    rollback.add_argument("--skip-bootstrap", action="store_true")
    rollback.add_argument("--skip-browser", action="store_true")
    rollback.add_argument("--keep-backups", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    skill_root = Path(args.skill_root).expanduser().resolve()
    if skill_root.name != SKILL_NAME:
        raise RuntimeError(f"skill root must end with {SKILL_NAME}: {skill_root}")
    if args.command == "status":
        status_command(skill_root)
    elif args.command == "check":
        check_command(skill_root, repository=args.repo, ref=args.ref)
    elif args.command == "upgrade":
        upgrade_command(
            skill_root,
            repository=args.repo,
            ref=args.ref,
            force=args.force,
            allow_local_changes=args.allow_local_changes,
            bootstrap=not args.skip_bootstrap,
            install_browser=not args.skip_browser,
            keep_backups=args.keep_backups,
        )
    elif args.command == "rollback":
        rollback_command(
            skill_root,
            backup_name=args.backup,
            bootstrap=not args.skip_bootstrap,
            install_browser=not args.skip_browser,
            keep_backups=args.keep_backups,
        )


if __name__ == "__main__":
    main()
