---
name: ppt-deck-workflow
description: Use this local workflow when Codex needs to create a PPT deck in this repository without calling the repo's AI client, model gateway, or runner. The skill guides Codex through outline, content, slide-plan approval checkpoints, renderer choice, Codex-authored HTML/SVG/IMG slide creation, and deterministic artifact/export helper scripts.
---

# PPT Deck Workflow

Use this skill for PPT generation tasks in this project. The user should only need to ask for a PPT; do not expose internal renderer functions as separate skills.

## Codex-Only Branch Override

This branch has removed the public Python runner and must not use the repository AI gateway. Treat any older runner-oriented notes below as legacy context only when they describe artifact names or approval semantics.

Do not call `ppt_workflow.runner`, `AIClient`, `pipeline.step*`, or provider/model environment configuration. Codex itself generates `outline.json`, `contents.json`, `slide-plans.json`, and the renderer source files. Use the bundled helper only for deterministic artifact state, preview generation, render cleanup, and PPTX export:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...
```

The current command flow is:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py init --topic "..." --audience "..." --pages "..." --research "..."
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode off
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-review --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Before generating any outline, contents, slide plans, HTML, SVG, IMG prompts, screenshot review, or repair pass, read `references/prompt-contracts.md`. It carries the old runner/pipeline prompt behavior in skill form: content rules, planning rules, role budgets, HTML/SVG generation constraints, screenshot review criteria, and repair feedback policy.

Audience control begins at the outline stage, not only at slide planning or rendering. When the user indicates a deck is for technical readers, management, investors, executives, government, operators, or similar groups, carry that choice through outline structure, page-count allocation, content depth, slide-plan style, and final page visuals.

Treat audience understanding as an internal operating lens for the entire workflow. Infer what that audience wants to understand, decide, compare, or de-risk, then let that inference shape structure, wording, evidence depth, pacing, and visual emphasis across outline, contents, slide plans, and rendering. Keep that reasoning mostly implicit in visible slide copy unless the user explicitly asks for an overt rhetorical style.

## Core Rule

Run the deck as one Codex workflow:

1. Generate only the current checkpoint artifact.
2. Stop at the review checkpoint and ask the user to approve or request changes.
3. After explicit user approval, generate the next artifact.
4. Let the user choose `html`, `svg`, or `img` only after outline, contents, and slide plans are each approved.
5. Render through the chosen branch.

## Strict Stage Gate

This workflow is sequential and approval-gated. Do not pre-generate, write, preview, research for, or otherwise prepare downstream artifacts before the current checkpoint is explicitly approved by the user in chat.

Required order:

1. Create `outline.json`.
2. Run `preview --artifact outline`.
3. Return `outline-preview.md` to the user and stop.
4. Only after user approval, perform any needed research or web search for `contents`.
5. Create `contents.json`.
6. Run `preview --artifact contents`.
7. Return `contents-preview.md` to the user and stop.
8. Only after user approval, create `slide-plans.json`.
9. Run `preview --artifact slide_plans`.
10. Return `slide-plans-preview.md` to the user and stop.
11. Only after user approval, ask for renderer choice and review preference.

Concrete prohibitions:

- Do not create `contents.json` until `outline` is approved.
- Do not create `slide-plans.json` until `contents` is approved.
- Do not create `html/`, `svg/`, `img/`, render screenshots, or export PPTX until `slide_plans` is approved and the renderer is chosen.
- Do not browse, research, or synthesize content for `contents` before `outline` approval unless the user explicitly asks for research before outlining.
- If a downstream file was accidentally created early, delete it or ignore it, reset the workflow to the current approved checkpoint, and tell the user what was corrected.

Do not use the Web UI for this workflow. The approval loop happens in the Codex conversation.

Do not use repository model-provider code for research or synthesis. For `contents` generation, use Codex-native research capability directly: a Codex-installed research skill when available in the current session, or Codex web search/browsing. If the user requests freshness or current facts, follow higher-priority browsing policy in Codex, then cite or record research notes in the generated artifacts.

For helper commands, use unbuffered Python (`-u`) so status lines stream back to Codex.

For long decks, generate artifacts incrementally inside Codex and write checkpoint files as soon as each stage is ready.

## Approval Transparency

Never ask the user to approve an artifact blindly.

Whenever the workflow reaches a user approval checkpoint, hand the generated Markdown preview document to the user for direct review. Do not read the preview file and summarize it for the user. The point of the preview Markdown is to give the user the review surface, not to have the agent substitute its own summary.

Required behavior:

- Name the exact Markdown file that was generated.
- Provide a clickable path to the Markdown file when possible.
- Tell the user to review that file and reply with approval or requested changes.
- Do not summarize, paraphrase, excerpt, or pre-judge the Markdown contents unless the user explicitly asks for a summary.
- Before handing the preview to the user, verify that the preview file is non-empty and visually legible in the intended language. If terminal encoding is ambiguous, inspect the file with a Unicode-safe read path before claiming it is ready.
- If the preview is blank, garbled, or does not reflect the current artifact, fix the source artifact and regenerate the preview before handing it to the user.
- Do not proceed past an approval checkpoint until the user has approved after receiving the file link.
- Treat approval as chat-only: a file existing on disk, a helper status, or the agent's own judgment is not approval.
- When handing off an approval checkpoint, end the turn after providing the preview path unless the user has already explicitly approved that artifact in the same message.
- Do not describe a checkpoint as approved, reviewed, or complete based only on the artifact existing on disk.

Encoding safety:

- When manually editing Chinese or other non-ASCII artifact files from the shell, prefer ASCII-safe escaped JSON content if the local shell or path handling has shown encoding instability.
- If a Windows shell path cannot reliably address the intended run directory because of encoding issues, locate the run directory programmatically first, then update only the current checkpoint artifact.

Render-stage review Markdown files such as `reviews/review-*.md` and `editable/review-*.md` are internal QA artifacts, not user approval checkpoints. Do not ask the user to review them one by one, and do not dump per-slide review summaries unless the user asks. At completion, use `slide-status.json` for a concise aggregate status and call out only exceptions: failed checks, warning counts, residual layout issues, fallback behavior, or export caveats.

## Style Control

If the user provides reference images, screenshots, brand examples, or a written style direction, encode that direction during the slide-plan stage. The plan artifact is the control surface for colors, typography, density, layout rhythm, visual motifs, chart treatment, and page-level art direction.

Audience-driven deck style is upstream of that control surface: the outline should already reflect who the deck is for, and `slide-plans.json` should refine that audience choice into page-level visual direction rather than inventing a new audience stance late in the workflow.

Required behavior:

- Put style requirements into `slide-plans.json` before asking for slide-plan approval.
- If the style guidance arrives after `slide-plans.json` exists, edit `slide-plans.json` directly and regenerate downstream render outputs only after the updated plan is approved.
- If the user gives style guidance at or before the slide-plan stage, encode that guidance directly into `slide-plans.json` and the Codex-authored renderer files.
- Express audience fit mostly through ordering, emphasis, density, and tone rather than explicit on-slide statements about what the audience cares about.
- Do not wait until HTML/SVG files are generated and then write a rebuild, migration, or batch patch script just to change colors or visual style.
- Use post-render edits only for small defects or implementation bugs, not for primary art direction.

## Commands

Run commands from the project root.

Use the project Python environment managed by uv: `uv run python`.

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py init --topic "..." --audience "..." --pages "..." --research "..."
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact outline
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact contents
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py preview --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py approve --run-dir output/... --artifact slide_plans
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode off
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-review --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
```

Use `svg` instead of `html` in `choose-renderer` when the user wants the SVG branch.

The `img` branch is a Codex-side full-page image generation route. Use approved `slide-plans.json` as the source of truth, generate one image prompt per slide in chat, call Codex's `imagegen` tool for each full 16:9 slide image, save the resulting images under `output/.../img/`, then package those images into a PPTX with the helper.

## Long Deck Background Execution

Use this for `contents` and `plans` when the deck has more than 10 pages, when the topic implies heavy research/detail, or when an earlier generation phase already took several minutes.

Work incrementally and save artifacts as soon as each checkpoint is ready.

Run only the current phase; do not start `plans` until `contents` is approved.

Monitoring cadence:

- Give concise progress updates while Codex is generating long artifacts.
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

After `outline`, return the `outline-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks. Stop here until the user approves; do not research or generate `contents.json` yet.

After `contents`, return the `contents-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks. Stop here until the user approves; do not generate `slide-plans.json` yet.

After `plans`, return the `slide-plans-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks. Stop here until the user approves; do not choose a renderer or render yet.

After slide plans are approved, ask:

- `html`: recommended for stable layout, image PPTX, and editable PPTX export.
- `svg`: lighter source files and faster visual drafts.
- `img`: full-page image generation through Codex imagegen; best for visually polished management-facing slides that should look like finished presentation images, including pages with Chinese copy, numbers, labels, and structured information.
- For `html` and `svg`, also ask whether to enable the render review subflow. Default recommendation: `off`.

When asking, explicitly mention that this branch uses Codex-authored renderer files and deterministic export, not a repository AI review/fix loop. Review is an explicit Codex-side subflow, not an automatic repo-side loop.

Only run the final render after the user chooses `html`, `svg`, or `img`.

For `html` and `svg`, confirm review preference before export:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode off
```

Or, when the user wants review enabled:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-review --run-dir output/... --mode on
```

Before every final render, clean render-only outputs from previous failed or interrupted runs so exported PPTX files cannot include stale slides:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
```

Do not delete approved source artifacts such as `outline.json`, `contents.json`, `slide-plans.json`, previews, or `workflow-state.json`.

## Long-Running Render Etiquette

HTML, SVG, and IMG export phases can take time because screenshots, PowerPoint export, and editable export are local rendering operations. Treat this as expected.

- Do not assume the render is stuck just because no output appears for several minutes.
- Do not try to kill or restart the process unless the command exits with an error, the user asks you to stop it, or the same fatal condition repeats and no files/progress have changed for a long time.
- While a render is running, give at most one short heartbeat update per minute.
- Check generated files or `status` at most once every 10 minutes unless the process exits or the user asks for an update.
- When helper status lines are available, relay concise progress to the user.
- When the render finishes, read `slide-status.json` before the final answer. Summarize aggregate pass/fail status and only call out exceptions; do not make generated review Markdown files a human review step unless the user asks.

Do not set AI review environment variables for this branch; the repository AI review/fix loop is not part of the skill-first workflow.

## Render Review Subflow

Use this only for `html` or `svg`, and only when the user explicitly enables it at renderer-choice time.

1. Choose `html` or `svg`.
2. Confirm review preference with the user. Default recommendation: `off`.
3. If review is `on`, record it with the helper.
4. Codex creates renderer source files.
5. Codex reviews rendered screenshots using `references/prompt-contracts.md`.
6. Codex applies small local fixes or rewrites slides using the repair contract.
7. After Codex considers the review loop complete, mark the review subflow complete:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-review --run-dir output/...
```

8. Clean render outputs if needed, then export.

If review is `off`, skip this subflow and export directly after renderer files are ready.

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

Use `workflow-state.json` for approval state. Keep `outline.json` and `contents.json` as plain data files because the skill helper and previews read them directly.

## Renderer Choice

HTML branch:

- Generates `html/`
- Uses Codex-authored HTML plus local screenshot/export checks
- Optional explicit Codex-side render review subflow
- Exports image PPTX
- Attempts editable PPTX export
- Writes `editable-ppt-chain.json`

SVG branch:

- Generates `svg/`
- Uses Codex-authored SVG plus local screenshot/export
- Optional explicit Codex-side render review subflow
- Exports PPTX

IMG branch:

- Does not use repository render code.
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
- `references/prompt-contracts.md` before generating or reviewing any deck content or renderer file.
