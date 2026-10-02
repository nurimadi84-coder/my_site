"""Счёт на оплату по заказу (fpdf2, генерация в памяти)."""

from __future__ import annotations

from fpdf.enums import TableCellFillMode
from fpdf.fonts import FontFace

from core.settings import get_seller_settings, seller_is_complete

from .common import (
    BRONZE,
    FONT,
    GOLD,
    GOLD_LIGHT,
    INK,
    IVORY,
    MUTED,
    NAVY,
    PAGE_LEFT,
    PAGE_RIGHT,
    PAGE_W,
    SAND,
    SHOP_NAME,
    WHITE,
    BasePDF,
    clean_text,
    format_amount,
    price_value,
    shop_date,
    shop_phone_text,
)

ROW_LINE = 6


def _field(seller: dict, key: str, limit: int) -> str:
    return clean_text(seller.get(key), limit) or "—"


def invoice_number(order: dict) -> str:
    try:
        seq = int(order.get("seq") or 0)
    except (TypeError, ValueError):
        seq = 0
    return f"SF-{seq:05d}" if seq > 0 else f"SF-{clean_text(order.get('id'), 16) or '00000'}"


# --- сумма прописью -----------------------------------------------------------

_ONES = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
_ONES_F = ["", "одна", "две"] + _ONES[3:]
_TEENS = [
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
    "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
]
_TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
_HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]
_SCALES = [
    (("", "", ""), False),
    (("тысяча", "тысячи", "тысяч"), True),
    (("миллион", "миллиона", "миллионов"), False),
    (("миллиард", "миллиарда", "миллиардов"), False),
    (("триллион", "триллиона", "триллионов"), False),
]


def _plural(n: int, forms: tuple[str, str, str]) -> str:
    if 11 <= n % 100 <= 14:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if 2 <= n % 10 <= 4:
        return forms[1]
    return forms[2]


def _triad(n: int, feminine: bool) -> list[str]:
    words = [_HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_ONES_F if feminine else _ONES)[rest % 10])
    return [w for w in words if w]


def amount_in_words(value: int) -> str:
    value = int(value)
    if value <= 0:
        return "Ноль"
    if value >= 1000 ** len(_SCALES):
        return f"{value:,}".replace(",", " ")
    parts: list[str] = []
    for index, (forms, feminine) in enumerate(_SCALES):
        triad = (value // 1000 ** index) % 1000
        if not triad:
            continue
        chunk = _triad(triad, feminine)
        if forms[0]:
            chunk.append(_plural(triad, forms))
        parts = chunk + parts
    text = " ".join(parts)
    return text[:1].upper() + text[1:]


# --- документ -----------------------------------------------------------------

def _order_lines(order: dict) -> list[dict]:
    lines = []
    for raw in order.get("items") or []:
        if not isinstance(raw, dict):
            continue
        try:
            qty = int(raw.get("qty") or 1)
        except (TypeError, ValueError, OverflowError):
            raise CorruptedOrderError(f"позиция «{raw.get('title')}»: количество {raw.get('qty')!r} не число") from None
        if not 1 <= qty <= 999:
            raise CorruptedOrderError(f"позиция «{raw.get('title')}»: количество {qty} вне 1–999")
        lines.append({
            "title": clean_text(raw.get("title"), 300) or "Позиция",
            "qty": qty,
            "price": price_value(raw.get("price")),
            "currency": str(raw.get("currency") or "KZT"),
        })
    if not lines:
        # Заявка без позиций (форма «Связаться», калькулятор): в счёт идёт текст заявки без строк с контактами.
        text = "\n".join(
            line for line in str(order.get("message") or order.get("wa_text") or "").splitlines()
            if not line.strip().lower().startswith(("имя:", "телефон:"))
        )
        title = clean_text(text, 300) or "Работы по заявке"
        lines.append({"title": title, "qty": 1, "price": None, "currency": "KZT"})
    return lines


class InvoicePDF(BasePDF):
    def __init__(self, title: str, footer_text: str) -> None:
        super().__init__(title)
        self.footer_text = footer_text
        self.set_auto_page_break(auto=True, margin=20)

    def footer(self) -> None:
        self.brand_footer(self.footer_text)


BAND_H = 40
LOGO_H = 24


def _rows_height(pdf: BasePDF, width: float, rows: list[tuple]) -> float:
    """rows: (стиль, кегль, цвет, текст, высота строки). Высота блока без отрисовки."""
    total = 0.0
    for style, size, _rgb, text, line_h in rows:
        if not text:
            continue
        pdf.set_font(FONT, style, size)
        total += len(pdf.multi_cell(width, line_h, text, dry_run=True, output="LINES")) * line_h
    return total


def _draw_rows(pdf: BasePDF, x: float, y: float, width: float, rows: list[tuple]) -> float:
    pdf.set_xy(x, y)
    for style, size, rgb, text, line_h in rows:
        if not text:
            continue
        pdf.set_x(x)
        pdf.set_font(FONT, style, size)
        pdf.ink(rgb)
        pdf.multi_cell(width, line_h, text, align="L", new_x="LEFT", new_y="NEXT")
    return pdf.get_y()


def _header_band(pdf: InvoicePDF, seller: dict, number: str, date: str) -> None:
    pdf.fill(NAVY)
    pdf.rect(0, 0, 210, BAND_H, "F")
    pdf.fill(GOLD)
    pdf.rect(0, BAND_H, 210, 1.2, "F")

    logo_w = pdf.draw_logo(PAGE_LEFT, (BAND_H - LOGO_H) / 2, LOGO_H)
    text_x = PAGE_LEFT + (logo_w + 6 if logo_w else 0)
    right_w = 72
    text_w = PAGE_RIGHT - right_w - 4 - text_x

    pdf.label(text_x, 8, text_w, "Корпусная мебель на заказ")
    contacts = " · ".join(
        x for x in (
            f"БИН {clean_text(seller.get('bin'), 20)}" if seller.get("bin") else "",
            f"тел. {clean_text(seller.get('phone'), 40)}" if seller.get("phone") else "",
        ) if x
    )
    _draw_rows(pdf, text_x, 12.5, text_w, [
        ("B", 13, WHITE, clean_text(seller.get("name"), 70) or SHOP_NAME, 6),
        ("", 7.5, GOLD_LIGHT, contacts, 4),
        ("", 7.5, GOLD_LIGHT, clean_text(seller.get("address"), 90), 4),
    ])

    right_x = PAGE_RIGHT - right_w
    pdf.label(right_x, 8, right_w, "Документ", align="R")
    pdf.set_xy(right_x, 12.5)
    pdf.set_font(FONT, "B", 15)
    pdf.ink(WHITE)
    pdf.cell(right_w, 8, "СЧЁТ НА ОПЛАТУ", align="R")
    pdf.set_xy(right_x, 21)
    pdf.set_font(FONT, "B", 12)
    pdf.ink(GOLD)
    pdf.cell(right_w, 6, f"№ {number}", align="R")
    pdf.set_xy(right_x, 27.5)
    pdf.set_font(FONT, "", 8.5)
    pdf.ink(GOLD_LIGHT)
    pdf.cell(right_w, 5, f"от {date}", align="R")

    pdf.set_y(BAND_H + 7)


def _sample_banner(pdf: InvoicePDF) -> None:
    y = pdf.get_y()
    pdf.set_fill_color(253, 236, 234)
    pdf.set_draw_color(200, 60, 50)
    pdf.set_line_width(0.3)
    pdf.rect(PAGE_LEFT, y, PAGE_W, 10, "DF", round_corners=True, corner_radius=2)
    pdf.set_xy(PAGE_LEFT, y + 2.5)
    pdf.set_font(FONT, "B", 8.5)
    pdf.set_text_color(180, 40, 30)
    pdf.cell(PAGE_W, 5, "ОБРАЗЕЦ — реквизиты продавца не заполнены (Кабинет → Реквизиты для счетов). Не отправляйте клиенту.",
             align="C")
    pdf.set_y(y + 15)


def _card(pdf: InvoicePDF, x: float, y: float, w: float, h: float, title: str, rows: list[tuple]) -> None:
    pdf.fill(IVORY)
    pdf.rect(x, y, w, h, "F", round_corners=True, corner_radius=2.5)
    pdf.fill(GOLD)
    pdf.rect(x, y + 3, 1.2, h - 6, "F")
    pdf.label(x + 6, y + 4, w - 10, title, BRONZE)
    _draw_rows(pdf, x + 6, y + 9, w - 11, rows)


def _parties(pdf: InvoicePDF, seller: dict, order: dict, date: str) -> None:
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    gap = 6
    w = (PAGE_W - gap) / 2
    seller_rows = [
        ("B", 10.5, INK, _field(seller, "name", 120), 5.5),
        ("", 8.5, MUTED, f"БИН/ИИН: {_field(seller, 'bin', 20)}", 4.6),
        ("", 8.5, MUTED, clean_text(seller.get("address"), 160), 4.6),
        ("", 8.5, MUTED, f"Тел.: {clean_text(seller.get('phone'), 40)}" if seller.get("phone") else "", 4.6),
    ]
    phone = clean_text(customer.get("phone"), 40)
    buyer_rows = [
        ("B", 10.5, INK, clean_text(customer.get("name"), 120) or "Частное лицо", 5.5),
        ("", 8.5, MUTED, f"Тел.: {phone}" if phone else "", 4.6),
        ("", 8.5, MUTED, f"Основание: заказ {clean_text(order.get('id'), 32)} от {date}", 4.6),
    ]
    inner = w - 11
    h = max(_rows_height(pdf, inner, seller_rows), _rows_height(pdf, inner, buyer_rows)) + 14
    y = pdf.get_y()
    _card(pdf, PAGE_LEFT, y, w, h, "Поставщик", seller_rows)
    _card(pdf, PAGE_LEFT + w + gap, y, w, h, "Покупатель", buyer_rows)
    pdf.set_y(y + h + 7)


def _requisites(pdf: InvoicePDF, seller: dict) -> None:
    pdf.label(PAGE_LEFT, pdf.get_y(), PAGE_W, "Платёжные реквизиты", BRONZE)
    y = pdf.get_y() + 5.5
    widths = (80, 70, 40)
    grid = [
        [("Бенефициар", f"{_field(seller, 'name', 120)}\nБИН {_field(seller, 'bin', 20)}"),
         ("ИИК (IBAN)", _field(seller, "iban", 40)),
         ("Кбе", _field(seller, "kbe", 4))],
        [("Банк бенефициара", _field(seller, "bank", 120)),
         ("БИК", _field(seller, "bik", 20)),
         ("КНП", _field(seller, "knp", 6))],
    ]
    pdf.stroke(SAND, 0.3)
    for row in grid:
        heights = [_rows_height(pdf, w - 6, [("B", 9.5, INK, value, 4.8)]) for w, (_, value) in zip(widths, row)]
        row_h = max(heights) + 10
        x = PAGE_LEFT
        for w, (title, value) in zip(widths, row):
            pdf.fill(WHITE)
            pdf.rect(x, y, w, row_h, "DF")
            pdf.label(x + 3, y + 2.5, w - 6, title, MUTED)
            _draw_rows(pdf, x + 3, y + 7, w - 6, [("B", 9.5, INK, value, 4.8)])
            x += w
        y += row_h
    pdf.stroke(GOLD, 0.6)
    pdf.line(PAGE_LEFT, y, PAGE_RIGHT, y)
    pdf.set_y(y + 9)


def _items_table(pdf: InvoicePDF, lines: list[dict]) -> tuple[dict[str, int], int]:
    totals: dict[str, int] = {}
    unpriced = 0
    pdf.set_font(FONT, "", 9)
    pdf.ink(INK)
    pdf.stroke(SAND, 0.2)
    with pdf.table(
        width=PAGE_W,
        col_widths=(10, 94, 20, 33, 33),
        text_align=("CENTER", "LEFT", "CENTER", "RIGHT", "RIGHT"),
        line_height=ROW_LINE,
        headings_style=FontFace(emphasis="BOLD", color=WHITE, fill_color=NAVY, size_pt=8.5),
        cell_fill_color=IVORY,
        cell_fill_mode=TableCellFillMode.EVEN_ROWS,
        borders_layout="HORIZONTAL_LINES",
        padding=2,
    ) as table:
        head = table.row()
        for title in ("№", "Наименование товара / услуги", "Кол-во", "Цена", "Сумма"):
            head.cell(title)
        for index, line in enumerate(lines, start=1):
            row = table.row()
            row.cell(str(index))
            row.cell(line["title"])
            row.cell(f"{line['qty']} шт.")
            if line["price"] is None:
                unpriced += 1
                row.cell("по запросу")
                row.cell("—")
            else:
                amount = line["price"] * line["qty"]
                totals[line["currency"]] = totals.get(line["currency"], 0) + amount
                row.cell(format_amount(line["price"], line["currency"]))
                row.cell(format_amount(amount, line["currency"]))
    return totals, unpriced


def _totals(pdf: InvoicePDF, seller: dict, lines: list[dict], totals: dict[str, int], unpriced: int) -> None:
    pdf.ln(6)
    amounts = [format_amount(v, c) for c, v in totals.items()] or ["по согласованию"]
    box_w = 78
    box_h = 11 + 8 * len(amounts)
    if pdf.get_y() + box_h + 10 > pdf.page_break_trigger:
        pdf.add_page()
    y = pdf.get_y()
    box_x = PAGE_RIGHT - box_w

    pdf.fill(NAVY)
    pdf.rect(box_x, y, box_w, box_h, "F", round_corners=True, corner_radius=2.5)
    pdf.label(box_x + 5, y + 4, box_w - 10, "Итого к оплате", GOLD_LIGHT, align="R")
    pdf.set_font(FONT, "B", 15)
    pdf.ink(WHITE)
    for i, amount in enumerate(amounts):
        pdf.set_xy(box_x + 5, y + 9 + 8 * i)
        pdf.cell(box_w - 10, 8, amount, align="R")
    if seller.get("vat_note"):
        pdf.set_xy(box_x, y + box_h + 1.5)
        pdf.set_font(FONT, "", 7.5)
        pdf.ink(MUTED)
        pdf.cell(box_w, 4, clean_text(seller["vat_note"], 60), align="R")

    left_w = PAGE_W - box_w - 8
    summary = f"Всего наименований {len(lines)}"
    if totals:
        summary += ", на сумму " + ", ".join(format_amount(v, c) for c, v in totals.items())
    rows = [("", 9, INK, summary, 5)]
    if len(totals) == 1 and "KZT" in totals:
        rows.append(("B", 9.5, INK, f"{amount_in_words(totals['KZT'])} тенге 00 тиын", 5))
    if unpriced:
        rows.append(("", 8, BRONZE,
                     f"Позиций с ценой по запросу: {unpriced}. Итоговая сумма будет уточнена после согласования.", 4.5))
    rows.append(("", 7.5, MUTED, "Счёт действителен 5 банковских дней. Оплата означает согласие с условиями заказа.", 4.2))
    bottom = _draw_rows(pdf, PAGE_LEFT, y + 1, left_w, rows)
    pdf.set_y(max(bottom, y + box_h + 6) + 4)


def _signatures(pdf: InvoicePDF, seller: dict) -> None:
    if pdf.get_y() + 38 > pdf.page_break_trigger:
        pdf.add_page()
    pdf.ln(8)
    y = pdf.get_y()
    signer = clean_text(seller.get("signer"), 60)
    for x, title, name in ((PAGE_LEFT, "Руководитель", signer), (PAGE_LEFT + 76, "Бухгалтер", "")):
        pdf.stroke(INK, 0.3)
        pdf.line(x, y + 10, x + 60, y + 10)
        if name:
            pdf.set_xy(x, y + 4.5)
            pdf.set_font(FONT, "", 9)
            pdf.ink(INK)
            pdf.cell(60, 5, f"/ {name} /", align="R")
        pdf.label(x, y + 11.5, 60, title, MUTED)

    cx, cy, r = PAGE_RIGHT - 16, y + 9, 13
    pdf.stroke(GOLD, 0.5)
    pdf.set_dash_pattern(dash=1.2, gap=1)
    pdf.ellipse(cx - r, cy - r, 2 * r, 2 * r)
    pdf.set_dash_pattern()
    pdf.set_xy(cx - r, cy - 2.5)
    pdf.set_font(FONT, "B", 9)
    pdf.ink(GOLD)
    pdf.cell(2 * r, 5, "М.П.", align="C")
    pdf.set_y(y + 26)


class CorruptedOrderError(ValueError):
    """Позиции заказа в базе повреждены: счёт с пустой таблицей формировать нельзя."""


def build_invoice_pdf(order: dict, seller: dict | None = None) -> bytes:
    """InvalidDateError / CorruptedOrderError — документ не формируется."""
    if order.get("items_corrupted"):
        raise CorruptedOrderError(f"позиции заказа {order.get('id')} повреждены в базе")
    seller = seller or get_seller_settings()
    number = invoice_number(order)
    date = shop_date(order.get("created_at"))
    lines = _order_lines(order)
    phone = clean_text(seller.get("phone"), 40) or shop_phone_text()

    pdf = InvoicePDF(f"Счёт на оплату № {number}", f"{SHOP_NAME} · {phone} · Счёт № {number} от {date}")
    pdf.add_page()

    _header_band(pdf, seller, number, date)
    if not seller_is_complete(seller):
        _sample_banner(pdf)
    _parties(pdf, seller, order, date)
    _requisites(pdf, seller)
    totals, unpriced = _items_table(pdf, lines)
    _totals(pdf, seller, lines, totals, unpriced)
    _signatures(pdf, seller)

    return bytes(pdf.output())
