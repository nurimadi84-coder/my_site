"""Вызов OpenAI-совместимого chat completions API."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from .attachments import format_for_llm
from .prompt import build_system_prompt

log = logging.getLogger("ai.llm")


def call_llm(
    settings: dict,
    history: list,
    system_extra: str = "",
    attachments: list | None = None,
) -> tuple[str | None, str]:
    key = settings["api_key"]
    if not key:
        return None, "no_key"
    messages = [
        {"role": "system", "content": build_system_prompt(system_extra)},
    ]
    for item in history[-10:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:1200]})

    # последнее сообщение пользователя уже в history; для вложений пересоберём его с vision/text
    user_text = ""
    if messages and messages[-1].get("role") == "user":
        user_text = str(messages[-1].get("content") or "")
        messages.pop()

    image_parts, file_bits = format_for_llm(attachments)
    text_bits = [user_text] if user_text else []
    text_bits.extend(file_bits)

    combined = "\n\n".join(bit for bit in text_bits if bit).strip() or (
        "Клиент прислал вложение. Прокомментируй содержимое (если удалось прочитать) "
        "и предложи следующий шаг по мебели."
    )
    if image_parts:
        content = [{"type": "text", "text": combined}, *image_parts]
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": combined[:6000]})

    payload = {
        "model": settings["model"],
        "temperature": 0.4 if image_parts else 0.45,
        "max_tokens": 720 if image_parts else 520,
        "messages": messages,
    }
    request = urllib.request.Request(
        settings["api_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            detail = err.read().decode("utf-8", errors="ignore")[:180]
        except OSError as read_err:
            detail = f"<тело ответа не прочитано: {read_err}>"
        log.error("ИИ API ответил HTTP %s: %s", err.code, detail)
        return None, f"http_{err.code}:{detail}"
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        log.error("ИИ API недоступен: %s: %s", type(err).__name__, err)
        return None, f"network:{type(err).__name__}"
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        log.error("ИИ API вернул не-JSON: %s", err)
        return None, "bad_json"

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        log.error("ИИ API: в ответе нет choices: %.300s", json.dumps(data, ensure_ascii=False))
        return None, "empty"
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        log.error("ИИ API вернул пустой ответ (finish_reason=%s)", choices[0].get("finish_reason"))
        return None, "empty"
    return text, "ok"
