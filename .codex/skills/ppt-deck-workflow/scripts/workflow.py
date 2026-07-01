from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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


def default_state() -> dict[str, Any]:
    return {
        "version": 4,
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
    return {
        "status": "new",
        "artifacts": {},
        "review": review,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output"))


def resolved_output_root() -> Path:
    root = output_root()
    if not root.is_absolute():
        root = REPO_ROOT / root
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
        repo_relative = (REPO_ROOT / run_dir).resolve()
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
    renderers[renderer] = normalized
    return normalized


def load_state(run_dir: Path) -> dict[str, Any]:
    return _normalize_state(read_json(run_dir / STATE_FILE, default=default_state()))


def save_state(run_dir: Path, state: dict[str, Any]) -> Path:
    normalized = _normalize_state(state)
    normalized["version"] = 4
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

    img_dir = run_dir / "img"
    images = sorted(
        [p for p in img_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    ) if img_dir.exists() else []
    if not images:
        raise ValueError(f"IMG directory is empty: {img_dir}")

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
    mark_completed(run_dir, "img", {"pptx": pptx_path})
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
    for pattern in ("*.pptx", "slide-status.json", "editable-ppt-chain.json"):
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
    for name, entry in sorted((state.get("artifacts") or {}).items()):
        print(f"{name}: {entry.get('status')} {entry.get('path')}", flush=True)
    for renderer_name, entry in sorted((state.get("renderers") or {}).items()):
        renderer_review = entry.get("review") or {}
        print(
            f"renderer[{renderer_name}]: status={entry.get('status')} "
            f"review={renderer_review.get('mode')}/{renderer_review.get('status')}",
            flush=True,
        )
        for artifact_name, artifact_entry in sorted((entry.get("artifacts") or {}).items()):
            print(f"renderer[{renderer_name}].{artifact_name}: {artifact_entry.get('status')} {artifact_entry.get('path')}", flush=True)
    slides = read_json(run_dir / "slide-status.json", default={}).get("slides") or {}
    if slides:
        ready = sum(1 for item in slides.values() if item.get("export_ready"))
        print(f"slides_ready={ready}/{len(slides)}", flush=True)
    patterns = {"html": "*.html", "svg": "*.svg", "img": "*.*"}
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

    jobs = sub.add_parser("prepare-render-jobs")
    jobs.add_argument("--run-dir", required=True)
    jobs.add_argument("--renderer", choices=["html", "svg", "img"], default=None)
    jobs.set_defaults(func=cmd_prepare_render_jobs)

    complete_review = sub.add_parser("complete-review")
    complete_review.add_argument("--run-dir", required=True)
    complete_review.set_defaults(func=cmd_complete_review)

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
