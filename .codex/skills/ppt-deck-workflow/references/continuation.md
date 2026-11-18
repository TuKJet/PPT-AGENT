# Resumption and corrections

Run `workflow.py resume --run-dir <run>` at the start of a continued task, after context compaction or a model change, and before delegating pages. Read the current canonical artifact and only the selected stage/renderer guide. Do not replay completed stages or reselect an already chosen renderer just because conversation context is shorter.

Maintain one compact `.workflow/task-brief.json` through `checkpoint --run-dir <run> --file <file>`. The input can be that same file; no extra report is needed. Supported fields:

```json
{
  "objective": "Explain the design choices and their evidence",
  "constraints": [
    "Content pages: medium density through diagrams and evidence, not paragraph volume",
    "During debugging: use the default image tool; no paid 4K generation",
    "All pages: retain the calibrated palette and use the approved plain footer"
  ],
  "source_paths": ["docs/design-overview.md#design-choices"],
  "pending_work": ["Repair the feedback connection on page 8"],
  "next_action": "Update page 8 in slide-plans.json, then regenerate only that page"
}
```

`objective`, `constraints`, `source_paths` and `pending_work` are required; the lists can be empty. `next_action` is optional. Record each correction as the desired final state with its scope. Source references point to evidence files or sections. Keep credentials out of the brief.

`checkpoint` preserves chat authorization; it does not confer new permission. New-deck stage approvals still apply. A precise request to repair an existing page and export authorizes that scoped repair; do not turn it into another whole-deck approval cycle. Record a fresh preview/approval for the changed artifact only when supported by that request. Broad replanning still follows the relevant checkpoints unless the user explicitly bypasses them. Previously approved unrelated content stays intact.

Each page worker uses the current projected job, shared system and any approved reference image. The author checks operational constraints in the brief separately. Assign exact page ownership and preserve unrelated/manual edits. Refresh jobs after a correction so their source hashes match.

For a cleaned delivery, `resume` reads `_delivery` in `slide-plans.json` and verifies the retained file hashes. This is delivery provenance, not a fresh approval. For a subsequent authorized revision, regenerate the needed preview from the canonical artifact and record the scoped approval. Do not `init` over the existing deck. If original IMG files are needed for a derivative, use the bundled `restore-img` helper described in [delivery.md](delivery.md).
