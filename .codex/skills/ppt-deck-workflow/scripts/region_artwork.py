"""Draw the approved data at the resolution of the generated slide artwork."""
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_COLORS = ("#2457A6", "#C2410C", "#775398", "#257876", "#A5772B", "#805152")


def series_colors(palette):
    if isinstance(palette, dict):
        return tuple(dict.fromkeys([palette.get("primary", DEFAULT_COLORS[0]),
                                    palette.get("accent", DEFAULT_COLORS[1]), *DEFAULT_COLORS]))
    return tuple(palette or DEFAULT_COLORS)


@lru_cache(maxsize=64)
def _font(size):
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/NotoSansSC-VF.ttf",
                 "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _label(draw, value, box, size, ink):
    if value is None or value == "":
        return
    text = str(value)
    left, top, right, bottom = box
    for points in range(max(8, round(size)), 7, -1):
        font = _font(points)
        x, y, w, h = draw.textbbox((0, 0), text, font=font)
        if w - x <= right - left - 2 and h - y <= bottom - top - 2:
            pos = ((left + right - w - x) / 2, (top + bottom - h - y) / 2)
            draw.text(pos, text, font=font, fill=ink)
            return
    raise ValueError(f"Enlarge the planned data region to fit {text!r}, or reserve it for PPTD.")


def _chart(draw, size, data, kind, font_size, colors, ink, muted):
    width, height = size
    f = font_size
    cols, rows = data["cols"], data["rows"]
    values = [v for row in rows for v in row[1:] if v is not None]
    low, high = min([0, *values]), max([0, *values])
    if low == high:
        high = 1
    ticks = (low, 0 if low < 0 < high else (low + high) / 2, high)
    tick_width = max(draw.textlength(f"{n:g}", font=_font(f)) for n in ticks)
    left, right, top, bottom = round(tick_width + f), width - f, round(2.4 * f), height - 2 * f
    if right <= left or bottom <= top:
        raise ValueError("Enlarge the planned chart region or reserve it for PPTD.")
    def y(value):
        return round(bottom - (value - low) / (high - low) * (bottom - top))
    slot = (right - left) / len(rows)
    def x(i):
        return left + (i + 0.5) * slot

    for tick in ticks:
        py = y(tick)
        draw.line((left, py, right, py), fill=muted if tick == 0 else "#C7CED5")
        _label(draw, f"{tick:g}", (0, py - f, left - 3, py + f), f, muted)
    for i, row in enumerate(rows):
        _label(draw, row[0], (x(i) - slot / 2, bottom + 2, x(i) + slot / 2, height - 1), f, ink)

    series_count = len(cols) - 1
    for j, name in enumerate(cols[1:]):
        color = colors[j % len(colors)]
        legend_width = width / series_count
        start = j * legend_width + f / 2
        draw.line((start, f, start + f, f), fill=color, width=max(2, f // 4))
        _label(draw, name, (start + 1.2 * f, 0, start + legend_width - f, 2 * f), f, ink)
        bar_width = 0.78 * slot / series_count
        previous = None
        for i, row in enumerate(rows):
            value = row[j + 1]
            if value is None:
                previous = None
                continue
            px, py = x(i), y(value)
            if kind == "bar":
                a = px - 0.39 * slot + j * bar_width
                draw.rectangle((a, min(py, y(0)), a + 0.92 * bar_width, max(py, y(0))), fill=color)
            else:
                if previous is not None:
                    draw.line((*previous, px, py), fill=color, width=max(2, round(f / 6)))
                r = max(2, round(f / 4))
                draw.ellipse((px - r, py - r, px + r, py + r), fill=color)
                previous = (px, py)


def _table(draw, size, data, f, colors, surface, ink):
    rows = [data["cols"], *data["rows"]]
    width, height = size
    font = _font(f)
    widths = [max(draw.textlength(str(v), font=font) for v in column if v is not None) + f
              for column in zip(*rows)]
    total = sum(widths)
    for r, row in enumerate(rows):
        left = 0
        for c, value in enumerate(row):
            right = left + width * widths[c] / total
            box = (round(left), round(r * height / len(rows)), round(right), round((r + 1) * height / len(rows)))
            draw.rectangle(box, fill=colors[0] if r == 0 else surface, outline="#CAD1D8")
            _label(draw, value, box, f, "#FFFFFF" if r == 0 else ink)
            left = right


def draw_image(image, regions, palette=None):
    canvas = image.convert("RGB")
    colors = series_colors(palette)
    tokens = palette if isinstance(palette, dict) else {}
    surface = tokens.get("surface", "#FFFFFF")
    ink, muted = tokens.get("text_primary", "#192731"), tokens.get("text_muted", "#536576")
    for region in regions:
        x, y, w, h = region["bounds"]
        left, top = round(x * canvas.width), round(y * canvas.height)
        size = (round((x + w) * canvas.width) - left, round((y + h) * canvas.height) - top)
        if min(size) < 1:
            raise ValueError("The data region is smaller than one image pixel.")
        block = Image.new("RGB", size, surface)
        if region.get("img") != "reserve":
            draw = ImageDraw.Draw(block)
            f = max(10, round(min(canvas.height / 40, size[0] / 16, size[1] / 8)))
            if region["kind"] == "table":
                _table(draw, size, region["data"], f, colors, surface, ink)
            else:
                _chart(draw, size, region["data"], region["kind"], f, colors, ink, muted)
        canvas.paste(block, (left, top))
    return canvas.convert(image.mode)
