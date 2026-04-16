from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TemplateRecord:
    template_id: str
    template_name: str
    description: str
    html_template: str
    style_config: dict[str, Any]
    tags: list[str]
    is_default: bool = False
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.template_id,
            "template_name": self.template_name,
            "description": self.description,
            "html_template": self.html_template,
            "style_config": self.style_config,
            "tags": list(self.tags),
            "is_default": self.is_default,
            "is_active": self.is_active,
        }


class LocalTemplateRepository:
    """File-backed replacement for LandPPT's database template repository."""

    def __init__(self, base_dir: Path | None = None):
        root = Path(__file__).resolve().parent.parent
        self.base_dir = base_dir or (root / "vendor_landppt" / "templates")
        self.catalog_path = self.base_dir / "templates.json"

    def _load_catalog(self) -> list[dict[str, Any]]:
        if not self.catalog_path.exists():
            return []
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def _read_template_html(self, html_file: str) -> str:
        return (self.base_dir / html_file).read_text(encoding="utf-8")

    def list_templates(self, active_only: bool = True) -> list[TemplateRecord]:
        templates: list[TemplateRecord] = []
        for raw in self._load_catalog():
            if active_only and not raw.get("is_active", True):
                continue
            templates.append(
                TemplateRecord(
                    template_id=str(raw["id"]),
                    template_name=str(raw["template_name"]),
                    description=str(raw.get("description", "")),
                    html_template=self._read_template_html(str(raw["html_file"])),
                    style_config=dict(raw.get("style_config", {})),
                    tags=list(raw.get("tags", [])),
                    is_default=bool(raw.get("is_default", False)),
                    is_active=bool(raw.get("is_active", True)),
                )
            )
        return templates

    def get_template_by_id(self, template_id: str) -> TemplateRecord | None:
        for template in self.list_templates(active_only=False):
            if template.template_id == str(template_id):
                return template
        return None

    def get_default_template(
        self,
        audience: str = "",
        topic: str = "",
        prefer_dark: bool | None = None,
    ) -> TemplateRecord:
        templates = self.list_templates()
        if not templates:
            raise FileNotFoundError(f"No templates found under {self.base_dir}")

        audience_text = audience.lower()
        topic_text = topic.lower()
        if prefer_dark is None:
            prefer_dark = any(
                keyword in audience_text or keyword in topic_text
                for keyword in ("学生", "年轻", "潮流", "科技", "ai", "agent", "startup")
            )

        preferred_tags = {"dark"} if prefer_dark else {"light", "editorial"}
        for template in templates:
            if preferred_tags.intersection(template.tags):
                return template

        for template in templates:
            if template.is_default:
                return template
        return templates[0]

    def save_generated_template(
        self,
        template_name: str,
        description: str,
        html_template: str,
        tags: list[str] | None = None,
    ) -> TemplateRecord:
        templates = self._load_catalog()
        next_id = (
            max((int(str(item.get("id", "0")).split("_")[-1]) for item in templates if str(item.get("id", "")).startswith("generated_")), default=0)
            + 1
        )
        template_id = f"generated_{next_id:03d}"
        html_file = f"{template_id}.html"
        (self.base_dir / html_file).write_text(html_template, encoding="utf-8")
        entry = {
            "id": template_id,
            "template_name": template_name,
            "description": description,
            "html_file": html_file,
            "style_config": {"source": "generated"},
            "tags": list(tags or ["generated"]),
            "is_default": False,
            "is_active": True,
        }
        templates.append(entry)
        self.catalog_path.write_text(json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8")
        return TemplateRecord(
            template_id=template_id,
            template_name=template_name,
            description=description,
            html_template=html_template,
            style_config={"source": "generated"},
            tags=list(tags or ["generated"]),
            is_default=False,
            is_active=True,
        )

