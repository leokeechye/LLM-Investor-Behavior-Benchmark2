"""DeepSeek adapter.

DeepSeek serves an OpenAI-compatible API, so this reuses OpenAIAdapter's request
logic and only overrides the key/base URL.
"""
from __future__ import annotations

from .openai_adapter import OpenAIAdapter


class DeepSeekAdapter(OpenAIAdapter):
    api_key_env = "DEEPSEEK_API_KEY"
    base_url = "https://api.deepseek.com"
