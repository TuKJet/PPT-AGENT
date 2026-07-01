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


if __name__ == "__main__":
    unittest.main()
