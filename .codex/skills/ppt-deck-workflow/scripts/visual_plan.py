"""Validate renderer-neutral, data-driven visual choices in slide plans."""

from __future__ import annotations

import math
from collections.abc import Mapping

_EDITABILITY = {"native_chart", "native_table", "visual"}


class VisualPlanError(ValueError):
    """A data visual declaration is ambiguous or internally inconsistent."""


def _finite(value: object) -> bool:
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value))


def _require_text(item: Mapping, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise VisualPlanError(f"{key} must be a non-empty string")
    return value


def _validate_series(item: Mapping) -> None:
    categories = item.get("categories")
    series = item.get("series")
    if not isinstance(series, list) or not series:
        raise VisualPlanError("series must be a non-empty list")
    for entry in series:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise VisualPlanError("each series needs a non-empty name")
        labels = entry.get("categories", categories)
        if not isinstance(labels, list) or not labels or not all(isinstance(v, str) and v for v in labels):
            raise VisualPlanError("each series needs the ordered category labels")
        values = entry.get("values")
        if not isinstance(values, list) or len(values) != len(labels) or not all(_finite(v) for v in values):
            raise VisualPlanError("series values must be finite numbers matching categories")
        if categories is not None and labels != categories:
            raise VisualPlanError("series categories must agree")


def _validate_cells(item: Mapping) -> None:
    cells = item.get("cells")
    if not isinstance(cells, list) or not cells or not all(isinstance(row, list) and row for row in cells):
        raise VisualPlanError("cells must be a non-empty rectangular list")
    width = len(cells[0])
    if any(len(row) != width or not all(isinstance(value, str) for value in row) for row in cells):
        raise VisualPlanError("cells must be rectangular strings")


def validate_data_visuals(plan: Mapping) -> Mapping:
    """Validate optional ``plan.data_visuals`` and return the original plan."""
    if not isinstance(plan, Mapping):
        raise VisualPlanError("plan must be a mapping")
    visuals = plan.get("data_visuals")
    if visuals is None:
        return plan
    if not isinstance(visuals, list):
        raise VisualPlanError("data_visuals must be a list")
    seen: set[str] = set()
    for item in visuals:
        if not isinstance(item, Mapping):
            raise VisualPlanError("each data visual must be a mapping")
        element_id = _require_text(item, "element_id")
        if element_id in seen:
            raise VisualPlanError("element_id must be stable, simple, and unique")
        seen.add(element_id)
        _require_text(item, "relationship")
        encoding = _require_text(item, "encoding")
        editability = _require_text(item, "editability")
        if editability not in _EDITABILITY or (editability == "native_chart" and encoding in {"table", "native_table"}):
            raise VisualPlanError("encoding and editability conflict")
        _require_text(item, "reason")
        if editability == "native_chart":
            _validate_series(item)
        elif editability == "native_table":
            _validate_cells(item)
    return plan
