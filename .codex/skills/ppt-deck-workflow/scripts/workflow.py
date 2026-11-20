from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import math
import platform
import re
from importlib.metadata import version as package_version
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image, ImageChops, ImageFilter, ImageStat

SKILL_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_RUNTIME_ROOT = SKILL_ROOT / "runtime"
GLOBAL_SKILL_MODE = (BUNDLED_RUNTIME_ROOT / "filename_utils.py").is_file()
try:
    LOCAL_REPO_ROOT = Path(__file__).resolve().parents[4]
except IndexError:
    LOCAL_REPO_ROOT = SKILL_ROOT
RUNTIME_ROOT = BUNDLED_RUNTIME_ROOT if GLOBAL_SKILL_MODE else LOCAL_REPO_ROOT
WORKSPACE_ROOT = Path(
    os.getenv("PPT_AGENT_WORKSPACE", str(Path.cwd() if GLOBAL_SKILL_MODE else LOCAL_REPO_ROOT))
).resolve()

if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

if str(SKILL_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
from embed_img_crops import validate_crop_entries, _validated_box
from filename_utils import safe_filename_part, slide_filename
from data_regions import apply_pptd as apply_pptd_data_regions
from data_regions import materialize_images as materialize_data_images
from data_regions import validate as validate_data_regions

STATE_FILE = "workflow-state.json"
ARTIFACT_FILES = {
    "outline": "outline.json",
    "contents": "contents.json",
    "slide_plans": "slide-plans.json",
}
PREVIEW_FILES = {
    "outline": ".workflow/outline-preview.md",
    "contents": ".workflow/contents-preview.md",
    "slide_plans": ".workflow/slide-plans-preview.md",
}
ARTIFACT_DEPENDENCIES = {"outline": ("contents", "slide_plans"), "contents": ("slide_plans",), "slide_plans": ()}
COMMON_ARTIFACT_KEYS = set(ARTIFACT_FILES)
RENDER_REVIEW_NOT_APPLICABLE = {
    "mode": "off",
    "status": "not_applicable",
}
SLIDE_PLAN_VERSION = 2
REQUIRED_DECK_STRATEGY_FIELDS = (
    "primary_audience",
    "decision_context",
    "first_questions",
    "evidence_order",
    "presentation_posture",
)
REQUIRED_DESIGN_SYSTEM_FIELDS = (
    "theme_name",
    "audience_fit",
    "palette",
    "typography",
    "component_rules",
    "chart_treatment",
    "illustration_policy",
    "design_genes",
)
REQUIRED_PALETTE_TOKENS = (
    "background",
    "surface",
    "primary",
    "accent",
    "text_primary",
    "text_muted",
)
REQUIRED_SLIDE_PLAN_FIELDS = (
    "core_message",
    "layout_structure",
    "visual_hierarchy",
    "required_elements",
    "palette_tokens",
    "style_controls",
    "audience_controls",
    "renderer_neutral_constraints",
)
PREVIEW_LABELS = {
    "primary_audience": "目标受众",
    "secondary_audience": "次要受众",
    "decision_context": "决策目标",
    "first_questions": "首要问题",
    "evidence_order": "证据顺序",
    "presentation_posture": "表达姿态",
    "theme_name": "主题名称",
    "audience_fit": "受众适配",
    "typography": "字体层级",
    "component_rules": "组件与间距",
    "chart_treatment": "图表与图解",
    "illustration_policy": "图像与插画",
    "design_genes": "设计基因",
    "title": "标题",
    "section_heading": "分区标题",
    "body": "正文",
    "metric": "核心数字",
    "cards": "卡片",
    "spacing": "间距",
    "lines": "线条",
    "footer": "页脚",
    "style": "表现方式",
    "labels": "标注",
    "risk_encoding": "风险编码",
    "density": "信息密度",
    "visual_motif": "视觉母题",
    "contrast": "对比策略",
    "technical_depth": "技术深度",
    "business_framing": "业务表达",
    "decision_orientation": "决策导向",
    "persuasion_intensity": "说服强度",
    "page_density": "页面密度",
}
PALETTE_LABELS = {
    "background": "页面背景",
    "surface": "卡片/表面",
    "primary": "主色",
    "accent": "强调色",
    "text_primary": "主要文字",
    "text_muted": "次要文字",
    "risk": "风险",
    "warning": "警示",
    "success": "成功/正向",
    "divider": "分隔线",
}
PAGE_ROLE_LABELS = {
    "cover": "封面",
    "toc": "目录",
    "content": "内容页",
    "timeline": "时间线",
    "summary": "总结页",
    "ending": "结束页",
}

IMG_SVG_PROMPT_PATH = SKILL_ROOT / "references" / "img-svg-prompt.md"


def default_img_svg_conversion() -> dict[str, Any]:
    return {
        "mode": None,
        "status": "waiting_for_img_export",
    }


def default_state() -> dict[str, Any]:
    return {
        "version": 7,
        "status": "new",
        "approvals": {},
        "artifacts": {},
        "renderer": None,
        "render_review": {
            "mode": None,
            "status": "not_applicable",
        },
        "renderers": {},
        "execution": "codex-skill",
        "plan_mode": "legacy",
        "style_samples": {"status": "not_started", "styles": [], "created_at": None},
        "design_choice": None,
    }


def default_renderer_state(renderer: str | None = None) -> dict[str, Any]:
    state = {"status": "new", "artifacts": {}, "review": dict(RENDER_REVIEW_NOT_APPLICABLE)}
    if renderer == "img":
        state["svg_conversion"] = default_img_svg_conversion()
    return state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output"))


def resolved_output_root() -> Path:
    root = output_root()
    if not root.is_absolute():
        root = WORKSPACE_ROOT / root
    return root.resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def normalize_run_dir(raw: str | None, *, topic: str | None = None) -> Path:
    base = resolved_output_root()
    if raw is None:
        if not topic:
            raise ValueError("topic is required when run_dir is omitted")
        return (base / safe_filename_part(topic, max_length=80)).resolve()

    run_dir = Path(raw)
    if run_dir.is_absolute():
        resolved = run_dir.resolve()
    else:
        repo_relative = (WORKSPACE_ROOT / run_dir).resolve()
        resolved = repo_relative if is_within(repo_relative, base) else (base / run_dir).resolve()

    if not is_within(resolved, base):
        raise ValueError(f"run_dir must stay inside output root: {base}")
    return resolved


def run_dir_for_topic(topic: str) -> Path:
    return normalize_run_dir(None, topic=topic)


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    merged = default_state()
    merged.update(state or {})
    if merged.pop("style_gate_required", False) and "plan_mode" not in (state or {}):
        merged["plan_mode"] = "samples"
    merged["approvals"] = dict(merged.get("approvals") or {})
    artifacts = dict(merged.get("artifacts") or {})
    renderers = merged.get("renderers")
    if not isinstance(renderers, dict):
        renderers = {}

    active_renderer = merged.get("renderer")
    if active_renderer and active_renderer not in renderers:
        common_artifacts = {key: value for key, value in artifacts.items() if key in COMMON_ARTIFACT_KEYS}
        renderer_artifacts = {key: value for key, value in artifacts.items() if key not in COMMON_ARTIFACT_KEYS}
        if renderer_artifacts:
            artifacts = common_artifacts
        renderers[active_renderer] = {
            **default_renderer_state(active_renderer),
            "status": merged.get("status", "new"),
            "artifacts": renderer_artifacts,
            "review": dict(merged.get("render_review") or default_renderer_state(active_renderer)["review"]),
        }

    normalized_renderers = {renderer: _normalize_renderer_state(renderer, entry)
                            for renderer, entry in renderers.items()}
    # V5 required a decline reply after IMG export. Migrate that old state only.
    for entry in normalized_renderers.values():
        conversion = entry.get("svg_conversion", {})
        if conversion.get("status") == "pending_choice":
            conversion.update(status="available", requires_explicit_opt_in=True,
                              additional_model_usage_required=True)
        if entry.get("status") == "img_svg_choice_pending":
            entry["status"] = "completed"

    merged["artifacts"] = artifacts
    merged["renderers"] = normalized_renderers
    if merged.get("status") == "img_svg_choice_pending":
        merged["status"] = "completed"
    merged["version"] = 7
    return merged


def _normalize_renderer_state(renderer: str, entry: Any) -> dict[str, Any]:
    normalized = default_renderer_state(renderer)
    if isinstance(entry, dict):
        normalized.update(entry)
    normalized["artifacts"] = dict(normalized.get("artifacts") or {})
    normalized["review"] = dict(normalized.get("review") or default_renderer_state(renderer)["review"])
    if renderer == "img":
        normalized["svg_conversion"] = {**default_img_svg_conversion(), **dict(normalized.get("svg_conversion") or {})}
    return normalized


def renderer_state(state: dict[str, Any], renderer: str) -> dict[str, Any]:
    renderers = state.setdefault("renderers", {})
    renderers[renderer] = _normalize_renderer_state(renderer, renderers.get(renderer))
    return renderers[renderer]


def load_state(run_dir: Path) -> dict[str, Any]:
    if (run_dir / STATE_FILE).is_file():
        return _normalize_state(read_json(run_dir / STATE_FILE))
    state = default_state()
    delivery = read_json(run_dir / 'slide-plans.json', default={}).get('_delivery') or {}
    if delivery:
        state.update(topic=delivery.get('topic', run_dir.name), audience=delivery.get('audience'))
        selected = delivery.get('renderer')
        if selected in {'img', 'pptd'}:
            state['renderer'] = selected
        state['renderers'] = {name: {**default_renderer_state(name), 'source': source}
                              for name, source in delivery.get('renderer_sources', {}).items()
                              if name in {'img', 'pptd'} and source in {'plans', 'img'}}
    return _normalize_state(state)


def save_state(run_dir: Path, state: dict[str, Any]) -> Path:
    normalized = _normalize_state(state)
    normalized["version"] = 7
    normalized["execution"] = "codex-skill"
    normalized["updated_at"] = utc_now()
    return write_json(run_dir / STATE_FILE, normalized)


def init_state(run_dir: Path, *, topic: str, audience: str, pages: str, research: str) -> dict[str, Any]:
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError(f"run already initialized: {run_dir}; use resume or choose a new run directory")
    state = load_state(run_dir)
    state.update({
        "topic": topic,
        "audience": audience,
        "pages": pages,
        "research": research,
        "status": "initialized",
        "created_at": state.get("created_at") or utc_now(),
        "approvals": state.get("approvals") or {},
        "artifacts": state.get("artifacts") or {},
        "renderer": state.get("renderer"),
        "render_review": state.get("render_review") or {
            "mode": None,
            "status": "not_applicable",
        },
        "renderers": state.get("renderers") or {},
        "plan_mode": None,
    })
    save_state(run_dir, state)
    return state


def planning_action(state: dict[str, Any]) -> str | None:
    mode = state["plan_mode"]
    if mode is None:
        return "ask-how-to-plan-slides"
    if mode == "samples":
        if state["style_samples"]["status"] != "ready":
            return "generate-and-record-four-style-samples"
        if not state.get("design_choice"):
            return "ask-user-for-style-preference"
    return None


def cmd_choose_plan_mode(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    require_approved(run_dir, "contents")
    state = load_state(run_dir)
    if state["plan_mode"] != args.mode:
        state["plan_mode"] = args.mode
        state["design_choice"] = None
        state["style_samples"] = {"status": "not_started", "styles": []}
        _invalidate_slide_plans(state)
        state["status"] = "planning_mode_chosen"
        save_state(run_dir, state)
    print(f"plan_mode={args.mode}", flush=True)
    next_step = 'resume' if state['approvals'].get('slide_plans') else 'write-and-preview-slide-plans'
    print(f"next={planning_action(state) or next_step}", flush=True)


def cmd_record_style_samples(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    require_approved(run_dir, "contents")
    if state["plan_mode"] != "samples":
        raise RuntimeError("choose-plan-mode --mode samples before recording style samples")
    from style_comparison import prepare
    styles = read_json(Path(args.file)).get("styles")
    comparisons = prepare(run_dir, styles, len(read_json(run_dir / "contents.json")))
    state["style_samples"] = {"status": "ready", "styles": styles, "comparisons": comparisons}
    state["design_choice"] = None
    _invalidate_slide_plans(state)
    state["status"] = "style_samples_ready"
    save_state(run_dir, state)
    for path in comparisons:
        print(f"show_image={path}", flush=True)
    print("next=ask-user-for-style-preference", flush=True)


def cmd_choose_style(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    require_approved(run_dir, "contents")
    if (state.get("style_samples") or {}).get("status") != "ready":
        raise RuntimeError("record four style samples before choosing a design direction")
    preference = str(args.preference or "").strip()
    if not preference:
        raise ValueError("style preference must be a free-form description")
    if (state.get("design_choice") or {}).get("preference") != preference:
        _invalidate_slide_plans(state)
    state["design_choice"] = {"preference": preference, "chosen_at": utc_now()}
    state["status"] = "style_chosen"
    save_state(run_dir, state)
    print("design_choice=recorded", flush=True)
    print("next=write-and-preview-slide-plans", flush=True)


def _invalidate_slide_plans(state: dict[str, Any]) -> None:
    """Require a fresh preview/approval when visual direction changes."""
    if "slide_plans" in state.get("approvals", {}):
        state["approvals"]["slide_plans"] = False
    entry = state.get("artifacts", {}).get("slide_plans")
    if isinstance(entry, dict):
        entry["status"] = "stale"


def ensure_render_ready(run_dir: Path, renderer: str) -> None:
    require_approved(run_dir, "slide_plans")
    if renderer not in {"img", "pptd"}:
        raise ValueError("renderer must be img or pptd; HTML and standalone SVG are removed")
    if load_state(run_dir).get("renderer") != renderer:
        raise RuntimeError(f"choose-renderer --renderer {renderer} is required first")


def mark_artifact(run_dir: Path, state: dict[str, Any], name: str, path: Path, preview_path: Path) -> None:
    artifact_sha = file_sha256(path)
    preview_sha = file_sha256(preview_path)
    previous = state.setdefault("artifacts", {}).get(name) or {}
    unchanged = previous.get("sha256") == artifact_sha and previous.get("preview_sha256") == preview_sha
    state.setdefault("artifacts", {})[name] = {
        **previous,
        "path": str(path),
        "preview_path": str(preview_path),
        "sha256": artifact_sha,
        "preview_sha256": preview_sha,
        "status": "approved" if unchanged and state.get("approvals", {}).get(name) else "pending_review",
        "updated_at": utc_now(),
    }
    if not unchanged:
        if name in ("outline", "contents") and not state.get("design_choice"):
            state["style_samples"] = {"status": "not_started", "styles": []}
        state.setdefault("approvals", {})[name] = False
        for dependent in ARTIFACT_DEPENDENCIES.get(name, ()):
            state.setdefault("approvals", {})[dependent] = False
            entry = state.setdefault("artifacts", {}).get(dependent)
            if entry:
                entry["status"] = "stale"
        for renderer in state.get("renderers", {}).values():
            if isinstance(renderer, dict):
                jobs = renderer.get("jobs")
                if isinstance(jobs, dict):
                    jobs["status"] = "stale"
    if not unchanged:
        state["status"] = f"{name}_pending_review"
    save_state(run_dir, state)


def require_approved(run_dir: Path, artifact: str) -> None:
    state = load_state(run_dir)
    entry = state.get("artifacts", {}).get(artifact) or {}
    path, preview = Path(entry.get("path", "")), Path(entry.get("preview_path", ""))
    current_sha = file_sha256(path) if path.is_file() else None
    current_preview_sha = file_sha256(preview) if preview.is_file() else None
    if (not state.get("approvals", {}).get(artifact) or not current_sha or not current_preview_sha or
            entry.get("sha256") != current_sha or entry.get("preview_sha256") != current_preview_sha):
        preview = state.get("artifacts", {}).get(artifact, {}).get("preview_path")
        detail = f" Review {preview} first." if preview else ""
        raise RuntimeError(f"{artifact} is not approved or has changed since approval.{detail}")
    for upstream, dependents in ARTIFACT_DEPENDENCIES.items():
        if artifact in dependents and upstream in state.get("artifacts", {}):
            require_approved(run_dir, upstream)


def current_task_brief(run_dir: Path) -> dict:
    path = run_dir / '.workflow/task-brief.json'
    if path.is_file():
        return read_json(path)
    delivery = read_json(run_dir / 'slide-plans.json', default={}).get('_delivery') or {}
    return delivery.get('task_brief') or {}


def task_brief_hash(run_dir: Path) -> str | None:
    brief = current_task_brief(run_dir)
    if not brief:
        return None
    # Progress bookkeeping does not change rendering intent.
    intent = {k: brief.get(k) for k in ('objective', 'constraints', 'source_paths')}
    return text_sha256(json.dumps(intent, sort_keys=True, ensure_ascii=False))


def render_jobs_issue(run_dir: Path, renderer: str) -> str | None:
    state = load_state(run_dir)
    entry = state.get('renderers', {}).get(renderer, {})
    jobs = entry.get('jobs') or {}
    manifest_path = render_jobs_root(run_dir, renderer) / 'manifest.json'
    if not manifest_path.is_file():
        return 'missing render manifest'
    try:
        manifest = read_json(manifest_path)
        plan_sha = file_sha256(run_dir / 'slide-plans.json')
        brief_sha = task_brief_hash(run_dir)
        if (jobs.get('status') == 'stale' or manifest.get('plan_sha256') != plan_sha or
                manifest.get('task_brief_sha256') != brief_sha or manifest.get('renderer') != renderer or
                manifest.get('source', 'plans') != entry.get('source', 'plans')):
            return 'render input changed'
        if jobs.get('manifest_sha256') != file_sha256(manifest_path):
            return 'render manifest changed or lacks provenance'
        shared = manifest_path.parent / 'shared-context.json'
        if not shared.is_file() or manifest.get('shared_context_sha256') != file_sha256(shared):
            return 'shared render context changed'
        slides = slide_jobs(run_dir)
        if len(manifest.get('slides', [])) != len(slides):
            return 'render page count changed'
        for page, item in zip(slides, manifest['slides']):
            path = manifest_path.parent / f"slide-{int(page['index']):02d}.json"
            if not path.is_file() or item.get('job_sha256') != file_sha256(path):
                return 'page render job changed'
        return None
    except (ValueError, OSError, KeyError, TypeError):
        return 'invalid render manifest or input'


def require_current_render_jobs(run_dir: Path, renderer: str) -> None:
    issue = render_jobs_issue(run_dir, renderer)
    if issue:
        # Old direct-authoring projects may have no jobs at all. Do not claim provenance.
        entry = load_state(run_dir).get('renderers', {}).get(renderer, {})
        if issue == 'missing render manifest' and not entry.get('jobs'):
            print('warning=no prepared render provenance; prepare-render-jobs before new authoring', file=sys.stderr)
            return
        raise RuntimeError(f'{renderer} jobs are stale: {issue}; run prepare-render-jobs again')


def _get_pages(outline: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(outline.get("pages"), list):
        return outline["pages"]
    inner = outline.get("ppt_outline", outline)
    pages: list[dict[str, Any]] = []
    for key in ("cover", "table_of_contents"):
        value = inner.get(key)
        if isinstance(value, dict):
            pages.append(value)
    for part in inner.get("parts", []) if isinstance(inner.get("parts"), list) else []:
        if isinstance(part, dict):
            for page in part.get("pages", []):
                if isinstance(page, dict):
                    pages.append(page)
    end_page = inner.get("end_page")
    if isinstance(end_page, dict):
        pages.append(end_page)
    return pages


def _get_title(page: dict[str, Any]) -> str:
    return str(page.get("title") or page.get("page_title") or page.get("name") or "Untitled")


def write_outline_preview(outline: dict[str, Any], path: Path) -> Path:
    lines = ["# Outline Preview", ""]
    for index, page in enumerate(_get_pages(outline), start=1):
        lines.append(f"## {index:02d}. {_get_title(page)}")
        sections = page.get("sections") or page.get("content") or page.get("bullets") or []
        if isinstance(sections, list):
            for item in sections[:8]:
                lines.append(f"- {item}")
        elif sections:
            lines.append(f"- {sections}")
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def write_contents_preview(contents: dict[str, Any], path: Path) -> Path:
    lines = ["# Contents Preview", ""]
    for title, material in contents.items():
        lines.extend([f"## {title}", "", str(material).strip(), ""])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def _is_non_empty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _require_non_empty_fields(value: Any, path: str, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    missing = [field for field in fields if not _is_non_empty(value.get(field))]
    if missing:
        raise ValueError(f"{path} is missing required fields: {', '.join(missing)}")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _require_non_empty_string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{path} must be a non-empty string list")
    return value


def validate_slide_plans(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("slide-plans.json must contain a JSON object")
    try:
        version = int(data.get("version", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("slide-plans.json version must be an integer") from exc
    if version != SLIDE_PLAN_VERSION:
        raise ValueError(
            "slide-plans.json must use version 2 with structured deck_strategy, "
            "design_system, and per-slide plan fields; legacy version 1/free-form plans "
            "must be regenerated before preview or approval"
        )

    deck_strategy = _require_non_empty_fields(
        data.get("deck_strategy"),
        "slide-plans.json deck_strategy",
        REQUIRED_DECK_STRATEGY_FIELDS,
    )
    for field in ("primary_audience", "decision_context", "presentation_posture"):
        _require_non_empty_string(deck_strategy[field], f"slide-plans.json deck_strategy.{field}")
    _require_non_empty_string_list(
        deck_strategy["first_questions"],
        "slide-plans.json deck_strategy.first_questions",
    )
    _require_non_empty_string_list(
        deck_strategy["evidence_order"],
        "slide-plans.json deck_strategy.evidence_order",
    )

    design_system = _require_non_empty_fields(
        data.get("design_system"),
        "slide-plans.json design_system",
        REQUIRED_DESIGN_SYSTEM_FIELDS,
    )
    for field in ("theme_name", "audience_fit", "illustration_policy"):
        _require_non_empty_string(design_system[field], f"slide-plans.json design_system.{field}")
    for field in ("typography", "component_rules", "chart_treatment"):
        if not isinstance(design_system[field], dict):
            raise ValueError(f"slide-plans.json design_system.{field} must be an object")
    _require_non_empty_string_list(
        design_system["design_genes"],
        "slide-plans.json design_system.design_genes",
    )
    palette = design_system.get("palette")
    if not isinstance(palette, dict):
        raise ValueError("slide-plans.json design_system requires a palette object")
    missing = sorted(token for token in REQUIRED_PALETTE_TOKENS if not _is_non_empty(palette.get(token)))
    if missing:
        raise ValueError(
            "slide-plans.json design_system.palette is missing required tokens: "
            + ", ".join(missing)
        )
    invalid_palette_values = sorted(
        token for token, color in palette.items() if not isinstance(color, str) or not color.strip()
    )
    if invalid_palette_values:
        raise ValueError(
            "slide-plans.json design_system.palette tokens must map to non-empty color strings: "
            + ", ".join(invalid_palette_values)
        )

    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        raise ValueError("slide-plans.json slides must be a non-empty list")

    seen_indexes: set[int] = set()
    for position, slide in enumerate(slides, start=1):
        slide_path = f"slide-plans.json slides[{position - 1}]"
        slide = _require_non_empty_fields(
            slide,
            slide_path,
            ("index", "title", "material", "page_role", "plan"),
        )
        try:
            index = int(slide["index"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{slide_path}.index must be an integer") from exc
        if index != position or index in seen_indexes:
            raise ValueError(f"{slide_path}.index must follow contiguous page order starting at 1")
        seen_indexes.add(index)
        for field in ("title", "material", "page_role"):
            _require_non_empty_string(slide[field], f"{slide_path}.{field}")

        plan = _require_non_empty_fields(
            slide["plan"],
            f"{slide_path}.plan",
            REQUIRED_SLIDE_PLAN_FIELDS,
        )
        for field in ("core_message", "layout_structure"):
            _require_non_empty_string(plan[field], f"{slide_path}.plan.{field}")
        for field in (
            "visual_hierarchy",
            "required_elements",
            "palette_tokens",
            "renderer_neutral_constraints",
        ):
            _require_non_empty_string_list(plan[field], f"{slide_path}.plan.{field}")
        for field in ("style_controls", "audience_controls"):
            if not isinstance(plan[field], dict):
                raise ValueError(f"{slide_path}.plan.{field} must be an object")
        validate_data_regions(plan.get("data_regions", []), f"{slide_path}.plan.data_regions")
        palette_tokens = plan["palette_tokens"]
        unknown_tokens = sorted(set(palette_tokens) - set(palette))
        if unknown_tokens:
            raise ValueError(
                f"{slide_path}.plan.palette_tokens references unknown design_system.palette tokens: "
                + ", ".join(unknown_tokens)
            )


def _preview_label(key: str) -> str:
    return PREVIEW_LABELS.get(key, key.replace("_", " ").strip().title())


def _append_preview_mapping(lines: list[str], value: dict[str, Any], *, indent: int = 0) -> None:
    prefix = " " * indent
    for key, item in value.items():
        label = _preview_label(str(key))
        if isinstance(item, dict):
            lines.append(f"{prefix}- **{label}**：")
            _append_preview_mapping(lines, item, indent=indent + 4)
        elif isinstance(item, list):
            lines.append(f"{prefix}- **{label}**：")
            for child in item:
                lines.append(f"{prefix}    - {str(child).strip()}")
        else:
            lines.append(f"{prefix}- **{label}**：{str(item).strip()}")


def _append_numbered_preview_list(lines: list[str], values: list[Any]) -> None:
    for index, value in enumerate(values, start=1):
        lines.append(f"{index}. {str(value).strip()}")


def _append_bulleted_preview_list(lines: list[str], values: list[Any]) -> None:
    for value in values:
        lines.append(f"- {str(value).strip()}")


def _append_deck_strategy_preview(lines: list[str], strategy: dict[str, Any]) -> None:
    lines.extend([
        "## 全局叙事策略",
        "",
        f"- **目标受众**：{strategy['primary_audience']}",
        f"- **决策目标**：{strategy['decision_context']}",
        f"- **表达姿态**：{strategy['presentation_posture']}",
        "",
        "### 受众首先会问",
        "",
    ])
    _append_numbered_preview_list(lines, strategy["first_questions"])
    lines.extend(["", "### 证据展开顺序", ""])
    _append_numbered_preview_list(lines, strategy["evidence_order"])
    rhythm = strategy.get("page_rhythm")
    if rhythm:
        lines.extend(["", "### 全稿页面节奏", ""])
        _append_bulleted_preview_list(lines, rhythm if isinstance(rhythm, list) else [rhythm])
    extras = {
        key: value
        for key, value in strategy.items()
        if key not in REQUIRED_DECK_STRATEGY_FIELDS and key != "page_rhythm"
    }
    if extras:
        lines.extend(["", "### 其他叙事约束", ""])
        _append_preview_mapping(lines, extras)
    lines.append("")


def _append_palette_preview(lines: list[str], palette: dict[str, Any]) -> None:
    lines.extend([
        "### 配色方案",
        "",
        "| 用途 | Token | 色值 |",
        "| --- | --- | --- |",
    ])
    for token, color in palette.items():
        lines.append(f"| {PALETTE_LABELS.get(token, _preview_label(token))} | `{token}` | `{color}` |")
    lines.append("")


def _append_design_system_preview(lines: list[str], design_system: dict[str, Any]) -> None:
    lines.extend([
        "## 全局设计规范",
        "",
        f"- **主题名称**：{design_system['theme_name']}",
        f"- **受众适配**：{design_system['audience_fit']}",
        f"- **图像与插画**：{design_system['illustration_policy']}",
        "",
    ])
    _append_palette_preview(lines, design_system["palette"])
    for key, title in (
        ("typography", "字体层级"),
        ("component_rules", "组件与间距"),
        ("chart_treatment", "图表与图解"),
    ):
        lines.extend([f"### {title}", ""])
        _append_preview_mapping(lines, design_system[key])
        lines.append("")
    lines.extend(["### 设计基因", ""])
    lines.append(" · ".join(str(item).strip() for item in design_system["design_genes"]))
    extras = {
        key: value
        for key, value in design_system.items()
        if key not in REQUIRED_DESIGN_SYSTEM_FIELDS
    }
    if extras:
        lines.extend(["", "### 其他设计约束", ""])
        _append_preview_mapping(lines, extras)
    lines.append("")


def _append_slide_plan_details(
    lines: list[str],
    plan: dict[str, Any],
    palette: dict[str, Any],
) -> None:
    lines.extend([
        "> **核心信息**",
        ">",
        f"> {plan['core_message']}",
        "",
        "### 页面布局",
        "",
        str(plan["layout_structure"]).strip(),
        "",
        "### 视觉层级",
        "",
    ])
    _append_numbered_preview_list(lines, plan["visual_hierarchy"])
    lines.extend(["", "### 页面元素", ""])
    _append_bulleted_preview_list(lines, plan["required_elements"])
    for region in plan.get("data_regions", []):
        label = {"line": "折线图", "bar": "柱状图", "table": "表格"}[region["kind"]]
        data = region["data"]
        lines.extend(["", f"### {label}数据", ""])
        for row in [data["cols"], ["---"] * len(data["cols"]), *data["rows"]]:
            cells = [str(value).replace("|", "\\|").replace("\n", "<br>") if value is not None else "—" for value in row]
            lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "### 本页配色", ""])
    colors = [
        f"{PALETTE_LABELS.get(token, _preview_label(token))} `{palette[token]}`"
        for token in plan["palette_tokens"]
    ]
    lines.append(" · ".join(colors))
    lines.extend(["", "### 样式控制", ""])
    _append_preview_mapping(lines, plan["style_controls"])
    lines.extend([
        "",
        "_受众控制与渲染通用约束已通过校验，并保留在 `slide-plans.json` 中供渲染阶段使用。_",
        "",
    ])


def write_plans_preview(data: dict[str, Any], path: Path) -> Path:
    validate_slide_plans(data)
    lines = ["# 幻灯片规划预览", ""]
    _append_deck_strategy_preview(lines, data["deck_strategy"])
    _append_design_system_preview(lines, data["design_system"])
    palette = data["design_system"]["palette"]
    for job in data.get("slides", []):
        role = str(job.get("page_role", "content"))
        lines.extend([
            "---",
            "",
            f"## 第 {int(job['index']):02d} 页｜{job['title']}",
            "",
            f"- **页面类型**：{PAGE_ROLE_LABELS.get(role, role)}",
            "",
        ])
        _append_slide_plan_details(lines, job["plan"], palette)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def preview_artifact(run_dir: Path, artifact: str) -> Path:
    data_path = run_dir / ARTIFACT_FILES[artifact]
    preview_path = run_dir / PREVIEW_FILES[artifact]
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    data = read_json(data_path)
    if artifact == "outline":
        write_outline_preview(data, preview_path)
    elif artifact == "contents":
        write_contents_preview(data, preview_path)
    elif artifact == "slide_plans":
        write_plans_preview(data, preview_path)
    state = load_state(run_dir)
    mark_artifact(run_dir, state, artifact, data_path, preview_path)
    return preview_path


def slide_jobs(run_dir: Path) -> list[dict[str, Any]]:
    data = slide_plan_document(run_dir)
    return list(data.get("slides") or [])


def slide_plan_document(run_dir: Path) -> dict[str, Any]:
    data = read_json(run_dir / "slide-plans.json", default={"slides": []})
    validate_slide_plans(data)
    return data


def renderer_pptx_name(run_dir: Path, renderer: str) -> str:
    topic = safe_filename_part(infer_topic(run_dir), max_length=30)
    return f"{topic}-{renderer}.pptx"


def slide_status_path(run_dir: Path, renderer: str | None = None) -> Path:
    return run_dir / ("slide-status.json" if renderer is None else f"slide-status-{renderer}.json")


def write_slide_status(run_dir: Path, slides: dict[str, Any], renderer: str | None = None) -> Path:
    payload: dict[str, Any] = {"slides": slides}
    if renderer:
        payload["renderer"] = renderer
        write_json(slide_status_path(run_dir, renderer), payload)
    return write_json(slide_status_path(run_dir), payload)


def infer_topic(run_dir: Path) -> str:
    return str(load_state(run_dir).get("topic") or run_dir.name)


def mark_completed(run_dir: Path, renderer: str, artifacts: dict[str, Path]) -> None:
    state = load_state(run_dir)
    state["renderer"] = renderer
    entry = renderer_state(state, renderer)
    entry["status"] = "completed"
    entry["completed_at"] = utc_now()
    if (run_dir / 'slide-plans.json').is_file():
        entry['export_plan_sha256'] = file_sha256(run_dir / 'slide-plans.json')
    entry["artifacts"] = {
        **entry.get("artifacts", {}),
        **{
            name: {"path": str(path), "status": "completed",
                   "sha256": file_sha256(path) if path.is_file() else None}
            for name, path in artifacts.items()
        },
    }
    state["render_review"] = dict(entry.get("review") or {})
    state["status"] = "completed"
    save_state(run_dir, state)


def render_jobs_root(run_dir: Path, renderer: str) -> Path:
    return run_dir / "render-jobs" / renderer


def render_target_path(run_dir: Path, renderer: str, index: int, title: str) -> Path:
    if renderer == "pptd":
        return run_dir / "pptd" / "pages" / slide_filename(index, title, "page")
    if renderer != "img":
        raise ValueError("renderer must be img or pptd")
    return run_dir / "img" / slide_filename(index, title, "png")


def prepare_render_jobs(run_dir: Path, renderer: str) -> Path:
    require_approved(run_dir, "slide_plans")
    if renderer not in {"img", "pptd"}:
        raise ValueError("renderer must be img or pptd")

    ensure_render_ready(run_dir, renderer)
    state = load_state(run_dir)
    plan_document = slide_plan_document(run_dir)
    slides = list(plan_document.get("slides") or [])
    source_mode = renderer_state(state, renderer).get("source", "plans")
    references = pptd_image_references(run_dir) if renderer == "pptd" and source_mode == "img" else []
    jobs_dir = render_jobs_root(run_dir, renderer)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    plan_path = run_dir / "slide-plans.json"
    plan_sha = file_sha256(plan_path)
    brief_sha = task_brief_hash(run_dir)
    # Only helper-owned slide jobs are pruned; authored pages and media remain.
    expected_job_names = {f"slide-{int(slide.get('index', i)):02d}.json" for i, slide in enumerate(slides, 1)}
    for old_job in jobs_dir.glob("slide-*.json"):
        if old_job.name not in expected_job_names:
            old_job.unlink()
    target_dir = run_dir / renderer
    target_dir.mkdir(parents=True, exist_ok=True)
    if renderer == "pptd":
        (target_dir / "pages").mkdir(exist_ok=True)
        (target_dir / "media").mkdir(exist_ok=True)

    shared_context_path = jobs_dir / "shared-context.json"
    shared_context = {
        "version": 2 if int(plan_document.get("version", 1)) >= 2 else 1,
        "topic": infer_topic(run_dir),
        "audience": state.get("audience"),
        "deck_strategy": plan_document.get("deck_strategy") or {},
        "design_system": plan_document.get("design_system") or {},
        "renderer": renderer,
        "slide_count": len(slides),
        "plan_sha256": plan_sha,
        "task_brief_sha256": brief_sha,
        "task_brief": current_task_brief(run_dir),
        "source": source_mode,
    }
    if references:
        shared_context["reconstruction_policy"] = {
            "default_mode": "hybrid",
            "native_rebuild_requires_explicit_request": True,
            "editable_text": "rebuild_titles_body_and_key_data",
            "complex_visuals": "prefer_source_crops",
            "simple_geometry": "rebuild_only_when_visually_faithful",
            "mixed_text_visuals": "preserve_as_separate_image_if_separation_degrades_fidelity",
        }
    write_json(shared_context_path, shared_context)

    manifest_slides: list[dict[str, Any]] = []
    for idx, job in enumerate(slides, start=1):
        slide_index = int(job.get("index", idx))
        title = str(job.get("title") or f"Slide {slide_index}")
        job_path = jobs_dir / f"slide-{slide_index:02d}.json"
        target_path = render_target_path(run_dir, renderer, slide_index, title)
        payload = {
            "version": shared_context["version"],
            "topic": shared_context["topic"],
            "audience": shared_context["audience"],
            "deck_strategy": shared_context["deck_strategy"],
            "design_system": shared_context["design_system"],
            "renderer": renderer,
            "index": slide_index,
            "title": title,
            "page_role": job.get("page_role", "content"),
            "material": job.get("material", ""),
            "plan": job.get("plan", ""),
            "total_pages": len(slides),
            "target_path": str(target_path),
            "shared_context_path": str(shared_context_path),
            "plan_sha256": plan_sha,
            "task_brief_sha256": brief_sha,
            "task_brief": shared_context['task_brief'],
            "source": source_mode,
        }
        if references:
            payload["image_reference"] = references[idx - 1]
            raw = run_dir / ".workflow/img-source" / Path(references[idx - 1]["source_image_path"]).name
            if job["plan"].get("data_regions") and raw.is_file():
                payload["artwork_before_data"] = str(raw)
            payload["reconstruction_policy"] = shared_context["reconstruction_policy"]
            payload["reconstruction_guide_path"] = str(SKILL_ROOT / "references" / "img-pptd.md")
        write_json(job_path, payload)
        manifest_slides.append({
            "index": slide_index,
            "title": title,
            "job_path": str(job_path),
            "target_path": str(target_path),
            "job_sha256": file_sha256(job_path),
        })

    manifest_path = jobs_dir / "manifest.json"
    write_json(manifest_path, {
        "version": shared_context["version"],
        "renderer": renderer,
        "topic": shared_context["topic"],
        "audience": shared_context["audience"],
        "slide_count": len(slides),
        "plan_sha256": plan_sha,
        "task_brief_sha256": brief_sha,
        "source": source_mode,
        "shared_context_sha256": file_sha256(shared_context_path),
        "shared_context_path": str(shared_context_path),
        "slides": manifest_slides,
    })

    entry = renderer_state(state, renderer)
    entry["jobs"] = {
        "manifest_sha256": file_sha256(manifest_path),
        "manifest_path": str(manifest_path),
        "shared_context_path": str(shared_context_path),
        "status": "prepared",
        "updated_at": utc_now(),
    }
    state["renderer"] = renderer
    state["render_review"] = dict(entry.get("review") or {})
    state["status"] = "render_jobs_prepared"
    save_state(run_dir, state)
    return manifest_path


def img_source_images(run_dir: Path) -> list[Path]:
    img_dir = run_dir / "img"
    return sorted(
        [path for path in img_dir.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    ) if img_dir.exists() else []


def require_complete_img_sources(run_dir: Path) -> list[Path]:
    images = img_source_images(run_dir)
    if not images:
        raise ValueError(f"IMG directory is empty: {run_dir / 'img'}")
    expected = len(slide_jobs(run_dir))
    if expected and len(images) != expected:
        raise ValueError(
            f"IMG page count mismatch: expected {expected} pages from slide-plans.json, found {len(images)}"
        )
    return images


def pptd_image_references(run_dir: Path) -> list[dict[str, Any]]:
    images = require_complete_img_sources(run_dir)
    references = []
    for image, job in zip(images, slide_jobs(run_dir)):
        expected = render_target_path(run_dir, "img", int(job["index"]), job["title"])
        if image.stem != expected.stem:
            raise ValueError(f"IMG page identity mismatch: expected {expected.stem}, found {image.stem}")
        with Image.open(image) as source:
            source.load()
            size = list(source.size)
        references.append({"source_image_path": str(image.resolve()),
                           "source_image_sha256": file_sha256(image), "source_size": size})
    return references


def mark_img_exported_complete(run_dir: Path, pptx_path: Path, images: list[Path]) -> None:
    state = load_state(run_dir)
    state["renderer"] = "img"
    entry = renderer_state(state, "img")
    entry["artifacts"] = {
        **entry.get("artifacts", {}),
        "pptx": {"path": str(pptx_path), "status": "completed", 'sha256': file_sha256(pptx_path)},
    }
    entry["svg_conversion"] = {
        "mode": None,
        "status": "available",
        "source_pptx_path": str(pptx_path),
        "source_images": [str(path) for path in images],
        "available_after_img_export": True,
        "requires_explicit_opt_in": True,
        "additional_model_usage_required": True,
        "updated_at": utc_now(),
    }
    entry["status"] = "completed"
    entry["completed_at"] = utc_now()
    entry['export_plan_sha256'] = file_sha256(run_dir / 'slide-plans.json')
    state["render_review"] = dict(entry.get("review") or {})
    state["status"] = "completed"
    save_state(run_dir, state)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def text_sha256(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def render_img_svg_review(source_image_path: Path, svg_path: Path, preview_path: Path) -> dict[str, float]:
    from pptx_builder import svg_to_png_bytes

    preview_bytes = svg_to_png_bytes(svg_path)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(preview_bytes)
    with Image.open(source_image_path) as source, Image.open(io.BytesIO(preview_bytes)) as rendered:
        source_rgb = source.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
        rendered_rgb = rendered.convert("RGB").resize((1280, 720), Image.Resampling.LANCZOS)
        pixel_mae = sum(ImageStat.Stat(ImageChops.difference(source_rgb, rendered_rgb)).mean) / 3
        edge_mae = sum(ImageStat.Stat(ImageChops.difference(
            source_rgb.filter(ImageFilter.FIND_EDGES), rendered_rgb.filter(ImageFilter.FIND_EDGES)
        )).mean) / 3
    pixel_similarity = max(0.0, 1 - pixel_mae / 255)
    edge_similarity = max(0.0, 1 - edge_mae / 255)
    return {
        "pixel_similarity": round(pixel_similarity, 6),
        "edge_similarity": round(edge_similarity, 6),
        "combined_similarity": round(pixel_similarity * .65 + edge_similarity * .35, 6),
    }


def img_svg_render_environment() -> str:
    """Cache identity for local renderer and installed font files; force-render is also available."""
    from playwright_runtime import playwright_cache

    roots = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
             Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Microsoft/Windows/Fonts"] if os.name == "nt" else [
                 Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".local/share/fonts",
                 Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
    renderer_hashes = [file_sha256(RUNTIME_ROOT / name) for name in ("pptx_builder.py", "playwright_runtime.py")]
    files = []
    for root in roots:
        if root.is_dir():
            files.extend(path for path in root.rglob("*") if path.is_file())
    explicit_browser = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if explicit_browser:
        files.append(Path(explicit_browser))
    cache = playwright_cache()
    fingerprint = [(str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in sorted(set(files))]
    return text_sha256(json.dumps([platform.platform(), package_version("playwright"),
                                  str(cache), sorted(p.name for p in cache.glob("*")), renderer_hashes, fingerprint]))


def _rects_intersect(first, second) -> bool:
    fx, fy, fw, fh = first
    sx, sy, sw, sh = second
    return min(fx + fw, sx + sw) > max(fx, sx) and min(fy + fh, sy + sh) > max(fy, sy)


def _normalize_img_svg_text(value: str) -> str:
    return "".join(value.split())


def _svg_visible_text_items(svg_path: Path) -> list[str]:
    root = ElementTree.fromstring(svg_path.read_text(encoding="utf-8"))
    return [_normalize_img_svg_text("".join(node.itertext())) for node in root.iter()
            if node.tag.rsplit("}", 1)[-1] == "text"]


def _require_text_occurrences(items: list[dict[str, Any]], fragments: list[str], *, complete: bool = True) -> None:
    # Consume each match, so one occurrence cannot satisfy repeated labels.
    remaining = ["".join(fragments)]
    for item in sorted(items, key=lambda item: len(item["text"]), reverse=True):
        text = _normalize_img_svg_text(item["text"])
        for index, fragment in enumerate(remaining):
            if text in fragment:
                before, after = fragment.split(text, 1)
                remaining[index:index + 1] = [before, after]
                break
        else:
            raise ValueError(f"IMG-to-SVG visible text missing from SVG text nodes: {item['id']}: {item['text']}")
    if complete and any(remaining):
        raise ValueError("IMG-to-SVG SVG contains extra text not recorded in visible_text")


def img_svg_text_items(job: dict[str, Any]) -> list[dict[str, Any]]:
    # Old jobs keep their text inventory inside the V3 crop manifest. Read it
    # without recreating the deleted visual inventory or self-attestation gate.
    items = job.get("visible_text")
    crop_path = Path(job["crop_manifest_path"])
    if items is None and crop_path.exists():
        crop = read_json(crop_path)
        items = crop.get("visible_text", crop.get("visible_text_inventory", {}).get("items"))
    if items is None:
        # Legacy jobs may lack text metadata. Seed a checklist from the SVG;
        # the V2 review still requires comparison against the actual source IMG.
        items = [{"id": f"text-{index}", "text": text} for index, text in
                 enumerate(_svg_visible_text_items(Path(job["target_path"])), start=1) if text]
    if not isinstance(items, list):
        raise ValueError("IMG-to-SVG visible_text must be a list of {id, text} items (empty for no text)")
    ids = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip() or item["id"] in ids:
            raise ValueError("IMG-to-SVG visible_text needs unique non-empty ids")
        if not isinstance(item.get("text"), str) or not item["text"].strip():
            raise ValueError("IMG-to-SVG visible_text needs non-empty text")
        ids.add(item["id"])
    return items


def validate_img_svg_crop_manifest(job: dict[str, Any], svg_stats: dict[str, Any]) -> dict[str, Any]:
    svg_path = Path(job["target_path"])
    items = img_svg_text_items(job)
    _require_text_occurrences(items, _svg_visible_text_items(svg_path))
    path = Path(job["crop_manifest_path"])
    if not path.exists():
        if svg_stats["embedded_image_count"]:
            raise ValueError("IMG-to-SVG embedded images need a crop manifest")
        return {}
    manifest = read_json(path)
    for key, expected in (("source_image_path", job["source_image_path"]), ("svg_path", job["target_path"])):
        if Path(manifest[key]).resolve() != Path(expected).resolve():
            raise ValueError(f"IMG-to-SVG crop manifest {key} mismatch")
    root = ElementTree.fromstring(svg_path.read_text(encoding="utf-8"))
    if manifest.get("canvas", {"width": 1280, "height": 720}) != {"width": 1280, "height": 720}:
        raise ValueError("IMG-to-SVG crop canvas must be 1280x720")
    crops = validate_crop_entries(manifest, root, embedded=True)
    text_by_id = {item["id"]: item for item in items}
    # Text boxes are needed only around crop conflicts/backplate replacements.
    local_items = manifest.get("visible_text", manifest.get("visible_text_inventory", {}).get("items", []))
    if not isinstance(local_items, list):
        raise ValueError("IMG-to-SVG crop visible_text must be a list")
    for item in local_items:
        if item["id"] not in text_by_id or item["text"] != text_by_id[item["id"]]["text"]:
            raise ValueError("IMG-to-SVG crop text must match the page visible_text items")
        if "source_box" in item:
            _validated_box(item["source_box"], name="text source_box", canvas_size=(1280, 720))
    boxed_items = {item["id"]: item for item in local_items if "source_box" in item}
    elements = list(root.iter())
    for crop in crops:
        if crop.get("contains_text") is not False:
            raise ValueError("IMG-to-SVG crop must declare contains_text=false for the final pixels")
        overlapping = {key for key, item in boxed_items.items() if _rects_intersect(crop["source_box"], item["source_box"])}
        if crop.get("content_type") != "complex_backplate":
            if overlapping or crop.get("source_contains_text"):
                raise ValueError("IMG-to-SVG crop overlaps visible text; shrink it or use a scrubbed backplate")
            continue
        replacement = crop.get("replacement_text_ids", [])
        if not replacement or len(set(replacement)) != len(replacement) or set(replacement) != overlapping:
            raise ValueError("IMG-to-SVG backplate replacement_text_ids must match boxed text inside the crop")
        removals = crop.get("text_removal_boxes", [])
        if not removals:
            raise ValueError("IMG-to-SVG backplate needs text_removal_boxes")
        if crop.get("text_removal_mode", "light_neutral") not in {"light_neutral", "dark_neutral", "all"}:
            raise ValueError("IMG-to-SVG backplate text_removal_mode is invalid")
        dilation = crop.get("text_removal_dilation", 2)
        if type(dilation) is not int or not 0 <= dilation <= 4:
            raise ValueError("IMG-to-SVG backplate text_removal_dilation must be an integer 0-4")
        cx, cy, cw, ch = crop["source_box"]
        for box in removals:
            rx, ry, rw, rh = _validated_box(box, name="text_removal_box", canvas_size=(1280, 720))
            if rx < cx or ry < cy or rx + rw > cx + cw or ry + rh > cy + ch:
                raise ValueError("IMG-to-SVG text_removal_box must stay inside backplate")
        position = next(i for i, node in enumerate(elements) if node.attrib.get("data-crop-id") == crop["id"])
        later_text = [_normalize_img_svg_text("".join(node.itertext())) for node in elements[position + 1:]
                      if node.tag.rsplit("}", 1)[-1] == "text"]
        for key in replacement:
            tx, ty, tw, th = boxed_items[key]["source_box"]
            if not any(rx <= tx and ry <= ty and rx + rw >= tx + tw and ry + rh >= ty + th for rx, ry, rw, rh in removals):
                raise ValueError(f"IMG-to-SVG backplate removal box must cover replacement text {key}")
        try:
            _require_text_occurrences([text_by_id[key] for key in replacement], later_text, complete=False)
        except ValueError as exc:
            raise ValueError("IMG-to-SVG replacement text must appear after the backplate image") from exc
    return manifest


def img_svg_review_inputs(job: dict[str, Any], environment: str) -> dict[str, Any]:
    crop_path = Path(job["crop_manifest_path"])
    return {
        "version": 2,
        "slide_index": job["index"],
        "source_image_path": str(Path(job["source_image_path"]).resolve()),
        "source_image_sha256": file_sha256(Path(job["source_image_path"])),
        "svg_path": str(Path(job["target_path"]).resolve()),
        "svg_sha256": file_sha256(Path(job["target_path"])),
        "text_sha256": text_sha256(json.dumps(img_svg_text_items(job), ensure_ascii=False, sort_keys=True)),
        "crop_sha256": file_sha256(crop_path) if crop_path.exists() else None,
        "render_environment": environment,
    }


def write_img_svg_review_artifact(job: dict[str, Any], *, environment: str | None = None, force_render: bool = False,
                                  svg_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = img_svg_review_inputs(job, environment or img_svg_render_environment())
    path = Path(job["fidelity_review_path"])
    preview = Path(job["rendered_preview_path"])
    previous = read_json(path, {})
    unchanged = all(previous.get(key) == value for key, value in inputs.items())
    if unchanged and preview.is_file() and previous.get("preview_sha256") == file_sha256(preview) and not force_render:
        return previous
    metrics = render_img_svg_review(Path(job["source_image_path"]), Path(job["target_path"]), preview)
    review = {**inputs, "rendered_preview_path": str(preview), "preview_sha256": file_sha256(preview),
              "automatic_metrics": metrics, "status": "pending_visual_review", "text_checked": False,
              "svg_diagnostics": svg_stats if svg_stats is not None else validate_ppt_compatible_svg(Path(job["target_path"])),
              "reviewer": "", "notes": "", "updated_at": utc_now()}
    write_json(path, review)
    return review


def validate_img_svg_fidelity_review(job: dict[str, Any], review: dict[str, Any], *, environment: str | None = None) -> dict[str, Any]:
    inputs = img_svg_review_inputs(job, environment or img_svg_render_environment())
    if any(review.get(key) != value for key, value in inputs.items()):
        raise ValueError("IMG-to-SVG review is stale; run complete-img-svg and review changed pages")
    preview = Path(job["rendered_preview_path"])
    if not preview.is_file() or review.get("preview_sha256") != file_sha256(preview):
        raise ValueError("IMG-to-SVG review preview changed or is missing; rerun complete-img-svg")
    if review.get("status") != "pass":
        raise RuntimeError(f"IMG-to-SVG visual review is pending: {job['fidelity_review_path']}")
    if review.get("text_checked") is not True or not str(review.get("reviewer", "")).strip() or not str(review.get("notes", "")).strip():
        raise ValueError("IMG-to-SVG passed review needs text_checked, reviewer and concrete notes")
    return review


def prepare_img_svg_jobs(run_dir: Path, state: dict[str, Any]) -> Path:
    images = require_complete_img_sources(run_dir)
    plans = slide_jobs(run_dir)
    jobs_dir = render_jobs_root(run_dir, "img-svg")
    target_dir = run_dir / "img-svg"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    slides = []
    for index, (source, plan) in enumerate(zip(images, plans), start=1):
        slides.append({
            "index": index, "title": plan.get("title", source.stem),
            "source_image_path": str(source), "target_path": str(target_dir / f"{source.stem}.svg"),
            "crop_manifest_path": str(jobs_dir / f"slide-{index:02d}-crops.json"),
            "rendered_preview_path": str(jobs_dir / "reviews" / f"slide-{index:02d}-rendered.png"),
            "fidelity_review_path": str(jobs_dir / "reviews" / f"slide-{index:02d}-fidelity-review.json"),
            "visible_text": [],
        })
    manifest_path = write_json(jobs_dir / "manifest.json", {
        "version": 3, "renderer": "img-svg", "slide_count": len(slides),
        "prompt_path": str(IMG_SVG_PROMPT_PATH), "slides": slides,
    })
    entry = renderer_state(state, "img")
    entry["svg_conversion"].update({"mode": "on", "status": "pending_generation", "manifest_path": str(manifest_path)})
    save_state(run_dir, state)
    return manifest_path


def img_svg_jobs(run_dir: Path, conversion: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = read_json(Path(conversion["manifest_path"]))
    pages = manifest.get("slides", [])
    images = require_complete_img_sources(run_dir)
    if len(pages) != len(images) or manifest.get("slide_count", len(pages)) != len(images):
        raise ValueError("IMG-to-SVG pages mismatch with source images")
    jobs = []
    for index, (page, source) in enumerate(zip(pages, images), start=1):
        # V2 per-page jobs remain readable; they need a new V2 review, not regeneration.
        job = read_json(Path(page["job_path"])) if manifest.get("version", 2) < 3 else page
        expected = run_dir / "img-svg" / f"{source.stem}.svg"
        if job["index"] != index or Path(job["source_image_path"]).resolve() != source.resolve() or Path(job["target_path"]).resolve() != expected.resolve():
            raise ValueError("IMG-to-SVG page mapping/order mismatch")
        for key in ("crop_manifest_path", "rendered_preview_path", "fidelity_review_path"):
            if not is_within(Path(job[key]).resolve(), run_dir.resolve()):
                raise ValueError(f"IMG-to-SVG {key} must remain in the project")
        jobs.append(job)
    actual = {path.resolve() for path in (run_dir / "img-svg").glob("*.svg")}
    expected = {Path(job["target_path"]).resolve() for job in jobs}
    if actual != expected:
        raise ValueError("IMG-to-SVG output mismatch: missing or extra SVG pages")
    return jobs


def validate_ppt_compatible_svg(path: Path) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ElementTree.ParseError) as exc:
        raise ValueError(f"Invalid SVG XML: {path}: {exc}") from exc

    root_name = root.tag.rsplit("}", 1)[-1].lower()
    if root_name != "svg":
        raise ValueError(f"SVG root element is required: {path}")

    view_box = (root.attrib.get("viewBox") or root.attrib.get("viewbox") or "").replace(",", " ").split()
    try:
        normalized_view_box = [float(value) for value in view_box]
    except ValueError as exc:
        raise ValueError(f"SVG viewBox must be numeric: {path}") from exc
    if normalized_view_box != [0.0, 0.0, 1280.0, 720.0]:
        raise ValueError(f"SVG viewBox must be exactly '0 0 1280 720': {path}")

    forbidden = {"foreignobject", "script", "animate", "animatetransform", "animatemotion", "set"}
    raster_area = 0.0
    vector_element_count = 0
    embedded_image_count = 0
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1].lower()
        if local_name in forbidden:
            raise ValueError(f"SVG contains forbidden <{local_name}> element: {path}")
        if local_name in {
            "text", "tspan", "path", "rect", "circle", "ellipse", "line",
            "polyline", "polygon",
        }:
            vector_element_count += 1
        if local_name == "image":
            embedded_image_count += 1
            href = ""
            for attribute, value in element.attrib.items():
                if attribute.rsplit("}", 1)[-1].lower() == "href":
                    href = value or ""
                    break
            allowed_prefixes = (
                "data:image/png;base64,",
                "data:image/jpeg;base64,",
                "data:image/jpg;base64,",
            )
            if not href.startswith(allowed_prefixes):
                raise ValueError(
                    f"SVG <image> must use an embedded Base64 PNG/JPEG data URI: {path}"
                )
            try:
                encoded = href.split(",", 1)[1]
                raster_bytes = base64.b64decode(encoded, validate=True)
                with Image.open(io.BytesIO(raster_bytes)) as raster:
                    raster.verify()
            except (IndexError, binascii.Error, OSError, ValueError) as exc:
                raise ValueError(f"SVG contains invalid embedded raster data: {path}") from exc

            try:
                x = float(element.attrib.get("x", "0"))
                y = float(element.attrib.get("y", "0"))
                width = float(element.attrib.get("width", "0"))
                height = float(element.attrib.get("height", "0"))
            except ValueError as exc:
                raise ValueError(f"SVG <image> geometry must be numeric: {path}") from exc
            if not all(math.isfinite(v) for v in (x, y, width, height)) or width <= 0 or height <= 0:
                raise ValueError(f"SVG <image> width and height must be positive: {path}")
            if x <= 1 and y <= 1 and width >= 1278 and height >= 718:
                raise ValueError(
                    f"SVG must not wrap the complete source slide in one full-page <image>: {path}"
                )
            raster_area += width * height
        for attribute, value in element.attrib.items():
            if attribute.rsplit("}", 1)[-1].lower().startswith("on"):
                raise ValueError(f"SVG contains an event handler: {path}")
            if (
                attribute.rsplit("}", 1)[-1].lower() == "href"
                and value
                and not value.startswith(("#", "data:image/png;base64,", "data:image/jpeg;base64,", "data:image/jpg;base64,"))
            ):
                raise ValueError(f"SVG contains an external href: {path}")

    source = path.read_text(encoding="utf-8").lower()
    if "@import" in source:
        raise ValueError(f"SVG contains external stylesheet data: {path}")
    for reference in re.findall(r"url\s*\((.*?)\)", source, re.DOTALL):
        if not reference.strip().strip("\"'").startswith("#"):
            raise ValueError(f"SVG contains an external CSS resource: {path}")
    if vector_element_count == 0:
        raise ValueError(f"SVG must contain vector text or shape elements: {path}")
    return {
        "vector_element_count": vector_element_count,
        "embedded_image_count": embedded_image_count,
        "embedded_raster_area": raster_area,
        "embedded_raster_ratio": round(raster_area / (1280 * 720), 6),
    }


def complete_img_svg_generation(run_dir: Path, *, force_render: bool = False) -> list[Path]:
    state = load_state(run_dir)
    if state.get("renderer") != "img":
        raise RuntimeError("IMG-to-SVG completion is only available for the img renderer")
    entry = renderer_state(state, "img")
    conversion = entry["svg_conversion"]
    if conversion.get("mode") != "on":
        raise RuntimeError("IMG-to-SVG conversion is not enabled")
    jobs = img_svg_jobs(run_dir, conversion)
    environment = img_svg_render_environment()
    pending = False
    for job in jobs:
        stats = validate_ppt_compatible_svg(Path(job["target_path"]))
        validate_img_svg_crop_manifest(job, stats)
        review = write_img_svg_review_artifact(job, environment=environment, force_render=force_render, svg_stats=stats)
        if review["status"] != "pass":
            pending = True
        else:
            validate_img_svg_fidelity_review(job, review, environment=environment)
    conversion["status"] = "pending_generation" if pending else "completed"
    entry["status"] = "img_svg_review_pending" if pending else "img_svg_export_ready"
    state["status"] = entry["status"]
    save_state(run_dir, state)
    return [] if pending else [Path(job["target_path"]) for job in jobs]


def validate_pptd_project(run_dir: Path) -> dict[str, Any]:
    ensure_render_ready(run_dir, "pptd")
    require_current_render_jobs(run_dir, 'pptd')
    entry = renderer_state(load_state(run_dir), "pptd")
    if entry.get("source") == "img":
        current = pptd_image_references(run_dir)
        jobs_root = render_jobs_root(run_dir, "pptd")
        for reference, job in zip(current, slide_jobs(run_dir)):
            payload = read_json(jobs_root / f"slide-{int(job['index']):02d}.json")
            if payload.get("image_reference") != reference:
                raise ValueError("IMG reference changed; prepare jobs and review/rebuild affected PPTD pages before export")
    plan = slide_plan_document(run_dir)
    apply_pptd_data_regions(run_dir, plan)
    from pptd_runtime import validate_project
    return validate_project(run_dir / "pptd", expected_pages=len(plan["slides"]))


def export_pptd(run_dir: Path) -> Path:
    report = validate_pptd_project(run_dir)
    from pptd_runtime import export_project
    output = run_dir / renderer_pptx_name(run_dir, "pptd")
    summary = export_project(run_dir / "pptd", output)
    write_json(run_dir / ".workflow/pptd-export.json", summary)
    write_slide_status(run_dir, {
        f"{i:02d}": {"page_path": path, "validation_status": "structure_and_pptx_verified",
                      "visual_review": "not_verified_by_helper", "export_ready": True}
        for i, path in enumerate(report["pages"], start=1)
    }, renderer="pptd")
    mark_completed(run_dir, "pptd", {"pptx": output, "project": run_dir / "pptd"})
    from pptd_visual import build_payload
    state = load_state(run_dir)
    renderer_state(state, 'pptd')['export_project_sha256'] = build_payload(run_dir / 'pptd')[2]
    save_state(run_dir, state)
    return output


def cmd_validate_pptd(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    print(json.dumps(validate_pptd_project(run_dir), ensure_ascii=False), flush=True)


def cmd_export_pptd_images(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    validate_pptd_project(run_dir)
    from pptd_visual import export_images
    summary = export_images(run_dir / "pptd", force=args.force)
    state = load_state(run_dir)
    renderer_state(state, "pptd")["visual_qa"] = summary
    save_state(run_dir, state)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def cmd_open_pptd_editor(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    validate_pptd_project(run_dir)
    from pptd_runtime import serve_editor
    serve_editor(run_dir / "pptd", port=args.port, open_browser=args.open)


def cmd_compare_pptd(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    report = validate_pptd_project(run_dir)
    from pptd_visual import build_comparison, build_payload
    manifest = read_json(run_dir / 'pptd/.qa-images/manifest.json')
    if manifest.get('source_sha256') != build_payload(run_dir / 'pptd')[2]:
        raise ValueError('PPTD changed since image export; run export-pptd-images --force')
    references = pptd_image_references(run_dir)
    images = manifest.get('images') or []
    if [item.get('page') for item in images] != report['pages'] or len(images) != len(references):
        raise ValueError('QA/source page mapping differs from PPTD manifest')
    from pptd_runtime import project_path
    selected = set(args.pages or range(1, len(images) + 1))
    if not selected.issubset(set(range(1, len(images) + 1))):
        raise ValueError('comparison page index out of range')
    result = build_comparison(run_dir,
        {f'{i:02}': Path(ref['source_image_path']) for i, ref in enumerate(references, 1) if i in selected},
        {f'{i:02}': project_path(run_dir / 'pptd/.qa-images', item['image']) for i, item in enumerate(images, 1) if i in selected},
        run_dir / '.workflow/pptd-comparison.jpg')
    print(json.dumps(result, ensure_ascii=False), flush=True)


def cmd_finalize(args: argparse.Namespace) -> None:
    from delivery import finalize_delivery
    result = finalize_delivery(normalize_run_dir(args.run_dir), apply=args.apply,
                               discard=args.discard, retain=args.keep)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


def cmd_restore_img(args: argparse.Namespace) -> None:
    from delivery import restore_img_sources
    paths = restore_img_sources(normalize_run_dir(args.run_dir), Path(args.pptx))
    print(json.dumps({'restored': [str(path) for path in paths]}, ensure_ascii=False), flush=True)


def export_img(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    require_current_render_jobs(run_dir, 'img')
    from pptx import Presentation
    from pptx.util import Inches

    images = require_complete_img_sources(run_dir)
    materialize_data_images(run_dir, images, slide_plan_document(run_dir))

    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    for image in images:
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(image), 0, 0, width=prs.slide_width, height=prs.slide_height)

    pptx_path = run_dir / renderer_pptx_name(run_dir, "img")
    prs.save(str(pptx_path))
    write_slide_status(run_dir, {
        f"{i:02d}": {
            "title": image.stem,
            "page_role": "image",
            "validation_status": "codex_imagegen",
            "export_ready": True,
            "image_path": str(image),
        }
        for i, image in enumerate(images, start=1)
    }, renderer="img")
    mark_img_exported_complete(run_dir, pptx_path, images)
    return pptx_path


def export_img_svg(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    state = load_state(run_dir)
    if state.get("renderer") != "img":
        raise RuntimeError("IMG-to-SVG export is only available for the img renderer")
    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    if conversion.get("mode") != "on" or conversion.get("status") != "completed":
        raise RuntimeError("IMG-to-SVG pages are not complete. Finish the model conversion before export.")

    from pptx_builder import build_native_svg_pptx

    svg_dir = run_dir / "img-svg"
    jobs = img_svg_jobs(run_dir, conversion)
    environment = img_svg_render_environment()
    for job in jobs:
        validate_img_svg_fidelity_review(job, read_json(Path(job["fidelity_review_path"])), environment=environment)
        stats = validate_ppt_compatible_svg(Path(job["target_path"]))
        validate_img_svg_crop_manifest(job, stats)

    pptx_path = run_dir / renderer_pptx_name(run_dir, "img-svg")
    build_native_svg_pptx(svg_dir, pptx_path, svg_paths=[Path(job["target_path"]) for job in jobs])

    manifest = read_json(Path(conversion["manifest_path"]))
    slides = manifest.get("slides", [])
    write_slide_status(run_dir, {
        f"{int(item.get('index', i)):02d}": {
            "title": item.get("title", f"Slide {i}"),
            "page_role": "vectorized_image",
            "validation_status": "codex_img_to_hybrid_svg",
            "export_ready": True,
            "source_image_path": item.get("source_image_path"),
            "svg_path": item.get("target_path"),
        }
        for i, item in enumerate(slides, start=1)
    }, renderer="img-svg")

    chain_manifest = write_json(run_dir / "img-svg-chain.json", {
        "version": 1,
        "source_renderer": "img",
        "conversion": "vision_model_img_to_hybrid_svg",
        "source_pptx_path": conversion.get("source_pptx_path"),
        "svg_dir": str(svg_dir),
        "svg_pptx_path": str(pptx_path),
        "slides": slides,
        "updated_at": utc_now(),
    })

    state = load_state(run_dir)
    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    entry["svg_conversion"] = {
        **conversion,
        "status": "exported",
        "pptx_path": str(pptx_path),
        "exported_at": utc_now(),
    }
    save_state(run_dir, state)
    mark_completed(run_dir, "img", {
        "svg_pptx": pptx_path,
        "svg_chain_manifest": chain_manifest,
    })
    return pptx_path


def clean_render_outputs(run_dir: Path) -> None:
    root = run_dir.resolve()
    # Keep renderer source dirs. Codex authors img/pptd directly in this branch,
    # so default cleanup should only remove derived outputs and review artifacts.
    for name in ("reviews", "editable"):
        target = (run_dir / name).resolve()
        if target.exists():
            if root not in target.parents:
                raise RuntimeError(f"refusing to delete outside run dir: {target}")
            shutil.rmtree(target)
            print(f"deleted={target}", flush=True)
    for pattern in ("*.pptx", "slide-status*.json", "editable-ppt-chain.json", "img-svg-chain.json"):
        for target in run_dir.glob(pattern):
            resolved = target.resolve()
            if root != resolved.parent:
                raise RuntimeError(f"refusing to delete outside run dir: {resolved}")
            target.unlink()
            print(f"deleted={resolved}", flush=True)


def cmd_init(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir, topic=args.topic)
    run_dir.mkdir(parents=True, exist_ok=True)
    init_state(run_dir, topic=args.topic, audience=args.audience, pages=args.pages, research=args.research or "")
    print(f"run_dir={run_dir}", flush=True)


TASK_BRIEF_FIELDS = ("objective", "constraints", "source_paths", "pending_work")


def _validate_task_brief(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("task brief must be a JSON object")
    missing = [field for field in TASK_BRIEF_FIELDS if field not in value]
    if missing:
        raise ValueError("task brief missing required fields: " + ", ".join(missing))
    if not isinstance(value["objective"], str) or not value["objective"].strip():
        raise ValueError("task brief objective must be a non-empty string")
    for field in ("constraints", "source_paths", "pending_work"):
        if not isinstance(value[field], list) or any(not isinstance(item, str) for item in value[field]):
            raise ValueError(f"task brief {field} must be a list of strings")
    if "next_action" in value and (not isinstance(value["next_action"], str) or not value["next_action"].strip()):
        raise ValueError("task brief next_action must be a non-empty string when present")
    # Reject recognizable credential assignments, not harmless instructions about secrets.
    encoded = json.dumps(value, ensure_ascii=False)
    if re.search(r'sk-(?:proj-)?[A-Za-z0-9_-]{16,}|(?:API_KEY|PASSWORD|TOKEN)\s*[=:]\s*\S+', encoded, re.I):
        raise ValueError("task brief must not contain credential values")
    return {key: value[key] for key in (*TASK_BRIEF_FIELDS, "next_action") if key in value}


def cmd_checkpoint(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    brief = _validate_task_brief(read_json(Path(args.file)))
    previous = task_brief_hash(run_dir)
    write_json(run_dir / ".workflow" / "task-brief.json", brief)
    if previous != task_brief_hash(run_dir) and (run_dir / STATE_FILE).is_file():
        state = load_state(run_dir)
        for entry in state.get('renderers', {}).values():
            if entry.get('jobs'):
                entry['jobs']['status'] = 'stale'
        save_state(run_dir, state)
    print(f"task_brief={run_dir / '.workflow' / 'task-brief.json'}", flush=True)


def cmd_resume(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state_path = run_dir / STATE_FILE
    if not state_path.is_file():
        from delivery import inspect_delivery
        delivery = read_json(run_dir / "slide-plans.json", default={}).get("_delivery")
        issues = inspect_delivery(run_dir) if delivery else ['no delivery provenance']
        print(json.dumps({"run_dir": str(run_dir), "state": 'needs_verification' if issues else 'delivered',
                          "delivery": delivery, 'issues': issues}, ensure_ascii=False), flush=True)
        return
    state = load_state(run_dir)
    brief = current_task_brief(run_dir)
    stale_jobs = []
    for renderer, entry in (state.get("renderers") or {}).items():
        if render_jobs_issue(run_dir, renderer):
            stale_jobs.append(renderer)
    artifact_status = {}
    delivered = read_json(run_dir / 'slide-plans.json', default={}).get('_delivery') or {}
    for name, filename in ARTIFACT_FILES.items():
        if not (run_dir / filename).is_file():
            artifact_status[name] = 'missing'
        else:
            try:
                require_approved(run_dir, name)
                artifact_status[name] = 'approved'
            except RuntimeError:
                from delivery import artifact_digest
                inherited = name not in state.get('artifacts', {}) and delivered.get('artifact_sha256', {}).get(name) == artifact_digest(run_dir / filename)
                artifact_status[name] = 'previously_delivered' if inherited else 'needs_review'
    pending = next((name for name, status in artifact_status.items() if status not in {'approved', 'previously_delivered'}), None)
    active = state.get('renderer')
    output_missing = []
    for renderer, entry in state.get('renderers', {}).items():
        for name, artifact in entry.get('artifacts', {}).items():
            if artifact.get('status') == 'completed' and not Path(artifact.get('path', '')).exists():
                output_missing.append(f'{renderer}.{name}')
    planning = planning_action(state)
    if planning and pending in {None, "slide_plans"}:
        next_action = planning
    elif pending:
        next_action = f"{'author' if artifact_status[pending] == 'missing' else 'preview/review'} {pending}"
    elif not active:
        next_action = 'choose-renderer'
    elif active in stale_jobs:
        next_action = 'prepare-render-jobs'
    elif state.get('status') == 'completed' and not output_missing:
        next_action = 'finish review and finalize'
    else:
        next_action = 'continue renderer work'
    effective_state = ('needs_review' if pending else 'needs_rebuild' if active in stale_jobs or output_missing else state.get('status'))
    print(json.dumps({"run_dir": str(run_dir), "state": effective_state,
                      'recorded_state': state.get('status'), 'approvals': artifact_status, 'missing_outputs': output_missing,
                      "renderer": state.get("renderer"),
                      "plan_mode": state["plan_mode"],
                      "style_samples": state.get("style_samples"),
                      "design_choice": state.get("design_choice"),
                      "source": (state.get("renderers", {}).get(state.get("renderer"), {}) or {}).get("source"),
                      "brief": brief, "previews": {name: str(run_dir / PREVIEW_FILES[name]) for name in ARTIFACT_FILES},
                      "stale_jobs": stale_jobs, "next_action": next_action}, ensure_ascii=False), flush=True)


def require_plan_direction(run_dir: Path) -> None:
    state = load_state(run_dir)
    if state["plan_mode"] == "legacy":
        return
    require_approved(run_dir, "contents")
    action = planning_action(state)
    if action:
        raise RuntimeError(f"Full slide planning is waiting for {action}")


def cmd_save_artifact(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.artifact == "slide_plans":
        require_plan_direction(run_dir)
    source = Path(args.file)
    data = read_json(source)
    target = write_json(run_dir / ARTIFACT_FILES[args.artifact], data)
    preview = preview_artifact(run_dir, args.artifact)
    print(f"{args.artifact}={target}", flush=True)
    print(f"preview={preview}", flush=True)


def cmd_preview(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    if args.artifact == "slide_plans":
        require_plan_direction(run_dir)
    preview = preview_artifact(run_dir, args.artifact)
    print(f"preview={preview}", flush=True)


def cmd_approve(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    if args.artifact not in state.get("artifacts", {}):
        raise ValueError(f"unknown artifact: {args.artifact}")
    if args.artifact == "slide_plans":
        require_plan_direction(run_dir)
        slide_plan_document(run_dir)
    artifact_entry = state["artifacts"][args.artifact]
    if artifact_entry.get("status") == "stale":
        raise RuntimeError("regenerate preview before approval")
    artifact_path = Path(artifact_entry["path"])
    preview_path = Path(artifact_entry["preview_path"])
    if not artifact_path.is_file() or not preview_path.is_file():
        raise RuntimeError(f"{args.artifact} preview or source is missing; regenerate preview first")
    if (artifact_entry.get('sha256') != file_sha256(artifact_path) or
            artifact_entry.get('preview_sha256') != file_sha256(preview_path)):
        raise RuntimeError('artifact or preview changed since preview; regenerate preview before approval')
    state.setdefault("approvals", {})[args.artifact] = True
    state["artifacts"][args.artifact]["status"] = "approved"
    state["artifacts"][args.artifact]["approved_at"] = utc_now()
    state["status"] = f"{args.artifact}_approved"
    save_state(run_dir, state)
    print(f"approved={args.artifact}", flush=True)
    if args.artifact == "contents":
        print(f"next={planning_action(state) or 'write-and-preview-slide-plans'}", flush=True)
    if args.artifact == "slide_plans" and not state.get("renderer"):
        print("next=choose-renderer", flush=True)
        print("recommended_renderer=img", flush=True)


def cmd_choose_renderer(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    require_approved(run_dir, "slide_plans")
    if args.renderer not in {"img", "pptd"}:
        raise ValueError("renderer must be img or pptd")
    source = getattr(args, "source", "plans")
    if source not in {"plans", "img"} or (source == "img" and args.renderer != "pptd"):
        raise ValueError("--source img is only supported for PPTD")
    if source == "img":
        pptd_image_references(run_dir)
    state = load_state(run_dir)
    state["renderer"] = args.renderer
    entry = renderer_state(state, args.renderer)
    if entry.get('source', 'plans') != source and entry.get('jobs'):
        entry['jobs']['status'] = 'stale'
    entry["source"] = source
    entry["review"] = {**RENDER_REVIEW_NOT_APPLICABLE, "confirmed_at": utc_now()}
    entry["status"] = "render_ready"
    state["render_review"] = dict(entry["review"])
    state["status"] = "render_ready"
    save_state(run_dir, state)
    print(f"renderer={args.renderer}", flush=True)
    print(f"branch_guide={SKILL_ROOT / 'references' / (args.renderer + '.md')}", flush=True)
    print("next=prepare-render-jobs", flush=True)


def cmd_choose_img_svg(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    if state.get("renderer") != "img":
        raise RuntimeError("IMG-to-SVG conversion is only available for the img renderer")
    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    if conversion.get("status") not in {"available", "skipped"}:
        raise RuntimeError(
            "IMG-to-SVG conversion is only available after the IMG PPTX has been exported"
        )
    source_pptx = Path(str(conversion.get("source_pptx_path") or ""))
    if not source_pptx.is_file():
        raise RuntimeError("The exported IMG PPTX is missing; re-export it before starting IMG-to-SVG conversion")

    if args.mode == "on":
        conversion.update({
            "mode": "on",
            "status": "pending_generation",
            "confirmed_at": utc_now(),
        })
        entry["svg_conversion"] = conversion
        save_state(run_dir, state)
        manifest = prepare_img_svg_jobs(run_dir, load_state(run_dir))
        print("img_svg_mode=on", flush=True)
        print(f"img_svg_jobs={manifest}", flush=True)
        print("next=complete-img-svg", flush=True)
        return

    entry["svg_conversion"] = {
        **conversion,
        "mode": "off",
        "status": "skipped",
        "confirmed_at": utc_now(),
    }
    entry["status"] = "completed"
    entry["completed_at"] = utc_now()
    state["status"] = "completed"
    save_state(run_dir, state)
    print("img_svg_mode=off", flush=True)
    print("completed=img", flush=True)


def cmd_complete_img_svg(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    svg_paths = complete_img_svg_generation(run_dir, force_render=getattr(args, "force_render", False))
    print(f"img_svg_completed={len(svg_paths)}", flush=True)
    print("next=export-img-svg" if svg_paths else "next=review-img-svg", flush=True)


def cmd_export_img_svg(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    out = export_img_svg(run_dir)
    print(f"completed={out}", flush=True)
    print("post_export_guidance=office-convert-svg-to-shape", flush=True)
    print("office_editability=vector-shapes-not-semantic-text-or-charts", flush=True)


def cmd_prepare_render_jobs(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    renderer = args.renderer or load_state(run_dir).get("renderer")
    if renderer not in {"img", "pptd"}:
        raise RuntimeError("renderer must be img or pptd")
    manifest = prepare_render_jobs(run_dir, renderer)
    print(f"render_jobs={manifest}", flush=True)


def cmd_export(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    renderer = args.renderer or state.get("renderer")
    if renderer:
        ensure_render_ready(run_dir, renderer)
    if renderer == "pptd":
        out = export_pptd(run_dir)
    elif renderer == "img":
        out = export_img(run_dir)
    else:
        raise ValueError("renderer must be img or pptd")
    if renderer == "img":
        print(f"img_pptx={out}", flush=True)
        print(f"completed={out}", flush=True)
        print("workflow_complete=yes", flush=True)
        print("user_reply_required=no", flush=True)
        print("offer_img_svg=yes", flush=True)
        print("offer_img_pptd=yes", flush=True)
        print("img_pptd_next=choose-renderer --renderer pptd --source img", flush=True)
        print("img_svg_conversion=available_on_explicit_request", flush=True)
        print("img_svg_editability=powerpoint-convert-to-shape", flush=True)
        print("img_svg_additional_model_usage=yes", flush=True)
        print("optional_next=choose-img-svg --mode on", flush=True)
    else:
        print(f"completed={out}", flush=True)


def cmd_status(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    print(f"run_dir={run_dir}", flush=True)
    print(f"status={state.get('status')}", flush=True)
    print(f"renderer={state.get('renderer')}", flush=True)
    review = state.get("render_review") or {}
    print(f"review_mode={review.get('mode')}", flush=True)
    print(f"review_status={review.get('status')}", flush=True)
    next_steps = {
        "img_svg_generation_pending": "complete-img-svg",
        "img_svg_export_ready": "export-img-svg",
    }
    if state.get("status") in next_steps:
        print(f"next={next_steps[state['status']]}", flush=True)
    for name, entry in sorted((state.get("artifacts") or {}).items()):
        print(f"{name}: {entry.get('status')} {entry.get('path')}", flush=True)
    for renderer_name, entry in sorted((state.get("renderers") or {}).items()):
        renderer_review = entry.get("review") or {}
        print(
            f"renderer[{renderer_name}]: status={entry.get('status')} "
            f"review={renderer_review.get('mode')}/{renderer_review.get('status')}",
            flush=True,
        )
        if renderer_name == "img":
            conversion = entry.get("svg_conversion") or {}
            print(
                f"renderer[img].svg_conversion: mode={conversion.get('mode')} "
                f"status={conversion.get('status')}",
                flush=True,
            )
        for artifact_name, artifact_entry in sorted((entry.get("artifacts") or {}).items()):
            print(f"renderer[{renderer_name}].{artifact_name}: {artifact_entry.get('status')} {artifact_entry.get('path')}", flush=True)
    slides = read_json(run_dir / "slide-status.json", default={}).get("slides") or {}
    if slides:
        ready = sum(1 for item in slides.values() if item.get("export_ready"))
        print(f"slides_ready={ready}/{len(slides)}", flush=True)
    patterns = {"pptd/pages": "*.page", "img": "*.*", "img-svg": "*.svg"}
    for name, pattern in patterns.items():
        count = len(list((run_dir / name).glob(pattern))) if (run_dir / name).exists() else 0
        if count:
            print(f"{name}_files={count}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex-skill PPT workflow artifact helper")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--topic", required=True)
    init.add_argument("--audience", default="通用受众")
    init.add_argument("--pages", default="12-15页")
    init.add_argument("--research", default="")
    init.add_argument("--run-dir", default=None)
    init.set_defaults(func=cmd_init)

    checkpoint = sub.add_parser("checkpoint", help="save the compact task brief used for resumption")
    checkpoint.add_argument("--run-dir", required=True)
    checkpoint.add_argument("--file", required=True)
    checkpoint.set_defaults(func=cmd_checkpoint)

    resume = sub.add_parser("resume", help="show compact resumable workflow state")
    resume.add_argument("--run-dir", required=True)
    resume.set_defaults(func=cmd_resume)

    save = sub.add_parser("save-artifact")
    save.add_argument("--run-dir", required=True)
    save.add_argument("--artifact", choices=sorted(ARTIFACT_FILES), required=True)
    save.add_argument("--file", required=True)
    save.set_defaults(func=cmd_save_artifact)

    preview = sub.add_parser("preview")
    preview.add_argument("--run-dir", required=True)
    preview.add_argument("--artifact", choices=sorted(ARTIFACT_FILES), required=True)
    preview.set_defaults(func=cmd_preview)

    approve = sub.add_parser("approve")
    approve.add_argument("--run-dir", required=True)
    approve.add_argument("--artifact", choices=sorted(ARTIFACT_FILES), required=True)
    approve.set_defaults(func=cmd_approve)

    plan_mode = sub.add_parser("choose-plan-mode", help="plan directly or explore sample images first")
    plan_mode.add_argument("--run-dir", required=True)
    plan_mode.add_argument("--mode", choices=("direct", "samples"), default="samples")
    plan_mode.set_defaults(func=cmd_choose_plan_mode)

    style_samples = sub.add_parser("record-style-samples",
                                   help="record four two-page imagegen alternatives before full slide plans")
    style_samples.add_argument("--run-dir", required=True)
    style_samples.add_argument("--file", required=True,
                               help="JSON containing four styles, each with page numbers, short plans and generated image paths")
    style_samples.set_defaults(func=cmd_record_style_samples)

    choose_style = sub.add_parser("choose-style",
                                  help="record the user's free-form visual direction or blend")
    choose_style.add_argument("--run-dir", required=True)
    choose_style.add_argument("--preference", required=True,
                              help="free-form description, including blends or screenshot references")
    choose_style.set_defaults(func=cmd_choose_style)

    choose = sub.add_parser("choose-renderer")
    choose.add_argument("--run-dir", required=True)
    choose.add_argument("--renderer", choices=["img", "pptd"], required=True)
    choose.add_argument("--source", choices=["plans", "img"], default="plans",
                        help="PPTD may reconstruct existing IMG pages; default uses approved plans")
    choose.set_defaults(func=cmd_choose_renderer)

    choose_img_svg = sub.add_parser("choose-img-svg")
    choose_img_svg.add_argument("--run-dir", required=True)
    choose_img_svg.add_argument("--mode", choices=["off", "on"], required=True)
    choose_img_svg.set_defaults(func=cmd_choose_img_svg)

    jobs = sub.add_parser("prepare-render-jobs")
    jobs.add_argument("--run-dir", required=True)
    jobs.add_argument("--renderer", choices=["img", "pptd"], default=None)
    jobs.set_defaults(func=cmd_prepare_render_jobs)

    complete_img_svg = sub.add_parser("complete-img-svg")
    complete_img_svg.add_argument("--run-dir", required=True)
    complete_img_svg.add_argument("--force-render", action="store_true", help="Regenerate previews and invalidate visual reviews")
    complete_img_svg.set_defaults(func=cmd_complete_img_svg)

    export_img_svg_parser = sub.add_parser("export-img-svg")
    export_img_svg_parser.add_argument("--run-dir", required=True)
    export_img_svg_parser.set_defaults(func=cmd_export_img_svg)

    export = sub.add_parser("export")
    export.add_argument("--run-dir", required=True)
    export.add_argument("--renderer", choices=["img", "pptd"], default=None)
    export.set_defaults(func=cmd_export)

    clean = sub.add_parser("clean-render")
    clean.add_argument("--run-dir", required=True)
    clean.set_defaults(func=lambda args: clean_render_outputs(normalize_run_dir(args.run_dir)))

    validate = sub.add_parser("validate-pptd")
    validate.add_argument("--run-dir", required=True)
    validate.set_defaults(func=cmd_validate_pptd)

    images = sub.add_parser("export-pptd-images")
    images.add_argument("--run-dir", required=True)
    images.add_argument("--force", action="store_true")
    images.set_defaults(func=cmd_export_pptd_images)

    compare = sub.add_parser('compare-pptd', help='build IMG/PPTD comparison images without HTML')
    compare.add_argument('--run-dir', required=True)
    compare.add_argument('--pages', nargs='+', type=int, help='optional one-based page indexes')
    compare.set_defaults(func=cmd_compare_pptd)

    finalize = sub.add_parser('finalize', help='inspect or clean temporary delivery files')
    finalize.add_argument('--run-dir', required=True)
    finalize.add_argument('--apply', action='store_true')
    finalize.add_argument('--discard', action='append', default=[], help='confirmed generated scratch path')
    finalize.add_argument('--keep', action='append', default=[], help='explicitly requested extra deliverable')
    finalize.set_defaults(func=cmd_finalize)

    restore = sub.add_parser('restore-img', help='recover original IMG pixels from retained image PPTX')
    restore.add_argument('--run-dir', required=True)
    restore.add_argument('--pptx', required=True)
    restore.set_defaults(func=cmd_restore_img)

    editor = sub.add_parser("open-pptd-editor")
    editor.add_argument("--run-dir", required=True)
    editor.add_argument("--port", type=int, default=0)
    editor.add_argument("--open", action="store_true", help="Open the system browser")
    editor.set_defaults(func=cmd_open_pptd_editor)

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
