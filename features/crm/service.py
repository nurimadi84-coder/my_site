"""CRM: клиенты и заказы в SQLite."""

from __future__ import annotations

import logging
import re
import secrets

from core.config import (
    ARCHIVE_DIR,
    CLIENTS_FILE,
    ORDER_RATE_LIMIT,
    ORDER_RATE_WINDOW,
    ORDER_STATUSES,
    ORDERS_FILE,
    shop_phone,
)
from core.db import dumps, import_legacy, loads, migrate, query, query_one, transaction
from core.ratelimit import RateLimiter
from core.storage import read_json, read_jsonl, utc_now
from features.catalog.service import load_products

STEPS = [
    """
    CREATE TABLE clients (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL DEFAULT '',
        phone TEXT NOT NULL DEFAULT '',
        phone_key TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        orders_count INTEGER NOT NULL DEFAULT 0,
        last_order_at TEXT NOT NULL DEFAULT '',
        last_source TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        hidden INTEGER NOT NULL DEFAULT 0
    );
    CREATE UNIQUE INDEX clients_phone_key ON clients(phone_key) WHERE phone_key <> '';
    CREATE TABLE orders (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        source TEXT NOT NULL DEFAULT 'site',
        customer_name TEXT NOT NULL DEFAULT '',
        customer_phone TEXT NOT NULL DEFAULT '',
        phone_key TEXT NOT NULL DEFAULT '',
        client_id TEXT REFERENCES clients(id) ON DELETE SET NULL,
        items TEXT NOT NULL DEFAULT '[]',
        message TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        wa_text TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX orders_client ON orders(client_id);
    CREATE INDEX orders_phone_key ON orders(phone_key);
    CREATE INDEX orders_created ON orders(created_at);
    """,
]

log = logging.getLogger("crm")
PHONE_KEY_RE = re.compile(r"^7\d{10}$")
ORDER_RATE = RateLimiter(ORDER_RATE_LIMIT, ORDER_RATE_WINDOW)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) == 10:
        digits = f"7{digits}"
    elif len(digits) == 11 and digits.startswith("8"):
        digits = f"7{digits[1:]}"
    return digits


def is_valid_phone_key(phone_key: str) -> bool:
    return bool(PHONE_KEY_RE.fullmatch(str(phone_key or "")))


def format_phone_display(phone_key: str, original: str = "") -> str:
    raw = str(original or "").strip()
    if raw:
        return raw[:40]
    if len(phone_key) == 11 and phone_key.startswith("7"):
        return f"+7 ({phone_key[1:4]}) {phone_key[4:7]}-{phone_key[7:9]}-{phone_key[9:11]}"
    return f"+{phone_key}" if phone_key else ""


def allow_order_create(ip: str) -> bool:
    return ORDER_RATE.allow(str(ip or "unknown"))


# --- rows -------------------------------------------------------------------

def _client_from_row(row) -> dict:
    row = dict(row)
    row.pop("seq", None)
    row["hidden"] = bool(row.get("hidden"))
    row["orders_count"] = int(row.get("orders_count") or 0)
    return row


def _order_from_row(row) -> dict:
    row = dict(row)
    items = loads(row["items"], None, context=f"orders.items id={row['id']}")
    corrupted = not isinstance(items, list)
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "status": row["status"],
        "source": row["source"],
        "customer": {"name": row["customer_name"], "phone": row["customer_phone"]},
        "client_id": row["client_id"] or "",
        "items": [] if corrupted else items,
        "items_corrupted": corrupted,
        "message": row["message"],
        "note": row["note"],
        "wa_text": row["wa_text"],
    }


def load_orders() -> list:
    return [_order_from_row(row) for row in query("SELECT * FROM orders ORDER BY seq DESC")]


def load_clients() -> list:
    return [_client_from_row(row) for row in query("SELECT * FROM clients ORDER BY seq DESC")]


def _get_order(conn, order_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return _order_from_row(row) if row else None


def get_order(order_id: str) -> dict | None:
    """Заказ с порядковым номером seq (AUTOINCREMENT: номер не переиспользуется после удаления)."""
    row = query_one("SELECT * FROM orders WHERE id = ?", (str(order_id or "")[:64],))
    if row is None:
        return None
    order = _order_from_row(row)
    order["seq"] = int(row["seq"])
    return order


def _get_client(conn, client_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    return _client_from_row(row) if row else None


def public_client(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "name": item.get("name") or "",
        "phone": item.get("phone") or "",
        "phone_key": item.get("phone_key") or "",
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "orders_count": int(item.get("orders_count") or 0),
        "last_order_at": item.get("last_order_at") or "",
        "last_source": item.get("last_source") or "",
        "note": item.get("note") or "",
        "hidden": bool(item.get("hidden")),
    }


def public_order(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "status": item.get("status") or "new",
        "source": item.get("source") or "site",
        "customer": item.get("customer") or {},
        "client_id": item.get("client_id") or "",
        "items": item.get("items") or [],
        "items_corrupted": bool(item.get("items_corrupted")),
        "message": item.get("message") or "",
        "note": item.get("note") or "",
        "wa_text": item.get("wa_text") or "",
    }


# --- client stats -------------------------------------------------------------

_MATCH = "(client_id = :id OR (:phone_key <> '' AND phone_key = :phone_key))"


def _sync_client(conn, client_id: str) -> None:
    """Пересчитать статистику клиента по его заказам (по id или телефону)."""
    client = conn.execute(
        "SELECT id, phone_key, phone FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    if client is None:
        return
    params = {"id": client["id"], "phone_key": client["phone_key"]}
    count = conn.execute(f"SELECT COUNT(*) FROM orders WHERE {_MATCH}", params).fetchone()[0]
    latest = conn.execute(
        f"""SELECT created_at, source, customer_name, customer_phone, phone_key
            FROM orders WHERE {_MATCH} ORDER BY created_at DESC, seq DESC LIMIT 1""",
        params,
    ).fetchone()
    if latest is None:
        conn.execute("UPDATE clients SET orders_count = 0 WHERE id = ?", (client_id,))
        return
    name = str(latest["customer_name"] or "").strip()[:120]
    phone = client["phone"]
    if latest["phone_key"] and latest["phone_key"] == client["phone_key"]:
        phone = format_phone_display(client["phone_key"], latest["customer_phone"] or phone)
    conn.execute(
        """UPDATE clients SET orders_count = ?, last_order_at = ?, last_source = ?,
               name = CASE WHEN ? <> '' THEN ? ELSE name END, phone = ?
           WHERE id = ?""",
        (
            count,
            str(latest["created_at"] or ""),
            str(latest["source"] or "")[:32],
            name,
            name,
            phone,
            client_id,
        ),
    )


def _new_client(conn, name: str, phone: str, phone_key: str, source: str, now: str) -> str:
    client_id = f"u{secrets.token_hex(6)}"
    conn.execute(
        """INSERT INTO clients(id, name, phone, phone_key, created_at, updated_at,
               last_order_at, last_source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            client_id,
            name or "Клиент",
            format_phone_display(phone_key, phone),
            phone_key,
            now,
            now,
            now,
            str(source or "")[:32],
        ),
    )
    return client_id


def _upsert_client(conn, name: str, phone: str, source: str, now: str) -> str | None:
    phone_key = normalize_phone(phone)
    clean_name = str(name or "").strip()[:120]
    if not phone_key and not clean_name:
        return None
    if phone_key:
        row = conn.execute("SELECT id FROM clients WHERE phone_key = ?", (phone_key,)).fetchone()
        if row:
            conn.execute(
                """UPDATE clients SET name = CASE WHEN ? <> '' THEN ? ELSE name END,
                       phone = ?, updated_at = ?, hidden = 0
                   WHERE id = ?""",
                (clean_name, clean_name, format_phone_display(phone_key, phone), now, row["id"]),
            )
            return row["id"]
    return _new_client(conn, clean_name, phone, phone_key, source, now)


def upsert_client(name: str, phone: str, source: str = "", at: str | None = None) -> dict | None:
    with transaction() as conn:
        client_id = _upsert_client(conn, name, phone, source, at or utc_now())
        if client_id is None:
            return None
        _sync_client(conn, client_id)
        return _get_client(conn, client_id)


def repair_client_stats() -> None:
    with transaction() as conn:
        for row in conn.execute("SELECT id FROM clients").fetchall():
            _sync_client(conn, row["id"])


def rebuild_clients_from_orders() -> list:
    """Создать клиентов по заказам без дублей по телефону (если клиентов ещё нет)."""
    with transaction() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY created_at, seq").fetchall()
        for row in rows:
            client_id = _upsert_client(
                conn, row["customer_name"], row["customer_phone"], row["source"], row["created_at"]
            )
            conn.execute("UPDATE orders SET client_id = ? WHERE id = ?", (client_id, row["id"]))
        for client in conn.execute("SELECT id FROM clients").fetchall():
            _sync_client(conn, client["id"])
    return load_clients()


# --- orders -------------------------------------------------------------------

def create_order(body: dict) -> dict:
    now = utc_now()
    source = str(body.get("source") or "site").strip().lower()[:32]
    if source not in {"cart", "product", "calc", "chat", "site"}:
        source = "site"
    customer = body.get("customer") if isinstance(body.get("customer"), dict) else {}
    name = str(customer.get("name") or body.get("name") or "").strip()[:120]
    phone = str(customer.get("phone") or body.get("phone") or "").strip()[:40]
    phone_key = normalize_phone(phone)
    if len(name) < 2:
        raise ValueError("Укажите имя")
    if not is_valid_phone_key(phone_key):
        raise ValueError("Укажите телефон в формате +7 XXX XXX-XX-XX")
    if phone_key == shop_phone():
        raise ValueError("Это номер мастерской. Укажите свой телефон, чтобы мастер мог перезвонить")
    # Скрытый товар снят с продажи: цену из каталога не подставляем, как для неизвестной позиции.
    catalog = {
        str(item.get("id")): item
        for item in load_products()
        if item.get("id") is not None and item.get("visible", True)
    }
    raw_items = body.get("items") if isinstance(body.get("items"), list) else []
    items = []
    for raw in raw_items[:20]:
        if not isinstance(raw, dict):
            continue
        product_id = str(raw.get("id") or "").strip()[:48]
        catalog_item = catalog.get(product_id) if product_id else None
        try:
            qty = int(raw.get("qty") or 1)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Некорректное количество товара") from None
        if not 1 <= qty <= 99:
            raise ValueError("Количество одной позиции: от 1 до 99")
        if catalog_item:
            title = str(catalog_item.get("title") or "").strip()[:160]
            if not title:
                continue
            raw_price = catalog_item.get("price")
            price = raw_price if isinstance(raw_price, int) and raw_price > 0 else None
            currency = str(catalog_item.get("currency") or "KZT")
            if currency not in {"KZT", "USD", "RUB"}:
                log.error("товар %s: неизвестная валюта %r в каталоге", product_id, currency)
                raise ValueError("Ошибка каталога: обратитесь к мастеру")
            kind = str(catalog_item.get("kind") or raw.get("kind") or "")[:40]
            category = str(catalog_item.get("category") or raw.get("category") or "")[:40]
            product_id = str(catalog_item.get("id") or product_id)[:48]
        else:
            title = str(raw.get("title") or "").strip()[:160]
            if not title:
                continue
            price = None
            currency = "KZT"
            kind = str(raw.get("kind") or "")[:40]
            category = str(raw.get("category") or "")[:40]
            product_id = ""
        items.append({
            "id": product_id,
            "title": title,
            "qty": qty,
            "price": price,
            "currency": currency,
            "kind": kind,
            "category": category,
        })
    message = str(body.get("message") or body.get("wa_text") or "").strip()[:4000]
    note = str(body.get("note") or "").strip()[:1000]
    if not items and not message:
        raise ValueError("Пустой заказ")
    order_id = f"o{secrets.token_hex(6)}"
    with transaction() as conn:
        client_id = _upsert_client(conn, name, phone, source, now)
        conn.execute(
            """INSERT INTO orders(id, created_at, updated_at, status, source, customer_name,
                   customer_phone, phone_key, client_id, items, message, note, wa_text)
               VALUES (?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, now, now, source, name, phone, phone_key, client_id,
             dumps(items), message, note, message),
        )
        if client_id:
            _sync_client(conn, client_id)
        return _get_order(conn, order_id)


def patch_order(order_id: str, status: str | None, note) -> dict | None:
    """status=None — статус не меняется (например, правится только заметка)."""
    if status is None and note is None:
        raise ValueError("Нечего менять: передайте status или note")
    if status is not None and status not in ORDER_STATUSES:
        raise ValueError("Неверный статус")
    with transaction() as conn:
        if _get_order(conn, order_id) is None:
            return None
        if status is not None:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        if note is not None:
            conn.execute("UPDATE orders SET note = ? WHERE id = ?", (str(note)[:1000], order_id))
        conn.execute("UPDATE orders SET updated_at = ? WHERE id = ?", (utc_now(), order_id))
        return _get_order(conn, order_id)


def delete_order(order_id: str) -> bool:
    with transaction() as conn:
        row = conn.execute(
            "SELECT client_id, phone_key FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        affected = conn.execute(
            "SELECT id FROM clients WHERE id = ? OR (? <> '' AND phone_key = ?)",
            (row["client_id"], row["phone_key"], row["phone_key"]),
        ).fetchall()
        now = utc_now()
        for client in affected:
            _sync_client(conn, client["id"])
            conn.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (now, client["id"]))
    return True


def patch_client(client_id: str, body: dict) -> dict | None:
    with transaction() as conn:
        if _get_client(conn, client_id) is None:
            return None
        if "note" in body:
            conn.execute(
                "UPDATE clients SET note = ? WHERE id = ?",
                (str(body.get("note") or "")[:1000], client_id),
            )
        if "hidden" in body:
            conn.execute(
                "UPDATE clients SET hidden = ? WHERE id = ?",
                (1 if body.get("hidden") else 0, client_id),
            )
        if "name" in body:
            name = str(body.get("name") or "").strip()[:120]
            if name:
                conn.execute("UPDATE clients SET name = ? WHERE id = ?", (name, client_id))
        conn.execute("UPDATE clients SET updated_at = ? WHERE id = ?", (utc_now(), client_id))
        return _get_client(conn, client_id)


# --- legacy JSON import -------------------------------------------------------

def _safe_int(value, context: str) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        log.warning("импорт CRM: %s = %r не число, записано 0 (пересчитается из заказов)", context, value)
        return 0


def _legacy_list(path, key: str, archive_name: str) -> list[dict]:
    data = read_json(path, {key: []})
    items = data.get(key, []) if isinstance(data, dict) else []
    items = [x for x in items if isinstance(x, dict)]
    items += [x for x in read_jsonl(ARCHIVE_DIR / archive_name) if isinstance(x, dict)]
    seen: set[str] = set()
    unique = []
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id and item_id in seen:
            continue
        seen.add(item_id)
        unique.append(item)
    return unique


def _import_crm(conn) -> int:
    now = utc_now()
    id_map: dict[str, str] = {}
    clients = _legacy_list(CLIENTS_FILE, "clients", "clients.jsonl")
    for raw in reversed(clients):
        old_id = str(raw.get("id") or "")
        phone = str(raw.get("phone") or "").strip()[:40]
        phone_key = normalize_phone(raw.get("phone_key") or phone)
        existing = None
        if phone_key:
            existing = conn.execute(
                "SELECT id FROM clients WHERE phone_key = ?", (phone_key,)
            ).fetchone()
        if existing:
            if old_id:
                id_map[old_id] = existing["id"]
            continue
        client_id = old_id or f"u{secrets.token_hex(6)}"
        if conn.execute("SELECT 1 FROM clients WHERE id = ?", (client_id,)).fetchone():
            client_id = f"u{secrets.token_hex(6)}"
        conn.execute(
            """INSERT INTO clients(id, name, phone, phone_key, created_at, updated_at,
                   orders_count, last_order_at, last_source, note, hidden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                client_id,
                str(raw.get("name") or "Клиент")[:120],
                format_phone_display(phone_key, phone),
                phone_key,
                str(raw.get("created_at") or now),
                str(raw.get("updated_at") or raw.get("created_at") or now),
                _safe_int(raw.get("orders_count"), f"clients.json id={old_id} orders_count"),
                str(raw.get("last_order_at") or ""),
                str(raw.get("last_source") or "")[:32],
                str(raw.get("note") or "")[:1000],
                1 if raw.get("hidden") else 0,
            ),
        )
        if old_id:
            id_map[old_id] = client_id

    orders = _legacy_list(ORDERS_FILE, "orders", "orders.jsonl")
    indexed = list(enumerate(orders))
    indexed.sort(key=lambda pair: (str(pair[1].get("created_at") or ""), -pair[0]))
    for _, raw in indexed:
        order_id = str(raw.get("id") or f"o{secrets.token_hex(6)}")
        customer = raw.get("customer") if isinstance(raw.get("customer"), dict) else {}
        name = str(customer.get("name") or "").strip()[:120]
        phone = str(customer.get("phone") or "").strip()[:40]
        phone_key = normalize_phone(phone)
        client_id = id_map.get(str(raw.get("client_id") or ""))
        if not client_id and phone_key:
            row = conn.execute("SELECT id FROM clients WHERE phone_key = ?", (phone_key,)).fetchone()
            client_id = row["id"] if row else None
        status = str(raw.get("status") or "new")
        created = str(raw.get("created_at") or now)
        conn.execute(
            """INSERT OR IGNORE INTO orders(id, created_at, updated_at, status, source,
                   customer_name, customer_phone, phone_key, client_id, items, message, note, wa_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_id,
                created,
                str(raw.get("updated_at") or created),
                status if status in ORDER_STATUSES else "new",
                str(raw.get("source") or "site")[:32],
                name,
                phone,
                phone_key,
                client_id,
                dumps(raw.get("items") if isinstance(raw.get("items"), list) else []),
                str(raw.get("message") or ""),
                str(raw.get("note") or ""),
                str(raw.get("wa_text") or ""),
            ),
        )
    return len(clients) + len(orders)


def setup() -> None:
    migrate("crm", STEPS)
    import_legacy(
        "legacy:crm",
        [CLIENTS_FILE, ORDERS_FILE, ARCHIVE_DIR / "clients.jsonl", ARCHIVE_DIR / "orders.jsonl"],
        _import_crm,
    )
    has_clients = query("SELECT 1 FROM clients LIMIT 1")
    has_orders = query("SELECT 1 FROM orders LIMIT 1")
    if has_orders and not has_clients:
        rebuild_clients_from_orders()
    else:
        repair_client_stats()
