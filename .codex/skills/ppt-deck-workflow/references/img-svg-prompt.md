# IMG-to-SVG Model Prompt

Use this as the only model-facing prompt for IMG-to-SVG reconstruction. Attach the exact source IMG in the same model turn.

Task: faithfully trace the attached presentation slide as one final SVG. This is not redesign, restyling, simplification, or content rewriting. The attached image is the sole visual source of truth; do not reconstruct from plans, summaries, memory, or earlier inspection.

Canvas: `width="1280" height="720" viewBox="0 0 1280 720"`.

Preserve every visible word, number, label, caption, legend, line break, reading order, color, font scale, card, divider, arrow, shadow, decoration, icon, logo, illustration, and spacing. Keep every visible text item in SVG `<text>/<tspan>`; rasterized visible text is a failure. Rebuild stable geometry as SVG primitives. Choose the representation that is most faithful for each difficult visual element: a carefully traced vector, or a tight source crop. Do not replace source-specific artwork with generic icons or approximations merely to avoid a crop.

Use a local `complex_backplate` only when a compact raster detail and editable text are inseparable without visible quality loss. Remove only the declared original text pixels, associate the scrub region with the matching `visible_text` item, and place the exact replacement SVG text after the image. Never use a backplate or crop as a full-slide wrapper, broad card, title band, chart, screenshot strip, or adjacent tile set.

Write exactly one final SVG at the job target. If crops are used, add `<image data-crop-id="...">` placeholders and a version-4 crop manifest; otherwise do not create a crop manifest. The lightweight page manifest's `visible_text` list must contain one `{id, text}` item for every visible text occurrence, including repeated wording. Do not create conversion-evidence files, artwork inventories, layered SVG variants, or explanatory prose.

The SVG must contain no external URLs/files, scripts, animation, external stylesheets/fonts, or `<foreignObject>`. Do not embed the complete source slide as one image. Compare the final SVG with the attached image left-to-right and top-to-bottom before returning it, checking text, artwork, line breaks, geometry, palette, spacing, and any scrubbed backplate for seams, smears, doubled text, or lost detail.
