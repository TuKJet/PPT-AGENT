# Agent Initialization Guide

Use this guide when an agent is asked to set up this project on a fresh machine, including Windows.

## Goal

Prepare the repository so the PPT workflow can run from source with `uv`, without relying on copied local runtime folders.

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

They are intentionally excluded because Python virtual environments, Python runtime builds, and Playwright browser caches are OS/architecture-specific.

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

4. Create local environment config.

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

5. Edit `.env`.

Set at least:

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
HTML_AI_REVIEW_ENABLED=false
SVG_AI_REVIEW_ENABLED=false
```

6. Verify the runner.

```bash
uv run python -m ppt_workflow.runner --help
```

7. Optional API smoke test.

```bash
uv run python -c "from ai_client import AIClient; c=AIClient('openai'); print(c.provider, c.model); print(c.chat('test', '只回复 OK', temperature=0.1)[:80])"
```

## Running The Workflow

Always run from the repository root.

Generate outline:

```bash
uv run python -u -m ppt_workflow.runner outline --topic "..." --audience "..." --pages "12" --provider openai --research "..."
```

Approve artifacts only after the user approves in chat:

```bash
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact outline
uv run python -u -m ppt_workflow.runner contents --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact contents
uv run python -u -m ppt_workflow.runner plans --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact slide_plans
```

Choose renderer after slide plans are approved:

```bash
uv run python -u -m ppt_workflow.runner choose-renderer --run-dir output/... --renderer html
```

Final render with review disabled by default:

```bash
HTML_AI_REVIEW_ENABLED=false SVG_AI_REVIEW_ENABLED=false uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

Windows PowerShell equivalent:

```powershell
$env:HTML_AI_REVIEW_ENABLED="false"
$env:SVG_AI_REVIEW_ENABLED="false"
uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

## Rerun Hygiene

Before rerunning final render for the same run directory, remove render-only outputs so stale slides cannot enter the exported PPTX.

Do not delete approved source artifacts such as:

- `outline.json`
- `contents.json`
- `slide-plans.json`
- `workflow-state.json`

macOS/Linux:

```bash
rm -rf output/.../html output/.../svg output/.../reviews output/.../editable output/.../slide-status.json output/.../editable-ppt-chain.json output/.../*.pptx
```

Windows PowerShell:

```powershell
Remove-Item -Recurse -Force output\...\html, output\...\svg, output\...\reviews, output\...\editable -ErrorAction SilentlyContinue
Remove-Item -Force output\...\slide-status.json, output\...\editable-ppt-chain.json, output\...\*.pptx -ErrorAction SilentlyContinue
```

## Expected Outputs

For the HTML renderer, expect:

- `output/<run>/html/*.html`
- `output/<run>/reviews/slide-*.png`
- `output/<run>/<deck>.pptx`
- `output/<run>/<deck>_editable.pptx`
- `output/<run>/editable-ppt-chain.json`

## Troubleshooting

- If Playwright cannot launch Chromium, rerun `uv run playwright install chromium`.
- If API smoke tests pass but rendering fails with `504`, `502`, or server disconnects, the model gateway likely cannot handle long generation requests. Use a more stable gateway/model or increase upstream timeout.
- If Windows shell syntax fails, use the PowerShell examples above instead of POSIX environment-variable prefixes.
