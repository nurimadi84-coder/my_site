"""JSON request/response helpers for BaseHTTPRequestHandler."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def behind_proxy() -> bool:
    """TRUST_PROXY=1 в .env, только когда перед сервером стоит nginx/Caddy: иначе заголовки X-Forwarded-* подделываются."""
    return os.environ.get("TRUST_PROXY", "").strip().lower() in {"1", "true", "yes"}


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    if behind_proxy():
        forwarded = handler.headers.get("X-Forwarded-For", "")
        # Последний адрес дописал наш прокси; первые клиент может подставить сам.
        last = forwarded.split(",")[-1].strip() if forwarded else ""
        real = last or handler.headers.get("X-Real-IP", "").strip()
        if real:
            return real[:64]
    return handler.client_address[0] if handler.client_address else "unknown"


def same_origin(handler: BaseHTTPRequestHandler) -> bool:
    """Браузер ставит Origin на POST/PATCH/DELETE; чужой Origin — запрос со стороннего сайта (CSRF)."""
    origin = handler.headers.get("Origin", "").strip()
    if not origin:
        return True
    if origin == "null":
        return False
    host = handler.headers.get("Host", "").strip().lower()
    if behind_proxy():
        host = handler.headers.get("X-Forwarded-Host", "").split(",")[0].strip().lower() or host
    return bool(host) and urlparse(origin).netloc.lower() == host


def is_https(handler: BaseHTTPRequestHandler) -> bool:
    return behind_proxy() and handler.headers.get("X-Forwarded-Proto", "").strip().lower() == "https"


def send_json(handler: BaseHTTPRequestHandler, payload, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def send_bytes(
    handler: BaseHTTPRequestHandler,
    content: bytes,
    content_type: str = "application/pdf",
    filename: str = "file.pdf",
    *,
    inline: bool = True,
) -> None:
    """Отдать бинарный файл из памяти. Cache-Control: no-store добавляет ShopHandler.end_headers."""
    disposition = "inline" if inline else "attachment"
    safe_name = "".join(ch for ch in filename if ch.isascii() and (ch.isalnum() or ch in "._-")) or "file"
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", f'{disposition}; filename="{safe_name}"')
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(content)


def content_length(handler: BaseHTTPRequestHandler) -> int:
    try:
        return int(handler.headers.get("Content-Length", "0") or 0)
    except ValueError:
        return -1


def read_body(handler: BaseHTTPRequestHandler, length: int) -> bytes | None:
    raw = handler.rfile.read(length)
    if len(raw) != length:
        handler.close_connection = True
        return None
    return raw


def read_json_body(handler: BaseHTTPRequestHandler, max_length: int = 200_000):
    length = content_length(handler)
    if length <= 0 or length > max_length:
        # Тело не прочитано: соединение нельзя переиспользовать под следующий запрос.
        handler.close_connection = True
        send_json(handler, {"error": "Пустой или слишком большой запрос"}, 400)
        return None
    raw = read_body(handler, length)
    if raw is None:
        send_json(handler, {"error": "Запрос получен не полностью"}, 400)
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        send_json(handler, {"error": "Некорректные данные"}, 400)
        return None
    if not isinstance(payload, dict):
        send_json(handler, {"error": "Некорректные данные"}, 400)
        return None
    return payload


def path_suffix(path: str, prefix: str) -> str:
    if not path.startswith(prefix):
        return ""
    return path[len(prefix) :].strip("/")
