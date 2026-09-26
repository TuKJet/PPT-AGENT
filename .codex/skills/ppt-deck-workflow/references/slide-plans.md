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

### Final-State Revision Contract

Apply this contract whenever an existing outline, content artifact, or slide plan receives a second or later user change.

Treat the user's change request as a transient delta. The persisted artifact must describe only the desired final slide, not how it differs from an earlier version.

- Rewrite affected fields instead of appending correction notes.
- Keep accepted content and the new final geometry; discard superseded alternatives and rejected wording.
- Make `required_elements` an allowlist of exact final visible copy and objects. A deleted object or string must not remain in this list.
- Do not store revision verbs or tombstones such as `delete`, `remove`, `omit`, `do not show`, `must not appear`, `不要出现`, `删除`, `去掉`, or `不保留` when they refer to content from the previous version.
- Do not quote the rejected literal inside a negative instruction. Mentioning a removed label again still gives it prompt attention and can cause it to reappear.
- Express the destination positively and spatially. Bad: `delete the old card and do not show its label`. Good: `keep this interval as clean background space; join the remaining modules with one short connector`.
- Keep generic safety and truthfulness constraints only when they remain useful without knowledge of the revision history, for example no invented metrics, no external brand logo, and exact required numbers.
- If the user supplies an annotated screenshot, extract the accepted layout and final-state geometry into the plan. Do not transcribe cross marks, comments, rejected labels, or deletion instructions into the plan.

Before generating `slide-plans-preview.md` or render jobs, audit the changed slide object:

1. List the literals and objects the user rejected in working memory only.
2. Search `material`, `core_message`, `layout_structure`, `visual_hierarchy`, `required_elements`, `style_controls`, `audience_controls`, and `renderer_neutral_constraints` for those literals.
3. If a rejected literal survives only in a negated or historical sentence, remove that sentence and replace it with a positive final-state description.
4. Confirm the preview contains no edit history and reads as if this were the first and only design specification.
5. Prepare renderer jobs only from this clean artifact.

