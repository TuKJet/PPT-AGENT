from __future__ import annotations

import json
import logging
import re
from typing import Any

from adapters.asset_repository import LocalAssetRepository
from ai_client import AIClient
from vendor_landppt.models import (
    ImageRequirement,
    SlideImageAsset,
    SlideImagePlan,
    SlideImageRequirements,
    SlideImagesCollection,
)

logger = logging.getLogger(__name__)


class LandPPTImageEngine:
    """Migrated image planning logic adapted to PPT-AGENT's local environment."""

    def __init__(self, client: AIClient, asset_repository: LocalAssetRepository | None = None):
        self.client = client
        self.asset_repository = asset_repository or LocalAssetRepository()

    def _extract_json_from_response(self, content: str) -> str | None:
        content = content.strip()
        if content.startswith("```"):
            match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
            if match:
                return match.group(1)
        match = re.search(r"(\{.*\})", content, re.DOTALL)
        if match:
            return match.group(1)
        return None

    def analyze_image_requirements(
        self,
        slide_data: dict[str, Any],
        confirmed_requirements: dict[str, Any],
        page_number: int,
        total_pages: int,
        template_html: str = "",
    ) -> SlideImageRequirements:
        slide_title = slide_data.get("title", "")
        slide_content = slide_data.get("content_points", [])
        if isinstance(slide_content, list):
            slide_content_text = "\n".join(str(item) for item in slide_content)
        else:
            slide_content_text = str(slide_content)

        prompt = f"""你是专业的 PPT 配图策略分析师。请判断当前页是否需要图片，并以纯 JSON 返回结果。

项目主题：{confirmed_requirements.get('topic', '')}
目标受众：{confirmed_requirements.get('target_audience', '')}
当前页：{page_number}/{total_pages}
当前页标题：{slide_title}
当前页内容：
{slide_content_text}

模板摘要：
{template_html[:600]}

判断规则：
1. 目录页、纯列表页、纯结论页通常不强制配图。
2. 如果页面更适合靠数据、时间线、卡片排版表达，可返回不需要图片。
3. 如果需要图片，优先说明用途：decoration / illustration / background / icon / content_visual。
4. 总图片数不超过 2。

返回格式：
{{
  "needs_images": true,
  "total_images": 1,
  "requirements": [
    {{
      "source": "local",
      "count": 1,
      "purpose": "illustration",
      "description": "需要一张能承接页面主题的主视觉图片",
      "priority": 1
    }}
  ],
  "reasoning": "说明为什么"
}}
"""
        try:
            response = self.client.chat(
                "你只输出合法 JSON，不要附加解释，不要使用 markdown 代码块。",
                prompt,
                temperature=0.2,
            )
            json_text = self._extract_json_from_response(response)
            if json_text:
                data = json.loads(json_text)
                requirements = [
                    ImageRequirement(
                        source=str(item.get("source", "local")),
                        count=int(item.get("count", 1)),
                        purpose=str(item.get("purpose", "illustration")),
                        description=str(item.get("description", "")),
                        priority=int(item.get("priority", 3)),
                    )
                    for item in data.get("requirements", [])
                ]
                return SlideImageRequirements(
                    needs_images=bool(data.get("needs_images", False)),
                    total_images=int(data.get("total_images", 0)),
                    requirements=requirements,
                    reasoning=str(data.get("reasoning", "")),
                )
        except Exception as exc:
            logger.warning("Image requirement analysis failed: %s", exc)

        content_length = len(slide_content_text)
        if page_number == 1 and content_length < 220:
            return SlideImageRequirements(
                needs_images=True,
                total_images=1,
                requirements=[
                    ImageRequirement(
                        source="local",
                        count=1,
                        purpose="background",
                        description="封面适合一张承担气氛的背景或主视觉素材",
                        priority=1,
                    )
                ],
                reasoning="首页通常需要主视觉来建立第一印象。",
            )
        return SlideImageRequirements(
            needs_images=False,
            total_images=0,
            requirements=[],
            reasoning="本页更适合靠排版、层级和组件节奏承载信息，不强制加图。",
        )

    def _build_query_hints(self, slide_data: dict[str, Any], requirements: SlideImageRequirements) -> list[str]:
        hints = []
        title = str(slide_data.get("title", "")).strip()
        content_points = slide_data.get("content_points", [])
        key_text = " ".join(content_points[:2]) if isinstance(content_points, list) else str(content_points)
        for requirement in requirements.requirements:
            hints.append(f"{title} {requirement.purpose} {requirement.description}")
            if key_text:
                hints.append(f"{title} {key_text[:40]}")
        return list(dict.fromkeys(hints))[:4]

    def _match_local_assets(
        self,
        requirements: SlideImageRequirements,
        query_hints: list[str],
    ) -> SlideImagesCollection:
        collection = SlideImagesCollection(planning_reasoning=requirements.reasoning)
        if not requirements.needs_images:
            return collection

        for requirement in requirements.requirements:
            remaining = max(requirement.count, 1)
            for hint in query_hints:
                for match in self.asset_repository.search_images(hint, count=remaining):
                    collection.assets.append(
                        SlideImageAsset(
                            source_type="local",
                            path=match["path"],
                            title=match["name"],
                            purpose=requirement.purpose,
                            metadata={"score": match["score"], "hint": hint},
                        )
                    )
                    remaining -= 1
                    if remaining <= 0:
                        break
                if remaining <= 0:
                    break
        return collection

    def build_slide_image_plan(
        self,
        slide_data: dict[str, Any],
        confirmed_requirements: dict[str, Any],
        page_number: int,
        total_pages: int,
        template_html: str = "",
    ) -> SlideImagePlan:
        requirements = self.analyze_image_requirements(
            slide_data=slide_data,
            confirmed_requirements=confirmed_requirements,
            page_number=page_number,
            total_pages=total_pages,
            template_html=template_html,
        )
        query_hints = self._build_query_hints(slide_data, requirements)
        collection = self._match_local_assets(requirements, query_hints)
        return SlideImagePlan(requirements=requirements, collection=collection, query_hints=query_hints)

