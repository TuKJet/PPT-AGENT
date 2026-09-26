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

