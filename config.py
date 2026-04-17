import os
from dotenv import load_dotenv

load_dotenv(override=True)

# 默认使用的 provider
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "openai")

# 支持的 AI Provider 配置
PROVIDERS = {
    "openai": {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o"),
        "reasoning_effort": os.getenv("OPENAI_REASONING_EFFORT", "high"),
    },
    "claude": {
        "api_key": os.getenv("CLAUDE_API_KEY", ""),
        "base_url": "https://api.anthropic.com/v1",
        "model": os.getenv("CLAUDE_MODEL", "claude-opus-4-6"),
    },
    "domestic": {
        "api_key": os.getenv("DOMESTIC_API_KEY", ""),
        "base_url": os.getenv("DOMESTIC_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "model": os.getenv("DOMESTIC_MODEL", "qwen-plus"),
    },
}

REVIEW_PROVIDER = os.getenv("REVIEW_PROVIDER", DEFAULT_PROVIDER)
REVIEW_MODEL = os.getenv("REVIEW_MODEL", "")
REVIEW_REASONING_EFFORT = os.getenv("REVIEW_REASONING_EFFORT", "low")
REVIEW_ENABLED = os.getenv("HTML_AI_REVIEW_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

SVG_REVIEW_ENABLED = os.getenv(
    "SVG_AI_REVIEW_ENABLED",
    "true" if REVIEW_ENABLED else "false",
).lower() in {"1", "true", "yes", "on"}
SVG_REVIEW_PROVIDER = os.getenv("SVG_REVIEW_PROVIDER", REVIEW_PROVIDER)
SVG_REVIEW_MODEL = os.getenv("SVG_REVIEW_MODEL", REVIEW_MODEL)
SVG_REVIEW_REASONING_EFFORT = os.getenv("SVG_REVIEW_REASONING_EFFORT", REVIEW_REASONING_EFFORT)

# 输出目录
HTML_USE_MIGRATED_CORE = os.getenv("HTML_USE_MIGRATED_CORE", "true").lower() in {"1", "true", "yes", "on"}
EDITABLE_EXPORT_ENGINE = os.getenv("EDITABLE_EXPORT_ENGINE", "dom_export")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
