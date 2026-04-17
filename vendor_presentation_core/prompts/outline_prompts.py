"""
PPT大纲生成相关提示词
包含所有用于生成PPT大纲的提示词模板
"""

from typing import Dict, Any, List


class OutlinePrompts:
    """PPT大纲生成相关的提示词集合"""
    
    @staticmethod
    def get_outline_prompt_zh(topic: str, scenario_desc: str, target_audience: str, 
                             style_desc: str, requirements: str, description: str,
                             research_section: str, page_count_instruction: str,
                             expected_page_count: int, language: str) -> str:
        """获取中文大纲生成提示词"""
        return f"""你是一位专业的PPT大纲策划专家，请基于以下项目信息，生成一个**结构清晰、内容创意、专业严谨、格式规范的JSON格式PPT大纲**。

### 📌【项目信息】：
- **主题**：{topic}
- **应用场景**：{scenario_desc}
- **目标受众**：{target_audience}
- **PPT风格**：{style_desc}
- **特殊要求**：{requirements or '无'}
- **补充说明**：{description or '无'}
{research_section}

### 📄【页数要求】：
{page_count_instruction}

---

### 📋【大纲生成规则】：

1. **内容契合度要求**：
   - 所有幻灯片内容必须与上述项目信息严格匹配，确保主题明确、风格统一、内容相关。
   - 信息表达要专业可信，同时具有吸引力与传播力。

2. **页面结构规范**：
   - 必须包含以下结构：封面页、目录页、内容页（若干）、结论页。
   - 内容页应合理分层，逻辑清晰；封面和结论页需具备视觉冲击力或独特设计说明。

3. **内容点控制**：
   - 每页控制在3～6个内容要点之间。
   - 每个要点内容简洁清晰，可做适当解释，但**不超过50字符**。
   - 内容分布需均衡，避免信息堆积或重复。

4. **图表展示优化**：
   - 对适合可视化的信息，**建议并提供图表配置**，写入 `chart_config` 字段中。
   - 图表需明确类型（如柱状图、折线图、饼图、甘特图、森林图、韦恩图、upset图、生存曲线图、漏斗图、环形图、和弦图、词云图、关联图、瀑布图、条形图、面积图等）、说明含义、配置样式及数据结构。

5. **语言风格与语境一致性**：
   - 使用统一语言（{language}），保持语境一致，适合目标受众理解与接受。

---

### 🧾【输出格式要求】：

请严格使用如下JSON格式进行输出，**使用代码块包裹，内容必须有效且结构完整**：

```json
{{
  "title": "专业且吸引人的PPT标题",
  "total_pages": {expected_page_count},
  "page_count_mode": "final",
  "slides": [
    {{
      "page_number": 1,
      "title": "页面标题",
      "content_points": ["要点1", "要点2", "要点3"],
      "slide_type": "title/content/conclusion",
      "type": "content",
      "description": "此页的简要说明与目的",
      "chart_config": {{
        "type": "bar",
        "data": {{
          "labels": ["示例A", "示例B", "示例C"],
          "datasets": [{{
            "label": "数据说明",
            "data": [80, 95, 70],
            "backgroundColor": ["#FF6B6B", "#4ECDC4", "#FFD93D"],
            "borderColor": ["#FF5252", "#26A69A", "#F4A261"],
            "borderWidth": 2
          }}]
        }},
        "options": {{
          "responsive": true,
          "plugins": {{
            "legend": {{"position": "top"}},
            "title": {{"display": true, "text": "图表标题"}}
          }},
          "scales": {{"y": {{"beginAtZero": true}}}}
        }}
      }}
    }}
  ],
  "metadata": {{
    "scenario": "{scenario_desc}",
    "language": "{language}",
    "total_slides": {expected_page_count},
    "generated_with_ai": true,
    "enhanced_with_charts": true,
    "content_depth": "professional"
  }}
}}
```"""

    @staticmethod
    def get_outline_prompt_en(topic: str, scenario_desc: str, target_audience: str,
                             style_desc: str, requirements: str, description: str,
                             research_section: str, page_count_instruction: str,
                             expected_page_count: int, language: str) -> str:
        """获取英文大纲生成提示词"""
        return f"""You are a **professional presentation outline designer**. Based on the following project details, please generate a **well-structured, creative, and professional JSON-format PowerPoint outline**.

### 📌【Project Details】:
- **Topic**: {topic}
- **Scenario**: {scenario_desc}
- **Target Audience**: {target_audience}
- **PPT Style**: {style_desc}
- **Special Requirements**: {requirements or 'None'}
- **Additional Notes**: {description or 'None'}
{research_section}

**Page Count Requirements:**
{page_count_instruction}

---

### 📋【Outline Generation Rules】:

1. **Content Relevance**:
   - All slide content must strictly align with the project details above.
   - Ensure the theme is clear, the tone is consistent, and the message is well-targeted.

2. **Slide Structure**:
   - The deck must include: **Title Slide**, **Agenda Slide**, **Content Slides**, and **Conclusion Slide**.
   - Title and Conclusion slides should be visually distinct or offer special design instructions.
   - Content slides must follow a logical and clear structure.

3. **Content Density Control**:
   - Each slide must contain **3–6 concise bullet points**.
   - Each point should be **no more than 50 characters**.
   - Distribute content evenly across slides to avoid overload or redundancy.

4. **Chart Suggestions**:
   - For any data, comparisons, or visual-friendly content, suggest a chart and include its configuration under `chart_config`.
   - Specify chart type (e.g., bar, pie, line), provide sample data, and chart options.

5. **Language & Tone**:
   - The entire outline should be in **{language}** and aligned with the communication preferences of the target audience.

---

### 🧾【Required Output Format】:

Please follow the exact JSON format below, and **wrap the result in a code block**. The JSON must be valid and complete.

```json
{{
  "title": "A compelling and professional PPT title",
  "total_pages": {expected_page_count},
  "page_count_mode": "final",
  "slides": [
    {{
      "page_number": 1,
      "title": "Slide Title",
      "content_points": ["Point 1", "Point 2", "Point 3"],
      "slide_type": "title/content/conclusion",
      "type": "content",
      "description": "Brief description of this slide",
      "chart_config": {{
        "type": "bar",
        "data": {{
          "labels": ["Metric A", "Metric B", "Metric C"],
          "datasets": [{{
            "label": "Performance Data",
            "data": [80, 95, 70],
            "backgroundColor": ["#FF6B6B", "#4ECDC4", "#FFD93D"],
            "borderColor": ["#FF5252", "#26A69A", "#F4A261"],
            "borderWidth": 2
          }}]
        }},
        "options": {{
          "responsive": true,
          "plugins": {{
            "legend": {{"position": "top"}},
            "title": {{"display": true, "text": "Chart Title"}}
          }},
          "scales": {{"y": {{"beginAtZero": true}}}}
        }}
      }}
    }}
  ],
  "metadata": {{
    "scenario": "{scenario_desc}",
    "language": "{language}",
    "total_slides": {expected_page_count},
    "generated_with_ai": true,
    "enhanced_with_charts": true,
    "content_depth": "professional"
  }}
}}
```"""

    @staticmethod
    def get_streaming_outline_prompt(topic: str, target_audience: str, ppt_style: str,
                                   page_count_instruction: str, research_section: str) -> str:
        """获取流式大纲生成提示词"""
        return f"""作为专业的PPT大纲生成助手，请为以下项目生成详细的PPT大纲。

项目信息：
- 主题：{topic}
- 目标受众：{target_audience}
- PPT风格：{ppt_style}
{page_count_instruction}{research_section}

请严格按照以下JSON格式生成PPT大纲：

{{
    "title": "PPT标题",
    "slides": [
        {{
            "page_number": 1,
            "title": "页面标题",
            "content_points": ["要点1", "要点2", "要点3"],
            "slide_type": "title"
        }},
        {{
            "page_number": 2,
            "title": "页面标题",
            "content_points": ["要点1", "要点2", "要点3"],
            "slide_type": "content"
        }}
    ]
}}

slide_type可选值：
- "title": 标题页/封面页
- "content": 内容页
- "agenda": 目录页
- "thankyou": 结束页/感谢页

要求：
1. 必须返回有效的JSON格式
2. 严格遵守页数要求
3. 第一页通常是标题页，最后一页是感谢页
4. 每页至少包含2-5个内容要点，可做适当解释
5. 页面标题要简洁明确
6. 内容要点要具体实用
7. 根据重点内容和技术亮点安排页面内容

请只返回JSON，使用```json```代码块包裹，不要包含其他文字说明。

示例格式：
```json
{{
  "title": "PPT标题",
  "slides": [
    {{
      "page_number": 1,
      "title": "页面标题",
      "content_points": ["要点1", "要点2"],
      "slide_type": "title"
    }}
  ]
}}
```"""

    @staticmethod
    def get_outline_generation_context(topic: str, target_audience: str, ppt_style: str,
                                     page_count_instruction: str, focus_content: List[str],
                                     tech_highlights: List[str], description: str) -> str:
        """获取大纲生成上下文提示词"""
        focus_content_str = ', '.join(focus_content) if focus_content else '无'
        tech_highlights_str = ', '.join(tech_highlights) if tech_highlights else '无'
        
        return f"""请为以下项目生成详细的PPT大纲：

项目信息：
- 主题：{topic}
- 目标受众：{target_audience}
- PPT风格：{ppt_style}
- 重点展示内容：{focus_content_str}
- 技术亮点：{tech_highlights_str}
- 其他说明：{description or '无'}
{page_count_instruction}

请生成结构化的PPT大纲，包含每页的标题、内容要点和页面类型。确保内容逻辑清晰，符合目标受众需求。"""

    @staticmethod
    def get_streaming_outline_prompt(topic: str, target_audience: str, ppt_style: str,
                                   page_count_instruction: str, research_section: str) -> str:
        """获取流式大纲生成提示词"""
        prompt = f"""
作为专业的PPT大纲生成助手，请为以下项目生成详细的PPT大纲。

项目信息：
- 主题：{topic}
- 目标受众：{target_audience}
- PPT风格：{ppt_style}
{page_count_instruction}{research_section}

请严格按照以下JSON格式生成PPT大纲：

{{
    "title": "PPT标题",
    "slides": [
        {{
            "page_number": 1,
            "title": "页面标题",
            "content_points": ["要点1", "要点2", "要点3"],
            "slide_type": "title"
        }},
        {{
            "page_number": 2,
            "title": "页面标题",
            "content_points": ["要点1", "要点2", "要点3"],
            "slide_type": "content"
        }}
    ]
}}

slide_type可选值：
- "title": 标题页/封面页
- "content": 内容页
- "agenda": 目录页
- "thankyou": 结束页/感谢页

要求：
1. 必须返回有效的JSON格式
2. 严格遵守页数要求
3. 第一页通常是标题页，最后一页是感谢页
4. 每页至少包含2-5个内容要点，可做适当解释
5. 页面标题要简洁明确
6. 内容要点要具体实用
7. 根据重点内容和技术亮点安排页面内容

请只返回JSON，使用```json```代码块包裹，不要包含其他文字说明。

示例格式：
```json
{{
  "title": "PPT标题",
  "slides": [
    {{
      "page_number": 1,
      "title": "页面标题",
      "content_points": ["要点1", "要点2"],
      "slide_type": "title"
    }}
  ]
}}
```
"""
        return prompt

    @staticmethod
    def get_outline_generation_context(topic: str, target_audience: str, page_count_instruction: str,
                                     ppt_style: str, custom_style: str, description: str,
                                     page_count_mode: str) -> str:
        """获取大纲生成上下文提示词"""
        context = f"""
项目信息：
- 主题：{topic}
- 目标受众：{target_audience}
{page_count_instruction}
- PPT风格：{ppt_style}
- 自定义风格说明：{custom_style}
- 其他说明：{description}

任务：生成完整的PPT大纲

请生成一个详细的PPT大纲，包括：
1. PPT标题
2. 各页面标题和主要内容要点
3. 逻辑结构和流程
4. 每页的内容重点
5. 根据页数要求合理安排内容分布

请以JSON格式返回大纲，使用```json```代码块包裹，格式如下：

```json
{{
    "title": "PPT标题",
    "total_pages": 实际页数,
    "page_count_mode": "{page_count_mode}",
    "slides": [
        {{
            "page_number": 1,
            "title": "页面标题",
            "content_points": ["要点1", "要点2", "要点3"],
            "slide_type": "title|content|conclusion",
            "description": "页面内容描述"
        }}
    ]
}}
```
"""
        return context
