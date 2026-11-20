## Slide Plan Contract

Create `slide-plans.json` version 2 with one deck-level `deck_strategy`, one deck-level `design_system`, and the page-local `slides`. For direct planning, derive the shared design system from the brief, supplied references and page content. On the sample route use the user's chosen treatment, palette or blend. Describe the chosen composition, palette and visual treatment concretely enough to apply them to a new page. Version 1 and a free-form string in `plan` are invalid even if the prose happens to mention color or layout.

`deck_strategy` must record the stable audience interpretation used across the deck:

- primary audience and any secondary audience constraint
- the decision or response the deck should enable
- the first questions this audience is likely to ask
- evidence order and detail-depth principles
- presentation posture and desired confidence level
- `page_rhythm`, a short list of numbered pages or ranges and what each contributes. Mark where the audience should pause on a key claim, where it needs dense evidence, and where a light transition helps it change questions. Use the mix the story needs. For example, a three-page technical review can use the opening choice, a dense comparison, and a closing decision without a standalone transition.

Use the outline's audience and occasion to carry the argument across pages. In each page's `layout_structure`, begin with the relationship the reader needs to see, then choose a form that makes it legible. Cause and effect may use linked steps, time can use a timeline, hierarchy a tree, alternatives a common comparison axis or matrix, and feedback a return arrow to the step that changes. A single result may only need a number or an image. The page rhythm determines where to enlarge that result or give its evidence more space.

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
- Layout structure derived from the page's relationships.
- Exact visible copy, objects and numbers. In a live meeting reserve explanation for the speaker and supporting detail for reference. For a reading deck include the context needed to interpret the evidence. State each takeaway once.
- Visual hierarchy.
- Element types such as title, subtitle, card, metric, timeline, process, matrix, callout, chart, footer.
- Style controls from the user: color, density, typography, visual motif, chart treatment, reference-image influence.
- Audience-driven presentation controls: technical depth, business framing, persuasion intensity, decision orientation, and page-level density.
- Renderer-neutral constraints; do not include renderer-specific class names, CSS, SVG path instructions, or implementation-only notes.

`slide-plans.json` must remain the control surface for art direction. If style guidance changes, edit the plan before rendering.

Reference-image calibration includes palette roles and approximate area balance, contrast, typography, block geometry and whitespace. A hex color alone does not capture a visual system. Record these in the existing `design_system` fields. Keep them stable across pages until the user changes them; do not imitate reference branding or add logos unless requested.

Keep source coverage and reasoning with the canonical page: optional `source_refs` identify file/section/figure, and optional `plan.diagram_spec` records nodes, directed edges, branch/merge points and edge labels for logic-heavy pages. Required relationships remain content even when geometry changes. `required_elements` contains actual visible copy/objects, not just “title, diagram, footer”. Separate speaker notes from the exact text allowed on the slide.

Before a rewrite, check approved page roles and source coverage. Changing density must not erase cover/contents, design mechanisms or evidence. For local feedback, update only affected pages and shared settings actually implicated. Present the helper-generated `.workflow/slide-plans-preview.md`, not a second versioned planning Markdown.

Use these exact canonical keys. Do not rename them, place them only inside prose, or substitute model-specific aliases:

```json
{
  "version": 2,
  "deck_strategy": {
    "primary_audience": "...",
    "decision_context": "...",
    "first_questions": ["..."],
    "evidence_order": ["..."],
    "presentation_posture": "...",
    "page_rhythm": ["P1 · Opening question and scope"]
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

For every source-backed line chart, bar chart or table, put its exact data in the corresponding `plan.data_regions` entry. Use the approved values, units and order. Bounds are fractions of the page in `[left, top, width, height]` order. For charts the first column lists categories and each remaining column is a numeric series. For tables all columns are displayed, including their headers. Use `null` for a missing measurement. Example:

```json
{"data_regions": [{
  "id": "cost-per-case", "kind": "bar", "bounds": [0.1, 0.3, 0.8, 0.55],
  "data": {"cols": ["方案", "每件成本（元）"], "rows": [["A", 130], ["B", 110]]}
}]}
```

Choose `line`, `bar` or `table` to express the comparison. By default the IMG export draws the data. To defer a specific panel to the editable PPTD, set its optional `"img": "reserve"`. The approval preview shows the values; both renderers use the same entries. If the source lacks the figures, keep the claim qualitative or get the source table from the user.

Before asking for slide-plan approval, run the helper preview. A validation error means the artifact is incomplete and must be repaired; never bypass the failure by manually converting only the fields that happened to be generated.

The helper must translate this strict machine schema into a smaller human-readable approval projection. `slide-plans-preview.md` should show the audience/decision lens, visual system, core message, layout, hierarchy, visible elements, and page style using natural labels, a compact palette table, numbered sequences, and bullets. Keep renderer-internal audience controls and neutral constraints in the validated JSON instead of copying them into the approval body. Never copy JSON objects, quoted field names, braces, or fenced `json` blocks into the preview.

The audience decision made in the outline stage must carry forward into `slide-plans.json`; do not silently switch the deck into a different audience style later.

Express audience fit through composition, emphasis, evidence density, ordering, and tone. Do not turn the slide plan into visible rhetoric about what the audience cares about unless the user explicitly requests that framing.

Apply feedback to the intended element: put its final position, direction and appearance in layout or style, and only audience-facing wording in visible copy. For scoped changes follow [revision.md](revision.md).
