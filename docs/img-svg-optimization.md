# IMG→SVG optimization

Approved scope: simplify conversion protocol and prompts, allow faithful vector or crop
choices, make visual review a normal state, reuse unchanged previews, and bind native
SVG export to reviewed files. Preserve staged approvals, opt-in conversion, one final
SVG per source image, existing projects and the original IMG PPTX. No new dependencies.

## Implementation order

1. Run existing tests and add regressions for changed-file export, page mapping,
   optional crops, review cache and crop structure before modifying production code.
2. Remove model self-attestation and full artwork inventories; use one prompt source,
   lightweight text checks and optional crop manifests. Keep backplate repair opt-in.
3. Centralize reviewed-file checks at export; retain source/SVG hashes and page order.
   Make similarity and crop size diagnostics rather than acceptance thresholds.
4. Consolidate state normalization and documentation; keep legacy project reads.
5. Run focused and full tests, native SVG export and representative image checks.

## Compatibility classification

- Legacy renderer state and IMG opt-out: grounded compatibility; preserve tests.
- Repeated state normalization: duplication; share one normalization function.
- XML parse failures returning empty inventories: masking fallback; parse errors must
  remain visible at the SVG boundary.
- Model-written evidence flags: self-attestation, not execution evidence; remove.
- Crop dimensions, area and score thresholds: quality heuristics; report diagnostics.
- Backplate scrubbing: bounded repair tool; preserve its algorithm and inspect output.

## Validation record

- Baseline: 35 workflow helper tests passed before production changes.
- Implementation complete; final full suite: 85/85 passed in 159.088 seconds.
- The sample comparison must distinguish real model regeneration from deterministic
  replay of existing SVGs; do not claim Token or visual quality gains from replay.

## Implementation result — 2026-09-10

- Removed conversion self-attestation, required artwork inventories, per-page prompt
  copies and crop files on vector-only pages. Prompt source is `references/img-svg-prompt.md`.
- Added occurrence-aware text matching, optional V4 crop declarations and normal pending
  visual review. Area and similarity are diagnostics, not automatic quality verdicts.
- Unchanged previews are reused. Source/SVG/text/crop/preview/environment changes invalidate
  the affected review; native SVG export checks current page mapping and reviewed hashes.
- Crop declarations now check unique IDs, finite coordinates, actual embedded geometry and
  backplate text replacement. Native PPTX checks slide relationships and submitted SVG order.
- Kept legacy job reads, IMG opt-in/opt-out semantics, original source files, staged approvals
  and the backplate algorithm. No dependencies or model-specific branches were added.
- `workflow.py`: 2595 → 1877 lines; `SKILL.md`: 542 → 393 lines;
  `prompt-contracts.md`: 620 → 465 lines. New IMG→SVG reference files contain the extracted contract.

### Verification and limits

- Baseline 35 workflow tests passed before changes; new regression tests first demonstrated
  stale SVG/source and extra-page export failures in the old implementation.
- Focused final checks: 26 documentation/prompt/protocol tests passed.
- Full final check: `uv run python -m unittest discover -s tests -q` — 85 tests passed.
  Raw log: `output/img-svg-optimization-verification-20260909/tests-final.log`.
- Syntax compilation and `git diff --check` passed. The project has no configured lint,
  typecheck or security-scan tool; no such tool was installed or claimed to pass.
- Six historical PNG/SVG pairs passed new structural validation without changing source bytes.
  First preview render took 11.025 seconds (6 renders); cached replay took 0.242 seconds
  (0 renders), excluding environment fingerprint discovery and model generation.
- Native export contained six slides and six SVG media items. Desktop PowerPoint opened it
  read-only and exported six valid 1280×720 PNGs. Only the verification presentation was closed;
  the user's existing PowerPoint session was left running.
- All six historical SVGs have visual defects and remain failed visual reviews. The exported
  verification deck is technical-only. These failures are pre-existing, not changed model output.
- Controlled Astra old/new regeneration A/B, Token metering and a photo-dominant real sample
  remain unverified. The implemented freedom to trace artwork is tested structurally; this
  report does not establish model-generation quality improvement or quality non-regression.

Detailed replay evidence: `output/img-svg-optimization-verification-20260909/validation.md`.
