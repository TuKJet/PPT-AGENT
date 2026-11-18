# IMG Branch

Read only after the user chooses IMG. Use the imagegen tool to generate finished full-page images.

Read the task brief before choosing an image tool or making paid calls. A newer instruction to use the default tool during debugging overrides an earlier 4K request within that scope. When native 4K is currently requested, follow the available imagegen skill's supported API workflow, load credentials only into that process from the user's external secret store, and verify returned dimensions. Never label upscaled or lower-resolution images as native 4K. Persist prompts and actual dimensions under `.workflow/`, not extra project-root reports.

Calibrate internally on representative pages before a long batch, including a logic-heavy page and a distinct page role. Inspect density, diagram relationships and shared styling against the approved plan. Do not add a user approval gate or reuse a rejected earlier design as a reference. Regenerate only pages affected by a correction unless a shared change requires more.

## IMG Prompt Compilation

Run `prepare-render-jobs`. Use the page job's `on_screen` and declared data for visible wording. A legacy version-2 job uses the visible copy approved in its plan.

Compile one 16:9 page. Describe the composition, reading order, chart or diagram structure, whitespace, palette and typography in visual terms. Use a clean reference image where appropriate. Inspect the rendered page for legible text, accurate data and the intended composition.


Export using `workflow.py export --run-dir output/<project>`. Read `slide-status-img.json` and deliver the original PPTX; this completes the IMG workflow.

Finish agent review and follow [delivery.md](delivery.md) before delivery. Original pixels remain recoverable from the IMG PPTX after cleanup. Do not generate an HTML slide viewer; native image previews in chat are sufficient.

Optional IMG-to-SVG Post-Export Opt-In: ask once whether the user wants an optional derivative, state additional model/Token usage and that PowerPoint can convert vector parts using its SVG tools. Do not present a decline option. Read [img-svg.md](img-svg.md) and [img-svg-prompt.md](img-svg-prompt.md) only after explicit opt-in. This remains a post-export derivative, not a renderer choice.

In the same post-export offer, describe editable PPTD as “文字和关键数据可编辑，复杂视觉裁剪保留，可独立移动、缩放，并支持本地网页编辑”. This is hybrid reconstruction by default; do not promise every visual's internal parts are editable. Both derivatives require additional model work; neither runs automatically. A prior explicit request for the derivative is sufficient authorization. For PPTD, use `choose-renderer --renderer pptd --source img`, then read [pptd.md](pptd.md) and [img-pptd.md](img-pptd.md). Keep the original IMG export available. Do not load either conversion guide while only producing IMG.
