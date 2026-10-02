"""AI engine: LLM, local fallback, tools, handoff."""

from .engine import reply
from .config_bridge import ai_settings

__all__ = ["reply", "ai_settings"]
