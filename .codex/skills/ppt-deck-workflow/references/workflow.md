# PPT Deck Workflow Reference

Current branch note: the public Python runner is removed. Use `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...`; Codex generates content and renderer source files directly.

## Phase Model

The workflow has one skill helper and three late renderer branches.

```text
common:
  outline -> contents -> slide_plans -> renderer_choice

renderer branches:
  html -> review_choice(optional) -> Codex-authored HTML files -> render_review(optional) -> image PPTX -> editable PPTX attempt
  svg  -> review_choice(optional) -> Codex-authored SVG files  -> render_review(optional) -> PPTX
  img  -> Codex imagegen full-slide images -> IMG PPTX -> required user SVG choice -> optional direct hybrid IMG-to-SVG -> native-SVG PPTX
```

The common phase must stay renderer-neutral. Do not ask the user to choose `html`, `svg`, or `img` until `slide-plans.json` exists and is approved.

## Recommended Codex Loop

1. Run the helper `init` command.
2. Read `prompt-contracts.md`.
3. Generate `outline.json`, then run helper `preview --artifact outline`.
4. Ask for approval or changes.
5. Approve `outline`.
6. Generate `contents.json`, then run helper `preview --artifact contents`.
7. Ask for approval or changes.
8. Approve `contents`.
9. Generate `slide-plans.json`, then run helper `preview --artifact slide_plans`.
10. Ask for approval or changes.
11. Approve `slide_plans`.
12. Ask for renderer choice.
13. Run helper `choose-renderer`.
14. If renderer is `html` or `svg`, ask whether to enable render review. Default recommendation: `off`.
15. Run helper `choose-review`.
16. For long or dense `html`/`svg` decks, optionally materialize renderer job files with `prepare-render-jobs`, then let subagents create the per-page renderer source files.
17. Codex creates the renderer source files using `prompt-contracts.md`.
18. If render review is `on`, run the Codex-side screenshot review and repair subflow, then helper `complete-review`.
19. If you need to clear stale derived outputs, run helper `clean-render`, then create or verify the renderer source files for that branch, then `export`.
20. For `img`, `export` creates the original IMG PPTX and moves the workflow to `img_svg_choice_pending`. Show the IMG PPTX to the user, explicitly ask whether to run IMG-to-SVG conversion, and stop. Do not ask this question before the IMG PPTX exists.
21. Record the user's answer with `choose-img-svg --mode off|on`. `off` completes the IMG branch. `on` writes one direct-image model job per page under `render-jobs/img-svg/`.
22. When `on`, pass each job's `source_image_path` directly to the model, write one final SVG to its exact `target_path`, use Pillow source crops for incompatible logo/icon regions, run `complete-img-svg`, then `export-img-svg` to create a PPTX with native SVG media. Do not create intermediate SVG variants.
23. Report final artifacts.

## Renderer Guidance

Recommend HTML by default when the user wants a deliverable deck, editable PPTX attempt, or the most stable layout path.

Recommend SVG when the user wants lightweight source pages, quick visual drafts, or pure SVG artifacts. Recommend IMG for polished full-page visuals when editability is not required.

## Resume Guidance

Use:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py status --run-dir output/...
```

Then continue from the first unapproved artifact:

- missing/unapproved outline: generate or revise `outline.json`
- approved outline but missing contents: generate `contents.json`
- approved contents but missing slide plans: generate `slide-plans.json`
- approved slide plans but no renderer: ask renderer choice
- `html` or `svg` chosen but review choice pending: confirm `off` or `on`
- render review enabled but incomplete: finish the Codex review subflow, then run helper `complete-review`
- `img` chosen but the original IMG PPTX does not exist: create IMG files, then run helper `export`
- status `img_svg_choice_pending`: show the exported IMG PPTX, ask the user for the SVG conversion choice, and stop
- status `img_svg_generation_pending`: pass every job image directly to the model and create the exact SVG outputs
- status `img_svg_export_ready`: run helper `export-img-svg`
- renderer chosen and otherwise ready: create renderer files, then run helper `export`

## Mandatory IMG Post-Export Choice

The IMG-to-SVG question is a post-export approval gate, not a renderer-selection option.

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
# helper prints next=ask-user-img-svg; show the IMG PPTX and stop for the user's answer
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
# pass each render-jobs/img-svg/slide-xx.json source_image_path directly to the model
# write one final img-svg/*.svg per page; use embed_img_crops.py for source-cropped image elements
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

Using `--mode off` is valid, but it still must be the user's explicit answer after reviewing the exported IMG result. The helper rejects an IMG-to-SVG choice made before the IMG PPTX export.

When the answer is `on`, keep the conversion path minimal:

1. Reconstruct text and simple geometry as vectors.
2. Identify only the incompatible or fidelity-sensitive source regions.
3. Put `<image data-crop-id="...">` placeholders directly in the final SVG.
4. Use the bundled Pillow helper to embed those source crops as Base64 PNG data in place.
5. Render the final SVG pages with Playwright, then export the native-SVG PPTX.

Do not generate temporary icon HTML, temporary icon PNG files, old-vector SVG layers, overlay SVG layers, or `v1`/`v2`/`clean` SVG directories.

## Multi-Renderer Compare Guidance

When one approved deck needs multiple renderer outputs for comparison:

1. Keep the comparison in the same run directory under `output/<project>/`.
2. Store renderer source files in sibling subdirectories of that same run directory, such as `output/<project>/html`, `output/<project>/svg`, and `output/<project>/img`.
3. Export renderer deliverables with distinct filenames so one renderer never overwrites another renderer's PPTX or status snapshot.
4. Use `clean-render` only to remove derived outputs such as editable exports, review files, `slide-status.json`, and prior `.pptx` files; it is not a renderer-source wipe in this Codex-authored branch.
5. Create separate run directories only when the user explicitly asks for isolated renderer branches.

## Render Jobs And Subagents

Use renderer job files when the main agent should coordinate the deck while subagents own page-local generation work.

1. After `slide_plans` is approved, choose the renderer and, for `html` or `svg`, prepare the renderer jobs:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
```

2. Read `render-jobs/<renderer>/shared-context.json` once in the main agent.
3. Dispatch one subagent per `render-jobs/<renderer>/slide-xx.json`.
4. Each subagent writes only its own renderer source file into the same run directory.
5. The main agent reviews the set, runs any screenshot-review loop, and sends only failed pages back for repair.
