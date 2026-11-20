# Clean delivery

The final run directory contains `outline.json`, `contents.json`, `slide-plans.json`, the requested `.pptx` exports, and, when applicable, `pptd/` with its manifest, authored pages and required local media/provenance. When the plan names original design references under `style-references/`, those images also belong to the reusable result. Do not add a second planning report, a README, an HTML image gallery, scripts or preview bundles unless the user requests that deliverable.

During work, keep prompt text, notes and temporary code under `.workflow/`. Helper-managed jobs, source images and QA outputs are temporary too. Prefer the bundled helpers for previews, page comparisons, export, validation and cleanup. When an operation recurs, improve the Skill implementation instead of copying a new Python script into every presentation. A one-off task-specific script, if actually necessary, stays in `.workflow/` and is removed after use.

Before finishing:

1. Complete authorized branches and agent visual checks; clear resolved `pending_work` in the task brief. Avoid exporting a succession of `v2`, `v3`, `final-final` files. Update the current named export; retain alternate versions only when requested. Keep IMG and PPTD exports distinct when both were requested.
2. Run `workflow.py finalize --run-dir <run>` to inspect retained files, temporary files and unclassified files. This checks PPTX integrity/count and local PPTD dependencies, not visual fidelity.
3. Run `workflow.py finalize --run-dir <run> --apply` to clean verified temporary files. This is part of delivery, not another user approval gate. Unknown files block deletion; classify them from evidence. For a confirmed agent-generated scratch file, add `--discard <relative-path>`. Never classify user inputs or requested deliverables as scratch. Paths cannot escape the run, traverse symlinks/junctions, or remove final dependencies.
4. Link only the requested final artifacts. No gallery or editor interaction is needed. Report actual editability and any real validation gap briefly.

Cleanup removes temporary state, prompt/job files, canonical Markdown previews and QA images. A compact `_delivery` object in `slide-plans.json` retains the task brief, export hashes and branch provenance, without a separate report. It is not visible slide copy. `resume` can inspect it after cleanup; do not pass it into image prompts.

Original IMG files are removed only when a retained IMG PPTX contains identical image bytes in matching order. If a requested later derivative needs those images, run:

```text
workflow.py restore-img --run-dir <run> --pptx <retained-img-pptx>
```

This recovers the embedded pixels without image generation, API usage or re-encoding. It refuses differing existing images. It does not reconstruct editable layers. Retain the image PPTX while building the derivative. For an explicitly requested standalone SVG or other extra artifact, pass `--keep <relative-path>` to preserve it; report the extra deliverable rather than deleting it to satisfy a default folder layout.
