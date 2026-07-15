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

    def test_img_svg_post_export_gate_is_documented_as_mandatory(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill_path = root / ".codex" / "skills" / "ppt-deck-workflow" / "SKILL.md"
        references = skill_path.parent / "references"

        skill_text = skill_path.read_text(encoding="utf-8")
        workflow_text = (references / "workflow.md").read_text(encoding="utf-8")
        contract_text = (references / "prompt-contracts.md").read_text(encoding="utf-8")

        self.assertIn("IMG-to-SVG Post-Export Gate", skill_text)
        self.assertIn("must not be asked earlier", skill_text)
        self.assertIn("next=ask-user-img-svg", workflow_text)
        self.assertIn("source_image_path` directly", contract_text)
        self.assertIn("must not rasterize", skill_text)


if __name__ == "__main__":
    unittest.main()
