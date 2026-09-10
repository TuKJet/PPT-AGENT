from __future__ import annotations

import argparse
import base64
import io
import json
import math
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from PIL import Image, ImageFilter


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
    if not all(math.isfinite(value) for value in (x, y, width, height)):
        raise ValueError("crop box values must be finite numbers")
    if x < 0 or y < 0 or width <= 0 or height <= 0:
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


def _validated_box(
    value: Any,
    *,
    name: str,
    canvas_size: tuple[int, int],
) -> list[float]:
    """Validate a normalized [x, y, width, height] box before embedding."""
    try:
        values = list(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be [x, y, width, height]") from exc
    if len(values) != 4:
        raise ValueError(f"{name} must be [x, y, width, height]")
    try:
        x, y, width, height = (float(item) for item in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} values must be finite numbers") from exc
    if not all(math.isfinite(item) for item in (x, y, width, height)):
        raise ValueError(f"{name} values must be finite numbers")
    canvas_width, canvas_height = canvas_size
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError(f"{name} must have non-negative origin and positive size")
    if x + width > canvas_width or y + height > canvas_height:
        raise ValueError(f"{name} must stay inside canvas {canvas_width}x{canvas_height}")
    return [x, y, width, height]


def _canvas_box_to_local_crop_box(
    source_size: tuple[int, int],
    canvas_size: tuple[int, int],
    crop_source_box: list[float],
    removal_box: list[float],
) -> tuple[int, int, int, int]:
    crop_left, crop_top, crop_right, crop_bottom = scaled_crop_box(
        source_size, canvas_size, crop_source_box
    )
    left, top, right, bottom = scaled_crop_box(source_size, canvas_size, removal_box)
    if left < crop_left or top < crop_top or right > crop_right or bottom > crop_bottom:
        raise ValueError(
            f"text removal box {removal_box} must stay inside crop box {crop_source_box}"
        )
    return left - crop_left, top - crop_top, right - crop_left, bottom - crop_top


def _pixel_matches_text_mode(pixel: tuple[int, ...], mode: str) -> bool:
    red, green, blue = pixel[:3]
    spread = max(red, green, blue) - min(red, green, blue)
    if mode == "light_neutral":
        return min(red, green, blue) > 125 and spread < 34
    if mode == "dark_neutral":
        return max(red, green, blue) < 140 and spread < 40
    if mode == "all":
        return True
    raise ValueError(
        "text_removal_mode must be light_neutral, dark_neutral, or all"
    )


def remove_text_from_backplate(
    crop: Image.Image,
    local_boxes: list[tuple[int, int, int, int]],
    *,
    mode: str,
    dilation: int,
) -> Image.Image:
    """Remove declared label pixels while retaining surrounding texture/artwork.

    The mask is limited to tight user/model-declared text boxes. Neutral light or
    dark modes preserve colored ornamentation inside those boxes; ``all`` is a
    deliberate fallback for flat/gradient regions with no intersecting artwork.
    Masked runs are filled by horizontal interpolation, which preserves the
    common left-to-right gradients used by presentation plaques and badges.
    """
    result = crop.convert("RGBA")
    mask = Image.new("L", result.size, 0)
    mask_pixels = mask.load()
    source_pixels = result.load()
    width, height = result.size

    for left, top, right, bottom in local_boxes:
        for y in range(max(0, top), min(height, bottom)):
            for x in range(max(0, left), min(width, right)):
                if _pixel_matches_text_mode(source_pixels[x, y], mode):
                    mask_pixels[x, y] = 255

    if dilation:
        size = dilation * 2 + 1
        mask = mask.filter(ImageFilter.MaxFilter(size=size))
        mask_pixels = mask.load()

    output = result.copy()
    output_pixels = output.load()
    for y in range(height):
        x = 0
        while x < width:
            if mask_pixels[x, y] == 0:
                x += 1
                continue
            start = x
            while x < width and mask_pixels[x, y] != 0:
                x += 1
            end = x - 1
            left = start - 1
            right = end + 1
            while left >= 0 and mask_pixels[left, y] != 0:
                left -= 1
            while right < width and mask_pixels[right, y] != 0:
                right += 1
            if left >= 0 and right < width:
                left_color = source_pixels[left, y]
                right_color = source_pixels[right, y]
                span = right - left
                for position in range(start, end + 1):
                    ratio = (position - left) / span
                    output_pixels[position, y] = tuple(
                        round(left_color[channel] * (1 - ratio) + right_color[channel] * ratio)
                        for channel in range(4)
                    )
            elif left >= 0:
                for position in range(start, end + 1):
                    output_pixels[position, y] = source_pixels[left, y]
            elif right < width:
                for position in range(start, end + 1):
                    output_pixels[position, y] = source_pixels[right, y]
    return output


def crop_data_uri(
    source: Image.Image,
    canvas_size: tuple[int, int],
    item: dict[str, Any],
) -> str:
    source_box = _validated_box(
        item["source_box"], name="crop source_box", canvas_size=canvas_size
    )
    crop = source.crop(scaled_crop_box(source.size, canvas_size, source_box))
    if str(item.get("content_type") or "") == "complex_backplate":
        removal_boxes = list(item.get("text_removal_boxes") or [])
        local_boxes = [
            _canvas_box_to_local_crop_box(
                source.size, canvas_size, source_box, list(removal_box)
            )
            for removal_box in removal_boxes
        ]
        crop = remove_text_from_backplate(
            crop,
            local_boxes,
            mode=str(item.get("text_removal_mode") or "light_neutral"),
            dilation=int(item.get("text_removal_dilation", 2)),
        )
    output = io.BytesIO()
    crop.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _manifest_canvas_size(manifest: dict[str, Any]) -> tuple[int, int]:
    canvas = manifest.get("canvas") or {"width": 1280, "height": 720}
    try:
        canvas_size = (int(canvas["width"]), int(canvas["height"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("crop manifest canvas must have numeric width and height") from exc
    if canvas_size[0] <= 0 or canvas_size[1] <= 0:
        raise ValueError("crop manifest canvas must have positive width and height")
    return canvas_size


def validate_crop_entries(
    manifest: dict[str, Any], root: ElementTree.Element, *, embedded: bool = False
) -> list[dict[str, Any]]:
    """Validate crop declarations and their SVG placeholders without writing files."""
    canvas_size = _manifest_canvas_size(manifest)
    crops = list(manifest.get("crops") or [])

    image_elements = [element for element in root.iter() if element.tag == SVG_IMAGE_TAG]
    svg_ids = [str(element.attrib.get("data-crop-id") or "").strip() for element in image_elements]
    if any(not crop_id for crop_id in svg_ids):
        raise ValueError("every SVG <image> crop placeholder must have data-crop-id")
    duplicate_svg_ids = sorted({crop_id for crop_id in svg_ids if svg_ids.count(crop_id) > 1})
    if duplicate_svg_ids:
        raise ValueError(f"SVG crop IDs must be unique: {duplicate_svg_ids}")
    images_by_id = dict(zip(svg_ids, image_elements))

    declared_ids: list[str] = []
    for index, item in enumerate(crops):
        if not isinstance(item, dict):
            raise ValueError(f"crop declaration {index} must be an object")
        crop_id = str(item.get("id") or "").strip()
        if not crop_id:
            raise ValueError(f"crop declaration {index} must have a non-empty id")
        if crop_id in declared_ids:
            raise ValueError(f"crop manifest IDs must be unique: {crop_id}")
        declared_ids.append(crop_id)
        _validated_box(
            item.get("source_box"),
            name=f"crop source_box ({crop_id})",
            canvas_size=canvas_size,
        )
        target_box = _validated_box(
            item["target_box"] if "target_box" in item else item.get("source_box"),
            name=f"crop target_box ({crop_id})",
            canvas_size=canvas_size,
        )
        if embedded and crop_id in images_by_id:
            image = images_by_id[crop_id]
            actual_box = _validated_box(
                [image.get(key, "0") for key in ("x", "y", "width", "height")],
                name=f"SVG image geometry ({crop_id})", canvas_size=canvas_size,
            )
            if not all(math.isclose(a, b, abs_tol=0.01) for a, b in zip(actual_box, target_box)):
                raise ValueError(f"SVG image geometry does not match crop target_box: {crop_id}")

    if set(declared_ids) != set(svg_ids):
        missing = sorted(set(declared_ids) - set(svg_ids))
        extra = sorted(set(svg_ids) - set(declared_ids))
        raise ValueError(f"crop manifest and SVG crop IDs do not match (missing={missing}, extra={extra})")

    return crops


def embed_crops(manifest_path: Path, output_path: Path | None = None) -> Path:
    manifest = read_manifest(manifest_path)
    source_path = Path(manifest["source_image_path"])
    svg_path = Path(manifest["svg_path"])
    target_path = output_path or Path(manifest.get("output_path") or svg_path)
    canvas_size = _manifest_canvas_size(manifest)

    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    tree = ElementTree.parse(svg_path)
    root = tree.getroot()
    crops = validate_crop_entries(manifest, root)
    if not crops:
        raise ValueError(f"crop manifest has no crops: {manifest_path}")
    images_by_id = {
        str(element.attrib["data-crop-id"]).strip(): element
        for element in root.iter()
        if element.tag == SVG_IMAGE_TAG and element.attrib.get("data-crop-id")
    }

    with Image.open(source_path) as source:
        source.load()
        for item in crops:
            crop_id = str(item["id"]).strip()
            element = images_by_id.get(crop_id)
            if element is None:
                raise ValueError(f"SVG has no <image data-crop-id='{crop_id}'>")
            element.set("href", crop_data_uri(source, canvas_size, item))
            target_box = _validated_box(
                item["target_box"] if "target_box" in item else item["source_box"],
                name=f"crop target_box ({crop_id})",
                canvas_size=canvas_size,
            )
            for attribute, value in zip(("x", "y", "width", "height"), target_box):
                element.set(attribute, str(value))
            element.set("preserveAspectRatio", str(item.get("preserve_aspect_ratio") or "none"))

    unresolved = [
        element.attrib.get("data-crop-id")
        for element in root.iter()
        if element.tag == SVG_IMAGE_TAG
        and element.attrib.get("data-crop-id")
        and not str(element.attrib.get("href") or "").startswith("data:image/png;base64,")
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
