---
name: ppt-deck-workflow
description: Use this local workflow when the user wants Codex to generate a PPT deck from inside this project, with shared outline/content/planning stages, Codex-in-chat approval checkpoints, and a later choice between HTML, SVG, or full-page image renderer branches.
---

# PPT Deck Workflow

Use this skill for PPT generation tasks in this project. The user should only need to ask for a PPT; do not expose internal renderer functions as separate skills.

## Core Rule

Run the deck as one Codex workflow:

1. Generate the common artifacts.
2. Stop at review checkpoints and ask the user to approve or request changes.
3. Let the user choose `html`, `svg`, or `img` only after outline, contents, and slide plans are ready.
4. Render through the chosen branch.

Do not use the Web UI for this workflow. The approval loop happens in the Codex conversation.

Do not use Codex-side web search, `web.run`, or browser/web-search tools to research the PPT topic for this project. Put all research instructions, freshness requirements, source constraints, and search questions into the runner `--research` argument and let the project pipeline/AI client perform its own search and synthesis.

For long runner commands, use unbuffered Python (`-u`) so progress lines stream back to Codex. When the runner prints `[progress]` lines, relay those to the user as the source of truth instead of probing files repeatedly.

For long decks, do not first run expensive phases in the foreground and wait for the tool timeout. If the requested deck has more than 10 pages, or the user describes a long/complex deck, run `contents` and `plans` as background runner jobs from the start and monitor them with the long-job cadence below.

## Approval Transparency

Never ask the user to approve an artifact blindly.

Whenever the workflow reaches a user approval checkpoint, hand the generated Markdown preview document to the user for direct review. Do not read the preview file and summarize it for the user. The point of the preview Markdown is to give the user the review surface, not to have the agent substitute its own summary.

Required behavior:

- Name the exact Markdown file that was generated.
- Provide a clickable path to the Markdown file when possible.
- Tell the user to review that file and reply with approval or requested changes.
- Do not summarize, paraphrase, excerpt, or pre-judge the Markdown contents unless the user explicitly asks for a summary.
- Do not proceed past an approval checkpoint until the user has approved after receiving the file link.
- Do not describe a checkpoint as approved, reviewed, or complete based only on the artifact existing on disk.

Render-stage review Markdown files such as `reviews/review-*.md` and `editable/review-*.md` are internal QA artifacts, not user approval checkpoints. Do not ask the user to review them one by one, and do not dump per-slide review summaries unless the user asks. At completion, use `slide-status.json` for a concise aggregate status and call out only exceptions: failed checks, warning counts, residual layout issues, fallback behavior, or export caveats.

## Style Control

If the user provides reference images, screenshots, brand examples, or a written style direction, encode that direction during the slide-plan stage. The plan artifact is the control surface for colors, typography, density, layout rhythm, visual motifs, chart treatment, and page-level art direction.

Required behavior:

- Put style requirements into `slide-plans.json` before asking for slide-plan approval.
- If the style guidance arrives after `slide-plans.json` exists, edit `slide-plans.json` directly and regenerate downstream render outputs only after the updated plan is approved.
- If the user gives style guidance at or before the slide-plan stage, render HTML with `HTML_USE_MIGRATED_CORE=false` so generation uses the legacy HTML prompt path instead of the migrated core template path.
- Do not wait until HTML/SVG files are generated and then write a rebuild, migration, or batch patch script just to change colors or visual style.
- Use post-render edits only for small defects or implementation bugs, not for primary art direction.

## Commands

Run commands from the project root.

Use the project Python environment managed by uv: `uv run python`.

```bash
uv run python -u -m ppt_workflow.runner outline --topic "..." --audience "..." --pages "..." --provider openai --research "..."
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact outline
uv run python -u -m ppt_workflow.runner contents --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact contents
uv run python -u -m ppt_workflow.runner plans --run-dir output/...
uv run python -u -m ppt_workflow.runner approve --run-dir output/... --artifact slide_plans
uv run python -u -m ppt_workflow.runner choose-renderer --run-dir output/... --renderer html
HTML_AI_REVIEW_ENABLED=false SVG_AI_REVIEW_ENABLED=false uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

Use `svg` instead of `html` in `choose-renderer` when the user wants the SVG branch.

The `img` branch is a Codex-side full-page image generation route. Do not run `ppt_workflow.runner render` for `img`, and do not call `choose-renderer` with `img` unless the project runner explicitly supports it in code. Instead, use the approved `slide-plans.json` as the source of truth, generate one image prompt per slide in chat, call Codex's `imagegen` tool for each full 16:9 slide image, save the resulting images under `output/.../img/`, then package those images into a PPTX.

## Long Deck Background Execution

Use this for `contents` and `plans` when the deck has more than 10 pages, when the topic implies heavy research/detail, or when an earlier generation phase already took several minutes.

Start the phase as a background job immediately. Do not let it run in the foreground until a 10-minute command timeout kills it.

```bash
mkdir -p output/.../logs
nohup uv run python -u -m ppt_workflow.runner contents --run-dir output/... > output/.../logs/contents.log 2>&1 & echo $! > output/.../logs/contents.pid
nohup uv run python -u -m ppt_workflow.runner plans --run-dir output/... > output/.../logs/plans.log 2>&1 & echo $! > output/.../logs/plans.pid
```

Run only the current phase; do not start `plans` until `contents` is approved.

Monitoring cadence:

- Check whether the runner process is alive at most once per minute.
- Tail the phase log at most once per minute and relay meaningful `[progress]` lines or the latest concise status to the user.
- Check generated artifact files, output directories, or `workflow-state.json` at most once every 10 minutes unless the process exits or the user asks for a status update.
- Do not kill, restart, or replace a live background phase just because there has been no new file output for several minutes.
- If the process exits successfully, move to the normal approval checkpoint and provide the preview Markdown path.
- If the process exits with an error, read the tail of the phase log, summarize the failure, and rerun only after fixing the cause or getting user direction.

## IMG Prompt Compilation

For the `img` branch, do not pass raw `slide-plans.json` text directly to imagegen. Treat each slide plan as source material and compile it into a clean image-generation prompt.

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

## Approval Checkpoints

After `outline`, return the `outline-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After `contents`, return the `contents-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After `plans`, return the `slide-plans-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After slide plans are approved, ask:

- `html`: recommended for stable layout, image PPTX, and editable PPTX export.
- `svg`: lighter source files and faster visual drafts.
- `img`: full-page image generation through Codex imagegen; best for visually polished management-facing slides that should look like finished presentation images, including pages with Chinese copy, numbers, labels, and structured information.

When asking, explicitly mention that the final render defaults to AI review disabled because review can be slow. If the user wants the review/fix loop, they must opt in clearly.

Only run the final render after the user chooses `html`, `svg`, or `img`.

Before every final render, clean render-only outputs from previous failed or interrupted runs so exported PPTX files cannot include stale slides:

```bash
rm -rf output/.../html output/.../svg output/.../img output/.../reviews output/.../editable output/.../slide-status.json output/.../*.pptx output/.../editable-ppt-chain.json
```

Do not delete approved source artifacts such as `outline.json`, `contents.json`, `slide-plans.json`, previews, or `workflow-state.json`.

## Long-Running Render Etiquette

HTML and SVG render phases can take a long time because they may generate, validate, screenshot, regenerate, and export every slide. Treat this as expected.

- Do not assume the render is stuck just because no output appears for several minutes.
- Do not try to kill or restart the process unless the command exits with an error, the user asks you to stop it, or the same fatal condition repeats and no files/progress have changed for a long time.
- While a render is running, give at most one short heartbeat update per minute.
- Check generated files or `status` at most once every 10 minutes unless the process exits or the user asks for an update.
- When `[progress]` lines are available, show progress as `current/total` or a simple progress bar in chat.
- When the render finishes, read `slide-status.json` before the final answer. Summarize aggregate pass/fail status and only call out exceptions; do not make generated review Markdown files a human review step unless the user asks.

By default, disable AI review for speed:

```bash
HTML_AI_REVIEW_ENABLED=false SVG_AI_REVIEW_ENABLED=false uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

When user-provided style guidance was encoded in `slide-plans.json`, also disable the migrated core for HTML renders:

```bash
HTML_USE_MIGRATED_CORE=false HTML_AI_REVIEW_ENABLED=false SVG_AI_REVIEW_ENABLED=false uv run python -u -m ppt_workflow.runner render --run-dir output/...
```

Only omit those environment variables when the user explicitly asks to enable the AI review/fix loop.

## Revision Policy

If the user requests changes at a checkpoint:

1. Edit the relevant JSON artifact directly when the requested change is clear.
2. Regenerate the downstream artifact after approval.
3. Do not approve an artifact until the user explicitly approves it.

Relevant files:

- `outline.json`
- `contents.json`
- `slide-plans.json`
- `workflow-state.json`

Use `workflow-state.json` for approval state. Keep `outline.json` and `contents.json` as plain data files because existing generation functions read them directly.

## Renderer Choice

HTML branch:

- Generates `html/`
- Runs HTML validation/review/fix loop
- Exports image PPTX
- Exports editable PPTX
- Writes `editable-ppt-chain.json`

SVG branch:

- Generates `svg/`
- Runs SVG validation/review/fix loop
- Exports PPTX

IMG branch:

- Does not use runner render.
- Uses Codex chat orchestration and the `imagegen` tool.
- Generates `img/`
- Generates each slide as one complete 16:9 full-page image.
- Does not split the slide into background, foreground, text overlay, layers, or selective per-page HTML/SVG rendering.
- Does not create editable slide contents; the exported PPTX uses one full-slide image per page.
- Do not discourage the user from using `img` because a slide contains Chinese copy, numbers, labels, equations, or tables.
- Prompt each slide as a finished presentation page: composition, hierarchy, management-facing visual tone, core message, visual constraints, and any required exact Chinese text or structured information.

## References

Read these only when needed:

- `references/workflow.md` for the full phase model.
- `references/artifact-contract.md` for artifact and approval contracts.
