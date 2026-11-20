---
name: ppt-deck-workflow
description: Create PowerPoint decks with staged outline, content, and slide-plan approval, then IMG or editable PPTD sources and direct PPTX export. Also install, check, upgrade, or roll back the self-contained global Skill.
---

# PPT Deck Workflow

Codex authors the content and renderer files. Use the deterministic helper for state, previews, export, and the local editor; never use `ppt_workflow.runner`, repository AI clients, or model-provider configuration.

For style samples, finished slides and revisions, use the imagegen skill's built-in `image_gen` by default, including for high-quality or batch requests. When the user explicitly asks for 4K images, that request selects the imagegen skill's supported 4K Images API for those images. An explicit request to use the Images API also selects that route for its stated scope.

## Runtime

- Repository-local mode (no `runtime/`): from the repository root, use `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...`.
- Globally installed mode (contains `runtime/`): use `uv run --project <skill-root>/runtime python -u <skill-root>/scripts/workflow.py ...` from the user's workspace.
- Global mode writes to the caller's workspace. `PPT_AGENT_WORKSPACE` can select another workspace; `OUTPUT_DIR` overrides the output root. Never depend on the original repository or a sibling reference project.

## Progressive Loading

Read only the current stage's reference. Do not pre-read downstream prompts, schemas, or renderer manuals. Do not recursively read `references/` or `assets/`.

| When | Read |
| --- | --- |
| Resuming, switching models, or receiving corrections | [continuation.md](references/continuation.md) |
| Before generating outline | [outline.md](references/outline.md) |
| After outline approval, before contents | [contents.md](references/contents.md) |
| Only if the user takes the sample route after contents approval | [style-samples.md](references/style-samples.md) |
| When planning directly or after sample feedback | [slide-plans.md](references/slide-plans.md), [role-budgets.md](references/role-budgets.md) |
| Revising an existing artifact | [revision.md](references/revision.md) |
| Only after user chooses IMG | [img.md](references/img.md) |
| Only after user chooses PPTD | [pptd.md](references/pptd.md); follow its targeted format-reading instructions |
| User requests editable PPTD from generated IMG | [pptd.md](references/pptd.md), [img-pptd.md](references/img-pptd.md) |
| Global maintenance request | [global-skill-maintenance.md](references/global-skill-maintenance.md) |
| Before final delivery or continuing a cleaned project | [delivery.md](references/delivery.md) |

**Do not read or include PPTD format specifications, examples, or editor implementation in model context before PPTD is selected.** Do not load IMG prompts for a PPTD task. Renderer choice does not require either renderer's detailed manual.

## Sequential Checkpoints

Keep this order: outline → contents → planning mode → slide plans → renderer choice → render/export.

1. `init --topic "..." --audience "..." --pages "..." --research "..."` creates a new `output/<project>/` run.
2. Write `outline.json`, run `preview --run-dir output/<project> --artifact outline`, link the non-empty preview and stop for approval.
3. After explicit approval, record `approve --artifact outline`. Read the contents contract, perform needed research, write `contents.json`, preview it, link the preview and stop.
4. After `approve --artifact contents`, ask in ordinary chat: “你想直接看整套页面规划、边看边改，还是先看两页的四种风格样张找方向？” Honor a choice already given in the brief or approval. If the user has no clear preference or delegates the choice, use samples. Record it with `choose-plan-mode --mode direct|samples`.
5. **Direct:** use the brief and any references to draft the complete slide plans immediately. **Samples:** read [style-samples.md](references/style-samples.md), show the four treatments of the same two pages and pause for a free-form choice or blend. On either path, preview the full `slide-plans.json`, invite natural-language edits and wait for approval.
6. After explicit approval, record `approve --artifact slide_plans`. Offer exactly **IMG or PPTD** and wait for the user's choice.
7. Record `choose-renderer --renderer img|pptd`, then read only that branch guide and follow it.

Every helper command after init uses `--run-dir output/<project>`. Approval is an explicit chat response, not a file existing or a successful helper call. Do not research for or prepare downstream artifacts before the current checkpoint is approved, unless the user explicitly requested research before outlining. Fix validation errors before handing over a preview.

Renderer choice wording: **IMG：整页图片，视觉表现优先；PPTD：文字、数据和适合重建的元素可编辑，直接导出 PPTX。** Default recommendation: IMG, unless editability is the user's priority. HTML and standalone SVG are no longer renderer options. Do not ask a render-review preference.

PPTD exports directly via CLI with background visual QA. Open the browser editor only when the user requests interactive editing.

After IMG export, offer optional SVG or editable PPTD reconstruction. For a requested PPTD derivative run `choose-renderer --renderer pptd --source img`, prepare jobs and read [img-pptd.md](references/img-pptd.md). The default hybrid approach keeps text and key data editable and preserves complex artwork as independent crops. Honor explicit native reconstruction requests at their stated scope. Direct PPTD uses `--source plans`.

## Shared Invariants

- On resumption run `resume --run-dir ...`. Persist scoped requirements, sources and pending work with `checkpoint --file ...`; see [continuation.md](references/continuation.md). Compressed summaries do not replace these files.
- Keep exactly one `outline.json`, `contents.json`, and `slide-plans.json`. Update these in place and show the helper's `.workflow/*-preview.md`; do not create parallel revision reports, planning summaries or HTML slide galleries. A chat explanation is enough.
- One new deck, one new folder under `output/`. Never reuse a previous run as a workaround for a permission/init failure. Keep sources, media, intermediate artifacts, reviews, and outputs in this same run directory.
- Audience understanding starts in the outline and carries through content, design system, and rendering. Leadership restraint means selective information, not a ban on color, images, diagrams, or polished visual design.
- Slide plans use version 2, one `deck_strategy`, one `design_system`, and structured per-page plans. Keep visible copy exact and reference the shared palette. The slide-plan contract contains the schema; do not load renderer schemas to plan the deck.
- Capture style changes in the plan before regenerating. Persist final-state copy, not revision history or rejected text. For small edits to an existing PPTD project, read its latest saved page first and preserve unrelated manual changes.
- Use `prepare-render-jobs` after selection for page-local inputs. Jobs carry the shared design system; work incrementally rather than rereading the entire deck for every page.
- For requested comparisons, keep both branches in the same run directory: `img/` and `pptd/`, with distinct exports.
- `clean-render` removes derived outputs, never authored pages or media.
- Before final delivery run `finalize`, inspect its keep/remove list, then `finalize --apply`. Follow [delivery.md](references/delivery.md): retain canonical plans, PPTX and essential PPTD project assets, clear temporary work, and keep compact recovery metadata inside the canonical plan. Reusable operations belong in the Skill, not per-deck scripts.
- Long operations are expected. Keep the user informed, do not restart healthy exports just for silence, and report material failures rather than implying successful delivery.

## Global Skill Maintenance

Read the maintenance reference only for install/status/check/upgrade/switch/rollback. Use `scripts/install_global_skill.py` for installation and `scripts/update_global_skill.py` for maintenance of an installed copy. Preserve staged updates, rollback, the runtime environment, and shared Playwright cache. Do not replace an installation with `--force` as an update strategy. The installer bundles runtime and editor assets; it must not create a symlink back to this repository.

Natural-language public/stable channel requests map to `update_global_skill.py switch public`; private/internal requests map to `switch pptd`. This changes update source, not renderer availability. Follow the maintenance reference for authentication and rollback. Never collect credentials; authentication failure leaves the installation unchanged. After a successful switch report channel/commit and end the turn so the new instructions load next turn.

After installing, follow the README's mandatory global PowerPoint Skill routing check. Never silently modify global Agent instructions. This development task does not install or upgrade the user's global copy automatically.
