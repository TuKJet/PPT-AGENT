"""Clone a PPTD project's editable sources and update named data fields."""
from __future__ import annotations

import math
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from pptd_runtime import load_mapping, project_path, validate_project, walk


def _documents(template):
    path = Path(template).resolve(strict=True)
    root = path if path.is_dir() else path.parent
    report = validate_project(root)
    manifest = Path(report["manifest"])
    if not path.is_dir() and path != manifest:
        raise ValueError("supply the PPTD manifest or its project directory")
    pages = {rel: load_mapping(project_path(root, rel)) for rel in report["pages"]}
    return root, manifest, pages


def _fields(element):
    # Return the owner and key of each data leaf. Layout/style/encode names
    # cannot be addressed through this inventory.
    kind = element["elementType"]
    if kind == "text":
        yield "content.text", element["content"], "text"
    elif kind == "table":
        for r, row in enumerate(element["rows"]):
            for c, cell in enumerate(row):
                if isinstance(cell.get("text"), str):
                    yield f"rows[{r}][{c}].text", cell, "text"
    elif kind == "chart":
        for r, row in enumerate(element.get("data", {}).get("rows", [])):
            for c, value in enumerate(row):
                if value is None or type(value) in (int, float, str):
                    yield f"data.rows[{r}][{c}]", row, c


def inventory(template):
    _, manifest, pages = _documents(template)
    doc = load_mapping(manifest)
    result = []
    for index, (rel, page) in enumerate(pages.items(), 1):
        fields = [{"element": e["elementId"], "type": e["elementType"], "field": field, "value": parent[key]}
                  for e in page["elements"] for field, parent, key in _fields(e)]
        result.append({"index": index, "path": rel, "pageType": page.get("pageType"), "fields": fields})
    return {"manifest": manifest.name, "title": doc.get("title"), "size": doc.get("size"), "pages": result}


def _page_path(pages, ref):
    if type(ref) is int and 1 <= ref <= len(pages):
        return list(pages)[ref-1]
    if isinstance(ref, str) and ref in pages:
        return ref
    raise ValueError(f"unknown page {ref!r}")


def _apply(pages, changes):
    if not isinstance(changes, list) or not changes:
        raise ValueError("expected a nonempty list of updates")
    dirty, seen = set(), set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"page", "element", "field", "expected", "value"}:
            raise ValueError("each change requires page, element, field, expected and value")
        rel = _page_path(pages, change["page"])
        eid, field = change["element"], change["field"]
        target = (rel, eid, field)
        if target in seen:
            raise ValueError(f"duplicate field update: {target}")
        seen.add(target)
        element = next((e for e in pages[rel]["elements"] if e["elementId"] == eid), None)
        binding = next(((p, k) for f, p, k in _fields(element) if f == field), None) if element else None
        if binding is None:
            raise ValueError(f"unknown data field: {target}")
        parent, key = binding
        old, value = parent[key], change["value"]
        if old != change["expected"] or type(change["expected"]) is bool:
            raise ValueError(f"{target}: expected {change['expected']!r}, found {old!r}")
        if old == value and type(old) is type(value):
            continue
        if isinstance(old, str):
            if not isinstance(value, str):
                raise ValueError(f"{target}: expected text")
            if element["elementType"] in {"text", "table"} and any(re.search(r"</?[A-Za-z][^>]*>", x) for x in (old, value)):
                raise ValueError(f"{target}: rich text requires a run-aware edit")
        elif value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f"{target}: expected a finite number or missing value")
        parent[key] = value
        dirty.add(rel)
    return dirty


def export(template, changes, output):
    root, manifest, pages = _documents(template)
    dest = Path(output).resolve()
    if dest.exists() or dest.is_relative_to(root):
        raise ValueError("output must be a new project outside the input")
    dirty = _apply(pages, changes)
    sources = {obj["src"] for doc in [load_mapping(manifest), *pages.values()]
               for obj in walk(doc) if "src" in obj}
    if (root / "media-sources.json").is_file():
        sources.add("media-sources.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        for rel in {manifest.name, *pages, *sources}:
            target = project_path(stage, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel in dirty:
                target.write_text(yaml.safe_dump(pages[rel], allow_unicode=True, sort_keys=False), encoding="utf-8")
            else:
                shutil.copyfile(project_path(root, rel), target)
        validate_project(stage)
        stage.rename(dest)
    return {"output": str(dest), "source": str(root), "changes": len(changes),
            "pages": len(pages), "changed_pages": sorted(dirty)}


def _series(chart):
    data = chart["data"]
    cols, rows = data["cols"], data["rows"]
    records = []
    for s in chart["series"]:
        kind, encode = s["type"], s.get("encode", {})
        if kind not in {"bar", "line", "area", "pie"}:
            raise ValueError(f"{chart['elementId']}: unsupported category chart {kind}")
        category, measure = ((encode.get("category"), encode.get("value")) if kind == "pie"
                             else (encode.get("x"), encode.get("y")))
        if category not in cols or measure not in cols:
            raise ValueError(f"{chart['elementId']}: invalid series encoding")
        cat, val = cols.index(category), cols.index(measure)
        if kind == "bar" and any(isinstance(row[val], str) for row in rows):
            cat, val = val, cat
        categories = [str(row[cat]) for row in rows]
        values = [row[val] for row in rows]
        if any(x is not None and (type(x) not in (int, float) or not math.isfinite(x)) for x in values):
            raise ValueError(f"{chart['elementId']}: measure column must contain numbers")
        records.append({"name": s.get("name") or cols[val], "categories": categories, "values": values})
    return records


def quarter_expectations(project, changes):
    _, _, pages = _documents(project)
    selected = {(_page_path(pages, c["page"]), c["element"]) for c in changes}
    slides = []
    for index, (rel, page) in enumerate(pages.items(), 1):
        visuals = []
        for el in page["elements"]:
            eid = el["elementId"]
            # A text-only revision should retain workbook editing on other
            # standard category charts in the supplied project.
            category_chart = el["elementType"] == "chart" and all(
                s.get("type") in {"line", "area", "bar", "pie"} for s in el.get("series", []))
            if (rel, eid) not in selected and not category_chart:
                continue
            if el["elementType"] == "chart":
                visuals.append({"element_id": eid, "editability": "native_chart", "series": _series(el)})
            elif el["elementType"] == "table":
                if any(c.get("rowSpan", 1) > 1 or c.get("colSpan", 1) > 1 for row in el["rows"] for c in row):
                    raise ValueError(f"{eid}: merged table cells require an explicit cell mapping")
                visuals.append({"element_id": eid, "editability": "native_table",
                                "cells": [[c.get("text", "") for c in row] for row in el["rows"]]})
        if visuals:
            slides.append({"index": index, "plan": {"data_visuals": visuals}})
    return {"slides": slides}
