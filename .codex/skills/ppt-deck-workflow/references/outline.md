## Outline Contract

Generate a complete renderer-neutral PPT outline.

- Match the requested topic, audience, and page count.
- Use stable slide roles: `cover`, `toc`, `content`, `timeline`, `summary`, `ending`.
- Read the assignment and named sources. Identify what the audience needs to understand or decide in this particular meeting, and what they already know.
- Identify the relationship behind that question, such as a cause, timeline, hierarchy, comparison or feedback loop. Order the sections and page titles to reveal it. Each substantive page supplies a premise, a piece of evidence, or an implication that the next page needs. For example, a design review might progress from operating constraint to competing mechanisms, then evidence and the remaining choice. Use the sequence that fits the assignment.
- Keep the subject's actual mechanisms, results and evidence limits. Give each page a specific title that can key `contents.json`. Include page-local `source_refs` when working from source material.
- On revision preserve approved page roles, including cover and contents where present.
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

The outline must already reflect audience level and use. In a live briefing, put the claim and its decisive evidence on screen and leave derivations for the speaker. A deck circulated for reading may need the baseline, units and assumptions beside the result.

The same subject can call for different orders. A **technical** design review may start with the constraint that drove a design choice. A **management** or executive investment meeting may open with the choice and show which evidence changes it. An **investor** discussion may start with a customer outcome and how often it has been reproduced. Choose from the actual brief and carry that thread through the deck.

For leadership presentations, restraint applies to information noise. Do not infer a monochrome palette from the audience label. Purposeful brand colors, illustrations and diagrams are available when they serve the subject.
