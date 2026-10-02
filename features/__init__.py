"""
Подключаемые feature-модули.
Новый модуль: скопируйте _template, реализуйте setup()/register(), добавьте в FEATURES.
setup() всех модулей вызывается при старте в порядке FEATURES (схема БД и перенос данных).
"""

from __future__ import annotations

from . import admin_status, catalog, chat, crm, pdf, spa

# Порядок важен: API/auth раньше, SPA catch-all — последним
FEATURES = (
    admin_status,
    catalog,
    crm,
    chat,
    pdf,
    spa,
)
