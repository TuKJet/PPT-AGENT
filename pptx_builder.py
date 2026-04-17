from pathlib import Path
import io
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_VERTICAL_ANCHOR, MSO_AUTO_SIZE
from pptx.dml.color import RGBColor

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


ALIGN_MAP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}

VERTICAL_ALIGN_MAP = {
    "top": MSO_VERTICAL_ANCHOR.TOP,
    "middle": MSO_VERTICAL_ANCHOR.MIDDLE,
    "bottom": MSO_VERTICAL_ANCHOR.BOTTOM,
}

SHAPE_MAP = {
    "rect": MSO_AUTO_SHAPE_TYPE.RECTANGLE,
    "rounded_rect": MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
    "oval": MSO_AUTO_SHAPE_TYPE.OVAL,
}


def _rgb(hex_color: str) -> RGBColor:
    value = (hex_color or "#000000").lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _inches(value: float):
    return Inches(value)


def _set_fill(shape, color: str | None, opacity: float | None = None):
    if color:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _rgb(color)
        if opacity is not None:
            shape.fill.transparency = max(0.0, min(1.0, 1.0 - float(opacity)))
    else:
        shape.fill.background()


def _set_line(shape, color: str | None, width: float = 1, opacity: float | None = None):
    if color:
        shape.line.color.rgb = _rgb(color)
        shape.line.width = Pt(width)
        if opacity is not None:
            try:
                shape.line.transparency = max(0.0, min(1.0, 1.0 - float(opacity)))
            except Exception:
                pass
    else:
        shape.line.fill.background()


def add_scene_shape(slide, element: dict):
    shape_type = SHAPE_MAP.get(element.get("shape", "rounded_rect"), MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE)
    shape = slide.shapes.add_shape(
        shape_type,
        _inches(element["x"]),
        _inches(element["y"]),
        _inches(element["w"]),
        _inches(element["h"]),
    )
    _set_fill(shape, element.get("fill"), element.get("fill_opacity"))
    _set_line(shape, element.get("line"), element.get("line_width", 1), element.get("line_opacity"))
    corner_ratio = element.get("corner_ratio")
    if corner_ratio is not None and hasattr(shape, "adjustments") and len(shape.adjustments) > 0:
        shape.adjustments[0] = float(corner_ratio)
    return shape


def add_scene_textbox(slide, element: dict):
    box = slide.shapes.add_textbox(
        _inches(element["x"]),
        _inches(element["y"]),
        _inches(element["w"]),
        _inches(element["h"]),
    )
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True

    selector = str(element.get("source_selector", ""))
    autosize_selectors = {".signal", ".footer-tag", ".header-badge", ".tag"}
    frame.auto_size = MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT if selector in autosize_selectors else MSO_AUTO_SIZE.NONE

    frame.vertical_anchor = VERTICAL_ALIGN_MAP.get(element.get("valign", "top"), MSO_VERTICAL_ANCHOR.TOP)
    frame.margin_left = Pt(element.get("padding_left", 4))
    frame.margin_right = Pt(element.get("padding_right", 4))
    frame.margin_top = Pt(element.get("padding_top", 2))
    frame.margin_bottom = Pt(element.get("padding_bottom", 2))
    p = frame.paragraphs[0]
    p.alignment = ALIGN_MAP.get(element.get("align", "left"), PP_ALIGN.LEFT)
    if element.get("line_spacing"):
        p.line_spacing = Pt(element.get("line_spacing"))
    run = p.add_run()
    run.text = element.get("text", "")
    font = run.font
    font.name = element.get("font_name", "Microsoft YaHei")
    font.size = Pt(element.get("font_size", 12))
    font.bold = bool(element.get("bold", False))
    font.color.rgb = _rgb(element.get("color", "#000000"))
    return box


def add_scene_line(slide, element: dict):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT,
        _inches(element["x1"]),
        _inches(element["y1"]),
        _inches(element["x2"]),
        _inches(element["y2"]),
    )
    line.line.color.rgb = _rgb(element.get("color", "#D0D5DD"))
    line.line.width = Pt(element.get("width", 1.5))
    return line


def render_editable_scene(slide, scene: dict):
    background = scene.get("background")
    if background:
        bg = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
        _set_fill(bg, background)
        _set_line(bg, None)

    for element in scene.get("elements", []):
        element_type = element.get("type")
        if element_type == "shape":
            add_scene_shape(slide, element)
        elif element_type == "textbox":
            add_scene_textbox(slide, element)
        elif element_type == "line":
            add_scene_line(slide, element)
        else:
            raise ValueError(f"Unsupported scene element type: {element_type}")


def build_editable_ppt(scene: dict, output_path: Path) -> Path:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    render_editable_scene(slide, scene)
    prs.save(str(output_path))
    return output_path


def build_editable_deck(scenes: list[dict], output_path: Path) -> Path:
    if not scenes:
        raise ValueError("Scene 列表为空，无法导出可编辑 PPT")

    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]

    for scene in scenes:
        slide = prs.slides.add_slide(blank_layout)
        render_editable_scene(slide, scene)

    prs.save(str(output_path))
    return output_path


def svg_path_to_html(svg_path: Path) -> str:
    svg_content = svg_path.read_text(encoding="utf-8")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0;background:#fff}}</style></head>
<body>{svg_content}</body></html>"""


def svg_to_png_bytes(svg_path: Path) -> bytes:
    from playwright.sync_api import sync_playwright
    html = svg_path_to_html(svg_path)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        page.set_content(html, wait_until="networkidle")
        png = page.locator("svg").first.screenshot(type="png")
        browser.close()
    return png


def save_svg_screenshot(svg_path: Path, image_path: Path) -> Path:
    image_path.write_bytes(svg_to_png_bytes(svg_path))
    return image_path


def write_slide_status(out_dir: Path, slide_status: dict) -> Path:
    import json

    status_path = out_dir / "slide-status.json"
    status_path.write_text(
        json.dumps({"slides": slide_status}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return status_path


def build_pptx(svg_dir: Path, output_path: Path) -> Path:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank_layout = prs.slide_layouts[6]

    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        raise ValueError(f"SVG 目录为空: {svg_dir}")

    for svg_path in svg_files:
        print(f"  插入: {svg_path.name}")
        slide = prs.slides.add_slide(blank_layout)
        try:
            png_bytes = svg_to_png_bytes(svg_path)
            slide.shapes.add_picture(
                io.BytesIO(png_bytes), left=0, top=0,
                width=SLIDE_W, height=SLIDE_H
            )
        except Exception as e:
            print(f"  [警告] {svg_path.name} 失败: {e}，跳过")

    prs.save(str(output_path))
    print(f"PPT 已保存: {output_path}")
    return output_path
