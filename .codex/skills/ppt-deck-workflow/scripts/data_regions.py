"""Materialize the approved page data into an IMG or native PPTD elements."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile

from PIL import Image

from pptd_runtime import finite_number, load_manifest, load_mapping, project_path
from region_artwork import draw_image, series_colors


def validate(regions, path="data_regions"):
    if not isinstance(regions, list):
        raise ValueError(f"{path} must be a list")
    ids = set()
    for offset, region in enumerate(regions):
        label = f"{path}[{offset}]"
        if not isinstance(region, dict) or region.get("kind") not in ("line", "bar", "table"):
            raise ValueError(f"{label}.kind must be line, bar or table")
        if region.get("img", "draw") not in ("draw", "reserve"):
            raise ValueError(f"{label}.img must be draw or reserve")
        key = region.get("id")
        if not isinstance(key, str) or not key.strip() or key in ids:
            raise ValueError(f"{label}.id must be nonempty and unique on the page")
        ids.add(key)
        bounds = region.get("bounds")
        if not isinstance(bounds, list) or len(bounds) != 4 or not all(map(finite_number, bounds)):
            raise ValueError(f"{label}.bounds must contain four finite coordinates")
        x, y, width, height = bounds
        if min(x, y) < 0 or min(width, height) <= 0 or max(x + width, y + height) > 1.000000001:
            raise ValueError(f"{label}.bounds must fit the page in normalized coordinates")
        data = region.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"{label}.data must supply cols and rows")
        cols, rows = data.get("cols"), data.get("rows")
        if not isinstance(cols, list) or not cols or not all(isinstance(c, str) and c.strip() for c in cols):
            raise ValueError(f"{label}.data.cols must contain column names")
        chart = region["kind"] != "table"
        if chart and (len(cols) < 2 or len(set(cols)) != len(cols)):
            raise ValueError(f"{label} needs a category column followed by named numeric series")
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{label}.data.rows must contain source data")
        for i, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(cols):
                raise ValueError(f"{label}.data.rows[{i}] has the wrong number of cells")
            for j, cell in enumerate(row):
                if cell is None or finite_number(cell) or (isinstance(cell, str) and (not chart or j == 0)):
                    continue
                raise ValueError(f"{label}.data.rows[{i}][{j}] is not a supported cell value")


def materialize_images(run_dir, images, plan):
    """Replace just the data panels, retaining the artwork to support revisions."""
    cache = run_dir / ".workflow/img-source"
    palette = plan["design_system"]["palette"]
    for target, slide in zip(images, plan["slides"], strict=True):
        regions = slide["plan"].get("data_regions", [])
        source = cache / target.name
        stamp = source.with_suffix(source.suffix + ".sha256")
        if not regions and not source.exists():
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        is_composite = source.is_file() and stamp.is_file() and stamp.read_text() == digest
        if not regions:
            if is_composite:
                shutil.copyfile(source, target)
            source.unlink(missing_ok=True)
            stamp.unlink(missing_ok=True)
            continue
        cache.mkdir(parents=True, exist_ok=True)
        if not is_composite:
            shutil.copyfile(target, source)
        with Image.open(source) as raw:
            rendered = draw_image(raw, regions, palette)
            with NamedTemporaryFile(dir=cache, suffix=target.suffix, delete=False) as pending:
                staged = Path(pending.name)
            try:
                rendered.save(staged, format=raw.format)
                stamp.write_text(hashlib.sha256(staged.read_bytes()).hexdigest())
                staged.replace(target)
            finally:
                staged.unlink(missing_ok=True)


def native_element(region, size, palette):
    x, y, w, h = region["bounds"]
    element = {
        "elementId": f"data-{region['id']}", "managedDataRegion": region["id"],
        "bounds": [x * size[0], y * size[1], w * size[0], h * size[1]],
    }
    cols, rows = region["data"]["cols"], region["data"]["rows"]
    if region["kind"] == "table":
        style = {"firstRowStyle": {"bold": True, "color": "#FFFFFF",
                                   "fill": {"type": "solid", "color": palette["primary"]}},
                 "cellStyle": {"color": palette["text_primary"],
                               "fill": {"type": "solid", "color": palette["surface"]}}}
        return dict(element, elementType="table", style=style, columnWidths=[1 / len(cols)] * len(cols),
                    rowHeights=[1 / (1 + len(rows))] * (1 + len(rows)),
                    rows=[[{"text": "" if cell is None else str(cell)} for cell in row] for row in [cols, *rows]])
    series = []
    colors = series_colors(palette)
    for i, name in enumerate(cols[1:]):
        item = {"type": region["kind"], "name": name, "encode": {"x": cols[0], "y": name}}
        item["fill" if region["kind"] == "bar" else "lineColor"] = colors[i % len(colors)]
        series.append(item)
    return dict(element, elementType="chart", data=region["data"], series=series)


def apply_pptd(run_dir, plan):
    root = run_dir / "pptd"
    _, _, pages, size = load_manifest(root, expected_pages=len(plan["slides"]))
    palette = plan["design_system"]["palette"]
    updates = {}
    for rel, slide in zip(pages, plan["slides"], strict=True):
        path = project_path(root, rel)
        if path.suffix != ".page":
            raise ValueError(f"expected .page file: {rel}")
        page = load_mapping(path)
        existing = page.get("elements", [])
        if not isinstance(existing, list) or any(not isinstance(e, dict) for e in existing):
            raise ValueError(f"invalid PPTD elements in {rel}")
        regions = slide["plan"].get("data_regions", [])
        wanted = {r["id"]: native_element(r, size, palette) for r in regions}
        if not wanted and not any("managedDataRegion" in e for e in existing):
            continue
        elements = []
        for element in existing:
            if "managedDataRegion" not in element:
                elements.append(element)
            elif element["managedDataRegion"] in wanted:
                elements.append(wanted.pop(element["managedDataRegion"]))
        elements.extend(wanted.values())
        if len({e.get("elementId") for e in elements}) != len(elements):
            raise ValueError(f"data region conflicts with an authored element ID in {rel}")
        if elements != existing:
            updates[path] = dict(page, elements=elements)
    for path, page in updates.items():
        with NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as f:
            staged = Path(f.name)
            json.dump(page, f, ensure_ascii=False, indent=2)
        try:
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)
