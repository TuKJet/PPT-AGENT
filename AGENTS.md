# PPT Deck Workflow Agent

For PPT generation work in this project, use the local `ppt-deck-workflow` skill.

The intended interaction is Codex-driven: Codex generates common artifacts, asks the user for approval in chat, then chooses HTML, SVG, or IMG and exports.

In this workspace, run deterministic workflow helper commands with `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...` from this directory. Do not use `ppt_workflow.runner` or repository AI provider code.
