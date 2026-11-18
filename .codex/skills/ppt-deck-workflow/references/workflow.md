# Workflow

Create one new run under `output/<project>/`. Keep all artifacts in the same run directory.

1. Outline → preview → explicit chat approval.
2. Contents → preview → explicit chat approval.
3. Version-3 slide plans with per-page copy layers → preview → explicit chat approval. Existing version-2 plans remain readable.
4. User chooses IMG or PPTD. Recommend IMG by default unless editability is the priority.
5. Load only the chosen branch guide. PPTD specifications must not be read before selection.
6. IMG: imagegen full-slide sources → original image PPTX.
7. PPTD: model-authored manifest/pages/media → validation → deterministic CLI PPTX export. Background Playwright image export may run for agent QA; the interactive browser editor starts only after an explicit user request.

HTML and standalone SVG renderers are removed from selection, jobs, and export. Legacy source files are not deleted by cleanup.

IMG-to-SVG remains an optional post-export derivative, separately authorized after IMG export. Do not ask the user to spend a reply declining it. Read its instructions only after opt-in; native SVG media is not a guarantee of semantic PowerPoint text/chart objects.

See the stage links in SKILL.md. No repository AI provider or runner is involved.

## Run hygiene and finalization

Keep one canonical source of truth: `outline.json`, `contents.json`, and `slide-plans.json`. Approval previews are generated projections; do not write a second planning Markdown report or an HTML gallery. Put render jobs, prompt snapshots, browser ZIPs, comparison images, and other review state under `.workflow/` or `.qa-images/`. Use the built-in finalization/cleanup command after export. The final run contains only the canonical planning files, requested PPTX, and the necessary renderer source tree (`pptd/deck.pptd`, `pptd/pages/`, `pptd/media/`, and provenance when PPTD is requested). Preserve user-authored source files; unknown files are surfaced for review rather than silently deleted.
