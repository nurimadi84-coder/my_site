"""Feature: экспорт в PDF (печатный каталог товаров, счета на оплату по заказам)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading

from core.context import AppContext
from core.http import read_json_body, send_bytes, send_json
from core.router import Router
from core.settings import get_seller_settings, save_seller_settings, seller_is_complete, validate_seller
from features.catalog.service import load_products, public_product
from features.crm.service import get_order

from .catalog_pdf import build_catalog_pdf
from .common import InvalidDateError, logo_version, today
from .invoice_pdf import CorruptedOrderError, build_invoice_pdf, invoice_number

log = logging.getLogger("pdf")

INVOICE_PATH = re.compile(r"^([A-Za-z0-9_-]{1,64})/pdf$")

# Адрес публичный, а генерация стоит ~0.4 с CPU: пересобираем PDF только при изменении товаров или даты.
_cache: dict[str, bytes] = {}
_cache_lock = threading.Lock()


def catalog_pdf_bytes() -> bytes:
    products = [public_product(item) for item in load_products() if item.get("visible", True)]
    day = today()
    key = hashlib.sha256(
        json.dumps([day, logo_version(), products], ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    with _cache_lock:
        data = _cache.get(key)
        if data is None:
            data = build_catalog_pdf(products, day=day)
            _cache.clear()
            _cache[key] = data
        return data


def setup(ctx: AppContext) -> None:
    pass


def register(router: Router, ctx: AppContext) -> None:
    def catalog_pdf(handler) -> None:
        send_bytes(handler, catalog_pdf_bytes(), filename="catalog.pdf")

    def order_invoice(handler, rest: str) -> None:
        match = INVOICE_PATH.fullmatch(rest)
        if not match:
            send_json(handler, {"error": "Не найдено"}, 404)
            return
        order = get_order(match.group(1))
        if order is None:
            send_json(handler, {"error": "Заказ не найден"}, 404)
            return
        try:
            pdf = build_invoice_pdf(order)
        except (InvalidDateError, CorruptedOrderError) as err:
            log.error("счёт по заказу %s не сформирован: %s", order.get("id"), err)
            send_json(handler, {"error": f"Счёт не сформирован: {err}", "code": type(err).__name__}, 409)
            return
        send_bytes(handler, pdf, filename=f"invoice_{invoice_number(order)}.pdf")

    def seller_get(handler) -> None:
        seller = get_seller_settings()
        send_json(handler, {"seller": seller, "complete": seller_is_complete(seller)})

    def seller_save(handler) -> None:
        body = read_json_body(handler, 20_000)
        if body is None:
            return
        clean, errors = validate_seller(body)
        if errors:
            send_json(handler, {"error": "Проверьте реквизиты: " + "; ".join(errors.values()), "fields": errors}, 400)
            return
        seller = save_seller_settings(clean)
        send_json(handler, {"seller": seller, "complete": seller_is_complete(seller)})

    router.add("GET", "/api/catalog/pdf", catalog_pdf)
    router.add_prefix("GET", "/api/orders/", order_invoice, auth=True)
    router.add("GET", "/api/admin/settings/seller", seller_get, auth=True)
    router.add("POST", "/api/admin/settings/seller", seller_save, auth=True)
