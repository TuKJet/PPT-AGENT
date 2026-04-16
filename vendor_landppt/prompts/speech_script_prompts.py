"""
Speech Script Generation Prompts
Contains all prompt templates for generating speech scripts from PPT slides
"""

from typing import Dict, Any, List
from ..speech_script_service import SpeechTone, TargetAudience, LanguageComplexity


class SpeechScriptPrompts:
    """Speech script generation prompt templates"""
    
    @staticmethod
    def get_single_slide_script_prompt(
        slide_data: Dict[str, Any],
        slide_index: int,
        total_slides: int,
        project_info: Dict[str, Any],
        previous_slide_context: str,
        customization: Dict[str, Any]
    ) -> str:
        """Generate prompt for single slide speech script"""
        
        slide_title = slide_data.get('title', f'第{slide_index + 1}页')
        slide_content = slide_data.get('html_content', '')
        
        # Extract text content from HTML
        import re
        text_content = re.sub(r'<[^>]+>', '', slide_content)
        text_content = re.sub(r'\s+', ' ', text_content).strip()
        
        # Build context information
        context_info = f"""
项目信息：
- 演示主题：{project_info.get('topic', '')}
- 应用场景：{project_info.get('scenario', '')}
- 目标受众：{customization.get('target_audience', 'general_public')}
- 语言风格：{customization.get('tone', 'conversational')}
- 语言复杂度：{customization.get('language_complexity', 'moderate')}

当前幻灯片信息：
- 幻灯片标题：{slide_title}
- 幻灯片位置：第{slide_index + 1}页，共{total_slides}页
- 幻灯片内容：{text_content}
"""
        
        if previous_slide_context:
            context_info += f"\n上一页内容概要：{previous_slide_context}"
        
        if customization.get('custom_style_prompt'):
            context_info += f"\n自定义风格要求：{customization['custom_style_prompt']}"
        
        # Get tone and audience descriptions
        tone_desc = SpeechScriptPrompts._get_tone_description(customization.get('tone', 'conversational'))
        audience_desc = SpeechScriptPrompts._get_audience_description(customization.get('target_audience', 'general_public'))
        complexity_desc = SpeechScriptPrompts._get_complexity_description(customization.get('language_complexity', 'moderate'))
        
        # Create the main prompt
        prompt = f"""你是一位专业的演讲稿撰写专家。请为以下PPT幻灯片生成一份自然流畅的演讲稿。

{context_info}

演讲稿要求：
1. 语调风格：{tone_desc}
2. 目标受众：{audience_desc}
3. 语言复杂度：{complexity_desc}
4. 包含过渡语句：{'是' if customization.get('include_transitions', True) else '否'}
5. 演讲节奏：{customization.get('speaking_pace', 'normal')}

生成要求：
- 内容要与幻灯片内容紧密相关，但不要简单重复
- 使用自然的口语化表达，适合现场演讲
- 如果需要过渡，请自然地连接上一页的内容
- 控制篇幅，确保演讲时长适中（建议1-3分钟）
- 语言要符合指定的风格和受众特点
- 可以适当添加例子、类比或互动元素来增强效果

请直接输出演讲稿内容，不需要额外的格式说明或标题。"""
        
        return prompt
    
    @staticmethod
    def get_opening_remarks_prompt(
        project_info: Dict[str, Any],
        customization: Dict[str, Any]
    ) -> str:
        """Generate prompt for opening remarks"""
        
        tone_desc = SpeechScriptPrompts._get_tone_description(customization.get('tone', 'conversational'))
        audience_desc = SpeechScriptPrompts._get_audience_description(customization.get('target_audience', 'general_public'))
        
        prompt = f"""请为以下演示生成一段精彩的开场白：

演示信息：
- 主题：{project_info.get('topic', '')}
- 场景：{project_info.get('scenario', '')}
- 目标受众：{customization.get('target_audience', 'general_public')}
- 语言风格：{customization.get('tone', 'conversational')}

开场白要求：
1. 语调风格：{tone_desc}
2. 目标受众：{audience_desc}
3. 时长控制在1-2分钟
4. 能够吸引听众注意力
5. 简要介绍演示主题和价值
6. 与听众建立连接
7. 为后续内容做好铺垫

生成要求：
- 使用自然的口语化表达
- 可以包含问候语、自我介绍（如需要）
- 可以使用引人入胜的开场方式（问题、故事、数据等）
- 要体现演讲者的专业性和亲和力
- 语言要符合指定的风格和受众特点

请直接输出开场白内容，使用自然流畅的演讲语言。"""
        
        return prompt
    
    @staticmethod
    def get_closing_remarks_prompt(
        project_info: Dict[str, Any],
        customization: Dict[str, Any]
    ) -> str:
        """Generate prompt for closing remarks"""
        
        tone_desc = SpeechScriptPrompts._get_tone_description(customization.get('tone', 'conversational'))
        audience_desc = SpeechScriptPrompts._get_audience_description(customization.get('target_audience', 'general_public'))
        
        prompt = f"""请为以下演示生成一段有力的结束语：

演示信息：
- 主题：{project_info.get('topic', '')}
- 场景：{project_info.get('scenario', '')}
- 目标受众：{customization.get('target_audience', 'general_public')}
- 语言风格：{customization.get('tone', 'conversational')}

结束语要求：
1. 语调风格：{tone_desc}
2. 目标受众：{audience_desc}
3. 时长控制在1-2分钟
4. 总结演示的核心要点
5. 强化主要信息和价值
6. 给听众留下深刻印象
7. 包含行动号召或下一步建议
8. 以积极正面的语调结束

生成要求：
- 使用自然的口语化表达
- 可以回顾关键要点，但要简洁
- 可以包含感谢语和互动邀请
- 要给听众明确的下一步指引
- 语言要符合指定的风格和受众特点
- 结尾要有力量感和感召力

请直接输出结束语内容，使用自然流畅的演讲语言。"""
        
        return prompt
    
    @staticmethod
    def get_transition_enhancement_prompt(
        current_script: str,
        previous_slide_context: str,
        next_slide_context: str
    ) -> str:
        """Generate prompt for enhancing transitions between slides"""
        
        prompt = f"""请为以下演讲稿添加自然的过渡语句，使其与前后内容更好地连接：

当前演讲稿：
{current_script}

上一页内容概要：
{previous_slide_context}

下一页内容概要：
{next_slide_context}

过渡要求：
1. 在演讲稿开头添加自然的过渡语句，连接上一页内容
2. 在演讲稿结尾添加引导语句，为下一页内容做铺垫
3. 过渡要自然流畅，不显突兀
4. 保持原有演讲稿的核心内容不变
5. 使用口语化的表达方式

请输出增强过渡后的完整演讲稿。"""
        
        return prompt
    
    @staticmethod
    def _get_tone_description(tone: str) -> str:
        """Get description for speech tone"""
        descriptions = {
            'formal': "正式、严谨、专业的商务语调",
            'casual': "轻松、自然、亲切的日常语调",
            'persuasive': "有说服力、激励性的语调",
            'educational': "教学式、解释性的语调",
            'conversational': "对话式、互动性的语调",
            'authoritative': "权威、自信、专家式的语调",
            'storytelling': "叙事性、生动有趣的语调"
        }
        return descriptions.get(tone, "自然流畅的语调")
    
    @staticmethod
    def _get_audience_description(audience: str) -> str:
        """Get description for target audience"""
        descriptions = {
            'executives': "企业高管和决策者，注重效率和结果",
            'students': "学生群体，需要清晰的解释和引导",
            'general_public': "普通大众，使用通俗易懂的语言",
            'technical_experts': "技术专家，可以使用专业术语",
            'colleagues': "同事和合作伙伴，平等交流的语调",
            'clients': "客户群体，注重价值和利益",
            'investors': "投资者，关注商业价值和回报"
        }
        return descriptions.get(audience, "一般听众")
    
    @staticmethod
    def _get_complexity_description(complexity: str) -> str:
        """Get description for language complexity"""
        descriptions = {
            'simple': "简单易懂，避免复杂词汇和长句",
            'moderate': "适中复杂度，平衡专业性和可理解性",
            'advanced': "较高复杂度，可以使用专业术语和复杂概念"
        }
        return descriptions.get(complexity, "适中复杂度")
    
    @staticmethod
    def get_script_refinement_prompt(
        original_script: str,
        refinement_request: str,
        customization: Dict[str, Any]
    ) -> str:
        """Generate prompt for refining existing speech script"""
        
        tone_desc = SpeechScriptPrompts._get_tone_description(customization.get('tone', 'conversational'))
        audience_desc = SpeechScriptPrompts._get_audience_description(customization.get('target_audience', 'general_public'))
        
        prompt = f"""请根据用户要求优化以下演讲稿：

原始演讲稿：
{original_script}

用户优化要求：
{refinement_request}

当前设置：
- 语调风格：{tone_desc}
- 目标受众：{audience_desc}
- 语言复杂度：{SpeechScriptPrompts._get_complexity_description(customization.get('language_complexity', 'moderate'))}

优化要求：
1. 保持演讲稿的核心信息和结构
2. 根据用户要求进行针对性调整
3. 确保语言风格与设置保持一致
4. 使用自然的口语化表达
5. 保持适当的演讲时长

请输出优化后的演讲稿。"""
        
        return prompt
