from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import OUTPUT_DIR
from filename_utils import safe_filename_part

STATE_FILE = "workflow-state.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_dir_for_topic(topic: str) -> Path:
    return Path(OUTPUT_DIR) / safe_filename_part(topic, max_length=80)


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
        "version": 1,
        "status": "new",
        "approvals": {},
        "artifacts": {},
        "renderer": None,
    })


def save_state(run_dir: Path, state: dict[str, Any]) -> Path:
    state["updated_at"] = utc_now()
    return write_json(run_dir / STATE_FILE, state)


def init_state(run_dir: Path, *, topic: str, audience: str, pages: str,
               provider: str | None, research: str) -> dict[str, Any]:
    state = load_state(run_dir)
    state.update({
        "version": 1,
        "topic": topic,
        "audience": audience,
        "pages": pages,
        "provider": provider,
        "research": research,
        "status": "initialized",
        "created_at": state.get("created_at") or utc_now(),
        "approvals": state.get("approvals") or {},
        "artifacts": state.get("artifacts") or {},
        "renderer": state.get("renderer"),
    })
    save_state(run_dir, state)
    return state


def mark_artifact(run_dir: Path, state: dict[str, Any], name: str, path: Path,
                  *, status: str = "pending_review", preview_path: Path | None = None) -> None:
    entry = {
        "path": str(path),
        "status": status,
        "updated_at": utc_now(),
    }
    if preview_path:
        entry["preview_path"] = str(preview_path)
    state.setdefault("artifacts", {})[name] = entry
    state.setdefault("approvals", {}).setdefault(name, False)
    state["status"] = status
    save_state(run_dir, state)


def approve(run_dir: Path, artifact: str) -> dict[str, Any]:
    state = load_state(run_dir)
    if artifact not in state.get("artifacts", {}):
        raise ValueError(f"unknown artifact: {artifact}")
    state.setdefault("approvals", {})[artifact] = True
    state["artifacts"][artifact]["status"] = "approved"
    state["artifacts"][artifact]["approved_at"] = utc_now()
    state["status"] = f"{artifact}_approved"
    save_state(run_dir, state)
    return state


def require_approved(run_dir: Path, artifact: str) -> None:
    state = load_state(run_dir)
    if not state.get("approvals", {}).get(artifact):
        preview = state.get("artifacts", {}).get(artifact, {}).get("preview_path")
        detail = f" Review {preview} first." if preview else ""
        raise RuntimeError(f"{artifact} is not approved.{detail}")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _string_list(value: Any, limit: int | None = None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [_clean_text(item) for item in value]
    else:
        items = [_clean_text(value)]
    items = [item for item in items if item]
    if limit is not None:
        return items[:limit]
    return items


def _looks_like_markdown(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped:
        return False
    if stripped.startswith(("#", "-", "*", ">")):
        return True
    if len(stripped) > 2 and stripped[0].isdigit() and stripped[1:3] in {". ", ") "}:
        return True
    return False


def _append_text_block(lines: list[str], text: str, *, indent: int = 0) -> None:
    prefix = "  " * indent
    parts = [part.rstrip() for part in text.splitlines()]
    non_empty = [part for part in parts if part.strip()]
    if not non_empty:
        return
    if len(non_empty) == 1:
        lines.append(f"{prefix}- {non_empty[0].strip()}")
        return
    for part in non_empty:
        stripped = part.strip()
        if _looks_like_markdown(stripped):
            lines.append(f"{prefix}{stripped}")
        else:
            lines.append(f"{prefix}- {stripped}")


def _append_preview_value(lines: list[str], value: Any, *, indent: int = 0) -> None:
    prefix = "  " * indent
    if value is None:
        return
    if isinstance(value, str):
        text = value.strip()
        if text:
            _append_text_block(lines, text, indent=indent)
        return
    if isinstance(value, (int, float, bool)):
        lines.append(f"{prefix}- {value}")
        return
    if isinstance(value, list):
        for item in value:
            _append_preview_value(lines, item, indent=indent)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            label = _clean_text(key)
            if not label or item is None:
                continue
            if isinstance(item, (str, int, float, bool)):
                text = _clean_text(item)
                if text:
                    lines.append(f"{prefix}- {label}: {text}")
                continue
            lines.append(f"{prefix}- {label}")
            _append_preview_value(lines, item, indent=indent + 1)
        return
    text = _clean_text(value)
    if text:
        lines.append(f"{prefix}- {text}")


def _format_preview_index(value: Any, fallback: int) -> str:
    try:
        return f"{int(value):02d}"
    except (TypeError, ValueError):
        text = _clean_text(value)
        if text:
            return text
        return f"{fallback:02d}"


def _page_groups(page: dict[str, Any]) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    for key in ("modules", "content_blocks", "blocks"):
        raw_groups = page.get(key) or []
        if not isinstance(raw_groups, list):
            continue
        for group in raw_groups:
            if not isinstance(group, dict):
                continue
            title = (
                _clean_text(group.get("module_title"))
                or _clean_text(group.get("block_title"))
                or _clean_text(group.get("heading"))
                or _clean_text(group.get("title"))
                or _clean_text(group.get("name"))
            )
            points = []
            for point_key in ("points", "bullets", "items", "content", "sections"):
                points = _string_list(group.get(point_key), limit=6)
                if points:
                    break
            if title or points:
                groups.append((title, points))
    return groups


def write_outline_preview(outline: dict[str, Any], path: Path) -> Path:
    from pipeline import _get_pages, _get_title

    lines = ["# Outline Preview", ""]

    header_pairs = [
        ("Deck Title", outline.get("deck_title")),
        ("Audience", outline.get("audience") or outline.get("target_audience")),
        ("Time Basis", outline.get("time_basis") or outline.get("date_baseline")),
        ("Total Pages", outline.get("total_pages") or outline.get("total_slides")),
        ("Style Note", outline.get("style_note")),
        ("Recommended Duration", outline.get("recommended_duration") or outline.get("recommended_duration_minutes")),
    ]
    for label, value in header_pairs:
        values = _string_list(value)
        if not values:
            continue
        if len(values) == 1:
            lines.append(f"- {label}: {values[0]}")
        else:
            lines.append(f"- {label}:")
            for item in values:
                lines.append(f"  - {item}")
    if len(lines) > 2:
        lines.append("")

    for index, page in enumerate(_get_pages(outline), start=1):
        title = _get_title(page)
        lines.append(f"## {index:02d}. {title}")

        for label, key in (
            ("Delivery Hint", "delivery_hint"),
            ("Purpose", "purpose"),
            ("Key Message", "key_message"),
        ):
            text = _clean_text(page.get(key))
            if text:
                lines.append(f"- {label}: {text}")

        direct_points: list[str] = []
        for key in ("sections", "content"):
            direct_points = _string_list(page.get(key), limit=8)
            if direct_points:
                break
        if direct_points:
            for item in direct_points:
                lines.append(f"- {item}")
        else:
            for group_title, points in _page_groups(page):
                if group_title:
                    lines.append(f"- {group_title}")
                for item in points:
                    lines.append(f"  - {item}")

        for label, key in (
            ("Visual Suggestion", "visual_suggestion"),
            ("Speaker Notes", "speaker_notes"),
        ):
            text = _clean_text(page.get(key))
            if text:
                lines.append(f"- {label}: {text}")

        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def write_contents_preview(contents: dict[str, Any], path: Path) -> Path:
    lines = ["# Contents Preview", ""]
    if isinstance(contents, dict):
        if "slides" in contents and isinstance(contents.get("slides"), list):
            entries = []
            for index, item in enumerate(contents["slides"], start=1):
                if not isinstance(item, dict):
                    entries.append((f"Slide {index:02d}", item))
                    continue
                title = (
                    _clean_text(item.get("title"))
                    or _clean_text(item.get("slide_title"))
                    or _clean_text(item.get("page_title"))
                    or f"Slide {index:02d}"
                )
                payload = item.get("material")
                if payload is None:
                    payload = item.get("content")
                if payload is None:
                    payload = item
                entries.append((title, payload))
        elif "pages" in contents and isinstance(contents.get("pages"), list):
            entries = []
            for index, item in enumerate(contents["pages"], start=1):
                if not isinstance(item, dict):
                    entries.append((f"Page {index:02d}", item))
                    continue
                title = (
                    _clean_text(item.get("title"))
                    or _clean_text(item.get("slide_title"))
                    or _clean_text(item.get("page_title"))
                    or f"Page {index:02d}"
                )
                payload = item.get("material")
                if payload is None:
                    payload = item.get("content")
                if payload is None:
                    payload = item
                entries.append((title, payload))
        else:
            entries = list(contents.items())
    elif isinstance(contents, list):
        entries = [(f"Item {index:02d}", item) for index, item in enumerate(contents, start=1)]
    else:
        entries = [("Contents", contents)]

    for title, material in entries:
        lines.extend([f"## {_clean_text(title) or 'Untitled'}", ""])
        _append_preview_value(lines, material)
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def write_plans_preview(slide_jobs: list[dict[str, Any]] | dict[str, Any], path: Path) -> Path:
    lines = ["# Slide Plans Preview", ""]
    if isinstance(slide_jobs, dict):
        jobs = slide_jobs.get("slides") or slide_jobs.get("pages") or slide_jobs.get("jobs") or []
    else:
        jobs = slide_jobs

    for fallback_index, job in enumerate(jobs, start=1):
        if not isinstance(job, dict):
            lines.extend([f"## {fallback_index:02d}. Untitled", ""])
            _append_preview_value(lines, job)
            lines.append("")
            continue

        index = job.get("index") or job.get("page") or job.get("slide") or fallback_index
        title = (
            _clean_text(job.get("title"))
            or _clean_text(job.get("slide_title"))
            or _clean_text(job.get("page_title"))
            or f"Slide {_format_preview_index(index, fallback_index)}"
        )
        lines.extend([f"## {_format_preview_index(index, fallback_index)}. {title}", ""])

        role = _clean_text(job.get("page_role") or job.get("role") or job.get("slide_type"))
        if role:
            lines.append(f"- role: {role}")

        for label, key in (
            ("Summary", "summary"),
            ("Objective", "objective"),
            ("Core Message", "core_message"),
            ("Material", "material"),
            ("Layout", "layout"),
            ("Plan", "plan"),
            ("Visual Direction", "visual_direction"),
            ("Notes", "notes"),
        ):
            if key not in job or job.get(key) is None:
                continue
            lines.append(f"- {label}")
            _append_preview_value(lines, job.get(key), indent=1)
        lines.append("")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path

