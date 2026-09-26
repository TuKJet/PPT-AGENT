# PPTD Branch

Read only after explicit PPTD selection, recorded by `choose-renderer --renderer pptd`.

Use the bundled open-kimi-ppt editor and WASM directly for this initial integration. Do not add a template engine, new intermediate DSL, or IMG reconstruction phase. Do not invoke the reference project's separate Skill workflow.

## Generation

1. Run `prepare-render-jobs --run-dir output/<project> --renderer pptd`.
2. Read the relevant portions of [pptd-format.md](pptd-format.md): global units, multi-file structure, theme, page, element base, and the element types actually used. Use its headings to locate sections; avoid reading the complete chart catalog for a text/image page. Read advanced tables/charts/math only when needed. The format reference is syntax documentation, not a promise of lossless conversion.
3. Codex directly writes `pptd/deck.pptd`, `pptd/pages/*.page`, and local assets under `pptd/media/`. Translate approved plans into concrete coordinates and elements; no additional approval artifact is required.
4. Use `version: v2`, a shared theme, an explicit page size (normally `[960, 540]`), and relative page/media paths. Keep page filenames from the render jobs and put them in the approved order in the manifest. Text and simple shapes must remain independent elements. Use images for photos/illustrations. Never use a full-page image as a substitute for an editable page.
5. Preserve exact final Chinese copy and numbers, stable element IDs, and deck-level palette tokens. Batch image preparation before laying out around image proportions. All media must be local to the project for repeatable offline export; do not embed base64 images in the model's YAML output.
6. Run `validate-pptd --run-dir output/<project>`. Repair invalid pages. This checks structure and local dependencies, not visual fidelity.

## Local editor

After generation and validation, start:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py open-pptd-editor --run-dir output/<project>
```

Use the global runtime command prefix in an installed Skill. This is a long-running foreground server; keep its terminal/session alive. It binds `127.0.0.1` on an available port, prints `editor_url` and `project_dir`, and serves only the bundled editor. Open the printed URL in the available browser tool or Codex browser panel; `--open` opens the system browser when appropriate. Do not repeatedly create new servers if the existing session is healthy.

For this first version, use the editor's **打开 PPTD 文件夹** action to select the printed `project_dir` (the run's `pptd/` directory). Tell the user the exact directory. Chromium's folder permission enables editing and saving to disk. Read-only upload mode saves edits in memory only; do not claim those edits reached disk. Do not present the editor's built-in demo as the generated deck.

Use the loaded deck to inspect rendered pages. Correct material clipping, overlap, missing assets, and text errors before delivery; use available browser screenshots for visual review. Structural validation alone is not a visual pass. Users may also refine and manually export through the editor.

Keep Agent and browser editing sequential: wait for the editor to show saved before reading its files; close/reload the document after Agent edits. Do not regenerate pages over unsaved browser changes. No automatic file-watch or conflict-merge facility is promised in this first version.

## Export and delivery

`export --run-dir output/<project>` reads the latest saved project and writes `<topic>-pptd.pptx`. Requires Node.js 18+; uses bundled WASM offline and the current Python runtime for YAML. No Kimi login or reference repository is required. The browser may request optional remote fonts such as MiSans and fall back to installed fonts when unavailable; prefer locally available fonts and inspect wrapping. Do not install prerequisites silently.

The CLI preserves supported native text, shapes, pictures, and tables. Its font arrays are empty: do not promise embedded fonts. The browser writer has additional preprocessing for icons, formulas, and some charts; complex charts can become images. Prefer text/shapes/lines/images/tables for initial validation. If CLI export cannot represent a requested advanced element, use browser export and report the limitation; never silently flatten the deck as a fallback.

Read `slide-status-pptd.json` after helper export. Deliver the complete PPTD folder, PPTX, and local editor URL. Explain that after manual edits, the user can export again in the editor or save and ask Codex to re-export. Browser-download exports are separate from the helper's recorded artifact. Do not mark them as helper exports without checking the file.
