"""Build a prompt for a run and dispatch it to the model's provider adapter.

The model is identified by the run directory name (the last path segment of the
LIBBmodel root), which must match a `name` in config/models.yaml.
"""
from ..prompts.deep_research_prompt import create_deep_research_prompt
from ..prompts.daily_research_prompt import create_daily_prompt
from ..providers.registry import generate


def _model_name(libb) -> str:
    """Registry name for this run — the last segment of the model root path."""
    return libb._root.name


def prompt_deep_research(libb) -> str:
    return generate(_model_name(libb), create_deep_research_prompt(libb))


def prompt_daily_report(libb) -> str:
    return generate(_model_name(libb), create_daily_prompt(libb))
