# Compare visual directions

Use this stage after `choose-plan-mode --mode samples`. Pick two pages whose different jobs reveal how a style handles this deck, for example a mechanism and a decision or a comparison and its interpretation. A one-page deck uses its actual page. Keep their message, data and relationships consistent across the four directions.

First write a short slide plan for each sample. Identify its focal point, how the reader sees the relationship, the on-screen words and the role of the colors. Render each plan as an individual 16:9 IMG using the imagegen skill's built-in `image_gen` tool by default. For quantitative pages reserve the data rectangle on the artwork and supply the approved rows via optional page-level `data_regions`, using the same shape as the full plan. The comparison helper composites those exact values. A panel awaiting source data may stay empty.

Order the four directions by increasing AIGC presence. A is a formal briefing on white, with a deep navy title accent, quiet dividers, clean typography and legible diagram lines. Derive B, C and D independently from the subject and the user's brief. Give them distinct palettes and compositions, and name the chosen background and accent in each image prompt. A bright orange accent on white can draw attention to a key result. Reserve dark forest or muted olive green as a dominant color for an explicit user preference or brand palette. Illustration or dimensional imagery can depict the actual product, process or setting when it clarifies the point. Show how each direction handles both page purposes using the same palette, typography and illustration technique.

Save the sample plans and their IMG paths under `.workflow/style-samples/`. Use an entry like the one below for **each** direction in the manifest's `styles` list. For data regions, pass optional `palette_tokens` such as `primary`, `accent` and `surface`.

```json
{
  "id": "A", "palette": "white and navy", "treatment": "formal briefing",
  "pages": [
    {"page": 2, "plan": "Two alternatives share one comparison axis; mark the allowable limit.", "path": ".workflow/style-samples/A-02.png"},
    {"page": 4, "plan": "One decision above a short row of supporting evidence.", "path": ".workflow/style-samples/A-04.png"}
  ]
}
```

1. Run `record-style-samples --run-dir <run> --file <manifest.json>`. Display **each** returned `show_image` inline so the user sees all four treatments of each page. The original images are available for a closer look.
2. Stop in ordinary chat and invite a description or annotated screenshot. For example, “哪种构图和配色最适合这次汇报？可以直接圈图，也可以混搭。” Wait for the reply. If the user requests another variation, show the revised sample and continue the discussion.
3. Once the user settles on a direction, record it with `choose-style --run-dir <run> --preference "<their direction>"`. Reopen the selected full-size sample images or user screenshots. For a blend, match each chosen feature to its source. Carry over recognizable typography and artwork across relevant pages. Carry over a sample's composition where the user or the page's purpose calls for it. Specific choices for headings or artwork take precedence over a general base style. Where the wording leaves a consequential choice open, show the proposed treatment on one representative page in the existing plan preview, or ask one focused question. Carry the chosen originals and their roles into the full plan as described in [slide-plans.md](slide-plans.md). The main renderer choice follows full plan approval.
