"""Общее для PDF-документов: шрифт с кириллицей, очистка текста, деньги."""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont
from fpdf import FPDF
from PIL import Image

from core.config import ROOT, shop_phone_display

log = logging.getLogger("pdf")

LOGO_FILE = ROOT / "assets" / "logo.png"
LOGO_PX = 600
FONT_DIR = ROOT / "core" / "assets" / "fonts"
FONT_REGULAR = FONT_DIR / "DejaVuSans.ttf"
FONT_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"
FONT = "DejaVu"

CURRENCY_MARK = {"KZT": "₸", "USD": "$", "RUB": "₽"}

PAGE_LEFT = 10
PAGE_RIGHT = 200
PAGE_W = PAGE_RIGHT - PAGE_LEFT

# Палитра сайта (styles.css :root): тёмно-синий, золото, слоновая кость.
NAVY = (16, 24, 32)
NAVY_2 = (36, 48, 68)
GOLD = (196, 163, 106)
GOLD_LIGHT = (228, 208, 164)
BRONZE = (140, 112, 68)
IVORY = (247, 243, 236)
SAND = (232, 224, 212)
INK = (28, 24, 20)
MUTED = (107, 98, 88)
WHITE = (255, 255, 255)

SHOP_NAME = "Mebel Almaty"
SHOP_INSTAGRAM = "@mebel_almaty2016"

# Даты в документах — по времени магазина, а не сервера (на хостинге обычно UTC). Казахстан с 2024 г. — единый UTC+5.
SHOP_TZ = timezone(timedelta(hours=5))


class InvalidDateError(ValueError):
    """Дата документа отсутствует или повреждена: документ не формируется."""


def shop_phone_text() -> str:
    return shop_phone_display()


def today() -> str:
    return f"{datetime.now(SHOP_TZ):%d.%m.%Y}"


def shop_date(raw) -> str:
    """ISO-время из БД (UTC) → дата магазина; без зоны считаем UTC. Пусто/мусор → InvalidDateError."""
    text = str(raw or "").strip()
    if not text:
        raise InvalidDateError("Invalid Date: у документа нет даты")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as err:
        raise InvalidDateError(f"Invalid Date: {text[:40]!r}") from err
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return f"{moment.astimezone(SHOP_TZ):%d.%m.%Y}"


class BasePDF(FPDF):
    """A4 со встроенным DejaVu (кириллица, ₸) и нумерацией страниц в подвале."""

    def __init__(self, title: str) -> None:
        super().__init__(format="A4")
        if not FONT_REGULAR.is_file():
            raise FileNotFoundError(f"Нет шрифта с кириллицей: {FONT_REGULAR}")
        self.add_font(FONT, "", str(FONT_REGULAR))
        self.add_font(FONT, "B", str(FONT_BOLD if FONT_BOLD.is_file() else FONT_REGULAR))
        self.set_title(title)
        self.set_creator("Mebel Almaty")
        self.set_margins(PAGE_LEFT, 10, 210 - PAGE_RIGHT)
        self.set_auto_page_break(auto=True, margin=18)
        self.alias_nb_pages()

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font(FONT, "", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Страница {self.page_no()}/{{nb}}", align="C")

    def fill(self, rgb: tuple[int, int, int]) -> None:
        self.set_fill_color(*rgb)

    def ink(self, rgb: tuple[int, int, int]) -> None:
        self.set_text_color(*rgb)

    def stroke(self, rgb: tuple[int, int, int], width: float = 0.2) -> None:
        self.set_draw_color(*rgb)
        self.set_line_width(width)

    def label(self, x: float, y: float, w: float, text: str, rgb=GOLD, align: str = "L") -> None:
        """Маленькая подпись капсом с разрядкой — как .kicker на сайте."""
        self.set_xy(x, y)
        self.set_font(FONT, "B", 6.5)
        self.ink(rgb)
        self.set_char_spacing(0.8)
        self.cell(w, 4, text.upper(), align=align)
        self.set_char_spacing(0)

    def brand_footer(self, left_text: str) -> None:
        self.set_y(-14)
        self.stroke(GOLD, 0.3)
        self.line(PAGE_LEFT, self.get_y(), PAGE_RIGHT, self.get_y())
        self.set_y(-12)
        self.set_font(FONT, "", 7.5)
        self.ink(MUTED)
        self.cell(PAGE_W / 2, 6, left_text, align="L")
        self.cell(PAGE_W / 2, 6, f"Страница {self.page_no()} из {{nb}}", align="R")

    def draw_logo(self, x: float, y: float, height: float, *, align_right: bool = False) -> float:
        """Логотип высотой height мм; при align_right x — правый край. Возвращает ширину (0, если логотипа нет)."""
        logo = load_logo()
        if logo is None:
            return 0.0
        data, ratio = logo
        width = height * ratio
        self.image(BytesIO(data), x=x - width if align_right else x, y=y, w=width, h=height)
        return width


def logo_version() -> str:
    """Метка файла логотипа для ключей кэша: замена файла сразу видна в PDF."""
    try:
        stat = LOGO_FILE.stat()
    except OSError:
        return ""
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def load_logo() -> tuple[bytes, float] | None:
    version = logo_version()
    return _load_logo(str(LOGO_FILE), version) if version else None


@lru_cache(maxsize=2)
def _load_logo(path: str, version: str) -> tuple[bytes, float] | None:
    try:
        with Image.open(Path(path)) as img:
            img.thumbnail((LOGO_PX, LOGO_PX))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            buffer = BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue(), img.width / img.height
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        log.error("логотип %s не загружен, PDF будет без логотипа: %s", path, err)
        return None


@lru_cache(maxsize=1)
def _font_chars() -> frozenset[int]:
    with TTFont(str(FONT_REGULAR), lazy=True) as font:
        return frozenset(font.getBestCmap())


def _is_invisible(ch: str) -> bool:
    """Селекторы вариантов эмодзи (U+FE0F и др.) и знаки нулевой ширины: в шрифте есть, но смысла в печати нет."""
    return 0xFE00 <= ord(ch) <= 0xFE0F or unicodedata.category(ch) == "Cf"


def clean_text(value, limit: int = 0, multiline: bool = False) -> str:
    """Убрать управляющие символы и то, чего нет в шрифте (эмодзи и т.п.), чтобы не было пустых квадратов."""
    chars = _font_chars()
    out = []
    for ch in str(value or ""):
        if ch == "\n" and multiline:
            out.append(ch)
        elif ch in "\r\n\t":
            out.append(" ")
        elif ord(ch) in chars and ch.isprintable() and not _is_invisible(ch):
            out.append(ch)
    text = re.sub(r" {2,}", " ", "".join(out)).strip()
    return text[:limit].rstrip() if limit and len(text) > limit else text


def price_value(price) -> int | None:
    """Цена как положительное целое или None («по запросу»)."""
    if isinstance(price, bool) or price in (None, ""):
        return None
    try:
        value = int(price)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if value > 0 else None


def currency_mark(currency) -> str:
    return CURRENCY_MARK.get(currency) or clean_text(currency, 8) or "₸"


def format_amount(value: int, currency: str = "KZT") -> str:
    return f"{int(value):,}".replace(",", " ") + f" {currency_mark(currency)}"


def format_price(price, currency: str = "KZT") -> str:
    value = price_value(price)
    return "Цена по запросу" if value is None else format_amount(value, currency)
