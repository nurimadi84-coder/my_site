"""WhatsApp handoff: маркеры, brief, wa_text."""

from __future__ import annotations

import re

HANDOFF_MARKERS = (
    "кнопк", "whatsapp", "ватсап", "вацап", "мастеру", "мастер ответит",
    "передам", "передаю", "открою чат", "связ", "напишите мастеру",
)

INTENT_HANDOFF = (
    "заказать", "оформить", "купить", "оставить заявку", "вызвать",
    "замер", "замерщик", "выезд", "связаться", "написать", "позвон",
    "whatsapp", "ватсап", "вацап", "менеджер", "мастер", "человек",
    "оператор", "номер", "телефон", "контакт", "хочу заказать",
    "посчитайте", "посчитай", "смету", "договор", "оплат",
)

READY_YES = (
    "да", "давай", "хорошо", "ок", "окей", "согласен", "согласна",
    "можно", "готово", "переводи", "свяжите", "пишите", "звоните",
)


def user_turns(history: list) -> list[str]:
    out = []
    for item in history or []:
        if item.get("role") == "user":
            text = str(item.get("content") or "").strip()
            if text:
                out.append(text)
    return out


def conversation_brief(history: list, latest: str) -> str:
    notes = user_turns(history)
    if latest and (not notes or notes[-1] != latest):
        notes.append(latest)
    notes = [item for item in notes if item][-6:]
    if not notes:
        return "Клиент написал с сайта и просит связаться с мастером."
    if len(notes) == 1:
        return notes[0]
    return " · ".join(notes)


def build_wa_text(history: list, latest: str) -> str:
    brief = conversation_brief(history, latest)
    return (
        "Здравствуйте! Меня направил ИИ-консультант с сайта Mebel Almaty.\n\n"
        f"Запрос клиента:\n{brief}\n\n"
        "Прошу связаться и продолжить консультацию."
    )


def wants_whatsapp(text: str) -> bool:
    low = (text or "").lower()
    return any(word in low for word in INTENT_HANDOFF) or any(word in low for word in HANDOFF_MARKERS)


def user_ready_for_handoff(message: str, history: list) -> bool:
    """Передача по намерению клиента / деталям диалога (без анализа текста ответа)."""
    low = (message or "").lower().strip()
    if any(word in low for word in INTENT_HANDOFF):
        return True
    short_yes = "?" not in low and len(low.split()) <= 4
    if short_yes and (low in READY_YES or any(low.startswith(word + " ") or low == word for word in READY_YES)):
        prior = " ".join(str(item.get("content") or "") for item in (history or [])[-3:]).lower()
        if wants_whatsapp(prior) or any(w in prior for w in ("whatsapp", "мастер", "замер", "смет", "заказ")):
            return True
    detail_keys = ("алмат", "район", "мкр", "улиц", "квартир", "метр", "бюджет", "тенге", "₸")
    product_keys = ("шкаф", "кухн", "кроват", "гардероб", "фасад", "издел")
    joined = " ".join(user_turns(history) + [message]).lower()
    has_size = re.search(r"\d\s*(см|мм|м)\b", joined) is not None
    if any(k in joined for k in product_keys) and (has_size or any(k in joined for k in detail_keys)):
        return True
    if len(user_turns(history)) >= 3 and any(k in joined for k in product_keys):
        return True
    return False


def should_handoff(message: str, history: list, reply_text: str) -> bool:
    reply_low = (reply_text or "").lower()
    if any(mark in reply_low for mark in HANDOFF_MARKERS):
        return True
    return user_ready_for_handoff(message, history)


def handoff_reply(topic: str = "") -> str:
    base = "Передаю вас мастеру Mebel Almaty — он уточнит детали и продолжит в WhatsApp."
    if topic:
        base = f"Понял: {topic}. " + base
    return base + " Нажмите кнопку ниже — открою чат с мастером и передам вашу задачу."


class HandoffTool:
    name = "handoff"
    description = "Передача клиента мастеру в WhatsApp"

    def context(self, products: list, history: list) -> str:
        return ""

    def maybe_act(self, message: str, history: list) -> dict | None:
        if user_ready_for_handoff(message, history):
            return {
                "whatsapp": True,
                "wa_text": build_wa_text(history, message),
                "cta": "Связаться с мастером",
            }
        return None
