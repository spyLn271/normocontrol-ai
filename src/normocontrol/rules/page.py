"""Правила страницы: формат, ориентация, поля, нумерация страниц."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from normocontrol.parser.model import (
    Alignment,
    Document,
    HeaderFooter,
    HeaderFooterKind,
    HeaderFooterVariant,
    ParagraphRole,
    Section,
)
from normocontrol.profiles.schema import PageConfig, Severity
from normocontrol.report.model import Category, Issue
from normocontrol.rules.base import RuleContext, fmt_num, plural, rule

_SIDES = {"left": "Левое", "right": "Правое", "top": "Верхнее", "bottom": "Нижнее"}
_POSITION_NAMES = {
    "bottom-center": "внизу по центру",
    "bottom-right": "внизу справа",
    "bottom-left": "внизу слева",
    "top-center": "вверху по центру",
    "top-right": "вверху справа",
    "top-left": "вверху слева",
}


def _page(ctx: RuleContext) -> PageConfig:
    assert ctx.profile.page is not None  # noqa: S101 — гарантирует applies
    return ctx.profile.page


def _sections_label(indices: list[int], total: int) -> str:
    if total == 1:
        return ""
    numbers = ", ".join(str(i + 1) for i in indices)
    return f" ({plural(len(indices), 'раздел', 'разделы', 'разделы')} {numbers})"


@rule("page.size", category=Category.PAGE, applies=lambda p: p.page is not None)
def check_size(ctx: RuleContext) -> Iterable[Issue]:
    """Формат листа (A4, A5…)."""
    cfg = _page(ctx)
    groups: dict[str, list[Section]] = defaultdict(list)
    for section in ctx.document.sections:
        if section.paper_size not in cfg.size:
            size = f"{fmt_num(section.page_width_cm, 1)}×{fmt_num(section.page_height_cm, 1)} см"
            label = f"{section.paper_size} ({size})" if section.paper_size else size
            groups[label].append(section)
    total = len(ctx.document.sections)
    for actual, sections in groups.items():
        expected = " или ".join(cfg.size)
        yield ctx.issue(
            "page.size",
            Category.PAGE,
            severity=cfg.severity,
            message=f"Формат листа {actual}, требуется {expected}"
            + _sections_label([s.index for s in sections], total),
            reference=cfg.source,
            section_index=sections[0].index,
            expected=expected,
            actual=actual,
            fix=f"Макет → Размер → {cfg.size[0]}",
        )


def _is_wide_content_section(document: Document, section: Section) -> bool:
    """Альбомный раздел только с таблицами/рисунками — допустимая практика."""
    paragraphs = document.paragraphs[
        section.first_paragraph_index : section.last_paragraph_index + 1
    ]
    body = [p for p in paragraphs if p.role in {ParagraphRole.BODY, ParagraphRole.LIST_ITEM}]
    return len(body) <= 2


@rule("page.orientation", category=Category.PAGE, applies=lambda p: p.page is not None)
def check_orientation(ctx: RuleContext) -> Iterable[Issue]:
    """Ориентация страницы."""
    cfg = _page(ctx)
    if cfg.orientation == "any":
        return
    expected_name = "книжная" if cfg.orientation == "portrait" else "альбомная"
    for section in ctx.document.sections:
        if section.orientation.value == cfg.orientation:
            continue
        severity = (
            Severity.INFO if _is_wide_content_section(ctx.document, section) else cfg.severity
        )
        actual_name = "альбомная" if cfg.orientation == "portrait" else "книжная"
        yield ctx.issue(
            "page.orientation",
            Category.PAGE,
            severity=severity,
            message=f"Ориентация страницы {actual_name}, требуется {expected_name}"
            + _sections_label([section.index], len(ctx.document.sections)),
            reference=cfg.source,
            section_index=section.index,
            expected=expected_name,
            actual=actual_name,
            fix="Макет → Ориентация",
        )


@rule("page.margins", category=Category.PAGE, applies=lambda p: p.page is not None)
def check_margins(ctx: RuleContext) -> Iterable[Issue]:
    """Поля страницы."""
    cfg = _page(ctx)
    if cfg.margins_cm is None:
        return
    total = len(ctx.document.sections)
    # (сторона, фактическое значение) → разделы
    groups: dict[tuple[str, float], list[int]] = defaultdict(list)
    for section in ctx.document.sections:
        for side in _SIDES:
            expected = getattr(cfg.margins_cm, side)
            actual = getattr(section.margins, f"{side}_cm")
            if side == "left":
                actual += section.margins.gutter_cm
            too_far = abs(actual - expected) > cfg.tolerance_cm
            violates = (
                actual < expected - cfg.tolerance_cm if cfg.margins_mode == "min" else too_far
            )
            if violates:
                groups[(side, round(actual, 2))].append(section.index)
    for (side, actual), sections in groups.items():
        expected = getattr(cfg.margins_cm, side)
        relation = "не менее " if cfg.margins_mode == "min" else ""
        yield ctx.issue(
            "page.margins",
            Category.PAGE,
            severity=cfg.severity,
            message=(
                f"{_SIDES[side]} поле {fmt_num(actual)} см, требуется {relation}"
                f"{fmt_num(expected)} см" + _sections_label(sections, total)
            ),
            reference=cfg.source,
            section_index=sections[0],
            expected=f"{relation}{fmt_num(expected)} см",
            actual=f"{fmt_num(actual)} см",
            fix=f"Макет → Поля → Настраиваемые поля: {_SIDES[side].lower()} {fmt_num(expected)} см",
        )


def _visible(hf_list: list[HeaderFooter], kind: HeaderFooterKind) -> dict[str, HeaderFooter]:
    return {hf.variant.value: hf for hf in hf_list if hf.kind is kind}


@rule("page.numbering", category=Category.PAGE, applies=lambda p: bool(p.page and p.page.numbering))
def check_numbering(ctx: RuleContext) -> Iterable[Issue]:
    """Номера страниц: наличие, положение, отсутствие номера на первой странице."""
    cfg = _page(ctx)
    numbering = cfg.numbering
    assert numbering is not None  # noqa: S101
    document = ctx.document
    pages = document.stats.pages_estimated
    # Если нумерация нужна только многостраничным документам, а число страниц неизвестно,
    # не гадаем: проверяем, лишь когда страниц точно больше одной.
    multi_page = pages is not None and pages > 1
    if not numbering.required and not multi_page:
        return

    expected_kind = (
        HeaderFooterKind.HEADER if numbering.position.startswith("top") else HeaderFooterKind.FOOTER
    )
    expected_align = {
        "center": Alignment.CENTER,
        "right": Alignment.RIGHT,
        "left": Alignment.LEFT,
    }[numbering.position.split("-", 1)[1]]
    position_name = _POSITION_NAMES[numbering.position]

    numbered = [
        hf
        for hf in document.headers_footers
        if hf.has_page_field and hf.variant is not HeaderFooterVariant.FIRST
    ]
    if not numbered:
        if numbering.required or multi_page:
            yield ctx.issue(
                "page.numbering",
                Category.PAGE,
                severity=cfg.severity,
                message=f"Нет номеров страниц (требуются {position_name})",
                reference=cfg.source,
                expected=position_name,
                actual="нет",
                fix="Вставка → Номер страницы → " + position_name,
            )
        return

    misplaced = [
        hf
        for hf in numbered
        if hf.kind is not expected_kind
        or (hf.page_field_alignment is not None and hf.page_field_alignment is not expected_align)
    ]
    if misplaced:
        hf = misplaced[0]
        place = "вверху" if hf.kind is HeaderFooterKind.HEADER else "внизу"
        align = {
            Alignment.CENTER: "по центру",
            Alignment.RIGHT: "справа",
            Alignment.LEFT: "слева",
        }.get(hf.page_field_alignment or Alignment.LEFT, "")
        yield ctx.issue(
            "page.numbering",
            Category.PAGE,
            severity=cfg.severity,
            message=f"Номер страницы расположен {place} {align}, требуется {position_name}",
            reference=cfg.source,
            section_index=hf.section_index,
            expected=position_name,
            actual=f"{place} {align}".strip(),
            fix="Удалите номер и вставьте заново: Вставка → Номер страницы → " + position_name,
        )

    if not numbering.title_page_numbered and _first_page_shows_number(document):
        yield ctx.issue(
            "page.numbering",
            Category.PAGE,
            severity=cfg.severity,
            message="Номер страницы проставлен на первой (титульной) странице",
            reference=cfg.source,
            section_index=0,
            expected="без номера на первой странице",
            actual="номер есть",
            fix="Конструктор колонтитулов → «Особый колонтитул для первой страницы»",
        )


def _first_page_shows_number(document: Document) -> bool:
    first_section = document.sections[0]
    hfs = document.headers_footers_of(0)
    for kind in (HeaderFooterKind.HEADER, HeaderFooterKind.FOOTER):
        variants = _visible(hfs, kind)
        shown = variants.get("first") if first_section.title_page else variants.get("default")
        if shown is not None and shown.has_page_field:
            return True
    return False
