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

    def test_slide_plan_contract_uses_canonical_structured_page_fields(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "references"
            / "prompt-contracts.md"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("free-form string in `plan`", text)
        for field in (
            '"core_message"',
            '"layout_structure"',
            '"visual_hierarchy"',
            '"required_elements"',
            '"palette_tokens"',
            '"style_controls"',
            '"audience_controls"',
            '"renderer_neutral_constraints"',
        ):
            self.assertIn(field, text)

        self.assertIn("smaller human-readable approval projection", text)
        self.assertIn("Never copy JSON objects", text)

    def test_img_svg_prompt_prioritizes_faithful_tracing_and_icons(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "references"
            / "prompt-contracts.md"
        )
        text = path.read_text(encoding="utf-8")

        self.assertIn("This is NOT a slide redesign", text)
        self.assertIn("sole and mandatory visual source of truth", text)
        self.assertIn("Pixel-level visual resemblance", text)
        self.assertIn("Every visible icon", text)
        self.assertIn("Never replace an original icon", text)
        self.assertIn("image_and_prompt_same_model_turn", text)
        self.assertIn("combined similarity", text)
        self.assertIn("complete `visible_text_inventory`", text)
        self.assertIn("Rasterized visible text is an automatic failure", text)
        self.assertIn("adjacent or overlapping crops", text)
        self.assertIn("`all_visible_text_editable`", text)
        self.assertIn("visual-element inventory", text)
        self.assertIn("Preserve icons, logos, illustrations", text)
        self.assertIn("lines, boxes, dividers, arrows, and simple geometry vector", text)


if __name__ == "__main__":
    unittest.main()
