# IMG-to-SVG Conversion Contract

This is the operational contract for the optional post-export IMG derivative. The original IMG PPTX is complete before this flow starts, and conversion begins only after an explicit `choose-img-svg --mode on` opt-in.

Keep one final SVG per source IMG under `img-svg/`. The source image and the compiled prompt are passed together in one vision-model turn. The model traces the source faithfully; it does not redesign, simplify, or rewrite the page. The exact prompt lives in [`img-svg-prompt.md`](img-svg-prompt.md).

For each page, preserve every visible text item as SVG `<text>/<tspan>`; rasterized visible text is a failure. Preserve layout, wording, line breaks, colors, geometry, spacing, decorations, and reading order. The model may choose vector reconstruction or a tight source crop for icons, logos, illustrations, photos, textures, and other difficult artwork. There is no type-based requirement to crop or trace.

Use the Pillow helper only for declared local crops. A crop is optional, must have a unique id and valid normalized `[x, y, width, height]` source box, and must correspond to an `<image data-crop-id="...">` placeholder. A `complex_backplate` is allowed only for a compact raster detail that cannot be separated from editable text without visible drift. Its scrub boxes may reference only the relevant `visible_text` items, and the replacement SVG text must follow the cleaned image in document order. Do not use broad page, card, chart, title-band, or screenshot crops.

The version-3 manifest at `render-jobs/img-svg/manifest.json` contains a `slides` list and one shared `prompt_path`; there are no separate page-job files. Each slide has `visible_text` entries with `id` and exact `text`, with a separate entry for each repeated occurrence. The helper checks missing and extra SVG text. Ordinary text needs no box. A version-4 crop manifest exists only when crops are used. Its optional root `visible_text` contains only nearby text or backplate replacement items, adding normalized `source_box` coordinates to the matching page items. Only backplate crop entries need `replacement_text_ids` and `text_removal_boxes`. It is not a page-wide artwork inventory. No conversion-evidence file is required: the helper records source, SVG, text, crop, environment, and preview hashes automatically.

Do not create layered SVG variants. `complete-img-svg` first returns a normal `pending_visual_review` state, renders changed pages, and records similarity metrics as diagnostics. Review records (version 2) use `status: pending_visual_review` or `pass`, include `text_checked: true` for a pass, reviewer, notes, and the source/SVG hashes. Unchanged pages reuse their previews and passing reviews; `--force-render` explicitly invalidates that reuse. Any source or SVG change invalidates only that page.

Before `export-img-svg`, the helper requires one current, passed review per source page, matching hashes and page order, valid SVG XML and viewBox, safe embedded data images, no external resources, scripts, or `<foreignObject>`, and no full-slide raster wrapper. The exporter embeds native SVG media and the corresponding PowerPoint preview.

## Operation

Use the local/global Python command prefix from `SKILL.md` for these helper commands:

1. Run `workflow.py choose-img-svg --run-dir <project> --mode on` after opt-in.
2. Read `render-jobs/img-svg/manifest.json` and its `prompt_path`. For each slide,
   inspect the actual source image with that prompt and write the final SVG to
   `target_path`. Populate the slide's `visible_text` list from the source.
3. If crops are needed, write the optional crop manifest and run
   `embed_img_crops.py --manifest <crop_manifest_path>`. Its fields are
   `version: 4`, `source_image_path`, `svg_path`, `canvas: {width: 1280, height: 720}`,
   and `crops`. Each crop has `id`, `source_box`, optional `target_box` (defaults to
   source box), `content_type`, and `contains_text: false` for the final pixels.
   For backplates, add root `visible_text` items with source boxes and the crop's
   `replacement_text_ids` / `text_removal_boxes`; removal boxes must cover the
   associated text and remain inside the crop. The optional removal mode defaults
   to `light_neutral` (`dark_neutral` and `all` are alternatives); dilation defaults
   to 2 and supports integers 0–4. Do not create a crop file for a vector-only page.
4. Run `workflow.py complete-img-svg --run-dir <project>`. Pending visual review is
   a normal result (`next=review-img-svg`), not a command failure.
5. View each original and its `rendered_preview_path` together. Check wording,
   repeated labels, line breaks, geometry, artwork, crop edges and any text-scrubbed
   areas. Repair actual defects. Only after inspection, set the page review's
   `status` to `pass`, `text_checked` to `true`, and add `reviewer` and concrete
   `notes`. Leave the automatically calculated hashes unchanged. A failed review
   remains failed until the page is repaired and inspected again.
6. Rerun completion, then `workflow.py export-img-svg --run-dir <project>`.

Old per-page jobs remain readable. If their text metadata is absent, the helper
seeds a checklist from the SVG for source-image review; this is not independent
proof that all source wording has been transcribed. Old reviews require a new
review, but source images and existing SVG files need not be regenerated.

Keep the original IMG PPTX beside the derivative. Do not run `clean-render` between
its export and optional conversion. When PowerPoint is installed, open the final
PPTX and export every slide to PNG for the Office rendering check.

## PowerPoint handoff

Tell the user to select the SVG in desktop PowerPoint, choose **Convert to Shape**
(also available from **Graphics Format**), then edit the converted pieces using
**Shape Format**. Use **Group → Ungroup** when needed. Vector parts can become
editable shapes; this does not guarantee semantic text boxes, native charts or
SmartArt. Text may become vector shapes, and embedded raster crops remain images.
