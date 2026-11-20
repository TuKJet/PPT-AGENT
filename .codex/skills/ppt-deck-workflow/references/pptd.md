# PPTD Branch

Read only after explicit PPTD selection, recorded by `choose-renderer --renderer pptd`.

Use the bundled PPTD WASM/CLI exporter directly. Do not add a template engine or new intermediate DSL. For `--source img`, also read [img-pptd.md](img-pptd.md). Do not invoke the reference project's separate Skill workflow. The local browser editor is an optional user-facing editing surface, not a required generation step; start it only when the user explicitly asks to edit in the browser or inspect the project interactively.

`--source img` uses hybrid reconstruction by default: editable copy and key data, faithful simple geometry, and separate source crops for complex visuals. Apply the IMG guide's region choices before the generic generation steps below. PPTD is the editable project format, not a requirement that every visual be a native shape; full native reconstruction needs an explicit user request.

## Visual materials

Choose materials according to their purpose: use user-provided assets and authoritative images for actual products, people, interfaces, places, and evidence. Search when suitable real material is missing. Use the available image-generation tool for conceptual illustrations, textures, backgrounds, or matching an established visual style. Generated illustrations must not be presented as documentary evidence.

Prepare assets before positioning the page around their proportions. For generation, specify the subject, palette, aspect ratio, composition, and empty space needed for native text. Keep editable copy out of generated assets. For direct PPTD authoring, use the job's selected reference images for their assigned features: place editable headings according to this page's plan and attach the artwork reference for the drawing features chosen for it. Inspect the result at its intended size. Search and generation are agent/tool actions, not functionality implemented by the exporter. If the relevant tool is unavailable, use supplied/local materials and disclose any material limitation.

Store final assets in `pptd/media/` and reference relative paths. For searched or generated assets, record their source URL or generation prompt/tool and intended usage in `pptd/media-sources.json`; for original-image crops, record source image and crop coordinates. This record is provenance, not an additional user approval stage. Reuse suitable existing assets; a PPTD page does not require a preceding full-page IMG generation.

## Generation

1. Run `prepare-render-jobs --run-dir output/<project> --renderer pptd`.
2. Read the relevant portions of [pptd-format.md](pptd-format.md): global units, multi-file structure, theme, page, element base, and the element types actually used. Use its headings to locate sections; avoid reading the complete chart catalog for a text/image page. Read advanced tables/charts/math only when needed. The format reference is syntax documentation, not a promise of lossless conversion.
3. Codex directly writes `pptd/deck.pptd`, `pptd/pages/*.page`, and local assets under `pptd/media/`. Translate approved plans into concrete coordinates and elements; no additional approval artifact is required.
4. Use `version: v2`, a shared theme, an explicit page size (normally `[960, 540]`), and relative page/media paths. Keep page filenames from the render jobs and put them in the approved order in the manifest. Author text and simple shapes as independent elements; for IMG reconstruction, follow the IMG guide's rules for inseparable diagram regions and raster labels. Use images for photos/illustrations and complex source visuals. Never use a full-page image as a substitute for an editable page.
5. Preserve exact final Chinese copy and numbers, stable element IDs, and deck-level palette tokens. Batch image preparation before laying out around image proportions. All media must be local to the project for repeatable offline export; do not embed base64 images in the model's YAML output.

For `plan.data_regions`, author the surrounding page and leave those rectangles free. Validation/export places native chart and table objects from the plan in those coordinates. Each exported line or bar chart includes its Excel data. Change managed values in the canonical plan before re-exporting. Other artwork and manually authored elements follow the normal PPTD workflow.
6. Run `validate-pptd --run-dir output/<project>`. Repair invalid pages. This checks structure and local dependencies, not visual fidelity.

## Optional local editor

Do not start the editor during ordinary generation or QA. After generation and validation, use the CLI export below. Start the editor only for an explicit request such as “open the PPTD editor” or “let me adjust this in the browser”:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py open-pptd-editor --run-dir output/<project>
```

Use the global runtime command prefix in an installed Skill. This is a long-running foreground server; keep its terminal/session alive. It binds `127.0.0.1` on an available port, prints `editor_url` and `project_dir`, and serves only the bundled editor. Opening a browser tab or using Computer Use is permitted only for that explicit request. Do not repeatedly create new servers if the existing session is healthy.

For this first version, use the editor's **打开 PPTD 文件夹** action to select the printed `project_dir` (the run's `pptd/` directory). Tell the user the exact directory. Chromium's folder permission enables editing and saving to disk. Read-only upload mode saves edits in memory only; do not claim those edits reached disk. Do not present the editor's built-in demo as the generated deck.

Use the loaded deck to inspect rendered pages only when the user requested the editor. Correct material clipping, overlap, missing assets, and text errors before delivery; structural validation alone is not a visual pass. Users may refine and manually export through the editor, but the agent's normal delivery remains the deterministic CLI export.

Keep Agent and browser editing sequential: wait for the editor to show saved before reading its files; close/reload the document after Agent edits. Do not regenerate pages over unsaved browser changes. No automatic file-watch or conflict-merge facility is promised in this first version.

## Export and delivery

Before PPTX delivery, run `export-pptd-images --run-dir output/<project>` as a background QA operation. This drives the bundled local renderer with Playwright on macOS/Windows/Linux, saves the downloaded ZIP, decodes all pages, and builds `.qa-images/overview.jpg`; it does not open an interactive editor or require Computer Use. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` can select an existing compatible Chromium binary. Remote assets/fonts are blocked for repeatability; use local assets and review font wrapping.

Read `.qa-images/manifest.json` for the P1..Pn to `.page` mapping. Inspect the overview, then full-resolution `pages/*.png` for suspicious pages. Check image clarity/proportions, exact copy, text overflow, overlap, contrast, alignment, page boundaries, and missing visuals. Correct the `.page` files, rerun with `--force`, and inspect again before delivery. For IMG reconstruction, call the reusable `compare-pptd` operation to compare source IMG and rendered pages; it produces a review-only image/hash artifact, never HTML. A successful image export means review is pending, never that the visual check passed. These are renderer previews, not PowerPoint readback previews. If browser export fails, preserve the project and report the error; do not substitute a demo or claim visual QA passed. Store temporary review outputs under `.workflow/` or `.qa-images/`, then clean them during finalization.

`export --run-dir output/<project>` reads the latest saved project and writes `<topic>-pptd.pptx`. Requires Node.js 18+; uses bundled WASM offline and the current Python runtime for YAML. No Kimi login or reference repository is required. The browser may request optional remote fonts such as MiSans and fall back to installed fonts when unavailable; prefer locally available fonts and inspect wrapping. Do not install prerequisites silently.

The CLI preserves supported native text, shapes, pictures, and tables. Its font arrays are empty: do not promise embedded fonts. The browser writer has additional preprocessing for icons, formulas, and some charts; complex charts can become images. Prefer text/shapes/lines/images/tables for initial validation. If CLI export cannot represent a requested advanced element, use browser export and report the limitation; never silently flatten the deck as a fallback.

Read `slide-status-pptd.json` after helper export. The normal delivery is the PPTX plus the necessary PPTD source (`deck.pptd`, `pages/`, `media/`, and provenance). Do not deliver a local editor URL unless the user explicitly requested the editor. Browser-download exports are separate from the helper's recorded artifact. Do not mark them as helper exports without checking the file.

## Finalization and clean output

The run directory is an authoring workspace during generation, not the delivery package. Finalization must leave only the canonical `outline.json`, `contents.json`, `slide-plans.json`, the requested PPTX, and the necessary `pptd/` source tree (or the requested IMG source files). Remove generated previews, render jobs, prompt dumps, browser ZIPs, comparison images/manifests, ad-hoc scripts, HTML viewers, and other temporary review files through the helper's finalization command. Never create a second planning Markdown report alongside the canonical slide plan; human-readable previews are projections used during approval and are disposable.
