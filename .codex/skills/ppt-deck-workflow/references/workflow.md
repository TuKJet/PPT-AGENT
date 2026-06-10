# PPT Deck Workflow Reference

## Phase Model

The workflow has one public entry and two late renderer branches.

```text
common:
  outline -> contents -> slide_plans -> renderer_choice

renderer branches:
  html -> html validation/review/fix -> image PPTX -> editable PPTX
  svg  -> svg validation/review/fix  -> PPTX
```

The common phase must stay renderer-neutral. Do not ask the user to choose HTML or SVG until `slide-plans.json` exists and is approved.

## Recommended Codex Loop

1. Start with `outline`.
2. Read `outline-preview.md`.
3. Ask for approval or changes.
4. Approve `outline`.
5. Run `contents`.
6. Read `contents-preview.md`.
7. Ask for approval or changes.
8. Approve `contents`.
9. Run `plans`.
10. Read `slide-plans-preview.md`.
11. Ask for approval or changes.
12. Approve `slide_plans`.
13. Ask for renderer choice.
14. Run `choose-renderer`.
15. Run `render`.
16. Report final artifacts.

## Renderer Guidance

Recommend HTML by default when the user wants a deliverable deck, editable PPTX, or the most stable layout path.

Recommend SVG when the user wants lightweight source pages, quick visual drafts, or pure SVG artifacts.

## Resume Guidance

Use:

```bash
../.venv/bin/python -m ppt_workflow.runner status --run-dir output/...
```

Then continue from the first unapproved artifact:

- missing/unapproved outline: review or rerun `outline`
- approved outline but missing contents: run `contents`
- approved contents but missing slide plans: run `plans`
- approved slide plans but no renderer: ask renderer choice
- renderer chosen but incomplete: run `render`
