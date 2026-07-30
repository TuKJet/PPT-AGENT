# Prompt Contracts

Use these contracts whenever Codex generates deck artifacts or renderer source files. They replace the old runner's model prompts from `pipeline.py`, `html_pipeline/pipeline.py`, `layout_policy.py`, `顶级架构师.md`, `顶级设计师.md`, `html-ppt优化提示词.md`, and `vendor_presentation_core/prompts/`.

Do not call those modules to generate content. Reuse the intent below inside Codex reasoning and generated artifacts.

## Outline Contract

Generate a complete renderer-neutral PPT outline.

- Match the requested topic, audience, and page count.
- Use stable slide roles: `cover`, `toc`, `content`, `timeline`, `summary`, `ending`.
- Prefer a coherent narrative arc over a flat topic list.
- Keep each slide title specific enough to key `contents.json`.
- The outline must already reflect audience level, decision context, and expected speaking style rather than leaving those choices only to later rendering stages.
- Make slide titles and section labels read like slide-ready judgments, not presenter notes about what will be discussed.
- Avoid self-referential or meta framing in visible outline copy unless the user explicitly asks for it. Do not use patterns such as `汇报目标`, `管理层关注`, `本页说明`, `下面介绍`, `我们将讨论`, or similar presenter-language placeholders as slide titles or bullets.
- For management or executive audiences, prefer conclusion-led titles that state the implication first and let `contents.json` supply the supporting evidence later.
- Output valid JSON only; no Markdown wrapper.
- Preferred shape:

```json
{
  "pages": [
    {
      "title": "...",
      "sections": ["...", "..."],
      "page_role": "cover"
    }
  ]
}
```

## Outline Audience And Style Contract

Treat audience as a first-class control variable from outline generation onward.

Before drafting visible copy, infer the audience's real decision lens:

- what they are likely trying to decide, approve, avoid, fund, or accelerate
- what uncertainty they most want reduced
- what evidence will change their confidence
- what level of abstraction feels natural to them

Use that inferred lens to shape the whole deck, but keep it implicit in visible copy. The deck should feel naturally tuned to the audience rather than explicitly stating what the audience cares about.

Audience adaptation changes information priority, evidence depth, decision framing, pacing, and visual emphasis. It is not an austerity preset. For leadership audiences, restraint applies to information noise, weak decoration, and competing focal points—not to color, imagery, or visual craft. Do not infer a monochrome or text-only deck from words such as `leadership`, `management`, `executive`, `boardroom`, `restrained`, or `concise`. Keep brand colors, purposeful illustrations, icons, diagrams, data visuals, editorial imagery, and polished visual accents available when they improve comprehension, confidence, recognition, or narrative momentum.

The outline must already reflect audience level:

- what questions they care about first
- what evidence depth they can absorb in the allotted page count
- what decision they are expected to make after reading
- what page roles should be emphasized, compressed, or omitted
- what visual tone should carry into slide plans and rendering

When the user gives audience labels such as `technical`, `management`, `investor`, `executive`, `government`, `operator`, `customer`, or similar, normalize them into the nearest behavior profile below and apply it in outline, content, slide plan, and renderer decisions.

`technical`

- Prioritize architecture, mechanism, implementation path, constraints, tradeoffs, benchmark detail, integration, and risk boundaries.
- Allow denser middle slides and more technical evidence pages.
- Favor explanatory sequences such as system context -> design choices -> implementation details -> performance/risks.
- Reduce empty branding pages and decorative business framing.
- Style direction: precise, structured, information-forward, lower ornament, stronger diagrams/tables/process views.

`management`

- Prioritize business context, current-state issues, strategic value, execution path, milestones, resource implications, delivery risk, and decision asks.
- Keep technical detail only to the level needed for confidence and governance.
- Favor story flow such as why now -> current gap -> recommended direction -> expected outcomes -> roadmap -> ask.
- Use fewer deep-dive pages and more synthesis pages.
- Use high-level, decision-oriented language that sounds like an executive takeaway, not like a narration of management interests.
- Do not write visible copy that literally says what management wants or cares about unless the user explicitly asks for that voice.
- Style direction: calm, credible, boardroom-safe, concise, and clearly hierarchical. Use brand color, diagrams, editorial illustration, restrained photography, or premium accents when they serve the message; reduce clutter and ornamental competition rather than visual expression itself.

`investor`

- Prioritize market, timing, differentiation, traction, unit economics or growth signals, moat, go-to-market, team confidence, and upside/risk framing.
- Compress implementation detail unless it directly supports defensibility.
- Favor persuasion flow such as opportunity -> problem -> solution -> traction -> business model -> moat -> roadmap -> raise/use of funds.
- Make the cover, summary, and closing ask more intentional and high-signal.
- Style direction: polished, high-conviction, premium, sparse but sharp, stronger emphasis on momentum and comparability.

`executive`

- Treat as a stricter management profile with even less tolerance for detail sprawl.
- Put conclusions, key numbers, risk posture, and decision requests earlier.
- Keep the total number of concepts per page low and make page titles conclusion-led.
- Avoid explicit audience callouts in visible copy unless requested; the deck should feel written for executives, not labeled as such on the page.
- Style direction: highly distilled, authoritative, decisive, and polished. Strong brand-led contrast, a memorable key visual, or selective illustration is welcome when it makes the decision clearer; never default to black-white-gray text-only pages merely because the audience is senior.

`government` or `public-sector`

- Prioritize policy alignment, compliance, safety, implementation feasibility, stakeholder coordination, timeline, and measurable outcomes.
- Avoid hype-heavy or aggressively commercial framing.
- Style direction: formal, stable, trustworthy, conservative color and layout choices.

`operator` or `delivery`

- Prioritize workflow, SOP, ownership, dependencies, metrics, risk controls, and next-step execution details.
- Favor process pages, timeline pages, and operational checkpoints over visionary framing.
- Style direction: practical, dense but organized, dashboard/process-oriented.

If the user provides multiple audiences, choose one primary audience for outline control and treat the others as secondary constraints. The primary audience should determine:

- page-count allocation
- slide-role mix
- evidence depth
- tone of titles and bullets
- downstream visual style defaults

If the audience is ambiguous, infer the nearest profile from the user request and keep the assumption stable across outline, contents, slide plans, and rendering unless the user corrects it.

## Content Contract

Audience inference should control what evidence appears first, how much detail is shown, and how the conclusion is phrased, but that inference should usually remain invisible in the slide copy itself.

For each slide, produce page-ready PPT material rather than research notes.

Research may come from Codex-native research capability, not repository AI provider code:

- Prefer a Codex-installed local research skill when one is available in the current session, and use it first to structure or gather evidence for `contents`.
- Otherwise use Codex web search/browsing directly when freshness or external evidence is needed.
- Do not route research through `pipeline.py`, `html_pipeline/pipeline.py`, `AIClient`, or repository model tools.

- Keep only information directly relevant to the slide title.
- Prefer conclusions, capability judgments, concrete facts, dates, metrics, and case outcomes.
- Use 3-5 short bullets by default.
- Keep each bullet compact, typically 30-45 Chinese characters or the English equivalent.
- Do not output URLs, footnote numbers, source lists, or long citations inside slide copy.
- Avoid vague phrasing such as "据报道", "可能", "有观点认为", unless the slide explicitly needs uncertainty.
- If evidence is weak, write conservative capability or logic statements instead of inventing numbers.
- Put research/source notes outside visible slide copy when needed.

## Slide Plan Contract

Create `slide-plans.json` version 2 with one deck-level `deck_strategy`, one deck-level `design_system`, and the page-local `slides`. Define the shared system before writing page plans so every page inherits the same visual language. Version 1 and a free-form string in `plan` are invalid even if the prose happens to mention color or layout.

`deck_strategy` must record the stable audience interpretation used across the deck:

- primary audience and any secondary audience constraint
- the decision or response the deck should enable
- the first questions this audience is likely to ask
- evidence order and detail-depth principles
- presentation posture and desired confidence level

`design_system` must define:

- theme name and audience-fit rationale
- `palette` tokens at minimum for `background`, `surface`, `primary`, `accent`, `text_primary`, and `text_muted`, plus semantic data/status colors when needed
- typography hierarchy
- card, line, radius, spacing, and footer behavior
- chart and diagram treatment
- imagery and illustration policy
- any brand or reference-image design genes

Choose the palette once for the whole deck. Page plans must reference the shared palette tokens and must not invent a new page palette, swap the primary/accent relationship, or introduce unrelated hex colors. Allow a page-specific color only for semantic encoding, a user-supplied asset, or an explicitly justified narrative moment; record that exception in the page plan and keep the rest of the system unchanged.

Do not express "restrained" as a ban on visual assets. The `design_system` should say what visual devices are useful for this audience and topic, not merely prohibit illustrations, brand colors, decorative motifs, photography, or depth.

For each slide plan, specify:

- Core message.
- Page role.
- Layout structure.
- Required visible copy and numbers.
- Visual hierarchy.
- Element types such as title, subtitle, card, metric, timeline, process, matrix, callout, chart, footer.
- Style controls from the user: color, density, typography, visual motif, chart treatment, reference-image influence.
- Audience-driven presentation controls: technical depth, business framing, persuasion intensity, decision orientation, and page-level density.
- Renderer-neutral constraints; do not include renderer-specific class names, CSS, SVG path instructions, or implementation-only notes.

`slide-plans.json` must remain the control surface for art direction. If style guidance changes, edit the plan before rendering.

Use these exact canonical keys. Do not rename them, place them only inside prose, or substitute model-specific aliases:

```json
{
  "version": 2,
  "deck_strategy": {
    "primary_audience": "...",
    "decision_context": "...",
    "first_questions": ["..."],
    "evidence_order": ["..."],
    "presentation_posture": "..."
  },
  "design_system": {
    "theme_name": "...",
    "audience_fit": "...",
    "palette": {
      "background": "#...",
      "surface": "#...",
      "primary": "#...",
      "accent": "#...",
      "text_primary": "#...",
      "text_muted": "#..."
    },
    "typography": {"...": "..."},
    "component_rules": {"...": "..."},
    "chart_treatment": {"...": "..."},
    "illustration_policy": "...",
    "design_genes": ["..."]
  },
  "slides": [
    {
      "index": 1,
      "title": "...",
      "material": "...",
      "page_role": "cover",
      "plan": {
        "core_message": "...",
        "layout_structure": "...",
        "visual_hierarchy": ["..."],
        "required_elements": ["..."],
        "palette_tokens": ["background", "primary", "accent", "text_primary"],
        "style_controls": {"density": "...", "typography": "...", "visual_motif": "..."},
        "audience_controls": {"technical_depth": "...", "decision_orientation": "..."},
        "renderer_neutral_constraints": ["..."]
      }
    }
  ]
}
```

Before asking for slide-plan approval, run the helper preview. A validation error means the artifact is incomplete and must be repaired; never bypass the failure by manually converting only the fields that happened to be generated.

The helper must translate this strict machine schema into a smaller human-readable approval projection. `slide-plans-preview.md` should show the audience/decision lens, visual system, core message, layout, hierarchy, visible elements, and page style using natural labels, a compact palette table, numbered sequences, and bullets. Keep renderer-internal audience controls and neutral constraints in the validated JSON instead of copying them into the approval body. Never copy JSON objects, quoted field names, braces, or fenced `json` blocks into the preview.

The audience decision made in the outline stage must carry forward into `slide-plans.json`; do not silently switch the deck into a different audience style later.

Express audience fit through composition, emphasis, evidence density, ordering, and tone. Do not turn the slide plan into visible rhetoric about what the audience cares about unless the user explicitly requests that framing.

## Render Job Contract

Use this when the main agent wants subagents to render page-local `html`, `svg`, or `img` files without carrying the whole deck context in one conversation window.

The helper command:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
```

materializes:

- `render-jobs/<renderer>/shared-context.json`
- `render-jobs/<renderer>/slide-01.json`
- `render-jobs/<renderer>/manifest.json`

Subagent contract:

- Read exactly one slide job plus the referenced shared context.
- Treat the job file as page-local source of truth for index, title, page role, material, plan, target path, and renderer.
- Treat the shared `deck_strategy` and `design_system` as immutable deck-level source of truth. Use their palette tokens, typography, illustration policy, component language, tone, density, naming, and visual rhythm on every page.
- Do not reinterpret the audience or choose a fresh color scheme from the page-local content. Page variation should come from layout and emphasis while the design system stays stable.
- Write exactly one renderer source file to the job's `target_path`.
- Do not mutate outline, contents, slide plans, or workflow approval state from a page subagent.
- If repair feedback arrives, reuse the same job file and apply only the requested page-local fix.

Main-agent contract:

- Own renderer choice, review preference, renderer job preparation, and final export.
- Aggregate quality across pages.
- Send only failed pages back to subagents for revision.
- Keep all generated renderer files inside the same run directory as the approved deck artifacts.

## Role And Content Budgets

Use these role budgets while planning and rendering.

`cover`

- Single focal point.
- One main title, one subtitle, and at most one supporting information block.
- Avoid multiple parallel content cards.
- Footer may be absent or visually quiet.

`toc`

- Clear grouping and rhythm.
- Prefer one main card plus 2-4 agenda items.
- Avoid complex three-column comparisons.
- If sparse, add only short supporting blocks, not large metrics cards.

`content`

- Default structure: two main regions plus one footer.
- Keep at most one core module and one supporting module.
- If using timeline, process, metrics, or scenarios, choose one supporting pattern rather than mixing several.
- Timeline max 4 nodes; process max 3 steps; metrics max 2 blocks; scenarios max 3 items.
- Footer max one conclusion plus 2-3 short tags.

`timeline`

- Max 4 timeline nodes.
- Each node: stage name, time, one sentence, and at most two short tags.
- Right-side support area max two cards or one metric plus one summary.
- Avoid dense five-plus-node timelines.

`summary`

- Prefer two columns or top-main/bottom-conclusion.
- Max two major columns.
- Right side may contain up to three steps.
- Footer must be a thin summary strip, not a competing content block.
- Avoid adding a second large conclusion paragraph.

`ending`

- Emphasize closure.
- Max two main blocks plus one light footer.
- Prefer one main conclusion area or a simple two-region structure.
- Avoid complex card matrices and dense detail.

## HTML Generation Contract

When generating HTML slides:

- Output one complete self-contained HTML document per slide.
- Fixed canvas: 1280x720, 16:9.
- Set `html, body` width/height to 1280x720, `overflow:hidden`, `margin:0`.
- Use one `.slide` container sized 1280x720.
- Use CSS Grid or Flexbox; main content regions must use `min-height:0`.
- Prefer card-based information design with consistent radii, padding, borders/shadows, and hierarchy.
- No external CDN or remote assets unless the user explicitly asks; use inline CSS.
- Fonts: `PingFang SC`, `Microsoft YaHei`, `Noto Sans SC`, sans-serif.
- Header/title zone should stay within roughly 110px; long titles should wrap to at most two lines.
- Main content should fit the remaining ~500-540px height.
- Footer/summary strip should usually stay within 84-96px.
- Do not hide text with `overflow:hidden` on content cards; all visible copy must be readable.
- If content does not fit, reduce modules, bullets, steps, labels, or wording before shrinking text.
- Keep labels and chips short, usually 4-8 Chinese characters or 1-3 English words.
- For technical audiences, prefer diagram clarity, stronger information scaffolding, and lower decorative weight.
- For management, enterprise, government, or ToB audiences, use credible professional themes with disciplined hierarchy; retain appropriate brand colors and purposeful visuals.
- For investor or executive audiences, increase polish and contrast while keeping the page sparse, premium, and decision-led; do not collapse the page into monochrome text unless the user explicitly asks for that style.
- For students or younger audiences, a darker or more energetic theme is acceptable, but still professional.
- Resolve all recurring colors from `design_system.palette`; do not choose colors independently per slide.
- Output only HTML, no Markdown fences or explanatory text in the generated slide file.

## SVG Generation Contract

When generating SVG slides:

- Output one complete 1280x720 SVG per slide.
- Preserve SVG editability; prefer text, rects, groups, simple shapes, and clean hierarchy.
- Align density, layout rhythm, and page role with the HTML contract.
- All text must stay within canvas and card safe boundaries.
- Before placing multi-line text, estimate line count and vertical extent; do not let `y + lines * dy` exceed the card bottom.
- Use `<tspan>` for line wrapping; do not place long sentences in single-line `<text>`.
- Keep adequate vertical spacing between title, subtitle, body, captions, and footer.
- If content is long, first increase card height, split hierarchy, or shorten copy; do not rely on tiny type.
- Tags, pills, and footer notes must be extra concise.
- Use professional color hierarchy for title, body, labels, numbers, and notes.
- Keep visual language aligned with the audience profile chosen during outline generation rather than re-deciding audience from scratch at render time.
- Resolve all recurring colors from `design_system.palette`; do not choose colors independently per slide.
- Output only SVG code, no Markdown fences or explanatory text in the generated slide file.

## IMG-to-SVG Model Conversion Contract

Use this only after the IMG renderer has produced and exported the completed IMG PPTX and the user has explicitly opted into the additional model usage by requesting `choose-img-svg --mode on` in chat.

For every version-2 `render-jobs/img-svg/slide-xx.json`:

- Pass that job's actual `source_image_path` and exact `compiled_prompt` together in the same vision-model turn. The source IMG is the sole and mandatory visual source of truth. Do not recreate the page from `slide-plans.json`, a textual summary, memory, or a previous image inspection.
- Treat the task as faithful visual tracing, not slide redesign, restyling, simplification, cleanup, or content rewriting. Visual resemblance and preservation of every visible element take priority over SVG simplicity.
- Faithfully reconstruct the visible page as one complete, final 1280x720 SVG with `viewBox="0 0 1280 720"`.
- Preserve exact wording, numbers, line breaks, hierarchy, sampled colors, relative geometry, spacing, shadows, strokes, diagrams, icons, decorations, and reading order as closely as the image allows.
- Rebuild text, cards, dividers, arrows, simple diagrams, and other stable geometry using SVG text, paths, groups, rects, circles, lines, polygons, gradients, and clip paths.
- Preserve logos, icons, badges, small illustrations, and other incompatible or fidelity-sensitive regions by cropping them directly from the source IMG with Pillow and embedding them as Base64 PNG `<image>` elements.
- Do not replace an original icon with a generic plus, checkmark, circle, arrow, user silhouette, database mark, Lucide symbol, or approximate library icon. Trace it faithfully or use a source crop.
- Do not place the complete source slide inside one full-page `<image>` element. The final exporter must not rasterize the whole reconstructed page.
- Do not create layered SVG variants such as `v1`, `v2`, `overlay`, `image-elements`, or `clean`. Each IMG page maps directly to one final `img-svg/*.svg`.
- Do not use external image URLs, linked files, `<foreignObject>`, scripts, animation, or external stylesheets/fonts.
- Prefer PowerPoint-compatible SVG primitives and attributes. Avoid filters or experimental SVG features when a simpler vector construction can reproduce the same visual result.
- Keep text as `<text>`/`<tspan>` whenever legibility and fidelity permit, so PowerPoint can retain useful vector/text structure after import.
- Write the SVG structure to the job's exact `target_path`. For every source crop, place an `<image data-crop-id="...">` element at its final target geometry and write the matching crop manifest to `crop_manifest_path`.
- Run `scripts/embed_img_crops.py --manifest <crop_manifest_path>` to replace crop placeholders with `data:image/png;base64,...` directly in the final SVG. The helper must not create temporary PNG files.
- Complete `conversion_evidence_path` with the source-image hash, compiled-prompt hash, model/agent identifier, timestamp, and exact `input_mode: image_and_prompt_same_model_turn` confirmation.
- Complete `crop_manifest_path` for every page, including pages with no crops. An empty crop list requires a concrete reason and `faithful_vector_trace` or `no_icons_visible` as the icon strategy.

Crop manifest shape:

```json
{
  "source_image_path": "output/.../img/slide-01.png",
  "svg_path": "output/.../img-svg/slide-01.svg",
  "canvas": {"width": 1280, "height": 720},
  "crops": [
    {
      "id": "apple-logo",
      "source_box": [552, 535, 64, 68],
      "preserve_aspect_ratio": "none"
    }
  ]
}
```

`source_box` uses `[x, y, width, height]` in the normalized 1280x720 slide coordinate system. The Pillow helper maps those coordinates to the actual source IMG dimensions before cropping. Use `preserveAspectRatio="none"` for exact source-region patches and `xMidYMid meet` only for an isolated icon that should preserve its own aspect ratio.

Use this model prompt shape:

```text
Task type: faithful visual tracing of an existing presentation slide.
This is NOT a slide redesign, restyling, simplification, or content-rewriting task.

Use the attached slide image as the sole and mandatory visual source of truth. Inspect the attached image directly in this same model turn while producing the SVG. Do not reconstruct the slide from a textual summary, slide plan, design system, previous memory, or a description of the image.

Priority order:
1. Pixel-level visual resemblance to the attached image at 1280x720.
2. Preservation of every visible element, including icons and decorations.
3. Exact wording, reading order, relative position, scale, alignment, spacing, and line breaks.
4. PowerPoint-compatible SVG rendering.
5. Editability of text and simple geometry.
6. SVG simplicity.

Canvas: width 1280, height 720, viewBox="0 0 1280 720".

Preserve all visible text verbatim. Preserve the original title position, font scale, line breaks, card geometry, border radius, spacing, margins, arrows, dividers, footer, shadows, strokes, fills, badges, icon backgrounds, and decorative marks. Sample colors from the attached image. Do not normalize spacing, improve the composition, introduce a new visual style, or remove decorative elements.

Every visible icon, logo, badge, illustration, and decorative symbol must remain. Never replace an original icon with a generic plus, checkmark, circle, arrow, user silhouette, database symbol, or approximate icon. Trace an icon as SVG paths only when the result is visually close. Otherwise preserve it with an exact source-image crop and a matching <image data-crop-id="..."> element.

Keep text as <text>/<tspan> when visually faithful. Rebuild cards, backgrounds, lines, dividers, arrows, and simple geometry as vectors. Complex regions may remain as small embedded Base64 PNG crops. Do not use one full-page raster image or raster patches that dominate the page.

No external URLs/files, <foreignObject>, script, animation, external stylesheet, or external font. Do not simplify visible styling merely to make the SVG shorter.

Before returning, compare the SVG against the attached image from left to right and top to bottom. Confirm every icon and decorative element is present and no card, title, label, arrow, footer, or line break has been redesigned.

Output exactly one final 1280x720 SVG and one crop manifest. Do not output alternative SVG versions or explanatory prose.
```

Before marking conversion complete:

- Run `complete-img-svg` once to render every final SVG with Playwright and create the per-slide rendered PNG, automatic pixel/edge similarity metrics, and pending fidelity-review JSON.
- Inspect each source IMG and rendered SVG PNG together in the same active turn. Review the entire page left-to-right and top-to-bottom, including icon presence, decoration, palette, typography, line breaks, geometry, spacing, and shadows.
- Revise pages with visible drift. Mark `status: pass` only after confirming `source_image_inspected`, `rendered_svg_inspected`, `layout_preserved`, `icons_preserved`, and `no_redesign`.
- A combined similarity below the recommended threshold requires revision or a concrete, page-specific override reason. A generic statement is not acceptable when visible redesign remains.
- Confirm all embedded images are valid Base64 PNG/JPEG data URIs.
- Confirm there are no external hrefs, `<foreignObject>`, or scripts.
- Confirm no `<image>` covers the full 1280x720 slide and embedded raster regions do not dominate the page.
- Confirm the exact one-to-one page set and `viewBox="0 0 1280 720"`.
- Confirm every page has completed same-turn conversion evidence and a crop manifest, including an explicit no-crop reason when applicable.
- Rerun `complete-img-svg`; it must not mark the conversion complete while any evidence, manifest, or fidelity review remains incomplete.
- Export native `.svg` media in the PPTX rather than rasterizing the generated SVG pages.
- When Microsoft PowerPoint is installed, open the final PPTX and export every page to PNG for the final Office rendering check.

## Technical Layout Checks

For HTML, inspect rendered screenshots and layout reports for:

- Overlap.
- Text clipping.
- Main content pushing into footer.
- Footer competing with main content.
- Too many cards or modules.
- Timeline, summary, dense-card, cover-header, cover-chain, conclusion, and step-card risk patterns.

For SVG, check:

- Horizontal overflow outside card or canvas.
- Vertical overflow outside card.
- Text overlap.
- Unsafe text/card boundaries.
- Long single-line labels.

If a generated slide fails checks, revise the slide source locally when defects are small. For structural issues, regenerate or rewrite the slide using the repair contract below.

## Screenshot Review Contract

Use this contract only when the user explicitly enables the render review subflow for `html` or `svg`.

Review rendered screenshots as a final PPT page, not as code.

Judge:

- Information density.
- Visual hierarchy.
- Clear focal point.
- Module count.
- Reading order.
- Footer interference.
- Whether content is rich but still stable and readable.

Return review decisions conceptually as:

```text
RESULT: PASS or RESULT: REVISE
REASONS:
- ...
SUGGESTIONS:
- ...
```

When suggesting fixes:

- Give at most four conservative, executable suggestions.
- Prefer local geometry and content-budget fixes.
- For HTML, suggestions may reduce modules, nodes, metrics, scenarios, or explanatory text.
- For SVG, first try local geometry: move text, increase card height, widen spacing, reduce local font size or line height.
- Avoid adding new complex structures during repair.
- Do not make the page empty merely to pass validation.

## Repair Contract

When a slide has layout problems, feed the issue summary back into the next Codex rewrite:

- Preserve the topic, message, page role, and visual style.
- Fix the named issue directly.
- Prefer reducing module count over only shrinking fonts.
- Convert crowded three-column layouts into two-column or top-main/bottom-support layouts.
- For timelines, reduce to at most four nodes and compress right-side support.
- For mixed support structures, keep only one type: process, timeline, metrics, scenarios, or summary.
- Shorten repeated explanation and secondary tags.
- Keep footer safe and visually separated from the main content.

## Migrated Core Design Intent

The old migrated HTML core added reusable design intelligence. Preserve its intent in Codex-generated slides:

- Choose a consistent deck-level visual system, not a new style on every page.
- Maintain stable typography, color tokens, card style, spacing, and footer behavior across slides.
- Extract "design genes" from any provided reference image, template, or prior accepted slide plan.
- Use slide context: cover introduces tone, TOC establishes structure, middle slides develop evidence, summary/ending pages close the argument.
- Decide whether images are needed; if they are, specify image purpose in the slide plan before generating renderer files.
- Keep generated visuals inspectable and presentation-ready rather than decorative filler.
