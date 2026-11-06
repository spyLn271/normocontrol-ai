"""Парсер ``.docx`` → :class:`~normocontrol.parser.model.Document`."""

from __future__ import annotations

import io
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from normocontrol.parser.blocks import (
    ParagraphBlock,
    TableEnd,
    TableStart,
    iter_blocks,
    paragraph_id,
)
from normocontrol.parser.classify import classify_paragraphs
from normocontrol.parser.model import (
    Alignment,
    Document,
    DocumentStats,
    Font,
    Footnote,
    HeaderFooter,
    HeaderFooterKind,
    HeaderFooterVariant,
    HeadingSource,
    Image,
    LineSpacing,
    LineSpacingRule,
    Margins,
    Numbering,
    Orientation,
    Paragraph,
    Run,
    Section,
    Table,
)
from normocontrol.parser.pages import PageEstimator, estimate_from_breaks
from normocontrol.parser.safety import InvalidDocumentError, validate_docx_bytes
from normocontrol.parser.styles import ParaProps, RunProps, StyleSheet
from normocontrol.parser.units import emu_to_cm, line_units_to_multiple, twips_to_cm, twips_to_pt
from normocontrol.parser.xml import (
    NS,
    W_P_PR,
    W_R,
    W_R_PR,
    W_SECT_PR,
    Element,
    attr,
    child,
    int_attr,
    iter_children,
    local_name,
    on_off,
    parse_xml,
    qn,
)

_ALIGNMENT = {
    "left": Alignment.LEFT,
    "start": Alignment.LEFT,
    "right": Alignment.RIGHT,
    "end": Alignment.RIGHT,
    "center": Alignment.CENTER,
    "both": Alignment.JUSTIFY,
    "distribute": Alignment.DISTRIBUTE,
    "thaiDistribute": Alignment.DISTRIBUTE,
    "lowKashida": Alignment.JUSTIFY,
    "mediumKashida": Alignment.JUSTIFY,
    "highKashida": Alignment.JUSTIFY,
}
_PAPER_SIZES_CM = {
    "A3": (29.7, 42.0),
    "A4": (21.0, 29.7),
    "A5": (14.8, 21.0),
    "Letter": (21.59, 27.94),
    "Legal": (21.59, 35.56),
}
_PAPER_TOLERANCE_CM = 0.15
_HEADING_STYLE_RE = re.compile(r"^(heading|заголовок)\s*([1-9])$", re.IGNORECASE)
_PAGE_FIELD_RE = re.compile(r"(?<![A-Z])PAGE(?![A-Z])")
# Контейнеры внутри абзаца, в которых лежат видимые run'ы.
_INLINE_CONTAINERS = frozenset(
    {"hyperlink", "smartTag", "customXml", "ins", "moveTo", "fldSimple", "bdo", "dir"}
)
_W_DRAWING = qn("w:drawing")
_W_PICT = qn("w:pict")
_W_OBJECT = qn("w:object")
_MC_ALT = f"{{{NS['mc']}}}AlternateContent"


@dataclass(slots=True)
class _ParagraphScan:
    """Промежуточный результат разбора одного абзаца."""

    runs: list[Run] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)
    name_weights: Counter[str] = field(default_factory=Counter)
    size_weights: Counter[float] = field(default_factory=Counter)
    visible_chars: int = 0
    bold_chars: int = 0
    italic_chars: int = 0
    underline_chars: int = 0
    caps_chars: int = 0
    page_break: bool = False
    rendered_break_before_text: bool = False
    rendered_breaks: int = 0
    images: list[tuple[float | None, float | None, bool]] = field(default_factory=list)
    in_toc_field: bool = False


class _FieldTracker:
    """Отслеживает сложные поля (fldChar), в том числе растянутые на много абзацев (TOC)."""

    def __init__(self) -> None:
        self._stack: list[list[str]] = []

    @property
    def in_toc(self) -> bool:
        return any("".join(parts).strip().upper().startswith("TOC") for parts in self._stack)

    def char(self, element: Element) -> None:
        kind = attr(element, "w:fldCharType")
        if kind == "begin":
            self._stack.append([])
        elif kind == "end" and self._stack:
            self._stack.pop()

    def instruction(self, text: str) -> None:
        if self._stack:
            self._stack[-1].append(text)


class DocxParser:
    def __init__(self, data: bytes, filename: str | None = None) -> None:
        validate_docx_bytes(data)
        self._data = data
        self._filename = filename
        try:
            self._doc: Any = docx.Document(io.BytesIO(data))
        except (ValueError, KeyError) as exc:
            raise InvalidDocumentError(f"Не удалось открыть документ: {exc}") from exc
        except Exception as exc:
            raise InvalidDocumentError(
                "Документ повреждён или имеет неподдерживаемый формат"
            ) from exc
        self._part = self._doc.part
        self._sheet = StyleSheet(
            styles=self._doc.styles.element,
            numbering=self._related_element(RT.NUMBERING),
            theme=self._related_element(RT.THEME),
        )
        self._fields = _FieldTracker()

    # ------------------------------------------------------------------ public

    def parse(self, page_estimator: PageEstimator | None = None) -> Document:
        body = self._doc.element.body
        paragraphs, tables, images = self._parse_body(body)
        sections = self._parse_sections(body, paragraphs)
        headers_footers = self._parse_headers_footers(body)
        paragraphs = classify_paragraphs(paragraphs, tables)

        page_source: str | None = None
        pages: dict[str, int] | None = None
        if page_estimator is not None:
            pages = page_estimator.estimate(self._data, paragraphs)
            page_source = page_estimator.name if pages else None
        if not pages:
            pages, page_source = estimate_from_breaks(paragraphs, self._rendered)
        if pages:
            paragraphs = [
                p.model_copy(update={"page_estimate": pages.get(p.id)}) for p in paragraphs
            ]

        words = sum(len(p.text.split()) for p in paragraphs)
        chars = sum(len(p.text) for p in paragraphs)
        page_values = [p.page_estimate for p in paragraphs if p.page_estimate is not None]
        stats = DocumentStats(
            paragraphs=len(paragraphs),
            words=words,
            characters=chars,
            tables=len(tables),
            images=len(images),
            pages_estimated=max(page_values) if page_values else None,
            page_source=page_source,
        )
        settings = self._doc.settings.element
        return Document(
            filename=self._filename,
            sections=sections,
            paragraphs=paragraphs,
            tables=tables,
            images=images,
            headers_footers=headers_footers,
            footnotes=self._parse_footnotes(),
            even_and_odd_headers=bool(on_off(child(settings, "w:evenAndOddHeaders"))),
            stats=stats,
        )

    # ------------------------------------------------------------------ body

    def _parse_body(self, body: Element) -> tuple[list[Paragraph], list[Table], list[Image]]:
        paragraphs: list[Paragraph] = []
        tables: list[Table] = []
        images: list[Image] = []
        self._rendered: dict[str, tuple[int, bool]] = {}
        section_index = 0
        last_top_index = -1
        open_tables: dict[int, dict[str, Any]] = {}

        for block in iter_blocks(body):
            if isinstance(block, TableStart):
                grid = child(block.element, "w:tblGrid")
                cols = len(list(iter_children(grid, "w:gridCol"))) if grid is not None else 0
                rows = len(block.element.findall(f".//{qn('w:tr')}"))
                open_tables[block.table_index] = {
                    "rows": rows,
                    "cols": cols,
                    "preceding": last_top_index,
                    "cells": [],
                }
                continue
            if isinstance(block, TableEnd):
                info = open_tables.pop(block.table_index)
                tables.append(
                    Table(
                        id=f"t-{block.table_index + 1}",
                        index=block.table_index,
                        rows=info["rows"],
                        cols=info["cols"],
                        preceding_paragraph_index=info["preceding"],
                        cell_paragraph_ids=info["cells"],
                    )
                )
                continue

            assert isinstance(block, ParagraphBlock)  # noqa: S101 — сужение типа для mypy
            index = len(paragraphs)
            paragraph, scan = self._parse_paragraph(block, index, section_index)
            paragraphs.append(paragraph)
            self._rendered[paragraph.id] = (scan.rendered_breaks, scan.rendered_break_before_text)
            for number, (width, height, inline) in enumerate(scan.images, start=len(images) + 1):
                images.append(
                    Image(
                        id=f"img-{number}",
                        paragraph_id=paragraph.id,
                        width_cm=width,
                        height_cm=height,
                        inline=inline,
                    )
                )
            if block.table_index is not None:
                open_tables[block.table_index]["cells"].append(paragraph.id)
            else:
                last_top_index = index
            if paragraph.ends_section:
                section_index += 1

        # индекс первого абзаца после каждой таблицы
        tables = [
            t.model_copy(update={"following_paragraph_index": _next_top_level(paragraphs, t)})
            for t in tables
        ]
        return paragraphs, tables, images

    def _parse_paragraph(
        self, block: ParagraphBlock, index: int, section_index: int
    ) -> tuple[Paragraph, _ParagraphScan]:
        element = block.element
        ppr = element.find(W_P_PR)
        style_id = attr(child(ppr, "w:pStyle"), "w:val")
        direct = ParaProps.from_ppr(ppr)
        props = self._sheet.resolve_paragraph(style_id, direct)
        style_name = self._sheet.style_name(style_id)

        scan = _ParagraphScan(in_toc_field=self._fields.in_toc)
        for run in _iter_runs(element):
            self._scan_run(run, style_id, scan)
        text = "".join(scan.text_parts)

        heading_level, heading_source = _heading_from_style(style_name, props.outline_level)
        numbering = self._numbering(props)
        visible = scan.visible_chars
        font = _dominant_font(scan) if visible else self._mark_font(style_id)

        paragraph = Paragraph(
            id=paragraph_id(index),
            index=index,
            section_index=section_index,
            text=text,
            style_id=style_id or self._sheet.default_paragraph_style,
            style_name=style_name,
            runs=_merge_runs(scan.runs),
            font=font,
            fonts_used=sorted(scan.name_weights),
            sizes_used=sorted(scan.size_weights),
            alignment=_ALIGNMENT.get(props.alignment or "left", Alignment.LEFT),
            first_line_indent_cm=twips_to_cm(props.first_line_twips or 0),
            left_indent_cm=twips_to_cm(props.left_twips or 0),
            right_indent_cm=twips_to_cm(props.right_twips or 0),
            line_spacing=_line_spacing(props.line),
            space_before_pt=14.0 if props.before_auto else twips_to_pt(props.before_twips or 0),
            space_after_pt=14.0 if props.after_auto else twips_to_pt(props.after_twips or 0),
            page_break_before=bool(props.page_break_before),
            contains_page_break=scan.page_break,
            ends_section=block.top_level and child(ppr, "w:sectPr") is not None,
            outline_level=props.outline_level,
            is_heading=heading_level is not None,
            heading_level=heading_level,
            heading_source=heading_source,
            numbering=numbering,
            in_table=block.table_index is not None,
            table_id=f"t-{block.table_index + 1}" if block.table_index is not None else None,
            has_drawing=bool(scan.images),
            has_formula=element.find(f".//{{{NS['m']}}}oMath") is not None,
            in_toc_field=scan.in_toc_field or block.in_toc_sdt,
        )
        return paragraph, scan

    def _scan_run(self, run: Element, paragraph_style: str | None, scan: _ParagraphScan) -> None:
        rpr_element = run.find(W_R_PR)
        run_style = attr(child(rpr_element, "w:rStyle"), "w:val")
        props = self._sheet.resolve_run(paragraph_style, run_style, RunProps.from_rpr(rpr_element))
        parts: list[str] = []
        for node in run:
            name = local_name(node)
            if name == "t":
                parts.append(node.text or "")
            elif name in {"tab", "ptab"}:
                parts.append("\t")
            elif name == "br":
                if attr(node, "w:type") == "page":
                    scan.page_break = True
                elif attr(node, "w:type") != "column":
                    parts.append("\n")
            elif name == "cr":
                parts.append("\n")
            elif name == "noBreakHyphen":
                parts.append("-")
            elif name == "lastRenderedPageBreak":
                scan.rendered_breaks += 1
                if scan.visible_chars == 0 and not "".join(parts).strip():
                    scan.rendered_break_before_text = True
            elif name == "fldChar":
                self._fields.char(node)
                scan.in_toc_field = scan.in_toc_field or self._fields.in_toc
            elif name == "instrText":
                self._fields.instruction(node.text or "")
                scan.in_toc_field = scan.in_toc_field or self._fields.in_toc
            elif node.tag in {_W_DRAWING, _W_PICT, _W_OBJECT, _MC_ALT}:
                scan.images.extend(_drawing_extents(node))

        text = "".join(parts)
        if props.hidden or not text:
            return
        font = Font(
            name=self._sheet.font_name(props, text),
            size_pt=self._sheet.size_pt(props),
            bold=bool(props.bold),
            italic=bool(props.italic),
            underline=bool(props.underline),
            all_caps=bool(props.all_caps),
        )
        scan.runs.append(Run(text=text, font=font))
        scan.text_parts.append(text)
        weight = sum(1 for ch in text if not ch.isspace())
        if weight:
            assert font.name is not None  # noqa: S101 — font_name всегда возвращает имя
            assert font.size_pt is not None  # noqa: S101
            scan.visible_chars += weight
            scan.name_weights[font.name] += weight
            scan.size_weights[font.size_pt] += weight
            scan.bold_chars += weight if font.bold else 0
            scan.italic_chars += weight if font.italic else 0
            scan.underline_chars += weight if font.underline else 0
            scan.caps_chars += weight if font.all_caps else 0

    def _mark_font(self, style_id: str | None) -> Font:
        """Шрифт пустого абзаца — по стилю абзаца."""
        props = self._sheet.resolve_run(style_id, None, RunProps())
        return Font(
            name=self._sheet.font_name(props, "а"),
            size_pt=self._sheet.size_pt(props),
            bold=bool(props.bold),
            italic=bool(props.italic),
        )

    def _numbering(self, props: ParaProps) -> Numbering | None:
        if not props.num_id:
            return None
        level = self._sheet.numbering_level(props.num_id, props.num_level)
        return Numbering(
            num_id=props.num_id,
            level=props.num_level or 0,
            format=level.format if level else None,
            label=level.text if level else None,
        )

    # ------------------------------------------------------------------ sections

    def _section_elements(self, body: Element) -> list[Element]:
        result: list[Element] = []
        for node in body:
            if node.tag == W_SECT_PR:
                result.append(node)
            elif local_name(node) == "p":
                sect = child(node.find(W_P_PR), "w:sectPr")
                if sect is not None:
                    result.append(sect)
        return result

    def _parse_sections(self, body: Element, paragraphs: list[Paragraph]) -> list[Section]:
        elements = self._section_elements(body)
        if not elements:
            elements = [parse_xml(f'<w:sectPr xmlns:w="{NS["w"]}"/>'.encode())]
        sections: list[Section] = []
        for index, sect in enumerate(elements):
            members = [p.index for p in paragraphs if p.section_index == index]
            pg_sz = child(sect, "w:pgSz")
            pg_mar = child(sect, "w:pgMar")
            # значения по умолчанию Word — A4 и поля 2/1.5/2/3 см не подставляем:
            # без w:pgSz Word использует Letter, это и отражаем
            width = twips_to_cm(int_attr(pg_sz, "w:w") or 12240)
            height = twips_to_cm(int_attr(pg_sz, "w:h") or 15840)
            orient = attr(pg_sz, "w:orient")
            orientation = (
                Orientation(orient)
                if orient in {"portrait", "landscape"}
                else (Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT)
            )
            sections.append(
                Section(
                    index=index,
                    page_width_cm=width,
                    page_height_cm=height,
                    orientation=orientation,
                    paper_size=_paper_size(width, height),
                    margins=Margins(
                        left_cm=twips_to_cm(abs(int_attr(pg_mar, "w:left") or 1440)),
                        right_cm=twips_to_cm(abs(int_attr(pg_mar, "w:right") or 1440)),
                        top_cm=twips_to_cm(abs(int_attr(pg_mar, "w:top") or 1440)),
                        bottom_cm=twips_to_cm(abs(int_attr(pg_mar, "w:bottom") or 1440)),
                        gutter_cm=twips_to_cm(int_attr(pg_mar, "w:gutter") or 0),
                    ),
                    header_distance_cm=_cm_or_none(int_attr(pg_mar, "w:header")),
                    footer_distance_cm=_cm_or_none(int_attr(pg_mar, "w:footer")),
                    title_page=bool(on_off(child(sect, "w:titlePg"))),
                    first_paragraph_index=min(members) if members else 0,
                    last_paragraph_index=max(members) if members else 0,
                )
            )
        return sections

    def _parse_headers_footers(self, body: Element) -> list[HeaderFooter]:
        result: list[HeaderFooter] = []
        inherited: dict[tuple[str, str], Element] = {}
        for index, sect in enumerate(self._section_elements(body)):
            for kind in (HeaderFooterKind.HEADER, HeaderFooterKind.FOOTER):
                own: dict[str, Element] = {}
                for ref in iter_children(sect, f"w:{kind.value}Reference"):
                    variant = attr(ref, "w:type") or "default"
                    r_id = ref.get(qn("r:id"))
                    part = self._part.related_parts.get(r_id) if r_id else None
                    if part is not None:
                        own[variant] = part.element
                for variant in HeaderFooterVariant:
                    key = (kind.value, variant.value)
                    element = own.get(variant.value)
                    is_inherited = element is None
                    if element is None:
                        element = inherited.get(key)
                    if element is None:
                        continue
                    inherited[key] = element
                    result.append(self._header_footer(element, index, kind, variant, is_inherited))
        return result

    def _header_footer(
        self,
        element: Element,
        section_index: int,
        kind: HeaderFooterKind,
        variant: HeaderFooterVariant,
        is_inherited: bool,
    ) -> HeaderFooter:
        texts: list[str] = []
        page_alignment: Alignment | None = None
        has_page = False
        for paragraph in element.iter(qn("w:p")):
            text = "".join(t.text or "" for t in paragraph.iter(qn("w:t")))
            texts.append(text)
            instructions = [
                *(node.text or "" for node in paragraph.iter(qn("w:instrText"))),
                *(attr(node, "w:instr") or "" for node in paragraph.iter(qn("w:fldSimple"))),
            ]
            if any(_PAGE_FIELD_RE.search(instr) for instr in instructions):
                has_page = True
                if page_alignment is None:
                    page_alignment = self._field_alignment(paragraph)
        return HeaderFooter(
            section_index=section_index,
            kind=kind,
            variant=variant,
            text="\n".join(t for t in texts if t).strip(),
            has_page_field=has_page,
            page_field_alignment=page_alignment,
            inherited=is_inherited,
        )

    def _field_alignment(self, paragraph: Element) -> Alignment:
        ppr = paragraph.find(W_P_PR)
        style_id = attr(child(ppr, "w:pStyle"), "w:val")
        props = self._sheet.resolve_paragraph(style_id, ParaProps.from_ppr(ppr))
        alignment = _ALIGNMENT.get(props.alignment or "left", Alignment.LEFT)
        if alignment is Alignment.LEFT:
            # номер, выставленный табуляцией: стиль «Нижний колонтитул» имеет
            # центральный и правый табулятор, поэтому 1 таб → центр, 2 таба → право
            tabs = 0
            for node in paragraph.iter():
                name = local_name(node)
                parent = node.getparent()
                if name == "tab" and parent is not None and local_name(parent) == "r":
                    tabs += 1
                elif name in {"instrText", "fldSimple"}:
                    break
            if tabs == 1:
                return Alignment.CENTER
            if tabs >= 2:
                return Alignment.RIGHT
        return alignment

    # ------------------------------------------------------------------ parts

    def _related_element(self, reltype: str) -> Element | None:
        try:
            part = self._part.part_related_by(reltype)
        except KeyError:
            return None
        element = getattr(part, "element", None)
        if element is not None:
            return element  # type: ignore[no-any-return]
        return parse_xml(part.blob)

    def _parse_footnotes(self) -> list[Footnote]:
        root = self._related_element(RT.FOOTNOTES)
        if root is None:
            return []
        notes: list[Footnote] = []
        for note in iter_children(root, "w:footnote"):
            if attr(note, "w:type") in {"separator", "continuationSeparator", "continuationNotice"}:
                continue
            text = "".join(t.text or "" for t in note.iter(qn("w:t"))).strip()
            notes.append(Footnote(id=attr(note, "w:id") or str(len(notes)), text=text))
        return notes


def parse_docx(
    source: bytes | Path,
    filename: str | None = None,
    *,
    page_estimator: PageEstimator | None = None,
) -> Document:
    """Разобрать ``.docx`` из байтов или пути."""
    if isinstance(source, Path):
        filename = filename or source.name
        source = source.read_bytes()
    return DocxParser(source, filename).parse(page_estimator)


# ---------------------------------------------------------------------- helpers


def _iter_runs(parent: Element) -> Iterator[Element]:
    for node in parent:
        if node.tag == W_R:
            yield node
            continue
        name = local_name(node)
        if name in _INLINE_CONTAINERS:
            yield from _iter_runs(node)
        elif name == "sdt":
            content = child(node, "w:sdtContent")
            if content is not None:
                yield from _iter_runs(content)


def _drawing_extents(node: Element) -> list[tuple[float | None, float | None, bool]]:
    if node.tag == _MC_ALT:
        choice = next(iter(node), None)
        return _drawing_extents(choice[0]) if choice is not None and len(choice) else []
    extents: list[tuple[float | None, float | None, bool]] = []
    for container in node.iter(f"{{{NS['wp']}}}inline", f"{{{NS['wp']}}}anchor"):
        extent = container.find(f"{{{NS['wp']}}}extent")
        cx = extent.get("cx") if extent is not None else None
        cy = extent.get("cy") if extent is not None else None
        extents.append(
            (
                emu_to_cm(int(cx)) if cx else None,
                emu_to_cm(int(cy)) if cy else None,
                local_name(container) == "inline",
            )
        )
    if not extents:  # VML-рисунок или OLE-объект без DrawingML-размеров
        extents.append((None, None, True))
    return extents


def _dominant_font(scan: _ParagraphScan) -> Font:
    """Шрифт абзаца — тот, которым набрано большинство видимых символов."""
    total = scan.visible_chars
    return Font(
        name=scan.name_weights.most_common(1)[0][0],
        size_pt=scan.size_weights.most_common(1)[0][0],
        bold=scan.bold_chars == total,
        italic=scan.italic_chars == total,
        underline=scan.underline_chars == total,
        all_caps=scan.caps_chars == total,
    )


def _merge_runs(runs: list[Run]) -> list[Run]:
    merged: list[Run] = []
    for run in runs:
        if merged and merged[-1].font == run.font:
            merged[-1] = Run(text=merged[-1].text + run.text, font=run.font)
        else:
            merged.append(run)
    return merged


def _line_spacing(line: tuple[int, str] | None) -> LineSpacing:
    if line is None:
        return LineSpacing(rule=LineSpacingRule.MULTIPLE, value=1.0)
    value, rule = line
    if rule == "exact":
        return LineSpacing(rule=LineSpacingRule.EXACT, value=twips_to_pt(value))
    if rule == "atLeast":
        return LineSpacing(rule=LineSpacingRule.AT_LEAST, value=twips_to_pt(value))
    return LineSpacing(rule=LineSpacingRule.MULTIPLE, value=line_units_to_multiple(value))


def _heading_from_style(
    style_name: str | None, outline_level: int | None
) -> tuple[int | None, HeadingSource | None]:
    if style_name and (match := _HEADING_STYLE_RE.match(style_name.strip())):
        return int(match.group(2)), HeadingSource.STYLE
    if outline_level is not None and 0 <= outline_level < 9:
        return outline_level + 1, HeadingSource.OUTLINE
    return None, None


def _paper_size(width: float, height: float) -> str | None:
    short, long_ = sorted((width, height))
    for name, (w, h) in _PAPER_SIZES_CM.items():
        if abs(short - w) <= _PAPER_TOLERANCE_CM and abs(long_ - h) <= _PAPER_TOLERANCE_CM:
            return name
    return None


def _cm_or_none(value: int | None) -> float | None:
    return None if value is None else twips_to_cm(value)


def _next_top_level(paragraphs: list[Paragraph], table: Table) -> int | None:
    cells = set(table.cell_paragraph_ids)
    start = table.preceding_paragraph_index + 1
    for paragraph in paragraphs[start:]:
        if paragraph.id in cells or paragraph.in_table:
            continue
        return paragraph.index
    return None
