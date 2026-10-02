"""Состояние подключения к ИИ — для кабинета (/api/admin/health)."""

from __future__ import annotations

import threading

from core.storage import utc_now

_LOCK = threading.Lock()
_STATE: dict = {"ok": None, "status": "", "at": "", "last_ok_at": "", "failures": 0}


def record(status: str) -> None:
    with _LOCK:
        now = utc_now()
        _STATE["status"] = status
        _STATE["at"] = now
        if status == "ok":
            _STATE["ok"] = True
            _STATE["last_ok_at"] = now
            _STATE["failures"] = 0
        else:
            _STATE["ok"] = False
            _STATE["failures"] += 1


def snapshot() -> dict:
    with _LOCK:
        return dict(_STATE)
