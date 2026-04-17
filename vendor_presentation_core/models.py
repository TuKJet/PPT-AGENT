from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageRequirement:
    source: str
    count: int
    purpose: str
    description: str
    priority: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "count": self.count,
            "purpose": self.purpose,
            "description": self.description,
            "priority": self.priority,
        }


@dataclass
class SlideImageRequirements:
    needs_images: bool
    total_images: int
    requirements: list[ImageRequirement] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_images": self.needs_images,
            "total_images": self.total_images,
            "requirements": [item.to_dict() for item in self.requirements],
            "reasoning": self.reasoning,
        }


@dataclass
class SlideImageAsset:
    source_type: str
    path: str
    title: str
    purpose: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "path": self.path,
            "title": self.title,
            "purpose": self.purpose,
            "metadata": dict(self.metadata),
        }


@dataclass
class SlideImagesCollection:
    assets: list[SlideImageAsset] = field(default_factory=list)
    planning_reasoning: str = ""

    @property
    def total_count(self) -> int:
        return len(self.assets)

    @property
    def local_count(self) -> int:
        return sum(asset.source_type == "local" for asset in self.assets)

    @property
    def network_count(self) -> int:
        return sum(asset.source_type == "network" for asset in self.assets)

    @property
    def ai_generated_count(self) -> int:
        return sum(asset.source_type == "ai_generated" for asset in self.assets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_count": self.total_count,
            "local_count": self.local_count,
            "network_count": self.network_count,
            "ai_generated_count": self.ai_generated_count,
            "planning_reasoning": self.planning_reasoning,
            "assets": [asset.to_dict() for asset in self.assets],
        }

    def get_summary_for_ai(self) -> str:
        if not self.assets:
            return "当前没有已落地的图片素材，可保留图像位或使用抽象视觉元素维持构图。"
        lines = []
        for index, asset in enumerate(self.assets, start=1):
            lines.append(
                f"{index}. [{asset.source_type}] {asset.title} | 用途: {asset.purpose} | 路径: {asset.path}"
            )
        return "\n".join(lines)


@dataclass
class SlideImagePlan:
    requirements: SlideImageRequirements
    collection: SlideImagesCollection
    query_hints: list[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        if not self.requirements.needs_images:
            return (
                "图片策略：本页不强制放图。请通过排版、图标、分隔线和卡片层级承担视觉重心，"
                "避免为了凑图而引入弱相关素材。"
            )

        lines = [
            f"图片策略：建议总计 {self.requirements.total_images} 张视觉素材。",
            f"规划理由：{self.requirements.reasoning or '优先让图像承担视觉焦点。'}",
        ]
        for requirement in self.requirements.requirements:
            lines.append(
                f"- [{requirement.priority}] {requirement.purpose} | {requirement.source} | {requirement.description}"
            )
        if self.collection.assets:
            lines.append("已匹配到的素材：")
            lines.append(self.collection.get_summary_for_ai())
        elif self.query_hints:
            lines.append("未落地素材时的检索提示：")
            lines.extend(f"- {hint}" for hint in self.query_hints)
        else:
            lines.append("若无合适图片，请保留明确图像占位并使用抽象背景或图标增强层次。")
        return "\n".join(lines)


def build_project_cache_key(topic: str, audience: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in f"{topic}_{audience}".strip().lower())
    return normalized.strip("_") or "default_project"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

