"""Audience settings and PowerPoint speaker notes."""
from __future__ import annotations


USE_CONTEXTS = {"live": "现场讲解", "standalone": "独立阅读", "hybrid": "现场与会后兼用"}


def presenter_notes(plan: dict) -> str | None:
    layers = plan.get("copy_layers")
    if layers is None:
        return None
    sections = []
    for field, label in (("talk_track", "讲解"), ("reference", "备查")):
        if layers[field]:
            sections.append("\n".join([label, *layers[field]]))
    return "\n\n".join(sections)


def apply_presenter_notes(slide, plan: dict) -> bool:
    text = presenter_notes(plan)
    if text is None or (not text and not slide.has_notes_slide):
        return False
    frame = slide.notes_slide.notes_text_frame
    if frame is None:
        raise ValueError("PowerPoint notes slide has no body placeholder")
    if frame.text == text:
        return False
    frame.text = text
    return True
