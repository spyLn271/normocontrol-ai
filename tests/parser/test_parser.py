from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from normocontrol.dataset.builders import add_page_field, set_font, tiny_png
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.parser.model import (
    Alignment,
    HeaderFooterKind,
    HeaderFooterVariant,
    LineSpacingRule,
    Orientation,
    ParagraphRole,
)
from normocontrol.parser.safety import InvalidDocumentError, validate_docx_bytes

MakeDocx = Callable[[Callable[[Any], None]], bytes]


def test_sections_margins_orientation_paper(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        section = doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.left_margin, section.right_margin = Cm(3), Cm(1.5)
        section.top_margin = section.bottom_margin = Cm(2)
        doc.add_paragraph("Текст")
        landscape = doc.add_section()
        landscape.orientation = WD_ORIENT.LANDSCAPE
        landscape.page_width, landscape.page_height = Cm(29.7), Cm(21)
        doc.add_paragraph("Широкая таблица")

    document = parse_docx(make_docx(fill))
    first, second = document.sections
    assert first.paper_size == "A4"
    assert first.orientation is Orientation.PORTRAIT
    assert first.margins.left_cm == pytest.approx(3.0, abs=0.01)
    assert first.margins.right_cm == pytest.approx(1.5, abs=0.01)
    assert second.orientation is Orientation.LANDSCAPE
    assert second.paper_size == "A4"
    assert [p.section_index for p in document.paragraphs if p.text] == [0, 1]


def test_paragraph_formatting_resolved(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        normal = doc.styles["Normal"]
        set_font(normal.element, "Times New Roman")
        normal.font.size = Pt(14)
        normal.paragraph_format.line_spacing = 1.5
        normal.paragraph_format.first_line_indent = Cm(1.25)
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        doc.add_paragraph("Основной текст документа на русском языке.")
        exact = doc.add_paragraph("Точный интервал")
        exact.paragraph_format.line_spacing = Pt(18)

    document = parse_docx(make_docx(fill))
    body, exact = document.paragraphs
    assert body.font.name == "Times New Roman"
    assert body.font.size_pt == 14
    assert body.line_spacing.rule is LineSpacingRule.MULTIPLE
    assert body.line_spacing.value == 1.5
    assert body.first_line_indent_cm == pytest.approx(1.25, abs=0.01)
    assert body.alignment is Alignment.JUSTIFY
    assert exact.line_spacing.rule is LineSpacingRule.EXACT
    assert exact.line_spacing.value == 18


def test_dominant_font_by_characters(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        set_font(doc.styles["Normal"].element, "Times New Roman")
        paragraph = doc.add_paragraph("Длинный фрагмент основного текста ")
        run = paragraph.add_run("Arial")
        set_font(run._r, "Arial")

    paragraph = parse_docx(make_docx(fill)).paragraphs[0]
    assert paragraph.font.name == "Times New Roman"
    assert paragraph.fonts_used == ["Arial", "Times New Roman"]


def test_hidden_deleted_and_hyperlink_text(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        paragraph = doc.add_paragraph("Видимый ")
        hidden = paragraph.add_run("скрытый")
        hidden.font.hidden = True
        deleted = OxmlElement("w:del")
        run = OxmlElement("w:r")
        text = OxmlElement("w:delText")
        text.text = "удалённый"
        run.append(text)
        deleted.append(run)
        paragraph._p.append(deleted)
        link = OxmlElement("w:hyperlink")
        link_run = OxmlElement("w:r")
        link_text = OxmlElement("w:t")
        link_text.text = "ссылка"
        link_run.append(link_text)
        link.append(link_run)
        paragraph._p.append(link)

    assert parse_docx(make_docx(fill)).paragraphs[0].text == "Видимый ссылка"


def test_page_field_in_footer_and_title_page(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        section = doc.sections[0]
        section.different_first_page_header_footer = True
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_page_field(footer)
        doc.add_paragraph("Текст")

    document = parse_docx(make_docx(fill))
    footer = next(
        hf
        for hf in document.headers_footers
        if hf.kind is HeaderFooterKind.FOOTER and hf.variant is HeaderFooterVariant.DEFAULT
    )
    assert footer.has_page_field
    assert footer.page_field_alignment is Alignment.CENTER
    assert document.sections[0].title_page


def test_page_field_alignment_by_tabs(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        footer = doc.sections[0].footer.paragraphs[0]
        footer.add_run("\t")
        add_page_field(footer)

    hf = next(h for h in parse_docx(make_docx(fill)).headers_footers if h.has_page_field)
    assert hf.page_field_alignment is Alignment.CENTER


def test_complex_page_field_detected(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        footer = doc.sections[0].footer.paragraphs[0]
        for kind, instr in (("begin", None), (None, " PAGE \\* MERGEFORMAT "), ("end", None)):
            run = OxmlElement("w:r")
            if kind:
                char = OxmlElement("w:fldChar")
                char.set(qn("w:fldCharType"), kind)
                run.append(char)
            else:
                text = OxmlElement("w:instrText")
                text.text = instr
                run.append(text)
            footer._p.append(run)

    assert any(hf.has_page_field for hf in parse_docx(make_docx(fill)).headers_footers)


def test_numpages_is_not_page_field(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        footer = doc.sections[0].footer.paragraphs[0]
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "NUMPAGES")
        footer._p.append(field)

    assert not any(hf.has_page_field for hf in parse_docx(make_docx(fill)).headers_footers)


def test_tables_images_and_roles(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        doc.add_paragraph("Таблица 1 – Показатели")
        table = doc.add_table(rows=2, cols=3)
        table.cell(0, 0).text = "Ячейка"
        doc.add_paragraph("После таблицы")
        doc.add_picture(io.BytesIO(tiny_png()), width=Cm(5))
        doc.add_paragraph("Рисунок 1 – Схема")

    document = parse_docx(make_docx(fill))
    assert len(document.tables) == 1
    table = document.tables[0]
    assert (table.rows, table.cols) == (2, 3)
    caption = document.paragraphs[table.preceding_paragraph_index]
    assert caption.role is ParagraphRole.TABLE_CAPTION
    assert document.paragraphs[table.following_paragraph_index or 0].text == "После таблицы"
    cells = [p for p in document.paragraphs if p.in_table]
    assert all(p.role is ParagraphRole.TABLE_CELL for p in cells)
    assert len(document.images) == 1
    assert document.images[0].width_cm == pytest.approx(5, abs=0.01)
    image_paragraph = document.paragraph(document.images[0].paragraph_id)
    assert image_paragraph is not None
    assert image_paragraph.role is ParagraphRole.IMAGE
    assert document.paragraphs[-1].role is ParagraphRole.FIGURE_CAPTION


def test_title_page_toc_headings_bibliography(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        doc.add_paragraph("УНИВЕРСИТЕТ").alignment = WD_ALIGN_PARAGRAPH.CENTER
        last = doc.add_paragraph("Костанай, 2026")
        last.add_run().add_break(WD_BREAK.PAGE)
        doc.add_heading("Содержание", level=1)
        doc.add_paragraph("Введение\t3")
        doc.add_paragraph("1 Обзор литературы\t5")
        intro = doc.add_heading("Введение", level=1)
        intro.paragraph_format.page_break_before = True
        doc.add_paragraph("Текст введения [1].")
        bold = doc.add_paragraph()
        bold.add_run("1 Обзор литературы").bold = True
        doc.add_paragraph("Текст раздела.")
        doc.add_paragraph("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ")
        doc.add_paragraph("1 Иванов И.И. Книга. – М.: Наука, 2020. – 100 с.")

    document = parse_docx(make_docx(fill))
    roles = [(p.text.split("\t")[0][:20], p.role) for p in document.paragraphs]
    assert roles[0][1] is ParagraphRole.TITLE_PAGE
    assert roles[1][1] is ParagraphRole.TITLE_PAGE
    assert roles[2] == ("Содержание", ParagraphRole.HEADING)
    assert roles[3][1] is ParagraphRole.TOC
    assert roles[4][1] is ParagraphRole.TOC
    assert roles[5] == ("Введение", ParagraphRole.HEADING)
    heuristic = document.paragraphs[7]
    assert heuristic.role is ParagraphRole.HEADING
    assert heuristic.heading_level == 1
    assert document.paragraphs[9].role is ParagraphRole.HEADING  # структурный заголовок без стиля
    assert document.paragraphs[10].role is ParagraphRole.BIBLIOGRAPHY_ENTRY


def test_toc_field_paragraphs(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        first = doc.add_paragraph()
        for kind, instr, text in (
            ("begin", None, None),
            (None, 'TOC \\o "1-3"', None),
            ("separate", None, None),
        ):
            run = OxmlElement("w:r")
            if kind:
                char = OxmlElement("w:fldChar")
                char.set(qn("w:fldCharType"), kind)
                run.append(char)
            if instr:
                element = OxmlElement("w:instrText")
                element.text = instr
                run.append(element)
            del text
            first._p.append(run)
        first.add_run("Введение\t3")
        doc.add_paragraph("Заключение\t9")
        last = doc.add_paragraph()
        end = OxmlElement("w:r")
        char = OxmlElement("w:fldChar")
        char.set(qn("w:fldCharType"), "end")
        end.append(char)
        last._p.append(end)
        doc.add_paragraph("Обычный текст после оглавления")

    document = parse_docx(make_docx(fill))
    assert [p.in_toc_field for p in document.paragraphs] == [True, True, True, False]
    assert document.paragraphs[0].role is ParagraphRole.TOC
    assert document.paragraphs[3].role is ParagraphRole.BODY


def test_rendered_page_breaks_give_page_numbers(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        doc.add_paragraph("Страница 1")
        second = doc.add_paragraph()
        run = second.add_run()
        run._r.append(OxmlElement("w:lastRenderedPageBreak"))
        second.add_run("Страница 2")
        doc.add_paragraph("Тоже страница 2")

    document = parse_docx(make_docx(fill))
    assert [p.page_estimate for p in document.paragraphs] == [1, 2, 2]
    assert document.stats.page_source == "word_render"


def test_explicit_breaks_give_page_numbers(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        doc.add_paragraph("1").add_run().add_break(WD_BREAK.PAGE)
        doc.add_paragraph("2")
        third = doc.add_paragraph("3")
        third.paragraph_format.page_break_before = True

    document = parse_docx(make_docx(fill))
    assert [p.page_estimate for p in document.paragraphs] == [1, 2, 3]
    assert document.stats.pages_estimated == 3
    assert document.stats.page_source == "breaks"


def test_numbered_list_detected(make_docx: MakeDocx) -> None:
    def fill(doc: Any) -> None:
        doc.add_paragraph("Пункт списка", style="List Number")

    paragraph = parse_docx(make_docx(fill)).paragraphs[0]
    assert paragraph.numbering is not None
    assert paragraph.role is ParagraphRole.LIST_ITEM


def test_json_roundtrip(make_docx: MakeDocx) -> None:
    from normocontrol.parser.model import Document  # noqa: PLC0415

    document = parse_docx(make_docx(lambda d: d.add_paragraph("Текст")), "a.docx")
    restored = Document.model_validate_json(document.model_dump_json())
    assert restored == document
    assert restored.paragraph("p-0") is not None


# ---------------------------------------------------------------------- safety


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "пустой"),
        (b"%PDF-1.7", "ZIP"),
        (b"PK\x03\x04broken", "Повреждённый"),
        (_zip({"content.xml": b"<x/>"}), "word/document.xml"),
    ],
)
def test_invalid_documents_rejected(data: bytes, message: str) -> None:
    with pytest.raises(InvalidDocumentError, match=message):
        validate_docx_bytes(data)


def test_zip_bomb_rejected() -> None:
    bomb = _zip({"word/document.xml": b"<a/>", "word/media/big.bin": b"\0" * (20 * 1024 * 1024)})
    with pytest.raises(InvalidDocumentError, match="zip-бомба"):
        validate_docx_bytes(bomb)


def test_size_limit_after_unpacking() -> None:
    data = _zip({"word/document.xml": b"<a/>" * 1000}, compression=zipfile.ZIP_STORED)
    with pytest.raises(InvalidDocumentError, match="слишком большой"):
        validate_docx_bytes(data, max_uncompressed_bytes=100)


def test_external_entities_not_resolved() -> None:
    from normocontrol.parser.xml import parse_xml  # noqa: PLC0415

    payload = (
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>'
    )
    element = parse_xml(payload)
    assert "root:" not in (element.text or "")
