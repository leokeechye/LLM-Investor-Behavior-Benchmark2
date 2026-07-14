"""Google Gemini adapter using the native `google-genai` SDK."""
from __future__ import annotations

from .base import ProviderAdapter


class GeminiAdapter(ProviderAdapter):
    api_key_env = "GEMINI_API_KEY"

    def __init__(self, model_id: str, **kwargs):
        super().__init__(model_id, **kwargs)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._require_key())
        return self._client

    def generate(self, prompt: str) -> str:
        from google.genai import types

        response = self._get_client().models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
            ),
        )
        text = response.text
        if not text:
            raise RuntimeError(f"Output from GeminiAdapter ({self.model_id}) was empty.")
        return text
