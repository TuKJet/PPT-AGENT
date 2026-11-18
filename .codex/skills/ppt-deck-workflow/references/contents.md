## Content Contract

Audience inference should control what evidence appears first, how much detail is shown, and how the conclusion is phrased, but that inference should usually remain invisible in the slide copy itself.

For each slide, produce page-ready PPT material rather than research notes.

Research may come from Codex-native research capability, not repository AI provider code:

- Prefer a Codex-installed local research skill when one is available in the current session, and use it first to structure or gather evidence for `contents`.
- Otherwise use Codex web search/browsing directly when freshness or external evidence is needed.
- Do not route research through `pipeline.py`, `html_pipeline/pipeline.py`, `AIClient`, or repository model tools.

- Keep only information directly relevant to the slide title.
- Prefer conclusions, capability judgments, concrete facts, dates, metrics, and case outcomes.
- Put genuinely parallel facts in a list. Express causes, tradeoffs and qualifications as connected statements. If a heading such as “边际收益显著” merely paraphrases the adjacent evidence, keep the comparison that earns it. Preserve architecture/process/comparison relationships and the assumptions behind estimates. Carry useful detail into the slide plan so the author can assign it to the screen, the speaker or reference material. There is no universal character quota.
- For a design claim, retain the chain from problem to design choice to mechanism to supported benefit. Map claims and metrics to named source sections in the canonical plan's `source_refs`; distinguish measured results from design expectations.
- Translate source diagrams into explicit relationships: direction, branching, merge points, feedback and edge labels. Do not reduce a diagram to a list of nouns. Keep detail that explains the design; move implementation syntax into notes.
- Do not output URLs, footnote numbers, source lists, or long citations inside slide copy.
- Avoid vague phrasing such as "据报道", "可能", "有观点认为", unless the slide explicitly needs uncertainty.
- If evidence is weak, write conservative capability or logic statements instead of inventing numbers.
- Put research/source notes outside visible slide copy when needed.

