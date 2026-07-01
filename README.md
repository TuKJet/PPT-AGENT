# PPT Deck Workflow Agent

Codex-facing PPT generation workflow with explicit outline, content, slide-plan approval checkpoints and HTML/SVG renderer branches.

This repository is intended to be distributed as source code. Do not commit machine-local runtimes such as `.venv/`, `.python/`, `.ms-playwright/`, generated `output/`, or a real `.env` file.

## Quick Start

Install `uv` first:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, use PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then initialize the project:

```bash
uv sync
uv run playwright install chromium
cp .env.example .env
uv run python -m ppt_workflow.runner --help
```

On Windows PowerShell, use this instead of `cp`:

```powershell
Copy-Item .env.example .env
uv run python -m ppt_workflow.runner --help
```

Edit `.env` with your model gateway:

```bash
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
HTML_AI_REVIEW_ENABLED=false
SVG_AI_REVIEW_ENABLED=false
```

## Workflow

Run commands from the repository root.

```bash
uv run python -u -m ppt_workflow.runner outline --topic "..." --audience "..." --pages "12" --provider openai --research "..."
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact outline
uv run python -u -m ppt_workflow.runner contents --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact contents
uv run python -u -m ppt_workflow.runner plans --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact slide_plans
uv run python -u -m ppt_workflow.runner choose-renderer --run-dir output/... --renderer html
HTML_AI_REVIEW_ENABLED=false SVG_AI_REVIEW_ENABLED=false uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

Use `--renderer svg` for the SVG branch.

Use `--renderer img` for the full-slide image branch. This branch requires `KRILL_IMAGE_API_URL`, `KRILL_IMAGE_API_KEY`, and optionally `KRILL_IMAGE_MODEL` in `.env`. If they are missing, the workflow will stop and ask you to either configure them or choose `html`/`svg` instead.

Before rerunning a final render, clean only render outputs under the run directory, not approved source artifacts:

```bash
rm -rf output/.../html output/.../svg output/.../reviews output/.../editable output/.../slide-status.json output/.../editable-ppt-chain.json output/.../*.pptx
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force output\...\html, output\...\svg, output\...\reviews, output\...\editable -ErrorAction SilentlyContinue
Remove-Item -Force output\...\slide-status.json, output\...\editable-ppt-chain.json, output\...\*.pptx -ErrorAction SilentlyContinue
```

## Codex Skill

The local skill lives at `.codex/skills/ppt-deck-workflow/SKILL.md`. When using Codex in this repository, ask it to use the `ppt-deck-workflow` skill and keep approvals in chat.

## Notes

- Generated decks are written to `output/`.
- HTML rendering requires Playwright Chromium.
- The editable PPTX export is best-effort and may use DOM source preview when platform-specific PowerPoint readback tools are unavailable.
- Long model calls require a gateway that can handle large `/chat/completions` requests without short timeouts.
- The `img` renderer generates one image per slide via the configured third-party image API and exports a non-editable image PPTX.

