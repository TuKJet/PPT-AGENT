# PPT Deck Workflow Agent

Codex-facing PPT generation workflow with explicit outline, content, slide-plan approval checkpoints and HTML/SVG/IMG renderer branches.

This branch is skill-first. Codex generates deck content inside the Codex conversation; repository code only handles deterministic artifact bookkeeping, render cleanup, screenshots, and PPTX export.

## Repository Surface

The executable surface is intentionally small:

- `.codex/skills/ppt-deck-workflow/`: workflow instructions, contracts, and the state/export helper
- `html_pipeline/html_builder.py`: deterministic 1280x720 HTML screenshot and image-PPTX export
- `pptx_builder.py`: deterministic SVG image-PPTX export and native-SVG PPTX export
- `vendor_presentation_core/export/`: retained DOM editable export and bundled browser runtime
- `playwright_runtime.py`, `filename_utils.py`: shared deterministic utilities

There is no repository model client, provider configuration, generation pipeline, or runner. HTML/SVG source files are authored by Codex and exporters do not silently rewrite them.

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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Codex writes `outline.json`, `contents.json`, `slide-plans.json`, and the final `html/`, `svg/`, or `img/` renderer files. The helper does not call model APIs.

For `html` and `svg`, renderer choice is followed by an explicit render-review preference:

- `off`: default and recommended unless the user wants an extra review/repair pass
- `on`: Codex runs a screenshot review subflow before export, then records completion with `complete-review`

For `img`, the first `export` creates the original full-image PPTX and deliberately stops at `img_svg_choice_pending`. Only then must Codex show that PPTX to the user and ask whether to run the IMG-to-SVG post-process. The helper rejects an early choice.

```bash
# after the IMG PPTX exists and the user answers in chat
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode off

# or, to create one direct-image model job per page
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

With `on`, every `render-jobs/img-svg/slide-xx.json` contains a `source_image_path` that must be passed directly to a vision-capable model. The returned page must be a pure-vector 1280x720 SVG under `img-svg/`; the final `<topic>-img-svg.pptx` embeds native SVG media rather than rasterizing it.

For multi-renderer comparison, keep everything in the same run directory under `output/<project>/`. Compare outputs by subdirectory and renderer-specific export filenames instead of forking separate `-html` / `-img` project folders.

For long HTML or SVG decks, prefer `prepare-render-jobs` and let subagents generate one page each while the main agent stays focused on consistency review and export coordination.

## Notes

- Generated decks are written to `output/`.
- Content research should use Codex-native research/web capability directly, not repository AI provider code.
- HTML and SVG export require Playwright Chromium.
- Native IMG-to-SVG PPT export also requires Playwright Chromium because the bundled exporter creates PowerPoint's native SVG media plus its PNG preview.
- HTML export creates an image PPTX and attempts a DOM-based editable PPTX.
- The former `ppt_workflow.runner`, provider client, generation pipeline, prompt/template runtime, and `.env.example` are intentionally removed from this branch.
