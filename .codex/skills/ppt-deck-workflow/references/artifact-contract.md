# Artifact Contract

## Files

`workflow-state.json`

- Tracks topic, audience, page request, provider, approvals, renderer, and final artifacts.
- This is the source of truth for approval state.

`outline.json`

- Plain JSON outline consumed by existing generation functions.
- Do not wrap it in metadata.

`outline-preview.md`

- Human-readable summary for Codex to show the user.

`contents.json`

- Plain mapping from slide title to generated material.
- If titles collide, edit carefully or regenerate with clearer page titles.

`contents-preview.md`

- Human-readable material review file.

`slide-plans.json`

- Contains renderer-neutral slide jobs.
- Shape:

```json
{
  "version": 1,
  "slides": [
    {
      "index": 1,
      "title": "...",
      "material": "...",
      "plan": "...",
      "page_role": "cover"
    }
  ]
}
```

`slide-plans-preview.md`

- Human-readable layout planning review file.

## Approval Invariant

The runner refuses to generate:

- `contents` until `outline` is approved
- `slide-plans` until `contents` is approved
- renderer output until `slide_plans` is approved

Use:

```bash
../.venv/bin/python -m ppt_workflow.runner approve --run-dir output/... --artifact outline
../.venv/bin/python -m ppt_workflow.runner approve --run-dir output/... --artifact contents
../.venv/bin/python -m ppt_workflow.runner approve --run-dir output/... --artifact slide_plans
```
