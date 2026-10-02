"""Настройки сайта в SQLite (ключ → JSON). Значения из .env имеют приоритет."""

from __future__ import annotations

import logging
import re
from typing import Any

from .config import CONFIG_FILE
from .db import dumps, import_legacy, loads, migrate, query, query_one, transaction
from .storage import read_json, utc_now

log = logging.getLogger("settings")

STEPS = [
    """
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]


def _import_config(conn) -> int:
    data = read_json(CONFIG_FILE, {})
    if not isinstance(data, dict):
        return 0
    now = utc_now()
    for key, value in data.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            (str(key), dumps(value), now),
        )
    return len(data)


def setup() -> None:
    migrate("settings", STEPS)
    import_legacy("legacy:config", [CONFIG_FILE], _import_config)
    # Пароль кабинета берётся только из .env: открытый текст в базе попадал бы во все резервные копии.
    with transaction() as conn:
        removed = conn.execute("DELETE FROM settings WHERE key IN ('login', 'password')").rowcount
    if removed:
        log.warning("логин/пароль кабинета удалены из базы — вход только по ADMIN_LOGIN/ADMIN_PASSWORD из .env")


def load_config() -> dict:
    return {row["key"]: loads(row["value"], None) for row in query("SELECT key, value FROM settings")}


def set_setting(key: str, value: Any) -> None:
    with transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
            (key, dumps(value), utc_now()),
        )


# --- реквизиты продавца для счетов ---------------------------------------------

SELLER_KEY = "seller_requisites"

# поле → (подпись для ошибок, максимальная длина)
SELLER_FIELDS: dict[str, tuple[str, int]] = {
    "name": ("Название компании", 160),
    "bin": ("БИН/ИИН", 12),
    "address": ("Адрес", 200),
    "phone": ("Телефон", 40),
    "iban": ("ИИК (IBAN)", 20),
    "bank": ("Банк", 120),
    "bik": ("БИК", 11),
    "kbe": ("Кбе", 2),
    "knp": ("Код назначения платежа", 3),
    "vat_note": ("Строка про НДС", 60),
    "signer": ("Руководитель (ФИО)", 80),
}

# Реквизиты в счёт попадают только из сохранённых владельцем настроек — никаких вшитых Кбе/КНП/НДС.
SELLER_DEFAULTS: dict[str, str] = {field: "" for field in SELLER_FIELDS}

# Без этих полей счёт не может быть официальным — генератор печатает пометку «ОБРАЗЕЦ».
SELLER_REQUIRED = ("name", "bin", "iban", "bank", "bik", "kbe", "knp", "vat_note")

_SELLER_FORMATS = {
    "bin": (re.compile(r"\d{12}"), "12 цифр"),
    "iban": (re.compile(r"KZ\d{2}[A-Z0-9]{16}"), "KZ и ещё 18 символов, например KZ12345678901234567890"),
    "bik": (re.compile(r"[A-Z0-9]{8}([A-Z0-9]{3})?"), "8 или 11 латинских букв и цифр"),
    "kbe": (re.compile(r"\d{2}"), "2 цифры"),
    "knp": (re.compile(r"\d{3}"), "3 цифры"),
}


def _normalize_seller_value(field: str, value: Any) -> str:
    text = " ".join(str(value if value is not None else "").split())
    if field in ("bin", "kbe", "knp"):
        text = re.sub(r"\s", "", text)
    elif field in ("iban", "bik"):
        text = re.sub(r"\s", "", text).upper()
    return text


def validate_seller(body: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Вернуть (чистые реквизиты, ошибки по полям). Неизвестные поля отбрасываются."""
    clean: dict[str, str] = {}
    errors: dict[str, str] = {}
    for field, (label, max_len) in SELLER_FIELDS.items():
        value = _normalize_seller_value(field, body.get(field, ""))
        if len(value) > max_len:
            errors[field] = f"{label}: не длиннее {max_len} символов"
        elif value and field in _SELLER_FORMATS and not _SELLER_FORMATS[field][0].fullmatch(value):
            errors[field] = f"{label}: {_SELLER_FORMATS[field][1]}"
        clean[field] = value
    return clean, errors


def get_seller_settings() -> dict[str, str]:
    row = query_one("SELECT value FROM settings WHERE key = ?", (SELLER_KEY,))
    data = loads(row["value"], {}) if row else {}
    if not isinstance(data, dict):
        data = {}
    return {
        field: str(data[field] if data.get(field) is not None else SELLER_DEFAULTS[field])
        for field in SELLER_FIELDS
    }


def save_seller_settings(clean: dict[str, str]) -> dict[str, str]:
    set_setting(SELLER_KEY, {field: clean.get(field, "") for field in SELLER_FIELDS})
    return get_seller_settings()


def seller_is_complete(seller: dict) -> bool:
    return all(str(seller.get(field) or "").strip() for field in SELLER_REQUIRED)
