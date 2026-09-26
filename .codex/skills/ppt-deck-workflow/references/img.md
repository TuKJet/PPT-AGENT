# IMG Branch

Read only after the user chooses IMG. Use the imagegen tool to generate finished full-page images.

## IMG Prompt Compilation

For the `img` branch, do not pass raw `slide-plans.json` text directly to imagegen. Treat each slide plan as source material and compile it into a clean image-generation prompt. After all images are generated, package them into the original IMG PPTX; that export completes the requested IMG workflow while leaving IMG-to-SVG available as a later explicit opt-in.

Compile only the approved final state. After a revision, never pass the user's edit request, rejected wording, or revision history to imagegen. A removed element must disappear from the prompt entirely; do not preserve it through instructions such as `remove X`, `do not show X`, or `without X`. Describe the resulting composition positively instead. If a marked-up screenshot contains crossed-out or rejected content, use it to understand the revision, but prefer the clean final-state plan or an unmarked reference for full-page regeneration.

Before calling imagegen, separate slide-plan text into:

- Visible slide copy: titles, headings, labels, table text, numbers, formulas, and sentences that should appear on the final slide.
- Layout-only notes: placeholders, occupancy markers, future paste areas, scaffold labels, and implementation notes that describe where content goes but should not be drawn.

Keep and translate layout intent from the slide plan:

- Main visual placement: left, right, center, full-bleed, split composition, or staged depth.
- Title zone placement and hierarchy.
- Approximate module count and spatial grouping.
- Intended chart, architecture, process, matrix, or ecosystem structure.
- Reserved blank areas requested by the user.
- User-provided screenshot/reference-image layout direction.
- Visual focus, reading order, density, whitespace, and management-facing tone.

Remove or rewrite implementation-specific layout details:

- Do not pass HTML/CSS terms such as grid, flex, px, rem, class names, DOM nodes, or component implementation notes.
- Do not pass SVG path/group details or renderer-specific instructions.
- Keep user-approved Chinese copy, key numbers, labels, tables, and formulas when they are part of the slide message, but rewrite their presentation as clear visual typography and organized content blocks rather than renderer implementation notes.
- Do not pass placeholder or occupancy text as visible copy. Strip or rewrite markers such as `占位`, `待补充`, `待插入`, `TBD`, `TODO`, `XXX`, `Lorem ipsum`, `[文本]`, `[图片]`, `{placeholder}`, `<placeholder>`, repeated punctuation, fake sample labels, or notes that only mean "reserve this area".
- When a placeholder represents reserved space, translate it into a visual instruction such as "leave a clean empty area for later image placement" or "show an unlabeled content panel", and explicitly say that no placeholder words or symbols should appear.
- Do not ask imagegen to create editable text boxes, layers, or separately movable page objects.

For a revised slide, perform one additional semantic-cleaning pass before writing the imagegen prompt:

- Compile from the final-state fields, not from the user's revision message or a diff against the prior slide.
- Include only visible copy from the cleaned `required_elements` allowlist.
- Drop rejected literals completely. Do not convert revision history into negative prompt clauses such as `remove X`, `do not render X`, or `X must not appear`.
- Replace a removal with the positive visual state that occupies the region: clean background, whitespace, a direct connector, a resized surviving module, or another approved final element.
- Do not pass marked-up screenshots with crossed-out content as a full-page image reference when the final-state plan can drive regeneration. Use an unmarked reference when available; otherwise use the annotation only to infer layout before compiling the prompt.
- Run a literal residue check against rejected strings before calling imagegen. If a rejected string still appears anywhere in the compiled prompt, rewrite the prompt before generation.

The compiled prompt must ask for one finished 16:9 presentation page image. It should include:

- Slide title and page role.
- One concise core message.
- Semantic composition instructions derived from the slide plan.
- Visual style, color, texture, depth, and mood.
- Exact visible Chinese copy, key numbers, labels, tables, or formulas required by the slide plan.
- Text rendering constraints that ask for accurate, legible Chinese typography and polished PPT-style information design.
- A negative instruction that placeholder words, scaffold markers, and occupancy characters must not appear in the image.

Use this prompt shape:

```text
Create one complete 16:9 presentation slide image.

Slide title: ...
Page role: ...
Core message: ...

Composition:
- ...

Visual style:
- ...

Text constraints:
- Preserve the required Chinese text and numbers exactly as provided.
- Render Chinese text as crisp, legible presentation typography with clear hierarchy.
- Use polished PPT-style content blocks, callouts, tables, or diagrams when needed.
- Do not render placeholder words, scaffold labels, occupancy markers, bracketed placeholders, or fake sample text.
```


Export using `workflow.py export --run-dir output/<project>`. Read `slide-status-img.json` and deliver the original PPTX; this completes the IMG workflow.

Optional IMG-to-SVG Post-Export Opt-In: ask once whether the user wants an optional derivative, state additional model/Token usage and that PowerPoint can convert vector parts using its SVG tools. Do not present a decline option. Read [img-svg.md](img-svg.md) and [img-svg-prompt.md](img-svg-prompt.md) only after explicit opt-in. This remains a post-export derivative, not a renderer choice.
