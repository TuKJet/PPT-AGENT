from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from adapters.asset_repository import LocalAssetRepository
from adapters.template_repository import LocalTemplateRepository
from ai_client import AIClient
from vendor_landppt.design_engine import LandPPTDesignEngine
from vendor_landppt.image_engine import LandPPTImageEngine
from vendor_landppt.prompts import prompts_manager

logger = logging.getLogger(__name__)


class LandPPTHtmlGenerationService:
    """LandPPT-style HTML generation core adapted to PPT-AGENT pipeline inputs."""

    def __init__(
        self,
        client: AIClient,
        template_repository: LocalTemplateRepository | None = None,
        asset_repository: LocalAssetRepository | None = None,
        cache_dir: Path | None = None,
    ):
        self.client = client
        self.template_repository = template_repository or LocalTemplateRepository()
        self.asset_repository = asset_repository or LocalAssetRepository()
        self.design_engine = LandPPTDesignEngine(
            client=client,
            template_repository=self.template_repository,
            cache_dir=cache_dir,
        )
        self.image_engine = LandPPTImageEngine(client=client, asset_repository=self.asset_repository)

    def _strip_code_block(self, text: str) -> str:
        match = re.search(r"```html\s*(<!DOCTYPE html>.*?</html>)\s*```", text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"(<!DOCTYPE html>.*?</html>)", text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _extract_content_points(self, material: str) -> list[str]:
        lines = []
        for raw_line in material.splitlines():
            line = raw_line.strip().lstrip("-").lstrip("•").strip()
            if len(line) >= 4:
                lines.append(line)
        if not lines and material.strip():
            clauses = re.split(r"[。；;]\s*|\n+", material)
            lines = [clause.strip() for clause in clauses if len(clause.strip()) >= 4]
        return lines[:6] or [material.strip()[:120]]

    def _build_slide_data(
        self,
        title: str,
        material: str,
        plan: str,
        page_role: str,
    ) -> dict[str, Any]:
        return {
            "title": title,
            "description": plan[:220],
            "content_points": self._extract_content_points(material),
            "slide_type": page_role,
            "type": page_role,
            "page_role": page_role,
            "raw_material": material,
            "raw_plan": plan,
        }

    def _build_confirmed_requirements(self, deck_topic: str, audience: str, page_role: str) -> dict[str, Any]:
        return {
            "topic": deck_topic,
            "target_audience": audience,
            "description": f"当前通过 PPT-AGENT 复用 LandPPT 风格链路生成 {page_role} 页面",
            "scenario": "presentation",
            "ppt_style": "landppt-migrated",
        }

    def _summarize_all_slides(self, all_slides: list[dict[str, Any]] | None) -> str:
        if not all_slides:
            return ""
        lines = []
        for index, slide in enumerate(all_slides, start=1):
            title = str(slide.get("title") or slide.get("page_title") or f"第{index}页").strip()
            slide_type = str(slide.get("slide_type") or slide.get("type") or "").strip()
            line = f"{index}. {title}"
            if slide_type:
                line += f"（{slide_type}）"
            lines.append(line)
        return "\n".join(lines)

    def _build_richer_composition_block(self, page_role: str) -> str:
        role = (page_role or "content").strip().lower()
        lines = [
            "**Composition density upgrade (must follow)**",
            "- Avoid large empty regions with only a title block and a few generic cards.",
            "- Build one dominant visual anchor in the main content area plus one supporting cluster nearby.",
            "- If no real image asset is available, use abstract visuals such as gradient blobs, orbit lines, dashboard fragments, signal bars, icon groups, or metric chips.",
            "- Top-right elements must be composed as a corner cluster. Do not leave a single floating page tag by itself.",
            "- Corner cluster elements should share one alignment edge and consistent spacing. Avoid random corner ornaments with mismatched offsets.",
        ]
        if role == "cover":
            lines.extend(
                [
                    "- Cover pages must include a hero visual panel or abstract hero graphic, not just two plain panels.",
                    "- Cover pages must include one secondary support group such as metric chips, mini timeline, compact chart, or capability badges.",
                    "- If the written content is short, spend the spare space on composition quality instead of leaving the page hollow.",
                ]
            )
        elif role in {"toc", "summary", "ending"}:
            lines.extend(
                [
                    "- Summary-style pages must avoid a hollow center. Use one anchor block plus 2-4 compact supporting items.",
                    "- If content is short, fill space with grouped chips, mini metrics, or small structured visuals instead of isolated decoration.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Content pages still need one obvious anchor, even when the slide is mostly text or metrics.",
                    "- Keep support elements grouped near the main composition, not scattered into multiple corners.",
                ]
            )
        return "\n".join(lines)

    def generate_slide_html(
        self,
        deck_topic: str,
        title: str,
        material: str,
        plan: str,
        audience: str,
        page_role: str,
        page_number: int,
        total_pages: int,
        layout_feedback: str = "",
        all_slides: list[dict[str, Any]] | None = None,
    ) -> str:
        slide_data = self._build_slide_data(title=title, material=material, plan=plan, page_role=page_role)
        confirmed_requirements = self._build_confirmed_requirements(
            deck_topic=deck_topic or title,
            audience=audience,
            page_role=page_role,
        )
        template = self.design_engine.select_template(audience=audience, topic=deck_topic or title)
        project_key = self.design_engine.get_project_cache_key(deck_topic or title, audience)
        style_genes = self.design_engine.get_or_extract_style_genes(project_key, template.html_template, page_number)
        image_plan = self.image_engine.build_slide_image_plan(
            slide_data=slide_data,
            confirmed_requirements=confirmed_requirements,
            page_number=page_number,
            total_pages=total_pages,
            template_html=template.html_template,
        )
        slide_data["images_info"] = image_plan.collection.to_dict()
        slide_data["images_summary"] = image_plan.collection.get_summary_for_ai()
        unified_design_guide = self.design_engine.generate_unified_design_guide(
            slide_data=slide_data,
            page_number=page_number,
            total_pages=total_pages,
            confirmed_requirements=confirmed_requirements,
            all_slides=all_slides,
            template_html=template.html_template,
        )
        context_info = prompts_manager.get_slide_context_prompt(page_number, total_pages)
        prompt = prompts_manager.get_single_slide_html_prompt(
            slide_data=slide_data,
            confirmed_requirements=confirmed_requirements,
            page_number=page_number,
            total_pages=total_pages,
            context_info=context_info,
            style_genes=style_genes,
            unified_design_guide=unified_design_guide,
            template_html=template.html_template,
        )
        extra_blocks = [
            "",
            "**PPT-AGENT 迁移链路补充上下文**",
            f"- 页面角色：{page_role}",
            f"- 策划摘要：{plan[:600]}",
            f"- 素材摘要：{material[:800]}",
            f"- 全局目录摘要：{self._summarize_all_slides(all_slides)[:1200] or '未提供'}",
            "",
            "**图片/视觉素材策略**",
            image_plan.to_prompt_block(),
            "",
            self._build_richer_composition_block(page_role),
        ]
        if layout_feedback.strip():
            extra_blocks.extend(
                [
                    "",
                    "**本轮必须修复的布局问题**",
                    layout_feedback,
                    "- 优先减少列数、卡片数和装饰层级，而不是简单缩小所有字号。",
                    "- 先保证 header / main / footer 不重叠，再追求样式复杂度。",
                ]
            )
        final_prompt = prompt + "\n".join(extra_blocks)
        system_prompt = prompts_manager.get_html_generation_system_prompt()
        raw = self.client.chat(system_prompt, final_prompt, temperature=0.45)
        html = self._strip_code_block(raw)
        if not html.lower().startswith("<!doctype html"):
            raise ValueError("Migrated LandPPT HTML generation did not return a full HTML document")
        return html
