"""Feature: session + AI status + health + login/logout + отчёты об ошибках фронтенда."""

from __future__ import annotations

import logging

from core.ai import health as ai_health
from core.auth import authorized, login_ok, logout, send_login_ok
from core.config import LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW, ai_settings, validate_env
from core.context import AppContext
from core.db import backup_status
from core.http import client_ip, read_json_body, send_json
from core.ratelimit import RateLimiter
from core.router import Router
from core.settings import load_config

log = logging.getLogger("auth")
client_log = logging.getLogger("client")

LOGIN_FAILS = RateLimiter(LOGIN_FAIL_LIMIT, LOGIN_FAIL_WINDOW)
CLIENT_ERRORS = RateLimiter(20, 60)
MAX_CLIENT_ERROR = 8_000


def _one_line(value, limit: int) -> str:
    """Данные от браузера: перевод строки позволил бы подделать в логе запись от имени сервера."""
    return " ".join(str(value or "").split())[:limit]


def register(router: Router, ctx: AppContext) -> None:
    def session(handler) -> None:
        send_json(handler, {"ok": authorized(handler)})

    def ai_status(handler) -> None:
        config = load_config()
        settings = ai_settings(config)
        send_json(
            handler,
            {
                "key_set": bool(settings["api_key"]),
                "model": settings["model"],
                "api_url": settings["api_url"],
                "health": ai_health.snapshot(),
            },
        )

    def admin_health(handler) -> None:
        settings = ai_settings(load_config())
        send_json(
            handler,
            {
                "ai": {"key_set": bool(settings["api_key"]), **ai_health.snapshot()},
                "backup": backup_status(),
                "config_problems": validate_env(),
            },
        )

    def client_errors(handler) -> None:
        ip = client_ip(handler)
        if not CLIENT_ERRORS.allow(ip):
            send_json(handler, {"error": "Слишком много отчётов"}, 429)
            return
        body = read_json_body(handler, MAX_CLIENT_ERROR)
        if body is None:
            return
        client_log.error(
            "%s | %s | url=%s | ua=%s | ip=%s\n%s",
            _one_line(body.get("kind") or "error", 40),
            _one_line(body.get("message"), 500),
            _one_line(body.get("url"), 300),
            _one_line(handler.headers.get("User-Agent"), 200),
            ip,
            "\n".join(f"    {line}" for line in str(body.get("stack") or "")[:4000].splitlines()),
        )
        send_json(handler, {"ok": True}, 202)

    def login(handler) -> None:
        ip = client_ip(handler)
        if LOGIN_FAILS.blocked(ip):
            minutes = max(1, LOGIN_FAILS.retry_after(ip) // 60)
            send_json(handler, {"error": f"Слишком много неудачных попыток. Попробуйте через {minutes} мин."}, 429)
            return
        body = read_json_body(handler, 10_000)
        if body is None:
            return
        token = login_ok(
            str(body.get("login", "")).strip()[:200],
            str(body.get("password", ""))[:200],
        )
        if not token:
            LOGIN_FAILS.hit(ip)
            log.warning("неудачный вход с %s", ip)
            send_json(handler, {"error": "Неверный логин или пароль"}, 401)
            return
        LOGIN_FAILS.reset(ip)
        send_login_ok(handler, token)

    def do_logout(handler) -> None:
        logout(handler)
        send_json(handler, {"ok": True})

    router.add("GET", "/api/session", session)
    router.add("GET", "/api/ai-status", ai_status, auth=True)
    router.add("GET", "/api/admin/health", admin_health, auth=True)
    router.add("POST", "/api/client-errors", client_errors)
    router.add("POST", "/api/login", login)
    router.add("POST", "/api/logout", do_logout)
