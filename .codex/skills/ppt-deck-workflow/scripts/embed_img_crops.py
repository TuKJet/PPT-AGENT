from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image


SVG_IMAGE_TAG = "{http://www.w3.org/2000/svg}image"


def read_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scaled_crop_box(
    source_size: tuple[int, int],
    canvas_size: tuple[int, int],
    box: list[float],
) -> tuple[int, int, int, int]:
    if len(box) != 4:
        raise ValueError("crop box must be [x, y, width, height]")
    x, y, width, height = (float(value) for value in box)
    if width <= 0 or height <= 0:
        raise ValueError("crop width and height must be positive")

    source_width, source_height = source_size
    canvas_width, canvas_height = canvas_size
    scale_x = source_width / canvas_width
    scale_y = source_height / canvas_height
    left = round(x * scale_x)
    top = round(y * scale_y)
    right = round((x + width) * scale_x)
    bottom = round((y + height) * scale_y)
    if left < 0 or top < 0 or right > source_width or bottom > source_height:
        raise ValueError(
            f"crop box {box} maps outside source image {source_width}x{source_height}"
        )
    return left, top, right, bottom


def crop_data_uri(
    source: Image.Image,
    canvas_size: tuple[int, int],
    box: list[float],
) -> str:
    crop = source.crop(scaled_crop_box(source.size, canvas_size, box))
    output = io.BytesIO()
    crop.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def embed_crops(manifest_path: Path, output_path: Path | None = None) -> Path:
    manifest = read_manifest(manifest_path)
    source_path = Path(manifest["source_image_path"])
    svg_path = Path(manifest["svg_path"])
    target_path = output_path or Path(manifest.get("output_path") or svg_path)
    canvas = manifest.get("canvas") or {"width": 1280, "height": 720}
    canvas_size = (int(canvas["width"]), int(canvas["height"]))
    crops = list(manifest.get("crops") or [])

    if not crops:
        raise ValueError(f"crop manifest has no crops: {manifest_path}")

    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ElementTree.parse(svg_path)
    root = tree.getroot()
    images_by_id = {
        element.attrib.get("data-crop-id"): element
        for element in root.iter()
        if element.tag == SVG_IMAGE_TAG and element.attrib.get("data-crop-id")
    }

    with Image.open(source_path) as source:
        source.load()
        for item in crops:
            crop_id = str(item["id"])
            element = images_by_id.get(crop_id)
            if element is None:
                raise ValueError(f"SVG has no <image data-crop-id='{crop_id}'>")
            element.set("href", crop_data_uri(source, canvas_size, list(item["source_box"])))
            element.set("preserveAspectRatio", str(item.get("preserve_aspect_ratio") or "none"))
            element.attrib.pop("data-crop-id", None)

    unresolved = [
        element.attrib.get("data-crop-id")
        for element in root.iter()
        if element.tag == SVG_IMAGE_TAG and element.attrib.get("data-crop-id")
    ]
    if unresolved:
        raise ValueError(f"unresolved crop placeholders remain: {unresolved}")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(target_path, encoding="utf-8", xml_declaration=False)
    return target_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Crop regions directly from a source IMG with Pillow and embed them as "
            "Base64 PNG <image> nodes in the final SVG. No temporary PNG files are written."
        )
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output = embed_crops(
        Path(args.manifest),
        Path(args.output) if args.output else None,
    )
    print(f"embedded_svg={output}", flush=True)


if __name__ == "__main__":
    main()
