"""Чат: история диалогов в SQLite. Парсинг вложений — в core.ai.attachments."""

from __future__ import annotations

import secrets

from core.ai.attachments import discard_attachments, ingest_attachments
from core.config import ARCHIVE_DIR, CHATS_FILE, MAX_CHATS
from core.db import dumps, import_legacy, loads, migrate, snapshot, transaction
from core.storage import read_json, read_jsonl, utc_now

STEPS = [
    """
    CREATE TABLE chats (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        preview TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX chats_updated ON chats(updated_at);
    CREATE TABLE chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        at TEXT NOT NULL,
        mode TEXT,
        whatsapp INTEGER,
        files TEXT
    );
    CREATE INDEX chat_messages_chat ON chat_messages(chat_id, id);
    """,
]


def _message(row) -> dict:
    item = {"role": row["role"], "content": row["content"], "at": row["at"]}
    if row["mode"]:
        item["mode"] = row["mode"]
    if row["whatsapp"] is not None:
        item["whatsapp"] = bool(row["whatsapp"])
    files = loads(row["files"], [], context=f"chat_messages.files chat={row['chat_id']}")
    if files:
        item["files"] = files
    return item


def load_chats(limit: int = MAX_CHATS) -> list:
    """Последние диалоги с сообщениями (для админки)."""
    with snapshot() as conn:
        chats = [
            dict(row)
            for row in conn.execute(
                """SELECT id, created_at, updated_at, preview FROM chats
                   ORDER BY updated_at DESC, seq DESC LIMIT ?""",
                (limit,),
            )
        ]
        if not chats:
            return []
        by_id = {chat["id"]: chat for chat in chats}
        for chat in chats:
            chat["messages"] = []
        marks = ",".join("?" * len(by_id))
        for row in conn.execute(
            f"SELECT * FROM chat_messages WHERE chat_id IN ({marks}) ORDER BY id",
            tuple(by_id),
        ):
            by_id[row["chat_id"]]["messages"].append(_message(row))
    return chats


MIN_CHAT_ID = 24


def chat_id_or_new(raw) -> str:
    """По id сервер подставляет историю диалога в ИИ, поэтому короткие (подбираемые) id не принимаются."""
    safe_id = "".join(ch for ch in str(raw or "") if ch.isalnum() or ch in "-_")[:48]
    return safe_id if len(safe_id) >= MIN_CHAT_ID else secrets.token_hex(16)


def load_history(chat_id: str, limit: int = 20) -> list[dict]:
    """Последние реплики диалога из базы, от старых к новым."""
    with snapshot() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [
        {"role": row["role"], "content": str(row["content"] or "")[:2000]}
        for row in reversed(rows)
        if str(row["content"] or "").strip()
    ]


def process_chat_attachments(raw_items) -> tuple[list, str]:
    """Сохранить файлы и распарсить содержимое для ИИ (ядро)."""
    return ingest_attachments(raw_items)


def drop_chat_attachments(items: list) -> None:
    discard_attachments(items)


def append_chat_turn(chat_id: str, user_text: str, assistant_text: str, meta: dict | None = None) -> str:
    meta = meta or {}
    now = utc_now()
    safe_id = "".join(ch for ch in str(chat_id or "") if ch.isalnum() or ch in "-_")[:48]
    if len(safe_id) < 8:
        safe_id = secrets.token_hex(8)
    preview = user_text.strip().replace("\n", " ")[:120]
    files = [str(path) for path in meta.get("files") or [] if path]
    whatsapp = meta.get("whatsapp")
    with transaction() as conn:
        conn.execute(
            """INSERT INTO chats(id, created_at, updated_at, preview) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at,
                                             preview = excluded.preview""",
            (safe_id, now, now, preview),
        )
        conn.execute(
            "INSERT INTO chat_messages(chat_id, role, content, at, files) VALUES (?, 'user', ?, ?, ?)",
            (safe_id, user_text[:2000], now, dumps(files) if files else None),
        )
        conn.execute(
            """INSERT INTO chat_messages(chat_id, role, content, at, mode, whatsapp)
               VALUES (?, 'assistant', ?, ?, ?, ?)""",
            (
                safe_id,
                assistant_text[:4000],
                now,
                meta.get("mode") or None,
                None if whatsapp is None else (1 if whatsapp else 0),
            ),
        )
    return safe_id


def _import_chats(conn) -> int:
    data = read_json(CHATS_FILE, {"chats": []})
    chats = data.get("chats", []) if isinstance(data, dict) else []
    chats = [x for x in chats if isinstance(x, dict)]
    chats += [x for x in read_jsonl(ARCHIVE_DIR / "chats.jsonl") if isinstance(x, dict)]
    now = utc_now()
    count = 0
    seen: set[str] = set()
    for chat in reversed(chats):
        chat_id = str(chat.get("id") or secrets.token_hex(8))[:48]
        messages = chat.get("messages") if isinstance(chat.get("messages"), list) else []
        created = str(chat.get("created_at") or now)
        conn.execute(
            """INSERT INTO chats(id, created_at, updated_at, preview) VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   updated_at = MAX(chats.updated_at, excluded.updated_at),
                   created_at = MIN(chats.created_at, excluded.created_at)""",
            (chat_id, created, str(chat.get("updated_at") or created), str(chat.get("preview") or "")[:120]),
        )
        record_keys: set[str] = set()
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role") if msg.get("role") in {"user", "assistant"} else "user"
            content = str(msg.get("content") or "")
            at = str(msg.get("at") or created)
            # The same chat can appear in both chats.json and the archive: skip overlap only.
            key = f"{chat_id}|{role}|{at}|{content}"
            if key in seen:
                continue
            record_keys.add(key)
            whatsapp = msg.get("whatsapp")
            files = msg.get("files") if isinstance(msg.get("files"), list) else []
            conn.execute(
                """INSERT INTO chat_messages(chat_id, role, content, at, mode, whatsapp, files)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    chat_id,
                    role,
                    content,
                    at,
                    msg.get("mode") or None,
                    None if whatsapp is None else (1 if whatsapp else 0),
                    dumps(files) if files else None,
                ),
            )
            count += 1
        seen |= record_keys
    return count


def setup() -> None:
    migrate("chat", STEPS)
    import_legacy("legacy:chats", [CHATS_FILE, ARCHIVE_DIR / "chats.jsonl"], _import_chats)
