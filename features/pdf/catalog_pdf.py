"""Печатный каталог товаров в PDF (fpdf2 + Pillow, генерация в памяти)."""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageOps

from core.config import ROOT

from .common import (
    BRONZE,
    FONT,
    GOLD,
    GOLD_LIGHT,
    INK,
    IVORY,
    MUTED,
    NAVY,
    NAVY_2,
    PAGE_LEFT,
    PAGE_RIGHT,
    PAGE_W,
    SAND,
    SHOP_INSTAGRAM,
    SHOP_NAME,
    WHITE,
    BasePDF,
    clean_text,
    format_price,
    price_value,
    shop_phone_text,
    today,
)

log = logging.getLogger("pdf.catalog")

IMG_PX = 560  # уменьшаем фото перед вставкой, чтобы PDF не раздувался
PAD = 4
GAP = 6
CARD_W = (PAGE_W - GAP) / 2
PHOTO_W = CARD_W - 2 * PAD
PHOTO_H = 46
COVER_H = 58
OTHER = "Другое"


class CatalogPDF(BasePDF):
    def __init__(self, title: str = "Каталог товаров", day: str = "") -> None:
        super().__init__(title)
        self.day = day or today()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        top = 8
        logo_w = self.draw_logo(PAGE_LEFT, top, 9)
        x = PAGE_LEFT + (logo_w + 3 if logo_w else 0)
        self.set_xy(x, top + 2)
        self.set_font(FONT, "B", 9)
        self.ink(NAVY)
        self.cell(80, 5, f"{SHOP_NAME} · Каталог")
        self.set_xy(PAGE_RIGHT - 60, top + 2)
        self.set_font(FONT, "", 8)
        self.ink(MUTED)
        self.cell(60, 5, f"WhatsApp {shop_phone_text()}", align="R")
        self.stroke(GOLD, 0.4)
        self.line(PAGE_LEFT, top + 12, PAGE_RIGHT, top + 12)
        self.set_y(top + 18)

    def footer(self) -> None:
        self.brand_footer(f"{SHOP_NAME} · {shop_phone_text()} · Instagram {SHOP_INSTAGRAM} · цены на {self.day}")


def _load_thumb(relative_path: str) -> BytesIO | None:
    """Фото товара, обрезанное по центру под рамку карточки, или None, если файла нет/он битый."""
    if not relative_path:
        return None
    if not relative_path.startswith("assets/products/") or ".." in relative_path:
        log.error("каталог PDF: недопустимый путь фото %r", relative_path)
        return None
    path = ROOT / relative_path
    if not path.is_file():
        log.error("каталог PDF: файл фото пропал: %s", path)
        return None
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                background = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                img = background
            img = ImageOps.fit(img, (IMG_PX, round(IMG_PX * PHOTO_H / PHOTO_W)), Image.Resampling.LANCZOS)
            # fpdf2 встраивает PIL-картинки без потерь (в разы тяжелее), поэтому отдаём ему JPEG.
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=82, optimize=True)
            return buffer
    except (OSError, ValueError, Image.DecompressionBombError) as err:
        log.error("каталог PDF: фото %s повреждено: %s", path, err)
        return None


def _prepare(products: list[dict]) -> list[tuple[str, list[dict]]]:
    """Товары по разделам в порядке появления; «Другое» в конце."""
    sections: dict[str, list[dict]] = {}
    for raw in products:
        item = {
            "title": clean_text(raw.get("title"), 160) or "Без названия",
            "kind": clean_text(raw.get("kind"), 40),
            "price": format_price(raw.get("price"), raw.get("currency") or "KZT"),
            "has_price": price_value(raw.get("price")) is not None,
            "description": clean_text(raw.get("description"), 280),
            "image": str(raw.get("image") or ""),
        }
        category = clean_text(raw.get("category"), 60) or OTHER
        sections.setdefault(category, []).append(item)
    ordered = [(name, items) for name, items in sections.items() if name != OTHER]
    if OTHER in sections:
        ordered.append((OTHER, sections[OTHER]))
    return ordered


def _plural_items(n: int) -> str:
    if 11 <= n % 100 <= 14:
        return f"{n} изделий"
    if n % 10 == 1:
        return f"{n} изделие"
    if 2 <= n % 10 <= 4:
        return f"{n} изделия"
    return f"{n} изделий"


def _cover(pdf: CatalogPDF, sections: list[tuple[str, list[dict]]]) -> None:
    pdf.fill(NAVY)
    pdf.rect(0, 0, 210, COVER_H, "F")
    pdf.fill(GOLD)
    pdf.rect(0, COVER_H, 210, 1.2, "F")

    logo_w = pdf.draw_logo(PAGE_LEFT, 12, 34)
    x = PAGE_LEFT + (logo_w + 8 if logo_w else 0)
    w = PAGE_RIGHT - x - 56
    pdf.label(x, 13, w, f"Каталог · {pdf.day}")
    pdf.set_xy(x, 18)
    pdf.set_font(FONT, "B", 21)
    pdf.ink(WHITE)
    pdf.multi_cell(w, 9, "Корпусная мебель\nна заказ", align="L", new_x="LEFT", new_y="NEXT")
    names = [name for name, _ in sections if name != OTHER]
    pdf.set_x(x)
    pdf.set_font(FONT, "", 8.5)
    pdf.ink(GOLD_LIGHT)
    pdf.multi_cell(w, 4.5, (", ".join(names) + " — " if names else "") + "по вашим размерам в Алматы",
                   align="L", new_x="LEFT", new_y="NEXT")

    cx = PAGE_RIGHT - 52
    pdf.label(cx, 13, 52, "Связаться", align="R")
    for i, (title, value) in enumerate((("WhatsApp", shop_phone_text()), ("Instagram", SHOP_INSTAGRAM))):
        y = 19 + i * 11
        pdf.set_xy(cx, y)
        pdf.set_font(FONT, "", 7)
        pdf.ink(GOLD_LIGHT)
        pdf.cell(52, 4, title, align="R")
        pdf.set_xy(cx, y + 4)
        pdf.set_font(FONT, "B", 9.5)
        pdf.ink(WHITE)
        pdf.cell(52, 5, value, align="R")

    pdf.set_y(COVER_H + 8)
    total = sum(len(items) for _, items in sections)
    pdf.set_x(PAGE_LEFT)
    pdf.set_font(FONT, "", 9.5)
    pdf.ink(INK)
    pdf.cell(0, 6, f"В каталоге {_plural_items(total)} в {len(sections)} "
                   f"{'разделе' if len(sections) == 1 else 'разделах'}:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    x = PAGE_LEFT
    y = pdf.get_y()
    pdf.set_font(FONT, "B", 8.5)
    for index, (name, items) in enumerate(sections, start=1):
        text = f"{index:02d}  {name} · {len(items)}"
        chip_w = pdf.get_string_width(text) + 10
        if x + chip_w > PAGE_RIGHT:
            x = PAGE_LEFT
            y += 10
        pdf.fill(IVORY)
        pdf.stroke(GOLD_LIGHT, 0.3)
        pdf.rect(x, y, chip_w, 7.5, "DF", round_corners=True, corner_radius=3.7)
        pdf.set_xy(x, y + 1.2)
        pdf.ink(NAVY)
        pdf.cell(chip_w, 5, text, align="C")
        x += chip_w + 4
    pdf.set_y(y + 15)


def _section_header(pdf: CatalogPDF, index: int, name: str, count: int) -> None:
    y = pdf.get_y()
    pdf.label(PAGE_LEFT, y, 60, f"Раздел {index:02d}")
    pdf.set_xy(PAGE_LEFT, y + 4)
    pdf.set_font(FONT, "B", 17)
    pdf.ink(NAVY)
    pdf.cell(PAGE_W - 40, 9, name)
    pdf.set_xy(PAGE_RIGHT - 40, y + 6)
    pdf.set_font(FONT, "", 8.5)
    pdf.ink(MUTED)
    pdf.cell(40, 6, _plural_items(count), align="R")
    pdf.fill(GOLD)
    pdf.rect(PAGE_LEFT, y + 14.5, 28, 1.1, "F")
    pdf.stroke(SAND, 0.3)
    pdf.line(PAGE_LEFT + 28, y + 15, PAGE_RIGHT, y + 15)
    pdf.set_y(y + 21)


SECTION_H = 21


TEXT_W = CARD_W - 2 * PAD
TITLE_LINE = 5.2
DESC_LINE = 4.1


def _lines(pdf: CatalogPDF, text: str, style: str, size: float, line_h: float) -> float:
    if not text:
        return 0.0
    pdf.set_font(FONT, style, size)
    return len(pdf.multi_cell(TEXT_W, line_h, text, dry_run=True, output="LINES")) * line_h


def _card_height(pdf: CatalogPDF, item: dict) -> float:
    desc_h = _lines(pdf, item["description"], "", 8.5, DESC_LINE)
    return (PAD + PHOTO_H + 4 + _lines(pdf, item["title"], "B", 11, TITLE_LINE)
            + 8 + (desc_h + 2 if desc_h else 0) + PAD)


def _draw_photo(pdf: CatalogPDF, item: dict, x: float, y: float) -> None:
    pdf.fill(IVORY)
    pdf.rect(x, y, PHOTO_W, PHOTO_H, "F", round_corners=True, corner_radius=2)
    thumb = _load_thumb(item["image"])
    if thumb is None:
        pdf.set_xy(x, y + PHOTO_H / 2 - 3)
        pdf.set_font(FONT, "", 8)
        pdf.ink(MUTED)
        pdf.cell(PHOTO_W, 6, "фото недоступно" if item["image"] else "фото по запросу", align="C")
    else:
        pdf.image(thumb, x=x, y=y, w=PHOTO_W, h=PHOTO_H)
    # «Товар» стоит почти у всего каталога — плашку показываем только для отличающихся типов (услуга, проект…).
    if item["kind"] and item["kind"].lower() != "товар":
        text = item["kind"].upper()
        pdf.set_font(FONT, "B", 6.5)
        chip_w = pdf.get_string_width(text) + 7
        pdf.fill(NAVY)
        pdf.rect(x + 3, y + 3, chip_w, 5, "F", round_corners=True, corner_radius=2.5)
        pdf.set_xy(x + 3, y + 3.4)
        pdf.ink(GOLD_LIGHT)
        pdf.cell(chip_w, 4.2, text, align="C")


def _card(pdf: CatalogPDF, item: dict, x: float, y: float, h: float) -> None:
    pdf.fill(WHITE)
    pdf.stroke(SAND, 0.35)
    pdf.rect(x, y, CARD_W, h, "DF", round_corners=True, corner_radius=3)
    _draw_photo(pdf, item, x + PAD, y + PAD)

    tx = x + PAD
    pdf.set_xy(tx, y + PAD + PHOTO_H + 4)
    pdf.set_font(FONT, "B", 11)
    pdf.ink(NAVY)
    pdf.multi_cell(TEXT_W, TITLE_LINE, item["title"], align="L", new_x="LEFT", new_y="NEXT")

    price_y = pdf.get_y() + 1.5
    pdf.set_xy(tx, price_y)
    if item["has_price"]:
        pdf.set_font(FONT, "B", 12.5)
        pdf.ink(BRONZE)
        pdf.cell(TEXT_W, 6, item["price"])
    else:
        pdf.set_font(FONT, "B", 9)
        pdf.ink(BRONZE)
        pdf.cell(TEXT_W, 6, "Цена по запросу")

    if item["description"]:
        pdf.stroke(SAND, 0.25)
        pdf.line(tx, price_y + 7.5, tx + TEXT_W, price_y + 7.5)
        pdf.set_xy(tx, price_y + 9)
        pdf.set_font(FONT, "", 8.5)
        pdf.ink(MUTED)
        pdf.multi_cell(TEXT_W, DESC_LINE, item["description"], align="L", new_x="LEFT", new_y="NEXT")


def _card_rows(pdf: CatalogPDF, items: list[dict]) -> list[tuple[list[dict], float]]:
    rows = []
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        rows.append((pair, max(_card_height(pdf, item) for item in pair)))
    return rows


def _how_to_order(pdf: CatalogPDF) -> None:
    steps = (
        ("01", "Выберите изделие", "из каталога или пришлите фото, эскиз, размеры ниши"),
        ("02", "Обсудим проект", "мастер уточнит материалы, фурнитуру и рассчитает стоимость"),
        ("03", "Изготовим", "обычно 14–25 дней после утверждения проекта"),
    )
    h = 58
    if pdf.get_y() + h > pdf.page_break_trigger:
        pdf.add_page()
    y = pdf.get_y() + 2
    pdf.fill(NAVY)
    pdf.rect(PAGE_LEFT, y, PAGE_W, h, "F", round_corners=True, corner_radius=3)
    pdf.label(PAGE_LEFT + 8, y + 6, 100, "Как заказать")
    pdf.set_xy(PAGE_LEFT + 8, y + 10.5)
    pdf.set_font(FONT, "B", 14)
    pdf.ink(WHITE)
    pdf.cell(120, 7, "Не нашли нужное? Сделаем по вашим размерам")
    col_w = (PAGE_W - 16 - 12) / 3
    for i, (num, title, text) in enumerate(steps):
        x = PAGE_LEFT + 8 + i * (col_w + 6)
        pdf.set_xy(x, y + 22)
        pdf.set_font(FONT, "B", 16)
        pdf.ink(GOLD)
        pdf.cell(12, 7, num)
        pdf.set_xy(x + 13, y + 22.5)
        pdf.set_font(FONT, "B", 9.5)
        pdf.ink(WHITE)
        pdf.cell(col_w - 13, 5, title)
        pdf.set_xy(x + 13, y + 28)
        pdf.set_font(FONT, "", 7.8)
        pdf.ink(GOLD_LIGHT)
        pdf.multi_cell(col_w - 13, 3.9, text, align="L")
    pdf.fill(NAVY_2)
    pdf.rect(PAGE_LEFT + 8, y + h - 14, PAGE_W - 16, 9, "F", round_corners=True, corner_radius=4.5)
    pdf.set_xy(PAGE_LEFT + 8, y + h - 12.5)
    pdf.set_font(FONT, "B", 9)
    pdf.ink(GOLD_LIGHT)
    pdf.cell(PAGE_W - 16, 6, f"WhatsApp {shop_phone_text()}   ·   Instagram {SHOP_INSTAGRAM}", align="C")
    pdf.set_y(y + h + 4)


def build_catalog_pdf(products: list[dict], day: str = "") -> bytes:
    pdf = CatalogPDF(day=day)
    pdf.add_page()
    sections = _prepare(products)
    _cover(pdf, sections)

    if not sections:
        pdf.set_font(FONT, "", 12)
        pdf.ink(MUTED)
        pdf.cell(0, 10, "Каталог пока пуст — напишите нам, подберём решение под ваш интерьер.", align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        _how_to_order(pdf)
        return bytes(pdf.output())

    for index, (name, items) in enumerate(sections, start=1):
        rows = _card_rows(pdf, items)
        # Заголовок раздела не должен остаться внизу страницы без единой карточки.
        if pdf.get_y() + SECTION_H + rows[0][1] > pdf.page_break_trigger:
            pdf.add_page()
        _section_header(pdf, index, name, len(items))
        for pair, row_h in rows:
            if pdf.get_y() + row_h > pdf.page_break_trigger:
                pdf.add_page()
            y = pdf.get_y()
            for col, item in enumerate(pair):
                _card(pdf, item, PAGE_LEFT + col * (CARD_W + GAP), y, row_h)
            pdf.set_y(y + row_h + GAP)
        pdf.ln(3)

    _how_to_order(pdf)
    return bytes(pdf.output())
