"""Provider adapters behind a common `generate()` interface.

Importing this package best-effort loads a `.env` file (if `python-dotenv` is
installed) so API keys defined there are available to the adapters.
"""
from __future__ import annotations

try:  # optional: .env support without a hard dependency
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .base import ModelSpec, ProviderAdapter
from .registry import generate, get_adapter, get_spec, load_registry

__all__ = [
    "ModelSpec",
    "ProviderAdapter",
    "generate",
    "get_adapter",
    "get_spec",
    "load_registry",
]
