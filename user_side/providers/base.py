"""Common provider interface.

Every provider adapter exposes the same `generate(prompt) -> str` method so the
rest of the app can talk to any model without knowing which SDK backs it. The
model registry (`config/models.yaml`) maps a model `name` to a `ModelSpec`, and
`registry.get_adapter` constructs the right adapter from it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
import os


@dataclass(frozen=True)
class ModelSpec:
    """One row of the model registry."""
    name: str
    provider: str
    model_id: str
    training_cutoff: date | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "ModelSpec":
        for key in ("name", "provider", "model_id"):
            if not raw.get(key):
                raise ValueError(f"Model registry entry missing required '{key}': {raw!r}")
        return cls(
            name=str(raw["name"]),
            provider=str(raw["provider"]),
            model_id=str(raw["model_id"]),
            training_cutoff=_coerce_date(raw.get("training_cutoff")),
        )


def _coerce_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


class ProviderAdapter(ABC):
    """Base class for a single provider behind a shared interface.

    Adapters are cheap to construct and lazily create their SDK client on first
    use, so importing the package never requires an SDK or an API key to be
    present unless that provider is actually called.
    """

    #: Environment variable holding this provider's API key.
    api_key_env: str = ""

    def __init__(self, model_id: str, *, temperature: float = 0.0, max_tokens: int = 8192):
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _require_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(
                f"{type(self).__name__} requires the '{self.api_key_env}' environment "
                "variable (set it in your shell or a gitignored .env file)."
            )
        return key

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send `prompt` to the model and return its text response."""
        raise NotImplementedError
