"""Provider adapter parity tests (network-free).

Confirms every registered model resolves to the right adapter and that all
adapters share the common interface. Live end-to-end auth is covered separately
by the manual smoke test, not here.
"""
import pytest

from user_side.providers.base import ProviderAdapter
from user_side.providers.registry import (
    _PROVIDERS,
    get_adapter,
    load_registry,
)

EXPECTED = {
    "gpt-4.1": ("openai", "OpenAIAdapter", "OPENAI_API_KEY"),
    "deepseek": ("deepseek", "DeepSeekAdapter", "DEEPSEEK_API_KEY"),
    "claude": ("anthropic", "AnthropicAdapter", "ANTHROPIC_API_KEY"),
    "gemini": ("google", "GeminiAdapter", "GEMINI_API_KEY"),
}


def test_registry_has_expected_models():
    reg = load_registry()
    assert set(reg) == set(EXPECTED)


@pytest.mark.parametrize("name,expected", EXPECTED.items())
def test_adapter_resolution_and_parity(name, expected):
    provider, cls_name, key_env = expected
    reg = load_registry()
    assert reg[name].provider == provider

    adapter = get_adapter(name)
    # right class, common interface, correct key env
    assert type(adapter).__name__ == cls_name
    assert isinstance(adapter, ProviderAdapter)
    assert callable(adapter.generate)
    assert adapter.api_key_env == key_env
    assert adapter.model_id == reg[name].model_id


def test_every_provider_class_shares_interface():
    for cls in _PROVIDERS.values():
        assert issubclass(cls, ProviderAdapter)


def test_missing_key_raises_friendly_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = get_adapter("claude")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        adapter._require_key()


def test_unknown_model_raises():
    with pytest.raises(KeyError):
        get_adapter("no-such-model")
