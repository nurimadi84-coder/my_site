"""SQLite-хранилище: подключения, транзакции, миграции, резервные копии.

Каждый feature-модуль описывает свою схему списком шагов и вызывает
``migrate("<feature>", STEPS)`` в ``setup()``. Уже применённые шаги
пропускаются, новые шаги дописываются в конец списка — старые не меняются.

Запись:   with transaction() as conn: conn.execute(...)
Чтение:   query(...), query_one(...) или with snapshot() as conn: ...
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .config import (
    BACKUP_DAILY_INTERVAL,
    BACKUP_DIR,
    BACKUP_KEEP,
    BACKUP_KEEP_DAILY,
    CHAT_DIR,
    DB_FILE,
    UPLOAD_DIR,
    backup_mirror_dirs,
)
from .storage import retire_legacy, utc_now

log = logging.getLogger("db")

_local = threading.local()
_WRITE_LOCK = threading.RLock()
_BUSY_TIMEOUT_MS = 30_000


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_FILE,
        timeout=_BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = FULL")
    return conn


def _current() -> sqlite3.Connection | None:
    state = getattr(_local, "tx", None)
    return state[0] if state else None


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Атомарная запись. Вложенные вызовы в том же потоке входят во внешнюю транзакцию."""
    state = getattr(_local, "tx", None)
    if state is not None:
        conn = state[0]
        state[1] += 1
        savepoint = f"sp{state[1]}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            yield conn
            conn.execute(f"RELEASE {savepoint}")
        except BaseException:
            conn.execute(f"ROLLBACK TO {savepoint}")
            conn.execute(f"RELEASE {savepoint}")
            raise
        finally:
            state[1] -= 1
        return
    with _WRITE_LOCK:
        conn = _connect()
        _local.tx = [conn, 1]
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            _local.tx = None
            conn.close()


@contextmanager
def snapshot() -> Iterator[sqlite3.Connection]:
    """Согласованное чтение нескольких запросов (одна точка во времени)."""
    current = _current()
    if current is not None:
        yield current
        return
    conn = _connect()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.execute("COMMIT")
    finally:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        conn.close()


def query(sql: str, params: tuple | dict = ()) -> list[dict]:
    with snapshot() as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | dict = ()) -> dict | None:
    with snapshot() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: str | None, fallback: Any, *, context: str = "") -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError) as err:
        log.error("повреждённый JSON%s: %s; начало значения: %.80r", f" ({context})" if context else "", err, value)
        return fallback


def _statements(script: str) -> list[str]:
    out: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                out.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError(f"Незавершённый SQL в миграции: {buffer.strip()[:80]}")
    return out


def migrate(feature: str, steps: list[str]) -> list[int]:
    """Применить новые шаги схемы модуля. Возвращает номера применённых шагов."""
    applied: list[int] = []
    with transaction() as conn:
        done = {
            row[0]
            for row in conn.execute(
                "SELECT version FROM schema_migrations WHERE feature = ?", (feature,)
            )
        }
        for version, script in enumerate(steps, start=1):
            if version in done:
                continue
            for statement in _statements(script):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(feature, version, applied_at) VALUES (?, ?, ?)",
                (feature, version, utc_now()),
            )
            applied.append(version)
    if applied:
        log.info("%s: применены миграции %s", feature, applied)
    return applied


def run_once(key: str, action: Callable[[sqlite3.Connection], Any]) -> bool:
    """Выполнить действие один раз за жизнь базы (в той же транзакции, что и отметка)."""
    with transaction() as conn:
        if conn.execute("SELECT 1 FROM meta WHERE key = ?", (key,)).fetchone():
            return False
        action(conn)
        conn.execute("INSERT INTO meta(key, value) VALUES (?, ?)", (key, utc_now()))
    return True


def import_legacy(key: str, sources: list[Path], action: Callable[[sqlite3.Connection], int]) -> None:
    """Однократно перенести старые JSON в базу, затем убрать файлы в data/legacy/."""
    present = [p for p in sources if p.exists() or p.with_name(p.name + ".bak").exists()]
    if not present:
        return
    count: list[int] = []
    if run_once(key, lambda conn: count.append(action(conn))):
        log.info("%s: перенесено записей: %s", key, count[0] if count else 0)
    else:
        log.info("%s: уже перенесено ранее, файлы убраны в data/legacy/", key)
    retire_legacy(*present)


def init() -> None:
    conn = _connect()
    try:
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if str(mode).lower() != "wal":
            log.warning("WAL недоступен, режим журнала: %s", mode)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                feature TEXT NOT NULL,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL,
                PRIMARY KEY (feature, version)
            )"""
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        result = conn.execute("PRAGMA quick_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"База данных повреждена: {result}. Восстановите из data/backups/")
    finally:
        conn.close()


def _rotate(folder: Path, reason: str) -> None:
    keep = BACKUP_KEEP_DAILY if reason == "daily" else BACKUP_KEEP
    copies = sorted(folder.glob(f"shop-*-{reason}.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in copies[keep:]:
        try:
            old.unlink()
        except OSError as err:
            log.warning("старая копия %s не удалена: %s", old, err)


_BACKUP_STATE: dict = {"ok": None, "at": "", "file": "", "error": "", "mirrors_failed": []}
_BACKUP_LOCK = threading.Lock()


def backup_status() -> dict:
    with _BACKUP_LOCK:
        state = dict(_BACKUP_STATE)
        state["mirrors_failed"] = list(_BACKUP_STATE["mirrors_failed"])
        return state


def _set_backup_state(**values) -> None:
    with _BACKUP_LOCK:
        _BACKUP_STATE.update(values, at=utc_now())


def _tmp_path(target: Path) -> Path:
    return target.with_name(target.name + ".tmp")


def _atomic_copy(source: Path, target: Path) -> None:
    """Копия через target.tmp → rename: недописанный файл никогда не лежит под рабочим именем."""
    tmp = _tmp_path(target)
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _remove_stale_tmp(folder: Path) -> None:
    for stale in folder.glob("*.tmp"):
        try:
            stale.unlink()
            log.warning("удалён недописанный файл копии от прошлого сбоя: %s", stale)
        except OSError as err:
            log.error("недописанный файл %s не удалён: %s", stale, err)


def _mirror(target: Path, reason: str) -> list[str]:
    """Копия на другой диск/в облако. Недоступная папка (флешка вынута) не ломает работу, но попадает в статус."""
    failed: list[str] = []
    for folder in backup_mirror_dirs():
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _remove_stale_tmp(folder)
            _atomic_copy(target, folder / target.name)
            _rotate(folder, reason)
        except OSError as err:
            log.error("копия базы в %s не создана: %s", folder, err)
            failed.append(f"{folder}: {err}")
    return failed


def backup(reason: str = "auto") -> Path:
    """Онлайн-копия базы (безопасна во время работы сервера) + зеркала из BACKUP_MIRROR_DIRS.

    Запись идёт во временный .tmp; под именем shop-*.db файл появляется только целиком.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _remove_stale_tmp(BACKUP_DIR)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"shop-{stamp}-{reason}.db"
    tmp = _tmp_path(target)
    try:
        source = _connect()
        try:
            dest = sqlite3.connect(tmp)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        os.replace(tmp, target)
    except BaseException as err:
        tmp.unlink(missing_ok=True)
        log.error("резервная копия %s не создана: %s", target.name, err, exc_info=True)
        _set_backup_state(ok=False, file=target.name, error=f"{type(err).__name__}: {err}", mirrors_failed=[])
        raise
    _rotate(BACKUP_DIR, reason)
    failed = _mirror(target, reason)
    failed += backup_files()
    _set_backup_state(ok=True, file=target.name, error="", mirrors_failed=failed)
    return target


# Фото товаров и вложения чата не лежат в базе: копируем их отдельно.
_FILE_DIRS = {"products": UPLOAD_DIR, "chat": CHAT_DIR}


def _copy_new_files(source: Path, target: Path) -> int:
    """Дописать в копию файлы, которых там ещё нет. Имена файлов случайные и не меняются,
    поэтому достаточно сравнить имя и размер. Удалённые с сайта файлы в копии остаются."""
    if not source.is_dir():
        return 0
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    failed = 0
    for path in source.iterdir():
        if not path.is_file() or path.name.startswith(".") or path.suffix == ".tmp":
            continue
        dest = target / path.name
        try:
            if dest.exists() and dest.stat().st_size == path.stat().st_size:
                continue
            _atomic_copy(path, dest)
            copied += 1
        except OSError as err:
            failed += 1
            log.error("файл %s не скопирован в %s: %s", path.name, target, err)
    if failed:
        raise OSError(f"не скопировано файлов: {failed}")
    return copied


def backup_files() -> list[str]:
    """Возвращает список сбоев (пустой — всё скопировано)."""
    failed: list[str] = []
    for root in [BACKUP_DIR, *backup_mirror_dirs()]:
        for name, source in _FILE_DIRS.items():
            try:
                copied = _copy_new_files(source, root / "files" / name)
            except OSError as err:
                log.error("копия файлов %s в %s не создана: %s", name, root, err)
                failed.append(f"{root / 'files' / name}: {err}")
                continue
            if copied:
                log.info("скопировано файлов %s в %s: %s", name, root, copied)
    return failed


def _last_backup_age(reason: str) -> float | None:
    """Сколько секунд прошло с последней копии этого типа (None — копий ещё не было)."""
    copies = [p.stat().st_mtime for p in BACKUP_DIR.glob(f"shop-*-{reason}.db")]
    return time.time() - max(copies) if copies else None


_MAINTENANCE: list[tuple[str, Callable[[], Any]]] = []


def register_maintenance(name: str, task: Callable[[], Any]) -> None:
    """Задача модуля, которая выполняется раз в сутки вместе с резервной копией."""
    _MAINTENANCE.append((name, task))


def _daily_if_due() -> None:
    age = _last_backup_age("daily")
    if age is not None and age < BACKUP_DAILY_INTERVAL:
        return
    try:
        path = backup("daily")
        log.info("ежедневная копия: %s", path.name)
    except Exception as err:
        log.warning("ежедневная копия будет повторена при следующей проверке: %s", err)
    for name, task in _MAINTENANCE:
        try:
            task()
        except Exception:
            log.exception("обслуживание %s", name)


def start_backup_scheduler(check_every_seconds: float = 3600.0) -> None:
    """Ежедневная копия считается по времени последней копии, а не по времени работы сервера:
    если компьютер выключают на ночь, копия делается при следующем запуске."""
    _daily_if_due()

    def loop() -> None:
        while True:
            time.sleep(check_every_seconds)
            _daily_if_due()

    threading.Thread(target=loop, name="db-backup", daemon=True).start()
