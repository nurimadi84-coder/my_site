"""Шаблон нового feature-модуля.

Скопируйте папку, переименуйте, реализуйте setup()/register() и добавьте модуль в features.FEATURES.

setup()    — вызывается при старте: схема таблиц (migrate) и разовый перенос данных.
register() — маршруты API и инструменты ИИ.
Новые изменения схемы — только новым элементом в конце STEPS, старые шаги не менять.
"""

from __future__ import annotations

from core.context import AppContext
from core.db import migrate
from core.http import send_json
from core.router import Router

STEPS: list[str] = [
    # """
    # CREATE TABLE template_items (
    #     id INTEGER PRIMARY KEY AUTOINCREMENT,
    #     title TEXT NOT NULL,
    #     created_at TEXT NOT NULL
    # );
    # """,
]


def setup(ctx: AppContext) -> None:
    migrate("template", STEPS)


def register(router: Router, ctx: AppContext) -> None:
    def hello(handler) -> None:
        send_json(handler, {"ok": True, "feature": "template"})

    # Пример: router.add("GET", "/api/template", hello)
    # Запись: with transaction() as conn: conn.execute("INSERT ...", (...))
    # Чтение: query("SELECT ...", (...))
    # При необходимости: ctx.tools.register(MyTool())
    _ = (hello, ctx)
