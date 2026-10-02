"""Каталог в контексте ИИ и форматирование цен."""

from __future__ import annotations

CURRENCY = {"KZT": "₸", "USD": "$", "RUB": "₽"}


def money(value, currency="KZT") -> str:
    if value in (None, ""):
        return "цена по запросу"
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "цена по запросу"
    mark = CURRENCY.get(currency, "₸")
    return f"{number:,}".replace(",", " ") + f" {mark}"


def catalog_text(products: list) -> str:
    visible = [item for item in products if item.get("visible", True)]
    if not visible:
        return "На витрине сейчас нет готовых карточек — работаем под заказ."
    lines = ["Готовые изделия на витрине:"]
    for item in visible[:12]:
        kind = item.get("kind") or "Товар"
        title = item.get("title") or "Без названия"
        price = money(item.get("price"), item.get("currency") or "KZT")
        lines.append(f"- [{kind}] {title} — {price}")
    return "\n".join(lines)


class CatalogTool:
    name = "catalog"
    description = "Витрина готовых изделий и цены"

    def context(self, products: list, history: list) -> str:
        return catalog_text(products)

    def maybe_act(self, message: str, history: list) -> dict | None:
        return None
