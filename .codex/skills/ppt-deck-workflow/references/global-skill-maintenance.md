# Global Skill Maintenance

Use these commands only for a globally installed `ppt-deck-workflow` containing `runtime/` and `.install-state.json`.

## Runtime Prefix

Windows PowerShell:

```powershell
$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$PptSkill = Join-Path $CodexHome "skills\ppt-deck-workflow"
$Runtime = Join-Path $PptSkill "runtime"
```

macOS/Linux:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PPT_SKILL="$CODEX_HOME/skills/ppt-deck-workflow"
RUNTIME="$PPT_SKILL/runtime"
```

## Commands

Status is local and read-only:

```powershell
uv run --project "$Runtime" python -B -u "$PptSkill\scripts\update_global_skill.py" status
```

Check compares the installed commit with the recorded GitHub branch without changing files:

```powershell
uv run --project "$Runtime" python -B -u "$PptSkill\scripts\update_global_skill.py" check
```

Upgrade clones the recorded branch to a temporary directory, materializes a candidate with that branch's installer, validates it, creates a rollback backup, and updates managed files:

```powershell
uv run --project "$Runtime" python -B -u "$PptSkill\scripts\update_global_skill.py" upgrade
```

Rollback restores the newest retained backup:

```powershell
uv run --project "$Runtime" python -B -u "$PptSkill\scripts\update_global_skill.py" rollback
```

Use the equivalent slash-separated paths on macOS/Linux.

## Source And Safety Contract

- Default to repository `https://github.com/TuKJet/PPT-AGENT.git` and branch `codex/all-logic-in-skills` when installation-time Git discovery is unavailable.
- Record the actual origin URL, branch, commit, and dirty-source flag during installation.
- Use `git ls-remote` for checks and a depth-one single-branch clone for upgrades; do not merge the remote branch into a live installation.
- Refuse an upgrade when managed files differ from their recorded hashes unless the user explicitly approves `--allow-local-changes`.
- Keep backups under `$CODEX_HOME/skill-state/ppt-deck-workflow/backups`, outside `$CODEX_HOME/skills`, so backup copies are not discovered as duplicate Skills.
- Preserve `runtime/.venv`, `runtime/.uv-cache`, local `runtime/uv.lock`, `.install-state.json`, and unmanaged local files.
- Keep the repository requirement as an open minimum. Before `uv sync`, inspect the shared cache's `.links` records and each linked Playwright `browsers.json`. If a complete cached `chromium_headless_shell-<revision>` maps to a Playwright version that satisfies the minimum, materialize that exact version in the installed runtime and record the selection in `.install-state.json`.
- Prefer the highest compatible cached Playwright version when several complete revisions are available. Do not infer a package version from a revision number alone; fall back to the open minimum when the mapping is missing, stale, incomplete, or below the minimum.
- Install only `playwright install --only-shell chromium` into the shared OS cache when browser setup is enabled. With a cache-compatible runtime selection, this command verifies and reuses the existing revision instead of downloading another one.
- Let Playwright select the exact browser revision. Use `PLAYWRIGHT_CHROMIUM_EXECUTABLE` only as an explicit user override.
- Restore the backup automatically if candidate application, dependency sync, browser setup, or workflow verification fails.
- Do not run `git reset --hard`, delete the shared Playwright cache, or overwrite a different repository/ref silently.

## Activation

The current turn already loaded the old `SKILL.md`. After `upgrade` or `rollback` succeeds, report the commit and end the turn. Use the updated Skill on the next turn.
