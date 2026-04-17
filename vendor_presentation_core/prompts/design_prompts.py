"""
PPT设计基因和视觉指导相关提示词
包含所有用于设计分析和视觉指导的提示词模板
"""

from typing import Dict, Any
import logging
import re

logger = logging.getLogger(__name__)


def _is_image_service_enabled() -> bool:
    """检查图片服务是否启用和可用"""
    try:
        # 尝试获取图片服务实例
        from ..service_instances import get_ppt_service
        ppt_service = get_ppt_service()

        # 检查图片服务是否存在且已初始化
        if not ppt_service.image_service:
            return False

        # 检查图片服务是否已初始化
        if not ppt_service.image_service.initialized:
            return False

        # 检查是否有可用的提供者
        from ..image.providers.base import provider_registry

        # 检查是否有AI生成提供者
        generation_providers = provider_registry.get_generation_providers(enabled_only=True)

        # 检查是否有网络搜索提供者
        search_providers = provider_registry.get_search_providers(enabled_only=True)

        # 检查是否有本地存储提供者（总是可用）
        storage_providers = provider_registry.get_storage_providers(enabled_only=True)

        # 如果有任何可用的提供者（AI生成、网络搜索或本地存储），则认为服务可用
        has_providers = len(generation_providers) > 0 or len(search_providers) > 0 or len(storage_providers) > 0

        logger.debug(f"Image service status: initialized={ppt_service.image_service.initialized}, "
                    f"generation_providers={len(generation_providers)}, "
                    f"search_providers={len(search_providers)}, "
                    f"storage_providers={len(storage_providers)}")

        return has_providers

    except Exception as e:
        logger.debug(f"Failed to check image service status: {e}")
        return False


def _has_slide_image_guidance(slide_data: Dict[str, Any] | None) -> bool:
    """Accept migrated image planning output as usable guidance for HTML generation."""
    if not slide_data:
        return False
    if slide_data.get("images_info"):
        return True
    summary = str(slide_data.get("images_summary", "")).strip()
    return bool(summary)


def _normalize_slide_role(slide_data: Dict[str, Any] | None, page_number: int, total_pages: int) -> str:
    raw_role = str(
        (slide_data or {}).get("page_role")
        or (slide_data or {}).get("slide_type")
        or (slide_data or {}).get("type")
        or ""
    ).strip().lower()
    if raw_role in {"title", "cover", "hero"}:
        return "cover"
    if raw_role in {"toc", "agenda", "directory"}:
        return "toc"
    if raw_role in {"summary", "conclusion"}:
        return "summary"
    if raw_role in {"ending", "closing", "end"}:
        return "ending"
    if raw_role in {"timeline", "roadmap"}:
        return "timeline"
    if page_number == 1:
        return "cover"
    if page_number == total_pages:
        return "ending"
    return raw_role or "content"


class DesignPrompts:
    """PPT设计基因和视觉指导相关的提示词集合"""

    @staticmethod
    def _build_project_brief(confirmed_requirements: Dict[str, Any]) -> str:
        """Build a compact project brief section for creative guidance prompts."""
        confirmed_requirements = confirmed_requirements or {}
        topic = confirmed_requirements.get('topic') or confirmed_requirements.get('title') or ''
        project_type = confirmed_requirements.get('type') or confirmed_requirements.get('scenario') or ''
        scenario = confirmed_requirements.get('scenario') or ''
        audience = (
            confirmed_requirements.get('target_audience')
            or confirmed_requirements.get('custom_audience')
            or ''
        )
        ppt_style = confirmed_requirements.get('ppt_style') or ''
        custom_style_prompt = confirmed_requirements.get('custom_style_prompt') or ''

        lines = [
            f"- 主题：{topic}" if topic else "",
            f"- 项目类型：{project_type}" if project_type else "",
            f"- 使用场景：{scenario}" if scenario else "",
            f"- 目标受众：{audience}" if audience else "",
            f"- 风格偏好：{ppt_style}" if ppt_style else "",
            f"- 自定义风格补充：{custom_style_prompt}" if custom_style_prompt else "",
        ]

        content = "\n".join([line for line in lines if line])
        return content or "- 未提供额外项目背景，请根据大纲内容自行建立合理的设计主张。"

    @staticmethod
    def _build_slide_images_context(slide_data: Dict[str, Any]) -> str:
        """Build image-specific guidance only when image inputs are available."""
        if not _has_slide_image_guidance(slide_data):
            return ""

        return """

**图片设计指导要求：**
- 请充分考虑这些图片资源在设计中的使用方式
- 根据图片的用途、内容描述和尺寸信息提供具体的布局建议
- 考虑图片的实际尺寸（宽度x高度）来优化布局和裁切比例
- 根据图片文件大小和格式选择合适的显示方式
- 确保图片与页面内容的协调性和视觉平衡
- 提供图片样式、蒙版、裁切和位置的优化建议
"""

    @staticmethod
    def _build_first_slide_anchor_context(first_slide_data: Dict[str, Any]) -> str:
        """Build a compact first-slide anchor so project guidance can reason about cover layout."""
        first_slide_data = first_slide_data or {}
        if not first_slide_data:
            return (
                "- 未提供第1页数据，请把第1页视为封面页/首屏引子页，自行推断其构图逻辑，"
                "并在回答中明确哪些判断来自推断。"
            )

        title = first_slide_data.get('title') or first_slide_data.get('page_title') or '第1页'
        slide_type = first_slide_data.get('slide_type') or first_slide_data.get('type') or 'unknown'
        subtitle = (
            first_slide_data.get('subtitle')
            or first_slide_data.get('description')
            or first_slide_data.get('summary')
            or ''
        )
        content_points = first_slide_data.get('content_points') or first_slide_data.get('content') or []

        point_texts = []
        if isinstance(content_points, list):
            for item in content_points[:6]:
                text = str(item).strip()
                if text:
                    point_texts.append(text)
        elif content_points:
            point_texts.append(str(content_points).strip())

        lines = [
            f"- 第1页标题：{title}",
            f"- 第1页类型：{slide_type}",
        ]
        if subtitle:
            lines.append(f"- 第1页补充信息：{subtitle}")
        if point_texts:
            lines.append(f"- 第1页核心信息：{'；'.join(point_texts)}")
        lines.append(
            "- 要求：请据此输出“第1页/封面页首屏锚点策略”，描述构图骨架、主副标题关系、"
            "主视觉处理、背景层次和装饰逻辑，但必须说明哪些做法只属于首页。"
        )
        return "\n".join(lines)

    @staticmethod
    def _build_template_html_context(template_html: str, max_chars: int = 6000) -> str:
        """Build a compact template HTML context with key signals plus a raw excerpt."""
        template_html = (template_html or "").strip()
        if not template_html:
            return (
                "- 当前未提供模板 HTML。请自行建立风格系统，但需要在回答中明确哪些判断"
                "来自项目语义推断，而不是模板约束。"
            )

        def _dedupe(items):
            result = []
            for item in items:
                item = item.strip()
                if item and item not in result:
                    result.append(item)
            return result

        color_tokens = _dedupe(
            re.findall(r'#(?:[0-9a-fA-F]{3,8})|rgba?\([^)]+\)|hsla?\([^)]+\)', template_html)
        )[:8]
        font_tokens = _dedupe(
            re.findall(r'font-family\s*:\s*([^;]+)', template_html, flags=re.IGNORECASE)
        )[:4]
        css_vars = _dedupe(
            [f"--{name}: {value.strip()}" for name, value in re.findall(r'--([\w-]+)\s*:\s*([^;]+)', template_html)]
        )[:6]

        lower_html = template_html.lower()
        structure_tokens = []
        if 'display: grid' in lower_html or 'display:grid' in lower_html:
            structure_tokens.append("存在 Grid 网格组织")
        if 'display: flex' in lower_html or 'display:flex' in lower_html:
            structure_tokens.append("存在 Flex 弹性布局")
        if 'position: absolute' in lower_html or 'position:absolute' in lower_html:
            structure_tokens.append("存在绝对定位叠压/装饰")
        if 'header' in lower_html:
            structure_tokens.append("可能存在页眉框架")
        if 'footer' in lower_html:
            structure_tokens.append("可能存在页脚框架")
        if 'linear-gradient' in lower_html or 'radial-gradient' in lower_html:
            structure_tokens.append("使用渐变背景或渐变描边")
        if 'box-shadow' in lower_html:
            structure_tokens.append("存在阴影层次")
        if 'border-radius' in lower_html:
            structure_tokens.append("存在圆角语言")
        if 'backdrop-filter' in lower_html:
            structure_tokens.append("存在玻璃/模糊材质")

        excerpt = template_html
        if len(excerpt) > max_chars:
            head_chars = int(max_chars * 0.72)
            tail_chars = max_chars - head_chars - 32
            excerpt = (
                f"{excerpt[:head_chars]}\n<!-- ... 中段已截断，保留首尾关键结构 ... -->\n"
                f"{excerpt[-tail_chars:]}"
            )

        lines = [
            "- 请把这段模板 HTML 当作“风格边界 + 结构线索”，而不是要逐字复刻的单页答案。",
        ]
        if color_tokens:
            lines.append(f"- 模板可见色彩线索：{', '.join(color_tokens)}")
        if font_tokens:
            lines.append(f"- 模板可见字体线索：{'；'.join(font_tokens)}")
        if css_vars:
            lines.append(f"- 模板 CSS 变量线索：{'；'.join(css_vars)}")
        if structure_tokens:
            lines.append(f"- 模板结构/材质线索：{'；'.join(structure_tokens)}")
        lines.extend([
            "- 模板 HTML 摘录：",
            "```html",
            excerpt,
            "```",
        ])
        return "\n".join(lines)

    @staticmethod
    def _build_fixed_canvas_strategy_context() -> str:
        """High-level layout guardrails for fixed-size PPT pages."""
        return """
**固定画布防溢出策略**
- 放弃“由内容自然撑高页面”的网页思维，改为“由 1280x720 外框先约束、内容再适配”的组件思维。
- 优先采用三段式结构：页眉、主体、页脚明确分层；页眉页脚不能被压缩，主体区负责吸收剩余空间。
- 先做高度预算，再做视觉设计：Header + Main + Footer + Gap 必须控制在 720px 内，避免页脚被挤出或底部信息丢失。
- 间距优先使用 `gap`、百分比和 `clamp()`，不要依赖大号固定 `padding` 或 `margin` 去硬顶版面。
- 对图表、卡片组、日志窗、长列表、代码块等容易增高的模块，优先限制容器高度、减少列数、收紧装饰，再考虑缩小字号。
- 建立页脚安全区：页码、标识、品牌元素不要贴死边缘；必要时页脚可固定在底部，而主体区必须预留对应底部空间。
""".strip()

    @staticmethod
    def _build_fixed_canvas_html_guardrails() -> str:
        """Detailed implementation guardrails for slide/template HTML generation."""
        return """
**固定比例画布防错机制（强制遵循）**
1. **三段式弹性架构**：
   - 根容器优先使用 `display:flex; flex-direction:column; height:720px; overflow:hidden;`
   - `header` / `footer` 必须 `flex-shrink:0`，绝不允许因为正文变多而被压缩或挤出画布
   - `main-content` 必须优先使用 `flex:1; min-height:0;`，需要居中时可在其内部继续使用 flex/grid
2. **由外框约束内容**：
   - 不要让正文、卡片组或图表自然把页面撑高
   - 布局时先估算页眉高度、页脚高度、主体区最大高度和模块间距，再决定字号与组件数量
3. **安全间距数值策略**：
   - 优先使用 `gap`、百分比和 `clamp()` 控制 `padding`、标题区留白和模块间距
   - 避免类似 `padding-top: 80px` 这类危险的硬编码大数值，除非它已经被模板结构证明安全
4. **溢出保险**：
   - 对卡片组、表格、终端窗口、长列表、代码块、图表容器等容易增高的模块设置 `max-height`
   - 当内容偏多时，优先减少装饰、压缩间距、减少列数和卡片数量，再谨慎下调字号
5. **安全区意识**：
   - 页码、logo、页脚标签等关键元素不能贴死边缘
   - 如果页脚采用 `position:absolute` 或固定到底部，主体区必须显式预留底部 `padding` 或安全区空间
6. **overflow 使用边界**：
   - 允许页面根容器或纯装饰裁切层使用 `overflow:hidden` 维持画布边界
   - 不要把 `overflow:hidden` / `text-overflow: ellipsis` 当作正文、卡片说明、核心要点的常规裁切方案
   - 对次要信息块如日志、代码、终端输出，可在不破坏主信息传达的前提下使用更强的高度约束
7. **输出前自查**：
   - 必须检查 `Header(H) + Main(H) + Footer(H) + Gaps <= 720px`
   - 必须检查页脚是否稳定可见，不能被主体内容顶出画布
   - 必须检查是否存在“固定高度 + 大量文字 + 直接裁切”的风险组合
""".strip()

    @staticmethod
    def _build_visual_density_context(slide_data: Dict[str, Any], page_number: int, total_pages: int) -> str:
        """Extra guardrails to avoid sparse layouts and chaotic corner decorations."""
        slide_role = _normalize_slide_role(slide_data, page_number, total_pages)
        lines = [
            "**Visual density and corner discipline (must follow)**",
            "- Do not leave large empty regions with only a title block and a few generic cards.",
            "- The main content area must contain one dominant visual anchor and one supporting cluster.",
            "- If no real image is available, fill the anchor with abstract visuals such as gradient blobs, orbit rings, dashboard fragments, signal lines, icon groups, or mini charts.",
            "- Decorative elements must be grouped into one or two intentional clusters. Do not scatter unrelated chips, dots, or micro-shapes around multiple corners.",
            "- If the page number is shown in the top-right area, it must be part of a corner cluster that also contains a divider, small label, kicker, chip, or graphic accent.",
            "- Corner cluster elements must share the same edge alignment and spacing rhythm so the corner feels composed rather than floating.",
        ]

        if slide_role == "cover":
            lines.extend(
                [
                    "- Cover slides must feel richer than a normal content page while keeping one clear hero focus.",
                    "- The cover must include at least one hero visual panel or abstract hero graphic in the main area.",
                    "- The cover must include at least one secondary support group such as metric chips, a micro timeline, capability badges, or a compact chart.",
                    "- The cover must behave like an opener. Do not build it as a numbered process, agenda, or section-step slide.",
                    "- Avoid large numeric badges or labels that imply sequence progression such as 1/2/3, 第一步, 第二阶段, or similar ordered markers.",
                    "- If there is a separate toc page in the deck, keep the cover thematic and unnumbered instead of previewing the whole deck as ordered subtopics.",
                ]
            )
        elif slide_role in {"toc", "summary", "ending"}:
            lines.extend(
                [
                    "- Summary-style slides must avoid a hollow center. Use a clear anchor block plus 2-4 compact support items.",
                    "- If the content is short, use structured fillers like grouped chips, mini metrics, or signal bars instead of isolated ornaments.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Content slides still need one obvious anchor, even when they are mostly text or metrics.",
                    "- Support elements should be grouped near the main composition, not pushed into corners as loose decoration.",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def _build_layout_mastery_context() -> str:
        """Advanced layout toolkit used to elevate creative guidance quality."""
        return """
**高级版式方法库（必须内化后使用，不要机械罗列术语）**
- 请把下面的方法当作“布局推理工具箱”，结合模板边界、页面目标、信息密度、受众气质和内容类型，主动选择最适合的版式策略。
- 输出时要把术语转化为可执行的排版判断，例如“采用 12 栏分栏网格，标题跨 8 栏，数据区占 4 栏”，而不是只写“使用分栏网格”。
- 可以混合使用多个方法，但必须明确主导策略、辅助策略，以及内容偏少、适中、偏多时各自如何调节。
- 任何出血、破格、叠层、截断、跨栏等高张力做法，都必须建立在版心、安全区、可读性和信息优先级稳定的前提下。

**一、栅格与空间体系（Grid & Spatial Systems）**
- 版心（Type Area / Live Area）：核心安全渲染区，主要文本和重要图表必须限制在版心内，绝不越界。
- 天头 / 地脚（Top Margin / Bottom Margin）：页面顶部与底部的边缘留白，在 PPT 中通常对应页眉与页脚的固定高度防线。
- 水槽 / 栏间距（Gutter）：相邻列或相邻卡片之间的水平或垂直间隙，决定页面的呼吸感。
- 模块化栅格（Modular Grid）：用纵横参考线切出等比矩形网格，适合展示同层级的大量卡片、图标矩阵、指标宫格，如 3x3、4x2。
- 分栏网格（Column Grid）：只在垂直方向划分栏数，如 12 栏、24 栏系统，适合文本主导页面做不对称切分，如左 4 栏、右 8 栏。
- 基线网格（Baseline Grid）：控制多行文本的底部对齐线，保证跨分栏文本仍具备稳定的纵向节律。
- 出血位（Bleed）：图片或色块故意突破版心直达屏幕边缘，用来制造空间延展感，例如全画幅背景图。
- 微观 / 宏观留白（Micro / Macro Whitespace）：微观留白管字距、行距、组件内间距；宏观留白管版块之间和版心四周的大面积空白。
- 安全边界缩进（Safe Zone Padding）：版心四周额外保留的绝对不可侵犯内边距，用于防止裁切和跨设备变形。

**二、视觉动线与阅读重心（Visual Flow & Reading Gravity）**
- 古腾堡图表 / 阅读重力（Gutenberg Diagram）：第一视觉落点通常在左上，最终停留在右下，重要内容应优先落在对角线关键区。
- F 型动线（F-Pattern）：适合文字密集页，要求左侧有稳定锚点，如项目符号、加粗小标题、编号体系。
- Z 型动线（Z-Pattern）：适合图文交替页，视线从左上到右上，再斜向左下，最后到右下，适合安排图文交错与 CTA 落点。
- 第一落幅 / 视觉锚点（Anchor Point / Primary Focal Point）：用户翻到页面第一眼锁定的元素，通常通过最大字号、最高对比度、最亮色块建立。
- 视觉流向引导（Leading Lines）：利用人物视线、手势、背景几何线条或容器延长线，把注意力指向核心文本区。
- 中心辐射动线（Radial Flow）：把核心信息放在中央，辅助信息环绕或发散，适合核心架构、总分模型、中心结论页。
- 格式塔分组（Gestalt Grouping）：利用亲密性原则，通过元素间距暗示内容关联度，减少多余分割线。

**三、版式结构与构图（Layout Structures & Composition）**
- 三分法则 / 九宫格构图（Rule of Thirds）：把焦点放在四个交叉点或其附近，让图表核心、人物视线、关键数据更自然稳定。
- 非对称平衡 / 动态平衡（Asymmetrical Balance）：左右元素体积不等，但通过色彩重量、信息密度、留白面积实现视觉平衡。
- 瀑布流 / 砌体布局（Masonry Layout）：卡片高度不一时采用交错排布，适合灵感板、案例集合、多维展示。
- 满版排版 / 全画幅（Full-Bleed Layout）：一张大图或大色块铺满页面，文字叠加在模糊蒙版或半透明遮罩上，营造沉浸感。
- 悬浮式排版 / 顶对齐结构（Canopy / Top-heavy Layout）：内容集中在页面中上部，下方留出大面积连续留白，形成轻盈、高级的呼吸感。
- 对角线构图（Diagonal Composition）：重要元素沿页面对角线分布，强化动态张力和速度感。
- 黄金比例分割（Golden Ratio Division, 1:1.618）：版面按约 3.8 : 6.2 切分主副区域，适合建立舒适而高级的主次关系。

**四、对齐、层级与微排版（Alignment, Hierarchy & Micro-typography）**
- 悬挂式缩进 / 凸排（Hanging Indent）：序号或项目符号悬挂在正文左侧之外，让正文形成绝对垂直对齐线。
- 孤行 / 寡行控制（Orphan / Widow Control）：禁止段落尾行只剩一个字，或上一组内容的最后一行孤立到下一组开头，可通过微调字距、文本框宽度强制换行。
- 视觉边界补偿（Optical Alignment / Margin Outset）：对引号、圆形图标、弱边缘元素做轻微外扩，让视觉上的左对齐更精准。
- 纵向节律 / 行高控制（Vertical Rhythm & Leading）：正文行高要与字号保持严格比例，如正文 1.5 倍、标题 1.2 倍，段间距通常为行高的 1.5 到 2 倍。
- 字偶间距调整（Kerning & Tracking）：大标题适当收紧字距增强整体性，小字号注释适当放宽字距提升可读性。
- 视觉层级跃升（Typographic Hierarchy Leap）：主标题与正文之间采用跨越式比例，如 48pt 直接跳到 16pt，制造强烈体积差。

**五、破局与张力制造（Breaking the Grid & Visual Tension）**
- 破格 / 破界排版（Breaking the Grid / Pop-out）：主图或核心数字故意突破卡片边界或栅格边界，制造视觉冲击。
- 叠层排版（Layering / Overlapping）：卡片与卡片、文字与图片发生交叠，并通过投影或层次关系拉开 Z 轴深度。
- 截断感排版（Cropping / Edge Bleeding）：把图片或超大字母故意切到屏幕边缘，暗示画面外仍有延展空间。
- 跨栏延展（Spanning）：在多栏系统中让关键元素横跨所有栏宽，强行打断阅读节奏，形成重音。
- 留白张力（Whitespace Tension）：把元素挤压到某个角落或边缘，留下巨大且不均等的负空间，形成现代感与压迫感。
- 色彩重量倾斜（Color Weight Shift）：用大面积深色或高饱和色块压住一侧，另一侧保持浅色或轻量内容，制造视觉失衡与吸引力。
- 底线对齐 / 沉底排版（Bottom-heavy Layout）：所有内容贴近页面下缘对齐，顶部大面积留空，适合表达基石、沉稳、落地感。
""".strip()

    @staticmethod
    def get_project_design_guide_prompt(confirmed_requirements: Dict[str, Any],
                                        slides_summary: str, total_pages: int,
                                        first_slide_data: Dict[str, Any] = None,
                                        template_html: str = "") -> str:
        """Generate a project-level creative guidance prompt for the whole deck."""
        project_brief = DesignPrompts._build_project_brief(confirmed_requirements)
        slides_summary = slides_summary or "(未提供完整大纲摘要)"
        first_slide_context = DesignPrompts._build_first_slide_anchor_context(first_slide_data)
        template_context = DesignPrompts._build_template_html_context(template_html)
        fixed_canvas_context = DesignPrompts._build_fixed_canvas_strategy_context()
        layout_mastery_context = DesignPrompts._build_layout_mastery_context()

        return f"""作为资深 PPT 创意总监，请基于以下项目信息，为整套 PPT 生成一份“项目级创意设计指导”。

这份指导会在整套幻灯片生成过程中被重复复用，因此你必须输出**全局可迁移**的设计策略，而不是某一页的局部排版答案。
你现在拿到的不只有项目简报，还包含整套结构摘要、第1页内容锚点和参考模板 HTML。

你的任务顺序必须是：
1. 先阅读参考模板 HTML，提炼其中可继承的视觉边界、结构框架和材质语言。
2. 再结合第1页内容，为封面页/首屏页定义一个**明确的布局锚点**。
3. 最后把这种锚点扩展成适用于整套 PPT 的页面家族系统与跨页节奏。

关键约束：
- **如果提供了模板 HTML，必须显式利用它**，说明哪些来自模板，应被继承；哪些允许变化，应被受控改写。
- **请直接依据模板 HTML 本身的结构、页眉页脚、留白、容器比例、配色和字体层级做判断**，不要依赖预设注释字段或固定阈值。
- **必须把“高级版式方法库”当作专业布局推理工具箱**，从中挑选最适合当前项目的栅格、动线、构图、微排版与张力方法，把术语转化为具体的排版决策，而不是机械堆砌名词。
- **必须给出第1页/封面页的首屏锚点策略**，但要明确哪些做法只属于首页，不能机械复制到所有页面。
- 不要把第一页的布局误当作整套 PPT 的统一方案，不要输出过于具体的绝对坐标，也不要直接代写任何页面的 HTML。
- 输出要落到构图关系、信息分区、视觉焦点、配色控制、组件策略和页面节奏，避免空泛形容词堆砌。

**项目简报**
{project_brief}

**整套 PPT 结构摘要**
{slides_summary}

**第1页（封面/首屏）锚点信息**
{first_slide_context}

**参考模板 HTML**
{template_context}

{fixed_canvas_context}

{layout_mastery_context}

**总页数**
- 共 {total_pages} 页

请按以下结构输出项目级创意指导：

**A. 整体叙事与视觉主张**
- 判断这套 PPT 应传达的核心气质、叙事节奏和视觉张力
- 明确整套作品的主视觉概念、风格关键词和整体基调

**B. 模板继承边界与全局风格系统**
- 如果提供了模板 HTML，先说明其中哪些元素应被继承，如页眉/页脚框架、色彩基因、字体气质、边框语言、装饰模块、卡片/图表容器风格
- 再说明哪些部分允许重组和变化，如内容区构图、图文比例、视觉焦点位置、局部强调色、组件组合方式
- 输出整套 PPT 的配色策略、字体气质、图形语言、装饰元素和材质感，并明确重复元素与受控变量

**C. 第1页 / 封面页首屏锚点策略**
- 必须给出首页的构图级布局骨架，例如纵向堆叠、横向分栏、中心聚焦、边缘包裹、主视觉压场等，但不要给绝对坐标
- 说明主标题、副标题/说明信息、辅助信息、品牌标识、装饰元素、背景层级之间的关系
- 说明首页的视觉焦点如何建立，哪些元素只属于首页，不应扩散到常规内容页

**D. 页面家族策略**
- 分别给出封面页、目录/过渡页、常规内容页、数据/图表页、案例/展示页、结尾页的设计打法
- 说明这些页面类型如何从“首页锚点”中继承气质，但在构图、信息密度和重点表达上保持差异
- 说明不同类型页面之间如何既统一又有变化

**E. 跨页版式与节奏**
- 规划页面密度、留白节奏、信息峰值与视觉停顿
- 说明整套 PPT 中如何避免每页都长得一样，同时也避免风格失控
- 请结合模板实际结构与目录中的内容疏密变化，说明当页面内容偏少、适中、偏多时，如何权衡字号、组件尺度、留白和构图复杂度
- 说明在固定 16:9 画布中，如何通过页眉/主体/页脚的高度预算、防溢出架构和安全区意识，避免内容溢出与页脚被挤出

**F. 图像、图标与数据可视化原则**
- 说明图片、插画、图标、图表在整套方案中的角色分工
- 给出适合这套 PPT 的图像处理方式、图表语气和信息可视化方向

**G. 风险与禁区**
- 明确应避免的廉价表达、常见套版感、视觉噪音和不适合的组件形式

**H. 给单页生成器的执行规则**
- 输出 5 到 8 条高度可执行的规则，供后续每一页直接复用
- 规则要能直接指导布局、层级、配色、重点突出、模板继承边界、页面差异化控制，以及按内容多少动态调节字体、组件尺度与留白
- 规则尽量写成“当……时，优先……”或“始终……，避免……”这种可执行句式

输出要求：
- 只输出项目级指导，不要代写某一页的最终 HTML
- 重点是“整套 PPT 的共性策略 + 首页锚点策略 + 页面类型差异策略”
- 内容要具体、专业、可操作，避免空泛形容词堆砌
- 如果模板 HTML 与项目语义存在冲突，请说明如何在不破坏模板基因的前提下做受控修正
"""

    @staticmethod
    def get_slide_design_guide_prompt(slide_data: Dict[str, Any], confirmed_requirements: Dict[str, Any],
                                      slides_summary: str, page_number: int, total_pages: int,
                                      template_html: str = "") -> str:
        """Generate a slide-level creative guidance prompt with deck context."""
        project_brief = DesignPrompts._build_project_brief(confirmed_requirements)
        slides_summary = slides_summary or "(未提供完整大纲摘要)"
        images_context = DesignPrompts._build_slide_images_context(slide_data)
        template_context = DesignPrompts._build_template_html_context(template_html)
        fixed_canvas_context = DesignPrompts._build_fixed_canvas_strategy_context()
        layout_mastery_context = DesignPrompts._build_layout_mastery_context()

        return f"""作为资深 PPT 页面设计师，请基于整套项目上下文，为当前页面生成一份“单页创意设计指导”。
目标是在延续整套 PPT 风格一致性的前提下，让第 {page_number} 页拥有明确角色、合适变化和强执行性的设计建议。
请聚焦当前页，不要把回答写成整套 PPT 的泛泛原则。

**项目简报**
{project_brief}

**整套 PPT 结构摘要**
{slides_summary}

**当前页完整数据**
{slide_data}

**参考模板 HTML**
{template_context}

{fixed_canvas_context}

{layout_mastery_context}

**页面位置**
- 第 {page_number} 页 / 共 {total_pages} 页
{images_context}

额外要求：
- 请直接从模板 HTML 的真实结构中判断哪些边界应继承，例如页眉页脚框架、主内容区范围、留白方式、容器比例、字体层级和装饰强弱。
- 请根据当前页标题长度、要点数量、段落长短，以及是否包含图表、表格、时间线、代码、图片等，自行判断这一页更适合放大焦点、保持均衡，还是压缩收敛。
- 必须主动调用“高级版式方法库”中的栅格、动线、构图、对齐与张力手法，把它们翻译成当前页可执行的布局建议，而不是只做抽象形容。

请按以下结构输出当前页的创意指导：
**A. 当前页角色判断**
- 说明这一页在整套 PPT 中承担什么职责
- 判断它是信息承接页、转场页、重点页、总结页还是其他角色

**B. 视觉焦点与布局骨架**
- 给出当前页最适合的版式方向、视觉重心和信息分区方式
- 说明标题、主体内容、辅助信息应如何建立层级
- 说明当前页应如何利用模板实际呈现出的主内容区边界、留白关系和容器尺度
- 说明当前页如何划分页眉、主体、页脚的高度预算，确保页脚稳定可见

**C. 内容呈现策略**
- 根据当前页内容特点，给出最合适的表达方式
- 说明何处适合卡片化、图示化、图表化、时间线化或对比式呈现
- 必须说明当内容偏少、适中、偏多时，标题、正文、卡片、图表、图标、装饰分别应放大、保持还是收敛

**D. 色彩、组件与图像处理**
- 结合整套风格，说明当前页应该强化哪些颜色、组件或装饰语汇
- 如果有图片资源，请明确图片的使用角色、摆放建议和处理方式

**E. 与前后页面的呼应和差异化**
- 说明当前页应延续哪些全局特征
- 同时指出当前页相较于相邻页面应做出的局部变化，避免连续页面雷同

**F. 执行限制与避坑**
- 给出 3 到 5 条当前页必须注意的风险点
- 避免设计过满、层级混乱、信息淹没、风格跳脱或内容与形式失配
- 必须说明当前页在内容过多时，哪些东西应先收缩：装饰、间距、列数、组件尺寸还是字号
- 必须指出如何避免当前页出现内容溢出、主体把页脚顶出、或安全区被侵占

输出要求：
- 只输出当前页可执行的创意设计指导
- 必须兼顾“全局一致性”和“当前页辨识度”
- 建议要能直接用于页面生成，不要泛泛而谈
- 不要只说“字调小一点”或“留白多一点”，而要结合模板实际结构和当前页内容给出可执行的调度逻辑
"""
    
    @staticmethod
    def get_style_gene_extraction_prompt(template_code: str) -> str:
        """获取设计基因提取提示词"""
        return f"""作为专业的UI/UX设计师，请分析以下HTML模板代码，提取其核心设计基因。

**模板代码：**
```html
{template_code}
```

请从以下维度分析并提取设计基因：

1. **色彩系统**：主色调、辅助色、背景色、文字色等
2. **字体系统**：字体族、字号层级、字重搭配等
3. **布局结构**：页面布局、间距规律、对齐方式等
4. **视觉元素**：边框样式、阴影效果、圆角设计等
5. **交互效果**：动画效果、悬停状态、过渡效果等
6. **组件风格**：按钮样式、卡片设计、图标风格等
7. **补充线索**：如果模板中有注释、语义命名、CSS变量或布局占位，可把它们当作辅助线索提炼设计意图，但不要把任何固定字段当作唯一依据

请以结构化的方式输出设计基因，包含具体的CSS属性值和设计规律，以便后续页面能够保持一致的视觉风格。

输出格式：
- 每个维度用明确的标题分隔
- 提供具体的CSS属性和数值
- 说明设计规律和应用场景
- 突出关键的视觉特征"""

    @staticmethod
    def get_style_genes_extraction_prompt(template_code: str) -> str:
        """向后兼容的设计基因提取提示词（别名）"""
        return DesignPrompts.get_style_gene_extraction_prompt(template_code)

    @staticmethod
    def get_unified_design_guide_prompt(slide_data: Dict[str, Any], page_number: int, total_pages: int) -> str:
        """获取统一设计指导提示词"""

        # 处理图片信息 - 只有在图片服务启用且有图片信息时才包含
        images_context = ""
        if _has_slide_image_guidance(slide_data):
            images_context = f"""


**图片设计指导要求：**
- 请充分考虑这些图片资源在设计中的运用
- 根据图片的用途、内容描述和尺寸信息提供具体的布局建议
- 考虑图片的实际尺寸（宽度x高度）来优化布局和比例
- 根据图片文件大小和格式选择合适的显示方式
- 确保图片与页面内容的协调性和视觉平衡
- 提供图片样式和位置的优化建议
"""

        return f"""作为资深的PPT设计师，请为以下幻灯片生成全面的创意设计指导，包含创意变化指导和内容驱动的设计建议：

**完整幻灯片数据：**
{slide_data}

**页面位置：**第{page_number}页（共{total_pages}页）

{images_context}

请从以下角度生成统一的设计指导：

**A. 页面定位与创意策略**：
- 分析该页面在整体PPT中的作用和重要性
- 确定页面的核心信息传达目标
- 提出符合页面定位的创意设计方向

**B. 视觉层级与布局建议**：
- 根据内容重要性设计视觉层级
- 提供具体的布局方案和元素排列建议
- 考虑信息密度和视觉平衡

**C. 色彩与风格应用**：
- 基于内容特点选择合适的色彩方案
- 提供具体的色彩搭配建议
- 确保与整体PPT风格的一致性

**D. 交互与动效建议**：
- 根据页面类型提供合适的交互效果
- 建议页面切换和元素动画
- 增强用户体验和视觉吸引力

**E. 内容优化建议**：
- 分析内容要点的表达方式
- 提供信息可视化建议
- 优化文字表达和信息结构

请提供具体、可操作的设计指导，帮助生成高质量的PPT页面。"""

    @staticmethod
    def get_creative_variation_prompt(slide_data: Dict[str, Any], page_number: int, total_pages: int) -> str:
        """获取创意变化指导提示词"""
        return f"""作为创意设计专家，请为以下幻灯片提供创意变化指导：

**幻灯片数据：**
{slide_data}

**页面位置：**第{page_number}页（共{total_pages}页）

请从以下角度提供创意指导：

**1. 视觉创意方向**：
- 根据页面内容特点，提出独特的视觉表现方式
- 建议创新的布局形式和元素组合
- 提供差异化的设计思路

**2. 交互创意建议**：
- 设计有趣的页面交互效果
- 提供动态元素的创意应用
- 增强用户参与感和体验感

**3. 内容呈现创新**：
- 优化信息的可视化表达
- 提供创意的内容组织方式
- 增强信息的传达效果

**4. 风格变化控制**：
- 在保持整体一致性的前提下，提供适度的风格变化
- 确保创意不影响信息传达的清晰度
- 平衡创新性与实用性

请提供具体的创意实施建议。"""

    @staticmethod
    def get_content_driven_design_prompt(slide_data: Dict[str, Any], page_number: int, total_pages: int) -> str:
        """获取内容驱动设计建议提示词"""
        return f"""作为内容驱动设计专家，请为以下幻灯片提供基于内容的设计建议：

**幻灯片数据：**
{slide_data}

**页面位置：**第{page_number}页（共{total_pages}页）

请从以下角度提供设计建议：

**1. 内容分析与层级**：
- 分析页面内容的重要性层级
- 确定主要信息和次要信息
- 提供信息优先级排序建议

**2. 视觉表达策略**：
- 根据内容类型选择最佳的视觉表达方式
- 提供图表、图像、文字的组合建议
- 优化信息的可读性和理解性

**3. 布局优化方案**：
- 基于内容特点设计最佳布局
- 确保信息流的逻辑性和连贯性
- 提供空间利用的优化建议

**4. 用户体验考虑**：
- 从目标受众角度优化设计
- 确保信息传达的有效性
- 提高用户的理解和记忆效果

请提供具体的设计实施方案。"""

    @staticmethod
    def get_creative_template_context_prompt(slide_data: Dict[str, Any], template_html: str,
                                           slide_title: str, slide_type: str, page_number: int,
                                           total_pages: int, context_info: str, style_genes: str,
                                           unified_design_guide: str, project_topic: str,
                                           project_type: str, project_audience: str, project_style: str) -> str:
        """获取创意模板上下文提示词"""
        template_context = DesignPrompts._build_template_html_context(template_html)
        fixed_canvas_guardrails = DesignPrompts._build_fixed_canvas_html_guardrails()
        visual_density_context = DesignPrompts._build_visual_density_context(
            slide_data=slide_data,
            page_number=page_number,
            total_pages=total_pages,
        )
        if context_info:
            fixed_canvas_guardrails = f"{fixed_canvas_guardrails}\n\n{context_info}"
        fixed_canvas_guardrails = f"{fixed_canvas_guardrails}\n\n{visual_density_context}"

        # 处理图片信息 - 只有在图片服务启用且有图片信息时才包含
        images_info = ""
        if _has_slide_image_guidance(slide_data):
            images_info = f"""


**图片使用要求：**
- 请在HTML中合理使用这些图片资源
- 图片地址已经是绝对地址，可以直接使用
- 根据图片用途、内容描述和实际尺寸选择合适的位置和样式
- 充分利用图片的尺寸信息（宽度x高度）来优化布局设计
- 根据图片文件大小和格式选择合适的显示策略
- 确保图片与页面内容和设计风格协调
- 可以使用CSS对图片进行适当的样式调整（大小、位置、边框等）
"""

        return f"""你是一位富有创意的设计师，需要为第{page_number}页创建一个既保持风格一致性又充满创意的PPT页面。

**严格内容约束**：
- 页面标题：{slide_title}
- 页面类型：{slide_type}
- 总页数：{total_pages}

**完整页面数据参考**：
{slide_data}

{images_info}

**风格模板（页眉和页脚必须完全保持原样）**：
```html
{template_html}
```

**模板结构与风格线索**：
{template_context}

{fixed_canvas_guardrails}

{context_info}

{visual_density_context}

{context_info}

{visual_density_context}

**❗ 首页（封面页）特殊处理**：
- 如果当前是第1页（封面/标题页），**不需要遵循模板的页眉页脚布局**，应进行全页创意设计：
  * 标题应居中显示，使用大号字体，成为视觉焦点
  * 副标题、作者信息等居中置于标题下方
  * 可以使用全屏背景、装饰图形、渐变等营造视觉冲击力
  * 页码可省略或放在不显眼的位置
- 同样，目录页和尾页也可以自由设计，不受模板页眉页脚约束

**❗ 非封面页的模板遵循规则**：
- 页眉和页脚的整体风格和位置应与参考模板保持一致
- **主要内容区域则应大胆创新**，不要简单套用模板的内容区布局
- 保持模板的配色体系和视觉语言，但布局结构应灵活多变

{context_info}

**核心设计原则**

1.  **固定画布**：所有设计都必须在`1280x720`像素的固定尺寸画布内完成。最终页面应水平和垂直居中显示。
2.  **页面专业度**：核心目标是让页面无论内容多少，都显得**专业且设计感强**。
3.  **模板风格参考**：
   - 页眉和页脚的整体风格应与参考模板保持一致
   - **主要内容区域不要照搬模板布局**，而是根据内容特点重新设计
   - 保持模板的配色体系和视觉语言，但布局结构应灵活多变
4.  **模板结构优先级**：
   - 直接根据模板真实呈现出的页眉页脚、主内容区范围、容器比例、留白节奏、字体层级和装饰强度来判断继承边界
   - 不要依赖固定注释字段或预设密度标签；所有字号、图表尺寸、卡片尺寸、留白和装饰强度都应结合当前页内容自行权衡

**动态内容自适应布局**

请根据内容的多少，智能地选择最佳布局和字体策略，并明确说明内容偏少、适中、偏多时各元素如何变化

**视觉呈现与组件运用**

*   **创意优先**：不要局限于简单的文本列表。请根据内容特点，**自由选择并组合最合适的视觉组件**
*   **视觉层次**：通过大小、颜色和布局的变化，建立清晰的视觉焦点和信息层次。

**设计指导理念**

*   **自然流畅的视觉体验**：页面内容应自然适应可用空间，营造舒适的阅读体验
*   **文字清晰可读**：所有文字内容都应该清晰可见，合理分布在可视区域内
*   **内容完整呈现**：确保所有元素都在可视区域内，避免装饰元素遮挡主要内容

**💡 自适应设计哲学**

设计应该像水一样，能够根据容器自动调整形态，优雅地适应不同内容量：

1. **内容驱动的空间利用**：
   - 当内容较少时，充分利用空间增强视觉表现力
   - 当内容丰富时，智能分配空间确保信息完整展示
   - 让每个元素都找到最适合的空间位置

2. **灵活的布局策略**：
   - 优先考虑信息的清晰传达，其次考虑视觉美感
   - 根据内容特点选择合适的布局方式（垂直、水平、网格等）
   - 空间不足时，可以调整字体、间距或布局结构
   - 若模板本身通过容器尺寸、定位关系或留白方式表达了主内容区边界，应优先围绕这些真实边界组织布局

3. **智能的内容适配**：
   - 文字、图像、图表等元素应该协调共存
   - 重要信息使用视觉层次突出，次要信息合理收敛
   - 保持整体设计的一致性和连贯性

4. **用户体验优先**：
   - 避免任何阻断阅读体验的设计元素
   - 确保内容易于扫描和理解
   - 营造舒适的信息浏览氛围

5. **灵活的视觉层次**：
   - 根据内容重要性调整字体大小和视觉权重
   - 使用适当的留白增强内容可读性
   - 让视觉焦点自然流向核心信息
   - 当内容变多时，优先收敛装饰、压缩间距、简化分栏，再谨慎下调字号

6. **内容完整呈现**：
   - 确保所有文字、图像等元素都在可视区域内
   - 注意元素的层级关系，避免后面的元素遮挡前面的内容
   - 当使用装饰元素、背景、边框等时，确保它们不会影响主要内容
   - 建议重要内容使用较高的层级，避免被装饰元素覆盖

7. **⚠️ 内容溢出防止（强制要求）**：
   - 页面根容器可以使用 `overflow:hidden` 维持 1280x720 画布边界，但不要把它当成正文裁切方案
   - 核心文字必须完整显示，不允许任何关键卡片、容器、列表项中的文字被粗暴截断
   - 如果内容在当前布局中放不下，**必须**通过以下方式适配，优先级从高到低：
     * 减少装饰层、收紧 gap / padding / margin、简化列数与容器数量
     * 调整容器大小或间距增加可用空间
     * 缩小字体大小（font-size）使内容完整显示
     * 切换为多行显示或更紧凑的布局（如减少列数、改为纵向排列）
     * 对日志、代码、终端窗口、次要长列表等模块设置 `max-height`，必要时做摘要化或更强约束
   - 生成 HTML 后请自查：检查是否存在“主体自然撑高页面”或“固定高度容器把页脚顶出”的风险组合

**设计目标**：创造一个既美观又实用的内容展示空间，让每个元素都发挥最佳效果。

**核心设计基因（必须保持）**：
{style_genes}

**统一创意设计指导**：
{unified_design_guide}

**项目背景**：
- 主题：{project_topic}
- 类型：{project_type}
- 目标受众：{project_audience}
- PPT风格：{project_style}

**设计哲学**：
1. **风格一致性** - 参考模板的配色、字体和视觉语言，但不是简单复制模板布局
2. **创意驱动** - 每页的内容区域应该根据内容特点重新设计布局，避免每页看起来都一样
3. **内容适配** - 让设计服务于内容，根据信息量和类型自由选择最佳展示方式
4. **视觉惊喜** - 每一页都应该有独特的视觉亮点，让观众保持新鲜感

**创意要求**：
- **内容区域应大胆创新**：不要简单套用模板的内容区布局，而是根据每页内容的特点重新设计
- 可以使用完全不同于模板的内容布局（卡片、时间线、数据可视化、对比图、流程图等）
- 保持模板的配色体系和视觉风格，但布局结构应灵活多变
- 根据内容特点选择最佳的信息展示方式
- **内容密度调度**：
  * 内容偏少时：优先放大标题、关键数据、主图形与留白，增强视觉冲击
  * 内容适中时：保持均衡比例，让标题、内容、辅助信息形成清晰三层结构
  * 内容偏多时：优先减少装饰层、收紧垂直节奏、减少并列容器数量，再谨慎下调正文与组件尺寸
- **空间利用**：
  * 设计时必须考虑内容如何填满整个可用空间
  * 对于内容较少的页面，通过增大字体、图标、间距等方式充分利用空间
  * 避免所有内容都集中在页面上半部分

**富文本支持**：
- 支持数学公式（使用MathJax）、代码高亮（使用Prism.js）、图表（使用Chart.js）等富文本元素
- 根据内容需要自动添加相应的库和样式

**技术规范**：
- 生成完整的HTML页面（包含<!DOCTYPE html>、head、body）
- 使用Tailwind CSS或内联CSS，确保美观的设计
- 页面尺寸自适应：html {{ height: 100%; display: flex; align-items: center; justify-content: center; }} body {{ width: 100%; height: 100%; position: relative; overflow: hidden; }}
- 支持使用Chart.js和Font Awesome库
- 页码显示为：{page_number}/{total_pages}
- **页眉页脚风格延续**：
  * 页眉区域：延续参考模板的标题风格和视觉特征
  * 页脚区域：保持页码和装饰元素的一致性
- **空间利用建议**：
  * 合理分配主内容区域的空间，避免浪费
  * 根据内容特点动态调整视觉元素
  * 确保所有内容在可视区域内自然展示
  * 保持各元素之间的协调平衡
- 图表元素应完整展示，充分利用可用空间

**重要输出格式要求**：
- 必须使用markdown代码块格式返回HTML代码
- 格式：```html\\n[HTML代码]\\n```
- HTML代码必须以<!DOCTYPE html>开始，以</html>结束
- 不要在代码块前后添加任何解释文字
"""

    @staticmethod
    def get_single_slide_html_prompt(slide_data: Dict[str, Any], confirmed_requirements: Dict[str, Any],
                                   page_number: int, total_pages: int, context_info: str,
                                   style_genes: str, unified_design_guide: str, template_html: str) -> str:
        """获取单页HTML生成提示词"""
        template_context = DesignPrompts._build_template_html_context(template_html)
        fixed_canvas_guardrails = DesignPrompts._build_fixed_canvas_html_guardrails()

        # 处理图片信息 - 只有在图片服务启用且有图片信息时才包含
        images_info = ""
        if _has_slide_image_guidance(slide_data):
            images_info = f"""

**图片使用要求：**
- 请在HTML中合理使用这些图片资源
- 图片地址已经是绝对地址，可以直接使用
- 根据图片用途、内容描述和实际尺寸选择合适的位置和样式
- 充分利用图片的尺寸信息（宽度x高度）来优化布局设计
- 根据图片文件大小和格式选择合适的显示策略
- 确保图片与页面内容和设计风格协调
- 可以使用CSS对图片进行适当的样式调整（大小、位置、边框等）
"""

        return f"""
根据项目信息，为第{page_number}页生成完整的HTML代码。

项目信息：
- 主题：{confirmed_requirements.get('topic', '')}
- 目标受众：{confirmed_requirements.get('target_audience', '')}
- 其他说明：{confirmed_requirements.get('description', '无')}

当前页面信息：
{slide_data}

{images_info}

**风格模板（页眉和页脚必须完全保持原样）**：
```html
{template_html}
```

**模板结构与风格线索**：
{template_context}

{fixed_canvas_guardrails}

**⚠️ 严格保留参考模板的页眉和页脚样式要求 ⚠️**

**绝对不允许修改的区域（除首页、目录页和尾页外）**：
1. **页眉部分**：包括标题位置、字体、颜色、大小、布局等必须与参考模板中所示完全一致
2. **页脚部分**：包括页码、位置、字体、颜色、大小和任何页脚元素必须与参考模板中所示完全一致
3. **模板框架**：页眉和页脚的整体框架结构必须保持完全不变

**允许修改的区域**：
- 仅限页眉和页脚之间的主要内容区域
- 主要内容区域内的布局、颜色、字体可以根据内容需要进行调整
- 主要内容区域内可以添加图片、图表、装饰元素等

**重要说明**：
- 无论生成的幻灯片内容或设计变体如何，页眉和页脚都必须保留原样
- AI生成过程中不应对页眉和页脚模板区域进行任何样式修改
- "完全保持原样"意味着这些区域的所有视觉属性都不能改变
- 请直接依据模板真实结构判断主内容区边界、留白关系和字号层级，不要依赖额外注释字段

**核心设计原则**

1.  **固定画布**：所有设计都必须在`1280x720`像素的固定尺寸画布内完成。最终页面应水平和垂直居中显示。
2.  **页面专业度**：核心目标是让页面无论内容多少，都显得**专业且设计感强**。
3.  **严格的模板框架保持**：
   - **页眉区域**：标题的位置、字体族、字体大小、字体颜色、字体粗细、对齐方式等必须与参考模板完全一致
   - **页脚区域**：页码的位置、字体族、字体大小、字体颜色、字体粗细、对齐方式等必须与参考模板完全一致
   - **框架结构**：页眉和页脚的容器尺寸、边距、内边距等布局属性必须保持不变
   - **视觉统一**：确保所有页面的页眉和页脚在视觉上完全一致，建立统一的品牌框架

**动态内容自适应布局**

请根据内容的数量，智能地选择最佳布局和字体策略。
- 你必须先判断当前页更适合放大焦点、保持均衡还是压缩收敛，再决定标题、正文、图表、卡片、图标、装饰的尺寸和占比。
- 当内容偏多时，先缩减装饰、压缩间距、简化列数和容器数量，再谨慎下调字号；不要直接粗暴缩字。
- 主内容区必须被当作“剩余空间容器”来设计，而不是继续把页脚往下挤。

**视觉呈现与组件运用**

*   **创意优先**：不要局限于简单的文本列表。请根据内容特点，**自由选择并组合最合适的视觉组件**
*   **视觉层次**：通过大小、颜色和布局的变化，建立清晰的视觉焦点和信息层次。

**设计指导理念**

*   **自然流畅的视觉体验**：页面内容应自然适应可用空间，营造舒适的阅读体验
*   **文字清晰可读**：所有文字内容都应该清晰可见，合理分布在可视区域内
*   **内容完整呈现**：确保所有元素都在可视区域内，避免装饰元素遮挡主要内容
**设计平衡要求（一致性与创新并重）**：
1. 使用16:9的响应式PPT尺寸，适配不同屏幕大小
2. **必须保持一致的核心元素**：
   - 遵循提供的设计风格模板中的核心约束
   - 保持主色调和字体系统的统一
   - 维持整体视觉品牌的连贯性
3. **鼓励创新的设计空间**：
   - 根据内容特点创新布局结构
   - 灵活运用视觉元素增强表达效果
   - 适度融入当前设计趋势
   - 优化信息层次和用户体验

**技术规范**：
- 生成完整的HTML页面（包含<!DOCTYPE html>、head、body，不包含style标签）
- 使用Tailwind CSS或内联CSS，确保美观的设计
- 使用16:9响应式设计，适配不同屏幕尺寸
- 使用CSS的aspect-ratio属性保持16:9比例
- 使用clamp()函数实现响应式字体大小
- 使用百分比和vw/vh单位实现响应式布局
- 内容布局清晰，重点突出
- 确保文字清晰可读，颜色搭配协调



{f'''
**图片集成指导**：
- 图片资源: {slide_data.get('image_url', '无')}
- 如果有图片资源，请必须合理地将图片融入页面设计中：
  * 根据图片的实际尺寸（宽度x高度）优化布局和比例设计
  * 考虑图片文件大小，对大文件图片进行适当的压缩显示
  * 根据图片格式（PNG/JPEG/WebP等）选择合适的显示方式
  * 图片大小和位置应与页面布局协调，不影响文字阅读
  * 可以作为背景图、装饰图或内容配图等各种方式使用
  * 确保图片不会导致页面内容溢出或布局混乱
  * 图片应使用响应式设计，适配不同屏幕尺寸

''' if _has_slide_image_guidance(slide_data) else ''}

**富文本支持**：
- 支持数学公式（使用MathJax）、代码高亮（使用Prism.js）、图表（使用Chart.js）等富文本元素
- 根据内容需要自动添加相应的库和样式

**严格的页面尺寸和高度控制**：
- **页面尺寸**：html {{ height: 100%; display: flex; align-items: center; justify-content: center; }} body {{ width: 100%; height: 100%; position: relative; overflow: hidden; }}
- **滚动条禁止**：严禁页面、body或任何容器出现纵向或横向滚动条，必须通过调整布局和内容使其在可视区域内完整呈现
- **内容高度分配**：
   * **页眉区域**：标题的HTML结构、CSS样式、字体族、字体大小、字体颜色、字体粗细、位置、对齐方式等必须与参考模板完全一致，不允许任何修改
   * **页脚区域**：页码的HTML结构、CSS样式、字体族、字体大小、字体颜色、字体粗细、位置、对齐方式等必须与参考模板完全一致，不允许任何修改
   * **主内容区域**：必须作为 `flex:1` 的剩余空间区域，自适应高度（充分利用可用空间，根据页眉页脚和内容动态调整）- 这是唯一允许修改的区域
   * 如果模板本身通过容器尺寸、padding、定位和留白关系表达了主内容区边界，主内容区必须围绕这些真实边界组织，而不是另起一套坐标
   * 如需页脚绝对定位到底部，主内容区域必须预留明确的底部安全区，不能让正文压到页脚上
   * 避免页面内容超出页面底部或顶部
   * 避免页面内容超出页面左右两侧
   * 避免页面内容被遮挡
- **空间充分利用原则**：
  * **内容自适应扩展**：根据内容数量和类型，动态调整各区域高度
  * **避免大量留白**：合理分配空间，避免底部出现过多空余区域

**⚠️ 内容溢出防止（强制要求）**：
- 页面根容器或纯装饰裁切层可以使用 `overflow:hidden`，但不要把它当成正文截断工具
- 所有核心文字必须完整显示，不允许任何关键卡片、容器、列表项中的文字被直接裁切或隐藏
- 如果内容在当前布局中放不下，**必须**通过以下方式适配，优先级从高到低：
  * 减少装饰层、压缩 gap / padding / margin、简化列数与卡片数量
  * 调整容器大小或间距增加可用空间
  * 缩小字体大小（font-size）使内容完整显示
  * 切换为多行显示或更紧凑的布局（如减少列数、改为纵向排列）
  * 对日志、代码、终端窗口、次要长列表等模块设置 `max-height`，必要时做摘要化或更强约束
- 生成 HTML 后请自查：检查是否存在“Header + Main + Footer + Gaps > 720px”的情况，或“主体把页脚顶出画布”的情况

**核心设计基因（必须保持）**：
{style_genes}

**统一创意设计指导**：
{unified_design_guide}

**重要输出格式要求：**
- 必须使用markdown代码块格式返回HTML代码
- 格式：```html\\n[HTML代码]\\n```
- HTML代码必须以<!DOCTYPE html>开始，以</html>结束
- 不要在代码块前后添加任何解释文字
- 确保代码块标记正确且完整
- 严格遵循上述风格要求生成HTML页面
- **页眉页脚保持原样**：生成的HTML中页眉和页脚部分必须与参考模板完全一致，不允许任何修改
"""

    @staticmethod
    def get_combined_style_genes_and_guide_prompt(template_code: str, slide_data: Dict[str, Any],
                                                  page_number: int, total_pages: int) -> str:
        """获取合并的设计基因提取 + 统一设计指导提示词（单次 LLM 调用）

        要求 LLM 输出用分隔标记分开的两段内容：
        - ===STYLE_GENES===  和 ===END_STYLE_GENES===  之间：设计基因
        - ===DESIGN_GUIDE=== 和 ===END_DESIGN_GUIDE=== 之间：通用设计指导
        """

        images_context = ""
        if _has_slide_image_guidance(slide_data):
            images_context = """

**图片设计指导要求：**
- 请充分考虑这些图片资源在设计中的运用
- 根据图片的用途、内容描述和尺寸信息提供具体的布局建议
- 确保图片与页面内容的协调性和视觉平衡
"""
        template_context = DesignPrompts._build_template_html_context(template_code)
        fixed_canvas_context = DesignPrompts._build_fixed_canvas_strategy_context()
        layout_mastery_context = DesignPrompts._build_layout_mastery_context()

        return f"""作为资深的PPT设计师和UI/UX专家，请同时完成以下两项分析任务，将结果分别放在对应的标记区域内。

**任务一：提取核心设计基因**

分析以下HTML模板代码，提取其核心设计基因：

```html
{template_code}
```

**模板结构与风格线索**
{template_context}

{fixed_canvas_context}

{layout_mastery_context}

请从以下维度分析：
1. **色彩系统**：主色调、辅助色、背景色、文字色等
2. **字体系统**：字体族、字号层级、字重搭配等
3. **布局结构**：页面布局、间距规律、对齐方式等
4. **视觉元素**：边框样式、阴影效果、圆角设计等
5. **交互效果**：动画效果、悬停状态、过渡效果等
6. **组件风格**：按钮样式、卡片设计、图标风格等
7. **补充线索**：如果模板中有注释、语义命名、CSS变量或布局占位，可把它们当作辅助线索提炼设计意图，但不要把任何固定字段当作唯一依据

请提供具体的CSS属性值和设计规律，以便后续页面能够保持一致的视觉风格。

---

**任务二：生成通用创意设计指导**

基于提取的设计基因和以下幻灯片信息，生成一份**通用的**创意设计指导，适用于整个PPT的所有页面：

**首页幻灯片数据参考：**
{slide_data}

**页面总数：**{total_pages}页
{images_context}

请从以下角度生成通用设计指导：

- 必须把“高级版式方法库”当作专业布局推理工具箱，优先输出可执行的栅格、动线、构图、微排版与张力策略，而不是空泛审美描述。

**A. 整体设计策略**：
- 分析PPT的整体风格定位和信息传达目标
- 确定贯穿所有页面的核心设计方向
- 提供首页、内容页、结尾页的差异化设计思路

**B. 视觉层级与布局原则**：
- 适用于所有页面的视觉层级设计原则
- 通用的布局方案和元素排列建议
- 信息密度和视觉平衡的指导原则

**C. 色彩与风格应用规范**：
- 基于设计基因的色彩应用规范
- 不同页面类型的色彩搭配建议
- 确保整体PPT风格一致性的准则

**D. 交互与动效规范**：
- 适用于不同页面类型的交互效果规范
- 页面切换和元素动画的统一标准
- 增强用户体验的通用建议

**E. 内容呈现指导**：
- 适用于不同内容量的布局策略
- 信息可视化的通用建议
- 文字表达和信息结构的优化原则
- 明确当内容偏少、适中、偏多时，字体、卡片、图表、装饰和留白如何按顺序放大或收敛
- 说明在固定 16:9 画布中，如何通过三段式布局、高度预算和安全区避免内容溢出与页脚被挤出

---

**输出格式要求（严格遵守）：**

请将两部分结果分别放在以下标记之间：

===STYLE_GENES===
（在此输出设计基因分析结果）
===END_STYLE_GENES===

===DESIGN_GUIDE===
（在此输出通用创意设计指导）
===END_DESIGN_GUIDE===

请确保两部分内容都完整且具体，提供可操作的设计指导。"""

    @staticmethod
    def get_slide_context_prompt(page_number: int, total_pages: int) -> str:
        """获取幻灯片上下文提示词（特殊页面设计要求）"""
        context_parts = []

        if page_number == 1 or page_number == total_pages:
            context_parts.append("**🌟 特殊页面设计要求 🌟**")

            if page_number == 1:
                context_parts.extend([
                    "这是首页，需要在保持原模板风格基础上创造强烈的第一印象。设计原则：",
                    "- **风格一致性**：严格遵循原模板的设计风格、色彩体系、字体选择和布局特征",
                    "- **主题呼应**：确保首页设计与演示主题高度契合，体现专业性和主题相关性",
                    "- **视觉层次**：在原模板框架内运用对比、大小、颜色等手段突出主题标题",
                    "- **背景处理**：基于原模板的背景风格进行适度增强，可考虑渐变、纹理等元素",
                    "- **标题强化**：在保持原模板字体风格的基础上，通过大小、颜色、位置等方式增强表现力",
                    "- **装饰协调**：使用与原模板风格一致的装饰元素，丰富视觉层次但不破坏整体和谐",
                    "- **色彩延续**：严格使用原模板的主色调体系，可适度增加饱和度或亮度来增强吸引力",
                    "- **品牌统一**：确保首页设计与整体演示保持品牌和视觉的统一性"
                ])
            elif page_number == total_pages:
                context_parts.extend([
                    "这是结尾页，需要在保持原模板风格基础上营造完整的收尾感。设计原则：",
                    "- **风格延续**：严格保持与原模板和首页一致的设计风格、色彩和字体体系",
                    "- **主题收尾**：确保结尾页设计与演示主题形成完整呼应，体现主题的完整性",
                    "- **视觉呼应**：与首页和中间页面形成视觉连贯性，保持整体演示的统一感",
                    "- **重点突出**：在原模板框架内突出核心总结信息，确保关键信息得到强调",
                    "- **背景协调**：基于原模板背景风格进行适度处理，营造收尾感但不破坏整体风格",
                    "- **布局平衡**：遵循原模板的布局原则，通过留白和元素分布增强页面的完整感",
                    "- **色彩统一**：严格使用原模板的色彩体系，可适度调整明度来营造收尾氛围",
                    "- **品牌闭环**：确保结尾页与整体演示形成完整的品牌和视觉闭环"
                ])

            context_parts.append("")

        return "\\n".join(context_parts) if context_parts else ""
