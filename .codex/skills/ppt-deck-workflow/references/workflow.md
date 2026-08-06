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
  img  -> Codex imagegen full-slide images -> completed IMG PPTX -> optional explicit IMG-to-SVG opt-in -> native-SVG PPTX
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
12. Ask for renderer choice, present `img` first, and recommend it by default.
13. Run helper `choose-renderer`.
14. If renderer is `html` or `svg`, ask whether to enable render review. Default recommendation: `off`.
15. For `html` or `svg`, run helper `choose-review`; skip this step for `img`.
16. For long or dense `html`/`svg` decks, optionally materialize renderer job files with `prepare-render-jobs`, then let subagents create the per-page renderer source files.
17. Codex creates the renderer source files using `prompt-contracts.md`, the approved `deck_strategy`, and the single deck-level `design_system`; page renderers inherit its palette tokens instead of selecting colors independently.
18. If render review is `on`, run the Codex-side screenshot review and repair subflow, then helper `complete-review`.
19. If you need to clear stale derived outputs, run helper `clean-render`, then create or verify the renderer source files for that branch, then `export`.
20. For `img`, `export` creates the original IMG PPTX and completes the requested workflow. Show the IMG PPTX to the user; no decline response is required.
21. Ask once whether the user wants the optional IMG-to-SVG derivative. Explain that SVG reconstruction preserves text and simple geometry as vectors so PowerPoint can convert much of the page into editable shapes, disclose the additional model calls/Token usage, and require no decline reply. Do not offer a “keep IMG” response option.
22. After an explicit opt-in, run `choose-img-svg --mode on`. Pass each job's actual source image and exact compiled high-fidelity tracing prompt together in the same model turn. Complete the conversion-evidence and crop-strategy manifests, write one final SVG to the exact target, and use Pillow source crops only for tight incompatible artwork; visible text, labels, captions, legends, cards, and simple geometry stay vector. Every crop declares an artwork `content_type` and `contains_text: false`, and the helper rejects broad crops or crops overlapping vector text. Run `complete-img-svg` once to generate rendered comparisons and pending review files; inspect every source/render pair, revise drift, mark faithful pages passed, rerun `complete-img-svg`, then `export-img-svg`. Do not create intermediate SVG variants.
23. Report the IMG artifact as complete whether or not the optional derivative is requested.

## Renderer Guidance

Recommend IMG by default for new deck rendering. Present it first as the polished full-page visual route. The original IMG PPTX is the completed deliverable; IMG-to-SVG is a later explicit opt-in with additional model usage, not a required completion question.

Offer HTML when the user explicitly prioritizes deterministic layout or an editable-PPTX attempt, but do not recommend HTML merely because the user wants a deliverable deck. Offer SVG when the user wants lightweight source pages, quick visual drafts, or direct SVG artifacts.

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
- status `img_svg_generation_pending`: use every job's image and compiled prompt in the same model turn, create exact SVG/evidence/crop outputs, then finish the generated fidelity reviews
- status `img_svg_export_ready`: run helper `export-img-svg`
- renderer chosen and otherwise ready: create renderer files, then run helper `export`

## Optional IMG Post-Export SVG Opt-In

IMG-to-SVG is an optional post-export derivative, not an approval or completion gate. Exporting the IMG PPTX completes the workflow. Do not ask the user to spend a reply declining extra work.

After handing off the IMG PPTX, ask one concise question such as: “是否需要继续转 SVG？转换会尽量保留文字和简单几何的矢量结构，之后可在 PowerPoint 中转换为可编辑形状；该步骤会按页重新调用模型并产生额外 Token/费用。需要时回复‘继续转 SVG’，不需要则无需回复。”

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
# helper prints completed plus optional conversion availability and cost warning
# run the next command only after the user explicitly asks to continue
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
# attach each source_image_path and compiled_prompt in the same model turn
# write one final SVG plus conversion evidence and a crop-strategy manifest per page
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
# first run renders review PNGs and stops while visual review is pending
# inspect each source/render pair, revise drift, mark fidelity reviews pass, then rerun complete-img-svg
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

The legacy `--mode off` command remains accepted for compatibility, but it must not be presented as a required user response. The helper rejects IMG-to-SVG conversion before the IMG PPTX export.

When the answer is `on`, keep the conversion path faithful and auditable:

1. Use the original image and compiled tracing prompt in the same model turn; never reconstruct from summaries or memory.
2. Preserve wording, geometry, palette, spacing, decorations, and every icon without redesign.
3. Reconstruct faithful text and stable geometry as vectors; identify incompatible or fidelity-sensitive regions.
4. Put `<image data-crop-id="...">` placeholders directly in the final SVG and use the bundled Pillow helper to embed those source crops.
5. Record conversion evidence and one crop-strategy manifest for every page.
6. Let the first `complete-img-svg` render source-comparison previews and create pending fidelity reviews.
7. Inspect every pair, revise changed pages, pass the review only when the original design and icons are preserved, then rerun completion and export.

Do not generate temporary icon HTML, temporary icon PNG files, old-vector SVG layers, overlay SVG layers, or `v1`/`v2`/`clean` SVG directories.

After `export-img-svg`, tell the user how to edit the result in desktop PowerPoint: select the SVG object, choose **Convert to Shape**, edit the converted parts from **Shape Format**, and use **Shape Format → Group → Ungroup** when a group remains. Clarify that vector regions become Office shapes, but the result is not guaranteed to contain semantic text boxes, native charts, or SmartArt; text may be vector outlines and embedded raster crops remain images.

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
3. Verify the shared context contains the approved `deck_strategy` and `design_system`, then dispatch one subagent per `render-jobs/<renderer>/slide-xx.json`.
4. Each subagent writes only its own renderer source file into the same run directory.
5. The main agent reviews the set, runs any screenshot-review loop, and sends only failed pages back for repair.
