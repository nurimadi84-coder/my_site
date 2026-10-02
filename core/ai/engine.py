"""Оркестрация ответа ИИ: LLM + handoff. Без LLM ответа нет — AIUnavailableError."""

from __future__ import annotations

import logging

from core.config import ai_settings

from . import health
from .catalog import CatalogTool, catalog_text
from .handoff import (
    HANDOFF_MARKERS,
    HandoffTool,
    build_wa_text,
    should_handoff,
    user_ready_for_handoff,
)
from .llm import call_llm
from .local import AttachmentTool
from .tools import ToolRegistry

log = logging.getLogger("ai")


class AIUnavailableError(RuntimeError):
    def __init__(self, status: str, wa_text: str = ""):
        super().__init__(f"ИИ недоступен: {status}")
        self.status = status
        self.configured = status != "no_key"
        self.wa_text = wa_text

_default_tools = ToolRegistry()
_default_tools.register(CatalogTool())
_default_tools.register(HandoffTool())
_default_tools.register(AttachmentTool())


def reply(
    message: str,
    history: list,
    products: list,
    config: dict,
    attachments: list | None = None,
    tools: ToolRegistry | None = None,
) -> dict:
    registry = tools or _default_tools
    files = attachments or []
    text = str(message or "").strip()[:1200]
    if len(text) < 1 and not files:
        return {
            "reply": "Напишите вопрос или прикрепите фото/файл — подскажу и при необходимости переведу к мастеру.",
            "whatsapp": False,
        }
    if len(text) < 1 and files:
        names = ", ".join(item.get("name") or "файл" for item in files[:3])
        text = f"Просмотрите приложенный файл ({names}) и прокомментируйте содержимое."

    settings = ai_settings(config)
    turns = list(history or [])
    turns.append({"role": "user", "content": text})

    system_extra = registry.build_context(products, history)
    if not system_extra:
        system_extra = catalog_text(products)

    llm, status = call_llm(settings, turns, system_extra, files)
    health.record(status)
    if not llm:
        if status == "no_key":
            log.error("ИИ не настроен: AI_API_KEY пуст")
        raise AIUnavailableError(status, build_wa_text(history, text))

    handoff = should_handoff(text, history, llm) or bool(files) or user_ready_for_handoff(text, history)
    if handoff and not any(mark in llm.lower() for mark in HANDOFF_MARKERS):
        llm = llm.rstrip() + "\n\nНажмите кнопку ниже — открою чат с мастером и передам вашу задачу."
    result = {
        "reply": llm[:2000],
        "whatsapp": handoff,
        "mode": "llm",
    }
    if handoff:
        result["wa_text"] = build_wa_text(history, text)
        result["cta"] = "Связаться с мастером"
    return result
