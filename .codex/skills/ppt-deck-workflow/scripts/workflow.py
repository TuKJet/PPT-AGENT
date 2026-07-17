from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image

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

from filename_utils import safe_filename_part, slide_filename

STATE_FILE = "workflow-state.json"
ARTIFACT_FILES = {
    "outline": "outline.json",
    "contents": "contents.json",
    "slide_plans": "slide-plans.json",
}
PREVIEW_FILES = {
    "outline": "outline-preview.md",
    "contents": "contents-preview.md",
    "slide_plans": "slide-plans-preview.md",
}
COMMON_ARTIFACT_KEYS = set(ARTIFACT_FILES)
RENDER_REVIEW_NOT_APPLICABLE = {
    "mode": "off",
    "status": "not_applicable",
}


def default_img_svg_conversion() -> dict[str, Any]:
    return {
        "mode": None,
        "status": "waiting_for_img_export",
    }


def default_state() -> dict[str, Any]:
    return {
        "version": 5,
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
    }


def default_renderer_state(renderer: str | None = None) -> dict[str, Any]:
    review = {"mode": None, "status": "not_applicable"}
    if renderer in {"html", "svg"}:
        review = {"mode": None, "status": "pending_choice"}
    elif renderer == "img":
        review = dict(RENDER_REVIEW_NOT_APPLICABLE)
    state = {
        "status": "new",
        "artifacts": {},
        "review": review,
    }
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

    normalized_renderers: dict[str, Any] = {}
    for renderer, entry in renderers.items():
        normalized = default_renderer_state(renderer)
        if isinstance(entry, dict):
            normalized.update(entry)
            normalized["artifacts"] = dict(normalized.get("artifacts") or {})
            normalized["review"] = dict(normalized.get("review") or default_renderer_state(renderer)["review"])
        if renderer == "img":
            conversion = normalized.get("svg_conversion")
            normalized["svg_conversion"] = {
                **default_img_svg_conversion(),
                **(dict(conversion) if isinstance(conversion, dict) else {}),
            }
        normalized_renderers[renderer] = normalized

    merged["artifacts"] = artifacts
    merged["renderers"] = normalized_renderers
    return merged


def renderer_state(state: dict[str, Any], renderer: str) -> dict[str, Any]:
    renderers = state.setdefault("renderers", {})
    entry = renderers.get(renderer)
    if not isinstance(entry, dict):
        entry = default_renderer_state(renderer)
        renderers[renderer] = entry
        return entry
    normalized = default_renderer_state(renderer)
    normalized.update(entry)
    normalized["artifacts"] = dict(normalized.get("artifacts") or {})
    normalized["review"] = dict(normalized.get("review") or default_renderer_state(renderer)["review"])
    if renderer == "img":
        conversion = normalized.get("svg_conversion")
        normalized["svg_conversion"] = {
            **default_img_svg_conversion(),
            **(dict(conversion) if isinstance(conversion, dict) else {}),
        }
    renderers[renderer] = normalized
    return normalized


def load_state(run_dir: Path) -> dict[str, Any]:
    return _normalize_state(read_json(run_dir / STATE_FILE, default=default_state()))


def save_state(run_dir: Path, state: dict[str, Any]) -> Path:
    normalized = _normalize_state(state)
    normalized["version"] = 5
    normalized["execution"] = "codex-skill"
    normalized["updated_at"] = utc_now()
    return write_json(run_dir / STATE_FILE, normalized)


def init_state(run_dir: Path, *, topic: str, audience: str, pages: str, research: str) -> dict[str, Any]:
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
    })
    save_state(run_dir, state)
    return state


def ensure_render_ready(run_dir: Path, renderer: str) -> None:
    state = load_state(run_dir)
    if renderer not in {"html", "svg"}:
        return
    review = renderer_state(state, renderer).get("review") or {}
    review_status = review.get("status")
    review_mode = review.get("mode")
    if review_status == "pending_choice":
        raise RuntimeError(f"{renderer} review preference is not confirmed. Confirm review preference first.")
    if review_mode == "on" and review_status != "completed":
        raise RuntimeError(f"{renderer} review subflow is not complete. Complete the review subflow first.")


def mark_artifact(run_dir: Path, state: dict[str, Any], name: str, path: Path, preview_path: Path) -> None:
    state.setdefault("artifacts", {})[name] = {
        "path": str(path),
        "preview_path": str(preview_path),
        "status": "pending_review",
        "updated_at": utc_now(),
    }
    state.setdefault("approvals", {})[name] = False
    state["status"] = f"{name}_pending_review"
    save_state(run_dir, state)


def require_approved(run_dir: Path, artifact: str) -> None:
    state = load_state(run_dir)
    if not state.get("approvals", {}).get(artifact):
        preview = state.get("artifacts", {}).get(artifact, {}).get("preview_path")
        detail = f" Review {preview} first." if preview else ""
        raise RuntimeError(f"{artifact} is not approved.{detail}")


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


def write_plans_preview(data: dict[str, Any], path: Path) -> Path:
    lines = ["# Slide Plans Preview", ""]
    for job in data.get("slides", []):
        lines.extend([
            f"## {int(job['index']):02d}. {job['title']}",
            "",
            f"- role: {job.get('page_role', 'content')}",
            "",
            str(job.get("plan", "")).strip(),
            "",
        ])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def preview_artifact(run_dir: Path, artifact: str) -> Path:
    data_path = run_dir / ARTIFACT_FILES[artifact]
    preview_path = run_dir / PREVIEW_FILES[artifact]
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
    data = read_json(run_dir / "slide-plans.json", default={"slides": []})
    return list(data.get("slides") or [])


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
    entry["artifacts"] = {
        **entry.get("artifacts", {}),
        **{
            name: {"path": str(path), "status": "completed"}
            for name, path in artifacts.items()
        },
    }
    state["render_review"] = dict(entry.get("review") or {})
    state["status"] = "completed"
    save_state(run_dir, state)


def render_jobs_root(run_dir: Path, renderer: str) -> Path:
    return run_dir / "render-jobs" / renderer


def render_target_path(run_dir: Path, renderer: str, index: int, title: str) -> Path:
    extensions = {
        "html": "html",
        "svg": "svg",
        "img": "png",
    }
    return run_dir / renderer / slide_filename(index, title, extensions[renderer])


def prepare_render_jobs(run_dir: Path, renderer: str) -> Path:
    require_approved(run_dir, "slide_plans")
    if renderer not in {"html", "svg", "img"}:
        raise ValueError("renderer must be html, svg, or img")

    state = load_state(run_dir)
    slides = slide_jobs(run_dir)
    jobs_dir = render_jobs_root(run_dir, renderer)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    target_dir = run_dir / renderer
    target_dir.mkdir(parents=True, exist_ok=True)

    shared_context_path = jobs_dir / "shared-context.json"
    shared_context = {
        "version": 1,
        "topic": infer_topic(run_dir),
        "audience": state.get("audience"),
        "renderer": renderer,
        "slide_count": len(slides),
        "slides": [
            {
                "index": int(job.get("index", idx)),
                "title": job.get("title", f"Slide {idx}"),
                "page_role": job.get("page_role", "content"),
                "material": job.get("material", ""),
                "plan": job.get("plan", ""),
            }
            for idx, job in enumerate(slides, start=1)
        ],
    }
    write_json(shared_context_path, shared_context)

    manifest_slides: list[dict[str, Any]] = []
    for idx, job in enumerate(slides, start=1):
        slide_index = int(job.get("index", idx))
        title = str(job.get("title") or f"Slide {slide_index}")
        job_path = jobs_dir / f"slide-{slide_index:02d}.json"
        target_path = render_target_path(run_dir, renderer, slide_index, title)
        payload = {
            "version": 1,
            "topic": shared_context["topic"],
            "audience": shared_context["audience"],
            "renderer": renderer,
            "index": slide_index,
            "title": title,
            "page_role": job.get("page_role", "content"),
            "material": job.get("material", ""),
            "plan": job.get("plan", ""),
            "total_pages": len(slides),
            "target_path": str(target_path),
            "shared_context_path": str(shared_context_path),
        }
        write_json(job_path, payload)
        manifest_slides.append({
            "index": slide_index,
            "title": title,
            "job_path": str(job_path),
            "target_path": str(target_path),
        })

    manifest_path = jobs_dir / "manifest.json"
    write_json(manifest_path, {
        "version": 1,
        "renderer": renderer,
        "topic": shared_context["topic"],
        "audience": shared_context["audience"],
        "slide_count": len(slides),
        "shared_context_path": str(shared_context_path),
        "slides": manifest_slides,
    })

    entry = renderer_state(state, renderer)
    entry["jobs"] = {
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


def mark_img_exported_pending_svg_choice(run_dir: Path, pptx_path: Path, images: list[Path]) -> None:
    state = load_state(run_dir)
    state["renderer"] = "img"
    entry = renderer_state(state, "img")
    entry["artifacts"] = {
        **entry.get("artifacts", {}),
        "pptx": {"path": str(pptx_path), "status": "completed"},
    }
    entry["svg_conversion"] = {
        "mode": None,
        "status": "pending_choice",
        "source_pptx_path": str(pptx_path),
        "source_images": [str(path) for path in images],
        "requested_after_img_export": True,
        "updated_at": utc_now(),
    }
    entry["status"] = "img_svg_choice_pending"
    state["render_review"] = dict(entry.get("review") or {})
    state["status"] = "img_svg_choice_pending"
    save_state(run_dir, state)


def prepare_img_svg_jobs(run_dir: Path, state: dict[str, Any]) -> Path:
    images = require_complete_img_sources(run_dir)
    jobs = slide_jobs(run_dir)
    jobs_dir = render_jobs_root(run_dir, "img-svg")
    target_dir = run_dir / "img-svg"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # A fresh opt-in must regenerate every SVG from the current IMG pages.
    for stale in target_dir.glob("*.svg"):
        stale.unlink()
    for stale in jobs_dir.glob("*.json"):
        stale.unlink()

    shared_context_path = jobs_dir / "shared-context.json"
    write_json(shared_context_path, {
        "version": 1,
        "topic": infer_topic(run_dir),
        "audience": state.get("audience"),
        "renderer": "img-svg",
        "source_renderer": "img",
        "slide_count": len(images),
        "model_input_rule": (
            "Pass each source_image_path directly to a vision-capable model and recreate that page "
            "as one final PowerPoint-compatible SVG."
        ),
        "output_rule": (
            "Write one final 1280x720 hybrid SVG per source image. Rebuild text, cards, lines, and "
            "simple diagrams as vectors. For logos, icons, and incompatible complex regions, place "
            "<image data-crop-id='...'> placeholders and use the Pillow crop helper to embed Base64 PNG data."
        ),
        "crop_helper_path": str(
            Path(__file__).resolve().parent / "embed_img_crops.py"
        ),
    })

    manifest_slides: list[dict[str, Any]] = []
    for index, image_path in enumerate(images, start=1):
        plan = jobs[index - 1] if index - 1 < len(jobs) else {}
        target_path = target_dir / f"{image_path.stem}.svg"
        job_path = jobs_dir / f"slide-{index:02d}.json"
        crop_manifest_path = jobs_dir / f"slide-{index:02d}-crops.json"
        payload = {
            "version": 1,
            "renderer": "img-svg",
            "source_renderer": "img",
            "index": int(plan.get("index", index)),
            "title": plan.get("title", image_path.stem),
            "page_role": plan.get("page_role", "content"),
            "source_image_path": str(image_path),
            "target_path": str(target_path),
            "crop_manifest_path": str(crop_manifest_path),
            "shared_context_path": str(shared_context_path),
            "prompt_contract_path": str(
                Path(__file__).resolve().parents[1] / "references" / "prompt-contracts.md"
            ),
            "prompt_contract_section": "IMG-to-SVG Model Conversion Contract",
            "crop_helper_path": str(
                Path(__file__).resolve().parent / "embed_img_crops.py"
            ),
        }
        write_json(job_path, payload)
        manifest_slides.append({
            "index": payload["index"],
            "title": payload["title"],
            "source_image_path": str(image_path),
            "job_path": str(job_path),
            "target_path": str(target_path),
            "crop_manifest_path": str(crop_manifest_path),
        })

    manifest_path = jobs_dir / "manifest.json"
    write_json(manifest_path, {
        "version": 1,
        "renderer": "img-svg",
        "source_renderer": "img",
        "topic": infer_topic(run_dir),
        "slide_count": len(images),
        "shared_context_path": str(shared_context_path),
        "slides": manifest_slides,
    })

    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    entry["svg_conversion"] = {
        **conversion,
        "mode": "on",
        "status": "pending_generation",
        "manifest_path": str(manifest_path),
        "shared_context_path": str(shared_context_path),
        "target_dir": str(target_dir),
        "updated_at": utc_now(),
    }
    entry["status"] = "img_svg_generation_pending"
    state["status"] = "img_svg_generation_pending"
    save_state(run_dir, state)
    return manifest_path


def validate_ppt_compatible_svg(path: Path) -> None:
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

    forbidden = {"foreignobject", "script"}
    raster_area = 0.0
    vector_element_count = 0
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
            if width <= 0 or height <= 0:
                raise ValueError(f"SVG <image> width and height must be positive: {path}")
            if x <= 1 and y <= 1 and width >= 1278 and height >= 718:
                raise ValueError(
                    f"SVG must not wrap the complete source slide in one full-page <image>: {path}"
                )
            raster_area += width * height
        for attribute, value in element.attrib.items():
            if (
                attribute.rsplit("}", 1)[-1].lower() == "href"
                and value
                and not value.startswith(("#", "data:image/png;base64,", "data:image/jpeg;base64,", "data:image/jpg;base64,"))
            ):
                raise ValueError(f"SVG contains an external href: {path}")

    source = path.read_text(encoding="utf-8").lower()
    if any(marker in source for marker in ("url(http://", "url(https://", "@import")):
        raise ValueError(f"SVG contains external image or stylesheet data: {path}")
    if vector_element_count == 0:
        raise ValueError(f"SVG must contain vector text or shape elements: {path}")
    if raster_area > 1280 * 720 * 0.70:
        raise ValueError(
            f"SVG embedded raster regions cover too much of the slide; reconstruct more as vectors: {path}"
        )


def complete_img_svg_generation(run_dir: Path) -> list[Path]:
    state = load_state(run_dir)
    if state.get("renderer") != "img":
        raise RuntimeError("IMG-to-SVG completion is only available for the img renderer")
    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    if conversion.get("mode") != "on":
        raise RuntimeError("IMG-to-SVG conversion is not enabled")
    if conversion.get("status") != "pending_generation":
        raise RuntimeError("IMG-to-SVG generation is not pending")

    manifest = read_json(Path(conversion["manifest_path"]))
    expected_paths = [Path(item["target_path"]) for item in manifest.get("slides", [])]
    actual_paths = sorted((run_dir / "img-svg").glob("*.svg"))
    if {path.resolve() for path in actual_paths} != {path.resolve() for path in expected_paths}:
        raise ValueError(
            f"IMG-to-SVG output mismatch: expected {len(expected_paths)} exact page files, found {len(actual_paths)}"
        )
    for svg_path in actual_paths:
        validate_ppt_compatible_svg(svg_path)

    entry["svg_conversion"] = {
        **conversion,
        "status": "completed",
        "svg_count": len(actual_paths),
        "svg_paths": [str(path) for path in actual_paths],
        "completed_at": utc_now(),
    }
    entry["status"] = "img_svg_export_ready"
    state["status"] = "img_svg_export_ready"
    save_state(run_dir, state)
    return actual_paths


def export_svg(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    from pptx_builder import build_pptx

    svg_dir = run_dir / "svg"
    svg_files = sorted(svg_dir.glob("*.svg")) if svg_dir.exists() else []
    if not svg_files:
        raise ValueError(
            f"SVG directory is empty: {svg_dir}. "
            "This branch needs Codex-authored SVG source files before export."
        )

    pptx_path = run_dir / renderer_pptx_name(run_dir, "svg")
    build_pptx(svg_dir, pptx_path)
    jobs = slide_jobs(run_dir)
    write_slide_status(run_dir, {
        f"{int(job.get('index', i)):02d}": {
            "title": job.get("title", f"Slide {i}"),
            "page_role": job.get("page_role", "content"),
            "validation_status": "codex_generated",
            "export_ready": True,
        }
        for i, job in enumerate(jobs, start=1)
    }, renderer="svg")
    mark_completed(run_dir, "svg", {"pptx": pptx_path})
    return pptx_path


def export_html(run_dir: Path, editable_engine: str | None = None) -> Path:
    require_approved(run_dir, "slide_plans")
    from html_pipeline.html_builder import build_pptx

    topic = infer_topic(run_dir)
    html_dir = run_dir / "html"
    html_files = sorted(html_dir.glob("*.html")) if html_dir.exists() else []
    if not html_files:
        raise ValueError(
            f"HTML directory is empty: {html_dir}. "
            "This branch needs Codex-authored HTML source files before export. "
            "If you used clean-render, note that it only clears derived outputs; "
            "HTML pages still must exist in this branch."
        )

    image_pptx = run_dir / renderer_pptx_name(run_dir, "html")
    build_pptx(html_dir, image_pptx)

    jobs = slide_jobs(run_dir)
    slide_meta = []
    for i, html_path in enumerate(html_files, start=1):
        job = jobs[i - 1] if i - 1 < len(jobs) else {}
        slide_meta.append({
            "index": int(job.get("index", i)),
            "title": job.get("title") or html_path.stem,
            "page_role": job.get("page_role", "content"),
            "html_path": str(html_path),
        })

    status = {
        f"{item['index']:02d}": {
            "title": item["title"],
            "page_role": item["page_role"],
            "validation_status": "codex_generated",
            "export_ready": True,
            "html_path": item["html_path"],
        }
        for item in slide_meta
    }
    write_slide_status(run_dir, status, renderer="html")

    artifacts = {"image_pptx": image_pptx}
    editable_dir = run_dir / "editable"
    try:
        from vendor_presentation_core.export.dom_pptx_exporter import build_dom_editable_deck_from_html

        editable_pptx = build_dom_editable_deck_from_html(
            html_dir=html_dir,
            out_dir=editable_dir,
            slide_meta=slide_meta,
            deck_name=topic,
        )
        artifacts["editable_pptx"] = editable_pptx
    except Exception as exc:
        print(f"[warning] editable export skipped: {exc}", flush=True)

    manifest = {
        "version": 1,
        "source": "codex-skill",
        "topic": topic,
        "renderer": "html",
        "slides": slide_meta,
        "image_pptx_path": str(image_pptx),
        "editable_pptx_path": str(artifacts.get("editable_pptx", "")),
        "editable_engine": editable_engine or "dom_export",
        "updated_at": utc_now(),
    }
    manifest_path = write_json(run_dir / "editable-ppt-chain.json", manifest)
    artifacts["chain_manifest"] = manifest_path
    mark_completed(run_dir, "html", artifacts)
    return image_pptx


def export_img(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    from pptx import Presentation
    from pptx.util import Inches

    images = require_complete_img_sources(run_dir)

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
    mark_img_exported_pending_svg_choice(run_dir, pptx_path, images)
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
    svg_paths = sorted(svg_dir.glob("*.svg"))
    for svg_path in svg_paths:
        validate_ppt_compatible_svg(svg_path)

    pptx_path = run_dir / renderer_pptx_name(run_dir, "img-svg")
    build_native_svg_pptx(svg_dir, pptx_path)

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
    # Keep renderer source dirs. Codex authors html/svg/img directly in this branch,
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


def cmd_save_artifact(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source = Path(args.file)
    data = read_json(source)
    target = write_json(run_dir / ARTIFACT_FILES[args.artifact], data)
    preview = preview_artifact(run_dir, args.artifact)
    print(f"{args.artifact}={target}", flush=True)
    print(f"preview={preview}", flush=True)


def cmd_preview(args: argparse.Namespace) -> None:
    preview = preview_artifact(normalize_run_dir(args.run_dir), args.artifact)
    print(f"preview={preview}", flush=True)


def cmd_approve(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    if args.artifact not in state.get("artifacts", {}):
        raise ValueError(f"unknown artifact: {args.artifact}")
    state.setdefault("approvals", {})[args.artifact] = True
    state["artifacts"][args.artifact]["status"] = "approved"
    state["artifacts"][args.artifact]["approved_at"] = utc_now()
    state["status"] = f"{args.artifact}_approved"
    save_state(run_dir, state)
    print(f"approved={args.artifact}", flush=True)
    if args.artifact == "slide_plans" and not state.get("renderer"):
        print("next=choose-renderer", flush=True)
        print("recommended_renderer=img", flush=True)


def cmd_choose_renderer(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    require_approved(run_dir, "slide_plans")
    state = load_state(run_dir)
    state["renderer"] = args.renderer
    entry = renderer_state(state, args.renderer)
    if args.renderer in {"html", "svg"}:
        entry["review"] = {
            "mode": None,
            "status": "pending_choice",
        }
        entry["status"] = "review_choice_pending"
        state["render_review"] = dict(entry["review"])
        state["status"] = "review_choice_pending"
    else:
        entry["review"] = {
            **RENDER_REVIEW_NOT_APPLICABLE,
            "confirmed_at": utc_now(),
        }
        entry["svg_conversion"] = default_img_svg_conversion()
        entry["status"] = "render_ready"
        state["render_review"] = dict(entry["review"])
        state["status"] = "render_ready"
    save_state(run_dir, state)
    print(f"renderer={args.renderer}", flush=True)
    if args.renderer in {"html", "svg"}:
        print("next=choose-review", flush=True)


def cmd_choose_review(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    renderer = state.get("renderer")
    if renderer not in {"html", "svg"}:
        raise RuntimeError("review choice is only available for html or svg renderer")
    entry = renderer_state(state, renderer)
    entry["review"] = {
        "mode": args.mode,
        "status": "pending" if args.mode == "on" else "skipped",
        "confirmed_at": utc_now(),
    }
    entry["status"] = "render_review_pending" if args.mode == "on" else "render_ready"
    state["render_review"] = dict(entry["review"])
    state["status"] = entry["status"]
    save_state(run_dir, state)
    print(f"review_mode={args.mode}", flush=True)
    if args.mode == "on":
        print("next=complete-review", flush=True)


def cmd_complete_review(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    renderer = state.get("renderer")
    if renderer not in {"html", "svg"}:
        raise RuntimeError("render review completion is only available for html or svg renderer")
    entry = renderer_state(state, renderer)
    review = entry.get("review") or {}
    if review.get("mode") != "on":
        raise RuntimeError("render review is not enabled")
    entry["review"] = {
        **review,
        "status": "completed",
        "completed_at": utc_now(),
    }
    entry["status"] = "render_ready"
    state["render_review"] = dict(entry["review"])
    state["status"] = "render_ready"
    save_state(run_dir, state)
    print(f"review_completed={renderer}", flush=True)


def cmd_choose_img_svg(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    if state.get("renderer") != "img":
        raise RuntimeError("IMG-to-SVG choice is only available for the img renderer")
    entry = renderer_state(state, "img")
    conversion = dict(entry.get("svg_conversion") or {})
    if conversion.get("status") != "pending_choice":
        raise RuntimeError(
            "IMG-to-SVG choice is only allowed after the IMG PPT has been exported and shown to the user"
        )
    source_pptx = Path(str(conversion.get("source_pptx_path") or ""))
    if not source_pptx.is_file():
        raise RuntimeError("The exported IMG PPTX is missing; re-export it before asking for IMG-to-SVG choice")

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
    svg_paths = complete_img_svg_generation(run_dir)
    print(f"img_svg_completed={len(svg_paths)}", flush=True)
    print("next=export-img-svg", flush=True)


def cmd_export_img_svg(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    out = export_img_svg(run_dir)
    print(f"completed={out}", flush=True)


def cmd_prepare_render_jobs(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    renderer = args.renderer or load_state(run_dir).get("renderer")
    if renderer not in {"html", "svg", "img"}:
        raise RuntimeError("renderer must be html, svg, or img")
    manifest = prepare_render_jobs(run_dir, renderer)
    print(f"render_jobs={manifest}", flush=True)


def cmd_export(args: argparse.Namespace) -> None:
    run_dir = normalize_run_dir(args.run_dir)
    state = load_state(run_dir)
    renderer = args.renderer or state.get("renderer")
    if renderer:
        ensure_render_ready(run_dir, renderer)
    if renderer == "html":
        out = export_html(run_dir, editable_engine=args.editable_engine)
    elif renderer == "svg":
        out = export_svg(run_dir)
    elif renderer == "img":
        out = export_img(run_dir)
    else:
        raise ValueError("renderer must be html, svg, or img")
    if renderer == "img":
        print(f"img_pptx={out}", flush=True)
        print("next=ask-user-img-svg", flush=True)
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
        "img_svg_choice_pending": "ask-user-img-svg",
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
    patterns = {"html": "*.html", "svg": "*.svg", "img": "*.*", "img-svg": "*.svg"}
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

    choose = sub.add_parser("choose-renderer")
    choose.add_argument("--run-dir", required=True)
    choose.add_argument("--renderer", choices=["html", "svg", "img"], required=True)
    choose.set_defaults(func=cmd_choose_renderer)

    choose_review = sub.add_parser("choose-review")
    choose_review.add_argument("--run-dir", required=True)
    choose_review.add_argument("--mode", choices=["off", "on"], required=True)
    choose_review.set_defaults(func=cmd_choose_review)

    choose_img_svg = sub.add_parser("choose-img-svg")
    choose_img_svg.add_argument("--run-dir", required=True)
    choose_img_svg.add_argument("--mode", choices=["off", "on"], required=True)
    choose_img_svg.set_defaults(func=cmd_choose_img_svg)

    jobs = sub.add_parser("prepare-render-jobs")
    jobs.add_argument("--run-dir", required=True)
    jobs.add_argument("--renderer", choices=["html", "svg", "img"], default=None)
    jobs.set_defaults(func=cmd_prepare_render_jobs)

    complete_review = sub.add_parser("complete-review")
    complete_review.add_argument("--run-dir", required=True)
    complete_review.set_defaults(func=cmd_complete_review)

    complete_img_svg = sub.add_parser("complete-img-svg")
    complete_img_svg.add_argument("--run-dir", required=True)
    complete_img_svg.set_defaults(func=cmd_complete_img_svg)

    export_img_svg_parser = sub.add_parser("export-img-svg")
    export_img_svg_parser.add_argument("--run-dir", required=True)
    export_img_svg_parser.set_defaults(func=cmd_export_img_svg)

    export = sub.add_parser("export")
    export.add_argument("--run-dir", required=True)
    export.add_argument("--renderer", choices=["html", "svg", "img"], default=None)
    export.add_argument("--editable-engine", default=None)
    export.set_defaults(func=cmd_export)

    clean = sub.add_parser("clean-render")
    clean.add_argument("--run-dir", required=True)
    clean.set_defaults(func=lambda args: clean_render_outputs(normalize_run_dir(args.run_dir)))

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
