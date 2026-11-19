## Slide Plan Contract

Create `slide-plans.json` version 3 with one deck-level `deck_strategy`, one deck-level `design_system`, and the page-local `slides`. Existing version-2 plans remain readable. When upgrading a plan, assign the actual material to the layers on every page before changing its version. Version 1 and a free-form string in `plan` are invalid.

`deck_strategy` must record the stable audience interpretation used across the deck:

- primary audience and any secondary audience constraint
- `use_context` as `live`, `standalone` or `hybrid`
- what the audience should understand, decide or do (use the existing `decision_context` field)
- the first questions this audience is likely to ask
- evidence order and detail-depth principles
- presentation posture and desired confidence level

Combine the setting with the audience's task. A live investment meeting needs the proposal, the meaningful difference between alternatives and the decision. A financial pre-read on the same subject needs assumptions, units and enough of the calculation to reproduce the estimate. A hybrid page carries a conclusion and sufficient evidence to stand on its own; the presenter can expand the reasoning. Keep the user's page count, required evidence and readability as constraints.

Assign material to three lists in each `plan.copy_layers`:

- Write only the words the audience should read in `on_screen` and apply design or revision directions to the page elements they describe. List the copy in reading order. Include a displayed title once. Use `plan.show_title: false` for an internal page name. A visual-only page may have an empty list. Native tables and charts take their data from `data_visuals`.
- `talk_track` holds the explanation a presenter would add, for example why a comparison matters or when to revisit the decision.
- `reference` holds detailed derivations, assumptions, lookup values or source pointers for follow-up. Leave either off-screen list empty when it serves no purpose. Details essential to a standalone reader belong on screen. The PPTX carries populated speaking and reference sections in the slide's speaker notes; the page drawing job receives neither.

Before previewing, read each page as the intended audience. If a title, KPI card and footer all draw the same conclusion, keep the best placement. Preserve repeated labels, units and baselines when readers need them to decode data. Replace generic praise with the source-backed observation or cut it. Across neighboring pages, check that repetitions build the argument. Set density through relationships and evidence; use the actual rendered size to check readability.

`design_system` must define:

- theme name and audience-fit rationale
- `palette` tokens at minimum for `background`, `surface`, `primary`, `accent`, `text_primary`, and `text_muted`, plus semantic data/status colors when needed
- typography hierarchy
- card, line, radius, spacing, and footer behavior
- chart and diagram treatment
- imagery and illustration policy
- any brand or reference-image design genes

For a page that uses data to support its claim, consult [visualization-choice.md](visualization-choice.md). Record each data-bearing visual, the comparison it enables, and the chosen encoding in `plan.data_visuals`. Both renderers receive this field. If the editable deliverable must expose a chart's backing data or table cells, record the expected series or cell matrix here while the source is in context. Existing plans and pages without data visuals may omit the field.

Choose the palette once for the whole deck. Page plans must reference the shared palette tokens and must not invent a new page palette, swap the primary/accent relationship, or introduce unrelated hex colors. Allow a page-specific color only for semantic encoding, a user-supplied asset, or an explicitly justified narrative moment; record that exception in the page plan and keep the rest of the system unchanged.

Do not express "restrained" as a ban on visual assets. The `design_system` should say what visual devices are useful for this audience and topic, not merely prohibit illustrations, brand colors, decorative motifs, photography, or depth.

For each slide plan, specify:

- Core message.
- Page role.
- Layout structure. Build the main visual from the people, objects and relationships in the approved content. For an abstract capability, its actual inputs, choices and outputs can be the illustration. Specify what the viewer sees, how composition carries the meaning and which labels make it readable. Introducing a different application or a worked example changes the content. A short overview can pair a formal heading with a sentence that adds the takeaway.
- Required visible copy and numbers.
- Visual hierarchy.
- Element types such as title, subtitle, card, metric, timeline, process, matrix, callout, chart, footer.
- Style controls from the user: color, density, typography, visual motif, chart treatment, reference-image influence.
- Audience controls: depth, register and density for the purpose and setting.
- Renderer-neutral constraints; do not include renderer-specific class names, CSS, SVG path instructions, or implementation-only notes.

`slide-plans.json` must remain the control surface for art direction. If style guidance changes, edit the plan before rendering.

Read a reference in light of what the user liked. Carry its way of explaining relationships into the page layout when that is the request. When adapting the look, set palette roles, area balance, type and spacing in the shared `design_system`; vary composition by page while keeping those choices consistent.

Keep source coverage and reasoning with the canonical page: optional `source_refs` identify file/section/figure, and optional `plan.diagram_spec` records nodes, directed edges, branch/merge points and edge labels. Use `required_elements` to specify concrete objects and their function, such as a current-versus-proposed cost comparison or a relationship diagram. Keep `material`, `talk_track` and `reference` in the canonical plan for review.

Before a rewrite, check approved page roles and source coverage. Changing density must not erase cover/contents, design mechanisms or evidence. For local feedback, update only affected pages and shared settings actually implicated. Present the helper-generated `.workflow/slide-plans-preview.md`, not a second versioned planning Markdown.

Use these exact canonical keys. Do not rename them, place them only inside prose, or substitute model-specific aliases:

```json
{
  "version": 3,
  "deck_strategy": {
    "primary_audience": "...",
    "use_context": "live",
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
      "title": "Pilot the staffing change in two stores",
      "material": "...",
      "page_role": "cover",
      "plan": {
        "core_message": "...",
        "copy_layers": {
          "on_screen": ["Pilot the staffing change in two stores", "Review overtime after six weeks"],
          "talk_track": ["Explain how the two stores were selected."],
          "reference": ["Staffing model assumptions in the operations workbook."]
        },
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

The helper translates this schema into a smaller human-readable approval projection. Review the audience and setting, then read each page's screen copy on its own before checking the speaking and reference material. These layers should be visibly distinct in the preview. Keep renderer-internal audience controls and neutral constraints in the validated JSON. Never copy JSON objects or fenced code into the preview.

The audience decision made in the outline stage must carry forward into `slide-plans.json`; do not silently switch the deck into a different audience style later.

Express audience fit through composition, emphasis, evidence density, ordering, and tone. Do not turn the slide plan into visible rhetoric about what the audience cares about unless the user explicitly requests that framing.

For changes to an existing page, follow [revision.md](revision.md).

