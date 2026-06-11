---
name: ppt-deck-workflow
description: Use this local workflow when the user wants Codex to generate a PPT deck from inside this project, with shared outline/content/planning stages, Codex-in-chat approval checkpoints, and a later choice between HTML and SVG renderer branches.
---

# PPT Deck Workflow

Use this skill for PPT generation tasks in this project. The user should only need to ask for a PPT; do not expose internal renderer functions as separate skills.

## Core Rule

Run the deck as one Codex workflow:

1. Generate the common artifacts.
2. Stop at review checkpoints and ask the user to approve or request changes.
3. Let the user choose `html` or `svg` only after outline, contents, and slide plans are ready.
4. Render through the chosen branch.

Do not use the Web UI for this workflow. The approval loop happens in the Codex conversation.

Do not use Codex-side web search, `web.run`, or browser/web-search tools to research the PPT topic for this project. Put all research instructions, freshness requirements, source constraints, and search questions into the runner `--research` argument and let the project pipeline/AI client perform its own search and synthesis.

For long runner commands, use unbuffered Python (`-u`) so progress lines stream back to Codex. When the runner prints `[progress]` lines, relay those to the user as the source of truth instead of probing files repeatedly.

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

## Approval Checkpoints

After `outline`, return the `outline-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After `contents`, return the `contents-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After `plans`, return the `slide-plans-preview.md` path to the user and ask them to review the file directly. Do not read or summarize the file unless the user asks.

After slide plans are approved, ask:

- `html`: recommended for stable layout, image PPTX, and editable PPTX export.
- `svg`: lighter source files and faster visual drafts.

When asking, explicitly mention that the final render defaults to AI review disabled because review can be slow. If the user wants the review/fix loop, they must opt in clearly.

Only run the final render after the user chooses `html` or `svg`.

Before every final render, clean render-only outputs from previous failed or interrupted runs so exported PPTX files cannot include stale slides:

```bash
rm -rf output/.../html output/.../svg output/.../reviews output/.../editable output/.../slide-status.json output/.../*.pptx output/.../editable-ppt-chain.json
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

## References

Read these only when needed:

- `references/workflow.md` for the full phase model.
- `references/artifact-contract.md` for artifact and approval contracts.
