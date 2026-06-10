import argparse
import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from ai_client import AIClient
from config import (
    OUTPUT_DIR,
    SVG_REVIEW_ENABLED,
    SVG_REVIEW_MODEL,
    SVG_REVIEW_PROVIDER,
    SVG_REVIEW_REASONING_EFFORT,
)
from filename_utils import safe_filename_part, slide_filename
from pipeline import (
    step1_outline,
    step2_content,
    step3_plan,
    _get_pages,
    _get_title,
    _infer_page_role,
)
from layout_policy import (
    build_layout_role_guidance,
    build_layout_content_budget,
    build_budget_refinement_feedback,
)
from html_pipeline.html_builder import render_html_with_validation
from playwright_runtime import launch_global_chromium, sync_playwright
from pptx_builder import build_editable_ppt, write_slide_status, save_svg_screenshot

SLIDE_W_IN = 13.33
SLIDE_H_IN = 7.5
PX_PER_IN = 96
FONT_FAMILY = "'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif"

SCENE_SYSTEM = """你是 PPT 结构化版式设计师。你的任务不是输出 SVG/HTML，而是输出一个可被渲染为可编辑 PPT 元素的 scene JSON。

输出要求：
1. 只输出 JSON，不要输出解释或 markdown 代码块
2. JSON 结构必须为：
{
  \"background\": \"#RRGGBB\",
  \"elements\": [ ... ]
}
3. elements 仅允许以下 type：shape / textbox / line
4. shape 字段：type, shape, x, y, w, h, fill, line, line_width(optional)
5. textbox 字段：type, x, y, w, h, text, font_size, color, bold(optional), align(optional)
6. line 字段：type, x1, y1, x2, y2, color, width(optional)
7. 坐标单位是英寸，对应 13.33 x 7.5 的 PPT 页面
8. 页面必须像高质量商业演示页，结构清楚，可编辑，不要碎片化过多
9. summary / ending 页优先：左主右辅 + 底部单条总结；cover 页优先：英雄主观点 + 2 个辅助块
10. 元素数量控制在 18-36 个之间，既要信息完整，也要避免杂乱
11. 所有元素必须在页面安全区域内，不能重叠、不能越界
12. 不要生成背景图片，不要生成复杂装饰 path
13. 内容密度和元素丰富度尽量接近高质量 HTML 演示页，不要因为保守而把页面做空
14. summary / timeline / ending 页优先采用大区块结构，不要堆太多零散小卡片
15. 如果是 timeline 或 summary 页，必须让时间/路径主线一眼可见：用明确的横向或纵向主轴连接节点，不要只靠读者自己推断顺序
16. 避免左右两边都成为主视觉；页面只能有一个主结构，另一侧必须是辅助解释区
17. 底部只能保留一个主要总结区，不要再额外出现第二个页脚式说明区
18. 默认采用更易读字号：正文/说明文字尽量 11-13pt，小标题 14-18pt，标签 10.5-12pt；除圆点编号等极小标记外，不要低于 10pt
19. 控制单个文本框长度：正文尽量 1-2 句，证据卡优先短句，不要为了塞内容把字号压得很小
20. 底部总结区要像 takeaway，而不是普通页脚说明：字号和对比要明显高于普通注释
"""

REVIEW_SYSTEM = """你是独立的 PPT 页面审查员，只负责审查，不负责美化表演。

审查目标：基于页面截图判断该页是否适合作为最终 PPT 页面导出。

审查原则：
1. 优先判断信息密度、视觉层级、重点突出、模块数量、页脚干扰、节奏感
2. 如果页面可接受，输出 PASS
3. 如果页面不可接受，输出 REVISE，并给出最多 4 条保守、可执行的修改建议
4. 建议优先偏局部几何修复，不要轻易删空页面

输出格式必须严格如下：
RESULT: PASS 或 RESULT: REVISE
REASONS:
- ...
- ...
SUGGESTIONS:
- ...
- ..."""


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or '#000000').lstrip('#')
    if len(value) == 3:
        value = ''.join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _is_dark_color(hex_color: str) -> bool:
    """判断颜色是否为深色（基于相对亮度）"""
    r, g, b = _hex_to_rgb(hex_color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 128


def _extract_gradient_base_color(gradient_str: str) -> str | None:
    """从 CSS gradient 字符串中提取 base color（最后一个 solid hex 或 rgb）。

    CSS gradient 通常写法如：
      radial-gradient(...), radial-gradient(...), #000000
      linear-gradient(135deg, #050505 0%, #111214 100%)
      radial-gradient(...), linear-gradient(135deg, #050505 0%, ..., #111214 100%)

    策略：提取所有 hex 颜色，取最后一个不透明的作为 base。
    """
    # 先检查 gradient 末尾是否有独立的 solid hex（如 "...), #000000"）
    tail_hex = re.search(r',\s*#([0-9A-Fa-f]{6})\s*$', gradient_str)
    if tail_hex:
        return f'#{tail_hex.group(1).upper()}'

    # 从 linear-gradient 的最后一个 color stop 提取
    all_hex = re.findall(r'#([0-9A-Fa-f]{6})', gradient_str)
    if all_hex:
        return f'#{all_hex[-1].upper()}'

    # 尝试 rgb/rgba，取最后一个不透明的
    all_rgba = list(re.finditer(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)', gradient_str))
    for m in reversed(all_rgba):
        alpha = float(m.group(4) or '1')
        if alpha >= 0.8:
            r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f'#{r:02X}{g:02X}{b:02X}'

    return None




def _blend_color(color: tuple[int, int, int], alpha: float, base: str) -> str:
    base_r, base_g, base_b = _hex_to_rgb(base)
    r = round(color[0] * alpha + base_r * (1 - alpha))
    g = round(color[1] * alpha + base_g * (1 - alpha))
    b = round(color[2] * alpha + base_b * (1 - alpha))
    return f'#{r:02X}{g:02X}{b:02X}'


def _pick_fill_color(style: dict, fallback: str | None = '#FFFFFF', blend_base: str | None = None) -> str | None:
    color = style.get('backgroundColor') or style.get('borderColor') or fallback or ''
    background_image = str(style.get('backgroundImage') or '')
    if color in {'rgba(0, 0, 0, 0)', 'transparent', ''} and 'gradient' in background_image:
        # 优先提取 gradient 的 base color（最后一个 solid 色）
        base_color = _extract_gradient_base_color(background_image)
        if base_color:
            return base_color
        # fallback: 取第一个 hex
        hex_match = re.search(r'#([0-9A-Fa-f]{6})', background_image)
        if hex_match:
            return f"#{hex_match.group(1).upper()}"
        rgb_match = re.search(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?', background_image)
        if rgb_match:
            r, g, b = (int(rgb_match.group(i)) for i in range(1, 4))
            alpha = float(rgb_match.group(4) or '1')
            if alpha < 1:
                return _blend_color((r, g, b), alpha, blend_base or fallback or '#000000')
            return f'#{r:02X}{g:02X}{b:02X}'
    if color in {'rgba(0, 0, 0, 0)', 'transparent', ''}:
        return fallback
    if color.startswith('#'):
        return color
    match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?', color)
    if match:
        r, g, b = (int(match.group(i)) for i in range(1, 4))
        alpha = float(match.group(4) or '1')
        if alpha <= 0:
            return fallback
        if alpha < 1:
            return _blend_color((r, g, b), alpha, blend_base or fallback or '#000000')
        return f'#{r:02X}{g:02X}{b:02X}'
    return fallback


def _pick_text_color(style: dict, fallback: str = '#111827', blend_base: str = '#FFFFFF') -> str:
    color = style.get('color') or fallback
    if color.startswith('#'):
        return color
    match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?', color)
    if match:
        r, g, b = (int(match.group(i)) for i in range(1, 4))
        alpha = float(match.group(4) or '1')
        if alpha <= 0:
            return fallback
        if alpha < 1:
            return _blend_color((r, g, b), alpha, blend_base)
        return f'#{r:02X}{g:02X}{b:02X}'
    return fallback

def _border_width(style: dict) -> float:
    raw = str(style.get('borderWidth', '0')).replace('px', '').strip()
    try:
        return float(raw or 0)
    except ValueError:
        return 0.0


def _px_to_in(value: float) -> float:
    return round(value / PX_PER_IN, 3)



def _pick_stroke_color(style: dict, fallback: str = '#B98746', blend_base: str = '#FFFFFF') -> str:
    stroke = style.get('stroke') or fallback
    if stroke in {'none', 'transparent', ''}:
        return fallback
    if stroke.startswith('#'):
        return stroke
    match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?', stroke)
    if match:
        r, g, b = (int(match.group(i)) for i in range(1, 4))
        alpha = float(match.group(4) or '1')
        if alpha <= 0:
            return fallback
        if alpha < 1:
            return _blend_color((r, g, b), alpha, blend_base)
        return f'#{r:02X}{g:02X}{b:02X}'
    return fallback


def _pick_stroke_width(style: dict, fallback: float = 1.5) -> float:
    raw = str(style.get('strokeWidth') or '').replace('px', '').strip()
    if not raw:
        raw = str(style.get('borderWidth') or '').replace('px', '').strip()
    try:
        return max(0.5, float(raw or fallback))
    except ValueError:
        return fallback


def _dedupe_points(points: list[dict], min_delta: float = 6.0) -> list[dict]:
    deduped = []
    for point in points:
        if not deduped:
            deduped.append(point)
            continue
        last = deduped[-1]
        if abs(point['x'] - last['x']) + abs(point['y'] - last['y']) < min_delta:
            continue
        deduped.append(point)
    return deduped


def _route_to_scene_lines(route: dict, slide_rect: dict) -> list[dict]:
    points = _dedupe_points(route.get('points') or [])
    if len(points) < 2:
        return []
    color = _pick_stroke_color(route.get('style') or {})
    width = round(_pick_stroke_width(route.get('style') or {}) * 0.75, 2)
    lines = []
    for start, end in zip(points, points[1:]):
        lines.append({
            'type': 'line',
            'x1': _px_to_in(start['x'] - slide_rect['x']),
            'y1': _px_to_in(start['y'] - slide_rect['y']),
            'x2': _px_to_in(end['x'] - slide_rect['x']),
            'y2': _px_to_in(end['y'] - slide_rect['y']),
            'color': color,
            'width': width,
        })
    return lines


def _build_route_scene(route_entries: list[dict], slide_rect: dict) -> list[dict]:
    lines = []
    for route in route_entries or []:
        lines.extend(_route_to_scene_lines(route, slide_rect))
    return lines


def _parse_css_color_with_alpha(value: str) -> tuple[str | None, float]:
    raw = str(value or '').strip()
    if not raw:
        return None, 0.0
    if raw.startswith('#'):
        return raw.upper(), 1.0
    match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?', raw)
    if not match:
        return None, 0.0
    r, g, b = (int(match.group(i)) for i in range(1, 4))
    alpha = float(match.group(4) or '1')
    if alpha <= 0:
        return None, 0.0
    return f'#{r:02X}{g:02X}{b:02X}', alpha


def _extract_radial_glow_specs(background_image: str) -> list[dict]:
    pattern = re.compile(
        r'radial-gradient\(\s*circle at\s*([^,]+),\s*(rgba?\([^\)]+\)|#[0-9a-fA-F]{6})\s*,\s*transparent\s+([0-9.]+)%\s*\)',
        re.IGNORECASE,
    )
    specs = []
    for match in pattern.finditer(str(background_image or '')):
        color, alpha = _parse_css_color_with_alpha(match.group(2))
        if not color or alpha <= 0:
            continue
        specs.append({
            'position': str(match.group(1) or '').strip().lower(),
            'color': color,
            'alpha': alpha,
            'stop': max(12.0, min(float(match.group(3) or 24), 42.0)),
        })
    return specs[:3]


def _build_background_glow_scene(background_image: str) -> list[dict]:
    glow_elements = []
    for spec in _extract_radial_glow_specs(background_image):
        base_size_px = max(1280, 720)
        outer_size_px = max(260, round(base_size_px * max(0.28, min((spec['stop'] / 100.0) * 1.5, 0.66))))
        inner_size_px = max(180, round(outer_size_px * 0.62))
        outer_size = _px_to_in(outer_size_px)
        inner_size = _px_to_in(inner_size_px)
        outer_alpha = max(0.04, min(spec['alpha'] * 0.95, 0.10))
        inner_alpha = max(0.06, min(spec['alpha'] * 1.35, 0.15))

        position = spec['position']
        if 'top right' in position or 'right top' in position or '100% 0%' in position:
            outer_x = SLIDE_W_IN - outer_size * 0.88
            outer_y = -outer_size * 0.22
        elif 'bottom left' in position or 'left bottom' in position or '0% 100%' in position:
            outer_x = -outer_size * 0.18
            outer_y = SLIDE_H_IN - outer_size * 0.78
        elif 'bottom right' in position or 'right bottom' in position or '100% 100%' in position:
            outer_x = SLIDE_W_IN - outer_size * 0.84
            outer_y = SLIDE_H_IN - outer_size * 0.76
        else:
            outer_x = -outer_size * 0.18
            outer_y = -outer_size * 0.22

        inner_x = outer_x + round((outer_size - inner_size) * 0.5, 3)
        inner_y = outer_y + round((outer_size - inner_size) * 0.5, 3)
        for x, y, size, alpha in (
            (outer_x, outer_y, outer_size, outer_alpha),
            (inner_x, inner_y, inner_size, inner_alpha),
        ):
            glow_elements.append({
                'type': 'shape',
                'shape': 'oval',
                'x': round(x, 3),
                'y': round(y, 3),
                'w': round(size, 3),
                'h': round(size, 3),
                'fill': spec['color'],
                'fill_opacity': round(alpha, 3),
                'line': None,
                'line_width': 0.0,
                'source_selector': '_bg_glow',
                '_dom_order': -1000,
            })
    return glow_elements


def _append_cover_visual_scene(scene: dict):
    elements = scene.setdefault('elements', [])
    elements.extend([
        {
            'type': 'line',
            'x1': 6.64,
            'y1': 3.26,
            'x2': 11.62,
            'y2': 3.26,
            'color': '#6EE7B7',
            'width': 3.0,
        },
        {
            'type': 'shape',
            'shape': 'oval',
            'x': 5.95,
            'y': 2.24,
            'w': 0.79,
            'h': 0.79,
            'fill': '#1F2937',
            'line': '#374151',
            'line_width': 0.75,
            'source_selector': '.icon',
        },
        {
            'type': 'shape',
            'shape': 'oval',
            'x': 7.42,
            'y': 1.76,
            'w': 0.79,
            'h': 0.79,
            'fill': '#1F2937',
            'line': '#374151',
            'line_width': 0.75,
            'source_selector': '.icon',
        },
        {
            'type': 'shape',
            'shape': 'oval',
            'x': 8.95,
            'y': 1.76,
            'w': 0.79,
            'h': 0.79,
            'fill': '#1F2937',
            'line': '#374151',
            'line_width': 0.75,
            'source_selector': '.icon',
        },
        {
            'type': 'shape',
            'shape': 'oval',
            'x': 10.5,
            'y': 2.24,
            'w': 0.79,
            'h': 0.79,
            'fill': '#1F2937',
            'line': '#374151',
            'line_width': 0.75,
            'source_selector': '.icon',
        },
        {
            'type': 'shape',
            'shape': 'oval',
            'x': 0.43,
            'y': 0.39,
            'w': 0.08,
            'h': 0.08,
            'fill': '#22C55E',
            'line': None,
            'line_width': 0.0,
            'source_selector': '.eyebrow-dot',
        },
    ])


def extract_html_layout_to_scene(html_path: Path, page_role: str = 'summary') -> tuple[dict, bytes, list[str]]:
    png_bytes, report = render_html_with_validation(html_path)
    final_report = report.get('final_report') or {}

    html_content = html_path.read_text(encoding='utf-8')
    with sync_playwright() as p:
        browser = launch_global_chromium(p)
        page = browser.new_page(viewport={'width': 1280, 'height': 720})
        page.set_content(html_content, wait_until='networkidle')
        dom = page.evaluate(
            """
            () => {
              const selectors = [
                '.slide', '.header', '.title-wrap', '.title-row', '.eyebrow', '.eyebrow-dot', 'h1', '.subtitle', '.header-tag', '.header-badge',
                '.main', '.content', '.card', '.left-card', '.right-card', '.map-card', '.story-card', '.main-card', '.side-card', '.card-inner', '.card-desc', '.footer', '.footer-card', '.footer-title',
                '.hero-card', '.hero-top', '.hero-copy', '.hero-visual', '.hero-line', '.cycle', '.arc', '.icon',
                '.map-stage', '.left-visual', '.right-copy', '.visual-title', '.mini-badge',
                '.node', '.pin', '.label', '.desc', '.node-title', '.node-time', '.node-desc', '.bean', '.continent', '.rule', '.summary',
                '.hero-kicker', '.hero-headline', '.hero-body', '.info-block', '.big-number', '.big-kpi', '.big-num', '.big-unit', '.info-text',
                '.title', '.step-desc', '.mini-tag', '.pill', '.metric-label', '.metric', '.metric-value', '.metric-note', '.card-sub',
                '.card-kicker', '.card-title', '.lead', '.value-item', '.num', '.value-name', '.chip',
                '.value-text', '.metric-wrap', '.metric-num', '.metric-unit', '.metric-desc',
                '.tag-row', '.tag', '.tags', '.map-body', '.map-figure', '.route-note', '.legend-band', '.legend-pill',
                '.steps', '.step', '.step-num', '.step-content', '.step-title', '.step-text', '.step-note', '.step-top', '.step-icon',
                '.step-item', '.step-no', '.right-tags', '.footer-text', '.footer-pill', '.footer-label', '.footer-tags',
                '.stage', '.stage-title', '.stage-time', '.stage-head', '.stage-no', '.stage-text', '.timeline', '.timeline-card', '.timeline-grid', '.summary-card', '.summary-intro', '.summary-metrics',
                '.center-badge', '.center-number', '.center-text',
                '.definition', '.definition-badge', '.definition-text',
                '.highlight', '.highlight-row', '.highlight-label', '.highlight-number', '.highlight-text',
                '.arrow-row', '.arrow',
                '.support', '.support-item', '.support-title', '.support-desc', '.support-text', '.support-label', '.support-list',
                '.mini-stat', '.mini-label', '.mini-value', '.mini-desc', '.mini-tags',
                '.point-list', '.point', '.dot',
                '.process-card', '.process-head', '.process-note',
                '.side-main', '.accent-red', '.accent-green',
                '.accent', '.badge', '.big', '.blue', '.bullet-text', '.card-label',
                '.compare-title', '.conclusion-text', '.emphasis', '.era',
                '.event-desc', '.event-title', '.focus-title', '.focus-text', '.focus-box',
                '.footer-main', '.footer-quote', '.footer-tag', '.gold', '.gray',
                '.highlight-big', '.highlight-title',
                '.k', '.keyword', '.layer-desc', '.layer-name',
                '.mini-chip', '.mini-text', '.mini-line',
                '.n', '.page-tag', '.pill-core', '.pill-left', '.pill-right',
                '.range-block', '.range-caption', '.range-label', '.range-years',
                '.right-note', '.signal', '.signal-key', '.signal-text', '.signal-item', '.signal-list',
                '.small', '.stat-main', '.stat-sub', '.summary-text',
                '.support-line', '.support-num',
                '.time', '.time-item', '.time-label', '.time-text', '.year',
                '.compare', '.compare-panel', '.conclusion-card', '.conclusion-top',
                '.hero-text', '.metrics', '.metric-box',
                '.mini-list', '.note-card', '.node-title',
                '.outlook-card', '.outlook-top',
                '.left-col', '.right-col', '.left', '.right',
                '.col', '.big-stat', '.bullet', '.bullets',
                '.fromto', '.stack', '.base', '.mid', '.top',
                '.timeline-item', '.timeline-list', '.timeline-line', '.timeline-wrap',
                '.dot-col', '.arrow-cell', '.arrow-wrap',
                '.big-point', '.keywords',
                '.scene', '.scene-list',
                '.step-body', '.step-tags',
                '.ai', '.mix',
                'h2', 'h3', 'h4', 'p', 'li'
              ];
              const rectOf = (el) => {
                const r = el.getBoundingClientRect();
                return {x: r.left, y: r.top, w: r.width, h: r.height};
              };
              const styleOf = (el) => {
                const s = getComputedStyle(el);
                return {
                  color: s.color,
                  backgroundColor: s.backgroundColor,
                  backgroundImage: s.backgroundImage,
                  borderColor: s.borderColor,
                  borderRadius: s.borderRadius,
                  borderWidth: s.borderWidth,
                  fontSize: s.fontSize,
                  lineHeight: s.lineHeight,
                  fontWeight: s.fontWeight,
                  textAlign: s.textAlign,
                  stroke: s.stroke,
                  strokeWidth: s.strokeWidth,
                };
              };
              const depthOf = (el) => {
                let d = 0;
                let n = el;
                while (n.parentElement) { d++; n = n.parentElement; }
                return d;
              };
              const seenEls = new Set();
              // 先收集所有匹配元素及其 DOM 引用
              const collected = [];
              for (const selector of selectors) {
                document.querySelectorAll(selector).forEach((el, index) => {
                  if (seenEls.has(el)) return;
                  seenEls.add(el);
                  const text = (el.innerText || '').trim();
                  const rect = rectOf(el);
                  if (rect.w < 8 || rect.h < 8) return;
                  collected.push({ el, selector, index, text, rect, style: styleOf(el), depth: depthOf(el) });
                });
              }
              // 按 DOM 文档顺序排序
              collected.sort((a, b) => {
                const pos = a.el.compareDocumentPosition(b.el);
                if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
                if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
                return 0;
              });
              const picked = collected.map((item, i) => ({
                selector: item.selector,
                index: item.index,
                text: item.text,
                rect: item.rect,
                style: item.style,
                depth: item.depth,
                domOrder: i,
              }));

              const routes = Array.from(document.querySelectorAll('svg.route path:not(.shadow)')).map((path) => {
                const svg = path.ownerSVGElement;
                const svgRect = svg.getBoundingClientRect();
                const viewBox = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal : {x: 0, y: 0, width: svgRect.width, height: svgRect.height};
                const totalLength = typeof path.getTotalLength === 'function' ? path.getTotalLength() : 0;
                const sampleCount = totalLength > 0 ? 12 : 0;
                const points = [];
                for (let i = 0; i <= sampleCount; i++) {
                  const pt = path.getPointAtLength(totalLength * i / sampleCount);
                  const px = svgRect.left + ((pt.x - viewBox.x) / (viewBox.width || svgRect.width || 1)) * svgRect.width;
                  const py = svgRect.top + ((pt.y - viewBox.y) / (viewBox.height || svgRect.height || 1)) * svgRect.height;
                  points.push({x: px, y: py});
                }
                return {
                  points,
                  style: styleOf(path),
                };
              }).filter((item) => item.points.length >= 2);

              return {picked, routes};
            }
            """
        )

        # 提取 body 和 html 的背景色作为 slide 背景的 fallback
        page_bg_info = page.evaluate("""() => {
            const body = document.body;
            const html = document.documentElement;
            const bs = getComputedStyle(body);
            const hs = getComputedStyle(html);
            return {
                body_bg: bs.backgroundColor,
                body_bgImage: bs.backgroundImage,
                html_bg: hs.backgroundColor,
                html_bgImage: hs.backgroundImage,
            };
        }""")

        browser.close()

    picked = dom['picked']
    route_entries = dom.get('routes') or []

    slide_rect = next(item['rect'] for item in picked if item['selector'] == '.slide')
    slide_style = next(item['style'] for item in picked if item['selector'] == '.slide')

    # 提取 slide 背景色，如果 .slide 透明则依次检查 body → html
    slide_bg = _pick_fill_color(slide_style, None)
    if slide_bg is None or slide_bg == '#FFFFFF':
        # .slide 没有有效背景，尝试 body
        body_bg = _pick_fill_color(
            {'backgroundColor': page_bg_info.get('body_bg', ''), 'backgroundImage': page_bg_info.get('body_bgImage', '')},
            None,
        )
        if body_bg is not None:
            slide_bg = body_bg
    if slide_bg is None or slide_bg == '#FFFFFF':
        # body 也没有，尝试 html
        html_bg = _pick_fill_color(
            {'backgroundColor': page_bg_info.get('html_bg', ''), 'backgroundImage': page_bg_info.get('html_bgImage', '')},
            None,
        )
        if html_bg is not None:
            slide_bg = html_bg
    if slide_bg is None:
        slide_bg = '#F7F8FA'

    scene = {
        'background': slide_bg,
        'elements': []
    }

    scene['elements'].extend(_build_background_glow_scene(slide_style.get('backgroundImage', '')))

    # 主题感知：根据背景色判断深/浅色主题，调整各类 fallback
    dark_theme = _is_dark_color(scene['background'])
    fill_fallback = '#1A1A2E' if dark_theme else '#FFFFFF'
    text_fallback = '#E5E7EB' if dark_theme else '#111827'
    text_blend_base = scene['background'] if dark_theme else '#FFFFFF'

    container_selectors = {
        '.card', '.footer-card', '.value-item', '.step-item', '.metric-wrap', '.metric',
        '.map-card', '.story-card', '.map-figure', '.route-note', '.legend-band', '.step',
        '.hero-card', '.map-stage', '.info-block', '.stage', '.timeline', '.timeline-card', '.summary-card', '.node', '.center-badge', '.cycle',
        '.main-card', '.side-card', '.card-inner', '.process-card',
        '.definition', '.highlight', '.highlight-row', '.support', '.support-item',
        '.mini-stat', '.point', '.big-kpi', '.support-list', '.timeline-grid',
        '.compare', '.compare-panel', '.conclusion-card', '.conclusion-top',
        '.outlook-card', '.outlook-top', '.note-card',
        '.focus-box', '.range-block', '.signal-item', '.signal-list',
        '.metric-box', '.metrics', '.mini-list',
        '.left-col', '.right-col', '.left-card', '.right-card',
        '.col', '.big-stat', '.bullet', '.bullets',
        '.stack', '.scene', '.scene-list',
        '.timeline-item', '.timeline-list', '.timeline-wrap',
        '.dot-col', '.arrow-cell', '.arrow-wrap',
        '.step-body', '.step-tags', '.step-content',
        '.big-point', '.keywords',
    }
    text_background_selectors = {
        '.eyebrow', '.header-tag', '.lead', '.num', '.chip', '.step-no', '.footer-pill',
        '.tag', '.legend-pill', '.step-note', '.footer-label', '.mini-badge', '.mini-tag', '.pill',
        '.header-badge', '.definition-badge', '.dot', '.stage-no', '.process-note',
        '.badge', '.mini-chip', '.page-tag', '.footer-tag',
        '.era', '.k', '.keyword', '.year',
        '.gold', '.blue', '.gray',
        '.pill-core', '.pill-left', '.pill-right',
        '.n', '.small', '.big', '.time',
    }
    text_selectors = {
        '.eyebrow', 'h1', '.subtitle', '.header-tag', '.card-kicker', '.card-title', '.lead',
        '.num', '.value-name', '.chip', '.value-text', '.metric-num', '.metric-unit', '.metric-desc', '.metric-label', '.metric-value', '.metric-note',
        '.tag', '.route-note', '.legend-pill', '.step-num', '.step-title', '.step-text', '.step-note', '.step-desc',
        '.step-no', '.footer-text', '.footer-pill', '.footer-label',
        '.visual-title', '.mini-badge', '.mini-tag', '.pill', '.label', '.desc', '.node-title', '.node-time', '.node-desc', '.summary', '.title', '.card-sub',
        '.hero-kicker', '.hero-headline', '.hero-body', '.hero-line', '.big-number', '.info-text', '.stage-title', '.stage-time', '.center-number', '.center-text', '.summary-intro',
        '.header-badge', '.definition-badge', '.definition-text',
        '.highlight-label', '.highlight-number', '.highlight-text',
        '.support-title', '.support-desc', '.support-text', '.support-label',
        '.mini-label', '.mini-value', '.mini-desc',
        '.dot', '.stage-no', '.stage-text', '.card-desc',
        '.big-num', '.big-unit', '.side-main', '.footer-title', '.process-note',
        '.point', '.arrow-row',
        '.accent', '.badge', '.big', '.blue', '.bullet-text', '.card-label',
        '.compare-title', '.conclusion-text', '.emphasis', '.era',
        '.event-desc', '.event-title', '.focus-title', '.focus-text',
        '.footer-main', '.footer-quote', '.footer-tag', '.gold', '.gray',
        '.highlight-big', '.highlight-title',
        '.k', '.keyword', '.layer-desc', '.layer-name',
        '.mini-chip', '.mini-text', '.mini-line',
        '.n', '.page-tag', '.pill-core', '.pill-left', '.pill-right',
        '.range-caption', '.range-label', '.range-years',
        '.right-note', '.signal', '.signal-key', '.signal-text',
        '.small', '.stat-main', '.stat-sub', '.summary-text',
        '.support-line', '.support-num',
        '.time', '.time-label', '.time-text', '.year',
        '.hero-text', '.node-title',
        '.left', '.right',
        '.ai', '.mix', '.fromto',
        'h2', 'h3', 'h4', 'p', 'li',
    }
    centered_text_selectors = {'.num', '.chip', '.step-no', '.footer-pill', '.metric-num', '.tag', '.legend-pill', '.step-num', '.footer-label', '.mini-badge', '.mini-tag', '.pill',
        '.definition-badge', '.dot', '.stage-no',
        '.badge', '.mini-chip', '.page-tag', '.footer-tag',
        '.era', '.k', '.keyword', '.year',
        '.gold', '.blue', '.gray',
        '.pill-core', '.pill-left', '.pill-right',
        '.n', '.small', '.big', '.time',
    }
    vertical_middle_selectors = {
        '.eyebrow', '.header-tag', '.num', '.value-name', '.chip', '.metric-num', '.metric-unit', '.metric-label',
        '.tag', '.legend-pill', '.step-num', '.step-no', '.step-title', '.step-note',
        '.footer-text', '.footer-pill', '.footer-label', '.mini-badge', '.mini-tag', '.pill', '.big-number', '.node-time',
        '.header-badge', '.definition-badge', '.dot', '.stage-no',
        '.mini-label', '.mini-value', '.footer-title',
        '.badge', '.mini-chip', '.page-tag', '.footer-tag',
        '.era', '.k', '.keyword', '.year',
        '.gold', '.blue', '.gray',
        '.pill-core', '.pill-left', '.pill-right',
        '.n', '.small', '.big', '.time',
        '.signal-key', '.support-num',
    }


    scene['elements'].extend(_build_route_scene(route_entries, slide_rect))

    for item in picked:
        selector = item['selector']
        if selector in {'.continent', '.bean', '.pin', '.rule'} and not item['text']:
            continue
        rect = item['rect']
        style = item['style']
        dom_depth = item.get('depth', 0)
        dom_order = item.get('domOrder', 0)
        x = _px_to_in(rect['x'] - slide_rect['x'])
        y = _px_to_in(rect['y'] - slide_rect['y'])
        w = _px_to_in(rect['w'])
        h = _px_to_in(rect['h'])
        fill_color = _pick_fill_color(style, fill_fallback, blend_base=scene['background'])
        border_width = _border_width(style)
        line_color = None
        border_fallback = '#2D3748' if dark_theme else '#DCE3EE'
        if border_width > 0:
            line_color = _pick_fill_color(
                {'backgroundColor': style.get('borderColor')},
                border_fallback,
                blend_base=fill_color or scene['background'],
            )
        if selector in container_selectors or selector in text_background_selectors:
            scene['elements'].append({
                'type': 'shape',
                'shape': 'rounded_rect',
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'fill': fill_color,
                'line': line_color,
                'line_width': max(border_width, 0.75) if line_color else 1.0,
                'source_selector': selector,
                '_dom_depth': dom_depth,
                '_dom_order': dom_order,
            })
        if selector in text_selectors and item['text']:
            align_map = {'left': 'left', 'center': 'center', 'right': 'right'}
            font_size_px = float(style.get('fontSize', '16px').replace('px', '') or 16)
            padding = {'padding_left': 2, 'padding_right': 2, 'padding_top': 1, 'padding_bottom': 1}
            if selector in {'.card-title', '.value-name', '.step-title', '.footer-text', '.step-text', '.route-note', '.visual-title', '.hero-kicker', '.hero-headline', '.summary', '.title', '.node-title', '.support-title', '.highlight-number', '.footer-title', '.big-num', '.big-unit', '.mini-value'}:
                padding.update({'padding_left': 4, 'padding_right': 4, 'padding_top': 2, 'padding_bottom': 2})
            elif selector in {'.hero-body', '.info-text', '.desc', '.label', '.node-desc', '.step-desc', '.card-sub', '.definition-text', '.highlight-text', '.support-desc', '.support-text', '.mini-desc', '.stage-text', '.card-desc', '.side-main', '.point', '.arrow-row'}:
                padding.update({'padding_left': 4, 'padding_right': 4, 'padding_top': 2, 'padding_bottom': 2})
            elif selector in {'.metric-num', '.metric-unit', '.header-tag', '.eyebrow', '.tag', '.legend-pill', '.step-num', '.step-note', '.footer-label', '.mini-badge', '.mini-tag', '.pill', '.node-time', '.header-badge', '.definition-badge', '.dot', '.stage-no', '.highlight-label', '.support-label', '.mini-label', '.process-note'}:
                padding.update({'padding_left': 3, 'padding_right': 3, 'padding_top': 2, 'padding_bottom': 2})
            elif selector == '.footer-pill':
                padding.update({'padding_left': 4, 'padding_right': 4, 'padding_top': 1, 'padding_bottom': 1})
            elif selector == '.metric-num':
                padding.update({'padding_left': 1, 'padding_right': 1, 'padding_top': 1, 'padding_bottom': 1})
            elif selector == '.metric-unit':
                padding.update({'padding_left': 2, 'padding_right': 2, 'padding_top': 1, 'padding_bottom': 1})

            font_scale = 0.75
            if page_role == 'cover':
                if selector == 'h1':
                    font_scale = 0.9
                elif selector in {'.hero-kicker', '.hero-line', '.stage-title', '.center-number'}:
                    font_scale = 0.82
                elif selector in {'.subtitle', '.stage-time', '.center-text', '.summary-intro', '.metric-label', '.metric-note', '.pill'}:
                    font_scale = 0.78
            textbox = {
                'type': 'textbox',
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'text': item['text'].replace(' · ', ' · '),
                'font_size': round(font_size_px * font_scale, 1),
                'color': _pick_text_color(style, fallback=text_fallback, blend_base=text_blend_base),
                'bold': int(style.get('fontWeight', '400')) >= 700,
                'align': 'center' if selector in centered_text_selectors else align_map.get(style.get('textAlign'), 'left'),
                'valign': 'middle' if selector in vertical_middle_selectors else 'top',
                'source_selector': selector,
                '_dom_depth': dom_depth,
                '_dom_order': dom_order,
                **padding,
            }
            raw_line_height = str(style.get('lineHeight') or '').replace('px', '').strip()
            try:
                line_height_px = float(raw_line_height)
            except ValueError:
                line_height_px = 0.0
            if line_height_px > 0:
                textbox['line_spacing'] = round(line_height_px * 0.75, 1)
            scene['elements'].append(textbox)

    # --- z-order 排序 ---
    # 按 DOM 顺序排列，shape 在同一 DOM 节点的 textbox 之前（容器先画，文字后画）
    def _z_sort_key(el):
        dom_order = el.get('_dom_order', 0)
        # shape 排在同一 dom_order 的 textbox 前面（type_rank=0 vs 1）
        type_rank = 0 if el['type'] == 'shape' else 1
        return (dom_order, type_rank)

    scene['elements'].sort(key=_z_sort_key)

    # 清理排序辅助字段
    for el in scene['elements']:
        el.pop('_dom_depth', None)
        el.pop('_dom_order', None)

    if page_role == 'cover':
        _append_cover_visual_scene(scene)

    issue_lines = report.get('final_issues') or []
    return auto_fix_scene(_apply_scene_budget(scene, page_role, hard_truncate=False), page_role), png_bytes, issue_lines


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def build_editable_deck_from_html(html_dir: Path, out_dir: Path,
                                  slide_meta: list[dict] | None = None,
                                  deck_name: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    scene_dir = out_dir / 'scenes'
    preview_dir = out_dir / 'previews'
    scene_dir.mkdir(exist_ok=True)
    preview_dir.mkdir(exist_ok=True)

    html_files = sorted(html_dir.glob('*.html'))
    if not html_files:
        raise ValueError(f'HTML 目录为空: {html_dir}')

    from pptx_builder import build_editable_deck

    meta_by_index = {}
    if slide_meta:
        meta_by_index = {item['index']: item for item in slide_meta if 'index' in item}

    scenes = []
    slide_status = {}
    manifest_slides = []
    for idx, html_path in enumerate(html_files, start=1):
        meta = meta_by_index.get(idx, {})
        page_role = meta.get('page_role', 'summary')
        title = meta.get('title', html_path.stem)
        scene, png_bytes, issue_lines = extract_html_layout_to_scene(html_path, page_role=page_role)
        issues = validate_scene(scene)

        scene_path = scene_dir / slide_filename(idx, title, "json")
        scene_path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding='utf-8')
        preview_svg = preview_dir / slide_filename(idx, title, "svg")
        preview_svg.write_text(scene_to_svg(scene), encoding='utf-8')
        save_svg_screenshot(preview_svg, preview_dir / f'slide-{idx:02d}.png')
        (preview_dir / f'html-source-{idx:02d}.png').write_bytes(png_bytes)

        review = {
            'result': 'PASS' if not issues else 'SKIPPED',
            'reasons': issue_lines[:6] or ['HTML→scene→可编辑 PPT 导出链路完成场景提取'],
            'suggestions': ['对比 html-source 与 editable preview 的一致性'],
            'raw': 'HTML→scene→editable PPT export',
            'review_rounds': 0,
        }
        review_path = out_dir / f'review-{idx:02d}.md'
        review_path.write_text('\n'.join([
            f'# {html_path.name}',
            '',
            f"RESULT: {review['result']}",
            '',
            '## Reasons',
            *([f"- {item}" for item in review['reasons']] or ['- 无']),
            '',
            '## Suggestions',
            *([f"- {item}" for item in review['suggestions']] or ['- 无']),
            '',
            '## Raw',
            '',
            review['raw'],
        ]), encoding='utf-8')

        slide_status[f'{idx:02d}'] = {
            'title': title,
            'page_role': page_role,
            'validation_status': classify_scene_validation(issues, review),
            'final_issues_count': len(issues),
            'review_status': review['result'],
            'review_rounds': 0,
            'review_path': str(review_path),
            'export_ready': len(issues) == 0,
            'html_path': str(html_path),
            'scene_path': str(scene_path),
            'preview_svg_path': str(preview_svg),
            'preview_png_path': str(preview_dir / f'slide-{idx:02d}.png'),
            'html_preview_png_path': str(preview_dir / f'html-source-{idx:02d}.png'),
        }
        manifest_slides.append({
            'index': idx,
            'title': title,
            'page_role': page_role,
            'html_path': str(html_path),
            'scene_path': str(scene_path),
            'review_path': str(review_path),
            'preview_svg_path': str(preview_svg),
            'preview_png_path': str(preview_dir / f'slide-{idx:02d}.png'),
            'html_preview_png_path': str(preview_dir / f'html-source-{idx:02d}.png'),
            'export_ready': len(issues) == 0,
            'validation_status': classify_scene_validation(issues, review),
            'final_issues_count': len(issues),
        })
        scenes.append(scene)

    deck_stem = safe_filename_part(deck_name or html_dir.parent.name, max_length=30)
    ppt_path = out_dir.parent / f'{deck_stem}_editable.pptx'
    build_editable_deck(scenes, ppt_path)
    write_slide_status(out_dir, slide_status)
    (out_dir / 'editable-export-manifest.json').write_text(
        json.dumps({
            'version': 1,
            'generated_at': _utc_now_iso(),
            'pipeline': 'html-first-editable-export',
            'source_of_truth': 'html',
            'html_dir': str(html_dir),
            'pptx_path': str(ppt_path),
            'slide_status_path': str(out_dir / 'slide-status.json'),
            'scene_dir': str(scene_dir),
            'preview_dir': str(preview_dir),
            'slides': manifest_slides,
        }, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return ppt_path


def summary_scene(topic: str, subtitle: str,
                  left_title: str, left_body: str,
                  left_box1_title: str, left_box1_body: str,
                  left_box2_title: str, left_box2_body: str,
                  left_note: str,
                  right_title: str, right_subtitle: str,
                  stages: list[tuple[str, str, str]],
                  footer: str) -> dict:
    elements = [
        {"type": "textbox", "x": 0.6, "y": 0.35, "w": 6.8, "h": 0.45, "text": topic, "font_size": 26, "color": "#1F2937", "bold": True},
        {"type": "textbox", "x": 0.6, "y": 0.78, "w": 8.8, "h": 0.35, "text": subtitle, "font_size": 12, "color": "#667085"},
        {"type": "shape", "shape": "rounded_rect", "x": 0.6, "y": 1.3, "w": 6.2, "h": 4.45, "fill": "#FFFFFF", "line": "#E5E7EB"},
        {"type": "textbox", "x": 0.9, "y": 1.55, "w": 2.2, "h": 0.35, "text": left_title, "font_size": 18, "color": "#1F2937", "bold": True},
        {"type": "textbox", "x": 0.9, "y": 2.0, "w": 5.35, "h": 0.8, "text": left_body, "font_size": 12, "color": "#4B5563"},
        {"type": "shape", "shape": "rounded_rect", "x": 0.9, "y": 3.0, "w": 2.7, "h": 1.35, "fill": "#FBF4E8", "line": "#E7E2D9"},
        {"type": "textbox", "x": 1.1, "y": 3.2, "w": 2.2, "h": 0.28, "text": left_box1_title, "font_size": 11, "color": "#7A4E2B", "bold": True},
        {"type": "textbox", "x": 1.1, "y": 3.48, "w": 2.2, "h": 0.65, "text": left_box1_body, "font_size": 12, "color": "#344054"},
        {"type": "shape", "shape": "rounded_rect", "x": 3.85, "y": 3.0, "w": 2.55, "h": 1.35, "fill": "#EEF7F1", "line": "#DCEBDD"},
        {"type": "textbox", "x": 4.05, "y": 3.2, "w": 2.0, "h": 0.28, "text": left_box2_title, "font_size": 11, "color": "#256F46", "bold": True},
        {"type": "textbox", "x": 4.05, "y": 3.48, "w": 2.0, "h": 0.65, "text": left_box2_body, "font_size": 12, "color": "#344054"},
        {"type": "shape", "shape": "rounded_rect", "x": 0.9, "y": 4.55, "w": 5.5, "h": 0.9, "fill": "#FAFBFC", "line": "#E5E7EB"},
        {"type": "textbox", "x": 1.1, "y": 4.78, "w": 4.95, "h": 0.4, "text": left_note, "font_size": 11, "color": "#475467"},
        {"type": "shape", "shape": "rounded_rect", "x": 7.05, "y": 1.3, "w": 5.65, "h": 4.45, "fill": "#FFFFFF", "line": "#E5E7EB"},
        {"type": "textbox", "x": 7.35, "y": 1.55, "w": 2.4, "h": 0.35, "text": right_title, "font_size": 18, "color": "#1F2937", "bold": True},
        {"type": "textbox", "x": 7.35, "y": 1.93, "w": 4.6, "h": 0.3, "text": right_subtitle, "font_size": 11, "color": "#667085"},
    ]

    top = 2.45
    for idx, (num, stage_title, desc) in enumerate(stages):
        y = top + idx * 1.05
        elements.extend([
            {"type": "shape", "shape": "oval", "x": 7.38, "y": y, "w": 0.42, "h": 0.42, "fill": "#B8822E", "line": None},
            {"type": "textbox", "x": 7.47, "y": y + 0.05, "w": 0.25, "h": 0.2, "text": num, "font_size": 9, "color": "#FFFFFF", "bold": True, "align": "center"},
            {"type": "textbox", "x": 7.95, "y": y + 0.02, "w": 1.75, "h": 0.22, "text": stage_title, "font_size": 13, "color": "#1F2937", "bold": True},
            {"type": "textbox", "x": 7.95, "y": y + 0.28, "w": 3.9, "h": 0.35, "text": desc, "font_size": 11, "color": "#475467"},
        ])
        if idx < len(stages) - 1:
            elements.append({"type": "shape", "shape": "rect", "x": 7.57, "y": y + 0.42, "w": 0.03, "h": 0.58, "fill": "#D0D5DD", "line": None})

    elements.extend([
        {"type": "shape", "shape": "rounded_rect", "x": 0.6, "y": 6.0, "w": 12.1, "h": 0.78, "fill": "#FFF8EC", "line": "#E7D9C0"},
        {"type": "textbox", "x": 0.95, "y": 6.22, "w": 8.2, "h": 0.28, "text": footer, "font_size": 12, "color": "#3D2B1F", "bold": True},
    ])

    return {"background": "#F7F8FA", "elements": elements}



def _extract_first_json_object(text: str) -> str:
    start = text.find('{')
    if start < 0:
        raise ValueError('无法从模型输出中提取 scene JSON')

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    raise ValueError('无法从模型输出中提取完整的 scene JSON')


def _repair_missing_commas(text: str, max_repairs: int = 8) -> str:
    repaired = text
    for _ in range(max_repairs):
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError as exc:
            if "Expecting ',' delimiter" not in exc.msg:
                raise

            prev_idx = exc.pos - 1
            while prev_idx >= 0 and repaired[prev_idx].isspace():
                prev_idx -= 1
            next_idx = exc.pos
            while next_idx < len(repaired) and repaired[next_idx].isspace():
                next_idx += 1

            if prev_idx < 0 or next_idx >= len(repaired):
                raise

            prev_char = repaired[prev_idx]
            next_char = repaired[next_idx]
            prev_window = repaired[max(0, prev_idx - 4):prev_idx + 1]
            next_window4 = repaired[next_idx:next_idx + 4]
            next_window5 = repaired[next_idx:next_idx + 5]
            valid_prev = prev_char in {'"', '}', ']', 'e', 'E'} or prev_char.isdigit() or prev_window.endswith(("true", "false", "null"))
            valid_next = next_char in {'"', '{', '[', '-'} or next_char.isdigit() or next_window4 in {"true", "null"} or next_window5 == "false"
            if not (valid_prev and valid_next):
                raise

            repaired = repaired[:next_idx] + ',' + repaired[next_idx:]

    raise ValueError('scene JSON 缺少逗号，自动修复失败')


def extract_scene_json(text: str) -> dict:
    candidate = _extract_first_json_object(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        try:
            return json.loads(_repair_missing_commas(candidate))
        except Exception:
            raise ValueError(f'scene JSON 解析失败: {exc}') from exc


def normalize_scene(scene: dict) -> dict:
    normalized = {"background": scene.get("background", "#F7F8FA"), "elements": []}
    for element in scene.get("elements", []):
        element_type = element.get("type")
        if element_type not in {"shape", "textbox", "line"}:
            continue
        cleaned = {"type": element_type}
        if element_type == "shape":
            cleaned.update({
                "shape": element.get("shape", "rounded_rect").replace('round_rect', 'rounded_rect'),
                "x": float(element["x"]),
                "y": float(element["y"]),
                "w": float(element["w"]),
                "h": float(element["h"]),
                "fill": element.get("fill"),
                "line": element.get("line"),
                "line_width": float(element.get("line_width", 1)),
                "source_selector": element.get("source_selector", ""),
            })
            if element.get("fill_opacity") is not None:
                cleaned["fill_opacity"] = float(element.get("fill_opacity"))
            if element.get("line_opacity") is not None:
                cleaned["line_opacity"] = float(element.get("line_opacity"))
        elif element_type == "textbox":
            cleaned.update({
                "x": float(element["x"]),
                "y": float(element["y"]),
                "w": float(element["w"]),
                "h": float(element["h"]),
                "text": str(element.get("text", "")),
                "font_size": float(element.get("font_size", 12)),
                "color": element.get("color", "#000000"),
                "bold": bool(element.get("bold", False)),
                "align": element.get("align", "left"),
                "valign": element.get("valign", "top"),
                "padding_left": float(element.get("padding_left", 4)),
                "padding_right": float(element.get("padding_right", 4)),
                "padding_top": float(element.get("padding_top", 2)),
                "padding_bottom": float(element.get("padding_bottom", 2)),
                "source_selector": element.get("source_selector", ""),
            })
            if element.get("line_spacing"):
                cleaned["line_spacing"] = float(element.get("line_spacing"))
        else:
            cleaned.update({
                "x1": float(element["x1"]),
                "y1": float(element["y1"]),
                "x2": float(element["x2"]),
                "y2": float(element["y2"]),
                "color": element.get("color", "#D0D5DD"),
                "width": float(element.get("width", 1.5)),
            })
        normalized["elements"].append(cleaned)
    return normalized


def _textbox_inner_width(element: dict) -> float:
    padding_left = float(element.get('padding_left', 4)) / 72
    padding_right = float(element.get('padding_right', 4)) / 72
    return max(0.6, element['w'] - padding_left - padding_right)


def _textbox_inner_height(element: dict) -> float:
    padding_top = float(element.get('padding_top', 2)) / 72
    padding_bottom = float(element.get('padding_bottom', 2)) / 72
    return max(0.2, element['h'] - padding_top - padding_bottom)


def _wrap_text(text: str, width_in: float, font_size: float) -> list[str]:
    lines = []
    raw_lines = [line.strip() for line in str(text).splitlines()] or [str(text)]
    chars_per_line = max(6, int((width_in * PX_PER_IN) / max(font_size * 0.58, 6)))
    for raw in raw_lines:
        if not raw:
            lines.append('')
            continue
        current = ''
        for ch in raw:
            if len(current) >= chars_per_line:
                lines.append(current)
                current = ch
            else:
                current += ch
        if current:
            lines.append(current)
    return lines or ['']


def _textbox_required_height(element: dict) -> float:
    lines = _wrap_text(element.get('text', ''), _textbox_inner_width(element), element.get('font_size', 12))
    font_size = float(element.get('font_size', 12))
    line_height = float(element.get('line_spacing') or (font_size * 1.38))
    padding_top = float(element.get('padding_top', 2)) / 72
    padding_bottom = float(element.get('padding_bottom', 2)) / 72
    text_height = max(0.2, len(lines) * line_height / 72)

    selector = str(element.get('source_selector', ''))
    safety = 0.04
    if selector in {'.lead', '.support-text', '.step-desc', '.footer-text'}:
        safety = 0.10
    elif selector in {'.step-note', '.subtitle'}:
        safety = 0.08

    return round(text_height + padding_top + padding_bottom + safety, 3)


def _shape_bounds(element: dict) -> tuple[float, float, float, float]:
    return element['x'], element['y'], element['x'] + element['w'], element['y'] + element['h']


def _container_key(element: dict) -> str:
    selector = str(element.get('source_selector', ''))
    x = round(float(element.get('x', 0)), 1)
    y = round(float(element.get('y', 0)), 1)
    if selector in {'.value-name', '.num', '.chip'}:
        return f'value-head:{round(y, 0)}'
    if selector == '.value-text':
        return ''
    if selector in {'.step-title', '.step-no'}:
        return f'step:{round(y, 0)}'
    if selector == '.footer-text':
        return 'footer-text'
    if selector == '.footer-pill':
        return f'footer-pill:{round(x, 1)}'
    if selector in {'.metric-num', '.metric-unit'}:
        return 'metric-head'
    if selector == '.metric-desc':
        return ''
    if selector in {'.card-kicker', '.card-title', '.lead'} and x < 7.8:
        return 'left-head'
    if selector in {'.card-kicker', '.card-title'} and x >= 7.8:
        return 'right-head'
    return ''




def _header_key(element: dict) -> str:
    selector = str(element.get('source_selector', ''))
    if selector in {'.eyebrow', 'h1', '.title', '.subtitle'}:
        return 'header-left'
    return ''


def _relayout_header_textboxes(scene: dict):
    textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']
    header_boxes = sorted(
        [tb for tb in textboxes if _header_key(tb)],
        key=lambda item: (item['y'], item['x']),
    )
    if len(header_boxes) < 2:
        return

    cursor_y = header_boxes[0]['y']
    for idx, box in enumerate(header_boxes):
        required = _textbox_required_height(box)
        box['h'] = round(max(box['h'], required), 3)
        if idx == 0:
            cursor_y = box['y'] + box['h']
            continue
        min_gap = 0.08 if box.get('source_selector') == '.subtitle' else 0.06
        box['y'] = round(max(box['y'], cursor_y + min_gap), 3)
        required = _textbox_required_height(box)
        box['h'] = round(max(box['h'], required), 3)
        cursor_y = box['y'] + box['h']


def _repair_toc_layout(scene: dict) -> dict:
    scene = normalize_scene(scene)
    textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']

    step_num_boxes = [tb for tb in textboxes if tb.get('source_selector') == '.step-num']
    n_boxes = [tb for tb in textboxes if tb.get('source_selector') == '.n']
    era_boxes = [tb for tb in textboxes if tb.get('source_selector') == '.era']

    if step_num_boxes and n_boxes and era_boxes:
        kept_elements = []
        for element in scene.get('elements', []):
            if element.get('type') != 'textbox' or element.get('source_selector') != '.step-num':
                kept_elements.append(element)
                continue
            sx, sy = float(element.get('x', 0)), float(element.get('y', 0))
            has_n = any(abs(float(tb.get('x', 0)) - sx) < 0.5 and abs(float(tb.get('y', 0)) - sy) < 0.7 for tb in n_boxes)
            has_era = any(abs(float(tb.get('x', 0)) - sx) < 0.5 and abs(float(tb.get('y', 0)) - sy) < 0.9 for tb in era_boxes)
            if has_n and has_era:
                continue
            kept_elements.append(element)
        scene['elements'] = kept_elements
        scene = normalize_scene(scene)
        textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']

    step_titles = [tb for tb in textboxes if tb.get('source_selector') == '.step-title']
    tags = [tb for tb in textboxes if tb.get('source_selector') == '.tag']
    for title in step_titles:
        for tag in tags:
            overlap_w = min(title['x'] + title['w'], tag['x'] + tag['w']) - max(title['x'], tag['x'])
            overlap_h = min(title['y'] + title['h'], tag['y'] + tag['h']) - max(title['y'], tag['y'])
            if overlap_w > 0 and overlap_h > 0 and tag['y'] <= title['y']:
                title['y'] = round(max(title['y'], tag['y'] + tag['h'] + 0.05), 3)
                title['h'] = round(max(title['h'], _textbox_required_height(title)), 3)

    return scene


def _repair_ending_layout(scene: dict) -> dict:
    scene = normalize_scene(scene)
    _relayout_header_textboxes(scene)
    # 移除装饰性背景光晕
    scene['elements'] = [
        element for element in scene.get('elements', [])
        if not (element.get('type') == 'shape' and element.get('source_selector') == '_glow')
    ]
    shapes = [element for element in scene.get('elements', []) if element.get('type') == 'shape']
    textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']

    metric_values = [tb for tb in textboxes if tb.get('source_selector') == '.metric-value']
    metric_nums = [tb for tb in textboxes if tb.get('source_selector') == '.metric-num']
    if metric_values and metric_nums:
        scene['elements'] = [element for element in scene.get('elements', []) if element.get('source_selector') != '.metric-value']
        scene = normalize_scene(scene)
        shapes = [element for element in scene.get('elements', []) if element.get('type') == 'shape']
        textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']

    def _by_selector(selector: str) -> list[dict]:
        return [tb for tb in textboxes if tb.get('source_selector') == selector]

    def _by_shape_selector(selector: str) -> list[dict]:
        return [shape for shape in shapes if shape.get('source_selector') == selector]

    def _first_box(*selectors: str):
        for selector in selectors:
            box = next((tb for tb in textboxes if tb.get('source_selector') == selector), None)
            if box:
                return box
        return None

    left_card = next((shape for shape in shapes if shape.get('source_selector') == '.card' and shape.get('x', 0) < 1.0 and shape.get('w', 0) > 6.5), None)
    right_card = next((shape for shape in shapes if shape.get('source_selector') == '.card' and shape.get('x', 0) > 7.0 and shape.get('w', 0) > 5.0), None)
    footer_card = next((shape for shape in shapes if shape.get('source_selector') == '.footer-card'), None)
    support_cards = sorted(_by_shape_selector('.support-item'), key=lambda item: item['y'])
    step_cards = sorted(_by_shape_selector('.step'), key=lambda item: item['y'])
    step_no_shapes = sorted(_by_shape_selector('.step-no'), key=lambda item: item['y'])
    tag_shapes = sorted(_by_shape_selector('.tag'), key=lambda item: item['x'])

    lead = _first_box('.lead')
    summary_title = next((tb for tb in textboxes if tb.get('source_selector') == '.card-title' and tb.get('x', 0) < 2.0), None)
    right_title = next((tb for tb in textboxes if tb.get('source_selector') == '.card-title' and tb.get('x', 0) > 7.0), None)
    signal = _first_box('.signal')
    footer_text = _first_box('.footer-text')
    footer_tags = sorted(_by_selector('.footer-tag'), key=lambda item: item['x'])
    tags = sorted(_by_selector('.tag'), key=lambda item: item['x'])
    support_nums = sorted(_by_selector('.support-num'), key=lambda item: item['y'])
    support_texts = sorted(_by_selector('.support-text'), key=lambda item: item['y'])
    step_nos = sorted(_by_selector('.step-no'), key=lambda item: item['y'])
    step_titles = sorted(_by_selector('.step-title'), key=lambda item: item['y'])
    step_descs = sorted(_by_selector('.step-desc'), key=lambda item: item['y'])
    step_notes = sorted(_by_selector('.step-note'), key=lambda item: item['y'])

    if left_card:
        left_inner_x = round(left_card['x'] + 0.22, 3)
        left_inner_w = round(left_card['w'] - 0.44, 3)
        if summary_title:
            summary_title['x'] = left_inner_x
            summary_title['y'] = round(left_card['y'] + 0.22, 3)
            summary_title['w'] = left_inner_w
            summary_title['h'] = 0.34
            summary_title['font_size'] = 13.0
            summary_title['padding_left'] = 2
            summary_title['padding_right'] = 2
            summary_title['padding_top'] = 1
            summary_title['padding_bottom'] = 1

        if lead:
            lead['x'] = left_inner_x
            lead['y'] = round((summary_title['y'] + summary_title['h'] + 0.18) if summary_title else left_card['y'] + 0.56, 3)
            lead['w'] = round(left_inner_w - 0.18, 3)
            lead['font_size'] = 15.0
            lead['line_spacing'] = 19.0
            lead['padding_left'] = 3
            lead['padding_right'] = 3
            lead['padding_top'] = 2
            lead['padding_bottom'] = 2
            lead['h'] = round(max(0.56, _textbox_required_height(lead)), 3)

        # 确保 support_cards 起始 y 不与 lead 重叠
        first_support_y = round((lead['y'] + lead['h'] + 0.14) if lead else (summary_title['y'] + summary_title['h'] + 0.50) if summary_title else left_card['y'] + 1.20, 3)
        for idx, card in enumerate(support_cards):
            num_box = support_nums[idx] if idx < len(support_nums) else None
            text_box = support_texts[idx] if idx < len(support_texts) else None
            card['x'] = left_inner_x
            card['w'] = left_inner_w
            if idx == 0:
                card['y'] = max(card['y'], first_support_y)
            card['h'] = max(card['h'], 0.98)
            if num_box:
                num_box['x'] = round(card['x'] + 0.14, 3)
                num_box['y'] = round(card['y'] + 0.16, 3)
                num_box['w'] = 0.62
                num_box['h'] = 0.44
                num_box['font_size'] = 9.0
                num_box['padding_left'] = 1
                num_box['padding_right'] = 1
                num_box['padding_top'] = 1
                num_box['padding_bottom'] = 1
            if text_box:
                text_box['x'] = round(card['x'] + 0.82, 3)
                text_box['y'] = round(card['y'] + 0.12, 3)
                text_box['w'] = round(card['w'] - 0.98, 3)
                text_box['font_size'] = 10.8
                text_box['line_spacing'] = 14.8
                text_box['padding_left'] = 2
                text_box['padding_right'] = 2
                text_box['padding_top'] = 1
                text_box['padding_bottom'] = 1
                text_box['h'] = round(max(0.78, _textbox_required_height(text_box)), 3)
                card['h'] = round(max(card['h'], text_box['h'] + 0.24), 3)

        if tags and support_cards:
            last_card = support_cards[-1]
            tag_y = round(min(left_card['y'] + left_card['h'] - 0.60, last_card['y'] + last_card['h'] + 0.16), 3)
            cursor_x = left_inner_x
            for idx, tag in enumerate(tags):
                tag['x'] = cursor_x
                tag['y'] = tag_y
                tag['h'] = max(tag['h'], 0.31)
                if idx < len(tag_shapes):
                    tag_shape = tag_shapes[idx]
                    tag_shape['x'] = round(tag['x'] - 0.01, 3)
                    tag_shape['y'] = round(tag['y'] - 0.02, 3)
                    tag_shape['w'] = max(tag_shape['w'], tag['w'] + 0.02)
                    tag_shape['h'] = max(tag_shape['h'], tag['h'] + 0.04)
                cursor_x = round(cursor_x + tag['w'] + 0.08, 3)

    if right_card:
        right_card['x'] = 7.36
        right_card['w'] = 5.72
        right_card['h'] = max(right_card['h'], 4.98)
        right_inner_x = round(right_card['x'] + 0.22, 3)
        right_inner_w = round(right_card['w'] - 0.44, 3)
        if right_title:
            right_title['x'] = right_inner_x
            right_title['y'] = round(right_card['y'] + 0.22, 3)
            right_title['w'] = 1.30
            right_title['h'] = 0.34
            right_title['font_size'] = 12.5
            right_title['padding_left'] = 2
            right_title['padding_right'] = 2
            right_title['padding_top'] = 1
            right_title['padding_bottom'] = 1
        if signal:
            signal['x'] = round(right_card['x'] + right_card['w'] - signal['w'] - 0.22, 3)
            signal['y'] = round(right_card['y'] + 0.20, 3)
            signal['h'] = max(signal['h'], 0.35)
            signal['padding_left'] = 3
            signal['padding_right'] = 3
            signal['padding_top'] = 1
            signal['padding_bottom'] = 1

        # 以显式游标重排 step 区，避免 step 内部和 step 之间互相挤压
        step_cursor_y = round(right_card['y'] + 0.84, 3)
        for idx, card in enumerate(step_cards):
            no_box = step_nos[idx] if idx < len(step_nos) else None
            title_box = step_titles[idx] if idx < len(step_titles) else None
            desc_box = step_descs[idx] if idx < len(step_descs) else None
            note_box = step_notes[idx] if idx < len(step_notes) else None
            no_shape = step_no_shapes[idx] if idx < len(step_no_shapes) else None

            card['x'] = right_inner_x
            card['y'] = step_cursor_y
            card['w'] = right_inner_w

            num_x = round(card['x'] + 0.16, 3)
            num_y = round(card['y'] + 0.15, 3)
            num_w = 0.56
            body_x = round(card['x'] + 0.85, 3)
            body_w = round(card['w'] - 1.02, 3)

            if no_shape:
                no_shape['x'] = num_x
                no_shape['y'] = num_y
                no_shape['w'] = num_w
                no_shape['h'] = 0.56
            if no_box:
                no_box['x'] = num_x
                no_box['y'] = num_y
                no_box['w'] = num_w
                no_box['h'] = 0.56
                no_box['align'] = 'center'
                no_box['valign'] = 'middle'
                no_box['padding_left'] = 1
                no_box['padding_right'] = 1
                no_box['padding_top'] = 1
                no_box['padding_bottom'] = 1

            title_h = 0.30
            if title_box:
                title_h = round(max(0.30, _textbox_required_height(title_box)), 3)
                title_box['x'] = body_x
                title_box['y'] = round(card['y'] + 0.13, 3)
                title_box['w'] = body_w
                title_box['h'] = title_h
                title_box['font_size'] = 13.5
                title_box['padding_left'] = 2
                title_box['padding_right'] = 2
                title_box['padding_top'] = 1
                title_box['padding_bottom'] = 1

            desc_h = 0.36
            if desc_box:
                desc_h = round(max(0.36, _textbox_required_height(desc_box)), 3)
                desc_box['x'] = body_x
                desc_box['y'] = round((title_box['y'] + title_box['h'] + 0.05) if title_box else card['y'] + 0.36, 3)
                desc_box['w'] = body_w
                desc_box['h'] = desc_h
                desc_box['font_size'] = 10.6
                desc_box['line_spacing'] = 14.8
                desc_box['padding_left'] = 2
                desc_box['padding_right'] = 2
                desc_box['padding_top'] = 1
                desc_box['padding_bottom'] = 1

            note_h = 0.28
            if note_box:
                note_h = round(max(0.28, _textbox_required_height(note_box)), 3)
                note_box['x'] = body_x
                note_box['y'] = round((desc_box['y'] + desc_box['h'] + 0.04) if desc_box else card['y'] + 0.74, 3)
                note_box['w'] = body_w
                note_box['h'] = note_h
                note_box['font_size'] = 9.8
                note_box['line_spacing'] = 12.2
                note_box['padding_left'] = 2
                note_box['padding_right'] = 2
                note_box['padding_top'] = 1
                note_box['padding_bottom'] = 1

            card_bottom = card['y'] + 0.14
            if note_box:
                card_bottom = note_box['y'] + note_box['h'] + 0.14
            elif desc_box:
                card_bottom = desc_box['y'] + desc_box['h'] + 0.14
            elif title_box:
                card_bottom = title_box['y'] + title_box['h'] + 0.14
            card['h'] = round(max(0.98, card_bottom - card['y']), 3)
            step_cursor_y = round(card['y'] + card['h'] + 0.08, 3)

        if step_cards:
            # 若 step 区域侵入 footer，优先整体上移 step（不下推 footer）
            if footer_card:
                available_bottom = round(footer_card['y'] - 0.10, 3)
                last_bottom = round(step_cards[-1]['y'] + step_cards[-1]['h'], 3)
                if last_bottom > available_bottom:
                    delta = round(last_bottom - available_bottom, 3)
                    min_top = round(right_card['y'] + 0.72, 3)
                    current_top = round(step_cards[0]['y'], 3)
                    if current_top - delta < min_top:
                        delta = round(max(0.0, current_top - min_top), 3)
                    if delta > 0:
                        for seq in (step_cards, step_nos, step_no_shapes, step_titles, step_descs, step_notes):
                            for item in seq:
                                item['y'] = round(item['y'] - delta, 3)

            last_step = step_cards[-1]
            needed_bottom = last_step['y'] + last_step['h'] + 0.14
            right_card['h'] = round(max(4.98, needed_bottom - right_card['y']), 3)

    if footer_card and footer_text:
        # 当 footer 被下移时，同步下移 footer-tag，避免与 step-note 重叠
        if footer_tags:
            tag_base_y = round(footer_card['y'] + 0.26, 3)
            for tag in footer_tags:
                tag['y'] = tag_base_y
                tag['h'] = max(tag.get('h', 0.0), 0.31)
                matching_shape = next((shape for shape in shapes if shape.get('source_selector') == '.footer-tag' and abs(shape.get('x', 0.0) - tag.get('x', 0.0)) < 0.25), None)
                if matching_shape:
                    matching_shape['y'] = round(tag['y'] - 0.02, 3)
                    matching_shape['h'] = max(matching_shape.get('h', 0.0), tag['h'] + 0.04)

        footer_text['x'] = round(footer_card['x'] + 0.18, 3)
        footer_text['y'] = round(footer_card['y'] + 0.38, 3)
        footer_text['font_size'] = 15.0
        footer_text['line_spacing'] = 18.0
        footer_text['padding_left'] = 2
        footer_text['padding_right'] = 2
        footer_text['padding_top'] = 1
        footer_text['padding_bottom'] = 1
        if footer_tags:
            first_tag_x = min(tag['x'] for tag in footer_tags)
            footer_text['w'] = round(first_tag_x - footer_text['x'] - 0.18, 3)
        else:
            footer_text['w'] = round(footer_card['w'] - 0.36, 3)
        footer_text['h'] = round(max(0.38, _textbox_required_height(footer_text)), 3)

        if footer_tags:
            top_y = footer_card['y'] + 0.20
            if footer_text['y'] + footer_text['h'] > top_y:
                footer_text['h'] = round(max(0.24, top_y - footer_text['y'] - 0.04), 3)

    return scene


def _repair_cover_map_layout(scene: dict) -> dict:
    scene = normalize_scene(scene)
    textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']
    shapes = [element for element in scene.get('elements', []) if element.get('type') == 'shape']

    cycle_shape = next((shape for shape in shapes if 5.0 <= shape.get('x', 0) <= 6.0 and 2.2 <= shape.get('y', 0) <= 2.7 and 6.5 <= shape.get('w', 0) <= 7.6 and 2.6 <= shape.get('h', 0) <= 3.6), None)
    hero_card = next((shape for shape in shapes if shape.get('w', 0) >= 11.5 and 1.2 <= shape.get('y', 0) <= 1.7 and 4.2 <= shape.get('h', 0) <= 5.2), None)
    footer_card = next((shape for shape in shapes if shape.get('w', 0) >= 11.5 and shape.get('y', 0) >= 6.0 and shape.get('h', 0) <= 1.2), None)

    if hero_card:
        hero_card['fill'] = '#18181B'
        hero_card['line'] = '#2A2B30'
        hero_card['line_width'] = 1.0
        hero_card['x'] = 0.354
        hero_card['y'] = 1.417
        hero_card['w'] = 12.625
        hero_card['h'] = 4.729

    if cycle_shape:
        cycle_shape['x'] = 5.95
        cycle_shape['y'] = 1.92
        cycle_shape['w'] = 6.25
        cycle_shape['h'] = 3.55
        cycle_shape['fill'] = '#18181B'
        cycle_shape['line'] = None

    if footer_card:
        footer_card['fill'] = '#18181B'
        footer_card['line'] = '#2A2B30'
        footer_card['line_width'] = 1.0
        footer_card['x'] = 0.354
        footer_card['y'] = 6.02
        footer_card['w'] = 12.625
        footer_card['h'] = 1.16

    def _by_selector(selector: str) -> list[dict]:
        return [tb for tb in textboxes if tb.get('source_selector') == selector]

    eyebrow = next((tb for tb in textboxes if tb.get('source_selector') == '.eyebrow'), None)
    title = next((tb for tb in textboxes if tb.get('source_selector') == 'h1'), None)
    subtitle = next((tb for tb in textboxes if tb.get('source_selector') == '.subtitle'), None)
    kicker = next((tb for tb in textboxes if tb.get('source_selector') == '.hero-kicker'), None)
    hero_body = next((tb for tb in textboxes if tb.get('source_selector') in {'.hero-line', '.hero-body', '.lead'}), None)
    stage_titles = sorted(_by_selector('.stage-title'), key=lambda item: item['x'])
    stage_times = sorted(_by_selector('.stage-time'), key=lambda item: item['x'])
    center_number = next((tb for tb in textboxes if tb.get('source_selector') == '.center-number'), None)
    center_text = next((tb for tb in textboxes if tb.get('source_selector') == '.center-text'), None)
    summary_intro = next((tb for tb in textboxes if tb.get('source_selector') == '.summary-intro'), None)
    pills = sorted(_by_selector('.pill'), key=lambda item: item['x'])
    metric_labels = sorted(_by_selector('.metric-label'), key=lambda item: item['x'])
    metric_values = sorted([tb for tb in textboxes if tb.get('source_selector') in {'.metric-value', '.metric-num'}], key=lambda item: item['x'])
    metric_notes = sorted([tb for tb in textboxes if tb.get('source_selector') in {'.metric-note', '.metric-desc'}], key=lambda item: item['x'])

    if eyebrow:
        eyebrow['x'] = 0.42
        eyebrow['y'] = 0.34
        eyebrow['w'] = 3.0
        eyebrow['h'] = 0.28
        eyebrow['font_size'] = 12.0
        eyebrow['color'] = '#86EFAC'
        eyebrow['padding_left'] = 2
        eyebrow['padding_right'] = 2
        eyebrow['padding_top'] = 1
        eyebrow['padding_bottom'] = 1

    if title:
        title['x'] = 0.38
        title['y'] = 0.66
        title['w'] = 4.1
        title['h'] = 0.48
        title['font_size'] = 24.0
        title['line_spacing'] = 26.0
        title['padding_left'] = 2
        title['padding_right'] = 2
        title['padding_top'] = 1
        title['padding_bottom'] = 1

    if subtitle:
        subtitle['x'] = 0.38
        subtitle['y'] = 1.18
        subtitle['w'] = 6.0
        subtitle['h'] = 0.28
        subtitle['font_size'] = 10.5
        subtitle['color'] = '#A1A1AA'
        subtitle['padding_left'] = 2
        subtitle['padding_right'] = 2
        subtitle['padding_top'] = 1
        subtitle['padding_bottom'] = 1

    if kicker:
        kicker['x'] = 0.66
        kicker['y'] = 1.88
        kicker['w'] = 2.0
        kicker['h'] = 0.28
        kicker['font_size'] = 12.0
        kicker['color'] = '#FDBA74'
        kicker['padding_left'] = 2
        kicker['padding_right'] = 2
        kicker['padding_top'] = 1
        kicker['padding_bottom'] = 1

    if hero_body:
        hero_body['x'] = 0.66
        hero_body['y'] = 2.2
        hero_body['w'] = 4.55
        hero_body['h'] = 0.95
        hero_body['font_size'] = 15.0
        hero_body['line_spacing'] = 18.0
        hero_body['color'] = '#F3F4F6'
        hero_body['padding_left'] = 3
        hero_body['padding_right'] = 3
        hero_body['padding_top'] = 2
        hero_body['padding_bottom'] = 2

    stage_x = [5.95, 7.42, 8.95, 10.5]
    stage_y = [2.72, 2.24, 2.24, 2.72]
    stage_title_width = 1.25
    stage_time_width = 1.45
    for idx, title_box in enumerate(stage_titles[:4]):
        title_box['x'] = stage_x[idx]
        title_box['y'] = stage_y[idx] + 0.7
        title_box['w'] = stage_title_width
        title_box['h'] = 0.34
        title_box['font_size'] = 13.5
        title_box['align'] = 'center'
        title_box['valign'] = 'middle'
        title_box['padding_left'] = 2
        title_box['padding_right'] = 2
        title_box['padding_top'] = 1
        title_box['padding_bottom'] = 1
        title_box['color'] = '#FFFFFF'

    for idx, time_box in enumerate(stage_times[:4]):
        time_box['x'] = stage_x[idx] - 0.08
        time_box['y'] = stage_y[idx] + 1.05
        time_box['w'] = stage_time_width
        time_box['h'] = 0.5
        time_box['font_size'] = 10.5
        time_box['line_spacing'] = 12.5
        time_box['align'] = 'center'
        time_box['valign'] = 'top'
        time_box['padding_left'] = 2
        time_box['padding_right'] = 2
        time_box['padding_top'] = 1
        time_box['padding_bottom'] = 1
        time_box['color'] = '#D1D5DB'

    if center_number:
        center_number['x'] = 7.62
        center_number['y'] = 4.14
        center_number['w'] = 2.3
        center_number['h'] = 0.52
        center_number['font_size'] = 24.0
        center_number['align'] = 'center'
        center_number['valign'] = 'middle'
        center_number['color'] = '#FB7185'
        center_number['padding_left'] = 2
        center_number['padding_right'] = 2
        center_number['padding_top'] = 1
        center_number['padding_bottom'] = 1

    if center_text:
        center_text['x'] = 7.35
        center_text['y'] = 4.70
        center_text['w'] = 2.8
        center_text['h'] = 0.28
        center_text['font_size'] = 10.5
        center_text['align'] = 'center'
        center_text['valign'] = 'middle'
        center_text['color'] = '#F3F4F6'
        center_text['padding_left'] = 2
        center_text['padding_right'] = 2
        center_text['padding_top'] = 1
        center_text['padding_bottom'] = 1

    if summary_intro:
        summary_intro['x'] = 0.62
        summary_intro['y'] = 6.12
        summary_intro['w'] = 1.75
        summary_intro['h'] = 0.28
        summary_intro['font_size'] = 11.0
        summary_intro['color'] = '#D4D4D8'
        summary_intro['padding_left'] = 2
        summary_intro['padding_right'] = 2
        summary_intro['padding_top'] = 1
        summary_intro['padding_bottom'] = 1

    if pills:
        pill = pills[0]
        pill['x'] = 1.78
        pill['y'] = 6.44
        pill['w'] = 1.0
        pill['h'] = 0.3
        pill['font_size'] = 10.5
        pill['align'] = 'center'
        pill['valign'] = 'middle'
        pill['fill_hint'] = '#86EFAC'
        pill['padding_left'] = 3
        pill['padding_right'] = 3
        pill['padding_top'] = 1
        pill['padding_bottom'] = 1
        matching_shape = next((shape for shape in shapes if abs(shape['x'] - pill['x']) < 0.35 and abs(shape['y'] - pill['y']) < 0.35 and shape['w'] <= 1.4), None)
        if matching_shape:
            matching_shape['x'] = 1.78
            matching_shape['y'] = 6.42
            matching_shape['w'] = 1.0
            matching_shape['h'] = 0.34
            matching_shape['fill'] = '#86EFAC'
            matching_shape['line'] = None

    metric_x = [2.78, 6.02, 9.28]
    value_colors = ['#FB7185', '#86EFAC', '#FDBA74']
    for idx, label in enumerate(metric_labels[:3]):
        label['x'] = metric_x[idx]
        label['y'] = 6.18
        label['w'] = 2.35
        label['h'] = 0.28
        label['font_size'] = 9.5
        label['color'] = '#A1A1AA'
        label['padding_left'] = 2
        label['padding_right'] = 2
        label['padding_top'] = 1
        label['padding_bottom'] = 1

    for idx, value in enumerate(metric_values[:3]):
        value['x'] = metric_x[idx]
        value['y'] = 6.47
        value['w'] = 2.35
        value['h'] = 0.36
        value['font_size'] = 17.0
        value['color'] = value_colors[idx]
        value['bold'] = True
        value['padding_left'] = 1
        value['padding_right'] = 1
        value['padding_top'] = 1
        value['padding_bottom'] = 1

    for idx, note in enumerate(metric_notes[:3]):
        note['x'] = metric_x[idx]
        note['y'] = 6.85
        note['w'] = 2.55
        note['h'] = 0.28
        note['font_size'] = 9.5
        note['line_spacing'] = 10.5
        note['color'] = '#D4D4D8'
        note['padding_left'] = 2
        note['padding_right'] = 2
        note['padding_top'] = 1
        note['padding_bottom'] = 1

    for textbox in textboxes:
        selector = textbox.get('source_selector', '')
        if selector in {'.hero-kicker', '.hero-line', '.summary-intro', '.stage-title', '.stage-time', '.center-number', '.center-text', '.metric-label', '.metric-value', '.metric-note', '.pill'}:
            continue
        if selector == 'h1':
            continue
        if selector == '.subtitle':
            continue
        if selector == '.eyebrow':
            continue
        if textbox.get('y', 0) > 5.8:
            textbox['font_size'] = max(9.5, float(textbox.get('font_size', 10.5)))

    # cover 下半区：keyword 与 desc 强制留白，避免微重叠
    keywords = sorted([tb for tb in textboxes if tb.get('source_selector') == '.keyword'], key=lambda item: (item['x'], item['y']))
    descs = sorted([tb for tb in textboxes if tb.get('source_selector') == '.desc'], key=lambda item: (item['x'], item['y']))
    for keyword in keywords:
        candidates = [
            d for d in descs
            if abs(float(d.get('x', 0)) - float(keyword.get('x', 0))) < 0.25 and float(d.get('y', 0)) >= float(keyword.get('y', 0)) - 0.2
        ]
        if not candidates:
            continue
        partner = min(candidates, key=lambda d: abs(float(d.get('y', 0)) - float(keyword.get('y', 0))))
        min_desc_y = round(keyword['y'] + keyword['h'] + 0.04, 3)
        if partner['y'] < min_desc_y:
            partner['y'] = min_desc_y
        partner['h'] = round(max(partner['h'], _textbox_required_height(partner)), 3)

    return scene





def _find_enclosing_shape(textbox: dict, shapes: list[dict], min_width: float = 0.0) -> dict | None:
    tx1, ty1, tx2, ty2 = _shape_bounds(textbox)
    candidates = []
    for shape in shapes:
        if shape.get('type') != 'shape':
            continue
        if shape.get('w', 0) < min_width:
            continue
        sx1, sy1, sx2, sy2 = _shape_bounds(shape)
        if tx1 >= sx1 and tx2 <= sx2 + 0.2 and ty1 >= sy1 and ty2 <= sy2 + 0.3:
            area = shape['w'] * shape['h']
            candidates.append((area, shape))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _min_font_size(element: dict) -> float:
    text = str(element.get('text', '')).strip()
    role = str(element.get('source_selector', ''))
    if role == '.metric-num':
        return max(17.0, float(element.get('font_size', 17.0)))
    if role in {'.value-name', '.step-title', '.footer-text'}:
        return max(13.0, float(element.get('font_size', 13.0)))
    if len(text) <= 3:
        return 9.0
    if len(text) <= 8:
        return 10.5
    return 11.0


def _textbox_overflows(element: dict) -> bool:
    required = _textbox_required_height(element)
    if required > element['h'] + 0.03:
        return True
    lines = _wrap_text(element.get('text', ''), _textbox_inner_width(element), element.get('font_size', 12))
    inner_height = _textbox_inner_height(element)
    line_height = float(element.get('line_spacing') or (element.get('font_size', 12) * 1.3)) / 72
    return len(lines) * line_height > inner_height + 0.02


def _scene_budget_rules(page_role: str) -> dict:
    if page_role == 'timeline':
        return {'max_elements': 30, 'max_body_chars': 34, 'max_footer_chars': 48}
    if page_role == 'summary':
        return {'max_elements': 28, 'max_body_chars': 34, 'max_footer_chars': 50}
    if page_role == 'ending':
        return {'max_elements': 26, 'max_body_chars': 34, 'max_footer_chars': 44}
    return {'max_elements': 30, 'max_body_chars': 40, 'max_footer_chars': 52}


def _collect_scene_budget_issues(scene: dict, page_role: str) -> list[str]:
    rules = _scene_budget_rules(page_role)
    issues = []
    budget_elements = [
        element for element in scene.get('elements', [])
        if element.get('source_selector') != '_bg_glow'
    ]
    if len(budget_elements) > rules['max_elements']:
        issues.append(f"元素过多：当前 {len(budget_elements)}，建议不超过 {rules['max_elements']}")
    for idx, element in enumerate(budget_elements):
        if element.get('type') != 'textbox':
            continue
        text = str(element.get('text', '')).strip()
        if not text:
            continue
        limit = rules['max_footer_chars'] if element.get('y', 0) >= 6.0 else rules['max_body_chars']
        compact_len = len(text.replace('\n', ' ').strip())
        if compact_len > limit:
            kind = 'footer' if element.get('y', 0) >= 6.0 else '正文'
            issues.append(f"textbox#{idx} {kind}过长：{compact_len}>{limit}，请改写为更短句并避免省略号截断。文本={text[:40]}")
    return issues


def _compress_text_for_budget(text: str, limit: int) -> str:
    compact = ' '.join(str(text).split()).strip()
    if len(compact) <= limit:
        return compact

    sentences = [part.strip() for part in re.split(r'(?<=[。！？；!?;])\s*', compact) if part.strip()]
    if sentences:
        picked = []
        total = 0
        for sentence in sentences:
            if total + len(sentence) > limit:
                break
            picked.append(sentence)
            total += len(sentence)
        if picked:
            return ' '.join(picked)
        first = sentences[0]
    else:
        first = compact

    clauses = [part.strip(' ，、；,; ') for part in re.split(r'[，、,;；]+', first) if part.strip(' ，、；,; ')]
    if clauses:
        picked = []
        total = 0
        for clause in clauses:
            addition = clause if not picked else f'，{clause}'
            if total + len(addition) > limit - 1:
                break
            picked.append(clause)
            total += len(addition)
        if picked:
            shortened = '，'.join(picked).rstrip('，、；,; ')
            return shortened + ('。' if not shortened.endswith(('。', '！', '？', '.', '!', '?')) else '')

    shortened = compact[:max(1, limit)].rstrip('，、；。,.!?！？ ')
    return shortened + ('。' if not shortened.endswith(('。', '！', '？', '.', '!', '?')) else '')


def _apply_scene_budget(scene: dict, page_role: str, hard_truncate: bool = True) -> dict:
    scene = normalize_scene(scene)
    rules = _scene_budget_rules(page_role)
    preserved = [element for element in scene.get('elements', []) if element.get('source_selector') == '_bg_glow']
    trimmed = []
    for element in scene.get('elements', []):
        if element.get('source_selector') == '_bg_glow':
            continue
        if element.get('type') != 'textbox':
            trimmed.append(element)
            continue
        text = str(element.get('text', '')).strip()
        if not text:
            trimmed.append(element)
            continue
        limit = rules['max_footer_chars'] if element.get('y', 0) >= 6.0 else rules['max_body_chars']
        if hard_truncate and len(text.replace('\n', ' ').strip()) > limit:
            element = {**element, 'text': _compress_text_for_budget(text, limit)}
        trimmed.append(element)
    scene['elements'] = preserved + (trimmed[:rules['max_elements']] if hard_truncate else trimmed)
    return scene


def _build_budget_refinement_feedback(scene: dict, page_role: str) -> str:
    budget_issues = _collect_scene_budget_issues(scene, page_role)
    return build_budget_refinement_feedback(page_role, budget_issues)


def _summarize_scene_issues(scene: dict) -> list[str]:
    issues = []
    for idx, element in enumerate(scene.get('elements', [])):
        if element.get('type') == 'textbox' and _textbox_overflows(element):
            issues.append(f"textbox#{idx} 文本框溢出：{str(element.get('text', ''))[:28]}")
    return issues


def _validate_scene_for_regeneration(scene: dict) -> tuple[bool, list[str]]:
    issues = validate_scene(scene)
    issues.extend(_summarize_scene_issues(scene))
    return bool(issues), issues


def _apply_scene_safe_patch(scene: dict, page_role: str = 'summary') -> dict:
    scene = normalize_scene(scene)
    if page_role == 'cover':
        return _repair_cover_map_layout(scene)
    if page_role == 'toc':
        scene = _repair_toc_layout(scene)
        _relayout_header_textboxes(scene)
        return scene
    if page_role == 'ending':
        return _repair_ending_layout(scene)
    if page_role != 'summary':
        _relayout_header_textboxes(scene)
        return scene
    scene = _semantic_reflow_scene(scene)
    _relayout_header_textboxes(scene)
    return scene


def _semantic_reflow_scene(scene: dict) -> dict:
    shapes = [element for element in scene.get('elements', []) if element.get('type') == 'shape']
    textboxes = [element for element in scene.get('elements', []) if element.get('type') == 'textbox']
    footer_pills = [tb for tb in textboxes if tb.get('source_selector') == '.footer-pill']
    footer_pills.sort(key=lambda tb: tb['x'])
    first_footer_pill_x = footer_pills[0]['x'] if footer_pills else None

    for textbox in textboxes:
        selector = textbox.get('source_selector')
        if selector == '.step-title':
            card = _find_enclosing_shape(textbox, shapes, min_width=4.0)
            if card:
                textbox['w'] = round(max(textbox['w'], card['x'] + card['w'] - textbox['x'] - 0.22), 3)
        elif selector == '.value-name':
            card = _find_enclosing_shape(textbox, shapes, min_width=6.5)
            if card:
                textbox['w'] = round(max(textbox['w'], card['x'] + card['w'] - textbox['x'] - 0.9), 3)
        elif selector == '.footer-text' and first_footer_pill_x is not None:
            textbox['w'] = round(max(textbox['w'], first_footer_pill_x - textbox['x'] - 0.32), 3)
        elif selector == '.metric-desc':
            card = _find_enclosing_shape(textbox, shapes, min_width=4.0)
            if card:
                textbox['y'] = round(textbox['y'] + 0.04, 3)
                textbox['w'] = round(max(textbox['w'], card['x'] + card['w'] - textbox['x'] - 0.36), 3)
        elif selector == '.chip':
            card = _find_enclosing_shape(textbox, shapes, min_width=6.5)
            if card:
                textbox['x'] = round(max(textbox['x'], card['x'] + card['w'] - textbox['w'] - 0.22), 3)
                textbox['y'] = round(max(textbox['y'], card['y'] + 0.16), 3)
                textbox['padding_left'] = 3
                textbox['padding_right'] = 3
                textbox['h'] = round(max(textbox['h'], 0.28), 3)
                chip_shape = next((shape for shape in shapes if abs(shape['x'] - textbox['x']) < 0.25 and abs(shape['y'] - textbox['y']) < 0.25 and shape['w'] <= 1.2), None)
                if chip_shape:
                    chip_shape['x'] = textbox['x']
                    chip_shape['y'] = textbox['y'] - 0.01
                    chip_shape['w'] = max(chip_shape['w'], textbox['w'])
                    chip_shape['h'] = max(chip_shape['h'], textbox['h'] + 0.03)
                    chip_shape['fill'] = chip_shape.get('fill') or '#E3DDD8'
                    chip_shape['line'] = None
                    chip_shape['shape'] = 'rounded_rect'
                    chip_shape['line_width'] = 1.0
        elif selector == '.metric-unit':
            metric_num = next((tb for tb in textboxes if tb.get('source_selector') == '.metric-num'), None)
            if metric_num:
                textbox['x'] = round(metric_num['x'] + metric_num['w'] + 0.12, 3)
                textbox['y'] = round(metric_num['y'] + 0.075, 3)
                textbox['w'] = round(max(textbox['w'], 1.05), 3)
                textbox['padding_left'] = 1
                textbox['padding_right'] = 1
                textbox['padding_top'] = 1
                textbox['padding_bottom'] = 1
                textbox['h'] = round(max(textbox['h'], 0.30), 3)
        elif selector == '.metric-num':
            textbox['w'] = round(max(textbox['w'], 0.24), 3)
            textbox['h'] = round(max(textbox['h'], 0.40), 3)
        elif selector == '.footer-pill':
            textbox['padding_left'] = 4
            textbox['padding_right'] = 4
            textbox['padding_top'] = 1
            textbox['padding_bottom'] = 1
            textbox['h'] = round(max(textbox['h'], 0.36), 3)
            pill_shape = next((shape for shape in shapes if abs(shape['x'] - textbox['x']) < 0.2 and abs(shape['y'] - textbox['y']) < 0.2 and shape['w'] <= 1.4), None)
            if pill_shape:
                pill_shape['w'] = max(pill_shape['w'], textbox['w'])
                pill_shape['h'] = max(pill_shape['h'], textbox['h'] + 0.04)
                pill_shape['y'] = textbox['y'] - 0.01
    return scene
def validate_scene(scene: dict) -> list[dict]:
    issues = []
    textboxes = []
    for idx, element in enumerate(scene.get('elements', [])):
        if element['type'] in {'shape', 'textbox'}:
            x, y, w, h = element['x'], element['y'], element['w'], element['h']
            if element.get('source_selector') == '_bg_glow':
                pass
            elif x < 0 or y < 0 or x + w > SLIDE_W_IN or y + h > SLIDE_H_IN:
                issues.append({'type': 'bounds', 'message': f'元素 {idx} 超出页面边界'})
        if element['type'] == 'textbox':
            est_height = _textbox_required_height(element)
            if est_height > element['h'] + 0.05:
                issues.append({'type': 'text_overflow', 'message': f'文本框内容可能溢出：{element.get("text", "")[:20]}'})
            textboxes.append((idx, element))

    for i in range(len(textboxes)):
        idx_a, a = textboxes[i]
        for j in range(i + 1, len(textboxes)):
            idx_b, b = textboxes[j]
            overlap_w = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
            overlap_h = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
            if overlap_w > 0 and overlap_h > 0 and overlap_w * overlap_h > 0.03:
                issues.append({'type': 'textbox_overlap', 'message': f'文本框可能重叠：{idx_a} 与 {idx_b}'})
    return issues


    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">',
        f'<rect width="1280" height="720" fill="{scene.get("background", "#F7F8FA")}"/>',
        f'<style>text{{font-family:{FONT_FAMILY};}}</style>',
    ]
    for element in scene.get('elements', []):
        if element['type'] == 'shape':
            x = int(element['x'] * PX_PER_IN)
            y = int(element['y'] * PX_PER_IN)
            w = int(element['w'] * PX_PER_IN)
            h = int(element['h'] * PX_PER_IN)
            fill = element.get('fill') or 'none'
            stroke = element.get('line') or 'none'
            fill_opacity = element.get('fill_opacity')
            line_opacity = element.get('line_opacity')
            fill_attr = f' fill-opacity="{max(0.0, min(float(fill_opacity), 1.0))}"' if fill_opacity is not None else ''
            line_attr = f' stroke-opacity="{max(0.0, min(float(line_opacity), 1.0))}"' if line_opacity is not None else ''
            if element.get('shape') == 'oval':
                svg.append(f'<ellipse cx="{x + w//2}" cy="{y + h//2}" rx="{w//2}" ry="{h//2}" fill="{fill}" stroke="{stroke}" stroke-width="1"{fill_attr}{line_attr}/>')
            else:
                rx = 14 if element.get('shape') == 'rounded_rect' else 0
                svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1"{fill_attr}{line_attr}/>')
        elif element['type'] == 'line':
            svg.append(
                f'<line x1="{int(element["x1"] * PX_PER_IN)}" y1="{int(element["y1"] * PX_PER_IN)}" '
                f'x2="{int(element["x2"] * PX_PER_IN)}" y2="{int(element["y2"] * PX_PER_IN)}" '
                f'stroke="{element.get("color", "#D0D5DD")}" stroke-width="{element.get("width", 1.5)}"/>'
            )
        elif element['type'] == 'textbox':
            lines = _wrap_text(element.get('text', ''), element['w'], element.get('font_size', 12))
            x = element['x'] * PX_PER_IN
            y = element['y'] * PX_PER_IN
            w = element['w'] * PX_PER_IN
            font_size = element.get('font_size', 12)
            line_height = font_size * 1.35
            align = element.get('align', 'left')
            if align == 'center':
                anchor = 'middle'
                tx = x + w / 2
            elif align == 'right':
                anchor = 'end'
                tx = x + w
            else:
                anchor = 'start'
                tx = x
            weight = '700' if element.get('bold') else '500'
            svg.append(f'<text x="{int(tx)}" y="{int(y + font_size)}" font-size="{font_size}" font-weight="{weight}" fill="{element.get("color", "#000000")}" text-anchor="{anchor}">')
            for idx, line in enumerate(lines):
                dy = 0 if idx == 0 else line_height
                svg.append(f'<tspan x="{int(tx)}" dy="{dy}">{escape(line)}</tspan>')
            svg.append('</text>')
    svg.append('</svg>')
    return '\n'.join(svg)




def _dedup_parent_child_textboxes(scene: dict) -> dict:
    """移除父子重叠的 textbox：
    1. 当父级文本由子级文本组成时，移除父级（保留子级）
    2. 当子级文本是父级文本的子串且很短（装饰性），移除子级（保留父级）"""
    elements = scene.get('elements', [])
    textboxes = [(i, e) for i, e in enumerate(elements) if e['type'] == 'textbox']
    remove_indices = set()

    for ai, (idx_a, a) in enumerate(textboxes):
        if idx_a in remove_indices:
            continue
        a_text = a.get('text', '').strip()
        if not a_text:
            continue
        ax1, ay1 = a['x'], a['y']
        ax2, ay2 = ax1 + a['w'], ay1 + a['h']
        a_area = a['w'] * a['h']
        if a_area < 0.01:
            continue

        children = []  # (idx_b, b, b_text)
        for bi, (idx_b, b) in enumerate(textboxes):
            if ai == bi or idx_b in remove_indices:
                continue
            b_text = b.get('text', '').strip()
            if not b_text:
                continue
            bx1, by1 = b['x'], b['y']
            bx2, by2 = bx1 + b['w'], by1 + b['h']

            # b 是否被 a 包含（允许容差：x 方向 0.05in，y 方向 0.25in —— 因为子级文本可能因换行/高度估算超出父容器底部）
            tol_x = 0.05
            tol_y = 0.25
            if bx1 >= ax1 - tol_x and by1 >= ay1 - tol_x and bx2 <= ax2 + tol_x and by2 <= ay2 + tol_y:
                children.append((idx_b, b, b_text))

        if not children:
            continue

        children_texts = [t for _, _, t in children]
        combined_children = ''.join(t.replace(' ', '').replace('\n', '') for t in children_texts)
        a_clean = a_text.replace(' ', '').replace('\n', '')

        if combined_children and len(combined_children) >= len(a_clean) * 0.6:
            # 子级文本覆盖了父级大部分内容 → 移除父级
            remove_indices.add(idx_a)
        else:
            # 反向检测：子级是装饰性片段（文本是父级子串且很短）→ 移除子级
            for idx_b, b, b_text in children:
                b_clean = b_text.replace(' ', '').replace('\n', '')
                if len(b_clean) <= 3 and b_clean in a_clean:
                    remove_indices.add(idx_b)

    if remove_indices:
        scene['elements'] = [e for i, e in enumerate(elements) if i not in remove_indices]
    return scene


def auto_fix_scene(scene: dict, page_role: str = 'summary') -> dict:
    scene = _dedup_parent_child_textboxes(scene)
    scene = _apply_scene_safe_patch(scene, page_role)

    for element in scene.get('elements', []):
        if element['type'] != 'textbox':
            continue
        minimum = _min_font_size(element)
        if element.get('font_size', 12) < minimum:
            element['font_size'] = minimum
        required = _textbox_required_height(element)
        while required > element['h'] + 0.02 and element.get('font_size', 12) > minimum:
            element['font_size'] = round(max(minimum, element['font_size'] - 1), 2)
            required = _textbox_required_height(element)
        if required > element['h'] + 0.02:
            element['h'] = round(required + 0.05, 3)

    if page_role in {'cover', 'toc', 'ending'}:
        # 文本高度在 grow 之后会变化，关键版式再走一遍 safe patch 以消除二次重叠
        scene = _apply_scene_safe_patch(scene, page_role)

    textboxes = [element for element in scene.get('elements', []) if element['type'] == 'textbox']
    textboxes.sort(key=lambda e: (e['y'], e['x']))
    for i, a in enumerate(textboxes):
        key_a = _container_key(a)
        if not key_a:
            continue
        for b in textboxes[i + 1:]:
            key_b = _container_key(b)
            if key_a != key_b:
                continue
            overlap_w = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
            overlap_h = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
            if overlap_w > 0 and overlap_h > 0:
                b['y'] = round(a['y'] + a['h'] + 0.04, 3)

    if page_role not in {'cover', 'ending'}:
        for _ in range(6):
            changed = False
            textboxes.sort(key=lambda e: (e['y'], e['x']))
            for i in range(len(textboxes)):
                a = textboxes[i]
                for j in range(i + 1, len(textboxes)):
                    b = textboxes[j]
                    overlap_w = min(a['x'] + a['w'], b['x'] + b['w']) - max(a['x'], b['x'])
                    overlap_h = min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y'])
                    if overlap_w <= 0 or overlap_h <= 0 or overlap_w * overlap_h <= 0.02:
                        continue
                    area_a = a['w'] * a['h']
                    area_b = b['w'] * b['h']
                    move_target = a if area_a < area_b else b
                    anchor = b if move_target is a else a
                    new_y = round(anchor['y'] + anchor['h'] + 0.06, 3)
                    if new_y > move_target['y']:
                        move_target['y'] = new_y
                        changed = True
            if not changed:
                break

    shapes = [element for element in scene.get('elements', []) if element['type'] == 'shape']
    for shape in shapes:
        sx1, sy1, sx2, sy2 = _shape_bounds(shape)
        max_bottom = sy2
        for textbox in textboxes:
            tx1, ty1, tx2, ty2 = _shape_bounds(textbox)
            if tx1 >= sx1 and tx2 <= sx2 and ty1 >= sy1 and ty1 <= sy2:
                max_bottom = max(max_bottom, ty2 + 0.12)
        shape['h'] = round(max(shape['h'], max_bottom - shape['y']), 3)

    max_bottom = 0
    for element in scene.get('elements', []):
        if element['type'] in {'shape', 'textbox'}:
            if element.get('source_selector') in {'_glow', '_bg_glow'}:
                continue
            max_bottom = max(max_bottom, element['y'] + element['h'])
        elif element['type'] == 'line':
            max_bottom = max(max_bottom, element['y1'], element['y2'])
    overflow = round(max(0, max_bottom - (SLIDE_H_IN - 0.15)), 3)
    if overflow > 0 and page_role not in {'cover', 'toc', 'ending'}:
        for element in scene.get('elements', []):
            if element.get('source_selector') in {'_glow', '_bg_glow'}:
                continue
            if element['type'] == 'textbox' and element['y'] > 5.2:
                element['y'] = round(max(0.2, element['y'] - overflow), 3)
            elif element['type'] == 'shape' and element['y'] > 5.0:
                element['y'] = round(max(0.2, element['y'] - overflow), 3)
            elif element['type'] == 'line' and element['y1'] > 5.0 and element['y2'] > 5.0:
                element['y1'] = round(max(0.2, element['y1'] - overflow), 3)
                element['y2'] = round(max(0.2, element['y2'] - overflow), 3)

    return scene


def scene_to_svg(scene: dict) -> str:
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">',
        f'<rect width="1280" height="720" fill="{scene.get("background", "#F7F8FA")}"/>',
        f'<style>text{{font-family:{FONT_FAMILY};}}</style>',
    ]
    for element in scene.get('elements', []):
        if element['type'] == 'shape':
            x = int(element['x'] * PX_PER_IN)
            y = int(element['y'] * PX_PER_IN)
            w = int(element['w'] * PX_PER_IN)
            h = int(element['h'] * PX_PER_IN)
            fill = element.get('fill') or 'none'
            stroke = element.get('line') or 'none'
            if element.get('shape') == 'oval':
                svg.append(f'<ellipse cx="{x + w//2}" cy="{y + h//2}" rx="{w//2}" ry="{h//2}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
            else:
                rx = 14 if element.get('shape') == 'rounded_rect' else 0
                svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        elif element['type'] == 'line':
            svg.append(
                f'<line x1="{int(element["x1"] * PX_PER_IN)}" y1="{int(element["y1"] * PX_PER_IN)}" '
                f'x2="{int(element["x2"] * PX_PER_IN)}" y2="{int(element["y2"] * PX_PER_IN)}" '
                f'stroke="{element.get("color", "#D0D5DD")}" stroke-width="{element.get("width", 1.5)}"/>'
            )
        elif element['type'] == 'textbox':
            lines = _wrap_text(element.get('text', ''), element['w'], element.get('font_size', 12))
            x = element['x'] * PX_PER_IN
            y = element['y'] * PX_PER_IN
            w = element['w'] * PX_PER_IN
            font_size = element.get('font_size', 12)
            line_height = font_size * 1.35
            align = element.get('align', 'left')
            if align == 'center':
                anchor = 'middle'
                tx = x + w / 2
            elif align == 'right':
                anchor = 'end'
                tx = x + w
            else:
                anchor = 'start'
                tx = x
            weight = '700' if element.get('bold') else '500'
            svg.append(f'<text x="{int(tx)}" y="{int(y + font_size)}" font-size="{font_size}" font-weight="{weight}" fill="{element.get("color", "#000000")}" text-anchor="{anchor}">')
            for idx, line in enumerate(lines):
                dy = 0 if idx == 0 else line_height
                svg.append(f'<tspan x="{int(tx)}" dy="{dy}">{escape(line)}</tspan>')
            svg.append('</text>')
    svg.append('</svg>')
    return '\n'.join(svg)


def _parse_review_result(text: str) -> dict:
    result = 'PASS'
    reasons = []
    suggestions = []
    section = 'reasons'
    for raw_line in text.splitlines():
        line = raw_line.strip()
        upper = line.upper()
        if upper.startswith('RESULT:'):
            result = upper.split(':', 1)[1].strip() or 'PASS'
            continue
        if upper.startswith('REASONS:'):
            section = 'reasons'
            continue
        if upper.startswith('SUGGESTIONS:'):
            section = 'suggestions'
            continue
        if line.startswith('- '):
            if section == 'suggestions':
                suggestions.append(line[2:].strip())
            else:
                reasons.append(line[2:].strip())
    normalized = 'REVISE' if 'REVISE' in result else 'PASS'
    return {'result': normalized, 'reasons': reasons, 'suggestions': suggestions, 'raw': text.strip()}


def _write_review_artifact(review_dir: Path, review: dict) -> Path:
    review_path = review_dir / 'review-01.md'
    lines = [
        '# editable_scene_review',
        '',
        f"RESULT: {review['result']}",
        '',
        f"REVIEW_ROUNDS: {review.get('review_rounds', 1)}",
        '',
        '## Reasons',
    ]
    lines.extend([f'- {item}' for item in review.get('reasons', [])] or ['- 无'])
    lines.extend(['', '## Suggestions'])
    lines.extend([f'- {item}' for item in review.get('suggestions', [])] or ['- 无'])
    lines.extend(['', '## Raw', '', review.get('raw', '(empty)')])
    review_path.write_text('\n'.join(lines), encoding='utf-8')
    return review_path


def classify_scene_validation(issues: list[dict], review_result: dict | None = None) -> str:
    if not issues:
        return 'pass'
    review_ok = (review_result or {}).get('result') == 'PASS'
    if review_ok and len(issues) <= 3:
        return 'compact_pass'
    return 'fail'




def _lighten_for_refinement(text: str, limit: int) -> str:
    compact = ' '.join((text or '').split())
    return compact if len(compact) <= limit else compact[:limit].rstrip('，、；。 ') + '…'


def _refinement_material_summary(core_material: str) -> str:
    lines = [line.strip() for line in str(core_material).splitlines() if line.strip()]
    summary = '\n'.join(lines[:3]) if lines else str(core_material).strip()
    return _lighten_for_refinement(summary, 160)

def _scene_prompt(title: str, subtitle: str, core_material: str, page_role: str, audience: str, plan: str, layout_feedback: str = '', refinement_mode: bool = False) -> str:
    structure_hint = {
        'cover': '英雄主观点 + 2 个辅助信息块，焦点强但不要过空',
        'ending': '左侧总结主区 + 右侧路径辅区 + 底部单条金句',
        'timeline': '单条明确时间轴 + 4-5 个节点 + 1 个辅助总结区，不要左右双主体并列',
        'summary': '左侧主区 + 右侧演变/路径辅区 + 底部单条总结，避免双主体并列',
    }.get(page_role, '2 个主区域 + 1 个轻量总结区')
    role_guidance = build_layout_role_guidance(page_role)
    content_budget = build_layout_content_budget(page_role)
    feedback_block = ''
    if layout_feedback:
        feedback_block = f"\n额外修正要求：\n{layout_feedback}\n"
    plan_summary = _lighten_for_refinement(plan, 220) if refinement_mode else plan[:600]
    material_summary = _refinement_material_summary(core_material) if refinement_mode else core_material
    mode_note = "- 当前是整页精炼重写模式：在保持页面主结构不变的前提下，优先缩短句子、删除重复说明、减少次要标签和次要补充块。\n" if refinement_mode else ''
    return f"""请为一个可编辑 PPT {page_role} 页面生成 scene JSON。
页面标题：{title}
页面副标题：{subtitle}
目标受众：{audience}
策划摘要：{plan_summary}
核心素材：{material_summary}

页面角色与结构指导：
{role_guidance}

页面内容预算（尽量遵守）：
{content_budget}

结构要求：
- 页面角色：{page_role}
- 主结构：{structure_hint}
- 风格：浅色、稳重、接近高质量 HTML 演示页
- 不要生成过多碎片小元素
- 元素数量控制在 18-28 个之间
- footer 只能保留 1 个底部总结区，不能重复生成第二条底部总结条或第二层页脚卡片
- 如果内容放不下，优先减少模块数量、缩短文案、压缩步骤和标签，不要靠缩小字号硬塞
- 如果发现正文/底部总结超预算，必须先主动改写为更短、更完整的句子，避免直接输出带“…”的半句
- summary 页左区最多 2 张卡；右区最多 3 个路径/步骤节点；timeline 页最多 4 个节点
- 单张卡片正文优先 1-2 句；标签只用于短分类词，不要塞整句判断
- 本次优化重点：提升投屏可读性，正文和标签不要偏小，优先通过缩短句子和增大区块高度来保证可读性
- 顶部结论、副标题、区块标签、证据卡正文、底部总结条都要有清晰字号层级，避免多个层级都挤在 9-10pt
{mode_note}{feedback_block}
"""


def generate_scene_with_ai(client: AIClient, title: str, subtitle: str, core_material: str,
                           page_role: str, audience: str, plan: str, layout_feedback: str = '',
                           raw_output_path: Path | None = None, refinement_mode: bool = False) -> dict:
    raw = client.chat(
        SCENE_SYSTEM,
        _scene_prompt(title, subtitle, core_material, page_role, audience, plan, layout_feedback, refinement_mode=refinement_mode),
        temperature=0.3,
    )
    if raw_output_path:
        raw_output_path.write_text(raw, encoding='utf-8')
    return normalize_scene(extract_scene_json(raw))


def build_ai_editable_page(title: str, subtitle: str, core_material: str,
                           page_role: str, audience: str, plan: str,
                           out_dir: Path, provider: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir = out_dir / 'reviews'
    review_dir.mkdir(exist_ok=True)
    client = AIClient(provider)
    review_client = None
    if SVG_REVIEW_ENABLED:
        review_client = AIClient(SVG_REVIEW_PROVIDER)
        if SVG_REVIEW_MODEL:
            review_client.model = SVG_REVIEW_MODEL

    review_result = {'result': 'SKIPPED', 'reasons': [], 'suggestions': [], 'raw': 'review disabled', 'review_rounds': 0}
    scene = None
    issues = []
    layout_feedback = ''
    screenshot_path = review_dir / 'slide-01.png'
    preview_svg = out_dir / 'scene-preview.svg'

    for attempt in range(2):
        raw_output_path = out_dir / f'scene-raw-attempt{attempt + 1:02d}.txt'
        try:
            scene = generate_scene_with_ai(
                client, title, subtitle, core_material, page_role, audience, plan, layout_feedback,
                raw_output_path=raw_output_path,
                refinement_mode=attempt > 0,
            )
            budget_issues = _collect_scene_budget_issues(scene, page_role)
            if budget_issues and attempt < 1:
                layout_feedback = _build_budget_refinement_feedback(scene, page_role)
                print(f"    [重试] scene 内容预算未通过，准备精炼重写：{'; '.join(budget_issues[:3])}")
                continue
            scene = auto_fix_scene(_apply_scene_budget(scene, page_role, hard_truncate=True), page_role)
        except Exception as exc:
            if attempt < 1:
                print(f"    [重试] scene 生成第 {attempt + 1} 次失败，准备重试：{exc}")
                continue
            raise

        overflow_for_regen, regen_issues = _validate_scene_for_regeneration(scene)
        issues = validate_scene(scene)
        preview_svg.write_text(scene_to_svg(scene), encoding='utf-8')
        save_svg_screenshot(preview_svg, screenshot_path)

        if overflow_for_regen and attempt < 1:
            layout_feedback = '\n'.join(f'- {item}' for item in regen_issues[:6])
            print(f"    [重试] scene 布局预算未通过，准备重试：{'; '.join(regen_issues[:3])}")
            continue

        if not review_client:
            break

        prompt = f"""请审查这页可编辑 PPT scene 预览图是否适合作为最终导出页面。
页面标题：{title}
页面角色：{page_role}
策划摘要：{plan[:500]}
核心素材：{core_material}
本地校验摘要：\n""" + ('\n'.join(f"- {issue['message']}" for issue in issues[:6]) or '- 无明显本地布局问题')
        review_result = _parse_review_result(
            review_client.review_image(
                REVIEW_SYSTEM,
                prompt,
                screenshot_path,
                reasoning_effort=SVG_REVIEW_REASONING_EFFORT,
            )
        )
        review_result['review_rounds'] = attempt + 1

        if not issues:
            review_result['result'] = 'PASS'
            review_result['reasons'] = ['根据 scene 自动修正后，页面已通过本地布局校验。']
            review_result['suggestions'] = ['无需继续修改']
            review_result['raw'] = 'RESULT: PASS\nREASONS:\n- 根据 scene 自动修正后，页面已通过本地布局校验。\nSUGGESTIONS:\n- 无需继续修改'
            break

        if review_result['result'] != 'REVISE' or not review_result['suggestions']:
            break
        layout_feedback = '\n'.join(f'- {item}' for item in review_result['suggestions'][:4])
        if page_role in {'summary', 'timeline'}:
            layout_feedback += '\n- 只保留一个主视觉结构，另一侧必须退为辅助说明。'
            layout_feedback += '\n- 必须补一条清晰主轴或箭头连接节点，不能只靠并列卡片表达顺序。'
            layout_feedback += '\n- 底部只保留一个总结区，不要再出现第二个页脚式说明区。'
        if issues:
            layout_feedback += '\n' + '\n'.join(f'- {issue["message"]}' for issue in issues[:6])

    if scene is None:
        raise RuntimeError('未能生成可编辑 scene')

    ppt_path = out_dir / 'editable_scene_page.pptx'
    build_editable_ppt(scene, ppt_path)
    review_path = _write_review_artifact(review_dir, review_result)
    validation_status = classify_scene_validation(issues, review_result)
    slide_status = {
        '01': {
            'title': title,
            'page_role': page_role,
            'validation_status': validation_status,
            'final_issues_count': len(issues),
            'review_status': review_result.get('result'),
            'review_rounds': review_result.get('review_rounds', 0),
            'review_path': str(review_path),
            'export_ready': validation_status in {'pass', 'compact_pass'} and review_result.get('result') != 'REVISE',
        }
    }
    write_slide_status(out_dir, slide_status)
    (out_dir / 'scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding='utf-8')
    return ppt_path


def run_editable_topic_page(topic: str, audience: str = '通用受众', page_req: str = '5-8页',
                            page_index: int = 1, provider: str | None = None, research: str = '') -> Path:
    client = AIClient(provider)
    outline = step1_outline(client, topic, audience, page_req, research)
    contents = step2_content(client, outline)
    all_pages = _get_pages(outline)
    if page_index < 1 or page_index > len(all_pages):
        raise ValueError(f'页码超出范围: {page_index}/{len(all_pages)}')
    page = all_pages[page_index - 1]
    title = _get_title(page)
    material = contents.get(title, '')
    plan = step3_plan(client, title, material)
    page_role = _infer_page_role(page_index, len(all_pages), title, plan, material)
    subtitle = (material.splitlines()[0].lstrip('- ').strip()[:42] if material else title)
    out_dir = Path(OUTPUT_DIR) / f"{safe_filename_part(topic, max_length=80)}_editable_page{page_index:02d}"
    return build_ai_editable_page(title, subtitle, material, page_role, audience, plan, out_dir, provider)


def build_editable_page_from_html_experiment(html_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    review_dir = out_dir / 'reviews'
    review_dir.mkdir(exist_ok=True)

    page_role = _infer_page_role(1, 1, html_path.stem, html_path.stem, html_path.stem)
    scene, png_bytes, issue_lines = extract_html_layout_to_scene(html_path, page_role=page_role)
    issues = validate_scene(scene)

    preview_svg = out_dir / 'scene-preview.svg'
    preview_svg.write_text(scene_to_svg(scene), encoding='utf-8')
    save_svg_screenshot(preview_svg, review_dir / 'slide-01.png')
    (review_dir / 'html-source-01.png').write_bytes(png_bytes)

    review_result = {
        'result': 'PASS' if not issues else 'SKIPPED',
        'reasons': issue_lines[:6] or ['HTML→scene→可编辑 PPT 单页实验导出完成'],
        'suggestions': ['对比 html-source 与 editable preview 的一致性'],
        'raw': 'HTML→scene→editable PPT single-page experiment',
        'review_rounds': 0,
    }
    review_path = _write_review_artifact(review_dir, review_result)

    ppt_path = out_dir / 'editable_scene_page.pptx'
    build_editable_ppt(scene, ppt_path)
    validation_status = classify_scene_validation(issues, review_result)
    slide_status = {
        '01': {
            'title': html_path.stem,
            'page_role': page_role,
            'validation_status': validation_status,
            'final_issues_count': len(issues),
            'review_status': review_result.get('result'),
            'review_rounds': review_result.get('review_rounds', 0),
            'review_path': str(review_path),
            'export_ready': len(issues) == 0,
            'scene_path': str(out_dir / 'scene.json'),
        }
    }
    write_slide_status(out_dir, slide_status)
    (out_dir / 'scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding='utf-8')
    return ppt_path
    scene = summary_scene(
        topic='茶叶的由来',
        subtitle='从中国西南山区的植物利用，走向饮用习惯、文化传播与商业价值形成。',
        left_title='起源与早期用途',
        left_body='茶树原产中国西南山区，最早并不一定以“冲泡饮料”出现，而更可能先作为植物资源进入药用、食用与日常利用。',
        left_box1_title='起源地区',
        left_box1_body='中国西南山区\n高湿温暖环境',
        left_box2_title='早期作用',
        left_box2_body='药用 / 食用 / 煮饮\n从植物利用到饮用实践',
        left_note='核心判断：茶叶最早的重要性，不只在“发现一种饮料”，而在于它逐步被纳入日常生活与文化系统。',
        right_title='演变主线',
        right_subtitle='从植物利用到饮用文化的三阶段转化',
        stages=[('01', '植物利用', '药用、食用、采集认知'), ('02', '饮用形成', '煮饮与习惯逐步稳定'), ('03', '文化传播', '从地方实践走向文化商品')],
        footer='总结：茶叶的起点不是单一发明，而是植物利用、饮用习惯与文化系统长期累积的结果。',
    )
    return build_editable_ppt(scene, output_path)


def build_coffee_poc(output_path: Path) -> Path:
    scene = summary_scene(
        topic='咖啡的由来',
        subtitle='从埃塞俄比亚高地的植物利用，走向阿拉伯传播、咖啡馆文化与现代商业饮品。',
        left_title='起源与早期传播',
        left_body='咖啡最早与埃塞俄比亚高地的植物利用相关，随后经阿拉伯世界形成更稳定的烘焙、煮饮与贸易路径。',
        left_box1_title='起源地区',
        left_box1_body='埃塞俄比亚高地\n植物资源利用',
        left_box2_title='早期作用',
        left_box2_body='提神 / 煮饮 / 贸易\n从地方实践到区域传播',
        left_note='核心判断：咖啡的价值不是单点发现，而是起源、传播、社交空间与商业系统共同塑造的结果。',
        right_title='演变主线',
        right_subtitle='从高地植物到全球饮品的三阶段转化',
        stages=[('01', '高地起源', '植物利用与地方经验'), ('02', '阿拉伯传播', '烘焙、煮饮与贸易稳定'), ('03', '商业扩张', '咖啡馆文化与全球商品化')],
        footer='总结：咖啡从地方植物利用发展为全球饮品，关键在于传播网络、社交场景与商业化体系的长期积累。',
    )
    return build_editable_ppt(scene, output_path)


def main():
    parser = argparse.ArgumentParser(description='Editable PPT scene POC / page runner')
    parser.add_argument('--topic', default=None)
    parser.add_argument('--page-index', type=int, default=None)
    parser.add_argument('--audience', default='通用受众')
    parser.add_argument('--pages', default='5-8页')
    parser.add_argument('--provider', default=None)
    parser.add_argument('--research', default='')
    parser.add_argument('--html-experiment', default=None, help='基于已有 HTML 页面做 HTML-first→scene 实验转换')
    args = parser.parse_args()

    out = Path('E:/PPT-AGENT/output/editable_ppt_poc')
    out.mkdir(parents=True, exist_ok=True)

    if args.html_experiment:
        html_path = Path(args.html_experiment)
        out_dir = Path(OUTPUT_DIR) / f"{html_path.stem[:30]}_htmlfirst_experiment"
        path = build_editable_page_from_html_experiment(html_path, out_dir)
        print(path)
        return

    if args.topic and args.page_index:
        path = run_editable_topic_page(args.topic, args.audience, args.pages, args.page_index, args.provider, args.research)
        print(path)
        return

    print(build_tea_poc(out / 'editable_summary_poc.pptx'))
    print(build_coffee_poc(out / 'editable_summary_poc_coffee.pptx'))
    ai_path = build_ai_editable_page(
        '茶叶的由来',
        '从中国西南山区的植物利用，走向饮用习惯、文化传播与商业价值形成。',
        '茶树原产中国西南山区，早期先作为植物资源进入药用、食用与煮饮，随后逐渐形成饮用习惯、文化传播与商品价值。',
        'summary',
        '通用受众',
        '左主右辅 + 底部总结条',
        out / 'editable_ai_scene_tea',
    )
    print(ai_path)


if __name__ == '__main__':
    main()
