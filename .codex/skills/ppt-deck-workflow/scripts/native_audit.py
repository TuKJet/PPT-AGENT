"""Read actual native objects and their embedded Excel data before publishing a PPTD export."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree as ET
from pptd_runtime import load_mapping, project_path
from pptx_template import A, C, P, R, S, _address, _decimal, _linked, _objects, _range, _slides


def _strings(wb):
    if "xl/sharedStrings.xml" not in wb.namelist():
        return []
    return ["".join(si.itertext(S + "t", with_tail=False))
            for si in ET.fromstring(wb.read("xl/sharedStrings.xml")).findall(S + "si")]


def _cell(cell, shared, numeric):
    if cell is None:
        return None
    if cell.find(S + "f") is not None:
        raise ValueError("formula-backed workbook cell")
    kind, raw = cell.get("t", "n"), cell.findtext(S + "v")
    if numeric:
        if kind != "n":
            raise ValueError("expected an Excel number")
        return _decimal(raw) if raw is not None else None
    if kind == "s" and raw is not None and 0 <= int(raw) < len(shared):
        return shared[int(raw)]
    if kind == "inlineStr":
        return "".join(cell.itertext(S + "t", with_tail=False))
    if kind == "str":
        return raw or ""
    raise ValueError("expected an Excel string")


def _check_reference(series, selector, expected, sheets, shared, numeric=False):
    ref_kind, cache_kind = ("numRef", "numCache") if numeric else ("strRef", "strCache")
    ref = series.find(C + selector + "/" + C + ref_kind)
    if ref is None:
        raise ValueError(f"{selector} has no workbook reference")
    bounds = _range(ref.findtext(C + "f"))
    sheet_name, r1, c1, r2, c2 = bounds
    if sheet_name not in sheets or max(r2-r1, c2-c1) + 1 != len(expected):
        raise ValueError(f"{selector} worksheet or formula range differs from expected")
    cache = ref.find(C + cache_kind)
    count = cache.find(C + "ptCount") if cache is not None else None
    if count is None or int(count.get("val")) != len(expected):
        raise ValueError(f"{selector} cache size differs from expected")
    points = {}
    for pt in cache.findall(C + "pt"):
        i = int(pt.get("idx"))
        if not 0 <= i < len(expected) or i in points:
            raise ValueError(f"{selector} cache index {i} is invalid")
        points[i] = pt.findtext(C + "v")
    for i, value in enumerate(expected):
        addr = _address(bounds, i)[-1]
        source = _cell(sheets[sheet_name].get(addr), shared, numeric)
        cached = points.get(i)
        if numeric:
            cached = _decimal(cached) if cached not in (None, "") else None
            value = _decimal(value) if value is not None else None
        if source != value or cached != value:
            raise ValueError(f"{selector} {sheet_name}!{addr}: expected {value!r}, cache {cached!r}, workbook {source!r}")


def _check_chart(z, slide_part, marker, item):
    part = _linked(z, slide_part, marker.get(R + "id"), "chart")
    chart = ET.fromstring(z.read(part))
    external = chart.find(C + "externalData")
    if external is None:
        raise ValueError("chart has no embedded workbook")
    book = _linked(z, part, external.get(R + "id"), "package")
    with zipfile.ZipFile(io.BytesIO(z.read(book))) as wb:
        shared = _strings(wb)
        sheets = {}
        for sh in ET.fromstring(wb.read("xl/workbook.xml")).iter(S + "sheet"):
            ws = _linked(wb, "xl/workbook.xml", sh.get(R + "id"), "worksheet")
            sheets[sh.get("name")] = {c.get("r"): c for c in ET.fromstring(wb.read(ws)).iter(S + "c")}
    actual = list(chart.iter(C + "ser"))
    expected = item["series"]
    if not expected or len(expected) != len(actual):
        raise ValueError("different number of chart series")
    for ser, spec in zip(actual, expected):
        categories = spec.get("categories", item.get("categories"))
        _check_reference(ser, "tx", [spec["name"]], sheets, shared)
        _check_reference(ser, "cat", categories, sheets, shared)
        _check_reference(ser, "val", spec["values"], sheets, shared, numeric=True)
    return {"series": len(actual), "workbook": book}


def verify_native_objects(pptx: Path, project: Path, slides: list[dict]) -> list[dict]:
    required = [(page["index"], item) for page in slides for item in page.get("plan", {}).get("data_visuals", [])
                if item["editability"] in {"native_chart", "native_table"}]
    if not required:
        return []
    manifest, = Path(project).glob("*.pptd")
    pages = load_mapping(manifest)["pages"]
    receipts = []
    with zipfile.ZipFile(pptx) as z:
        parts = _slides(z)
        for index, item in required:
            kind = "table" if item["editability"] == "native_table" else "chart"
            eid = item["element_id"]
            record = {"slide": index, "element_id": eid, "editability": item["editability"], "status": "passed", "errors": []}
            try:
                if not 1 <= index <= len(parts):
                    raise ValueError("slide number out of range")
                page = load_mapping(project_path(project, pages[index-1]))
                if not any(e.get("elementId") == eid and e.get("elementType") == kind for e in page["elements"]):
                    raise ValueError(f"{kind} absent from the PPTD source page")
                part = parts[index-1]
                matches = [(k, obj) for _, name, k, obj in _objects(ET.fromstring(z.read(part))) if name == eid]
                if len(matches) != 1 or matches[0][0] != kind:
                    raise ValueError(f"expected one native {kind} named {eid!r}")
                obj = matches[0][1]
                if kind == "chart":
                    record.update(_check_chart(z, part, obj, item))
                else:
                    rows = [["\n".join("".join(p.itertext(A + "t", with_tail=False))
                             for p in tc.findall(A + "txBody/" + A + "p"))
                             for tc in tr.findall(A + "tc")] for tr in obj.findall(A + "tr")]
                    if rows != item["cells"]:
                        raise ValueError("native table dimensions or cell contents differ from expected")
                    record.update(rows=len(rows), columns=len(rows[0]))
            except (ValueError, KeyError, IndexError, TypeError, ET.XMLSyntaxError, zipfile.BadZipFile) as exc:
                record.update(status="failed", errors=[f"slide {index} / {eid}: {exc}"])
            receipts.append(record)
    return receipts
