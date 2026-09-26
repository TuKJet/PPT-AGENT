### Final-State Revision Contract

Apply this contract whenever an existing outline, content artifact, or slide plan receives a second or later user change.

Treat the user's change request as a transient delta. The persisted artifact must describe only the desired final slide, not how it differs from an earlier version.

- Rewrite affected fields instead of appending correction notes.
- Keep accepted content and the new final geometry; discard superseded alternatives and rejected wording.
- Make `required_elements` an allowlist of exact final visible copy and objects. A deleted object or string must not remain in this list.
- Do not store revision verbs or tombstones such as `delete`, `remove`, `omit`, `do not show`, `must not appear`, `不要出现`, `删除`, `去掉`, or `不保留` when they refer to content from the previous version.
- Do not quote the rejected literal inside a negative instruction. Mentioning a removed label again still gives it prompt attention and can cause it to reappear.
- Express the destination positively and spatially. Bad: `delete the old card and do not show its label`. Good: `keep this interval as clean background space; join the remaining modules with one short connector`.
- Keep generic safety and truthfulness constraints only when they remain useful without knowledge of the revision history, for example no invented metrics, no external brand logo, and exact required numbers.
- If the user supplies an annotated screenshot, extract the accepted layout and final-state geometry into the plan. Do not transcribe cross marks, comments, rejected labels, or deletion instructions into the plan.

Before generating `slide-plans-preview.md` or render jobs, audit the changed slide object:

1. List the literals and objects the user rejected in working memory only.
2. Search `material`, `core_message`, `layout_structure`, `visual_hierarchy`, `required_elements`, `style_controls`, `audience_controls`, and `renderer_neutral_constraints` for those literals.
3. If a rejected literal survives only in a negated or historical sentence, remove that sentence and replace it with a positive final-state description.
4. Confirm the preview contains no edit history and reads as if this were the first and only design specification.
5. Prepare renderer jobs only from this clean artifact.

