# PPT workflow usage review and implementation plan

Source: [制作工程管理层汇报PPT](codex://threads/01a1a5e2-5ce9-7550-8124-d0998f92f3fc), reviewed 2026-11-05. Review used the chat and its local rollout when an oversized turn exceeded the chat reader limit. Credentials and private experiment contents are excluded from this report.

## Observed failures

| Evidence from user feedback | Engineering response |
| --- | --- |
| Design logic and architecture diagrams were repeatedly omitted while usage logic dominated. | Source-to-slide coverage and diagram relationships must survive audience adaptation. |
| Density swung between sparse cards and long text; cover and contents disappeared during a rewrite. | Replace rigid role caps with semantic density guidance; preserve page roles unless a requested change affects them. |
| Purple styling required repeated correction; audience labels appeared as visible copy. | Persist current style and copy constraints, with explicit scope; keep audience intent outside visible copy. |
| Revisions were presented through separate planning reports rather than the official slide-plan preview. | One canonical outline, contents and slide-plans file; previews are generated projections only. |
| The user stopped paid 4K generation during debugging. | Persist the latest tool/cost constraint and verify actual image dimensions; do not infer authorization from an older request. |
| IMG-to-PPTD lost labels, node identity, feedback arrows and split/merge relationships, despite a claimed review. | Validate supported line syntax and compare relation completeness as well as text and appearance. |
| User reports excessive scripts, intermediate files and HTML viewers in output folders. | Bundle reusable operations; isolate temporary work; finalize to canonical planning JSON, PPTX and necessary PPTD sources/media. |
| User rejects editor/Computer Use handoffs for routine PPTD output. | Direct CLI export is the default; background rendering is agent QA, and the interactive editor is explicit opt-in. |

The recorded conversation used Astra and 6.1 Sol and contains multiple context compactions. This establishes the operating conditions, not that one model or compaction alone caused a particular defect. Several failures also have direct support in the current code: boolean-only approvals, unversioned render inputs and state-version inconsistency.

## Change plan and acceptance

1. Lock current behavior with the existing regression suite, then add targeted failing cases for stale approvals, edited plans, obsolete jobs and unsupported arrow fields.
2. Bind approvals/jobs to content hashes; provide a compact resume view and durable task constraints, without introducing a new approval gate.
3. Correct content, density, palette, revision and reconstruction guidance. Keep renderer instructions progressively loaded and keep user-approved choices across resumption.
4. Add reusable source/render comparison and safe delivery cleanup. Do not generate parallel planning reports or HTML image viewers by default. Keep manual inputs and unrelated files safe; unknown files must be surfaced rather than silently deleted.
5. Verify targeted tests, full regression, clean-output behavior and an independent resumption/revision scenario. Do not claim new model or visual-quality acceptance solely from unit tests.

Existing untracked scratch files in this repository belong to earlier work and are not part of this change. This task changes the engineering source; it does not silently replace the installed global Skill or modify the referenced presentation.

## Implementation

- Added `checkpoint`, `resume`, `compare-pptd`, `finalize`, and `restore-img` to the deterministic helper. Page jobs carry the current scoped brief and verified source fingerprints. Approval hashes, upstream invalidation, contiguous page identities and empty-run initialization are enforced.
- Finalization checks export freshness, PPTX structure/page count and PPTD dependencies before deleting known temporary files. It refuses unknown files and links/junctions. Required source pixels can be recovered byte-for-byte from the retained IMG PPTX. Compact delivery metadata lives in the canonical plan, not an extra report.
- Replaced fixed density caps that discarded diagram structure with source- and role-aware guidance. Revision/palette/source-coverage guidance now preserves design mechanisms, page roles and canonical planning files.
- Added strict PPTD line/arrow validation and image comparison output with pending-review status. Chinese YAML input/output encoding in the Node→Python bridge is now explicitly UTF-8, fixing a Windows locale failure uncovered by the real-export regression.
- Updated local/global-use documentation to direct PPTD export without a user editor handoff. Global installation/update logic remains staged; the installed global Skill is not changed by this engineering task.

Unit/integration tests verify workflow and file behavior. They do not prove that either model will always maintain visual quality after arbitrary future compactions; that remains a realistic-deck acceptance check.

## Verification — 2026-11-05

- Full regression: **123 tests, 121 passed, 2 skipped, no failures** (417.340 seconds). The skipped checks require Windows symbolic-link privileges; traversal rejection and other path checks still ran.
- The independent forward scenario produced real IMG and native PPTD PPTX exports, checked Chinese text and arrow endpoints in OOXML, finalized the directory to the intended files, recovered identical IMG bytes and detected a changed delivered PPTX. It did not start the interactive editor. Its background QA call was mocked; the separate real-editor image-export regression passed against the bundled renderer.
- Global self-contained installation and export checks passed. No actual global installation was changed; the tests use temporary copies.
- Skill validation, Python syntax parsing, Node syntax checking and diff whitespace checks passed. No dependency was added and no paid image generation was performed.
