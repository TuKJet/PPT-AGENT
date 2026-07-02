# PPT Deck Workflow Agent

For PPT generation work in this project, use the local `ppt-deck-workflow` skill.

Do not default to loading or using `superpowers` skills in this repository. Prefer the project-local `ppt-deck-workflow` skill and ordinary repo inspection unless the user explicitly asks for a `superpowers` skill or the task clearly requires some other non-project skill.

The intended interaction is Codex-driven, not Web-driven: generate common artifacts, ask the user for approval in chat, then choose HTML or SVG and render.

In this workspace, run workflow commands with `uv run python -m ppt_workflow.runner ...` from this directory.
