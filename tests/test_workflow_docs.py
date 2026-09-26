from __future__ import annotations

import unittest
from pathlib import Path


class WorkflowDocsTests(unittest.TestCase):
    def test_progressive_reference_links_resolve(self) -> None:
        import re
        skill_root = Path(__file__).resolve().parents[1] / ".codex/skills/ppt-deck-workflow"
        text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        for link in re.findall(r"\]\((references/[^)]+)\)", text):
            self.assertTrue((skill_root / link).is_file(), link)
        # The entry point is a stage router, not a copy of the large schema.
        self.assertNotIn("interface ElementBase", text)
        self.assertNotIn("bounds: [", text)
        self.assertLess(len(text), 9000)
        self.assertIn("Only after user chooses PPTD", text)
        self.assertNotIn("pptd-format.md", (skill_root / "references/slide-plans.md").read_text())

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
