from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    import pythoncom
    import win32com.client
except ImportError:  # pragma: no cover - depends on local Windows Office environment
    pythoncom = None
    win32com = None


_POWERPOINT_CANDIDATES = (
    Path(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"),
    Path(r"C:\Program Files\Microsoft Office\root\Office15\POWERPNT.EXE"),
    Path(r"C:\Program Files (x86)\Microsoft Office\root\Office15\POWERPNT.EXE"),
)


def _contains_non_ascii(value: str) -> bool:
    return any(ord(ch) > 127 for ch in value)


def _resolve_powerpoint_binary() -> Path | None:
    for candidate in _POWERPOINT_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def detect_powerpoint_render_support() -> dict[str, Any]:
    if pythoncom is None or win32com is None:
        return {
            "available": False,
            "engine": None,
            "reason": "pywin32 unavailable",
            "binary_path": None,
        }

    binary_path = _resolve_powerpoint_binary()
    if binary_path is None:
        return {
            "available": False,
            "engine": None,
            "reason": "POWERPNT.EXE not found",
            "binary_path": None,
        }

    return {
        "available": True,
        "engine": "powerpoint-com",
        "reason": None,
        "binary_path": str(binary_path),
    }


def export_powerpoint_slide_previews(
    ppt_path: Path,
    out_dir: Path,
    slide_count: int,
    prefix: str = "editable-preview",
    width: int = 1280,
    height: int = 720,
) -> dict[str, Any]:
    support = detect_powerpoint_render_support()
    if not support["available"]:
        raise RuntimeError(f"PowerPoint render unavailable: {support['reason']}")

    ppt_path = ppt_path.resolve()
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    use_ascii_workspace = _contains_non_ascii(str(ppt_path)) or _contains_non_ascii(str(out_dir))
    workspace_root: Path | None = None
    export_ppt_path = ppt_path
    export_dir = out_dir
    exported_paths: list[Path] = []

    if use_ascii_workspace:
        workspace_root = Path(tempfile.mkdtemp(prefix="ppt_readback_"))
        export_ppt_path = workspace_root / "deck_editable.pptx"
        export_dir = workspace_root / "preview"
        export_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ppt_path, export_ppt_path)

    app = None
    presentation = None
    pythoncom.CoInitialize()
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        app.Visible = 1
        try:
            app.DisplayAlerts = 0
        except Exception:
            pass

        presentation = app.Presentations.Open(str(export_ppt_path), False, False, False)
        actual_slide_count = int(presentation.Slides.Count)
        if slide_count and actual_slide_count != slide_count:
            raise RuntimeError(
                f"PowerPoint slide count mismatch: exported={actual_slide_count} expected={slide_count}"
            )

        for index in range(1, actual_slide_count + 1):
            export_path = export_dir / f"{prefix}-{index:02d}.png"
            presentation.Slides(index).Export(str(export_path), "PNG", width, height)
            deadline = time.time() + 10.0
            while time.time() < deadline:
                if export_path.exists() and export_path.stat().st_size > 0:
                    break
                time.sleep(0.05)
            if not export_path.exists() or export_path.stat().st_size <= 0:
                raise RuntimeError(f"PowerPoint did not produce preview for slide {index:02d}")

            final_path = out_dir / export_path.name
            if final_path != export_path:
                shutil.copy2(export_path, final_path)
            exported_paths.append(final_path)
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
        if workspace_root is not None:
            shutil.rmtree(workspace_root, ignore_errors=True)

    return {
        "engine": support["engine"],
        "binary_path": support["binary_path"],
        "used_ascii_workspace": use_ascii_workspace,
        "slide_count": len(exported_paths),
        "paths": [str(path) for path in exported_paths],
    }
