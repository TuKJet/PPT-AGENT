# PPT Deck Workflow Agent

Codex-facing PPT generation workflow with explicit outline, content, slide-plan approval checkpoints and HTML/SVG/IMG renderer branches.

This branch is skill-first. Codex generates deck content inside the Codex conversation; repository code only handles deterministic artifact bookkeeping, render cleanup, screenshots, and PPTX export.

## Quick Start

Install `uv`, then initialize the project:

```bash
uv sync
uv run playwright install chromium
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py --help
```

## Workflow

Use the local skill at `.codex/skills/ppt-deck-workflow/SKILL.md`.

The helper command is:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...
```

Every deck run must live under `output/<project>/`. Keep all intermediate JSON/Markdown artifacts, renderer files, review files, and exported PPTX files inside that single project folder. If you pass `--run-dir deck-a`, the helper now normalizes it to `output/deck-a`; paths outside `output/` are not allowed.

Typical helper calls:

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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Codex writes `outline.json`, `contents.json`, `slide-plans.json`, and the final `html/`, `svg/`, or `img/` renderer files. The helper does not call model APIs.

For `html` and `svg`, renderer choice is followed by an explicit render-review preference:

- `off`: default and recommended unless the user wants an extra review/repair pass
- `on`: Codex runs a screenshot review subflow before export, then records completion with `complete-review`

## Notes

- Generated decks are written to `output/`.
- Content research should use Codex-native research/web capability directly, not repository AI provider code.
- HTML and SVG export require Playwright Chromium.
- HTML export creates an image PPTX and attempts a DOM-based editable PPTX.
- Do not use `ppt_workflow.runner`; it is intentionally removed in this branch.
