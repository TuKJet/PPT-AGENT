# PPT Deck Workflow Agent

For PPT generation work in this project, use the local `ppt-deck-workflow` skill.

The intended interaction is Codex-driven: Codex generates common artifacts, asks the user for approval in chat, then chooses HTML, SVG, or IMG and exports.

In this workspace, run deterministic workflow helper commands with `uv run python -u .codex/skills/ppt-deck-workflow/scripts/workflow.py ...` from this directory. Do not use `ppt_workflow.runner` or repository AI provider code.

For optional post-export IMG-to-SVG conversion, preserve the existing user choice gate, then generate one final SVG per source IMG. Use the bundled Pillow crop helper for incompatible icons/logos and do not create layered SVG variants.

When asked to install this capability globally, use `scripts/install_global_skill.py` from the skill folder. The installed skill must carry its own `runtime/` and use the caller's current workspace for `output/`; do not create a symlink back to this repository.

When asked to check, upgrade, inspect, or roll back an installed global copy, use `scripts/update_global_skill.py`. The recorded default source is `https://github.com/TuKJet/PPT-AGENT.git`, branch `codex/all-logic-in-skills`. Use its staged update path; do not replace the installation with `--force`, merge into the live Skill, or delete its `.venv` or shared Playwright browser cache.
