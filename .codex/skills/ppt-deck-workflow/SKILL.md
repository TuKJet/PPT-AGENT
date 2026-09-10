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
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py choose-renderer --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer img
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py clean-render --run-dir output/...
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py export --run-dir output/...
# Optional IMG derivative: run only after the user explicitly asks to spend
# additional model usage on SVG reconstruction
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

Audience adaptation is not visual austerity. For management, executive, leadership, or board audiences, make the information more selective and decision-led, but do not automatically turn the deck into black-white-gray text, ban illustrations, suppress brand colors, or remove all visual decoration. Use brand-led color, diagrams, data visuals, editorial imagery, icons, and selective ornament when they clarify the message or improve confidence; remove noise and competing focal points instead.

## Workflow Contract

Run the deck as one staged Codex workflow. Keep the approved artifacts as the source of truth, stop at each user checkpoint, and generate only the next artifact after explicit chat approval. The required order is outline → contents → slide plans → renderer choice → render → export.

The original IMG PPTX completes the IMG workflow. Ask once after export whether the user wants the optional SVG derivative; mention additional model/Token usage and that no reply is needed to decline. See `references/img-svg.md` and `references/img-svg-prompt.md` for the derivative contract.
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
11. Only after user approval, ask for renderer choice, recommend `img` by default, and request a review preference only when the user chooses `html` or `svg`.

Concrete prohibitions:

- Do not create `contents.json` until `outline` is approved.
- Do not create `slide-plans.json` until `contents` is approved.
- Do not create `html/`, `svg/`, `img/`, render screenshots, or export PPTX until `slide_plans` is approved and the renderer is chosen.
- For the `img` branch, do not ask about IMG-to-SVG conversion at renderer-choice time. Generate all IMG pages and export the original IMG PPTX first.
- After the original IMG PPTX export, describe the requested workflow as complete and ask once whether the user needs the optional SVG derivative. State that it preserves vector structure for PowerPoint shape conversion, requires additional model calls/Token usage, and needs no reply unless the user wants it. Never ask the user to reply with an `off`, decline, or “keep IMG” answer just to close the workflow.
- If the user chooses `on`, do not export the native-SVG PPTX until every source IMG has been passed directly to the model and every returned SVG passes the helper validation.
- Do not browse, research, or synthesize content for `contents` before `outline` approval unless the user explicitly asks for research before outlining.
- If a downstream file was accidentally created early, delete it or ignore it, reset the workflow to the current approved checkpoint, and tell the user what was corrected.

Do not use the Web UI for this workflow. The approval loop happens in the Codex conversation.

Do not use repository model-provider code for research or synthesis. For `contents` generation, prefer this order: a Codex-installed local research skill when one is available in the current session, then direct Codex web search/browsing to primary sources when needed, then repo-local synthesis. If a suitable local research skill is available, invoke it first and let it structure the evidence-gathering pass instead of jumping straight to ad hoc web browsing. If the user requests freshness or current facts, follow higher-priority browsing policy in Codex, then cite or record research notes in the generated artifacts.

For helper commands, use unbuffered Python (`-u`) so status lines stream back to Codex.

For long decks, generate artifacts incrementally inside Codex and write checkpoint files as soon as each stage is ready.

## Approval Transparency

At each outline, contents, and slide-plan checkpoint, provide the exact non-empty Markdown preview path and ask the user to review it. Continue only after explicit approval in chat. A file existing on disk or a helper status is not approval. Keep encoding checks for non-ASCII previews and do not hand off blank or garbled previews.

Render-stage review files are internal QA artifacts, not user approval checkpoints. Report only aggregate status and material exceptions unless the user asks for per-slide detail.
## Style Control

If the user provides reference images, screenshots, brand examples, or a written style direction, encode that direction during the slide-plan stage. The plan artifact is the control surface for colors, typography, density, layout rhythm, visual motifs, chart treatment, and page-level art direction.

Audience-driven deck style is upstream of that control surface: the outline should already reflect who the deck is for, and `slide-plans.json` should refine that audience choice into page-level visual direction rather than inventing a new audience stance late in the workflow.

Required behavior:

- Generate `slide-plans.json` version 2 with a top-level `deck_strategy`, a top-level `design_system`, and page-local `slides`. Version 1 and free-form string plans are legacy input and must not be generated or approved.
- In `deck_strategy`, record the primary audience, decision context, first questions they need answered, evidence order, and presentation posture so content and visual planning share one audience interpretation.
- In `design_system`, define one deck-level palette using named tokens, typography hierarchy, component/spacing rules, chart treatment, imagery/illustration policy, and brand/reference-image design genes.
- Make every page's `plan` a structured object with `core_message`, `layout_structure`, `visual_hierarchy`, `required_elements`, `palette_tokens`, `style_controls`, `audience_controls`, and `renderer_neutral_constraints`. Do not collapse these into one prose paragraph even when the model prefers a shorter response.
- Require every page plan and renderer prompt to reference the shared palette tokens. Do not let pages invent new primary, accent, background, surface, or text colors; permit page-specific colors only for semantic meaning, user-provided assets, or an explicitly justified narrative exception.
- Treat `render-jobs/<renderer>/shared-context.json` as the immutable carrier of `deck_strategy` and `design_system` for page-local rendering.
- Put style requirements into `slide-plans.json` before asking for slide-plan approval.
- Treat helper validation failure as a generation failure: repair or regenerate `slide-plans.json`, rerun `preview --artifact slide_plans`, and do not hand the user a partial Markdown preview. The helper intentionally rejects legacy/free-form plans and names missing field paths.
- Keep strict structured JSON as the machine source of truth, but make `slide-plans-preview.md` a curated human review surface. Show only the audience/decision lens, visual system, core message, layout, hierarchy, visible elements, and page-level style needed for approval. Keep renderer-internal audience controls and neutral constraints validated in JSON without dumping them into the approval body. Use readable headings, a compact palette table, numbered steps, and bullets; never expose raw JSON objects, braces, quoted field names, or fenced `json` blocks.
- If the style guidance arrives after `slide-plans.json` exists, edit `slide-plans.json` directly and regenerate downstream render outputs only after the updated plan is approved.
- If the user gives style guidance at or before the slide-plan stage, encode that guidance directly into `slide-plans.json` and the Codex-authored renderer files.
- Express audience fit mostly through ordering, emphasis, density, and tone rather than explicit on-slide statements about what the audience cares about.
- Interpret words such as `restrained`, `concise`, `executive`, and `boardroom-safe` as information-discipline constraints, not as instructions to prohibit brand color, illustrations, imagery, depth, or polished visual accents.
- Do not wait until HTML/SVG files are generated and then write a rebuild, migration, or batch patch script just to change colors or visual style.
- Use post-render edits only for small defects or implementation bugs, not for primary art direction.

## Command Reference

Run commands from the active PPT workspace with the repository-local or global prefix described above. The canonical sequence is shown once near the top of this file; use `workflow.py --help` for the complete command list. Keep all artifacts inside one `output/<project>/` directory.
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

## Optional IMG-to-SVG Post-Export Opt-In

The original IMG PPTX is complete before SVG conversion. Ask once after export: “是否需要继续转 SVG？矢量部分可在 PowerPoint 中转换为可编辑形状；转换会额外调用模型并产生 Token/费用。需要时回复‘继续转 SVG’，不需要则无需回复。” Do not present a decline option. After opt-in, use [`references/img-svg.md`](references/img-svg.md) and the sole model prompt in [`references/img-svg-prompt.md`](references/img-svg-prompt.md).

The derivative writes one final SVG per source IMG, preserves visible text as SVG text, and exports native SVG media. The detailed crop, backplate, visual review, hash binding, and PowerPoint boundary rules live in the referenced contract.
## Renderer Choice And Review

Ask for `html`, `svg`, or `img` only after the three approved checkpoints. Recommend `img` by default. For `html` or `svg`, ask whether render review is wanted and record `choose-review --mode off` or `on`; `off` is the default. IMG-to-SVG is asked only after the original IMG PPTX export.
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

For `img`, the original IMG PPTX export is final completion of the requested workflow. Read `slide-status-img.json`, hand off the IMG PPTX, and ask once whether the user needs the optional SVG derivative. Explain its editable-shape benefit and additional model/Token usage, but do not request a decline response.

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

For every second or later revision, treat the user's message as an edit delta, never as artifact copy. Rewrite the affected slide plan into a clean final-state specification:

- Keep only what the finished slide should contain and how it should be arranged.
- Rebuild `required_elements` as an allowlist of final visible content.
- Remove superseded literals from `material`, every `plan` field, the preview, render jobs, and renderer prompts. Do not retain rejected content inside negated phrases such as `delete X`, `do not include X`, or `must not show X`.
- Translate removals into positive end-state geometry. For example, replace `delete the old card and do not show its label` with `use clean background space; connect the two remaining modules with one short line`.
- Keep stable safety, brand, and factual constraints when they are independently useful; do not mix them with revision tombstones.
- Before previewing or preparing render jobs, search the revised slide block for rejected literal strings and revision verbs. Rewrite any residue unless the user explicitly wants that exact wording visible.
- Do not attach a marked-up reference containing rejected content to a full-page regeneration when the approved final-state plan is sufficient.

Read the final-state revision rules in `references/prompt-contracts.md` before revising an existing slide plan or compiling a renderer prompt from a revised plan.

Relevant files:

- `outline.json`
- `contents.json`
- `slide-plans.json`
- `workflow-state.json`

Use `workflow-state.json` for approval state. Keep `outline.json` and `contents.json` as plain data files because the skill helper and previews read them directly.

## Renderer Choice

Default recommendation: IMG. Keep HTML and SVG available as deliberate alternatives when their specific tradeoffs better match the user's request.

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
- That original export completes the IMG workflow. IMG-to-SVG remains available afterward only as an explicit opt-in that consumes additional model usage; do not require a decline response.
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
