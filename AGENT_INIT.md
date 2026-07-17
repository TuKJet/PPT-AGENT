# Agent Initialization Guide

Use this guide when an agent is asked to set up this project on a fresh machine.

## Goal

Prepare the repository so the Codex skill can manage PPT artifacts and export decks without relying on copied local runtime folders or repository model API credentials.

An Agent may choose:

- Repository-local installation for development and testing.
- Global self-contained skill installation for use from arbitrary workspaces without retaining this repository.

## Do Not Commit Or Copy

Do not commit these machine-local or generated paths:

- `.venv/`
- `.python/`
- `.ms-playwright/`
- `.env`
- `output/`
- `__pycache__/`
- `.omx/`

## Required Setup

1. Install `uv`.

macOS/Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

2. Create the project environment.

```bash
uv sync
```

3. Install the Playwright Chromium headless shell into the shared OS cache.

```bash
uv run playwright install --only-shell chromium
```

4. Verify the skill helper.

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py --help
```

5. Run the complete test suite.

```bash
uv run python -B -m unittest discover -s tests -p "test_*.py"
```

Do not claim the installation is complete until the helper lists the IMG-to-SVG commands and the test suite reports `OK`.

## Agent Self-Install As A Global Skill

Use this when the Agent should keep the PPT capability after the source repository is removed.

Prerequisites:

- `uv` is installed and available on `PATH`.
- Git is installed and available on `PATH` for later branch checks and upgrades.
- The Agent can write to `$CODEX_HOME/skills` or `~/.codex/skills`.
- Network access is available for the first dependency and Chromium installation.

Windows:

```powershell
py -3 .codex\skills\ppt-deck-workflow\scripts\install_global_skill.py `
  --bootstrap `
  --install-browser
```

macOS/Linux:

```bash
python3 .codex/skills/ppt-deck-workflow/scripts/install_global_skill.py \
  --bootstrap \
  --install-browser
```

Default target:

```text
$CODEX_HOME/skills/ppt-deck-workflow
```

Fallback target when `CODEX_HOME` is unset:

```text
~/.codex/skills/ppt-deck-workflow
```

The installed skill includes its own deterministic runtime under `runtime/`; it does not import files from the original checkout. The runtime includes HTML screenshot export, image/SVG PPTX export, editable DOM export, Pillow crop embedding, and the bundled JavaScript PPTX exporter.

The installer records its GitHub repository, branch, commit, dirty-source status, managed file hashes, selected Playwright requirement, cache-reuse decision, and browser revision in `.install-state.json`. By default it records `https://github.com/TuKJet/PPT-AGENT.git` and branch `codex/all-logic-in-skills` when Git discovery is unavailable.

Before syncing dependencies, the installer inspects the shared Playwright cache's `.links` records. If a linked Playwright package maps a complete cached Chromium headless-shell revision to a version that satisfies the Skill minimum, the installed runtime materializes the highest such version and reuses that browser. If no reliable compatible pair exists, it keeps the open minimum requirement and lets Playwright install the required headless shell into the shared OS cache. It never guesses a Playwright package version from a raw revision directory alone.

After installation, restart or refresh the Agent/skill catalog if the host does not discover new skills dynamically.

### Global Verification Checklist

Resolve the installed path and run:

```powershell
$CodexHome = if ($env:CODEX_HOME) {
  $env:CODEX_HOME
} else {
  Join-Path $HOME ".codex"
}
$PptSkill = Join-Path $CodexHome "skills\ppt-deck-workflow"

Test-Path "$PptSkill\SKILL.md"
Test-Path "$PptSkill\agents\openai.yaml"
Test-Path "$PptSkill\runtime\pptx_builder.py"
Test-Path "$PptSkill\runtime\vendor_presentation_core\export\dom-to-pptx.bundle.js"

uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\workflow.py" --help
```

Expected results:

- Every `Test-Path` returns `True`.
- `workflow.py --help` exits successfully.
- The command list contains `choose-img-svg`, `complete-img-svg`, and `export-img-svg`.

### Global Workspace Behavior

The installed workflow treats the current working directory as the deck workspace:

```text
<current-directory>/output/<project>/
```

Override the workspace when necessary:

```powershell
$env:PPT_AGENT_WORKSPACE = "D:\work\ppt-workspace"
```

Or override only the output root:

```powershell
$env:OUTPUT_DIR = "D:\work\ppt-workspace\output"
```

Do not write deck artifacts inside the global skill installation directory.

### Upgrade

Use the globally installed updater instead of replacing the Skill from a newer checkout. Local status does not use the network:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" status
```

Check the recorded GitHub branch without changing files:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" check
```

After the user explicitly requests the mutation, upgrade with:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" upgrade
```

The updater clones the recorded branch into a temporary directory, validates a candidate, preserves `.venv`, uv caches, local `uv.lock`, and the shared Playwright cache, then rolls back automatically if synchronization or verification fails. Use the updated Skill instructions on the next Agent turn.

Restore the newest retained backup with:

```powershell
uv run --project "$PptSkill\runtime" `
  python -B -u "$PptSkill\scripts\update_global_skill.py" rollback
```

### Failure Recovery

- `uv` not found: install uv and rerun the same installer command.
- dependency sync fails during initial installation: verify network/proxy access, then rerun the installer with `--force --bootstrap` only when a full replacement is intended.
- Chromium headless shell missing: rerun the installer with `--force --bootstrap --install-browser` for a full replacement, or run the global updater's `upgrade --force` path.
- skill already exists: inspect the existing copy, then use `--force` only when replacement is intended.
- managed Skill files changed locally: review them before upgrading; do not use `--allow-local-changes` unless the user explicitly approves overwriting those changes.
- GitHub upgrade fails after applying files: inspect `$CODEX_HOME/skill-state/ppt-deck-workflow/backups`; the updater attempts automatic rollback and keeps the active Skill outside the backup discovery path.
- global skill is discovered but export imports fail: verify the installed `runtime/` tree and run the global `workflow.py --help` command from the verification checklist.

## Running The Workflow

Always run from the repository root and use the local `ppt-deck-workflow` skill.

Codex generates `outline.json`, `contents.json`, `slide-plans.json`, and renderer source files. The helper only manages state, previews, cleanup, and export:

After `slide_plans` approval, present `img` first and recommend it by default. Keep `html` for an explicit deterministic-layout or editable-PPTX need, and keep `svg` for an explicit direct-SVG need.

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py init --topic "..." --audience "..." --pages "12"
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

For the IMG renderer, the normal export is not the end of the workflow. It creates the original IMG PPTX, then the agent must show it to the user and ask the post-export IMG-to-SVG question. Record the answer only after that handoff:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode off
# or
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

When `on`, pass each `render-jobs/img-svg/slide-xx.json` `source_image_path` directly to a vision-capable model and save one final hybrid SVG to its exact `target_path`. Keep text and simple geometry vector. For incompatible icons, logos, badges, or small complex regions, place crop placeholders in that final SVG and run:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/embed_img_crops.py --manifest output/.../render-jobs/img-svg/slide-01-crops.json
```

The helper crops directly from the source IMG with Pillow and embeds Base64 PNG data without temporary PNG files. Do not create layered or versioned SVG intermediates.

## Rerun Hygiene

Before rerunning final export for the same run directory, call:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
```

The helper removes render-only outputs and preserves approved source artifacts.

## Expected Outputs

For HTML:

- `output/<run>/html/*.html`
- `output/<run>/<deck>-html.pptx`
- `output/<run>/<deck>_editable.pptx` when DOM editable export succeeds
- `output/<run>/editable-ppt-chain.json`

For SVG:

- `output/<run>/svg/*.svg`
- `output/<run>/<deck>-svg.pptx`

For IMG:

- `output/<run>/img/*.{png,jpg,jpeg}`
- `output/<run>/<deck>-img.pptx`

For the optional post-export IMG-to-SVG derivative:

- `output/<run>/render-jobs/img-svg/*.json`
- `output/<run>/img-svg/*.svg` with vector structure plus safe embedded source crops where required
- `output/<run>/<deck>-img-svg.pptx` with native SVG media
- `output/<run>/img-svg-chain.json`

For multi-renderer comparison, keep those artifacts in the same run directory and compare `html/`, `svg/`, `img/`, and the renderer-specific PPTX files side by side.

## Troubleshooting

- If Playwright cannot launch Chromium, rerun `uv run playwright install --only-shell chromium`.
- If editable export fails, the image PPTX can still be valid; check `workflow-state.json` and `slide-status.json`.
