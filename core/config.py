"""Пути, константы, dotenv и настройки ИИ."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


class ConfigError(RuntimeError):
    pass


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ.setdefault(key, value)


# .env читается при импорте, до вычисления путей и порта ниже.
load_dotenv()


def _env_port() -> int:
    raw = os.environ.get("MEBEL_PORT", "").strip()
    if not raw:
        return 8780
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ConfigError(f"MEBEL_PORT={raw!r}: нужно число от 1 до 65535")
    return int(raw)


# 0.0.0.0 нужен только внутри Docker: наружу порт пробрасывается лишь на 127.0.0.1 хоста.
HOST = os.environ.get("MEBEL_HOST", "").strip() or "127.0.0.1"
DIST = ROOT / "dist"
DATA_DIR = Path(os.environ.get("MEBEL_DATA_DIR") or ROOT / "data").resolve()
LOG_DIR = ROOT / "logs"
DB_FILE = DATA_DIR / "shop.db"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_KEEP = 14
# Ежедневные копии: по одной в сутки, храним месяц
BACKUP_KEEP_DAILY = 30
BACKUP_DAILY_INTERVAL = 24 * 3600
LEGACY_DIR = DATA_DIR / "legacy"
# Старые JSON-файлы: импортируются в SQLite при первом запуске и переносятся в LEGACY_DIR
ARCHIVE_DIR = DATA_DIR / "archive"
DATA_FILE = DATA_DIR / "products.json"
CHATS_FILE = DATA_DIR / "chats.json"
ORDERS_FILE = DATA_DIR / "orders.json"
CLIENTS_FILE = DATA_DIR / "clients.json"
CONFIG_FILE = DATA_DIR / "config.json"
UPLOAD_DIR = ROOT / "assets" / "products"
# Рядом с папкой фото, а не в DATA_DIR: сервер с чужой MEBEL_DATA_DIR (тест) чистит ту же папку фото,
# и убранные им файлы должны остаться у владельца, а не во временной папке теста.
PHOTO_TRASH_DIR = ROOT / "data" / "trash" / "products"
PHOTO_TRASH_DAYS = 30
CHAT_DIR = ROOT / "assets" / "chat"

# Ошибки, найденные при импорте (до настройки логов): server.main() пишет их в лог и не запускается.
STARTUP_ERRORS: list[str] = []
try:
    PORT = _env_port()
except ConfigError as _port_err:
    PORT = 0
    STARTUP_ERRORS.append(str(_port_err))
SPA_ROUTES = {"/", "/products", "/admin", "/index.html", "/products.html", "/admin.html"}
MAX_IMAGE = 6 * 1024 * 1024
# 3 файла по 4 МБ в base64 (~16.8 МБ) + текст и история
MAX_CHAT_BODY = 18 * 1024 * 1024
MAX_CHAT_FILE = 4 * 1024 * 1024
MAX_CHATS = 400
SESSION_TTL = 7 * 24 * 3600
ORDER_STATUSES = {"new", "in_progress", "done", "cancelled"}
ORDER_RATE_LIMIT = 8
ORDER_RATE_WINDOW = 60.0
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW = 15 * 60.0
CHAT_RATE_LIMIT = 12
CHAT_RATE_WINDOW = 60.0
CHAT_DIR_QUOTA = 500 * 1024 * 1024
# При переполнении папки удаляются самые старые вложения, но не моложе этого срока
CHAT_FILE_MIN_AGE = 30 * 24 * 3600

BLOCKED = {
    "/data/config.json",
    "/data/chats.json",
    "/data/orders.json",
    "/data/clients.json",
    "/data/products.json",
    "/server.py",
    "/start.bat",
    "/.env",
    "/.env.example",
    "/.gitignore",
    "/consultant.py",
    "/package.json",
    "/package-lock.json",
    "/vite.config.js",
    "/requirements.txt",
    "/node_modules",
    "/core",
    "/features",
    "/logs",
}


def _win_filename(part: str) -> str:
    """Normalize one path segment the way Windows resolves names."""
    # Drop NTFS alternate data stream suffix (name::$DATA)
    if "::" in part:
        part = part.split("::", 1)[0]
    # NTFS ignores trailing spaces and dots in file/dir names
    return part.rstrip(". ")


def normalize_request_path(path: str) -> str:
    """Decode, resolve . / .., apply Windows name rules, lowercase."""
    from urllib.parse import unquote

    raw = unquote(str(path or "")).replace("\\", "/")
    while "//" in raw:
        raw = raw.replace("//", "/")
    if not raw.startswith("/"):
        raw = "/" + raw

    parts: list[str] = []
    for part in raw.split("/"):
        if part in ("", "."):
            continue
        # Exact parent ref before Windows stripping (rstrip would turn ".." into "")
        if part == "..":
            if parts:
                parts.pop()
            continue
        cleaned = _win_filename(part)
        if cleaned in ("", "."):
            continue
        if cleaned == "..":
            if parts:
                parts.pop()
            continue
        parts.append(cleaned)

    resolved = "/" + "/".join(parts) if parts else "/"
    return resolved.lower()


def is_blocked(path: str) -> bool:
    p = normalize_request_path(path)
    if p in BLOCKED:
        return True
    if p.startswith("/data/") or p == "/data":
        return True
    if p.startswith("/src/") or p == "/src":
        return True
    if p.startswith("/core/") or p == "/core":
        return True
    if p.startswith("/features/") or p == "/features":
        return True
    if p.startswith("/logs/") or p == "/logs":
        return True
    if p == "/node_modules" or p.startswith("/node_modules/"):
        return True
    name = p.rsplit("/", 1)[-1]
    if name in {".env", ".env.example", ".gitignore", "server.py", "consultant.py", "start.bat", "requirements.txt"}:
        return True
    if name.endswith((".md", ".py", ".pyc", ".log")):
        return True
    return False


MIN_PASSWORD_LENGTH = 8


def credentials() -> tuple[str, str] | None:
    """Логин и пароль только из .env. None — вход в кабинет закрыт: запасного пароля нет."""
    login = os.environ.get("ADMIN_LOGIN", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not login or len(password) < MIN_PASSWORD_LENGTH:
        return None
    return login, password


_PHONE_RE = re.compile(r"7\d{10}")


def normalize_phone(value) -> str:
    """Цифры телефона в виде 7XXXXXXXXXX (8… и 10 цифр приводятся к 7…)."""
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) == 10:
        digits = f"7{digits}"
    elif len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits


def shop_phone() -> str:
    """Телефон/WhatsApp мастерской из PHONE_E164 в .env. Без него документы и ИИ не знают, куда звать клиента."""
    raw = os.environ.get("PHONE_E164", "")
    phone = normalize_phone(raw)
    if not _PHONE_RE.fullmatch(phone):
        raise ConfigError(f"PHONE_E164={raw!r}: нужен номер вида 77078274377")
    return phone


def format_phone(phone: str) -> str:
    return f"+7 ({phone[1:4]}) {phone[4:7]}-{phone[7:9]}-{phone[9:11]}"


def shop_phone_display() -> str:
    return format_phone(shop_phone())


def ai_settings(config: dict) -> dict:
    block = config.get("ai") if isinstance(config.get("ai"), dict) else {}
    return {
        "api_key": str(
            os.environ.get("AI_API_KEY")
            or block.get("api_key")
            or config.get("ai_api_key")
            or ""
        ).strip(),
        "api_url": str(
            os.environ.get("AI_API_URL")
            or block.get("api_url")
            or "https://api.openai.com/v1/chat/completions"
        ).strip(),
        "model": str(
            os.environ.get("AI_MODEL")
            or block.get("model")
            or "gpt-4o-mini"
        ).strip(),
    }


log = logging.getLogger("config")

_ENV_VAR_RE = re.compile(r"%[^%]+%|\$\{[^}]+\}|\$\w+")
MIRROR_FALLBACK_DIR = DATA_DIR / "mirrors"
_warned: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        log.warning(message)


def backup_mirror_dirs() -> list[Path]:
    """Доп. папки для копий базы: BACKUP_MIRROR_DIRS в .env, через «;» (другой диск, OneDrive).

    Если переменной из пути нет в системе (%OneDrive% без OneDrive), копия идёт в data/mirrors/<имя папки>:
    папка с буквальным именем «%OneDrive%» не создаётся.
    """
    raw = os.environ.get("BACKUP_MIRROR_DIRS", "")
    dirs: list[Path] = []
    for part in raw.split(";"):
        part = part.strip().strip('"')
        if not part:
            continue
        expanded = os.path.expandvars(part)
        if _ENV_VAR_RE.search(expanded):
            rest = _ENV_VAR_RE.sub("", expanded).replace("\\", "/").strip("/")
            path = MIRROR_FALLBACK_DIR / (Path(rest).name or "mirror")
            _warn_once(f"BACKUP_MIRROR_DIRS: в «{part}» переменная окружения не задана — копии идут в {path}")
        else:
            path = Path(expanded)
            if not path.is_absolute():
                path = (ROOT / path).resolve()
        if path not in dirs:
            dirs.append(path)
    return dirs


def validate_env() -> list[str]:
    """Проблемы конфигурации, которые не мешают запуску, но должны быть видны в логе."""
    problems: list[str] = []
    try:
        shop_phone()
    except ConfigError as err:
        problems.append(str(err))
    url = os.environ.get("AI_API_URL", "").strip()
    if url and not url.startswith("https://"):
        problems.append("AI_API_URL должен начинаться с https://")
    proxy = os.environ.get("TRUST_PROXY", "").strip().lower()
    if proxy not in {"", "0", "1", "true", "false", "yes", "no"}:
        problems.append(f"TRUST_PROXY={proxy!r}: допустимо 1 или 0")
    for part in os.environ.get("BACKUP_MIRROR_DIRS", "").split(";"):
        part = part.strip().strip('"')
        if part and _ENV_VAR_RE.search(os.path.expandvars(part)):
            problems.append(
                f"BACKUP_MIRROR_DIRS: в «{part}» переменная не задана — копия лежит в {MIRROR_FALLBACK_DIR}, "
                "на том же диске, что и база"
            )
    if credentials() is None:
        problems.append(
            f"вход в кабинет закрыт — задайте ADMIN_LOGIN и ADMIN_PASSWORD (от {MIN_PASSWORD_LENGTH} символов) в .env"
        )
    return problems


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
