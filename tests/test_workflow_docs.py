from __future__ import annotations

import unittest
from pathlib import Path


class WorkflowDocsTests(unittest.TestCase):
    def test_multi_renderer_guidance_uses_same_run_directory(self) -> None:
        skill_path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "SKILL.md"
        )
        workflow_path = skill_path.parent / "references" / "workflow.md"

        skill_text = skill_path.read_text(encoding="utf-8")
        workflow_text = workflow_path.read_text(encoding="utf-8")

        self.assertIn("same run directory", skill_text)
        self.assertIn("output/<project>/html", skill_text)
        self.assertIn("same run directory", workflow_text)

    def test_render_job_guidance_mentions_subagents_and_prepare_command(self) -> None:
        skill_path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "SKILL.md"
        )
        contracts_path = skill_path.parent / "references" / "prompt-contracts.md"

        skill_text = skill_path.read_text(encoding="utf-8")
        contracts_text = contracts_path.read_text(encoding="utf-8")

        self.assertIn("prepare-render-jobs", skill_text)
        self.assertIn("subagent", skill_text)
        self.assertIn("Render Job Contract", contracts_text)


if __name__ == "__main__":
    unittest.main()
