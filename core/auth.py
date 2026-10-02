"""Сессии админки (SQLite, переживают перезапуск сервера)."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import TYPE_CHECKING

from .config import SESSION_TTL, credentials
from .db import migrate, query_one, transaction
from .http import is_https
from .storage import utc_now

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler

STEPS = [
    """
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        expires_at REAL NOT NULL
    );
    CREATE INDEX sessions_expires ON sessions(expires_at);
    """,
]


def setup() -> None:
    migrate("auth", STEPS)
    with transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_token(handler: BaseHTTPRequestHandler) -> str:
    cookie = handler.headers.get("Cookie", "")
    for part in cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "session":
            return value
    return ""


def authorized(handler: BaseHTTPRequestHandler) -> bool:
    token = session_token(handler)
    if not token or len(token) > 200:
        return False
    row = query_one(
        "SELECT 1 FROM sessions WHERE token_hash = ? AND expires_at > ?",
        (_hash(token), time.time()),
    )
    return row is not None


def logout(handler: BaseHTTPRequestHandler) -> None:
    token = session_token(handler)
    if token:
        with transaction() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))


def login_ok(login: str, password: str) -> str | None:
    expected = credentials()
    if expected is None:
        return None
    expect_login, expect_password = expected
    login_match = secrets.compare_digest(login.encode("utf-8"), expect_login.encode("utf-8"))
    password_match = secrets.compare_digest(password.encode("utf-8"), expect_password.encode("utf-8"))
    if not (login_match and password_match):
        return None
    token = secrets.token_urlsafe(32)
    now = time.time()
    with transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        conn.execute(
            "INSERT INTO sessions(token_hash, created_at, expires_at) VALUES (?, ?, ?)",
            (_hash(token), utc_now(), now + SESSION_TTL),
        )
    return token


def send_login_ok(handler: BaseHTTPRequestHandler, token: str) -> None:
    secure = "; Secure" if is_https(handler) else ""
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header(
        "Set-Cookie",
        f"session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}{secure}",
    )
    payload = json.dumps({"ok": True}).encode("utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)
