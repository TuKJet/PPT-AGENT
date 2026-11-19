---
name: ppt-deck-workflow
description: Create staged IMG or editable PPTD decks, verify native data in PPTX, and update selected values in supplied PPTD or PowerPoint templates. Install and maintain the global Skill.
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
| Resuming, switching models, or receiving corrections | [continuation.md](references/continuation.md) |
| Before generating outline | [outline.md](references/outline.md) |
| After outline approval, before contents | [contents.md](references/contents.md) |
| After contents approval, before slide plans | [slide-plans.md](references/slide-plans.md), [role-budgets.md](references/role-budgets.md) |
| Revising an existing artifact | [revision.md](references/revision.md) |
| Updating specific values in a supplied PPTD/PPTX template | [template-update.md](references/template-update.md) |
| Only after user chooses IMG | [img.md](references/img.md) |
| Only after user chooses PPTD | [pptd.md](references/pptd.md); follow its targeted format-reading instructions |
| User requests editable PPTD from generated IMG | [pptd.md](references/pptd.md), [img-pptd.md](references/img-pptd.md) |
| Global maintenance request | [global-skill-maintenance.md](references/global-skill-maintenance.md) |
| Before final delivery or continuing a cleaned project | [delivery.md](references/delivery.md) |

**Do not read or include PPTD format specifications, examples, or editor implementation in model context before PPTD is selected.** Do not load IMG prompts for a PPTD task. Renderer choice does not require either renderer's detailed manual.

## Sequential Checkpoints

For new decks: outline → contents → slide plans → renderer choice → render/export. For a fixed-deck update use the template revision route above.

1. `init --topic "..." --audience "..." --pages "..." --research "..."` creates a new `output/<project>/` run.
2. Write `outline.json`, run `preview --run-dir output/<project> --artifact outline`, link the non-empty preview and stop for approval.
3. After explicit approval, record `approve --artifact outline`. Read the contents contract, perform needed research, write `contents.json`, preview it, link the preview and stop.
4. After explicit approval, record `approve --artifact contents`. Read the slide-plan contract, write version-3 `slide-plans.json`, preview it, link the preview and stop.
5. After explicit approval, record `approve --artifact slide_plans`. Offer exactly **IMG or PPTD** and wait for the user's choice.
6. Record `choose-renderer --renderer img|pptd`, then read only that branch guide and follow it.

Every helper command after init uses `--run-dir output/<project>`. Approval is an explicit chat response, not a file existing or a successful helper call. Do not research for or prepare downstream artifacts before the current checkpoint is approved, unless the user explicitly requested research before outlining. Fix validation errors before handing over a preview.

Renderer choice wording: **IMG：整页图片，视觉表现优先；PPTD：文字、数据和适合重建的元素可编辑，直接导出 PPTX。** Default recommendation: IMG, unless editability is the user's priority. HTML and standalone SVG are no longer renderer options. Do not ask a render-review preference.

PPTD selection leads to direct CLI PPTX export. Do not start an interactive editor, use Computer Use, request folder selection, or ask the user to export. Background rendering for agent QA is automatic. Open the optional editor only when the user explicitly asks to edit there.

After IMG export, offer optional editable PPTD reconstruction alongside SVG. Continue only when requested; a prior explicit request for both is sufficient. Record `choose-renderer --renderer pptd --source img`, then prepare jobs. Preserve the original pixels in the IMG PPTX; final cleanup may remove verified duplicate sources. This derivative does not restart outline/content approval. Direct PPTD uses `--source plans` (the default).

For IMG → PPTD, “可编辑”, “转 PPTD” or “参考图片做可编辑 PPT” selects **hybrid reconstruction** by default: editable titles/body/key data plus independent source-image crops for complex visuals. Preserve the source's visual quality; rebuild simple geometry only when faithful. Full native reconstruction requires an explicit request such as “全部原生” or “图内每个节点和连线都要能改”; “不用 SVG” alone does not imply it. State the hybrid approach and proceed without another choice gate. Apply any explicit native requirement only to its requested scope. See [img-pptd.md](references/img-pptd.md) after this derivative is selected.

## Shared Invariants

- On resumption run `resume --run-dir ...`. Persist scoped requirements, sources and pending work with `checkpoint --file ...`; see [continuation.md](references/continuation.md). Compressed summaries do not replace these files.
- Keep exactly one `outline.json`, `contents.json`, and `slide-plans.json`. Update these in place and show the helper's `.workflow/*-preview.md`; do not create parallel revision reports, planning summaries or HTML slide galleries. A chat explanation is enough.
- One new deck, one new folder under `output/`. Never reuse a previous run as a workaround for a permission/init failure. Keep sources, media, intermediate artifacts, reviews, and outputs in this same run directory.
- Start the outline with what the user wants the audience to understand, decide or do. Adjust evidence, register and density for that audience and for live, standalone or hybrid use.
- New version-3 plans share one `deck_strategy` and `design_system`. Allocate screen copy, speaking points and reference material by page. Render approved screen copy and data. Existing version-2 plans remain readable.
- Update the plan before regenerating. For small edits to an existing PPTD project, read its latest saved page first and preserve unrelated manual changes.
- Use `prepare-render-jobs` after selection for page-local inputs. Jobs carry the shared design system; work incrementally rather than rereading the entire deck for every page.
- For requested comparisons, keep both branches in the same run directory: `img/` and `pptd/`, with distinct exports.
- `clean-render` removes derived outputs, never authored pages or media.
- Before final delivery run `finalize`, inspect its keep/remove list, then `finalize --apply`. Follow [delivery.md](references/delivery.md): retain canonical plans, PPTX and essential PPTD project assets, clear temporary work, and keep compact recovery metadata inside the canonical plan. Reusable operations belong in the Skill, not per-deck scripts.
- Long operations are expected. Keep the user informed, do not restart healthy exports just for silence, and report material failures rather than implying successful delivery.

## Global Skill Maintenance

Read the maintenance reference only for install/status/check/upgrade/switch/rollback. Use `scripts/install_global_skill.py` for installation and `scripts/update_global_skill.py` for maintenance of an installed copy. Preserve staged updates, rollback, the runtime environment, and shared Playwright cache. Do not replace an installation with `--force` as an update strategy. The installer bundles runtime and editor assets; it must not create a symlink back to this repository.

Natural-language public/stable channel requests map to `update_global_skill.py switch public`; private/internal requests map to `switch pptd`. This changes update source, not renderer availability. Follow the maintenance reference for authentication and rollback. Never collect credentials; authentication failure leaves the installation unchanged. After a successful switch report channel/commit and end the turn so the new instructions load next turn.

After installation, follow the README's mandatory global routing check. Global Agent instruction edits require permission.
