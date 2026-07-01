# PPT Deck Workflow Reference

Current branch note: the public Python runner is removed. Use `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...`; Codex generates content and renderer source files directly.

## Phase Model

The workflow has one skill helper and three late renderer branches.

```text
common:
  outline -> contents -> slide_plans -> renderer_choice

renderer branches:
  html -> review_choice(optional) -> Codex-authored HTML files -> render_review(optional) -> image PPTX -> editable PPTX attempt
  svg  -> review_choice(optional) -> Codex-authored SVG files  -> render_review(optional) -> PPTX
  img  -> Codex imagegen full-slide images -> PPTX
```

The common phase must stay renderer-neutral. Do not ask the user to choose `html`, `svg`, or `img` until `slide-plans.json` exists and is approved.

## Recommended Codex Loop

1. Run the helper `init` command.
2. Read `prompt-contracts.md`.
3. Generate `outline.json`, then run helper `preview --artifact outline`.
4. Ask for approval or changes.
5. Approve `outline`.
6. Generate `contents.json`, then run helper `preview --artifact contents`.
7. Ask for approval or changes.
8. Approve `contents`.
9. Generate `slide-plans.json`, then run helper `preview --artifact slide_plans`.
10. Ask for approval or changes.
11. Approve `slide_plans`.
12. Ask for renderer choice.
13. Run helper `choose-renderer`.
14. If renderer is `html` or `svg`, ask whether to enable render review. Default recommendation: `off`.
15. Run helper `choose-review`.
16. For long or dense `html`/`svg` decks, optionally materialize renderer job files with `prepare-render-jobs`, then let subagents create the per-page renderer source files.
17. Codex creates the renderer source files using `prompt-contracts.md`.
18. If render review is `on`, run the Codex-side screenshot review and repair subflow, then helper `complete-review`.
19. If you need to clear stale derived outputs, run helper `clean-render`, then create or verify the renderer source files for that branch, then `export`.
20. Report final artifacts.

## Renderer Guidance

Recommend HTML by default when the user wants a deliverable deck, editable PPTX attempt, or the most stable layout path.

Recommend SVG when the user wants lightweight source pages, quick visual drafts, or pure SVG artifacts. Recommend IMG for polished full-page visuals when editability is not required.

## Resume Guidance

Use:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py status --run-dir output/...
```

Then continue from the first unapproved artifact:

- missing/unapproved outline: generate or revise `outline.json`
- approved outline but missing contents: generate `contents.json`
- approved contents but missing slide plans: generate `slide-plans.json`
- approved slide plans but no renderer: ask renderer choice
- `html` or `svg` chosen but review choice pending: confirm `off` or `on`
- render review enabled but incomplete: finish the Codex review subflow, then run helper `complete-review`
- renderer chosen and ready: create renderer files, then run helper `export`

## Multi-Renderer Compare Guidance

When one approved deck needs multiple renderer outputs for comparison:

1. Keep the comparison in the same run directory under `output/<project>/`.
2. Store renderer source files in sibling subdirectories of that same run directory, such as `output/<project>/html`, `output/<project>/svg`, and `output/<project>/img`.
3. Export renderer deliverables with distinct filenames so one renderer never overwrites another renderer's PPTX or status snapshot.
4. Use `clean-render` only to remove derived outputs such as editable exports, review files, `slide-status.json`, and prior `.pptx` files; it is not a renderer-source wipe in this Codex-authored branch.
5. Create separate run directories only when the user explicitly asks for isolated renderer branches.

## Render Jobs And Subagents

Use renderer job files when the main agent should coordinate the deck while subagents own page-local generation work.

1. After `slide_plans` is approved, choose the renderer and, for `html` or `svg`, prepare the renderer jobs:

```bash
uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py prepare-render-jobs --run-dir output/... --renderer html
```

2. Read `render-jobs/<renderer>/shared-context.json` once in the main agent.
3. Dispatch one subagent per `render-jobs/<renderer>/slide-xx.json`.
4. Each subagent writes only its own renderer source file into the same run directory.
5. The main agent reviews the set, runs any screenshot-review loop, and sends only failed pages back for repair.
