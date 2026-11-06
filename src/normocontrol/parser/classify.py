"""Определение роли каждого абзаца: титульный лист, заголовок, подпись, литература, текст…

Роль нужна правилам: например, требования к шрифту основного текста нельзя применять к
титульному листу, оглавлению или ячейкам таблиц — иначе будут ложные срабатывания.
"""

from __future__ import annotations

from normocontrol.parser.model import HeadingSource, Paragraph, ParagraphRole, Table
from normocontrol.parser.vocabulary import (
    FIGURE_CAPTION_RE,
    NUMBERED_HEADING_RE,
    TABLE_CAPTION_RE,
    TOC_LINE_RE,
    heading_number,
    is_bibliography_heading,
    is_structural_heading,
    is_toc_heading,
)

MAX_HEADING_CHARS = 200
MAX_CAPTION_CHARS = 300
MAX_TITLE_PAGE_PARAGRAPHS = 80
_TOC_STYLE_PREFIXES = ("toc ", "оглавление ", "содержание ")


def classify_paragraphs(paragraphs: list[Paragraph], tables: list[Table]) -> list[Paragraph]:
    del tables  # таблицы уже отражены в in_table у абзацев; параметр — для будущих эвристик
    headings = _detect_headings(paragraphs)
    toc = _detect_toc(paragraphs, headings)
    title_page = _detect_title_page(paragraphs, headings)
    bibliography = _detect_bibliography(paragraphs, headings)

    result: list[Paragraph] = []
    for paragraph in paragraphs:
        role = _role(paragraph, headings, toc, title_page, bibliography)
        update: dict[str, object] = {"role": role}
        heading = headings.get(paragraph.index)
        if role is ParagraphRole.HEADING and heading is not None:
            update.update(is_heading=True, heading_level=heading[0], heading_source=heading[1])
        elif paragraph.is_heading:
            update.update(is_heading=False, heading_level=None, heading_source=None)
        result.append(paragraph.model_copy(update=update))
    return result


def _role(
    paragraph: Paragraph,
    headings: dict[int, tuple[int, HeadingSource]],
    toc: set[int],
    title_page: set[int],
    bibliography: set[int],
) -> ParagraphRole:
    text = paragraph.text.strip()
    if paragraph.in_table:
        return (
            ParagraphRole.TITLE_PAGE if paragraph.index in title_page else ParagraphRole.TABLE_CELL
        )
    if paragraph.index in title_page:
        return ParagraphRole.TITLE_PAGE
    if paragraph.index in toc:
        return ParagraphRole.TOC
    if not text:
        if paragraph.has_drawing:
            return ParagraphRole.IMAGE
        return ParagraphRole.FORMULA if paragraph.has_formula else ParagraphRole.EMPTY
    if len(text) <= MAX_CAPTION_CHARS and FIGURE_CAPTION_RE.match(text):
        return ParagraphRole.FIGURE_CAPTION
    if len(text) <= MAX_CAPTION_CHARS and TABLE_CAPTION_RE.match(text):
        return ParagraphRole.TABLE_CAPTION
    if paragraph.index in headings:
        return ParagraphRole.HEADING
    if paragraph.has_formula and len(text) < 40:
        return ParagraphRole.FORMULA
    if paragraph.index in bibliography:
        return ParagraphRole.BIBLIOGRAPHY_ENTRY
    if paragraph.numbering is not None:
        return ParagraphRole.LIST_ITEM
    return ParagraphRole.BODY


def _detect_headings(paragraphs: list[Paragraph]) -> dict[int, tuple[int, HeadingSource]]:
    headings: dict[int, tuple[int, HeadingSource]] = {}
    for position, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if paragraph.in_table or not text or _is_toc_style(paragraph) or paragraph.in_toc_field:
            continue
        if len(text) > MAX_HEADING_CHARS:
            continue
        if FIGURE_CAPTION_RE.match(text) or TABLE_CAPTION_RE.match(text):
            continue
        if paragraph.is_heading and paragraph.heading_level is not None:
            assert paragraph.heading_source is not None  # noqa: S101
            headings[paragraph.index] = (paragraph.heading_level, paragraph.heading_source)
            continue
        if is_structural_heading(text) and len(text) <= 80:
            headings[paragraph.index] = (1, HeadingSource.HEURISTIC)
            continue
        number = heading_number(text)
        if (
            number is not None
            and paragraph.font.bold
            and not text.endswith((":", ";", ","))
            and paragraph.numbering is None
            and _has_body_after(paragraphs, position)
        ):
            headings[paragraph.index] = (number.count(".") + 1, HeadingSource.HEURISTIC)
    return headings


def _has_body_after(paragraphs: list[Paragraph], position: int) -> bool:
    for paragraph in paragraphs[position + 1 : position + 4]:
        if paragraph.text.strip():
            return not paragraph.font.bold or bool(NUMBERED_HEADING_RE.match(paragraph.text))
    return False


def _is_toc_style(paragraph: Paragraph) -> bool:
    name = (paragraph.style_name or "").casefold()
    return name.startswith(_TOC_STYLE_PREFIXES)


def _detect_toc(
    paragraphs: list[Paragraph], headings: dict[int, tuple[int, HeadingSource]]
) -> set[int]:
    toc = {p.index for p in paragraphs if not p.in_table and (_is_toc_style(p) or p.in_toc_field)}
    # Ручное содержание: строки «Заголовок …… 5» после заголовка «Содержание».
    for position, paragraph in enumerate(paragraphs):
        if paragraph.index not in headings or not is_toc_heading(paragraph.text):
            continue
        for candidate in paragraphs[position + 1 :]:
            if candidate.in_table:
                continue
            text = candidate.text.strip()
            if not text:
                continue
            if TOC_LINE_RE.match(text) and not candidate.ends_section:
                toc.add(candidate.index)
                headings.pop(candidate.index, None)
                if candidate.contains_page_break:
                    break
                continue
            break
        break
    return toc


def _detect_title_page(
    paragraphs: list[Paragraph], headings: dict[int, tuple[int, HeadingSource]]
) -> set[int]:
    """Титульный лист — всё до первого разрыва страницы, если после него идут разделы."""
    structural = [
        p.index for p in paragraphs if p.index in headings and is_structural_heading(p.text)
    ]
    if not structural:
        return set()
    first_structural = structural[0]
    boundary: int | None = None
    for paragraph in paragraphs[: min(len(paragraphs), MAX_TITLE_PAGE_PARAGRAPHS)]:
        if paragraph.index >= first_structural:
            break
        if paragraph.page_break_before and paragraph.index > 0:
            boundary = paragraph.index - 1
            break
        if paragraph.contains_page_break or paragraph.ends_section:
            boundary = paragraph.index
            break
    if boundary is None:
        candidate = paragraphs[first_structural] if first_structural < len(paragraphs) else None
        if candidate is not None and candidate.page_break_before and first_structural > 0:
            boundary = first_structural - 1
    if boundary is None:
        return set()
    title = {p.index for p in paragraphs[: boundary + 1]}
    for index in list(title):
        headings.pop(index, None)
    return title


def _detect_bibliography(
    paragraphs: list[Paragraph], headings: dict[int, tuple[int, HeadingSource]]
) -> set[int]:
    entries: set[int] = set()
    inside = False
    for paragraph in paragraphs:
        if paragraph.index in headings:
            inside = is_bibliography_heading(paragraph.text)
            continue
        if inside and not paragraph.in_table and paragraph.text.strip():
            entries.add(paragraph.index)
    return entries
