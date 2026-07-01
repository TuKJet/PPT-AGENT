from __future__ import annotations

import argparse
from pathlib import Path

from ai_client import AIClient
from config import (
    EDITABLE_EXPORT_ENGINE,
    OUTPUT_DIR,
    REVIEW_ENABLED,
    REVIEW_MODEL,
    REVIEW_PROVIDER,
    SVG_REVIEW_ENABLED,
    SVG_REVIEW_MODEL,
    SVG_REVIEW_PROVIDER,
    missing_krill_image_settings,
)
from filename_utils import safe_filename_part, slide_filename
import pipeline as svg_pipeline
from ppt_workflow.artifacts import (
    approve,
    init_state,
    load_state,
    mark_artifact,
    read_json,
    require_approved,
    run_dir_for_topic,
    save_state,
    write_contents_preview,
    write_json,
    write_outline_preview,
    write_plans_preview,
)


def _log(message: str) -> None:
    print(message, flush=True)


def _progress(stage: str, current: int, total: int, detail: str = "") -> None:
    width = 20
    filled = round(width * current / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    suffix = f" {detail}" if detail else ""
    _log(f"[progress] {stage} [{bar}] {current}/{total}{suffix}")


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if getattr(args, "run_dir", None):
        return Path(args.run_dir)
    topic = getattr(args, "topic", None)
    if not topic:
        raise ValueError("--topic or --run-dir is required")
    return run_dir_for_topic(topic)


def cmd_init(args: argparse.Namespace) -> None:
    run_dir = run_dir_for_topic(args.topic)
    run_dir.mkdir(parents=True, exist_ok=True)
    init_state(
        run_dir,
        topic=args.topic,
        audience=args.audience,
        pages=args.pages,
        provider=args.provider,
        research=args.research or "",
    )
    _log(str(run_dir))


def cmd_outline(args: argparse.Namespace) -> None:
    run_dir = _resolve_run_dir(args)
    state = load_state(run_dir)
    topic = args.topic or state.get("topic")
    audience = args.audience or state.get("audience", "通用受众")
    pages = args.pages or state.get("pages", "12-15页")
    provider = args.provider if args.provider is not None else state.get("provider")
    research = args.research if args.research is not None else state.get("research", "")
    if not topic:
        raise ValueError("topic is missing")

    state = init_state(run_dir, topic=topic, audience=audience, pages=pages, provider=provider, research=research or "")
    client = AIClient(provider)
    _log("[progress] outline start")
    outline = svg_pipeline.step1_outline(client, topic, audience, pages, research or "")
    outline_path = write_json(run_dir / "outline.json", outline)
    preview_path = write_outline_preview(outline, run_dir / "outline-preview.md")
    mark_artifact(run_dir, state, "outline", outline_path, preview_path=preview_path)
    _log("[progress] outline done")
    _log(f"outline={outline_path}")
    _log(f"preview={preview_path}")


def cmd_contents(args: argparse.Namespace) -> None:
    run_dir = _resolve_run_dir(args)
    require_approved(run_dir, "outline")
    state = load_state(run_dir)
    client = AIClient(args.provider if args.provider is not None else state.get("provider"))
    outline = read_json(run_dir / "outline.json")
    _log("[progress] contents start")
    contents = svg_pipeline.step2_content(client, outline)
    contents_path = write_json(run_dir / "contents.json", contents)
    preview_path = write_contents_preview(contents, run_dir / "contents-preview.md")
    mark_artifact(run_dir, state, "contents", contents_path, preview_path=preview_path)
    _log("[progress] contents done")
    _log(f"contents={contents_path}")
    _log(f"preview={preview_path}")


def cmd_plans(args: argparse.Namespace) -> None:
    run_dir = _resolve_run_dir(args)
    require_approved(run_dir, "contents")
    state = load_state(run_dir)
    client = AIClient(args.provider if args.provider is not None else state.get("provider"))
    outline = read_json(run_dir / "outline.json")
    contents = read_json(run_dir / "contents.json")
    pages = svg_pipeline._get_pages(outline)
    if args.max_pages and args.max_pages > 0:
        pages = pages[:args.max_pages]
    total_pages = len(pages)

    slide_jobs = []
    for index, page in enumerate(pages, start=1):
        title = svg_pipeline._get_title(page)
        _progress("plans", index, total_pages, f"planning: {title}")
        material = contents.get(title, "")
        plan = svg_pipeline.step3_plan(client, title, material)
        page_role = svg_pipeline._infer_page_role(index, total_pages, title, plan, material)
        slide_jobs.append({
            "index": index,
            "title": title,
            "material": material,
            "plan": plan,
            "page_role": page_role,
        })
        _progress("plans", index, total_pages, f"done: {title}")

    data = {"version": 1, "slides": slide_jobs}
    plans_path = write_json(run_dir / "slide-plans.json", data)
    preview_path = write_plans_preview(slide_jobs, run_dir / "slide-plans-preview.md")
    mark_artifact(run_dir, state, "slide_plans", plans_path, preview_path=preview_path)
    _log(f"plans={plans_path}")
    _log(f"preview={preview_path}")


def cmd_approve(args: argparse.Namespace) -> None:
    state = approve(Path(args.run_dir), args.artifact)
    _log(f"approved={args.artifact}")
    _log(f"state={Path(args.run_dir) / 'workflow-state.json'}")
    if args.artifact == "slide_plans" and not state.get("renderer"):
        _log("next=choose-renderer")


def cmd_choose_renderer(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    require_approved(run_dir, "slide_plans")
    if args.renderer == "img":
        missing = missing_krill_image_settings()
        if missing:
            names = ", ".join(missing)
            raise RuntimeError(
                "IMG renderer is not configured. Missing env settings: "
                f"{names}. Configure them and retry `img`, or choose `html`/`svg` instead."
            )
    state = load_state(run_dir)
    state["renderer"] = args.renderer
    state["status"] = "renderer_chosen"
    save_state(run_dir, state)
    _log(f"renderer={args.renderer}")


def _load_slide_jobs(run_dir: Path) -> list[dict]:
    data = read_json(run_dir / "slide-plans.json")
    return list(data.get("slides") or [])


def _make_review_client(enabled: bool, provider: str, model: str) -> AIClient | None:
    if not enabled:
        return None
    client = AIClient(provider)
    if model:
        client.model = model
    return client


def render_svg(run_dir: Path, *, polish: bool = False) -> Path:
    require_approved(run_dir, "slide_plans")
    state = load_state(run_dir)
    topic = state.get("topic") or run_dir.name
    audience = state.get("audience", "通用受众")
    provider = state.get("provider")
    client = AIClient(provider)
    review_client = _make_review_client(SVG_REVIEW_ENABLED, SVG_REVIEW_PROVIDER, SVG_REVIEW_MODEL)
    slide_jobs = _load_slide_jobs(run_dir)

    svg_dir = run_dir / "svg"
    review_dir = run_dir / "reviews"
    svg_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    slide_status = {}
    total_pages = len(slide_jobs)

    for job in slide_jobs:
        index = int(job["index"])
        title = job["title"]
        _progress("render-svg", index, total_pages, f"generating: {title}")
        material = job.get("material", "")
        plan = job.get("plan", "")
        page_role = job.get("page_role", "content")
        svg = svg_pipeline.step4_svg(client, title, material, plan, audience, page_role)
        svg_path = svg_dir / slide_filename(index, title, "svg")
        svg_path.write_text(svg, encoding="utf-8")
        _, validation_issues = svg_pipeline._validate_and_optionally_regenerate_svg(
            client, svg_path, title, material, plan, audience, page_role, polish
        )
        review_result = svg_pipeline._review_and_optionally_fix_svg(
            client, review_client, svg_path, index, title, material, plan, audience, page_role, validation_issues
        )
        final_validation_status = review_result.get(
            "post_fix_validation_status",
            svg_pipeline._classify_svg_validation(validation_issues, review_result),
        )
        final_issues_count = review_result.get("post_fix_final_issues", len(validation_issues))
        slide_status[f"{index:02d}"] = {
            "title": title,
            "page_role": page_role,
            "validation_status": final_validation_status,
            "final_issues_count": final_issues_count,
            "review_status": review_result.get("result"),
            "review_rounds": review_result.get("review_rounds", 0),
            "review_path": review_result.get("review_path"),
            "export_ready": final_validation_status in {"pass", "compact_pass"} and review_result.get("result") != "REVISE",
        }
        from pptx_builder import write_slide_status
        write_slide_status(run_dir, slide_status)
        _progress("render-svg", index, total_pages, f"ready: {title}")

    from pptx_builder import build_pptx
    pptx_path = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    _log("[progress] export-svg-pptx start")
    build_pptx(svg_dir, pptx_path)
    state["status"] = "completed"
    state["renderer"] = "svg"
    state.setdefault("artifacts", {})["pptx"] = {"path": str(pptx_path), "status": "completed"}
    save_state(run_dir, state)
    _log("[progress] export-svg-pptx done")
    return pptx_path


def render_html(run_dir: Path, *, polish: bool = False, editable_engine: str | None = None) -> Path:
    require_approved(run_dir, "slide_plans")
    from html_pipeline import pipeline as html_pipeline
    from html_pipeline.html_builder import build_pptx, write_slide_status

    state = load_state(run_dir)
    topic = state.get("topic") or run_dir.name
    audience = state.get("audience", "通用受众")
    provider = state.get("provider")
    client = AIClient(provider)
    review_client = _make_review_client(REVIEW_ENABLED, REVIEW_PROVIDER, REVIEW_MODEL)
    slide_jobs = _load_slide_jobs(run_dir)
    all_slides_context = html_pipeline._build_all_slides_context(slide_jobs)

    html_dir = run_dir / "html"
    review_dir = run_dir / "reviews"
    html_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    slide_status = {}
    editable_slide_meta = []
    total_pages = len(slide_jobs)

    for job in slide_jobs:
        index = int(job["index"])
        title = job["title"]
        _progress("render-html", index, total_pages, f"generating: {title}")
        material = job.get("material", "")
        plan = job.get("plan", "")
        page_role = job.get("page_role", "summary")
        html_path = html_dir / slide_filename(index, title, "html")
        html = html_pipeline.step4_html(
            client,
            title,
            material,
            plan,
            audience,
            page_role,
            deck_topic=topic,
            page_number=index,
            total_pages=total_pages,
            all_slides=all_slides_context,
        )
        html_path.write_text(html, encoding="utf-8")
        validation_report = html_pipeline._validate_and_optionally_regenerate(
            client,
            html_path,
            title,
            material,
            plan,
            audience,
            page_role,
            polish,
            deck_topic=topic,
            page_number=index,
            total_pages=total_pages,
            all_slides=all_slides_context,
        )
        review_result = html_pipeline._review_and_optionally_fix(
            client,
            review_client,
            html_path,
            index,
            title,
            material,
            plan,
            audience,
            page_role,
            validation_report,
            deck_topic=topic,
            total_pages=total_pages,
            all_slides=all_slides_context,
        )
        final_validation_status = review_result.get("post_fix_validation_status", validation_report.get("status"))
        final_issues_count = review_result.get("post_fix_final_issues", len(validation_report.get("final_issues") or []))
        slide_status[f"{index:02d}"] = {
            "title": title,
            "page_role": page_role,
            "validation_status": final_validation_status,
            "final_issues_count": final_issues_count,
            "review_status": review_result.get("result"),
            "review_rounds": review_result.get("review_rounds", 0),
            "review_path": review_result.get("review_path"),
            "export_ready": final_validation_status == "pass" and review_result.get("result") != "REVISE",
            "html_path": str(html_path),
        }
        editable_slide_meta.append({
            "index": index,
            "title": title,
            "page_role": page_role,
            "html_path": str(html_path),
            "slide_type": page_role,
            "description": plan[:220],
        })
        write_slide_status(run_dir, slide_status)
        _progress("render-html", index, total_pages, f"ready: {title}")

    image_pptx_path = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    _log("[progress] export-image-pptx start")
    build_pptx(html_dir, image_pptx_path)
    _log("[progress] export-image-pptx done")
    editable_dir = run_dir / "editable"
    _log("[progress] export-editable-pptx start")
    editable_pptx_path = html_pipeline._build_editable_deck(
        html_dir=html_dir,
        out_dir=editable_dir,
        slide_meta=editable_slide_meta,
        deck_name=topic,
        engine_override=editable_engine or EDITABLE_EXPORT_ENGINE,
    )
    _log("[progress] export-editable-pptx done")
    manifest_path = html_pipeline._write_editable_chain_manifest(
        run_dir=run_dir,
        topic=topic,
        html_dir=html_dir,
        slide_meta=editable_slide_meta,
        image_pptx_path=image_pptx_path,
        editable_pptx_path=editable_pptx_path,
        editable_dir=editable_dir,
        source="codex-workflow",
    )
    state["status"] = "completed"
    state["renderer"] = "html"
    state.setdefault("artifacts", {})["image_pptx"] = {"path": str(image_pptx_path), "status": "completed"}
    state.setdefault("artifacts", {})["editable_pptx"] = {"path": str(editable_pptx_path), "status": "completed"}
    state.setdefault("artifacts", {})["chain_manifest"] = {"path": str(manifest_path), "status": "completed"}
    save_state(run_dir, state)
    return image_pptx_path


def cmd_render(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    renderer = args.renderer or state.get("renderer")
    if renderer not in {"html", "svg", "img"}:
        raise ValueError("renderer must be html, svg, or img")
    if renderer == "html":
        out = render_html(run_dir, polish=args.polish, editable_engine=args.editable_engine)
    elif renderer == "img":
        from img_renderer import render_img
        out = render_img(run_dir)
    else:
        out = render_svg(run_dir, polish=args.polish)
    _log(f"completed={out}")


def cmd_edit_img(args: argparse.Namespace) -> None:
    from img_renderer import revise_img_slide

    run_dir = Path(args.run_dir)
    out = revise_img_slide(run_dir, page_index=args.page_index, feedback=args.feedback)
    _log(f"revised={out}")


def cmd_status(args: argparse.Namespace) -> None:
    run_dir = Path(args.run_dir)
    state = load_state(run_dir)
    _log(f"run_dir={run_dir}")
    _log(f"status={state.get('status')}")
    _log(f"renderer={state.get('renderer')}")
    for name, entry in sorted((state.get("artifacts") or {}).items()):
        _log(f"{name}: {entry.get('status')} {entry.get('path')}")

    slide_status = read_json(run_dir / "slide-status.json", default={}).get("slides") or {}
    if slide_status:
        ready = sum(1 for item in slide_status.values() if item.get("export_ready"))
        _log(f"slides_ready={ready}/{len(slide_status)}")
    html_count = len(list((run_dir / "html").glob("*.html"))) if (run_dir / "html").exists() else 0
    svg_count = len(list((run_dir / "svg").glob("*.svg"))) if (run_dir / "svg").exists() else 0
    img_count = len(list((run_dir / "img").glob("*.png"))) if (run_dir / "img").exists() else 0
    if html_count:
        _log(f"html_files={html_count}")
    if svg_count:
        _log(f"svg_files={svg_count}")
    if img_count:
        _log(f"img_files={img_count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex-facing PPT deck workflow runner")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--topic", required=True)
    init.add_argument("--audience", default="通用受众")
    init.add_argument("--pages", default="12-15页")
    init.add_argument("--provider", default=None)
    init.add_argument("--research", default="")
    init.set_defaults(func=cmd_init)

    outline = sub.add_parser("outline")
    outline.add_argument("--run-dir", default=None)
    outline.add_argument("--topic", default=None)
    outline.add_argument("--audience", default=None)
    outline.add_argument("--pages", default=None)
    outline.add_argument("--provider", default=None)
    outline.add_argument("--research", default=None)
    outline.set_defaults(func=cmd_outline)

    contents = sub.add_parser("contents")
    contents.add_argument("--run-dir", required=True)
    contents.add_argument("--provider", default=None)
    contents.set_defaults(func=cmd_contents)

    plans = sub.add_parser("plans")
    plans.add_argument("--run-dir", required=True)
    plans.add_argument("--provider", default=None)
    plans.add_argument("--max-pages", type=int, default=None)
    plans.set_defaults(func=cmd_plans)

    approve_parser = sub.add_parser("approve")
    approve_parser.add_argument("--run-dir", required=True)
    approve_parser.add_argument("--artifact", choices=["outline", "contents", "slide_plans"], required=True)
    approve_parser.set_defaults(func=cmd_approve)

    choose = sub.add_parser("choose-renderer")
    choose.add_argument("--run-dir", required=True)
    choose.add_argument("--renderer", choices=["html", "svg", "img"], required=True)
    choose.set_defaults(func=cmd_choose_renderer)

    render = sub.add_parser("render")
    render.add_argument("--run-dir", required=True)
    render.add_argument("--renderer", choices=["html", "svg", "img"], default=None)
    render.add_argument("--polish", action="store_true")
    render.add_argument("--editable-engine", default=None)
    render.set_defaults(func=cmd_render)

    edit_img = sub.add_parser("edit-img")
    edit_img.add_argument("--run-dir", required=True)
    edit_img.add_argument("--page-index", required=True, type=int)
    edit_img.add_argument("--feedback", required=True)
    edit_img.set_defaults(func=cmd_edit_img)

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    status.set_defaults(func=cmd_status)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
