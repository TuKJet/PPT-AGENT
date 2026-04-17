from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from adapters.template_repository import LocalTemplateRepository, TemplateRecord
from ai_client import AIClient
from vendor_presentation_core.models import build_project_cache_key, ensure_directory
from vendor_presentation_core.prompts import prompts_manager

logger = logging.getLogger(__name__)


class MigratedDesignEngine:
    """Migrated design-side logic adapted for PPT-AGENT."""

    def __init__(
        self,
        client: AIClient,
        template_repository: LocalTemplateRepository | None = None,
        cache_dir: Path | None = None,
    ):
        self.client = client
        self.template_repository = template_repository or LocalTemplateRepository()
        self.cache_dir = ensure_directory(cache_dir or (Path(__file__).resolve().parent.parent / ".ppt_agent_cache"))
        self.style_cache_dir = ensure_directory(self.cache_dir / "style_genes")
        self.template_cache_dir = ensure_directory(self.cache_dir / "templates")
        self._cached_style_genes: dict[str, str] = {}

    def select_template(self, audience: str, topic: str, prefer_dark: bool | None = None) -> TemplateRecord:
        return self.template_repository.get_default_template(audience=audience, topic=topic, prefer_dark=prefer_dark)

    def extract_html_from_response(self, response_content: str) -> str:
        patterns = [
            r"```html\s*(<!DOCTYPE html>.*?</html>)\s*```",
            r"```html\s*(<html.*?</html>)\s*```",
            r"(<!DOCTYPE html>.*?</html>)",
            r"(<html.*?</html>)",
        ]
        for pattern in patterns:
            match = re.search(pattern, response_content, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        content_stripped = response_content.strip()
        if content_stripped.lower().startswith("<!doctype html") and content_stripped.lower().endswith("</html>"):
            return content_stripped
        return content_stripped

    def validate_html_template(self, html_content: str) -> bool:
        if not html_content or not html_content.strip():
            return False
        html_lower = html_content.lower().strip()
        if not html_lower.startswith("<!doctype html"):
            return False
        if "</html>" not in html_lower:
            return False
        for token in ("<head", "<body", "<title"):
            if token not in html_lower:
                return False
        return True

    def generate_template_with_ai(
        self,
        prompt: str,
        template_name: str,
        description: str = "",
        tags: list[str] | None = None,
        persist: bool = False,
    ) -> dict[str, Any]:
        user_prompt = f"""
你是专业的 PPT 母版设计师。请基于以下要求生成一个 1280x720 的完整 HTML 母版模板。

模板名：{template_name}
模板描述：{description}
设计要求：{prompt}

输出要求：
1. 直接返回完整 HTML，必须从 <!DOCTYPE html> 开始。
2. 必须包含 header / main / footer 结构。
3. 必须内联 CSS。
4. 页眉和页脚要具备稳定的品牌识别结构，适合作为后续单页生成的参考模板。
"""
        raw = self.client.chat(prompts_manager.get_html_generation_system_prompt(), user_prompt, temperature=0.55)
        html_template = self.extract_html_from_response(raw)
        if not self.validate_html_template(html_template):
            raise ValueError("AI generated template failed validation")

        record: TemplateRecord | None = None
        if persist:
            record = self.template_repository.save_generated_template(
                template_name=template_name,
                description=description,
                html_template=html_template,
                tags=tags or ["generated"],
            )
        style_config = self.extract_style_config(html_template)
        return {
            "template_name": template_name,
            "description": description,
            "html_template": html_template,
            "style_config": style_config,
            "saved_template_id": record.template_id if record else None,
        }

    def extract_style_config(self, html_content: str) -> dict[str, Any]:
        style_config: dict[str, Any] = {
            "dimensions": "1280x720",
            "aspect_ratio": "16:9",
            "framework": "HTML + CSS",
        }
        colors = re.findall(r"(?:background|color)[^:]*:\s*([^;]+)", html_content, re.IGNORECASE)
        fonts = re.findall(r"font-family[^:]*:\s*([^;]+)", html_content, re.IGNORECASE)
        if colors:
            style_config["colors"] = list(dict.fromkeys(color.strip() for color in colors[:10]))
        if fonts:
            style_config["fonts"] = list(dict.fromkeys(font.strip() for font in fonts[:5]))
        if "tailwind" in html_content.lower():
            style_config["framework"] = "Tailwind CSS"
        return style_config

    def _extract_fallback_style_genes(self, template_html: str) -> str:
        genes: list[str] = []
        colors = re.findall(r"(?:background|color)[^:]*:\s*([^;]+)", template_html, re.IGNORECASE)
        fonts = re.findall(r"font-family[^:]*:\s*([^;]+)", template_html, re.IGNORECASE)
        paddings = re.findall(r"padding[^:]*:\s*([^;]+)", template_html, re.IGNORECASE)
        if colors:
            genes.append(f"- 核心色彩：{', '.join(list(dict.fromkeys(color.strip() for color in colors[:3])))}")
        if fonts:
            genes.append(f"- 字体系统：{fonts[0].strip()}")
        if "display: grid" in template_html:
            genes.append("- 布局方式：Grid 网格布局")
        elif "display: flex" in template_html:
            genes.append("- 布局方式：Flex 弹性布局")
        design_elements = []
        if "border-radius" in template_html:
            design_elements.append("圆角卡片")
        if "box-shadow" in template_html:
            design_elements.append("柔和投影")
        if "gradient" in template_html:
            design_elements.append("渐变背景")
        if design_elements:
            genes.append(f"- 设计元素：{', '.join(design_elements)}")
        if paddings:
            genes.append(f"- 间距模式：{paddings[0].strip()}")
        if not genes:
            genes.extend(
                [
                    "- 使用现代简洁的演示设计风格",
                    "- 保持页眉页脚稳定一致",
                    "- 通过大标题、卡片层级和留白建立视觉秩序",
                ]
            )
        return "\n".join(genes)

    def extract_style_genes(self, template_html: str) -> str:
        try:
            prompt = prompts_manager.get_style_genes_extraction_prompt(template_html)
            result = self.client.chat(
                "你是专业的 PPT 视觉分析师，负责从模板代码中提炼稳定可复用的设计基因。",
                prompt,
                temperature=0.2,
            )
            cleaned = result.strip()
            if len(cleaned) >= 50:
                return cleaned
        except Exception as exc:
            logger.warning("AI style gene extraction failed: %s", exc)
        return self._extract_fallback_style_genes(template_html)

    def get_or_extract_style_genes(self, project_key: str, template_html: str, page_number: int) -> str:
        default_genes = (
            "- 使用现代简洁的演示设计风格\n"
            "- 保持页眉页脚和卡片语言的一致性\n"
            "- 通过清晰的标题层级和适度留白维持阅读节奏"
        )
        if not template_html.strip():
            return default_genes

        project_cache_key = project_key or f"page_{page_number}"
        if project_cache_key in self._cached_style_genes:
            return self._cached_style_genes[project_cache_key]

        cache_file = self.style_cache_dir / f"{project_cache_key}_style_genes.json"
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text(encoding="utf-8"))
                style_genes = cache_data.get("style_genes", default_genes)
                self._cached_style_genes[project_cache_key] = style_genes
                return style_genes
            except Exception as exc:
                logger.warning("Failed to read style gene cache: %s", exc)

        try:
            style_genes = self.extract_style_genes(template_html)
        except Exception:
            style_genes = default_genes

        self._cached_style_genes[project_cache_key] = style_genes
        cache_file.write_text(
            json.dumps(
                {
                    "project_key": project_cache_key,
                    "style_genes": style_genes,
                    "template_hash": hashlib.md5(template_html.encode("utf-8")).hexdigest()[:8],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return style_genes

    def _generate_fallback_unified_guide(
        self,
        slide_data: dict[str, Any],
        page_number: int,
        total_pages: int,
    ) -> str:
        title = slide_data.get("title", "")
        slide_type = slide_data.get("slide_type", "content")
        guides = [
            "**A. 页面定位与视觉主张**",
            "- 保持页眉和页脚的模板识别度，主内容区根据信息密度动态伸缩。",
            "- 使用 1 个主视觉焦点、1 个次级信息区，避免多个同等级焦点抢占注意力。",
        ]
        if page_number == 1:
            guides.extend(
                [
                    "- 首页面需要建立封面级冲击力：标题更大，留白更多，辅助信息只保留一句短说明。",
                    "- 主视觉建议集中在页面中上部，避免页脚区域被主内容挤压。",
                ]
            )
        elif page_number == total_pages:
            guides.extend(
                [
                    "- 结尾页应回收复杂结构，优先强化结论、行动建议或收束语。",
                    "- 结尾页保持节奏干净，不再铺陈过多并列卡片。",
                ]
            )
        else:
            guides.extend(
                [
                    f"- 当前页《{title}》按 {slide_type} 类型处理，优先让布局服务于信息主次。",
                    "- 若内容偏多，先压缩装饰、列数和标签数量，再谨慎缩小字号。",
                ]
            )
        guides.extend(
            [
                "",
                "**B. 组件与排版规则**",
                "- 卡片之间保持一致的圆角、边框和间距语言，避免同页出现两套不兼容容器风格。",
                "- 大标题与正文采用跨层级字号落差，正文尽量控制在 14-16px 的舒适阅读区间。",
                "- 标签、数字强调、结论徽标要少而准，不要把所有信息都做成视觉重点。",
                "",
                "**C. 内容自适应策略**",
                "- 内容偏少时放大焦点、增加留白和单个容器体量。",
                "- 内容适中时优先使用 2 栏或 1 主 1 辅布局。",
                "- 内容偏多时减少卡片数量、缩短描述句，必要时把复杂说明合并成摘要。",
            ]
        )
        return "\n".join(guides)

    def generate_unified_design_guide(
        self,
        slide_data: dict[str, Any],
        page_number: int,
        total_pages: int,
        confirmed_requirements: dict[str, Any] | None = None,
        all_slides: list[dict[str, Any]] | None = None,
        template_html: str = "",
    ) -> str:
        confirmed_requirements = confirmed_requirements or {}
        slides_summary = ""
        if all_slides:
            lines = []
            for index, slide in enumerate(all_slides, start=1):
                title = str(slide.get("title") or slide.get("page_title") or f"第{index}页").strip()
                slide_type = str(slide.get("slide_type") or slide.get("type") or "").strip()
                lines.append(f"{index}. {title}" + (f"（{slide_type}）" if slide_type else ""))
            slides_summary = "\n".join(lines)
        else:
            slides_summary = f"1. {slide_data.get('title', '当前页')}"

        prompt = prompts_manager.get_slide_design_guide_prompt(
            slide_data=slide_data,
            confirmed_requirements=confirmed_requirements,
            slides_summary=slides_summary,
            page_number=page_number,
            total_pages=total_pages,
            template_html=template_html,
        )
        try:
            result = self.client.chat(
                "你是资深 PPT 创意总监，负责把模板约束转成可执行的页面设计规则。",
                prompt,
                temperature=0.6,
            )
            cleaned = result.strip()
            if len(cleaned) >= 80:
                return cleaned
        except Exception as exc:
            logger.warning("AI unified design guide generation failed: %s", exc)
        return self._generate_fallback_unified_guide(slide_data, page_number, total_pages)

    def get_project_cache_key(self, topic: str, audience: str) -> str:
        return build_project_cache_key(topic, audience)
