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


def write_outline_preview(outline: dict[str, Any], path: Path) -> Path:
    from pipeline import _get_pages, _get_title

    lines = ["# Outline Preview", ""]
    for index, page in enumerate(_get_pages(outline), start=1):
        title = _get_title(page)
        lines.append(f"## {index:02d}. {title}")
        sections = page.get("sections") or page.get("content") or []
        if isinstance(sections, list):
            for item in sections[:6]:
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


def write_plans_preview(slide_jobs: list[dict[str, Any]], path: Path) -> Path:
    lines = ["# Slide Plans Preview", ""]
    for job in slide_jobs:
        lines.extend([
            f"## {job['index']:02d}. {job['title']}",
            "",
            f"- role: {job.get('page_role', 'content')}",
            "",
            str(job.get("plan", "")).strip(),
            "",
        ])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path

