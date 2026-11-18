"""Update selected values in a source PPTX while retaining original, unedited package parts."""
from __future__ import annotations

import io
import posixpath
import re
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import NamedTemporaryFile

from lxml import etree as ET
from xlsxwriter.utility import xl_col_to_name, xl_cell_to_rowcol

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
CELL = r"[A-Z]{1,3}[1-9][0-9]*"


class TemplateError(ValueError):
    """The source has no unambiguous writable value at the requested address."""


def _relations(z, source):
    base, name = posixpath.split(source)
    path = posixpath.join(base, "_rels", name + ".rels")
    return ET.fromstring(z.read(path)) if path in z.namelist() else ()


def _target(source, rel):
    target = rel.get("Target", "")
    if not target or rel.get("TargetMode", "Internal") != "Internal":
        raise TemplateError(f"{source}: an embedded part is required")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target)).lstrip("/")


def _linked(z, source, rid, kind):
    matches = [r for r in _relations(z, source)
               if r.get("Id") == rid and r.get("Type", "").endswith("/" + kind)]
    if len(matches) != 1:
        raise TemplateError(f"{source}: unresolved {kind} relationship {rid}")
    part = _target(source, matches[0])
    if part not in z.namelist():
        raise TemplateError(f"missing part: {part}")
    return part


def _slides(z):
    pres = "ppt/presentation.xml"
    root = ET.fromstring(z.read(pres))
    return [_linked(z, pres, s.get(R + "id"), "slide") for s in root.findall(P + "sldIdLst/" + P + "sldId")]


def _objects(root):
    for node in root.iter(P + "sp", P + "graphicFrame"):
        prop = node.find("*/" + P + "cNvPr")
        if prop is None:
            continue
        body = node.find(P + "txBody")
        chart = node.find(".//" + C + "chart")
        table = node.find(".//" + A + "tbl")
        for kind, obj in (("text", body), ("table", table), ("chart", chart)):
            if obj is not None:
                yield int(prop.get("id")), prop.get("name", ""), kind, obj
                break


def _text(body):
    return "".join(body.itertext(A + "t", with_tail=False))


def _update_text(body, expected, value):
    if not isinstance(expected, str) or not isinstance(value, str):
        raise TemplateError("text and table cells require string values")
    old = _text(body)
    if old != expected:
        raise TemplateError(f"expected {expected!r}, found {old!r}")
    if old == value:
        return False
    # Keep the common prefix/suffix in their original rich-text runs.
    prefix = 0
    while prefix < min(len(old), len(value)) and old[prefix] == value[prefix]:
        prefix += 1
    end, new_end = len(old), len(value)
    while end > prefix and new_end > prefix and old[end - 1] == value[new_end - 1]:
        end -= 1
        new_end -= 1
    cursor = 0
    owners = []
    for run in body.iter(A + "t"):
        stop = cursor + len(run.text or "")
        if cursor <= prefix <= end <= stop:
            owners.append((run, cursor))
        cursor = stop
    if len(owners) != 1 or owners[0][0].getparent().tag != A + "r":
        raise TemplateError("update spans formatting runs or a field; specify a smaller change")
    run, start = owners[0]
    text = run.text or ""
    run.text = text[:prefix-start] + value[prefix:new_end] + text[end-start:]
    return True


def _cells(table):
    return {f"{xl_col_to_name(c)}{r}": tc for r, tr in enumerate(table.findall(A + "tr"), 1)
            for c, tc in enumerate(tr.findall(A + "tc"))}


def _range(formula):
    # Sheet names may contain spaces and doubled apostrophes.
    match = re.fullmatch(r"('(?:[^']|'')+'|[^'!\[\]]+)!([$A-Z0-9:]+)", formula or "")
    if not match:
        raise TemplateError(f"unsupported chart formula {formula!r}")
    sheet, coords = match.groups()
    sheet = sheet[1:-1].replace("''", "'") if sheet.startswith("'") else sheet
    cells = coords.replace("$", "").split(":")
    if len(cells) > 2 or any(not re.fullmatch(CELL, cell) for cell in cells):
        raise TemplateError(f"unsupported chart range: {formula}")
    r1, c1 = xl_cell_to_rowcol(cells[0])
    r2, c2 = xl_cell_to_rowcol(cells[-1])
    if r1 > r2 or c1 > c2 or (r1 != r2 and c1 != c2):
        raise TemplateError(f"expected a one-dimensional chart range: {formula}")
    return sheet, r1, c1, r2, c2


def _address(bounds, index):
    sheet, r1, c1, r2, c2 = bounds
    if not 0 <= index <= max(r2-r1, c2-c1):
        raise TemplateError("chart point outside referenced range")
    row = r1 + (index if r1 != r2 else 0)
    col = c1 + (index if c1 != c2 else 0)
    return sheet, row, col, f"{xl_col_to_name(col)}{row+1}"


def _decimal(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise TemplateError("expected a finite numeric chart value") from None
    if not result.is_finite():
        raise TemplateError("expected a finite numeric chart value")
    return result


def _points(series, index):
    ref = series.find(C + "val/" + C + "numRef")
    if ref is None:
        raise TemplateError("chart has no direct numeric value range")
    bounds = _range(ref.findtext(C + "f"))
    points = {int(p.get("idx")): p.find(C + "v") for p in ref.findall(C + "numCache/" + C + "pt")}
    if index not in points or points[index] is None:
        raise TemplateError("chart point has no cached value")
    return ref, points[index], _address(bounds, index)


def _unique_part(z, target, owner, kind):
    # Follow real package relationships even for nonstandard chart part names.
    references = 0
    for path in z.namelist():
        if not path.endswith(".rels") or "/_rels/" not in path:
            continue
        base, name = path.rsplit("/_rels/", 1)
        source = posixpath.join(base, name[:-5])
        for rel in ET.fromstring(z.read(path)):
            if (rel.get("Type", "").endswith("/" + kind) and rel.get("TargetMode") != "External"
                    and _target(source, rel) == target):
                if source != owner:
                    raise TemplateError(f"{target} is shared; scoped update would affect other objects")
                references += 1
    if references != 1:
        raise TemplateError(f"{target} has ambiguous references")


def _serialize(root):
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)


def _write_package(src, dst, updates):
    with zipfile.ZipFile(dst, "w") as out:
        out.comment = src.comment
        for info in src.infolist():
            out.writestr(info, updates[info.filename] if info.filename in updates else src.read(info))


def _update_chart(z, slide, node, change, updates):
    chart_part = _linked(z, slide, node.get(R + "id"), "chart")
    _unique_part(z, chart_part, slide, "chart")
    slide_xml = ET.fromstring(z.read(slide))
    if sum(_linked(z, slide, el.get(R + "id"), "chart") == chart_part for el in slide_xml.iter(C + "chart")) != 1:
        raise TemplateError("multiple objects display the same chart")
    chart = ET.fromstring(updates.get(chart_part) or z.read(chart_part))
    all_series = list(chart.iter(C + "ser"))
    si, pi = change["series"], change["point"]
    if type(si) is not int or not 0 <= si < len(all_series) or type(pi) is not int:
        raise TemplateError("invalid series or point index")
    selected, cached, (sheet, row, col, addr) = _points(all_series[si], pi)
    old = _decimal(change["expected"])
    new = _decimal(change["value"])
    if _decimal(cached.text) != old:
        raise TemplateError(f"cache differs from expected at {sheet}!{addr}")
    # Reject only overlapping cells. Disjoint series normally share a workbook.
    for formula in chart.iter(C + "f"):
        if formula.getparent() == selected:
            continue
        other, r1, c1, r2, c2 = _range(formula.text)
        if other == sheet and r1 <= row <= r2 and c1 <= col <= c2:
            raise TemplateError("another chart reference uses this cell")
    external = chart.find(C + "externalData")
    if external is None:
        raise TemplateError("chart has no embedded workbook")
    book = _linked(z, chart_part, external.get(R + "id"), "package")
    _unique_part(z, book, chart_part, "package")
    with zipfile.ZipFile(io.BytesIO(updates.get(book) or z.read(book))) as wb:
        wpart = "xl/workbook.xml"
        matches = [s for s in ET.fromstring(wb.read(wpart)).iter(S + "sheet") if s.get("name") == sheet]
        if len(matches) != 1:
            raise TemplateError(f"worksheet {sheet!r} not found")
        part = _linked(wb, wpart, matches[0].get(R + "id"), "worksheet")
        ws = ET.fromstring(wb.read(part))
        cell = ws.find(f".//{S}sheetData/{S}row/{S}c[@r='{addr}']")
        if cell is None or cell.get("t", "n") != "n" or cell.find(S + "f") is not None:
            raise TemplateError(f"{sheet}!{addr} must be a numeric input cell")
        v = cell.find(S + "v")
        if v is None or _decimal(v.text) != old:
            raise TemplateError(f"embedded workbook differs from expected at {sheet}!{addr}")
        if old == new:
            return
        v.text = cached.text = str(new)
        buf = io.BytesIO()
        _write_package(wb, buf, {part: _serialize(ws)})
    updates[book] = buf.getvalue()
    updates[chart_part] = _serialize(chart)


def inventory(path):
    result = []
    with zipfile.ZipFile(path) as z:
        for number, part in enumerate(_slides(z), 1):
            row = []
            for sid, name, kind, obj in _objects(ET.fromstring(z.read(part))):
                item = {"shape_id": sid, "name": name, "kind": kind}
                if kind == "text":
                    item["text"] = _text(obj)
                elif kind == "table":
                    item["cells"] = {address: _text(cell) for address, cell in _cells(obj).items()}
                else:
                    cp = _linked(z, part, obj.get(R + "id"), "chart")
                    item["series"] = []
                    chart = ET.fromstring(z.read(cp))
                    for si, ser in enumerate(chart.iter(C + "ser")):
                        ref = ser.find(C + "val/" + C + "numRef")
                        if ref is None or chart.find(C + "externalData") is None:
                            continue
                        labels = {p.get("idx"): p.findtext(C + "v") for p in ser.findall(C + "cat//" + C + "pt")}
                        try:
                            bounds = _range(ref.findtext(C + "f"))
                            points = [{"point": int(p.get("idx")), "value": p.findtext(C + "v"),
                                       "label": labels.get(p.get("idx")), "address": _address(bounds, int(p.get("idx")))[-1]}
                                      for p in ref.findall(C + "numCache/" + C + "pt")]
                        except TemplateError:
                            continue
                        item["series"].append({"series": si, "sheet": bounds[0], "points": points})
                row.append(item)
            result.append({"slide": number, "part": part, "objects": row})
    return {"path": str(path), "slides": result}


def export(template, changes, output):
    template, output = Path(template), Path(output)
    if template.resolve() == output.resolve() or not isinstance(changes, list) or not changes:
        raise TemplateError("require field changes and a separate output path")
    updates, dirty, seen = {}, set(), set()
    with zipfile.ZipFile(template) as z:
        parts = _slides(z)
        pages = {}
        for change in changes:
            if not isinstance(change, dict) or not {"slide", "shape_id", "expected"} <= change.keys():
                raise TemplateError("require slide, shape_id and expected")
            slide, sid = change["slide"], change["shape_id"]
            if type(slide) is not int or not 1 <= slide <= len(parts) or type(sid) is not int:
                raise TemplateError("invalid slide number or shape_id")
            part = parts[slide-1]
            if part not in pages:
                pages[part] = ET.fromstring(z.read(part))
            objects = [(k, obj) for ident, _, k, obj in _objects(pages[part]) if ident == sid]
            if len(objects) != 1:
                raise TemplateError(f"slide {slide}: shape {sid} is missing or ambiguous")
            kind, obj = objects[0]
            fields = {"text": {"text"}, "table": {"cell", "value"}, "chart": {"series", "point", "value"}}[kind]
            if set(change) != {"slide", "shape_id", "expected"} | fields:
                raise TemplateError(f"invalid {kind} update on slide {slide}, shape {sid}")
            key = (part, sid, str(change.get("cell", "")).upper(), change.get("series"), change.get("point"))
            if key in seen:
                raise TemplateError("duplicate change location")
            seen.add(key)
            if kind == "chart":
                _update_chart(z, part, obj, change, updates)
                continue
            if kind == "table":
                obj = _cells(obj).get(key[2])
                if obj is None:
                    raise TemplateError(f"table cell {key[2]} not found")
            if _update_text(obj, change["expected"], change.get("text", change.get("value"))):
                dirty.add(part)
        for part in dirty:
            updates[part] = _serialize(pages[part])
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, delete=False) as tmp:
            staged = Path(tmp.name)
        try:
            _write_package(z, staged, updates)
            staged.replace(output)
        finally:
            staged.unlink(missing_ok=True)
    return {"template": str(template), "output": str(output), "changed_parts": sorted(updates), "changes": len(changes)}
