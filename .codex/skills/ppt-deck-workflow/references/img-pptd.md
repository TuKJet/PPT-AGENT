# IMG to Editable PPTD

Use after the user requests an editable derivative of generated IMG pages. Preserve original pixels in the image PPTX, requested SVG derivatives and unrelated manual PPTD edits. Keep working IMG sources until verified final cleanup; `restore-img` can recover them later without regeneration.

## Interpret editability

Default to **hybrid reconstruction with visual fidelity**. “可编辑”, “参考图片走 PPTD” and “转成可编辑 PPT” authorize editable text and separately movable visual assets; they do not request replacing all artwork with native shapes. Tell the user briefly: “按原图保真转成可编辑版：文字和关键数据可编辑，复杂图像裁剪保留并可独立移动、缩放。” Then proceed; do not add an approval stage.

Only explicit requests such as “全部用原生元素”, “不要图片” or “图中节点和连线都能单独修改” override the hybrid default, and only within the requested scope. A requirement that one chart's data be editable does not apply to the deck's illustrations. “不用 SVG” only excludes SVG. For an explicit native request, honor it and disclose unavoidable fidelity or asset limits; do not silently return raster content as fully native.

Choose representation per region before authoring:

| Region | Default treatment |
| --- | --- |
| Titles, body, key numbers and independently placed labels | Editable text, preserving copy and placement |
| Simple cards, rules, arrows and geometric structures | Native elements when they faithfully reproduce the source |
| Photos, textured/3D icons, networks, hardware art, glow and other complex visuals | Tight source crops as separate pictures, preserving texture, geometry and effects; do not replace with generic icons or rough shapes |
| Dense diagrams with inseparable internal labels/lines | Preserve the complete diagram region as one independently movable picture; keep surrounding copy editable and disclose that internal labels remain raster |
| Charts/tables requiring editable data | Use authoritative data for native reconstruction; do not invent values from pixels |

An image-heavy source should retain its visual assets. There is no target native-element ratio. Editable object count does not compensate for lost visual quality, and a full-slide image with duplicate text overlays is not hybrid reconstruction.

## Reconstruct and verify

1. Record `choose-renderer --run-dir <run> --renderer pptd --source img`, then `prepare-render-jobs --run-dir <run>`. The helper validates image count, page filenames and decoding before recording the choice. Jobs include `image_reference` with the absolute image path, pixel size and SHA-256.
2. Pass each referenced IMG directly to the vision-capable model. Use approved copy and data as the textual authority; use the IMG for composition, relative geometry, colors and visual assets. Resolve visible discrepancies using approved content, and report material departures from the reference. Do not regenerate from plans alone.
3. Write ordinary `pptd/deck.pptd`, `pages/*.page`, and `media/` using the PPTD guide and the region choices above. The jobs' `reconstruction_policy` repeats the hybrid default for page-local work; pass explicit user overrides and their scope to any delegated author. Preserve source composition, visual density and asset identity rather than redesigning from the plans.
4. Reuse original pixels for suitable illustrations and photos. Either copy the source to a uniquely named file in `pptd/media/` and use the image element's proportional `crop`, or crop it with Pillow into a separate local asset. Scale source coordinates to the declared PPTD size: `x_pptd = x_pixel * page_width / source_width`, likewise for y and dimensions. Keep source dimensions separate from the usual 1280x720 SVG canvas and 960x540 PPTD canvas. Do not stretch cropped content.
5. Inspect crops for baked-in text and background edges. Avoid duplicate text overlays. When text cannot be cleanly separated from a complex visual, keep that region intact and disclose its internal text limit. Use image editing for a clean asset only when the requested text edit requires separation; inspect changed details. Do not force shape reconstruction merely to remove baked-in labels. Cropping cannot recover hidden pixels. Record source/crop or edit provenance and any internal text retained in `pptd/media-sources.json`.
6. Run `validate-pptd` and `export-pptd-images`, inspect `.qa-images/overview.jpg`, and call the reusable `compare-pptd` operation to compare every rendered page with its original IMG. Check all approved text, crop boundaries, repeated text, text wrapping, alignment and missing visuals. For every diagram or process, perform an explicit relation audit: each visible label maps to one authored text element or an intentionally documented raster region; each edge has the correct start and end nodes, direction, arrow head, branch, merge, feedback loop, and nearby label. Use the PPTD line schema `viewBox` + `points` + `arrow: [start, end]`; do not substitute unsupported arrow fields. Counting arrows or passing structural validation does not prove that relationships are correct. Explicitly check whether textured art, dense diagrams, glow or source-specific icons were replaced with visibly weaker approximations; in hybrid mode restore source crops rather than accepting this as an editability tradeoff. Inspect suspicious regions at full resolution and repair them; regenerate images with `--force` after edits. Keep comparison output and notes under `.workflow/` or `.qa-images/`; they are temporary review artifacts and must be removed during finalization.
7. Export through the existing PPTD exporter. The helper rejects missing/changed image references relative to prepared jobs. After a source changes, refresh jobs and inspect/rebuild affected pages; do not refresh hashes merely to bypass a mismatch. Report actual editability: native text/structure versus movable raster pictures. Browser preview is not PowerPoint readback verification.

The original IMG is the visual reference, not editable source layers. This route is model-authored reconstruction with deterministic packaging, not automatic lossless image conversion. Do not overwrite an existing manually edited PPTD project without incorporating those edits or obtaining direction when intent conflicts. Do not create an HTML gallery, a second planning report, or a one-off repair script for a normal run; reusable comparison and validation belong in the Skill helpers.
