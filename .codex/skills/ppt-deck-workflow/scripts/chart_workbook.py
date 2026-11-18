"""Bind literal category charts from the PPTD exporter to embedded Excel data."""
from __future__ import annotations

import io
import os
import posixpath
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile

from lxml import etree as ET
import xlsxwriter
from xlsxwriter.utility import xl_col_to_name

from pptx_template import P, C, R, _linked, _serialize, _slides

REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


class ChartWorkbookError(ValueError):
    """An exported chart cannot be safely bound to a workbook."""


def _cached(literal):
    count = int(literal.find(C + "ptCount").get("val"))
    points = {int(p.get("idx")): p.findtext(C + "v") for p in literal.findall(C + "pt")}
    if count < 1 or any(not 0 <= i < count for i in points):
        raise ChartWorkbookError("invalid chart cache point count")
    return [points.get(i) for i in range(count)]


def _bind_literal(literal, formula, numeric=False):
    parent = literal.getparent()
    ref = ET.Element(C + ("numRef" if numeric else "strRef"))
    ET.SubElement(ref, C + "f").text = formula
    parent.replace(literal, ref)
    literal.tag = C + ("numCache" if numeric else "strCache")
    ref.append(literal)


def _bind_series(chart):
    # Build from the delivered chart's cache. The independent readback compares
    # these values to the approved plan after the workbook has been written.
    buf = io.BytesIO()
    book = xlsxwriter.Workbook(buf, {"in_memory": True})
    sheet = book.add_worksheet("Data")
    sheet.write_string(0, 0, "Category")
    categories = None
    series = list(chart.iter(C + "ser"))
    if not series:
        raise ChartWorkbookError("chart contains no series")
    for col, ser in enumerate(series, 1):
        title = ser.find(C + "tx/" + C + "v")
        labels = ser.find(C + "cat/" + C + "strLit")
        points = ser.find(C + "val/" + C + "numLit")
        if title is None or not title.text or labels is None or points is None:
            raise ChartWorkbookError("expected a named category series with literal labels and numeric values")
        current, values = _cached(labels), _cached(points)
        if (categories is not None and current != categories) or len(values) != len(current):
            raise ChartWorkbookError("inconsistent category or value ranges")
        if categories is None:
            categories = current
            for row, label in enumerate(categories, 1):
                if label is None:
                    raise ChartWorkbookError("missing category label")
                sheet.write_string(row, 0, label)
        sheet.write_string(0, col, title.text)
        for row, value in enumerate(values, 1):
            if value not in (None, ""):
                sheet.write_number(row, col, float(value))
        column = xl_col_to_name(col)
        tx = title.getparent()
        ref = ET.Element(C + "strRef")
        tx.replace(title, ref)
        ET.SubElement(ref, C + "f").text = f"Data!${column}$1"
        cache = ET.SubElement(ref, C + "strCache")
        ET.SubElement(cache, C + "ptCount", val="1")
        ET.SubElement(ET.SubElement(cache, C + "pt", idx="0"), C + "v").text = title.text
        _bind_literal(labels, f"Data!$A$2:$A${len(current)+1}")
        _bind_literal(points, f"Data!${column}$2:${column}${len(current)+1}", numeric=True)
    book.close()
    return buf.getvalue()


def _available(prefix, suffix, used):
    index = 1
    while f"{prefix}{index}{suffix}" in used:
        index += 1
    return f"{prefix}{index}{suffix}"


def bind_chart_workbooks(pptx: Path, slides: list[dict]) -> None:
    required = [(slide["index"], v["element_id"]) for slide in slides
                for v in slide.get("plan", {}).get("data_visuals", []) if v["editability"] == "native_chart"]
    if not required:
        return
    updates = {}
    tmp_path = None
    try:
        with zipfile.ZipFile(pptx) as z:
            names = set(z.namelist())
            parts = _slides(z)
            types = ET.fromstring(z.read("[Content_Types].xml"))
            for index, eid in required:
                if not 1 <= index <= len(parts):
                    raise ChartWorkbookError(f"slide {index}: no such slide")
                slide = parts[index-1]
                frames = [f for f in ET.fromstring(z.read(slide)).iter(P + "graphicFrame")
                          if f.find(P + "nvGraphicFramePr/" + P + "cNvPr").get("name") == eid]
                marker = frames[0].find(".//" + C + "chart") if len(frames) == 1 else None
                if marker is None:
                    raise ChartWorkbookError(f"slide {index} / {eid}: no uniquely matching native chart")
                part = _linked(z, slide, marker.get(R + "id"), "chart")
                chart = ET.fromstring(z.read(part))
                if chart.find(C + "externalData") is not None:
                    continue  # Already bound. The verifier checks the actual data.
                directory, filename = posixpath.split(part)
                relpath = f"{directory}/_rels/{filename}.rels"
                rels = (ET.fromstring(z.read(relpath)) if relpath in names else
                        ET.Element(REL + "Relationships", nsmap={None: REL[1:-1]}))
                workbook = _available("ppt/embeddings/ChartData", ".xlsx", names | updates.keys())
                rid = _available("rId", "", {r.get("Id") for r in rels})
                try:
                    updates[workbook] = _bind_series(chart)
                except (ValueError, AttributeError, TypeError) as exc:
                    raise ChartWorkbookError(f"slide {index} / {eid}: {exc}") from exc
                ET.SubElement(rels, REL + "Relationship", Id=rid, Type=R[1:-1]+"/package",
                              Target=posixpath.relpath(workbook, directory))
                external = ET.Element(C + "externalData", {R + "id": rid})
                after = next((el for el in chart if el.tag in {C+"printSettings", C+"userShapes", C+"extLst"}), None)
                chart.insert(chart.index(after) if after is not None else len(chart), external)
                ET.SubElement(types, CT + "Override", PartName="/" + workbook,
                              ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                updates[part], updates[relpath] = _serialize(chart), _serialize(rels)
            if not updates:
                return
            updates["[Content_Types].xml"] = _serialize(types)
            with NamedTemporaryFile(dir=Path(pptx).parent, delete=False) as tmp:
                tmp_path = tmp.name
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as out:
                for info in z.infolist():
                    out.writestr(info, updates.pop(info.filename) if info.filename in updates else z.read(info))
                for part, data in updates.items():
                    out.writestr(part, data)
        os.replace(tmp_path, pptx)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
