from __future__ import annotations

import unittest
from pathlib import Path


class PromptContractsAudienceTests(unittest.TestCase):
    def test_audience_controls_are_explicit_from_outline(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "references"
            / "prompt-contracts.md"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("Outline Audience And Style Contract", text)
        self.assertIn("technical", text)
        self.assertIn("management", text)
        self.assertIn("investor", text)
        self.assertIn("The outline must already reflect audience level", text)

    def test_leadership_restraint_does_not_collapse_visual_expression(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "references"
            / "prompt-contracts.md"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("restraint applies to information noise", text)
        self.assertIn("Do not infer a monochrome", text)
        self.assertIn("brand colors", text)
        self.assertIn("illustrations", text)

    def test_slide_plans_define_one_deck_level_design_system(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "references"
            / "prompt-contracts.md"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("one deck-level `design_system`", text)
        self.assertIn("palette tokens", text)
        self.assertIn("must not invent a new page palette", text)


if __name__ == "__main__":
    unittest.main()
