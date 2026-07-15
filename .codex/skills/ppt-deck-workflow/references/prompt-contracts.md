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
- Style direction: calm, credible, boardroom-safe, concise, clear hierarchy, restrained visuals.

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
- Style direction: highly distilled, authoritative, decisive, uncluttered.

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
- Use the shared context only to maintain cross-page consistency in tone, density, naming, and visual rhythm.
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
- For management, enterprise, government, or ToB audiences, use restrained light or sober professional themes.
- For investor or executive audiences, increase polish and contrast while keeping the page sparse, premium, and decision-led.
- For students or younger audiences, a darker or more energetic theme is acceptable, but still professional.
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
- Output only SVG code, no Markdown fences or explanatory text in the generated slide file.

## IMG-to-SVG Model Conversion Contract

Use this only after the IMG renderer has produced and exported the complete IMG PPT, the workflow has stopped, and the user has explicitly chosen `choose-img-svg --mode on` in chat.

For every `render-jobs/img-svg/slide-xx.json`:

- Pass that job's `source_image_path` directly to a vision-capable model. The source IMG is the primary and mandatory visual source of truth; do not recreate the page from `slide-plans.json` alone.
- Ask the model to faithfully reconstruct the visible page as one complete, native 1280x720 SVG with `viewBox="0 0 1280 720"`.
- Preserve the page's visible wording, numbers, hierarchy, colors, relative geometry, diagrams, icons, and reading order as closely as the image allows.
- Produce real vector content using SVG text, paths, groups, rects, circles, lines, polygons, gradients, and clip paths.
- Do not place the original IMG inside an `<image>` element. Do not use base64/data-URI images, external image URLs, linked files, `<foreignObject>`, scripts, animation, or external stylesheets/fonts.
- Prefer PowerPoint-compatible SVG primitives and attributes. Avoid filters or experimental SVG features when a simpler vector construction can reproduce the same visual result.
- Keep text as `<text>`/`<tspan>` whenever legibility and fidelity permit, so PowerPoint can retain useful vector/text structure after import.
- Write only the SVG document to the job's exact `target_path`; do not write Markdown fences or explanatory prose into the file.

Use this model prompt shape:

```text
Reconstruct the attached presentation-slide image as one native, PowerPoint-compatible SVG.

Canvas: 1280x720, viewBox="0 0 1280 720".
Faithfulness: preserve all visible text, numbers, hierarchy, colors, relative geometry, diagrams, icons, and reading order from the attached image.
Vector requirement: use SVG text, paths, groups, rects, circles, lines, polygons, gradients, and clip paths. Do not embed or reference the attached raster image.
Compatibility: no <image>, data URI, external URL/file, <foreignObject>, script, animation, or external stylesheet/font. Prefer simple PowerPoint-compatible SVG primitives.
Output: the complete SVG document only, with no Markdown fence or explanation.
```

Before marking conversion complete, the helper validates the exact one-to-one page set, the 1280x720 viewBox, XML validity, and the absence of raster/external wrappers. The final exporter must embed native `.svg` media in the PPTX rather than rasterizing the generated SVG pages.

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
