"""Время и чтение старых JSON-файлов (импорт в SQLite)."""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import LEGACY_DIR

log = logging.getLogger("storage")

_RETRIES = 40
_RETRY_DELAY = 0.05


class StorageError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _retry(action):
    """Windows: антивирус/индексатор/редактор могут кратко держать файл открытым."""
    for attempt in range(_RETRIES):
        try:
            return action()
        except PermissionError:
            if attempt == _RETRIES - 1:
                raise
            time.sleep(_RETRY_DELAY)
    return None


def _load(path: Path):
    def action():
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    return _retry(action)


def read_json(path: Path, fallback):
    backup = path.with_name(path.name + ".bak")
    if not path.exists():
        return _load(backup) if backup.exists() else fallback
    try:
        return _load(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        log.error("%s повреждён (%s), читаю резервную копию", path.name, err)
        if backup.exists():
            return _load(backup)
        raise StorageError(f"{path.name} повреждён, резервной копии нет") from err


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    items = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as err:
            log.error("пропущена битая строка в %s: %s", path.name, err)
    return items


def retire_legacy(*paths: Path) -> None:
    """Перенести импортированные JSON (и их .bak) в data/legacy/, не перезаписывая."""
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    for path in paths:
        for source in (path, path.with_name(path.name + ".bak")):
            if not source.exists():
                continue
            target = LEGACY_DIR / source.name
            if target.exists():
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                target = LEGACY_DIR / f"{source.stem}-{stamp}{source.suffix}"
            _retry(lambda: shutil.move(str(source), str(target)))
