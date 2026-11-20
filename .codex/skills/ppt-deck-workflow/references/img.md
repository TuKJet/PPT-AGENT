# IMG Branch

Read only after the user chooses IMG. Use the imagegen skill's built-in `image_gen` tool by default for finished full-page images.

Follow the current brief and the image-tool choice in [SKILL.md](../SKILL.md). Verify the returned pixel dimensions before describing an image as native 4K. Record prompts and actual dimensions under `.workflow/`.

Calibrate internally on representative pages before a long batch, including a logic-heavy page and a distinct page role. Inspect density, diagram relationships and shared styling against the approved plan. Do not add a user approval gate or reuse a rejected earlier design as a reference. Regenerate only pages affected by a correction unless a shared change requires more.

## IMG Prompt Compilation

For the `img` branch, do not pass raw `slide-plans.json` text directly to imagegen. Treat each slide plan as source material and compile it into a clean image-generation prompt. After all images are generated, package them into the original IMG PPTX; that export completes the requested IMG workflow while leaving IMG-to-SVG available as a later explicit opt-in.

For each page, use the approved visible wording, spatial relationships and selected design system. Put the words to typeset in their own block. Turn design feedback into geometry, typography or color. For an annotated screenshot take the final layout from its markup.

For `plan.data_regions`, give imagegen the panel's position and dimensions and ask it to render a clean surface there. Supply the rest of the page as usual. At export the helper fills those panels from the approved rows. When the plan intentionally leaves the data for the PPTD version, `"img": "reserve"` keeps that panel empty in IMG. Reserve the same space in the style samples.

Save each generated page to the job's target path. Original artwork for managed data regions is kept temporarily under `.workflow/img-source/` so later renders can move a chart or change its data.

Export using `workflow.py export --run-dir output/<project>`. Read `slide-status-img.json` and deliver the original PPTX; this completes the IMG workflow.

Finish agent review and follow [delivery.md](delivery.md) before delivery. Original pixels remain recoverable from the IMG PPTX after cleanup. Do not generate an HTML slide viewer; native image previews in chat are sufficient.

Optional IMG-to-SVG Post-Export Opt-In: ask once whether the user wants an optional derivative, state additional model/Token usage and that PowerPoint can convert vector parts using its SVG tools. Do not present a decline option. Read [img-svg.md](img-svg.md) and [img-svg-prompt.md](img-svg-prompt.md) only after explicit opt-in. This remains a post-export derivative, not a renderer choice.

In the same post-export offer, describe editable PPTD as “文字和关键数据可编辑，复杂视觉裁剪保留，可独立移动、缩放，并支持本地网页编辑”. This is hybrid reconstruction by default; do not promise every visual's internal parts are editable. Both derivatives require additional model work; neither runs automatically. A prior explicit request for the derivative is sufficient authorization. For PPTD, use `choose-renderer --renderer pptd --source img`, then read [pptd.md](pptd.md) and [img-pptd.md](img-pptd.md). Keep the original IMG export available. Do not load either conversion guide while only producing IMG.
