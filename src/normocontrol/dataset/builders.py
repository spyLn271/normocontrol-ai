"""Генерация «идеально правильных» документов по профилю (python-docx).

Все параметры оформления берутся из профиля, поэтому правильный документ для одного профиля
(КРУ: одинарный интервал, правое поле 1 см) будет неправильным для другого (ГОСТ: 1,5 и 1,5 см).
"""

from __future__ import annotations

import io
import random
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any, Literal

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from normocontrol.dataset.content import (
    BIBLIOGRAPHY_ENTRIES,
    KK,
    ORDER_TEXT,
    RU,
    Vocabulary,
    paragraph_text,
)
from normocontrol.profiles.schema import HeadingRule, Profile

type Language = Literal["ru", "kk"]

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


@dataclass(slots=True)
class Anchors:
    """Ссылки на элементы сгенерированного документа — нужны мутациям."""

    body: list[Any] = field(default_factory=list)  # абзацы основного текста
    headings: dict[str, Any] = field(default_factory=dict)  # ключ → абзац заголовка
    sections: list[Any] = field(default_factory=list)  # заголовки нумерованных разделов
    toc: list[Any] = field(default_factory=list)
    figure_captions: list[Any] = field(default_factory=list)
    figure_images: list[Any] = field(default_factory=list)
    figure_refs: list[Any] = field(default_factory=list)
    table_captions: list[Any] = field(default_factory=list)
    tables: list[Any] = field(default_factory=list)
    table_refs: list[Any] = field(default_factory=list)
    bibliography: list[Any] = field(default_factory=list)
    citations: dict[int, Any] = field(default_factory=dict)  # номер → абзац первой ссылки
    requisites: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Generated:
    document: Any  # docx.Document
    anchors: Anchors
    profile: Profile
    language: Language


def tiny_png(width: int = 8, height: int = 6) -> bytes:
    """Минимальный валидный PNG без Pillow."""
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def set_font(element_owner: Any, name: str) -> None:
    """Задать шрифт во всех слотах и убрать ссылки на шрифты темы (иначе тема «победит»)."""
    rpr = element_owner.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn(f"w:{attribute}"), None)
    for slot in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{slot}"), name)


def add_page_field(paragraph: Any) -> None:
    field_element = OxmlElement("w:fldSimple")
    field_element.set(qn("w:instr"), "PAGE")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "2"
    run.append(text)
    field_element.append(run)
    paragraph._p.append(field_element)  # python-docx не умеет вставлять поля


class _Base:
    def __init__(self, profile: Profile, rng: random.Random) -> None:
        self.profile = profile
        self.rng = rng
        self.doc: Any = docx.Document()
        self.anchors = Anchors()
        body = profile.body_text
        self.font = body.font_family[0] if body and body.font_family else "Times New Roman"
        size = body.font_size_pt if body else None
        self.size = (size.recommended or size.min or 14) if size else 14
        self.spacing = body.line_spacing if body and body.line_spacing else 1.0
        self.indent = body.first_line_indent_cm if body and body.first_line_indent_cm else 1.25
        self.alignment = (
            _ALIGN.get(body.alignment or "justify", WD_ALIGN_PARAGRAPH.JUSTIFY)
            if body
            else WD_ALIGN_PARAGRAPH.JUSTIFY
        )
        self._setup_styles()
        self._setup_page()

    def _setup_styles(self) -> None:
        normal = self.doc.styles["Normal"]
        set_font(normal.element, self.font)
        normal.font.size = Pt(self.size)
        fmt = normal.paragraph_format
        fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        fmt.line_spacing = self.spacing
        fmt.first_line_indent = Cm(self.indent)
        fmt.alignment = self.alignment
        fmt.space_before = Pt(0)
        fmt.space_after = Pt(0)
        for name in ("Heading 1", "Heading 2"):
            style = self.doc.styles[name]
            set_font(style.element, self.font)
            style.font.size = Pt(self.size)
            style.font.bold = True
            style.font.italic = False
            style.font.color.rgb = RGBColor(0, 0, 0)
            style.paragraph_format.space_before = Pt(0)
            style.paragraph_format.space_after = Pt(self.size)
            style.paragraph_format.line_spacing = self.spacing

    def _setup_page(self) -> None:
        page = self.profile.page
        section = self.doc.sections[0]
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        margins = page.margins_cm if page else None
        if margins is not None:
            bump = 0.5 if page and page.margins_mode == "min" else 0.0
            section.left_margin = Cm(margins.left + bump)
            section.right_margin = Cm(margins.right + bump)
            section.top_margin = Cm(margins.top + bump)
            section.bottom_margin = Cm(margins.bottom + bump)
        numbering = page.numbering if page else None
        if numbering is not None and (numbering.required or self.multi_page):
            section.different_first_page_header_footer = not numbering.title_page_numbered
            container = section.header if numbering.position.startswith("top") else section.footer
            paragraph = container.paragraphs[0]
            paragraph.alignment = _ALIGN[numbering.position.split("-", 1)[1]]
            paragraph.paragraph_format.first_line_indent = Cm(0)
            add_page_field(paragraph)

    multi_page = True

    # ------------------------------------------------------------------ helpers

    def plain(
        self, text: str, *, align: str | None = None, indent: bool = False, bold: bool = False
    ) -> Any:
        paragraph = self.doc.add_paragraph()
        run = paragraph.add_run(text)
        run.bold = bold or None
        if align:
            paragraph.alignment = _ALIGN[align]
        if not indent:
            paragraph.paragraph_format.first_line_indent = Cm(0)
        return paragraph

    def body(self, text: str) -> Any:
        paragraph = self.doc.add_paragraph(text)
        self.anchors.body.append(paragraph)
        return paragraph

    def heading(self, text: str, level: int, rule: HeadingRule | None, *, new_page: bool) -> Any:
        paragraph = self.doc.add_heading(text, level=level)
        fmt = paragraph.paragraph_format
        if rule is not None and rule.alignment:
            paragraph.alignment = _ALIGN[rule.alignment]
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER or (rule and rule.indent == "none"):
            fmt.first_line_indent = Cm(0)
        else:
            fmt.first_line_indent = Cm(self.indent)
        fmt.page_break_before = new_page
        bold = True if rule is None or rule.bold is None else rule.bold
        for run in paragraph.runs:
            run.bold = bold
        return paragraph

    def save(self) -> bytes:
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


def _cased(text: str, rule: HeadingRule | None) -> str:
    if rule is not None and rule.case == "upper":
        return text.upper()
    return text


class ReportBuilder(_Base):
    """Курсовая / отчёт: титульный лист, содержание, разделы, рисунки, таблицы, литература."""

    def __init__(self, profile: Profile, rng: random.Random, language: Language = "ru") -> None:
        super().__init__(profile, rng)
        self.language: Language = language
        self.vocab: Vocabulary = KK if language == "kk" else RU
        headings = profile.headings
        self.structural_rule = headings.structural if headings else None
        self.section_rule = headings.section if headings else None
        self.subsection_rule = headings.subsection if headings else None
        self.figures = 0
        self.tables = 0
        self.citation = 0

    def build(self) -> Generated:
        vocab = self.vocab
        self._title_page()
        plan = self._plan()
        self._structural("toc", vocab.toc, new_page=False)
        for title in plan:
            self.anchors.toc.append(self.plain(f"{title}\t{self.rng.randint(3, 40)}"))
        self._structural("intro", vocab.intro)
        intro = self.body(f"{self._cite(paragraph_text(self.rng, vocab))} {self._cite('')}")
        self.anchors.citations[1] = self.anchors.citations[2] = intro
        self.body(paragraph_text(self.rng, vocab, 2))
        for number, (title, subsections) in enumerate(vocab.sections, start=1):
            self._section(number, title, subsections)
        self._structural("conclusion", vocab.conclusion)
        self.body(paragraph_text(self.rng, vocab, 3))
        self._structural("bibliography", vocab.bibliography)
        for number in range(1, self.citation + 1):
            dot = (
                "."
                if self.profile.bibliography and self.profile.bibliography.entry_number_trailing_dot
                else ""
            )
            entry = BIBLIOGRAPHY_ENTRIES[(number - 1) % len(BIBLIOGRAPHY_ENTRIES)]
            paragraph = self.doc.add_paragraph(f"{number}{dot} {entry}")
            self.anchors.bibliography.append(paragraph)
        return Generated(self.doc, self.anchors, self.profile, self.language)

    def _plan(self) -> list[str]:
        vocab = self.vocab
        titles = [vocab.intro]
        for number, (title, subsections) in enumerate(vocab.sections, start=1):
            titles.append(f"{number} {title}")
            titles.extend(f"{number}.{i} {sub}" for i, sub in enumerate(subsections, start=1))
        titles += [vocab.conclusion, vocab.bibliography]
        return [_cased(t, self.structural_rule) if not t[0].isdigit() else t for t in titles]

    def _title_page(self) -> None:
        lines = self.vocab.title_lines
        for index, line in enumerate(lines):
            paragraph = self.plain(line, align="center", bold=line.isupper())
            if index == len(lines) - 1:
                paragraph.add_run().add_break(WD_BREAK.PAGE)
        self.anchors.headings["title"] = self.doc.paragraphs[0]

    def _structural(self, key: str, text: str, *, new_page: bool = True) -> Any:
        paragraph = self.heading(
            _cased(text, self.structural_rule), 1, self.structural_rule, new_page=new_page
        )
        self.anchors.headings[key] = paragraph
        return paragraph

    def _cite(self, text: str) -> str:
        self.citation += 1
        return f"{text} [{self.citation}]".strip()

    def _section(self, number: int, title: str, subsections: tuple[str, ...]) -> None:
        heading = self.heading(f"{number} {title}", 1, self.section_rule, new_page=True)
        self.anchors.sections.append(heading)
        self.anchors.headings[f"section-{number}"] = heading
        for index, sub in enumerate(subsections, start=1):
            self.heading(f"{number}.{index} {sub}", 2, self.subsection_rule, new_page=False)
            paragraph = self.body(self._cite(paragraph_text(self.rng, self.vocab)))
            self.anchors.citations[self.citation] = paragraph
            if index == 1:
                self._figure()
            else:
                self._table()

    def _figure(self) -> None:
        self.figures += 1
        n = self.figures
        ref = self.body(
            f"{paragraph_text(self.rng, self.vocab, 2)} {self.vocab.figure_ref.format(n=n)}."
        )
        self.anchors.figure_refs.append(ref)
        self.doc.add_picture(io.BytesIO(tiny_png()), width=Cm(6))
        image = self.doc.paragraphs[-1]
        image.alignment = WD_ALIGN_PARAGRAPH.CENTER
        image.paragraph_format.first_line_indent = Cm(0)
        self.anchors.figure_images.append(image)
        figures = self.profile.figures
        align = figures.caption_alignment if figures and figures.caption_alignment else "center"
        caption = self.plain(f"{self.vocab.figure} {n} – Схема установки {n}", align=align)
        self.anchors.figure_captions.append(caption)
        self.body(paragraph_text(self.rng, self.vocab, 2))

    def _table(self) -> None:
        self.tables += 1
        n = self.tables
        ref = self.body(
            f"{paragraph_text(self.rng, self.vocab, 2)} {self.vocab.table_ref.format(n=n)}."
        )
        self.anchors.table_refs.append(ref)
        tables = self.profile.tables
        align = tables.caption_alignment if tables and tables.caption_alignment else "left"
        caption = self.plain(f"{self.vocab.table} {n} – Показатели качества воды", align=align)
        self.anchors.table_captions.append(caption)
        table = self.doc.add_table(rows=3, cols=3)
        table.style = "Table Grid"
        for row_index, row in enumerate(table.rows):
            for col_index, cell in enumerate(row.cells):
                cell.text = "Показатель" if row_index == 0 else f"{row_index}.{col_index}"
        self.anchors.tables.append(table)
        self.body(paragraph_text(self.rng, self.vocab, 2))


class OrderBuilder(_Base):
    """Приказ организации по Правилам документирования (одна страница)."""

    multi_page = False

    def build(self) -> Generated:
        text = ORDER_TEXT
        anchors = self.anchors
        anchors.requisites["org"] = self.plain(str(text["org"]), align="center", bold=True)
        anchors.requisites["type"] = self.plain(str(text["type"]), align="center", bold=True)
        anchors.requisites["date"] = self.plain(f"{text['date']}\t\t\t{text['number']}")
        anchors.requisites["place"] = self.plain(str(text["place"]), align="center")
        anchors.requisites["title"] = self.plain(str(text["title"]), align="left", bold=True)
        preamble = self.body(f"{text['preamble']} ")
        run = preamble.add_run("ПРИКАЗЫВАЮ:")
        run.bold = True
        anchors.requisites["prikazyvayu"] = preamble
        for point in text["points"]:
            self.body(str(point))
        anchors.requisites["signature"] = self.plain(str(text["signature"]), bold=True)
        return Generated(self.doc, anchors, self.profile, "ru")


def build_document(profile: Profile, rng: random.Random, language: Language = "ru") -> Generated:
    if profile.requisites is not None:  # служебные документы по Правилам документирования
        return OrderBuilder(profile, rng).build()
    return ReportBuilder(profile, rng, language).build()
