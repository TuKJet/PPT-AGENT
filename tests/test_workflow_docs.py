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

    def test_img_is_the_default_renderer_recommendation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill_root = root / ".codex" / "skills" / "ppt-deck-workflow"

        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        workflow_text = (skill_root / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        readme = (root / "README.md").read_text(encoding="utf-8")

        self.assertIn("Default recommendation: IMG", skill_text)
        self.assertIn("Recommend IMG by default", workflow_text)
        self.assertIn("`IMG`（默认推荐）", readme)
        self.assertNotIn("Recommend HTML by default", workflow_text)

    def test_img_svg_is_documented_as_optional_post_export_opt_in(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill_path = root / ".codex" / "skills" / "ppt-deck-workflow" / "SKILL.md"
        references = skill_path.parent / "references"

        skill_text = skill_path.read_text(encoding="utf-8")
        workflow_text = (references / "workflow.md").read_text(encoding="utf-8")
        contract_text = (references / "prompt-contracts.md").read_text(encoding="utf-8")
        img_svg_text = (references / "img-svg.md").read_text(encoding="utf-8")

        self.assertIn("Optional IMG-to-SVG Post-Export Opt-In", skill_text)
        self.assertIn("Do not present a decline option", skill_text)
        self.assertIn("additional model/Token", skill_text)
        self.assertIn("img-svg.md", skill_text)
        self.assertIn("native SVG media", skill_text)
        self.assertIn("Do not ask the user to spend a reply", workflow_text)
        self.assertIn("PowerPoint can convert much of the page into editable shapes", workflow_text)
        self.assertNotIn("next=ask-user-img-svg", workflow_text)
        self.assertIn("img-svg.md", contract_text)
        self.assertIn("img-svg-prompt.md", contract_text)
        self.assertIn("same vision-model turn", contract_text)
        self.assertIn("pending_visual_review", img_svg_text)
        self.assertIn("native SVG media", img_svg_text)

    def test_pillow_crop_contract_preserves_the_post_export_choice(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill_path = root / ".codex" / "skills" / "ppt-deck-workflow" / "SKILL.md"
        references = skill_path.parent / "references"

        skill_text = skill_path.read_text(encoding="utf-8")
        workflow_text = (references / "workflow.md").read_text(encoding="utf-8")
        contract_text = (references / "prompt-contracts.md").read_text(encoding="utf-8")
        img_svg_text = (references / "img-svg.md").read_text(encoding="utf-8")

        self.assertIn("optional post-export derivative", workflow_text)
        self.assertIn("Pillow", contract_text + img_svg_text)
        self.assertIn("Do not create layered SVG variants", contract_text + img_svg_text)
        self.assertIn("source crop", contract_text + img_svg_text)
        self.assertIn("version-4", img_svg_text)
        self.assertIn("optional", img_svg_text)
        self.assertNotIn("conversion_evidence_path", contract_text)
        self.assertNotIn("for every page", contract_text)

    def test_global_skill_installation_is_documented(self) -> None:
        root = Path(__file__).resolve().parents[1]
        readme = (root / "README.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        agent_init = (root / "AGENT_INIT.md").read_text(encoding="utf-8")
        skill = (
            root
            / ".codex"
            / "skills"
            / "ppt-deck-workflow"
            / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("install_global_skill.py", readme)
        self.assertIn("--bootstrap", readme)
        self.assertIn("--install-browser", readme)
        self.assertIn("update_global_skill.py", readme)
        self.assertIn("codex/all-logic-in-skills", readme)
        self.assertIn("--only-shell", readme)
        self.assertIn(".links", readme)
        self.assertIn("cache-compatible Playwright version", readme)
        self.assertIn("## Quick Use / 快速使用", readme)
        self.assertIn("使用 $ppt-deck-workflow", readme)
        self.assertIn("大纲预览 → 用户批准", readme)
        self.assertIn("$CODEX_HOME/skills/ppt-deck-workflow", readme)
        self.assertIn("## PowerPoint Skill Routing / PowerPoint Skill 路由", readme)
        self.assertIn("$CODEX_HOME/AGENTS.override.md", readme)
        self.assertIn("request the user's permission", agents)
        self.assertIn("must not silently edit global Agent instructions", agents)
        self.assertIn("Global Verification Checklist", agent_init)
        self.assertIn("PPT_AGENT_WORKSPACE", agent_init)
        self.assertIn("update_global_skill.py", agent_init)
        self.assertIn("Globally installed mode", skill)
        self.assertIn("Global Skill Maintenance", skill)
        self.assertIn("runtime/", skill)


if __name__ == "__main__":
    unittest.main()
