---
name: ppt-deck-workflow
description: Use this workflow when Codex needs to create a PPT deck with staged outline, content, and slide-plan approvals; HTML, SVG, or IMG rendering; optional Pillow-assisted IMG-to-SVG conversion; deterministic PPTX export; or installation, update checks, GitHub branch upgrades, status checks, and rollback of the globally installed PPT Skill. Supports both this repository and a self-contained global skill installation without a repository AI client, model gateway, or runner.
---

# PPT Deck Workflow

Use this skill for PPT generation tasks in either repository-local or globally installed mode. The user should only need to ask for a PPT; do not expose internal renderer functions as separate skills.

## Local And Global Runtime Modes

Determine the runtime mode from the skill folder:

- Repository-local mode: the skill has no `runtime/` directory. Run commands from the repository root with `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...`.
- Globally installed mode: the skill contains `runtime/`. Run its scripts with `uv run --project <skill-root>/runtime python -u <skill-root>/scripts/workflow.py ...`.

In global mode, the current working directory is the default PPT workspace and generated runs go under that workspace's `output/`. Set `PPT_AGENT_WORKSPACE` to an absolute directory when the deck should be written somewhere else. `OUTPUT_DIR` may still override the output root.

Do not assume the original `PPT-AGENT` repository exists when `runtime/` is present. The global skill bundles `filename_utils.py`, `playwright_runtime.py`, `pptx_builder.py`, `html_pipeline/`, and `vendor_presentation_core/`.

## Global Skill Maintenance

Use `scripts/update_global_skill.py` only when `runtime/` and `.install-state.json` are present. The installed state records the GitHub repository, branch, commit, and managed file hashes; the default source is `TuKJet/PPT-AGENT` branch `codex/all-logic-in-skills`.

- For a status-only request, run `status`; do not use the network.
- For an update check, run `check`; do not modify the installation.
- Run `upgrade` or `rollback` only after the user explicitly requests that mutation. Let Codex request network and `$CODEX_HOME` write approval when required.
- Do not use `install_global_skill.py --force` as the normal update path. The updater stages the branch, validates it, preserves `runtime/.venv`, `runtime/.uv-cache`, local `uv.lock`, and the shared Playwright cache, then rolls back on failure.
- Before resolving Playwright, let the installer inspect the shared cache links. When a complete cached Chromium headless-shell revision maps to a Playwright version at or above the Skill minimum, materialize that exact version in the installed runtime so `playwright install --only-shell chromium` reuses the existing browser. Fall back to the open minimum requirement only when no reliable compatible mapping exists.
- Stop after a successful upgrade or rollback and tell the user the new Skill instructions apply on the next turn.

Read `references/global-skill-maintenance.md` before installing, checking, upgrading, or rolling back the global Skill.

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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-review --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
# IMG only: export now stops at a required post-export user choice
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

Run-directory discipline is mandatory:

- Every new PPT request must create one project folder under `output/`.
- Keep all intermediate artifacts, render files, review files, and exported decks inside that single `output/<project>/` folder.
- Do not create workflow run directories in the repository root or elsewhere outside `output/`.
- If you pass `--run-dir`, it must resolve inside `output/`; a bare relative name such as `project-a` is treated as `output/project-a`.
- Do not reuse an existing run directory, empty directory, backup directory, smoke-test directory, or any other pre-existing folder as a shortcut for a new deck unless the user explicitly asks for reuse.
- If creating the new `output/<project>/` folder fails because of sandbox, ACL, or helper-init restrictions, request the needed permission or escalation instead of reusing an existing folder or copying an old run as a workaround.

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
6. For the `img` branch, export the original IMG PPTX first, then stop and ask the user whether to convert every page IMG to native SVG and create a second SVG-based PPTX. This post-export question is mandatory and must not be asked earlier.

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
- For the `img` branch, do not ask about IMG-to-SVG conversion at renderer-choice time. Generate all IMG pages and export the original IMG PPTX first.
- After the original IMG PPTX export, do not describe the workflow as complete and do not silently choose `on` or `off`. Show the IMG PPTX path, ask the user explicitly, and stop.
- If the user chooses `on`, do not export the native-SVG PPTX until every source IMG has been passed directly to the model and every returned SVG passes the helper validation.
- Do not browse, research, or synthesize content for `contents` before `outline` approval unless the user explicitly asks for research before outlining.
- If a downstream file was accidentally created early, delete it or ignore it, reset the workflow to the current approved checkpoint, and tell the user what was corrected.

Do not use the Web UI for this workflow. The approval loop happens in the Codex conversation.

Do not use repository model-provider code for research or synthesis. For `contents` generation, prefer this order: a Codex-installed local research skill when one is available in the current session, then direct Codex web search/browsing to primary sources when needed, then repo-local synthesis. If a suitable local research skill is available, invoke it first and let it structure the evidence-gathering pass instead of jumping straight to ad hoc web browsing. If the user requests freshness or current facts, follow higher-priority browsing policy in Codex, then cite or record research notes in the generated artifacts.

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
- If the intended new run directory cannot be created or initialized in the current permission mode, stop and request approval for directory creation; do not fall back to any existing folder, even if it is empty.

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

Run commands from the active PPT workspace. In repository-local mode this is the project root; in global mode it is the directory where the user wants the new `output/` folder.

Use the correct uv launch prefix for the detected runtime mode. The examples below show repository-local mode; in global mode replace the prefix as described in `Local And Global Runtime Modes`.

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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-review --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode off
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
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

## Subagent Render Decomposition

Use this when rendering `html` or `svg` decks with many pages, when the slide plans are dense, or when you want to keep the main Codex context focused on review and coordination instead of carrying every page draft inline.

Recommended flow:

1. Keep outline, contents, and slide-plan generation in the main agent because they are deck-global checkpoints.
2. After `slide_plans` is approved and the renderer is chosen, materialize page jobs:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
```

3. The helper writes a shared deck context plus one job file per slide under `render-jobs/<renderer>/`.
4. Dispatch one subagent per page job. Each subagent should read only its `slide-xx.json`, the shared context it references, and the prompt contract for the chosen renderer.
5. Each subagent writes exactly one renderer source file into the same run directory, such as `output/<project>/html/...` or `output/<project>/svg/...`.
6. The main agent stays responsible for naming consistency, spot-checking the results, running any render-review subflow, and deciding whether a page needs a follow-up subagent repair pass.
7. If a page needs revision, send the same job file back to a subagent with the repair feedback instead of letting the main agent absorb the full page-generation context again.

Guardrails:

- Use the same run directory for subagent work; do not fork page jobs into separate project folders.
- Treat `render-jobs/<renderer>/shared-context.json` as the deck-level source for cross-page consistency.
- Keep the subagent scope page-local: one job file in, one renderer source file out.
- The main agent should aggregate quality, not rewrite every page itself unless the change is trivial.

## IMG Prompt Compilation

For the `img` branch, do not pass raw `slide-plans.json` text directly to imagegen. Treat each slide plan as source material and compile it into a clean image-generation prompt. After all images are generated, package them into the original IMG PPTX; that export intentionally stops at the mandatory post-export IMG-to-SVG user choice.

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

## IMG-to-SVG Post-Export Gate

This gate is mandatory for every `img` renderer run. Keep the user interaction unchanged: export and hand off the IMG PPTX first, then ask whether to convert it to SVG.

1. Generate every full-slide IMG page under `img/`.
2. Run normal `export`. It creates `<topic>-img.pptx`, records `img_svg_choice_pending`, and prints `next=ask-user-img-svg`.
3. Give the user the exact IMG PPTX path and ask whether to convert each page IMG to PowerPoint-compatible SVG and create a second PPTX. Stop the turn. Do not record a choice unless it came from the user after this export.
4. Record the answer. `off` completes the branch with the original IMG PPTX:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode off
```

For `on`:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-img-svg --run-dir output/... --mode on
```

5. Read `render-jobs/img-svg/manifest.json`. For every page job, pass `source_image_path` directly to a vision-capable model and follow `references/prompt-contracts.md#img-to-svg-model-conversion-contract`. The IMG itself is mandatory model input; do not regenerate the SVG from slide plans alone.
6. Create exactly one final SVG per page at the exact `target_path` under `img-svg/`. Do not create layered variants or sibling directories such as `v1`, `v2`, `overlay`, `image-elements`, or `clean`.
7. Rebuild text, cards, dividers, arrows, and simple diagrams as SVG vectors.
8. For logos, icons, badges, and other incompatible or high-fidelity regions, crop directly from the original IMG with Pillow and embed each crop as a Base64 PNG `<image>` node. Do not redraw known icons through HTML or an icon library by default.
9. Use the bundled deterministic helper. It maps 1280x720 crop coordinates to the original image dimensions and writes Base64 data directly into the final SVG without creating temporary PNG files:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/embed_img_crops.py --manifest output/.../render-jobs/img-svg/slide-01-crops.json
```

10. Validate and export:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py complete-img-svg --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export-img-svg --run-dir output/...
```

The validator requires one exact SVG per IMG, valid XML, `viewBox="0 0 1280 720"`, vector page structure, safe embedded Base64 PNG/JPEG crops, and no external URL/file, `<foreignObject>`, or script. The final exporter embeds native `.svg` media plus its PowerPoint preview; it must not rasterize the SVG back into the deck.

Use Playwright for final SVG rendering and visual QA, not for routine icon crop generation. When Microsoft PowerPoint is installed, open the final PPTX and export all slides to PNG for the final Office rendering check.

Do not run `clean-render` between the original IMG PPTX export and this post-export choice/conversion; the original IMG PPTX is an input artifact and must remain available beside the SVG derivative. If a fresh IMG render is required, restart that render intentionally and let the new IMG export reopen the mandatory choice gate.

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

The IMG-to-SVG choice is separate from renderer choice. Never bundle it into this earlier question; it is asked only after the original IMG PPTX has been generated and handed to the user.

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

In this Codex-authored branch, `clean-render` is for derived outputs only. It must not be used as a way to wipe `html/`, `svg/`, or `img/` source pages. If you truly need to rebuild renderer source files from scratch, do that intentionally after confirming the branch state instead of assuming cleanup should delete them.

Do not delete approved source artifacts such as `outline.json`, `contents.json`, `slide-plans.json`, previews, `workflow-state.json`, or renderer source pages that were already authored for the active branch.

## Multi-Renderer Compare Discipline

When the user wants `html` and `img`, or any multi-renderer comparison:

- Keep all renderer outputs in the same run directory under `output/<project>/`.
- Renderer source files stay separated by subdirectory inside that same run directory, for example `output/<project>/html`, `output/<project>/svg`, and `output/<project>/img`.
- Renderer-specific exports must also stay in the same run directory, using distinct filenames so compare artifacts do not overwrite each other.
- Use renderer-specific status snapshots or manifests when available, but preserve the common checkpoint artifacts in place.
- Never fork a comparison into sibling project directories unless the user explicitly asks for isolated branches.
- If cleanup is needed, use `clean-render` only to remove derived outputs; do not use it as a shortcut to clear authored renderer source pages from the active run directory.

## Long-Running Render Etiquette

HTML, SVG, and IMG export phases can take time because screenshots, PowerPoint export, and editable export are local rendering operations. Treat this as expected.

- Do not assume the render is stuck just because no output appears for several minutes.
- Do not try to kill or restart the process unless the command exits with an error, the user asks you to stop it, or the same fatal condition repeats and no files/progress have changed for a long time.
- While a render is running, give at most one short heartbeat update per minute.
- Check generated files or `status` at most once every 10 minutes unless the process exits or the user asks for an update.
- When helper status lines are available, relay concise progress to the user.
- When the render finishes, read `slide-status.json` before the final answer. Summarize aggregate pass/fail status and only call out exceptions; do not make generated review Markdown files a human review step unless the user asks.

For `img`, the first IMG PPTX export is not final completion. It is the trigger for the mandatory user-facing IMG-to-SVG question. Read `slide-status-img.json`, hand off the IMG PPTX, and stop. Only after the user's `off` choice or the successful `on` conversion/export may the run be called complete.

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

- Does not use repository model-provider or AI render code; image generation and IMG-to-SVG reconstruction remain Codex/model-orchestrated, while deterministic local helpers package and validate the PPTX artifacts.
- Uses Codex chat orchestration and the `imagegen` tool.
- Generates `img/`
- Generates each slide as one complete 16:9 full-page image.
- Does not split the slide into background, foreground, text overlay, layers, or selective per-page HTML/SVG rendering.
- First exports an original PPTX that uses one full-slide image per page.
- After that original export, requires an explicit user choice about the optional IMG-to-SVG model conversion; this question cannot be moved earlier or skipped.
- When the user chooses `on`, passes every page IMG directly to the model, writes one final hybrid vector-plus-embedded-crop page under `img-svg/`, and creates `<topic>-img-svg.pptx` with native SVG media that PowerPoint can import and convert using its SVG tooling.
- The SVG derivative keeps text and simple geometry vector while preserving incompatible icons/logos as embedded raster image elements. It is not guaranteed to become semantically separated PowerPoint text boxes or chart objects; PowerPoint receives one native SVG object per slide.
- Do not discourage the user from using `img` because a slide contains Chinese copy, numbers, labels, equations, or tables.
- Prompt each slide as a finished presentation page: composition, hierarchy, management-facing visual tone, core message, visual constraints, and any required exact Chinese text or structured information.

## References

Read these only when needed:

- `references/workflow.md` for the full phase model.
- `references/artifact-contract.md` for artifact and approval contracts.
- `references/prompt-contracts.md` before generating or reviewing any deck content or renderer file.
- `references/global-skill-maintenance.md` before global installation, update checks, upgrades, or rollback.
