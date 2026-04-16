import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from ai_client import AIClient
from config import (
    OUTPUT_DIR,
    SVG_REVIEW_ENABLED,
    SVG_REVIEW_MODEL,
    SVG_REVIEW_PROVIDER,
    SVG_REVIEW_REASONING_EFFORT,
)
from layout_policy import (
    build_budget_refinement_feedback,
    build_layout_content_budget,
    build_layout_role_guidance,
)
from svg_checker import check_svg, format_issues


PROMPTS_DIR = Path(__file__).resolve().parent
OUTLINE_PROMPT_FILE = PROMPTS_DIR / "顶级架构师.md"
SVG_PROMPT_FILE = PROMPTS_DIR / "顶级设计师.md"

CONTENT_SYSTEM = """你是企业级 AI 平台研究员，负责为 PPT 页面输出可直接上页的结论型素材。

你的任务不是罗列搜索结果，而是基于联网检索结果，提炼与当前页面标题强相关的 3-5 条 PPT 要点。

强约束：
1. 必须紧扣页面标题，除非标题明确要求，否则不要展开讲其他平台
2. 每条必须是可直接放进 PPT 的短 bullet，控制在 30-45 字
3. 优先输出结论、能力判断、数据事实、案例结果，不写检索过程
4. 禁止输出 URL、参考文献、脚注编号、来源列表、括号里的长链接
5. 优先使用 2024-2026 的公开事实；不确定就不要编造
6. 最终只输出 3-5 条分点，不要写引言、总结、说明"""

PLAN_SYSTEM = """你是PPT策划稿设计师，负责规划页面布局和元素类型。
输出核心观点、布局规划和元素建议，简洁明确。"""

REVIEW_SYSTEM = """你是独立的 PPT 页面审查员，只负责审查，不负责美化表演。

审查目标：基于页面截图判断该页是否适合作为最终 PPT 页面导出。

审查原则：
1. 优先判断信息密度、视觉层级、重点突出、模块数量、页脚干扰、节奏感
2. 不要重复技术校验已能发现的纯 SVG 边界错误；重点补充“视觉上是否拥挤、是否难读、是否重点不清”
3. 如果页面可接受，输出 PASS
4. 如果页面不可接受，输出 REVISE，并给出最多 4 条保守、可执行的修改建议
5. 建议优先偏局部几何修复：上移文本、增大卡片高度、拉开间距、缩小局部字号/行距；只有明显拥挤时再建议删减内容
6. 不要因为页面元素略多就判错；如果视觉上仍清楚、稳定、有层次，应判为 PASS

输出格式必须严格如下：
RESULT: PASS 或 RESULT: REVISE
REASONS:
- ...
- ...
SUGGESTIONS:
- ...
- ..."""


def load_outline_prompt(page_req: str) -> str:
    template = OUTLINE_PROMPT_FILE.read_text(encoding="utf-8")
    return template.replace("{{PAGE_REQUIREMENTS}}", page_req)


def load_svg_prompt() -> str:
    return SVG_PROMPT_FILE.read_text(encoding="utf-8")


def extract_outline(text: str) -> dict:
    match = re.search(r'\[PPT_OUTLINE\](.*?)\[/PPT_OUTLINE\]', text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # 模型未加标签，直接尝试解析 JSON
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    raise ValueError("无法从模型输出中提取大纲 JSON")


def extract_svg(text: str) -> str:
    match = re.search(r'<svg.*?</svg>', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0)
    return text


def _generate_with_retry(label: str, func, attempts: int = 5):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts:
                print(f"    [重试] {label} 第 {attempt} 次失败，准备重试：{exc}")
            else:
                raise
    raise last_exc


def _parse_review_result(text: str) -> dict:
    result = "PASS"
    reasons = []
    suggestions = []
    section = "reasons"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        upper = line.upper()
        if upper.startswith("RESULT:"):
            result = upper.split(":", 1)[1].strip() or "PASS"
            continue
        if upper.startswith("REASONS:"):
            section = "reasons"
            continue
        if upper.startswith("SUGGESTIONS:"):
            section = "suggestions"
            continue
        if line.startswith("- "):
            if section == "suggestions":
                suggestions.append(line[2:].strip())
            else:
                reasons.append(line[2:].strip())
    normalized = "REVISE" if "REVISE" in result else "PASS"
    return {
        "result": normalized,
        "reasons": [item for item in reasons if item],
        "suggestions": [item for item in suggestions if item],
        "raw": text.strip(),
    }


def _write_review_artifact(review_dir: Path, page_index: int, svg_name: str, review: dict) -> Path:
    review_path = review_dir / f"review-{page_index:02d}.md"
    lines = [
        f"# {svg_name}",
        "",
        f"RESULT: {review['result']}",
        "",
        f"REVIEW_ROUNDS: {review.get('review_rounds', 1)}",
        "",
        "## Reasons",
    ]
    if review["reasons"]:
        lines.extend([f"- {item}" for item in review["reasons"]])
    else:
        lines.append("- 无")
    lines.extend(["", "## Suggestions"])
    if review["suggestions"]:
        lines.extend([f"- {item}" for item in review["suggestions"]])
    else:
        lines.append("- 无")
    lines.extend(["", "## Raw", "", review["raw"] or "(empty)"])
    review_path.write_text("\n".join(lines), encoding="utf-8")
    return review_path


def _text_matches_issue(elem: ET.Element, target: str) -> bool:
    if ((elem.text or "").strip()) == target:
        return True
    for child in list(elem):
        if child.tag.split('}')[-1] != 'tspan':
            continue
        if ((child.text or "").strip()) == target:
            return True
    return False


def _apply_issue_aware_svg_fixes(svg: str, issues: list[dict]) -> str:
    if not issues:
        return svg
    try:
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    changed = False
    vertical_issues = [issue for issue in issues if issue.get("direction") == "vertical"]
    overlap_issues = [issue for issue in issues if issue.get("direction") == "overlap"]

    for issue in vertical_issues:
        target = (issue.get("text") or "").strip()
        if not target:
            continue
        for elem in root.iter():
            if elem.tag.split('}')[-1] != 'text':
                continue
            if not _text_matches_issue(elem, target):
                continue
            y = elem.get('y')
            if not y:
                break
            try:
                y_val = float(y)
            except ValueError:
                break

            overflow = float(issue.get("overflow_y", 0) or 0)
            shift = max(8, int(overflow) + 6)
            elem.set('y', str(int(y_val - shift)))
            cls = elem.get('class', '')
            if 'step-desc' in cls:
                elem.set('font-size', '13')
            elif 'note' in cls:
                elem.set('font-size', '12')
            elif 'metric-desc' in cls:
                elem.set('font-size', '13')
            elif 'bodySm' in cls:
                elem.set('font-size', '13')
            changed = True
            break

        card_x = issue.get("card_x")
        card_y = issue.get("card_y")
        if card_x is not None and card_y is not None:
            for elem in root.iter():
                if elem.tag.split('}')[-1] != 'rect':
                    continue
                try:
                    x = float(elem.get('x', 'nan'))
                    y = float(elem.get('y', 'nan'))
                    h = float(elem.get('height', 'nan'))
                except ValueError:
                    continue
                if int(x) == int(card_x) and int(y) == int(card_y):
                    elem.set('height', str(int(h + max(8, int(issue.get("overflow_y", 0) or 0) + 6))))
                    changed = True
                    break

    for issue in overlap_issues:
        target = (issue.get("text2") or issue.get("text") or "").strip()
        if not target:
            continue
        for elem in root.iter():
            if elem.tag.split('}')[-1] != 'text':
                continue
            if not _text_matches_issue(elem, target):
                continue
            y = elem.get('y')
            if not y:
                break
            try:
                y_val = float(y)
            except ValueError:
                break
            elem.set('y', str(int(y_val + 10)))
            changed = True
            break

    if not changed:
        return svg
    return ET.tostring(root, encoding='unicode')


def _apply_final_svg_compaction(svg: str) -> str:
    try:
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg

    changed = False
    for elem in root.iter():
        tag = elem.tag.split('}')[-1]
        if tag != 'text':
            continue
        y = elem.get('y')
        if not y:
            continue
        try:
            y_val = float(y)
        except ValueError:
            continue

        if y_val < 640:
            continue

        tspans = [child for child in list(elem) if child.tag.split('}')[-1] == 'tspan']
        font_size = elem.get('font-size')
        current_size = None
        if font_size:
            try:
                current_size = float(font_size)
            except ValueError:
                current_size = None

        if current_size and current_size >= 24:
            elem.set('font-size', str(max(24, current_size - 4)).rstrip('0').rstrip('.'))
            changed = True
        elif current_size and current_size >= 16:
            elem.set('font-size', str(max(14, current_size - 2)).rstrip('0').rstrip('.'))
            changed = True

        if tspans:
            for tspan in tspans[1:]:
                dy = tspan.get('dy')
                if not dy:
                    continue
                try:
                    dy_val = float(dy)
                except ValueError:
                    continue
                if dy_val > 18:
                    tspan.set('dy', str(max(16, dy_val - 4)).rstrip('0').rstrip('.'))
                    changed = True
                elif dy_val > 14:
                    tspan.set('dy', str(max(13, dy_val - 2)).rstrip('0').rstrip('.'))
                    changed = True
            if len(tspans) >= 2 and y_val >= 645:
                elem.set('y', str(int(y_val - 8)))
                changed = True
        elif y_val >= 650:
            elem.set('y', str(int(y_val - 10)))
            changed = True
        elif y_val >= 640:
            elem.set('y', str(int(y_val - 6)))
            changed = True

    if not changed:
        return svg
    return ET.tostring(root, encoding='unicode')


def _classify_svg_validation(issues: list[dict], review_result: dict | None = None) -> str:
    if not issues:
        return "pass"
    review_ok = (review_result or {}).get("result") == "PASS"
    if review_ok and len(issues) <= 3 and all(issue.get("direction") in {"vertical", "overlap"} for issue in issues):
        return "compact_pass"
    return "regenerate"



def _build_svg_regen_feedback(page_role: str, issues: list[dict]) -> str:
    if not issues:
        return ""
    issue_text = format_issues(issues).splitlines()
    summary_lines = [
        "- 当前版本未通过 SVG 技术校验，请在保持整体风格的前提下修正。",
        "- 优先保证卡片边界安全、阅读顺序稳定、footer 不被主内容挤压。",
    ]
    summary_lines.extend(issue_text[:8])
    return build_budget_refinement_feedback(page_role, summary_lines)



def _validate_and_optionally_regenerate_svg(client: AIClient, svg_path: Path,
                                            title: str, material: str, plan: str,
                                            audience: str, page_role: str,
                                            polish: bool) -> tuple[str, list[dict]]:
    svg = svg_path.read_text(encoding="utf-8")
    issues = check_svg(svg)
    if not issues:
        print(f"    [检查] {svg_path.name} 通过 SVG 技术校验")
        return svg, issues

    attempts = 2 if polish else 1
    current_svg = svg
    current_issues = issues
    for attempt in range(attempts):
        regen_feedback = _build_svg_regen_feedback(page_role, current_issues)
        if attempt == 0:
            print(f"    [检查] {svg_path.name} 存在结构性 SVG 问题，执行一次重生成...")
        else:
            print(f"    [精修] {svg_path.name} 仍有问题，执行逐页精修重生成...")
        current_svg = step4_svg(client, title, material, plan, audience, page_role, layout_feedback=regen_feedback)
        current_svg = _apply_issue_aware_svg_fixes(current_svg, current_issues)
        current_svg = _apply_final_svg_compaction(current_svg)
        svg_path.write_text(current_svg, encoding="utf-8")
        current_issues = check_svg(current_svg)
        if not current_issues:
            print(f"    [检查] {svg_path.name} 重生成后通过 SVG 技术校验")
            return current_svg, current_issues

    if current_issues:
        print(f"    [检查] {svg_path.name} 仍有 {len(current_issues)} 个问题，使用当前最优版本继续")
    return current_svg, current_issues




def _infer_page_role(index: int, total_pages: int, title: str, plan: str, material: str) -> str:
    text = f"{title}\n{plan}\n{material}".lower()
    if any(keyword in text for keyword in ["目录", "agenda", "toc"]):
        return "toc"
    if index == 1 or any(keyword in text for keyword in ["封面", "cover"]):
        return "cover"
    if index == total_pages or any(keyword in text for keyword in ["总结与展望", "thanks", "thank", "ending"]):
        return "ending"
    if any(keyword in text for keyword in ["总结", "结论", "判断", "建议", "表达", "路线", "路径", "销售", "应用", "价值", "话术"]):
        return "summary"
    if any(keyword in text for keyword in ["脉络", "发展史", "演变", "阶段", "timeline"]):
        return "timeline"
    return "content"


def _build_svg_budget_constraints(page_role: str) -> str:
    common = """- 页面总高固定为 720px，生成前必须先做空间预算。
- 标题区最多占 90-110px；主内容区约 500-540px；footer/总结区约 80-96px。
- 必须先锁定标题区和 footer，再让中间主内容区适配剩余空间。
- 主内容区与 footer 之间至少保留 16-20px 空隙，绝不能互相挤压或重叠。
- 页面采用 Bento Grid / 卡片式结构，但优先少量大区块，不要堆大量碎卡。
- 默认优先结构是：1 个主模块 + 1 个辅助模块 + 1 个薄 footer 总结条。
- 如果内容放不下，必须按顺序处理：删除重复说明 → 删除次要标签/补充块 → 减少模块数量 → 减少步骤/节点数量 → 缩短句子；最后才允许轻微缩小字号。
- 绝对禁止靠裁切文字、极小字号或把页面做空来过检。
- 所有卡片之间至少保留 20px 间距，卡片内边距建议 20-32px。
- 所有文字必须完整可见，不能贴边、越界、裁切或压到装饰元素上。"""
    role_specific = {
        "cover": """- cover 页只保留单焦点标题区 + 少量辅助信息，不要扩成多主体。
- 可增加 1 组轻量数字/阶段/关键词支撑，但不能抢标题主视觉。""",
        "toc": """- toc 页优先 1 个主卡 + 2-4 个目录项，最多 1 个轻量辅助说明区。
- 不要做复杂三栏，也不要补大型数据卡。""",
        "summary": """- summary 页固定为 2 个主区域 + 1 个 footer。
- 左区最多 2 张主卡；右区最多 3 个步骤/路径节点，或 1 组指标卡。
- 如果已有步骤区，就不要再叠第二层总结大段文字。
- 如果已有指标块，只保留 1 个大数字模块。""",
        "timeline": """- timeline 页最多 4 个时间节点 + 1-2 个辅助卡。
- 每节点只保留：阶段名 + 时间 + 1 句说明 + 最多 2 个短标签。
- 如果既有时间线又有右侧指标卡，优先减少节点，不要双边同时过满。""",
        "ending": """- ending 页要收束，固定为左主右辅 + 底部单条金句。
- 左侧最多 2 张总结模块；右侧最多 3 步路径区；底部只保留 1 条强化结论。
- 不要再叠第二个总结块或第二层 footer。""",
        "content": """- 普通内容页默认 2 个主区域 + 1 个轻量总结区。
- 辅助区最多保留 1 类辅助信息：步骤 / 指标 / 场景 / 时间线 四选一。
- 不要同时混合太多表达结构。""",
    }.get(page_role, "")
    micro_rules = """- 步骤/路径最多 3 步；每步只保留序号 + 短标题 + 1 句说明（如确有必要）。
- 指标区最多保留 1 个大数字或 1 个日期模块，下方只能配 1 段简短说明。
- 标签/胶囊每组最多 2-4 个；单个标签优先控制在 4-8 个中文字符或 1-3 个英文词。
- 标签只承载分类词、状态词、关键词，禁止把结论句或流程说明句塞进胶囊。
- 标题最多 2 行，卡片标题最多 2 行，正文长句优先拆成 2-3 行，正文不得小于 12px。"""
    return "\n".join([common, role_specific, micro_rules]).strip()


def _get_pages(outline: dict) -> list:
    """兼容两种大纲结构：扁平 pages[] 或 ppt_outline 的 cover/toc/parts/end_page。"""
    if "pages" in outline:
        return outline["pages"]
    inner = outline.get("ppt_outline", outline)
    pages = []
    for key in ("cover", "table_of_contents"):
        page = inner.get(key)
        if page:
            pages.append(page)
    for part in inner.get("parts", []):
        pages.extend(part.get("pages", []))
    end_page = inner.get("end_page")
    if end_page:
        pages.append(end_page)
    return pages


def _get_title(page: dict) -> str:
    return page.get("title") or page.get("page_title", f"第{page.get('page','')}页")


def _fallback_page_content(title: str, hint: str) -> str:
    base_points = [
        f"- 围绕“{title}”先给出最核心定义，再说明它为什么重要。",
        f"- 结合页面主题，提炼 2-3 个最直接的判断或事实，不展开冗长背景。",
        f"- 如果涉及时间、用途、差异或价值，只保留最关键的一层信息。",
    ]
    if hint:
        base_points.append(f"- 参考要点：{hint[:60]}{'…' if len(hint) > 60 else ''}")
    return "\n".join(base_points[:4])


def step1_outline(client: AIClient, topic: str, audience: str,
                  page_req: str, research: str = "") -> dict:
    instructions = load_outline_prompt(page_req)
    user = f"""PPT主题：{topic}
目标受众：{audience}
页数要求：{page_req}
调研信息：{research or '暂无，请根据主题合理规划'}

请生成完整PPT大纲，严格遵循JSON格式。"""
    if client.provider == "openai":
        raw = client.responses(instructions, user)
    else:
        raw = client.chat(instructions, user, temperature=0.6)
    return extract_outline(raw)


def step2_content(client: AIClient, outline: dict) -> dict:
    pages = _get_pages(outline)
    contents = {}
    for page in pages:
        title = _get_title(page)
        sections = page.get("sections") or page.get("content") or []
        hint = "\n".join(str(s) for s in sections) if sections else ""
        user = f"""页面标题：{title}
页面参考要点：{hint or '无'}

请联网检索后输出适合 PPT 正文的内容，要求：
- 只保留与该页面标题直接相关的信息
- 输出 3-5 条短 bullet
- 每条控制在 30-45 字
- 尽量包含明确数据、能力事实、发布时间点或可验证结论
- 禁止输出网址、来源、脚注编号、参考文献
- 禁止使用“据报道”“有观点认为”“可能”“或许”等模糊表述
- 如果检索结果不足，就输出更稳妥的能力结论，不要硬编

直接输出分点列表。"""
        try:
            if client.provider == "openai":
                tools = [{"type": "web_search", "search_context_size": "high"}]
                contents[title] = client.responses(
                    CONTENT_SYSTEM,
                    user,
                    reasoning_effort="low",
                    tools=tools,
                )
            else:
                contents[title] = client.chat(CONTENT_SYSTEM, user, temperature=0.5)
        except Exception as exc:
            print(f"    [降级] 页面《{title}》联网扩写失败，改用保守内容生成：{exc}")
            fallback_user = f"""页面标题：{title}
页面参考要点：{hint or '无'}

请不要联网，直接基于标题与参考要点，输出适合 PPT 的 2-3 条保守短 bullet。
要求：
- 不要编造具体年份、数据、机构
- 优先输出定义、用途、判断逻辑、常见差异
- 每条控制在 22-35 字
- 只输出分点列表"""
            try:
                contents[title] = client.chat(CONTENT_SYSTEM, fallback_user, temperature=0.3)
            except Exception:
                contents[title] = _fallback_page_content(title, hint)
    return contents


def step3_plan(client: AIClient, title: str, material: str) -> str:
    user = f"""页面标题：{title}
素材内容：{material}
请输出：1.核心观点 2.布局规划 3.元素建议"""
    return _generate_with_retry(
        f"策划稿《{title}》",
        lambda: client.chat(PLAN_SYSTEM, user, temperature=0.6),
        attempts=4,
    )


def step4_svg(client: AIClient, title: str, material: str, plan: str, audience: str,
              page_role: str = "content", layout_feedback: str = "") -> str:
    role_guidance = build_layout_role_guidance(page_role)
    content_budget = build_layout_content_budget(page_role)
    budget_constraints = _build_svg_budget_constraints(page_role)
    feedback_block = ""
    if layout_feedback:
        feedback_block = f"""

额外修正要求（来自独立截图审查或技术校验）：
{layout_feedback}

请严格按“保内容的局部修复”执行：
- 优先微调局部几何：上移文本、增大卡片高度、拉开间距、压缩局部字号或行距
- 如果反馈显示内容预算超限，先删重复说明、次要标签、次要补充块，再考虑缩减步骤/节点
- 保持原有信息密度，不要无必要地把页面改得过空
- 不要新增复杂结构，不要为了修复再堆更多装饰元素"""
    user = f"""请将以下内容转化为专业SVG演示文稿页面：
页面标题：{title}
核心素材：{material}
布局规划：{plan}
目标受众：{audience}
页面角色：{page_role}{feedback_block}

页面角色与结构指导（与 HTML 链路一致，必须遵守）：
{role_guidance}

页面内容预算（与 HTML 链路一致，必须优先遵守）：
{content_budget}

页面空间与删减约束（必须严格遵守）：
{budget_constraints}

生成约束：
- 最终视觉风格必须根据目标受众决定；如果受众偏企业、管理层、政务或 ToB，则更稳重克制；如果受众偏高校、学生或年轻群体，则可以更轻快，但仍需专业。
- SVG 页面的版式结构、信息密度、视觉层级、阅读路径应尽量对齐成熟的 HTML 演示页，但保留 SVG 可编辑特性。
- 优先做“丰富但有层次”的布局：主观点区 + 1-2 组辅助信息区 + 轻量总结区，而不是只有非常少的元素。
- 若页面视觉上仍清楚稳定，不要为了保守而主动删减模块；只有出现明显拥挤、重叠、重点不清时，才减少元素数量。
- 所有文本必须严格落在画布与卡片安全边界内，不能越出卡片、贴边、裁切或压到装饰元素上。
- 垂直方向同样重要：多行 tspan 堆叠后的总高度不得超出所属卡片的底边；放置文本前先计算 y + 行数×dy 是否超过卡片 y+height-16，超过时必须减少行数、缩小 dy 或增大卡片高度。
- 标题、副标题、注释等不同文本块之间必须保留足够的 y 间距，避免上下文字区域重叠。标题 dy 不得小于 font-size 的 1.2 倍。
- 页面标题与卡片标题如偏长，必须自动拆为 2 行内；正文不得出现明显超宽单行。
- 长正文优先拆成 2-3 行，多行文本优先使用 <tspan> 排版，不要把长句直接塞进单行 <text>。
- 如果内容过长，优先通过增加卡片高度、拆分层级、拉开间距来消化内容；只有确实放不下时，再减少 bullet 数量、合并相近信息或提炼结论，不要靠无限缩小字号硬塞。
- 标签、胶囊、页脚说明、注释文字使用更保守的长度控制，避免出现超长单行。
- 标签与胶囊只能承载非常短的分类词、状态词或关键词；单个标签优先控制在 4-8 个中文字符或 1-3 个英文词内。
- 同一区域可以有适量标签与辅助元素，但要保持整齐分组；若标签过多、过长或显得杂乱，再考虑删减，只保留最关键标签，或改成普通正文。
- 不要把转折句、结论句、流程说明句塞进胶囊；这类内容应改用普通文本或分组标题表达。
- 时间信息优先拆成”时间小标签 + 普通说明文字”，不要把时间和整句说明做成同一个长胶囊。
- 阶段名称、能力环节、流程节点优先使用简洁中文短词，除非英文术语本身不可替换。
- 页脚说明默认拆成 2 行内，优先使用 <tspan> 换行，不要把整段补充说明压成一整条长句。
- 请使用更丰富但专业的配色，并明确区分标题、正文、说明、标签、数字的颜色层级。
- 卡片需要有统一的圆角、描边、阴影和内边距系统，确保页面层次清晰且风格一致。
- 直接输出完整 SVG 代码。"""
    raw = _generate_with_retry(
        f"SVG生成《{title}》",
        lambda: client.chat(load_svg_prompt(), user, temperature=0.4),
    )
    svg = extract_svg(raw)

    issues = check_svg(svg)
    if not issues:
        return svg

    fix_prompt = format_issues(issues)
    n_h = sum(1 for i in issues if i["direction"] == "horizontal")
    n_v = sum(1 for i in issues if i["direction"] == "vertical")
    n_o = sum(1 for i in issues if i["direction"] == "overlap")
    desc = "、".join(filter(None, [
        f"水平溢出{n_h}处" if n_h else "",
        f"垂直溢出{n_v}处" if n_v else "",
        f"文本重叠{n_o}处" if n_o else "",
    ]))
    print(f"    [检查] 检测到 {desc}，正在修复...")
    fix_user = f"""以下是一份已生成的 SVG 演示文稿页面，但存在排版问题（可能包括：文本水平超出卡片宽度、文本垂直超出卡片底边、文本之间区域重叠）。
请在保持整体设计不变的前提下，只修复问题部分，输出完整的修复后 SVG 代码。

原始 SVG：
{svg}

{fix_prompt}"""
    fix_raw = _generate_with_retry(
        f"SVG修复《{title}》第1轮",
        lambda: client.chat(load_svg_prompt(), fix_user, temperature=0.3),
    )
    fixed_svg = extract_svg(fix_raw)

    remaining = check_svg(fixed_svg)
    if not remaining:
        print("    [检查] 修复完成，所有排版问题已解决")
        return fixed_svg

    fix_prompt2 = format_issues(remaining)
    print(f"    [检查] 第一轮修复后仍有 {len(remaining)} 处问题，进行第二轮修复...")
    fix_user2 = f"""以下 SVG 仍存在排版问题，请继续修复。注意：这是第二轮修复，请更大胆地调整布局（如增大卡片高度、拉开文本间距、缩短文案）来彻底解决问题。

原始 SVG：
{fixed_svg}

{fix_prompt2}"""
    fix_raw2 = _generate_with_retry(
        f"SVG修复《{title}》第2轮",
        lambda: client.chat(load_svg_prompt(), fix_user2, temperature=0.3),
    )
    fixed_svg2 = extract_svg(fix_raw2)

    remaining2 = check_svg(fixed_svg2)
    if remaining2:
        print(f"    [检查] 第二轮修复后仍有 {len(remaining2)} 处问题，使用当前版本继续")
    else:
        print("    [检查] 第二轮修复完成，所有排版问题已解决")
    return fixed_svg2


def _review_and_optionally_fix_svg(generator_client: AIClient, review_client: AIClient | None,
                                   svg_path: Path, page_index: int, title: str,
                                   material: str, plan: str, audience: str,
                                   page_role: str, validation_issues: list[dict]) -> dict:
    review_result = {
        "result": "SKIPPED",
        "reasons": [],
        "suggestions": [],
        "raw": "review disabled",
        "review_path": None,
        "review_rounds": 0,
    }
    if not review_client:
        return review_result

    from pptx_builder import save_svg_screenshot

    review_dir = svg_path.parent.parent / "reviews"
    review_dir.mkdir(exist_ok=True)
    screenshot_path = review_dir / f"slide-{page_index:02d}.png"
    save_svg_screenshot(svg_path, screenshot_path)

    current_svg = svg_path.read_text(encoding="utf-8")
    current_issues = list(validation_issues)
    current_review = None

    for attempt in range(2):
        issue_text = format_issues(current_issues) if current_issues else "- 无明显技术排版问题"
        review_prompt = f"""请审查这页 PPT 截图是否适合作为最终导出页面。
页面标题：{title}
页面角色：{page_role}
目标受众：{audience}
策划摘要：{plan[:500]}
素材摘要：{material[:500]}
技术校验摘要：
{issue_text}

请重点判断：
- 信息是否过满
- 模块是否过多
- 视觉重点是否清楚
- 页脚是否喧宾夺主
- 是否需要删减节点/指标/场景/说明文字
- 是否在保持丰富信息量的同时仍然层次清楚、阅读稳定
"""
        current_review = _parse_review_result(
            _generate_with_retry(
                f"SVG截图审查《{title}》第{attempt + 1}轮",
                lambda: review_client.review_image(
                    REVIEW_SYSTEM,
                    review_prompt,
                    screenshot_path,
                    reasoning_effort=SVG_REVIEW_REASONING_EFFORT,
                ),
                attempts=4,
            )
        )
        current_review["review_rounds"] = attempt + 1

        if current_review["result"] != "REVISE" or not current_review["suggestions"]:
            break

        review_feedback = "\n".join(f"- {item}" for item in current_review["suggestions"][:4])
        if page_role == "ending":
            review_feedback += "\n- ending 页应更收束，但优先通过局部几何微调达成：缩短重复句、上移右侧说明、压紧局部间距，不要把页面改空。"
        if current_issues:
            review_feedback = f"{review_feedback}\n\n{format_issues(current_issues)}"
        updated_svg = step4_svg(generator_client, title, material, plan, audience, page_role, layout_feedback=review_feedback)
        updated_svg = _apply_issue_aware_svg_fixes(updated_svg, current_issues)
        updated_svg = _apply_final_svg_compaction(updated_svg)
        svg_path.write_text(updated_svg, encoding="utf-8")
        save_svg_screenshot(svg_path, screenshot_path)
        current_svg = updated_svg
        current_issues = check_svg(current_svg)

        if current_issues:
            compacted_svg = _apply_issue_aware_svg_fixes(current_svg, current_issues)
            compacted_svg = _apply_final_svg_compaction(compacted_svg)
            if compacted_svg != current_svg:
                svg_path.write_text(compacted_svg, encoding="utf-8")
                save_svg_screenshot(svg_path, screenshot_path)
                current_svg = compacted_svg
                current_issues = check_svg(current_svg)

        if not current_issues:
            current_review["result"] = "PASS"
            current_review["reasons"] = ["根据审查建议重生成后，页面已通过 SVG 技术校验。"]
            current_review["suggestions"] = ["无需继续修改"]
            current_review["raw"] = "RESULT: PASS\nREASONS:\n- 根据审查建议重生成后，页面已通过 SVG 技术校验。\nSUGGESTIONS:\n- 无需继续修改"
            break

    review_result.update(current_review or {})
    if current_issues:
        compacted_svg = _apply_final_svg_compaction(current_svg)
        if compacted_svg != current_svg:
            svg_path.write_text(compacted_svg, encoding="utf-8")
            save_svg_screenshot(svg_path, screenshot_path)
            current_svg = compacted_svg
            current_issues = check_svg(current_svg)
    review_path = _write_review_artifact(review_dir, page_index, svg_path.name, review_result)
    review_result["review_path"] = str(review_path)
    review_result["post_fix_validation_status"] = _classify_svg_validation(current_issues, review_result)
    review_result["post_fix_final_issues"] = len(current_issues)
    return review_result


def run_pipeline(topic: str, audience: str = "通用受众",
                 page_req: str = "12-15页", provider: str | None = None,
                 research: str = "", polish: bool = False,
                 max_pages: int | None = None) -> Path:
    client = AIClient(provider)
    review_client = None
    if SVG_REVIEW_ENABLED:
        review_client = AIClient(SVG_REVIEW_PROVIDER)
        if SVG_REVIEW_MODEL:
            review_client.model = SVG_REVIEW_MODEL
    out = Path(OUTPUT_DIR) / topic.replace(" ", "_")
    out.mkdir(parents=True, exist_ok=True)
    slide_status = {}

    print("[1/4] 生成大纲...")
    outline = step1_outline(client, topic, audience, page_req, research)
    (out / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[2/4] 扩写内容...")
    contents = step2_content(client, outline)
    (out / "contents.json").write_text(
        json.dumps(contents, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[3/4] 生成策划稿 + SVG...")
    svg_dir = out / "svg"
    svg_dir.mkdir(exist_ok=True)
    review_dir = out / "reviews"
    review_dir.mkdir(exist_ok=True)
    for old_svg in svg_dir.glob("*.svg"):
        old_svg.unlink()
    for old_review in review_dir.glob("*"):
        if old_review.is_file():
            old_review.unlink()
    all_pages = _get_pages(outline)
    if max_pages and max_pages > 0:
        all_pages = all_pages[:max_pages]
    total_pages = len(all_pages)
    idx = 1
    for page in all_pages:
        title = _get_title(page)
        material = contents.get(title, "")
        plan = step3_plan(client, title, material)
        page_role = _infer_page_role(idx, total_pages, title, plan, material)
        svg = step4_svg(client, title, material, plan, audience, page_role)
        svg_path = svg_dir / f"{idx:02d}_{title[:20]}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        svg, validation_issues = _validate_and_optionally_regenerate_svg(
            client, svg_path, title, material, plan, audience, page_role, polish
        )
        review_result = _review_and_optionally_fix_svg(
            client, review_client, svg_path, idx, title, material, plan, audience, page_role, validation_issues
        )
        final_validation_status = review_result.get("post_fix_validation_status", _classify_svg_validation(validation_issues, review_result))
        final_issues_count = review_result.get("post_fix_final_issues", len(validation_issues))
        export_ready = final_validation_status in {"pass", "compact_pass"} and review_result.get("result") != "REVISE"
        slide_status[f"{idx:02d}"] = {
            "title": title,
            "page_role": page_role,
            "validation_status": final_validation_status,
            "final_issues_count": final_issues_count,
            "review_status": review_result.get("result"),
            "review_rounds": review_result.get("review_rounds", 0),
            "review_path": review_result.get("review_path"),
            "export_ready": export_ready,
        }
        from pptx_builder import write_slide_status
        write_slide_status(out, slide_status)
        idx += 1

    print("[4/4] 合成 PPT...")
    from pptx_builder import build_pptx
    pptx_path = out / f"{topic[:30]}.pptx"
    build_pptx(svg_dir, pptx_path)
    print(f"完成！PPT 已保存：{pptx_path}")
    return out
