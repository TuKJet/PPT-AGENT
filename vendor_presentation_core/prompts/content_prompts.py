"""
PPT内容生成和增强相关提示词
包含所有用于生成和优化PPT内容的提示词模板
"""

from typing import Dict, Any, List


class ContentPrompts:
    """PPT内容生成和增强相关的提示词集合"""
    
    @staticmethod
    def get_slide_content_prompt_zh(slide_title: str, scenario: str, topic: str) -> str:
        """获取中文幻灯片内容生成提示词"""
        return f"""为PPT幻灯片生成内容：

PPT主题：{topic}
幻灯片标题：{slide_title}
场景类型：{scenario}

请生成这张幻灯片的具体内容，包括：
- 3-5个要点
- 每个要点的简短说明
- 适合{scenario}场景的语言风格

内容要求：
- 简洁明了，适合幻灯片展示
- 逻辑清晰，层次分明
- 语言专业但易懂
- 符合中文表达习惯

请直接输出内容，不需要额外说明。"""

    @staticmethod
    def get_slide_content_prompt_en(slide_title: str, scenario: str, topic: str) -> str:
        """获取英文幻灯片内容生成提示词"""
        return f"""Generate content for a PPT slide:

PPT Topic: {topic}
Slide Title: {slide_title}
Scenario: {scenario}

Please generate specific content for this slide, including:
- 3-5 key points
- Brief explanation for each point
- Language style appropriate for {scenario} scenario

Content requirements:
- Concise and suitable for slide presentation
- Clear logic and structure
- Professional but understandable language
- Appropriate for the target audience

Please output the content directly without additional explanations."""

    @staticmethod
    def get_enhancement_prompt_zh(content: str, scenario: str) -> str:
        """获取中文内容增强提示词"""
        return f"""请优化以下PPT内容，使其更适合{scenario}场景：

原始内容：
{content}

优化要求：
- 保持原有信息的完整性
- 改善语言表达和逻辑结构
- 增加适合{scenario}场景的专业术语
- 使内容更具吸引力和说服力
- 保持简洁明了的风格

请输出优化后的内容："""

    @staticmethod
    def get_enhancement_prompt_en(content: str, scenario: str) -> str:
        """获取英文内容增强提示词"""
        return f"""Please enhance the following PPT content to make it more suitable for {scenario} scenario:

Original content:
{content}

Enhancement requirements:
- Maintain the completeness of original information
- Improve language expression and logical structure
- Add professional terminology suitable for {scenario} scenario
- Make content more attractive and persuasive
- Keep concise and clear style

Please output the enhanced content:"""

    @staticmethod
    def get_ppt_creation_context(topic: str, stage_type: str, focus_content: List[str],
                               tech_highlights: List[str], target_audience: str, description: str) -> str:
        """获取PPT创建上下文提示词"""
        focus_content_str = ', '.join(focus_content) if focus_content else '无'
        tech_highlights_str = ', '.join(tech_highlights) if tech_highlights else '无'
        
        return f"""请为以下项目生成PPT页面：

项目信息：
- 主题：{topic}
- 类型：{stage_type}
- 重点展示内容：{focus_content_str}
- 技术亮点：{tech_highlights_str}
- 目标受众：{target_audience}
- 其他说明：{description or '无'}

请根据大纲内容生成专业的HTML PPT页面，确保设计风格统一，内容表达清晰。"""

    @staticmethod
    def get_general_stage_prompt(topic: str, stage_type: str, description: str) -> str:
        """获取通用阶段任务提示词"""
        return f"""项目信息：
- 主题：{topic}
- 类型：{stage_type}
- 其他说明：{description or '无'}

当前阶段：{stage_type}

请根据以上信息完成当前阶段的任务。"""

    @staticmethod
    def get_general_subtask_context(topic: str, stage_type: str, focus_content: List[str],
                                  tech_highlights: List[str], target_audience: str, 
                                  description: str, subtask: str) -> str:
        """获取通用子任务上下文提示词"""
        focus_content_str = ', '.join(focus_content) if focus_content else '无'
        tech_highlights_str = ', '.join(tech_highlights) if tech_highlights else '无'
        
        return f"""项目信息：
- 主题：{topic}
- 类型：{stage_type}
- 重点展示内容：{focus_content_str}
- 技术亮点：{tech_highlights_str}
- 目标受众：{target_audience}
- 其他说明：{description or '无'}

当前子任务：{subtask}

请根据以上信息完成当前子任务。"""

    @staticmethod
    def get_general_subtask_prompt(confirmed_requirements: Dict[str, Any], stage_name: str, subtask: str) -> str:
        """获取通用子任务提示词"""
        return f"""项目信息：
- 主题：{confirmed_requirements['topic']}
- 类型：{confirmed_requirements['type']}
- 重点展示内容：{confirmed_requirements['focus_content']}
- 技术亮点：{confirmed_requirements['tech_highlights']}
- 目标受众：{confirmed_requirements['target_audience']}
- 其他说明：{confirmed_requirements.get('description', '无')}

当前阶段：{stage_name}
当前子任务：{subtask}

请根据以上信息执行当前子任务。
"""
