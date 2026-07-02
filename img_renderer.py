from __future__ import annotations

import re
from pathlib import Path

from config import missing_krill_image_settings
from filename_utils import safe_filename_part, slide_filename
from krill_image_client import KrillImageClient
from ppt_workflow.artifacts import load_state, read_json, require_approved, save_state
from pptx_builder import build_pptx_from_images, write_slide_status


PLACEHOLDER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bTBD\b",
        r"\bTODO\b",
        r"\bXXX\b",
        r"lorem ipsum",
        r"\[图片\]",
        r"\[文本\]",
        r"<placeholder>",
        r"\{placeholder\}",
        r"占位",
        r"待补",
        r"待插",
        r"预留",
        r"后续补",
        r"示意图",
    ]
]


def ensure_img_renderer_configured() -> None:
    missing = missing_krill_image_settings()
    if not missing:
        return
    names = ", ".join(missing)
    raise RuntimeError(
        "IMG renderer is not configured. Missing env settings: "
        f"{names}. Please configure them and retry `img`, or choose `html`/`svg` instead."
    )


def _normalize_lines(text: str) -> list[str]:
    lines = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip(" -\t")
        if line:
            lines.append(line)
    return lines


def _is_placeholder_line(line: str) -> bool:
    if not line:
        return True
    return any(pattern.search(line) for pattern in PLACEHOLDER_PATTERNS)


def _extract_visible_copy(material: str, plan: str) -> list[str]:
    visible = []
    for line in _normalize_lines(material):
        if not _is_placeholder_line(line):
            visible.append(line)
    for line in _normalize_lines(plan):
        if not _is_placeholder_line(line):
            visible.append(line)
    deduped = []
    seen = set()
    for line in visible:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return deduped[:10]


def _extract_composition(plan: str) -> list[str]:
    compositions = []
    for line in _normalize_lines(plan):
        if _is_placeholder_line(line):
            continue
        lowered = line.lower()
        if any(token in lowered for token in ["左", "右", "中", "居中", "主标题", "路径", "图", "表", "卡", "模块", "title", "chart", "table", "diagram"]):
            compositions.append(line)
    if not compositions:
        compositions.append("Use a polished PPT-style composition with clear hierarchy, balanced whitespace, and a strong management-facing focal point.")
    return compositions[:6]


def _core_message(material: str, title: str) -> str:
    lines = _normalize_lines(material)
    if lines:
        return lines[0]
    return f"Communicate the key message of {title} with crisp executive storytelling."


def compile_img_prompt(slide_job: dict) -> str:
    title = str(slide_job.get("title", "")).strip() or "Untitled"
    page_role = str(slide_job.get("page_role", "content")).strip() or "content"
    material = str(slide_job.get("material", "") or "")
    plan = str(slide_job.get("plan", "") or "")
    visible_copy = _extract_visible_copy(material, plan)
    composition = _extract_composition(plan)
    copy_lines = visible_copy or [title]

    prompt_lines = [
        "Create one complete 16:9 presentation slide image.",
        "",
        f"Slide title: {title}",
        f"Page role: {page_role}",
        f"Core message: {_core_message(material, title)}",
        "",
        "Composition:",
    ]
    prompt_lines.extend(f"- {item}" for item in composition)
    prompt_lines.extend([
        "",
        "Visual style:",
        "- Polished management-facing presentation design with crisp hierarchy, high information density, and intentional whitespace.",
        "- Premium PPT aesthetics, refined color contrast, subtle depth, and clean structured modules.",
        "- Keep the layout visually rich but controlled, with strong readability for Chinese text.",
        "",
        "Required visible copy:",
    ])
    prompt_lines.extend(f"- {item}" for item in copy_lines)
    prompt_lines.extend([
        "",
        "Text constraints:",
        "- Preserve the required Chinese text and numbers exactly as provided.",
        "- Render Chinese text as crisp, legible presentation typography with clear hierarchy.",
        "- Use polished PPT-style content blocks, callouts, tables, or diagrams when needed.",
        "- Do not render placeholder words, scaffold labels, occupancy markers, bracketed placeholders, or fake sample text.",
    ])
    return "\n".join(prompt_lines).strip() + "\n"


def _slide_prompt_path(img_dir: Path, index: int, title: str) -> Path:
    safe_title = safe_filename_part(title, max_length=20, fallback="slide")
    return img_dir / f"{index:02d}_{safe_title}.prompt.txt"


def _img_progress(current: int, total: int, detail: str) -> None:
    width = 20
    filled = round(width * current / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    suffix = f" {detail}" if detail else ""
    print(f"[progress] render-img [{bar}] {current}/{total}{suffix}", flush=True)


def _load_slide_status(run_dir: Path) -> dict:
    return read_json(run_dir / "slide-status.json", default={}).get("slides") or {}


def _write_slide_status_entry(run_dir: Path, slide_status: dict) -> None:
    write_slide_status(run_dir, slide_status)


def _find_slide_job(run_dir: Path, page_index: int) -> dict:
    slide_jobs = list((read_json(run_dir / "slide-plans.json").get("slides") or []))
    for job in slide_jobs:
        if int(job["index"]) == int(page_index):
            return job
    raise RuntimeError(f"slide-plans.json does not contain page {page_index}")


def compile_img_edit_prompt(slide_job: dict, feedback: str) -> str:
    base_prompt = compile_img_prompt(slide_job).strip()
    feedback = str(feedback or "").strip()
    return (
        f"{base_prompt}\n\n"
        "Revise the existing slide image instead of creating a different page concept.\n"
        "Keep the same slide topic, core message, and overall layout intent unless the feedback explicitly asks to change them.\n"
        "Apply these requested changes for the specific page:\n"
        f"- {feedback}\n"
    )


def render_img(run_dir: Path) -> Path:
    require_approved(run_dir, "slide_plans")
    ensure_img_renderer_configured()

    state = load_state(run_dir)
    topic = state.get("topic") or run_dir.name
    slide_jobs = list((read_json(run_dir / "slide-plans.json").get("slides") or []))
    if not slide_jobs:
        raise RuntimeError("slide-plans.json does not contain any slides")
    total_pages = len(slide_jobs)

    img_dir = run_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    client = KrillImageClient()
    slide_status = {}

    for sequence, job in enumerate(slide_jobs, start=1):
        index = int(job["index"])
        title = str(job.get("title", f"slide-{index}"))
        _img_progress(sequence, total_pages, f"generating: {title}")
        prompt = compile_img_prompt(job)
        prompt_path = _slide_prompt_path(img_dir, index, title)
        prompt_path.write_text(prompt, encoding="utf-8")
        image_path = img_dir / slide_filename(index, title, "png")
        client.generate_image(prompt, image_path)
        slide_status[f"{index:02d}"] = {
            "title": title,
            "page_role": job.get("page_role", "content"),
            "validation_status": "pass",
            "final_issues_count": 0,
            "review_status": "SKIPPED",
            "review_rounds": 0,
            "export_ready": True,
            "image_path": str(image_path),
            "prompt_path": str(prompt_path),
        }
        _write_slide_status_entry(run_dir, slide_status)
        _img_progress(sequence, total_pages, f"done: {title}")

    pptx_path = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    build_pptx_from_images(img_dir, pptx_path)

    state["status"] = "completed"
    state["renderer"] = "img"
    state.setdefault("artifacts", {})["img_dir"] = {"path": str(img_dir), "status": "completed"}
    state.setdefault("artifacts", {})["image_pptx"] = {"path": str(pptx_path), "status": "completed"}
    save_state(run_dir, state)
    return pptx_path


def revise_img_slide(run_dir: Path, page_index: int, feedback: str) -> Path:
    require_approved(run_dir, "slide_plans")
    ensure_img_renderer_configured()

    state = load_state(run_dir)
    topic = state.get("topic") or run_dir.name
    slide_job = _find_slide_job(run_dir, page_index)
    slide_status = _load_slide_status(run_dir)
    key = f"{int(page_index):02d}"
    entry = slide_status.get(key, {})
    title = str(slide_job.get("title", f"slide-{page_index}"))
    img_dir = run_dir / "img"
    image_path = Path(entry.get("image_path") or (img_dir / slide_filename(page_index, title, "png")))
    if not image_path.exists():
        raise RuntimeError(f"Cannot revise img page {page_index}: source image is missing at {image_path}")

    prompt = compile_img_edit_prompt(slide_job, feedback)
    prompt_path = _slide_prompt_path(img_dir, int(page_index), title)
    prompt_path.write_text(prompt, encoding="utf-8")

    client = KrillImageClient()
    client.edit_image(prompt, image_path, image_path)

    slide_status[key] = {
        "title": title,
        "page_role": slide_job.get("page_role", "content"),
        "validation_status": "pass",
        "final_issues_count": 0,
        "review_status": "REVISED",
        "review_rounds": int(entry.get("review_rounds", 0) or 0) + 1,
        "export_ready": True,
        "image_path": str(image_path),
        "prompt_path": str(prompt_path),
        "revision_feedback": feedback,
    }
    _write_slide_status_entry(run_dir, slide_status)

    pptx_path = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    build_pptx_from_images(img_dir, pptx_path)
    state["status"] = "completed"
    state["renderer"] = "img"
    state.setdefault("artifacts", {})["image_pptx"] = {"path": str(pptx_path), "status": "completed"}
    save_state(run_dir, state)
    return image_path


def regenerate_img_slide(run_dir: Path, page_index: int) -> Path:
    require_approved(run_dir, "slide_plans")
    ensure_img_renderer_configured()

    state = load_state(run_dir)
    topic = state.get("topic") or run_dir.name
    slide_job = _find_slide_job(run_dir, page_index)
    slide_status = _load_slide_status(run_dir)
    key = f"{int(page_index):02d}"
    entry = slide_status.get(key, {})
    title = str(slide_job.get("title", f"slide-{page_index}"))
    img_dir = run_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    prompt = compile_img_prompt(slide_job)
    prompt_path = _slide_prompt_path(img_dir, int(page_index), title)
    prompt_path.write_text(prompt, encoding="utf-8")

    image_path = Path(entry.get("image_path") or (img_dir / slide_filename(page_index, title, "png")))
    client = KrillImageClient()
    print(f"[progress] render-img-page regenerating: {page_index} {title}", flush=True)
    client.generate_image(prompt, image_path)
    print(f"[progress] render-img-page done: {page_index} {title}", flush=True)

    slide_status[key] = {
        "title": title,
        "page_role": slide_job.get("page_role", "content"),
        "validation_status": "pass",
        "final_issues_count": 0,
        "review_status": "REGENERATED",
        "review_rounds": int(entry.get("review_rounds", 0) or 0),
        "export_ready": True,
        "image_path": str(image_path),
        "prompt_path": str(prompt_path),
        "regeneration_count": int(entry.get("regeneration_count", 0) or 0) + 1,
    }
    _write_slide_status_entry(run_dir, slide_status)

    pptx_path = run_dir / f"{safe_filename_part(topic, max_length=30)}.pptx"
    build_pptx_from_images(img_dir, pptx_path)
    state["status"] = "completed"
    state["renderer"] = "img"
    state.setdefault("artifacts", {})["image_pptx"] = {"path": str(pptx_path), "status": "completed"}
    save_state(run_dir, state)
    return image_path
