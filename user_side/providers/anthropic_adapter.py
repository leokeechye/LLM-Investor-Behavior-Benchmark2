"""Anthropic (Claude) adapter using the native `anthropic` SDK."""
from __future__ import annotations

from .base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):
    api_key_env = "ANTHROPIC_API_KEY"

    def __init__(self, model_id: str, **kwargs):
        super().__init__(model_id, **kwargs)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._require_key())
        return self._client

    def generate(self, prompt: str) -> str:
        # Anthropic requires an explicit max_tokens; the weekly deep-research
        # report can be long, so max_tokens defaults high (see ProviderAdapter).
        #
        # Notes on newer Claude models (e.g. claude-sonnet-5):
        #   - `temperature` is rejected (400) — do not send it.
        #   - thinking is disabled here so the whole token budget goes to the
        #     report and the call stays a cheap, deterministic completion like
        #     the other providers. (`{"type": "disabled"}` is accepted on
        #     Sonnet 5 / Opus 4.x; note it 400s on Fable 5 — omit thinking there.)
        response = self._get_client().messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        if not text:
            raise RuntimeError(f"Output from AnthropicAdapter ({self.model_id}) was empty.")
        return text
