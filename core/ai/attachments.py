"""
Парсинг вложений чата для ИИ-ядра.

Принимает сырые bytes / base64 от клиента, сохраняет файл при необходимости,
извлекает текст (txt/office/pdf) или готовит image для vision.
Без внешних зависимостей — только stdlib.
"""

from __future__ import annotations

import base64
import binascii
import logging
import re
import secrets
import time
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from core.config import CHAT_DIR, CHAT_DIR_QUOTA, CHAT_FILE_MIN_AGE, MAX_CHAT_FILE
from .prompt import IMAGE_VISION_HINT

log = logging.getLogger("ai.attachments")

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

TEXT_TYPES = {
    "text/plain",
    "text/csv",
    "text/markdown",
    "text/x-markdown",
    "text/html",
    "text/xml",
    "text/tab-separated-values",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-javascript",
    "application/typescript",
}
TEXT_EXT = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".log",
    ".xml", ".html", ".htm", ".yml", ".yaml", ".ini", ".cfg",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".css", ".sql", ".rtf",
}

DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
XLSX_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
PDF_TYPES = {"application/pdf"}

MAX_TEXT = 8000
MAX_LLM_EXCERPT = 4500


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w.\- ()а-яА-ЯёЁ]+", "_", str(name or "file"))
    return (cleaned or "file")[:80]


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _is_mostly_text(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:4096]
    if b"\x00" in sample:
        return False
    printable = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13) or b >= 192)
    return printable / max(1, len(sample)) >= 0.85


ZIP_MAX_ENTRIES = 2000
ZIP_MAX_TOTAL = 50 * 1024 * 1024
ZIP_MAX_RATIO = 100
ZIP_RATIO_MIN_SIZE = 1024 * 1024
ZIP_CHUNK = 64 * 1024


class UnsafeArchiveError(ValueError):
    """Office-файл похож на zip-бомбу: распаковка прервана."""


class _SafeZip:
    """Чтение .docx/.xlsx с общим бюджетом распаковки: заявленным размерам в архиве не доверяем, считаем реальные байты."""

    def __init__(self, raw: bytes):
        self.archive = zipfile.ZipFile(BytesIO(raw))
        infos = self.archive.infolist()
        if len(infos) > ZIP_MAX_ENTRIES:
            raise UnsafeArchiveError(f"слишком много записей в архиве: {len(infos)}")
        declared = sum(info.file_size for info in infos)
        if declared > ZIP_MAX_TOTAL:
            raise UnsafeArchiveError(f"заявленный распакованный объём {declared} байт больше {ZIP_MAX_TOTAL}")
        if declared > ZIP_RATIO_MIN_SIZE and declared / max(1, len(raw)) > ZIP_MAX_RATIO:
            raise UnsafeArchiveError(f"коэффициент сжатия архива {declared // max(1, len(raw))}:1")
        for info in infos:
            if info.file_size > ZIP_RATIO_MIN_SIZE and info.file_size / max(1, info.compress_size) > ZIP_MAX_RATIO:
                raise UnsafeArchiveError(f"коэффициент сжатия {info.filename}: {info.file_size // max(1, info.compress_size)}:1")
        self.budget = ZIP_MAX_TOTAL

    def __enter__(self) -> "_SafeZip":
        return self

    def __exit__(self, *exc) -> None:
        self.archive.close()

    def namelist(self) -> list[str]:
        return self.archive.namelist()

    def read(self, name: str) -> bytes:
        info = self.archive.getinfo(name)
        limit = min(self.budget, info.file_size)
        chunks: list[bytes] = []
        total = 0
        with self.archive.open(info) as stream:
            while True:
                chunk = stream.read(ZIP_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise UnsafeArchiveError(f"{name}: распаковано больше заявленного или лимита ({limit} байт)")
                chunks.append(chunk)
        self.budget -= total
        return b"".join(chunks)


def extract_docx(raw: bytes) -> str:
    with _SafeZip(raw) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for para in root.iter(f"{ns}p"):
        parts = [node.text for node in para.iter(f"{ns}t") if node.text]
        line = "".join(parts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs).strip()


def extract_xlsx(raw: bytes) -> str:
    with _SafeZip(raw) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            for si in root.findall(f"{ns}si"):
                parts = [t.text or "" for t in si.iter(f"{ns}t")]
                shared.append("".join(parts))
        lines: list[str] = []
        sheet_names = sorted(
            name for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
        for sheet in sheet_names[:3]:
            root = ET.fromstring(archive.read(sheet))
            ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            rows: list[str] = []
            for row in root.iter(f"{ns}row"):
                cells: list[str] = []
                for cell in row.findall(f"{ns}c"):
                    value_node = cell.find(f"{ns}v")
                    if value_node is None or value_node.text is None:
                        cells.append("")
                        continue
                    raw_val = value_node.text
                    if cell.get("t") == "s":
                        try:
                            cells.append(shared[int(raw_val)])
                        except (ValueError, IndexError):
                            cells.append(raw_val)
                    else:
                        cells.append(raw_val)
                if any(cell.strip() for cell in cells):
                    rows.append(" | ".join(cells))
            if rows:
                lines.append(f"[{Path(sheet).stem}]")
                lines.extend(rows[:80])
        return "\n".join(lines).strip()


def extract_pdf(raw: bytes) -> str:
    """Грубое извлечение текстовых литералов из PDF (без внешних библиотек)."""
    blob = raw.decode("latin-1", errors="ignore")
    chunks: list[str] = []
    for match in re.finditer(r"\((?:\\.|[^\\)]){1,500}\)", blob):
        piece = match.group(0)[1:-1]
        piece = (
            piece.replace("\\n", "\n")
            .replace("\\r", "")
            .replace("\\t", "\t")
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\\\", "\\")
        )
        # отбросить мусорные бинарные хвосты
        if sum(1 for ch in piece if ch.isprintable() or ch in "\n\t") < max(1, len(piece) * 0.7):
            continue
        if piece.strip():
            chunks.append(piece)
    text = "\n".join(chunks)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_TEXT]


def _extract(extractor, name: str, raw: bytes) -> tuple[str, str]:
    """(текст, причина_отказа). Причина пуста, если разбор прошёл (даже если текста нет)."""
    try:
        return extractor(raw)[:MAX_TEXT], ""
    except UnsafeArchiveError as err:
        log.warning("вложение %s отклонено как zip-бомба: %s", name, err)
        return "", "файл отклонён: подозрение на zip-бомбу"
    except (zipfile.BadZipFile, KeyError, ET.ParseError, ValueError, OSError) as err:
        log.warning("вложение %s не разобрано: %s: %s", name, type(err).__name__, err)
        return "", "файл повреждён или в неизвестном формате, текст не извлечён"


def parse_bytes(name: str, mime: str, raw: bytes) -> dict:
    """Разобрать файл → структура для LLM."""
    safe = _safe_name(name)
    mime = (mime or "application/octet-stream").split(";")[0].strip().lower()
    ext = Path(safe).suffix.lower()
    size = len(raw)

    # --- images → vision ---
    if mime in IMAGE_TYPES or ext in IMAGE_EXT:
        if mime not in IMAGE_TYPES:
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(ext, "image/jpeg")
        return {
            "kind": "image",
            "name": safe,
            "type": mime,
            "size": size,
            "parsed": False,
            "parse_note": "фото сохранено; содержимое разбирает только ИИ-модель",
            "data_url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}",
        }

    # --- docx ---
    if mime in DOCX_TYPES or ext == ".docx":
        text, failure = _extract(extract_docx, safe, raw)
        return {
            "kind": "document" if text else "file",
            "name": safe,
            "type": mime or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": size,
            "parsed": bool(text),
            "parse_note": "текст из Word (.docx)" if text else (failure or "Word-файл без текста"),
            "text": text,
        }

    # --- xlsx ---
    if mime in XLSX_TYPES or ext == ".xlsx":
        text, failure = _extract(extract_xlsx, safe, raw)
        return {
            "kind": "document" if text else "file",
            "name": safe,
            "type": mime or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": size,
            "parsed": bool(text),
            "parse_note": "таблица Excel (.xlsx)" if text else (failure or "Excel-файл без данных"),
            "text": text,
        }

    # --- pdf ---
    if mime in PDF_TYPES or ext == ".pdf":
        text, failure = _extract(extract_pdf, safe, raw)
        if failure:
            text = ""
        return {
            "kind": "document" if text else "file",
            "name": safe,
            "type": mime or "application/pdf",
            "size": size,
            "parsed": bool(text),
            "parse_note": "текст из PDF" if text else "PDF, текст не извлечён (возможно скан)",
            "text": text,
        }

    # --- plain / code text ---
    if mime in TEXT_TYPES or ext in TEXT_EXT or _is_mostly_text(raw):
        text = _decode_text(raw)[:MAX_TEXT]
        return {
            "kind": "text",
            "name": safe,
            "type": mime if mime != "application/octet-stream" else "text/plain",
            "size": size,
            "parsed": True,
            "parse_note": "текстовый файл",
            "text": text,
        }

    # --- unknown binary ---
    return {
        "kind": "file",
        "name": safe,
        "type": mime or "application/octet-stream",
        "size": size,
        "parsed": False,
        "parse_note": "бинарный файл, содержимое для ИИ недоступно",
        "text": "",
    }


# Файлы из assets/chat/ отдаются с адреса сайта: .html/.svg/.js выполнились бы как страница сайта у админа.
STORE_EXT = IMAGE_EXT | {".pdf", ".txt", ".csv", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".rtf", ".odt", ".ods"}


def _store_suffix(parsed: dict) -> str:
    ext = Path(parsed["name"]).suffix.lower()
    if parsed["kind"] == "image":
        return ext if ext in IMAGE_EXT else ".jpg"
    if ext in STORE_EXT:
        return ext
    if parsed["kind"] in {"text", "document"}:
        return ".txt"
    return ".bin"


def _chat_dir_size() -> int:
    """Если папку не удаётся посчитать, считаем её заполненной: лучше отказать в приёме, чем переполнить диск."""
    if not CHAT_DIR.exists():
        return 0
    try:
        return sum(p.stat().st_size for p in CHAT_DIR.iterdir() if p.is_file())
    except OSError:
        log.exception("не удалось посчитать размер %s — приём файлов приостановлен", CHAT_DIR)
        return CHAT_DIR_QUOTA


def _prune_chat_dir(need: int) -> int:
    """Удалить самые старые вложения (старше CHAT_FILE_MIN_AGE), чтобы влезло ещё need байт. Возвращает новый размер папки."""
    try:
        files = [(p.stat(), p) for p in CHAT_DIR.iterdir() if p.is_file()]
    except OSError:
        log.exception("не удалось просмотреть %s для очистки", CHAT_DIR)
        return _chat_dir_size()
    used = sum(st.st_size for st, _ in files)
    target = int(CHAT_DIR_QUOTA * 0.9) - need
    cutoff = time.time() - CHAT_FILE_MIN_AGE
    removed = 0
    for st, path in sorted(files, key=lambda item: item[0].st_mtime):
        if used <= target or st.st_mtime > cutoff:
            break
        try:
            path.unlink()
        except OSError as err:
            log.warning("не удалось удалить старое вложение %s: %s", path, err)
            continue
        used -= st.st_size
        removed += 1
    if removed:
        log.warning("папка %s переполнена: удалено старых файлов %s", CHAT_DIR, removed)
    return used


def _store(raw: bytes, suffix: str) -> str:
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{secrets.token_hex(8)}{suffix}"
    target = CHAT_DIR / stored
    try:
        target.write_bytes(raw)
    except OSError:
        target.unlink(missing_ok=True)
        raise
    return f"assets/chat/{stored}"


def discard_attachments(items: list[dict]) -> None:
    """Удалить файлы, сохранённые для сообщения, которое так и не попало в историю."""
    for item in items or []:
        path = item.get("path")
        if not path:
            continue
        target = CHAT_DIR / Path(str(path)).name
        try:
            target.unlink(missing_ok=True)
        except OSError as err:
            log.warning("не удалось удалить вложение %s: %s", target, err)


def ingest_attachments(raw_items) -> tuple[list[dict], str]:
    """
    Принять attachments из HTTP-тела чата.
    Returns: (prepared, message). message пуст, только если приняты все файлы;
    при частичном приёме это предупреждение, которое нужно показать посетителю.
    """
    if raw_items is None:
        return [], ""
    if not isinstance(raw_items, list):
        return [], "Некорректный формат вложений"
    if not raw_items:
        return [], ""

    prepared: list[dict] = []
    used = _chat_dir_size()
    skipped_empty = 0
    skipped_big = 0
    skipped_bad = 0
    skipped_quota = 0

    for item in raw_items[:3]:
        if not isinstance(item, dict):
            skipped_bad += 1
            continue
        name = _safe_name(str(item.get("name") or "file"))
        mime = str(item.get("type") or "application/octet-stream").split(";")[0].strip().lower()
        data_b64 = item.get("data")
        if data_b64 is None:
            skipped_empty += 1
            continue
        data_b64 = str(data_b64)
        if "," in data_b64 and "base64" in data_b64[:64].lower():
            data_b64 = data_b64.split(",", 1)[1]
        data_b64 = re.sub(r"\s+", "", data_b64)
        if not data_b64:
            skipped_empty += 1
            continue
        try:
            raw = base64.b64decode(data_b64, validate=False)
        except (binascii.Error, ValueError) as err:
            log.warning("вложение %s: некорректный base64: %s", name, err)
            skipped_bad += 1
            continue
        if not raw:
            skipped_empty += 1
            continue
        if len(raw) > MAX_CHAT_FILE:
            skipped_big += 1
            continue

        if used + len(raw) > CHAT_DIR_QUOTA:
            used = _prune_chat_dir(len(raw))
        if used + len(raw) > CHAT_DIR_QUOTA:
            log.error("папка %s заполнена (%s байт), файл %s не сохранён", CHAT_DIR, used, name)
            skipped_quota += 1
            continue
        try:
            parsed = parse_bytes(name, mime, raw)
            parsed["path"] = _store(raw, _store_suffix(parsed))
            used += len(raw)
            prepared.append(parsed)
        except Exception:
            log.exception("вложение %s не обработано", name)
            skipped_bad += 1

    skipped = skipped_bad + skipped_big + skipped_empty + skipped_quota + max(0, len(raw_items) - 3)
    if prepared:
        if skipped:
            return prepared, f"Принято файлов: {len(prepared)}, не принято: {skipped}. Непринятые отправьте мастеру в WhatsApp."
        return prepared, ""

    if skipped_quota:
        return [], "Сейчас не получается принять файл. Напишите текстом или отправьте файл мастеру в WhatsApp."
    if skipped_big:
        return [], "Файл слишком большой. Максимум 4 МБ."
    if skipped_empty:
        return [], "Файл не получен (пустые данные). Выберите файл ещё раз через «+»."
    if skipped_bad:
        return [], "Не удалось прочитать файл. Попробуйте другой формат или ещё раз."
    return [], "Не удалось прикрепить файл."


def format_for_llm(attachments: list | None) -> tuple[list, list[str]]:
    """
    Собрать vision-parts и текстовые куски для user-сообщения LLM.
    Returns: (image_parts, text_bits)
    """
    parts: list = []
    text_bits: list[str] = []
    image_count = 0
    for item in attachments or []:
        kind = item.get("kind")
        name = item.get("name") or "файл"
        note = item.get("parse_note") or ""
        size = int(item.get("size") or 0)
        size_label = f"{max(1, size // 1024)} КБ" if size else ""
        mime = str(item.get("type") or "")

        if kind == "image" and item.get("data_url"):
            image_count += 1
            parts.append({
                "type": "image_url",
                "image_url": {"url": item["data_url"]},
            })
            detail = f"[Изображение {image_count}: {name}"
            if mime:
                detail += f" · {mime}"
            if size_label:
                detail += f" · {size_label}"
            if note:
                detail += f" · {note}"
            detail += "]"
            detail += (
                "\nИнструкция: это реальное фото во вложении vision. "
                "Опиши видимое применительно к шкафу/кухне/кровати/планировке; "
                "если размеры на фото читаются — приведи их; не выдумывай то, чего не видно."
            )
            text_bits.append(detail)
            continue

        text = str(item.get("text") or "").strip()
        if kind in {"text", "document"} and text:
            excerpt = text[:MAX_LLM_EXCERPT]
            header = f"[Файл {name}"
            if note:
                header += f" · {note}"
            header += "]"
            text_bits.append(f"{header}\n{excerpt}")
            continue

        meta = f"[Файл {name}"
        if note:
            meta += f" · {note}"
        if size_label:
            meta += f" · {size_label}"
        meta += f" · тип {item.get('type') or 'unknown'}]"
        meta += "\nСодержимое автоматически не прочитано. Опиши клиенту, что файл сохранён, и при необходимости предложи WhatsApp мастеру."
        text_bits.append(meta)

    if image_count:
        text_bits.insert(0, IMAGE_VISION_HINT)

    return parts, text_bits
