---
name: ppt-deck-workflow
description: Create PowerPoint decks with staged outline, content, and slide-plan approval, then IMG or editable PPTD output with a local browser editor. Also install, check, upgrade, or roll back the self-contained global Skill.
---

# PPT Deck Workflow

Codex authors the content and renderer files. Use the deterministic helper for state, previews, export, and the local editor; never use `ppt_workflow.runner`, repository AI clients, or model-provider configuration.

## Runtime

- Repository-local mode (no `runtime/`): from the repository root, use `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...`.
- Globally installed mode (contains `runtime/`): use `uv run --project <skill-root>/runtime python -u <skill-root>/scripts/workflow.py ...` from the user's workspace.
- Global mode writes to the caller's workspace. `PPT_AGENT_WORKSPACE` can select another workspace; `OUTPUT_DIR` overrides the output root. Never depend on the original repository or a sibling reference project.

## Progressive Loading

Read only the current stage's reference. Do not pre-read downstream prompts, schemas, or renderer manuals. Do not recursively read `references/` or `assets/`.

| When | Read |
| --- | --- |
| Before generating outline | [outline.md](references/outline.md) |
| After outline approval, before contents | [contents.md](references/contents.md) |
| After contents approval, before slide plans | [slide-plans.md](references/slide-plans.md), [role-budgets.md](references/role-budgets.md) |
| Revising an existing artifact | [revision.md](references/revision.md) |
| Only after user chooses IMG | [img.md](references/img.md) |
| Only after user chooses PPTD | [pptd.md](references/pptd.md); follow its targeted format-reading instructions |
| Global maintenance request | [global-skill-maintenance.md](references/global-skill-maintenance.md) |

**Do not read or include PPTD format specifications, examples, or editor implementation in model context before PPTD is selected.** Do not load IMG prompts for a PPTD task. Renderer choice does not require either renderer's detailed manual.

## Sequential Checkpoints

Keep this order: outline → contents → slide plans → renderer choice → render/export.

1. `init --topic "..." --audience "..." --pages "..." --research "..."` creates a new `output/<project>/` run.
2. Write `outline.json`, run `preview --run-dir output/<project> --artifact outline`, link the non-empty preview and stop for approval.
3. After explicit approval, record `approve --artifact outline`. Read the contents contract, perform needed research, write `contents.json`, preview it, link the preview and stop.
4. After explicit approval, record `approve --artifact contents`. Read the slide-plan contract, write version-2 `slide-plans.json`, preview it, link the preview and stop.
5. After explicit approval, record `approve --artifact slide_plans`. Offer exactly **IMG or PPTD** and wait for the user's choice.
6. Record `choose-renderer --renderer img|pptd`, then read only that branch guide and follow it.

Every helper command after init uses `--run-dir output/<project>`. Approval is an explicit chat response, not a file existing or a successful helper call. Do not research for or prepare downstream artifacts before the current checkpoint is approved, unless the user explicitly requested research before outlining. Fix validation errors before handing over a preview.

Renderer choice wording: **IMG：整页图片，视觉表现优先；PPTD：元素可编辑，生成后打开本地网页编辑器，可手动调整并导出 PPTX。** Default recommendation: IMG, unless editability is the user's priority. HTML and standalone SVG are no longer renderer options. Do not ask a render-review preference.

PPTD selection authorizes starting the local editor after its project files are ready. Do not start it for IMG or during upstream planning. The browser is a page editing surface; the three content approvals remain in chat.

## Shared Invariants

- One new deck, one new folder under `output/`. Never reuse a previous run as a workaround for a permission/init failure. Keep sources, media, intermediate artifacts, reviews, and outputs in this same run directory.
- Audience understanding starts in the outline and carries through content, design system, and rendering. Leadership restraint means selective information, not a ban on color, images, diagrams, or polished visual design.
- Slide plans use version 2, one `deck_strategy`, one `design_system`, and structured per-page plans. Keep visible copy exact and reference the shared palette. The slide-plan contract contains the schema; do not load renderer schemas to plan the deck.
- Capture style changes in the plan before regenerating. Persist final-state copy, not revision history or rejected text. For small edits to an existing PPTD project, read its latest saved page first and preserve unrelated manual changes.
- Use `prepare-render-jobs` after selection for page-local inputs. Jobs carry the shared design system; work incrementally rather than rereading the entire deck for every page.
- For requested comparisons, keep both branches in the same run directory: `img/` and `pptd/`, with distinct exports.
- `clean-render` removes derived outputs, never authored pages or media.
- Long operations are expected. Keep the user informed, do not restart healthy exports just for silence, and report material failures rather than implying successful delivery.

## Global Skill Maintenance

Read the maintenance reference only for install/status/check/upgrade/rollback. Use `scripts/install_global_skill.py` for installation and `scripts/update_global_skill.py` for maintenance of an installed copy. Preserve staged updates, rollback, the runtime environment, and shared Playwright cache. Do not replace an installation with `--force` as an update strategy. The installer bundles runtime and editor assets; it must not create a symlink back to this repository.

After installing, follow the README's mandatory global PowerPoint Skill routing check. Never silently modify global Agent instructions. This development task does not install or upgrade the user's global copy automatically.
