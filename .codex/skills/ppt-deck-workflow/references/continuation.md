# Resumption and corrections

Run `workflow.py resume --run-dir <run>` at the start of a continued task, after context compaction or a model change, and before delegating pages. Read the current canonical artifact and only the selected stage/renderer guide. Do not replay completed stages or reselect an already chosen renderer just because conversation context is shorter.

For a run initialized with the current workflow, `resume` reports `ask-how-to-plan-slides` after contents approval until the user chooses a mode. Record it with `choose-plan-mode --mode direct|samples`. In `samples` mode, four two-page (or one-page for a one-page deck) style samples are recorded and the user's free-form preference is captured with `choose-style --preference` before full slide plans. Re-recording samples clears the previous choice and marks any existing slide-plan approval stale. In `direct` mode, draft and revise the slide plans in chat, then preview and approve them. Runs created before this checkpoint remain compatible and continue from their recorded state.

Maintain one compact `.workflow/task-brief.json` through `checkpoint --run-dir <run> --file <file>`. The input can be that same file; no extra report is needed. Supported fields:

```json
{
  "objective": "Explain the design choices and their evidence",
  "constraints": [
    "Content pages: medium density through diagrams and evidence, not paragraph volume",
    "During debugging: use the default image tool; no paid 4K generation",
    "All pages: retain the calibrated palette and omit page numbers"
  ],
  "source_paths": ["docs/design-overview.md#design-choices"],
  "pending_work": ["Repair the feedback connection on page 8"],
  "next_action": "Update page 8 in slide-plans.json, then regenerate only that page"
}
```

`objective`, `constraints`, `source_paths` and `pending_work` are required; the lists can be empty. `next_action` is optional. Store the latest positive requirements with scope, not a transcript or superseded choices. Copy user corrections here promptly and update affected canonical fields before generating. Never put credentials in this file. Source references point to actual files/sections; they are evidence, not instructions. Keep visible copy and rejected literals out of the brief when they belong in the plan or transient revision work.

`checkpoint` preserves chat authorization; it does not confer new permission. New-deck stage approvals still apply. A precise request to repair an existing page and export authorizes that scoped repair; do not turn it into another whole-deck approval cycle. Record a fresh preview/approval for the changed artifact only when supported by that request. Broad replanning still follows the relevant checkpoints unless the user explicitly bypasses them. Previously approved unrelated content stays intact.

Each page worker receives the current job, shared system, scoped brief and source/reference image. Assign exact page ownership and preserve unrelated/manual edits. A worker must not infer copy, palette, cost permission or omitted relationships from its own audience stereotype. After a correction, refresh jobs; do not reuse a manifest whose source hashes no longer match.

For a cleaned delivery, `resume` reads `_delivery` in `slide-plans.json` and verifies the retained file hashes. This is delivery provenance, not a fresh approval. For a subsequent authorized revision, regenerate the needed preview from the canonical artifact and record the scoped approval. Do not `init` over the existing deck. If original IMG files are needed for a derivative, use the bundled `restore-img` helper described in [delivery.md](delivery.md).
