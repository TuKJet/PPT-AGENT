from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".codex" / "skills" / "ppt-deck-workflow"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


class GlobalSkillUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.installer = load_module(
            "install_global_skill_for_update_tests",
            SKILL_ROOT / "scripts" / "install_global_skill.py",
        )
        self.updater = load_module(
            "update_global_skill_for_tests",
            SKILL_ROOT / "scripts" / "update_global_skill.py",
        )

    def make_source_repository(self, destination: Path, branch: str) -> str:
        skill_target = destination / ".codex" / "skills" / "ppt-deck-workflow"
        skill_target.parent.mkdir(parents=True)
        shutil.copytree(SKILL_ROOT, skill_target)
        for file_name in self.installer.RUNTIME_FILES:
            shutil.copy2(ROOT / file_name, destination / file_name)
        for directory_name in self.installer.RUNTIME_DIRS:
            shutil.copytree(ROOT / directory_name, destination / directory_name)

        git("init", cwd=destination)
        git("config", "user.email", "ppt-skill-tests@example.invalid", cwd=destination)
        git("config", "user.name", "PPT Skill Tests", cwd=destination)
        git("checkout", "-b", branch, cwd=destination)
        git("add", ".", cwd=destination)
        git("commit", "-m", "initial skill", cwd=destination)
        return git("rev-parse", "HEAD", cwd=destination)

    def test_upgrade_from_recorded_branch_preserves_runtime_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_repo = root / "source-repo"
            source_repo.mkdir()
            branch = "feature/ppt-skill"
            first_commit = self.make_source_repository(source_repo, branch)

            target = root / "codex-home" / "skills" / "ppt-deck-workflow"
            source = {
                "repository": str(source_repo),
                "ref": branch,
                "commit": first_commit,
                "dirty": False,
            }
            self.installer.install_skill(target, source=source)
            sentinel = target / "runtime" / ".venv" / "preserved.txt"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text("keep", encoding="utf-8")

            source_skill = source_repo / ".codex" / "skills" / "ppt-deck-workflow"
            skill_path = source_skill / "SKILL.md"
            skill_path.write_text(
                skill_path.read_text(encoding="utf-8") + "\n<!-- branch-update-marker -->\n",
                encoding="utf-8",
            )
            git("add", ".", cwd=source_repo)
            git("commit", "-m", "update skill", cwd=source_repo)
            second_commit = git("rev-parse", "HEAD", cwd=source_repo)

            previous_codex_home = os.environ.get("CODEX_HOME")
            os.environ["CODEX_HOME"] = str(root / "codex-home")
            try:
                changed = self.updater.upgrade_command(
                    target,
                    bootstrap=False,
                    keep_backups=4,
                )
                self.assertTrue(changed)
                self.assertTrue(sentinel.is_file())
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
                self.assertIn(
                    "branch-update-marker",
                    (target / "SKILL.md").read_text(encoding="utf-8"),
                )
                state = json.loads(
                    (target / ".install-state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(state["source"]["commit"], second_commit)
                self.assertFalse(state["source"]["dirty"])

                self.updater.rollback_command(
                    target,
                    bootstrap=False,
                    keep_backups=4,
                )
                self.assertTrue(sentinel.is_file())
                self.assertNotIn(
                    "branch-update-marker",
                    (target / "SKILL.md").read_text(encoding="utf-8"),
                )
                rolled_back = json.loads(
                    (target / ".install-state.json").read_text(encoding="utf-8")
                )
                self.assertEqual(rolled_back["source"]["commit"], first_commit)
            finally:
                if previous_codex_home is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = previous_codex_home

    def test_local_managed_changes_stop_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills" / "ppt-deck-workflow"
            self.installer.install_skill(target)
            (target / "SKILL.md").write_text("locally changed", encoding="utf-8")
            state = self.updater.load_state(target)
            changes = self.updater.local_changes(target, state)
            self.assertIn("modified:SKILL.md", changes)

    def test_restore_removes_partially_applied_candidate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "codex-home" / "skills" / "ppt-deck-workflow"
            self.installer.install_skill(target)
            original_state = self.updater.load_state(target)
            original_skill = (target / "SKILL.md").read_text(encoding="utf-8")
            backup = self.updater.create_backup(
                target,
                original_state,
                root / "backups",
                label="test",
            )

            partially_added = target / "scripts" / "candidate-only.py"
            partially_added.write_text("partial", encoding="utf-8")
            (target / "SKILL.md").write_text("corrupted", encoding="utf-8")

            self.updater.restore_backup(
                target,
                backup,
                extra_managed_files=["scripts/candidate-only.py"],
            )

            self.assertFalse(partially_added.exists())
            self.assertEqual(
                (target / "SKILL.md").read_text(encoding="utf-8"),
                original_skill,
            )
            self.assertEqual(self.updater.local_changes(target, original_state), [])


if __name__ == "__main__":
    unittest.main()
