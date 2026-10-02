"""Feature: ИИ-чат."""

from __future__ import annotations

from core.ai.engine import AIUnavailableError, reply
from core.ai.local import AttachmentTool
from core.config import CHAT_RATE_LIMIT, CHAT_RATE_WINDOW, MAX_CHAT_BODY
from core.context import AppContext
from core.http import client_ip, read_json_body, send_json
from core.ratelimit import RateLimiter
from core.router import Router
from core.settings import load_config
from features.catalog.service import load_products

from . import service

CHAT_RATE = RateLimiter(CHAT_RATE_LIMIT, CHAT_RATE_WINDOW)
AI_DOWN_MESSAGE = "Сервис ИИ временно недоступен. Напишите мастеру в WhatsApp — он ответит лично."


def setup(ctx: AppContext) -> None:
    service.setup()


def register(router: Router, ctx: AppContext) -> None:
    ctx.tools.register(AttachmentTool())

    def list_chats(handler) -> None:
        send_json(handler, {"chats": service.load_chats()})

    def handle_chat(handler) -> None:
        if not CHAT_RATE.allow(client_ip(handler)):
            send_json(handler, {"error": "Слишком много сообщений подряд. Подождите минуту."}, 429)
            return
        body = read_json_body(handler, MAX_CHAT_BODY)
        if body is None:
            return
        message = str(body.get("message", "")).strip()
        # История берётся из базы: присланной браузером можно подделать «ответы консультанта».
        chat_id = service.chat_id_or_new(body.get("chat_id"))
        history = service.load_history(chat_id)
        raw_attachments = body.get("attachments")
        attachments, attach_error = service.process_chat_attachments(raw_attachments)
        if not message and not attachments:
            err = attach_error or "Напишите сообщение или прикрепите файл"
            send_json(handler, {"error": err}, 400)
            return
        config = load_config()
        try:
            try:
                result = reply(message, history, load_products(), config, attachments, tools=ctx.tools)
            except AIUnavailableError as err:
                service.drop_chat_attachments(attachments)
                send_json(
                    handler,
                    {
                        "error": AI_DOWN_MESSAGE,
                        "code": "ai_unavailable" if err.configured else "ai_not_configured",
                        "whatsapp": True,
                        "wa_text": err.wa_text,
                        "cta": "Написать мастеру",
                    },
                    503,
                )
                return
            save_label = message
            if attachments:
                names = ", ".join(item.get("name") or "файл" for item in attachments)
                save_label = f"{message}\n[вложения: {names}]".strip() if message else f"[вложения: {names}]"
            result["chat_id"] = service.append_chat_turn(
                chat_id,
                save_label,
                str(result.get("reply") or ""),
                {
                    "mode": result.get("mode"),
                    "whatsapp": result.get("whatsapp"),
                    "files": [item.get("path") for item in attachments if item.get("path")],
                },
            )
        except Exception:
            service.drop_chat_attachments(attachments)
            raise
        if attach_error:
            result["attachment_warning"] = attach_error
        result["attachments"] = [
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "kind": item.get("kind"),
                "path": item.get("path"),
                "parsed": bool(item.get("parsed")),
                "parse_note": item.get("parse_note") or "",
                "size": item.get("size") or 0,
            }
            for item in attachments
        ]
        send_json(handler, result)

    router.add("GET", "/api/admin/chats", list_chats, auth=True)
    router.add("POST", "/api/chat", handle_chat)
