# Agent Initialization Guide

Use this guide when an agent is asked to set up this project on a fresh machine.

## Goal

Prepare the repository so the Codex skill can manage PPT artifacts and export decks without relying on copied local runtime folders or repository model API credentials.

## Do Not Commit Or Copy

Do not commit these machine-local or generated paths:

- `.venv/`
- `.python/`
- `.ms-playwright/`
- `.env`
- `output/`
- `__pycache__/`
- `.omx/`
- `.ppt_agent_cache/`

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

3. Install Playwright Chromium for the current OS.

```bash
uv run playwright install chromium
```

4. Verify the skill helper.

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py --help
```

## Running The Workflow

Always run from the repository root and use the local `ppt-deck-workflow` skill.

Codex generates `outline.json`, `contents.json`, `slide-plans.json`, and renderer source files. The helper only manages state, previews, cleanup, and export:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py init --topic "..." --audience "..." --pages "12"
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode off
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

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

For multi-renderer comparison, keep those artifacts in the same run directory and compare `html/`, `svg/`, `img/`, and the renderer-specific PPTX files side by side.

## Troubleshooting

- If Playwright cannot launch Chromium, rerun `uv run playwright install chromium`.
- If editable export fails, the image PPTX can still be valid; check `workflow-state.json` and `slide-status.json`.
