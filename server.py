"""
Локальный сервер визитки и магазина.
Ядро: core/  ·  модули: features/

Запуск: python server.py
Сайт:   http://127.0.0.1:8780/
Кабинет: http://127.0.0.1:8780/admin
Сборка:  npm run build  →  папка dist/
Dev:     npm run dev     →  http://127.0.0.1:5173/ (прокси на API)
Данные: SQLite data/shop.db  ·  резервные копии: data/backups/
Логи:   logs/server.log (всё) · logs/error.log (ошибки со стеком)
Пароль: в .env (ADMIN_LOGIN / ADMIN_PASSWORD)
Ключ ИИ: в .env → AI_API_KEY

Сервер слушает только этот компьютер. В интернет его не выставляйте.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
import re
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# core.config при импорте первым делом читает .env — до любых обращений к переменным окружения.
from core.config import (
    DB_FILE,
    DIST,
    HOST,
    LOG_DIR,
    PORT,
    ROOT,
    STARTUP_ERRORS,
    ConfigError,
    backup_mirror_dirs,
    ensure_dirs,
    is_blocked,
    normalize_request_path,
    shop_phone_display,
    validate_env,
)
from core import auth, db, settings
from core.context import AppContext
from core.http import is_https
from core.logging_setup import setup_logging
from features import FEATURES

log = logging.getLogger("server")
http_log = logging.getLogger("http")

ensure_dirs()

CTX = AppContext()
for feature in FEATURES:
    feature.register(CTX.router, CTX)


_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.S | re.I)
_csp_cache: dict[str, object] = {"mtime": None, "value": ""}


def _inline_script_hashes() -> list[str]:
    """Хеши инлайн-скриптов dist/index.html: CSP разрешает ровно их, без 'unsafe-inline'."""
    index = DIST / "index.html"
    try:
        mtime = index.stat().st_mtime
    except OSError:
        return []
    if _csp_cache["mtime"] != mtime:
        hashes = []
        for attrs, body in _INLINE_SCRIPT_RE.findall(index.read_text(encoding="utf-8")):
            if "application/ld+json" in attrs.lower():
                continue
            digest = hashlib.sha256(body.encode("utf-8")).digest()
            hashes.append(f"'sha256-{base64.b64encode(digest).decode()}'")
        _csp_cache.update(mtime=mtime, value=hashes)
    return list(_csp_cache["value"])


def site_csp() -> str:
    scripts = " ".join(["'self'", *_inline_script_hashes()])
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src {scripts}",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' data: https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "frame-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
    )


class ShopHandler(SimpleHTTPRequestHandler):
    timeout = 60
    response_started = False
    server_version = "MebelAlmaty"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_response(self, code, message=None) -> None:
        self.response_started = True
        super().send_response(code, message)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        if is_https(self):
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        if normalize_request_path(urlparse(self.path).path).startswith("/assets/chat/"):
            # Файлы от посетителей: даже если что-то исполняемое попадёт в папку, оно не получит доступ к сайту.
            self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'")
        else:
            self.send_header("Content-Security-Policy", site_csp())
        super().end_headers()

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path).path
        if parsed.startswith("/assets/"):
            return super().translate_path(path)
        if DIST.is_dir():
            candidate = (DIST / parsed.lstrip("/")).resolve()
            try:
                candidate.relative_to(DIST.resolve())
            except ValueError:
                return super().translate_path(path)
            if candidate.is_file():
                return str(candidate)
        return super().translate_path(path)

    def list_directory(self, path):
        # Directory listings would expose customer chat attachments in assets/chat/.
        self.send_error(404)
        return None

    def _dispatch(self, method: str) -> bool:
        self.response_started = False
        path = urlparse(self.path).path
        # Block secrets/source on every method (Windows FS is case-insensitive)
        if is_blocked(path):
            self.send_error(404)
            return True
        # Вложения посетителей (фото квартир, документы) видит только вошедший в кабинет.
        if normalize_request_path(path).startswith("/assets/chat/"):
            try:
                allowed = auth.authorized(self)
            except Exception:
                log.exception("проверка сессии для %s", path)
                self.send_error(503)
                return True
            if not allowed:
                self.send_error(404)
                return True
        return CTX.router.dispatch(self, method, path)

    def do_GET(self) -> None:
        if self._dispatch("GET"):
            return
        super().do_GET()

    def do_HEAD(self) -> None:
        if self._dispatch("HEAD"):
            return
        super().do_HEAD()

    def do_POST(self) -> None:
        if self._dispatch("POST"):
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        if self._dispatch("PATCH"):
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        if self._dispatch("PUT"):
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        if self._dispatch("DELETE"):
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args) -> None:
        http_log.info("%s %s", self.address_string(), fmt % args)


class ShopServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR lets a second instance bind the same port.
    allow_reuse_address = os.name != "nt"
    # socketserver default backlog is 5: a burst of visitors gets "connection refused".
    request_queue_size = 256

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        logging.getLogger("http").exception("необработанная ошибка запроса от %s", client_address)


def _backup_or_warn(reason: str) -> None:
    """Сбой копии не мешает работе магазина: причина уже в logs/error.log и в баннере кабинета."""
    try:
        db.backup(reason)
    except Exception as err:
        log.error("сервер запускается без копии «%s»: %s", reason, err)


def setup_storage() -> None:
    had_db = DB_FILE.exists()
    db.init()
    if had_db:
        _backup_or_warn("start")
    settings.setup()
    auth.setup()
    for feature in FEATURES:
        setup = getattr(feature, "setup", None)
        if setup is not None:
            setup(CTX)
    if not had_db:
        _backup_or_warn("initial")
    db.start_backup_scheduler()


def main() -> None:
    setup_logging()
    for problem in STARTUP_ERRORS:
        log.critical("Сервер не запущен: %s", problem)
    if STARTUP_ERRORS:
        raise SystemExit(1)
    try:
        phone = shop_phone_display()
    except ConfigError as err:
        log.critical("Сервер не запущен: %s", err)
        raise SystemExit(1) from err
    for problem in validate_env():
        log.error("Настройка .env: %s", problem)
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("image/webp", ".webp")
    try:
        server = ShopServer((HOST, PORT), ShopHandler)
    except OSError as err:
        log.critical("Порт %s занят — сервер уже запущен? (%s)", PORT, err)
        raise SystemExit(1) from err
    try:
        setup_storage()
    except Exception:
        log.critical("Сервер не запущен: ошибка подготовки базы", exc_info=True)
        server.server_close()
        raise SystemExit(1) from None
    mirrors = ", ".join(str(p) for p in backup_mirror_dirs()) or "не настроены (BACKUP_MIRROR_DIRS в .env)"
    log.info("База:    SQLite %s", DB_FILE)
    log.info("Копии:   data/backups + %s", mirrors)
    log.info("Логи:    %s", LOG_DIR)
    log.info("Телефон: %s (PHONE_E164)", phone)
    log.info("Сайт:    http://127.0.0.1:%s/", PORT)
    log.info("Кабинет: http://127.0.0.1:%s/admin", PORT)
    if DIST.is_dir():
        log.info("Фронт:   React build из %s", DIST)
    else:
        log.warning("Фронт:   dist/ нет — выполните npm run build")
    log.info("Модули:  %s", ", ".join(m.__name__.split(".")[-1] for m in FEATURES))
    log.info("Остановка: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Сервер остановлен.")
        server.server_close()


if __name__ == "__main__":
    main()
