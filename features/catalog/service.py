"""Каталог товаров: хранение в SQLite и публичное представление."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import time
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.config import DATA_FILE, MAX_IMAGE, PHOTO_TRASH_DAYS, PHOTO_TRASH_DIR, ROOT, UPLOAD_DIR
from core.db import backup_files, dumps, import_legacy, loads, migrate, query, register_maintenance, transaction
from core.storage import read_json, utc_now

log = logging.getLogger("catalog")

STEPS = [
    """
    CREATE TABLE products (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'Другое',
        kind TEXT NOT NULL DEFAULT 'Товар',
        currency TEXT NOT NULL DEFAULT 'KZT',
        price INTEGER,
        qty INTEGER NOT NULL DEFAULT 1,
        description TEXT NOT NULL DEFAULT '',
        image TEXT NOT NULL DEFAULT '',
        images TEXT NOT NULL DEFAULT '[]',
        visible INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
]

_UPLOAD_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PRICE = 10**12
MAX_QTY = 1_000_000

_COLUMNS = (
    "id", "title", "category", "kind", "currency", "price", "qty",
    "description", "image", "images", "visible", "created_at", "updated_at",
)


def _from_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "category": row["category"],
        "kind": row["kind"],
        "currency": row["currency"],
        "price": row["price"],
        "qty": row["qty"],
        "description": row["description"],
        "image": row["image"],
        "images": loads(row["images"], [], context=f"products.images id={row['id']}"),
        "visible": bool(row["visible"]),
    }


def _to_params(item: dict, created_at: str, updated_at: str) -> tuple:
    price = item.get("price")
    try:
        price = None if price in ("", None) else min(MAX_PRICE, int(price))
    except (TypeError, ValueError, OverflowError):
        price = None
    if price is not None and price <= 0:
        price = None
    try:
        qty = min(MAX_QTY, max(1, int(item.get("qty") or 1)))
    except (TypeError, ValueError, OverflowError):
        qty = 1
    images = product_images(item)
    return (
        str(item["id"]),
        str(item.get("title") or "").strip()[:120] or "Без названия",
        str(item.get("category") or "Другое"),
        str(item.get("kind") or "Товар"),
        str(item.get("currency") or "KZT"),
        price,
        qty,
        str(item.get("description") or "")[:500],
        images[0] if images else "",
        dumps(images),
        1 if item.get("visible", True) else 0,
        created_at,
        updated_at,
    )


_INSERT = f"INSERT INTO products({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})"


def _import_products(conn) -> int:
    data = read_json(DATA_FILE, {"products": []})
    items = data.get("products", []) if isinstance(data, dict) else []
    now = utc_now()
    count = 0
    for raw in reversed([x for x in items if isinstance(x, dict)]):
        item = dict(raw)
        item["id"] = str(item.get("id") or secrets.token_hex(6))
        cursor = conn.execute(_INSERT.replace("INSERT", "INSERT OR IGNORE", 1), _to_params(item, now, now))
        count += cursor.rowcount
    return count


def setup() -> None:
    migrate("catalog", STEPS)
    import_legacy("legacy:products", [DATA_FILE], _import_products)
    cleanup_orphan_uploads()
    register_maintenance("catalog: брошенные фото", cleanup_orphan_uploads)


def move_to_trash(path: Path) -> Path:
    """Фото не удаляется сразу, а уходит в data/trash/products и лежит там PHOTO_TRASH_DAYS дней."""
    PHOTO_TRASH_DIR.mkdir(parents=True, exist_ok=True)
    target = PHOTO_TRASH_DIR / path.name
    if target.exists():
        target = PHOTO_TRASH_DIR / f"{path.stem}-{int(time.time())}{path.suffix}"
    # shutil.move, а не os.replace: в Docker папка фото и data/ — разные тома
    shutil.move(str(path), str(target))
    # Срок в корзине считается от удаления, а не от загрузки фото
    os.utime(target)
    log.info("фото %s перенесено в корзину %s", path.name, target)
    return target


def purge_photo_trash() -> int:
    if not PHOTO_TRASH_DIR.is_dir():
        return 0
    cutoff = time.time() - PHOTO_TRASH_DAYS * 24 * 3600
    purged = 0
    for path in PHOTO_TRASH_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                purged += 1
        except OSError as err:
            log.warning("не удалось очистить корзину фото %s: %s", path.name, err)
    if purged:
        log.info("из корзины фото удалено старше %s дн.: %s", PHOTO_TRASH_DAYS, purged)
    return purged


def cleanup_orphan_uploads(min_age_hours: float = 24.0) -> int:
    """Убрать в корзину загруженные фото, которые не попали ни в один товар (форму закрыли без сохранения).

    Свежие файлы не трогаем: админ может ещё заполнять форму товара.
    """
    purge_photo_trash()
    if not UPLOAD_DIR.is_dir():
        return 0
    used: set[str] = set()
    for row in query("SELECT images FROM products"):
        used.update(loads(row["images"], []))
    # Пустой список фото значит чужую или новую базу (тест, MEBEL_DATA_DIR), а не брошенные файлы:
    # папка фото общая и не зависит от папки данных.
    if not used:
        log.info("в базе нет товаров с фото — очистку папки фото пропускаю")
        return 0
    backup_files()
    cutoff = time.time() - min_age_hours * 3600
    removed = 0
    for path in UPLOAD_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in _UPLOAD_SUFFIXES:
            continue
        if f"assets/products/{path.name}" in used or path.stat().st_mtime > cutoff:
            continue
        try:
            move_to_trash(path)
            removed += 1
        except OSError as err:
            log.warning("не удалось убрать в корзину %s: %s", path.name, err)
    if removed:
        log.info("брошенных фото перенесено в корзину: %s", removed)
    return removed


def load_products() -> list:
    return [_from_row(row) for row in query("SELECT * FROM products ORDER BY seq DESC")]


def product_images(item: dict) -> list[str]:
    """Главное фото + доп. ракурсы (до 8), без дублей и path-traversal."""
    seen: set[str] = set()
    out: list[str] = []
    raw = item.get("images") if isinstance(item.get("images"), list) else []
    primary = str(item.get("image") or "").strip()
    candidates = ([primary] if primary else []) + [str(x or "").strip() for x in raw]
    for path in candidates:
        if not path or path in seen:
            continue
        if not path.startswith("assets/products/") or ".." in path:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= 8:
            break
    return out


def public_product(item: dict) -> dict:
    images = product_images(item)
    return {
        "id": item.get("id"),
        "title": item.get("title", ""),
        "category": item.get("category", "Другое"),
        "kind": item.get("kind", "Товар"),
        "currency": item.get("currency", "KZT"),
        "price": item.get("price"),
        "qty": item.get("qty", 1),
        "description": item.get("description", ""),
        "image": images[0] if images else "",
        "images": images,
        "visible": bool(item.get("visible", True)),
    }


CATEGORIES = {"Шкафы", "Кровати", "Кухни", "Другое"}
KINDS = {"Товар", "Услуга"}
CURRENCIES = {"KZT", "USD", "RUB"}


def _int_field(value, label: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}: нужно число")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}: нужно целое число, получено «{str(value)[:20]}»") from None
    if not low <= number <= high:
        raise ValueError(f"{label}: допустимо от {low} до {high}")
    return number


def apply_fields(item: dict, body: dict) -> None:
    """Применить присланные поля. Некорректное значение — ValueError, а не тихая подмена дефолтом."""
    if "title" in body:
        title = str(body.get("title") or "").strip()
        if len(title) < 2:
            raise ValueError("Название: минимум 2 символа")
        item["title"] = title[:120]
    if "category" in body:
        category = str(body.get("category"))
        if category not in CATEGORIES:
            raise ValueError(f"Неизвестная категория «{category[:30]}»")
        item["category"] = category
    if "kind" in body:
        kind = str(body.get("kind"))
        if kind not in KINDS:
            raise ValueError(f"Неизвестный тип «{kind[:30]}»")
        item["kind"] = kind
    if "currency" in body:
        currency = str(body.get("currency"))
        if currency not in CURRENCIES:
            raise ValueError(f"Неизвестная валюта «{currency[:10]}»")
        item["currency"] = currency
    if "qty" in body:
        item["qty"] = _int_field(body.get("qty"), "Количество", 1, MAX_QTY)
    if "description" in body:
        item["description"] = str(body.get("description") or "")[:500]
    if "visible" in body:
        if not isinstance(body.get("visible"), bool):
            raise ValueError("visible: нужно true или false")
        item["visible"] = body["visible"]
    if "price" in body:
        raw_price = body.get("price")
        item["price"] = None if raw_price in ("", None) else _int_field(raw_price, "Цена", 1, MAX_PRICE)
    if "images" in body:
        images = product_images({"images": body.get("images")})
        item["images"] = images
        item["image"] = images[0] if images else ""
    elif "image" in body:
        image = str(body.get("image") or "").strip()
        if image and (not image.startswith("assets/products/") or ".." in image):
            image = ""
        others = [path for path in product_images(item) if path != item.get("image")]
        images = product_images({"image": image, "images": others})
        item["images"] = images
        item["image"] = images[0] if images else ""


def create_product(body: dict) -> dict:
    title = str(body.get("title", "")).strip()
    if len(title) < 2:
        raise ValueError("Напишите название")
    item = {
        "id": secrets.token_hex(6),
        "title": title,
        "category": "Другое",
        "kind": "Товар",
        "currency": "KZT",
        "price": None,
        "qty": 1,
        "description": "",
        "image": "",
        "images": [],
        "visible": True,
    }
    apply_fields(item, body)
    now = utc_now()
    with transaction() as conn:
        conn.execute(_INSERT, _to_params(item, now, now))
        return _get(conn, item["id"])


def _get(conn, product_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return _from_row(dict(row)) if row else None


def update_product(product_id: str, body: dict) -> dict | None:
    with transaction() as conn:
        item = _get(conn, product_id)
        if item is None:
            return None
        before = product_images(item)
        apply_fields(item, body)
        params = _to_params(item, "", utc_now())
        conn.execute(
            """UPDATE products SET title = ?, category = ?, kind = ?, currency = ?, price = ?,
                   qty = ?, description = ?, image = ?, images = ?, visible = ?, updated_at = ?
               WHERE id = ?""",
            (*params[1:11], params[12], product_id),
        )
        updated = _get(conn, product_id)
    discard_images([path for path in before if path not in product_images(updated)])
    return updated


def discard_images(paths: list[str]) -> None:
    """Удалить файлы фото, на которые больше не ссылается ни один товар."""
    if not paths:
        return
    used: set[str] = set()
    for row in query("SELECT images FROM products"):
        used.update(loads(row["images"], []))
    for path in paths:
        if path not in used:
            try:
                delete_image_file(path)
            except OSError as err:
                log.warning("не удалось удалить %s: %s", path, err)


def delete_product(product_id: str) -> dict | None:
    with transaction() as conn:
        item = _get(conn, product_id)
        if item is None:
            return None
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return item


def delete_image_file(image: str) -> None:
    if not image.startswith("assets/products/") or ".." in image:
        return
    path = (ROOT / image).resolve()
    if UPLOAD_DIR.resolve() in path.parents and path.is_file():
        move_to_trash(path)


_IMAGE_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def image_extension(data: bytes) -> str | None:
    """Расширение по настоящему содержимому файла (JPG/PNG/WebP) или None, если это не такая картинка."""
    try:
        with Image.open(BytesIO(data)) as img:
            img.verify()
            return _IMAGE_EXTENSIONS.get(img.format or "")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


def save_upload(data: bytes, extension: str) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}{extension}"
    (UPLOAD_DIR / name).write_bytes(data)
    return f"assets/products/{name}"


__all__ = [
    "MAX_IMAGE",
    "setup",
    "load_products",
    "product_images",
    "public_product",
    "apply_fields",
    "create_product",
    "update_product",
    "delete_product",
    "delete_image_file",
    "discard_images",
    "save_upload",
    "image_extension",
]
