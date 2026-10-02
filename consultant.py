"""
ИИ-консультант Mebel Almaty (совместимый facade).
Реализация живёт в core.ai — этот модуль реэкспортирует публичный API.
"""

from __future__ import annotations

from core.ai.catalog import CURRENCY, catalog_text, money
from core.ai.engine import AIUnavailableError, reply
from core.ai.handoff import (
    HANDOFF_MARKERS,
    INTENT_HANDOFF,
    READY_YES,
    build_wa_text,
    conversation_brief,
    handoff_reply,
    should_handoff,
    user_ready_for_handoff,
    user_turns,
    wants_whatsapp,
)
from core.ai.llm import call_llm as _call_llm
from core.ai.prompt import SYSTEM, system_prompt
from core.config import ai_settings


def call_llm(settings, history, products, attachments=None):
    """Совместимость со старой сигнатурой (settings, history, products, attachments)."""
    return _call_llm(settings, history, catalog_text(products), attachments)


__all__ = [
    "CURRENCY",
    "SYSTEM",
    "system_prompt",
    "AIUnavailableError",
    "money",
    "catalog_text",
    "ai_settings",
    "call_llm",
    "user_turns",
    "conversation_brief",
    "build_wa_text",
    "HANDOFF_MARKERS",
    "INTENT_HANDOFF",
    "READY_YES",
    "wants_whatsapp",
    "should_handoff",
    "user_ready_for_handoff",
    "handoff_reply",
    "reply",
]
