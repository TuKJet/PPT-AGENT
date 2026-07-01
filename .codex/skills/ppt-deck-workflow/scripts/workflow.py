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

from filename_utils import safe_filename_part

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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root() -> Path:
    return Path(os.getenv("OUTPUT_DIR", "output"))


def run_dir_for_topic(topic: str) -> Path:
    return output_root() / safe_filename_part(topic, max_length=80)


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


def load_state(run_dir: Path) -> dict[str, Any]:
    return read_json(run_dir / STATE_FILE, default={
        "version": 3,
        "status": "new",
        "approvals": {},
        "artifacts": {},
        "renderer": None,
        "render_review": {
            "mode": None,
            "status": "not_applicable",
        },
        "execution": "codex-skill",
    })


def save_state(run_dir: Path, state: dict[str, Any]) -> Path:
    state["version"] = 3
    state["execution"] = "codex-skill"
    state["updated_at"] = utc_now()
    return write_json(run_dir / STATE_FILE, state)


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
    })
    save_state(run_dir, state)
    return state


def ensure_render_ready(run_dir: Path, renderer: str) -> None:
    state = load_state(run_dir)
    if renderer not in {"html", "svg"}:
        return
    review = state.get("render_review") or {}
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


def write_slide_status(run_dir: Path, slides: dict[str, Any]) -> Path:
    return write_json(run_dir / "slide-status.json", {"slides": slides})


def infer_topic(run_dir: Path) -> str:
    return str(load_state(run_dir).get("topic") or run_dir.name)


def mark_completed(run_dir: Path, renderer: str, artifacts: dict[str, Path]) -> None:
    state = load_state(run_dir)
    state["status"] = "completed"
    state["renderer"] = renderer
    for name, path in artifacts.items():
        state.setdefault("artifacts", {})[name] = {"path": str(path), "status": "completed"}
    save_state(run_dir, state)


def export_svg(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    from pptx_builder import build_pptx

    pptx_path = run_dir / f"{safe_filename_part(infer_topic(run_dir), max_length=30)}.pptx"
    build_pptx(run_dir / "svg", pptx_path)
    jobs = slide_jobs(run_dir)
    write_slide_status(run_dir, {
        f"{int(job.get('index', i)):02d}": {
            "title": job.get("title", f"Slide {i}"),
            "page_role": job.get("page_role", "content"),
            "validation_status": "codex_generated",
            "export_ready": True,
        }
        for i, job in enumerate(jobs, start=1)
    })
    mark_completed(run_dir, "svg", {"pptx": pptx_path})
    return pptx_path


def export_html(run_dir: Path, editable_engine: str | None = None) -> Path:
    require_approved(run_dir, "slide_plans")
    from html_pipeline.html_builder import build_pptx

    topic = infer_topic(run_dir)
    html_dir = run_dir / "html"
    image_pptx = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    build_pptx(html_dir, image_pptx)

    jobs = slide_jobs(run_dir)
    html_files = sorted(html_dir.glob("*.html"))
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
    write_slide_status(run_dir, status)

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

    pptx_path = run_dir / f"{safe_filename_part(infer_topic(run_dir), max_length=30)}.pptx"
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
    })
    mark_completed(run_dir, "img", {"pptx": pptx_path})
    return pptx_path


def clean_render_outputs(run_dir: Path) -> None:
    root = run_dir.resolve()
    for name in ("html", "svg", "img", "reviews", "editable"):
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
    run_dir = Path(args.run_dir) if args.run_dir else run_dir_for_topic(args.topic)
    run_dir.mkdir(parents=True, exist_ok=True)
    init_state(run_dir, topic=args.topic, audience=args.audience, pages=args.pages, research=args.research or "")
    print(f"run_dir={run_dir}", flush=True)


def cmd_save_artifact(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    source = Path(args.file)
    data = read_json(source)
    target = write_json(run_dir / ARTIFACT_FILES[args.artifact], data)
    preview = preview_artifact(run_dir, args.artifact)
    print(f"{args.artifact}={target}", flush=True)
    print(f"preview={preview}", flush=True)


def cmd_preview(args: argparse.Namespace) -> None:
    preview = preview_artifact(Path(args.run_dir), args.artifact)
    print(f"preview={preview}", flush=True)


def cmd_approve(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
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
    run_dir = Path(args.run_dir)
    require_approved(run_dir, "slide_plans")
    state = load_state(run_dir)
    state["renderer"] = args.renderer
    if args.renderer in {"html", "svg"}:
        state["render_review"] = {
            "mode": None,
            "status": "pending_choice",
        }
        state["status"] = "review_choice_pending"
    else:
        state["render_review"] = {
            "mode": "off",
            "status": "not_applicable",
            "confirmed_at": utc_now(),
        }
        state["status"] = "render_ready"
    save_state(run_dir, state)
    print(f"renderer={args.renderer}", flush=True)
    if args.renderer in {"html", "svg"}:
        print("next=choose-review", flush=True)


def cmd_choose_review(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    renderer = state.get("renderer")
    if renderer not in {"html", "svg"}:
        raise RuntimeError("review choice is only available for html or svg renderer")
    state["render_review"] = {
        "mode": args.mode,
        "status": "pending" if args.mode == "on" else "skipped",
        "confirmed_at": utc_now(),
    }
    state["status"] = "render_review_pending" if args.mode == "on" else "render_ready"
    save_state(run_dir, state)
    print(f"review_mode={args.mode}", flush=True)
    if args.mode == "on":
        print("next=complete-review", flush=True)


def cmd_complete_review(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    renderer = state.get("renderer")
    review = state.get("render_review") or {}
    if renderer not in {"html", "svg"}:
        raise RuntimeError("render review completion is only available for html or svg renderer")
    if review.get("mode") != "on":
        raise RuntimeError("render review is not enabled")
    state["render_review"] = {
        **review,
        "status": "completed",
        "completed_at": utc_now(),
    }
    state["status"] = "render_ready"
    save_state(run_dir, state)
    print(f"review_completed={renderer}", flush=True)


def cmd_export(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
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
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    print(f"run_dir={run_dir}", flush=True)
    print(f"status={state.get('status')}", flush=True)
    print(f"renderer={state.get('renderer')}", flush=True)
    review = state.get("render_review") or {}
    print(f"review_mode={review.get('mode')}", flush=True)
    print(f"review_status={review.get('status')}", flush=True)
    for name, entry in sorted((state.get("artifacts") or {}).items()):
        print(f"{name}: {entry.get('status')} {entry.get('path')}", flush=True)
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
    clean.set_defaults(func=lambda args: clean_render_outputs(Path(args.run_dir)))

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
