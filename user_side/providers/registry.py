"""Model registry: load `config/models.yaml` and build provider adapters.

The YAML is the single source of truth for which models exist, which provider
serves each, and each model's training cutoff (used later to flag lookahead bias
in replay). Callers reference a model by its registry `name`.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .base import ModelSpec, ProviderAdapter
from .openai_adapter import OpenAIAdapter
from .deepseek_adapter import DeepSeekAdapter
from .anthropic_adapter import AnthropicAdapter
from .gemini_adapter import GeminiAdapter

# provider identifier (as written in models.yaml) -> adapter class
_PROVIDERS: dict[str, type[ProviderAdapter]] = {
    "openai": OpenAIAdapter,
    "deepseek": DeepSeekAdapter,
    "anthropic": AnthropicAdapter,
    "google": GeminiAdapter,
}

# repo_root/config/models.yaml  (this file: repo_root/user_side/providers/registry.py)
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "config" / "models.yaml"


@lru_cache(maxsize=None)
def load_registry(path: str | Path | None = None) -> dict[str, ModelSpec]:
    """Parse the registry YAML into `{name: ModelSpec}`. Cached per path."""
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        raise FileNotFoundError(f"Model registry not found at {registry_path}")

    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("models", [])
    if not entries:
        raise ValueError(f"Model registry at {registry_path} has no 'models' entries.")

    registry: dict[str, ModelSpec] = {}
    for entry in entries:
        spec = ModelSpec.from_dict(entry)
        if spec.name in registry:
            raise ValueError(f"Duplicate model name in registry: {spec.name!r}")
        if spec.provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown provider {spec.provider!r} for model {spec.name!r}. "
                f"Known providers: {sorted(_PROVIDERS)}"
            )
        registry[spec.name] = spec
    return registry


def get_spec(name: str, path: str | Path | None = None) -> ModelSpec:
    registry = load_registry(path)
    try:
        return registry[name]
    except KeyError:
        raise KeyError(
            f"Model {name!r} is not in the registry. Available: {sorted(registry)}"
        ) from None


def get_adapter(name: str, path: str | Path | None = None, **adapter_kwargs) -> ProviderAdapter:
    """Construct the adapter for a registered model name."""
    spec = get_spec(name, path)
    return _PROVIDERS[spec.provider](spec.model_id, **adapter_kwargs)


def generate(name: str, prompt: str, path: str | Path | None = None) -> str:
    """Convenience: build the adapter for `name` and run one generation."""
    return get_adapter(name, path).generate(prompt)
