# Prompt Contracts — staged index

Read only the contract for the current approved stage, not this whole directory.

- Outline: [outline.md](outline.md).
- Contents, after outline approval: [contents.md](contents.md).
- Planning mode, after contents approval: ask whether to draft directly or compare visual samples. Record `choose-plan-mode --mode direct|samples`; default to `samples` when the user delegates or expresses no preference.
- Style samples, only in samples mode: [style-samples.md](style-samples.md).
- Full slide plans, after direct planning or after the user describes a sample preference: [slide-plans.md](slide-plans.md) and [role-budgets.md](role-budgets.md).
- Revisions: [revision.md](revision.md).
- IMG, only after selection: [img.md](img.md).
- PPTD, only after selection: [pptd.md](pptd.md); that guide routes to the format specification as needed.
- Optional IMG-to-SVG, only after exported IMG and explicit opt-in: [img-svg.md](img-svg.md), then [img-svg-prompt.md](img-svg-prompt.md).

## Render Job Contract

`prepare-render-jobs` writes one page job per slide and a shared context. Use the page job and the shared design system to write the selected renderer's source. Do not read unrelated page jobs or renderer contracts. Use the same run directory throughout. HTML and standalone SVG renderers are removed.
