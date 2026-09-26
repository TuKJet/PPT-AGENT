# Workflow

Create one new run under `output/<project>/`. Keep all artifacts in the same run directory.

1. Outline → preview → explicit chat approval.
2. Contents → preview → explicit chat approval.
3. Version-2 slide plans → preview → explicit chat approval.
4. User chooses IMG or PPTD. Recommend IMG by default unless editability is the priority.
5. Load only the chosen branch guide. PPTD specifications must not be read before selection.
6. IMG: imagegen full-slide sources → original image PPTX.
7. PPTD: model-authored manifest/pages/media → validation → local browser editor → editable PPTX. The browser is started only for this branch.

HTML and standalone SVG renderers are removed from selection, jobs, and export. Legacy source files are not deleted by cleanup.

IMG-to-SVG remains an optional post-export derivative, separately authorized after IMG export. Do not ask the user to spend a reply declining it. Read its instructions only after opt-in; native SVG media is not a guarantee of semantic PowerPoint text/chart objects.

See the stage links in SKILL.md. No repository AI provider or runner is involved.
