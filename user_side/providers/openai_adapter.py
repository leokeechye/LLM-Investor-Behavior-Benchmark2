"""OpenAI (and OpenAI-compatible) chat completions adapter."""
from __future__ import annotations

from .base import ProviderAdapter


class OpenAIAdapter(ProviderAdapter):
    """Uses the official `openai` SDK against the OpenAI Chat Completions API.

    `base_url` lets subclasses point the same client at OpenAI-compatible
    endpoints (e.g. DeepSeek) without duplicating request logic.
    """

    api_key_env = "OPENAI_API_KEY"
    base_url: str | None = None

    def __init__(self, model_id: str, **kwargs):
        super().__init__(model_id, **kwargs)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            key = self._require_key()
            self._client = (
                OpenAI(api_key=key, base_url=self.base_url)
                if self.base_url
                else OpenAI(api_key=key)
            )
        return self._client

    def generate(self, prompt: str) -> str:
        response = self._get_client().chat.completions.create(
            model=self.model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        if not response.choices:
            raise RuntimeError(f"No choices returned from {type(self).__name__} ({self.model_id}).")

        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError(f"Output from {type(self).__name__} ({self.model_id}) was None.")
        return content
