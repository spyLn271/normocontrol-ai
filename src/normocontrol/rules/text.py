"""Правила основного текста: шрифт, кегль, интервал, отступ, выравнивание, чистота текста."""

from __future__ import annotations

import re
from collections.abc import Iterable

from normocontrol.parser.model import Alignment, LineSpacingRule, Paragraph, ParagraphRole
from normocontrol.profiles.schema import BodyTextConfig, Profile, Severity, TextConfig
from normocontrol.report.model import Category, Issue
from normocontrol.rules.base import AppliesFunc, RuleContext, fmt_num, rule

# К каким абзацам применяются требования к шрифту и интервалу
_FONT_ROLES = (ParagraphRole.BODY, ParagraphRole.LIST_ITEM, ParagraphRole.BIBLIOGRAPHY_ENTRY)
_ALIGN_NAMES = {
    "left": "по левому краю",
    "center": "по центру",
    "right": "по правому краю",
    "justify": "по ширине",
    "distribute": "по ширине (распределённое)",
}
_DASH_START = re.compile(r"^\s*[-–—•·*▪●]\s+")
_PLACEHOLDER = re.compile(
    r"(<[^<>\n]{1,40}>|\{[^{}\n]{1,40}\}"
    r"|\[(?:фио|ф\.и\.о\.|дата|подпись|наименование|адрес|должность|номер|тема)[^\]\n]{0,30}\]"
    r"|\b[XХ]{3,}\b|_{2}\.\s?_{2}\.\s?_{2,4})",
    re.IGNORECASE,
)


def _body(ctx: RuleContext) -> BodyTextConfig:
    assert ctx.profile.body_text is not None  # noqa: S101
    return ctx.profile.body_text


def _text_cfg(ctx: RuleContext) -> TextConfig:
    assert ctx.profile.text is not None  # noqa: S101
    return ctx.profile.text


def _font_paragraphs(ctx: RuleContext) -> list[Paragraph]:
    return [p for p in ctx.document.by_role(*_FONT_ROLES) if not p.is_empty]


def _has_body(field: str) -> AppliesFunc:
    def applies(profile: Profile) -> bool:
        return profile.body_text is not None and getattr(profile.body_text, field) is not None

    return applies


@rule("font.family", category=Category.FONT, applies=_has_body("font_family"))
def check_font_family(ctx: RuleContext) -> Iterable[Issue]:
    """Гарнитура основного текста."""
    cfg = _body(ctx)
    assert cfg.font_family is not None  # noqa: S101
    allowed = {name.casefold() for name in cfg.font_family}
    expected = " или ".join(cfg.font_family)
    findings = [
        (p, p.font.name or "не определён")
        for p in _font_paragraphs(ctx)
        if (p.font.name or "").casefold() not in allowed
    ]
    return ctx.grouped(
        "font.family",
        Category.FONT,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        expected=expected,
        message=lambda actual, _n, where: f"Шрифт «{actual}» {where}, требуется {expected}",
        fix=f"Выделите текст и установите шрифт {cfg.font_family[0]} "
        "(лучше — в стиле «Обычный», чтобы изменение применилось ко всему документу)",
    )


@rule("font.size", category=Category.FONT, applies=_has_body("font_size_pt"))
def check_font_size(ctx: RuleContext) -> Iterable[Issue]:
    """Кегль основного текста."""
    cfg = _body(ctx)
    size = cfg.font_size_pt
    assert size is not None  # noqa: S101
    if size.min is not None and size.min == size.max:
        expected = f"{fmt_num(size.min)} pt"
    else:
        parts = []
        if size.min is not None:
            parts.append(f"не менее {fmt_num(size.min)} pt")
        if size.max is not None:
            parts.append(f"не более {fmt_num(size.max)} pt")
        expected = ", ".join(parts) or f"{fmt_num(size.recommended or 0)} pt"

    violations: list[tuple[Paragraph, str]] = []
    recommendations: list[tuple[Paragraph, str]] = []
    for paragraph in _font_paragraphs(ctx):
        actual_size = paragraph.font.size_pt
        if actual_size is None:
            continue
        actual = f"{fmt_num(actual_size)} pt"
        if (size.min is not None and actual_size < size.min - 0.01) or (
            size.max is not None and actual_size > size.max + 0.01
        ):
            violations.append((paragraph, actual))
        elif size.recommended is not None and abs(actual_size - size.recommended) > 0.01:
            recommendations.append((paragraph, actual))

    issues = ctx.grouped(
        "font.size",
        Category.FONT,
        severity=cfg.severity,
        reference=cfg.source,
        findings=violations,
        expected=expected,
        message=lambda actual, _n, where: f"Размер шрифта {actual} {where}, требуется {expected}",
        fix="Выделите текст и установите нужный размер шрифта (Главная → Размер шрифта)",
    )
    if size.recommended is not None:
        recommended = f"{fmt_num(size.recommended)} pt"
        issues += ctx.grouped(
            "font.size",
            Category.FONT,
            severity=Severity.INFO,
            reference=cfg.source,
            findings=recommendations,
            expected=recommended,
            message=lambda actual, _n, where: (
                f"Размер шрифта {actual} {where}; рекомендуется {recommended}"
            ),
            fix=f"Рекомендуется установить размер {recommended}",
        )
    return issues


def _spacing_label(paragraph: Paragraph) -> str:
    spacing = paragraph.line_spacing
    if spacing.rule is LineSpacingRule.MULTIPLE:
        return fmt_num(spacing.value)
    prefix = "точно" if spacing.rule is LineSpacingRule.EXACT else "минимум"
    return f"{prefix} {fmt_num(spacing.value)} pt"


@rule(
    "paragraph.line_spacing",
    category=Category.PARAGRAPH,
    applies=_has_body("line_spacing"),
)
def check_line_spacing(ctx: RuleContext) -> Iterable[Issue]:
    """Межстрочный интервал."""
    cfg = _body(ctx)
    assert cfg.line_spacing is not None  # noqa: S101
    expected = fmt_num(cfg.line_spacing)
    findings = []
    for paragraph in _font_paragraphs(ctx):
        spacing = paragraph.line_spacing
        if spacing.rule is not LineSpacingRule.MULTIPLE or (
            abs(spacing.value - cfg.line_spacing) > cfg.line_spacing_tolerance
        ):
            findings.append((paragraph, _spacing_label(paragraph)))
    return ctx.grouped(
        "paragraph.line_spacing",
        Category.PARAGRAPH,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        expected=expected,
        message=lambda actual, _n, where: (
            f"Межстрочный интервал {actual} {where}, требуется {expected}"
        ),
        fix=f"Абзац → Междустрочный интервал → множитель {expected}",
    )


@rule(
    "paragraph.first_line_indent",
    category=Category.PARAGRAPH,
    applies=_has_body("first_line_indent_cm"),
)
def check_first_line_indent(ctx: RuleContext) -> Iterable[Issue]:
    """Абзацный отступ."""
    cfg = _body(ctx)
    assert cfg.first_line_indent_cm is not None  # noqa: S101
    expected_value = cfg.first_line_indent_cm
    expected = f"{fmt_num(expected_value)} см"
    findings: list[tuple[Paragraph, str]] = []
    for paragraph in ctx.document.body_paragraphs:
        if paragraph.is_empty:
            continue
        indent = paragraph.first_line_indent_cm
        if abs(indent - expected_value) <= cfg.indent_tolerance_cm:
            continue
        if indent < cfg.indent_tolerance_cm and paragraph.text[:1] in {" ", "\t"}:
            findings.append((paragraph, "пробелами или табуляцией"))
        else:
            findings.append((paragraph, f"{fmt_num(indent)} см"))
    return ctx.grouped(
        "paragraph.first_line_indent",
        Category.PARAGRAPH,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        expected=expected,
        message=lambda actual, _n, where: (
            f"Абзацный отступ сделан {actual} {where}, требуется {expected}"
            if actual.startswith("пробел")
            else f"Абзацный отступ {actual} {where}, требуется {expected}"
        ),
        fix=f"Абзац → Отступ → первая строка: {expected}; уберите пробелы и табуляцию в начале",
    )


@rule("paragraph.alignment", category=Category.PARAGRAPH, applies=_has_body("alignment"))
def check_alignment(ctx: RuleContext) -> Iterable[Issue]:
    """Выравнивание основного текста."""
    cfg = _body(ctx)
    assert cfg.alignment is not None  # noqa: S101
    expected_alignment = Alignment(cfg.alignment)
    accepted = {expected_alignment}
    if expected_alignment is Alignment.JUSTIFY:
        accepted.add(Alignment.DISTRIBUTE)
    findings = [
        (p, _ALIGN_NAMES[p.alignment.value])
        for p in ctx.document.body_paragraphs
        if not p.is_empty and p.alignment not in accepted
    ]
    expected = _ALIGN_NAMES[cfg.alignment]
    return ctx.grouped(
        "paragraph.alignment",
        Category.PARAGRAPH,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        expected=expected,
        message=lambda actual, _n, where: f"Выравнивание {actual} {where}, требуется {expected}",
        fix=f"Главная → Выравнивание {expected}",
    )


# ---------------------------------------------------------------------- text hygiene


def _text_enabled(field: str) -> AppliesFunc:
    def applies(profile: Profile) -> bool:
        return profile.text is not None and bool(getattr(profile.text, field))

    return applies


@rule(
    "text.dash_paragraphs", category=Category.TEXT, applies=_text_enabled("forbid_dash_paragraphs")
)
def check_dash_paragraphs(ctx: RuleContext) -> Iterable[Issue]:
    """Абзацы, обозначенные дефисами или маркерами."""
    cfg = _text_cfg(ctx)
    findings: list[tuple[Paragraph, str]] = []
    for paragraph in ctx.document.by_role(ParagraphRole.BODY, ParagraphRole.LIST_ITEM):
        if _DASH_START.match(paragraph.text):
            findings.append((paragraph, "дефис/маркер в начале абзаца"))
        elif paragraph.numbering is not None and paragraph.numbering.format == "bullet":
            findings.append((paragraph, "маркированный список"))
    return ctx.grouped(
        "text.dash_paragraphs",
        Category.TEXT,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        expected="пункты 1., 2., подпункты 1), 2)",
        message=lambda actual, _n, where: f"Абзацы обозначены знаками ({actual}) {where}",
        fix="Пронумеруйте пункты цифрами с точкой (1., 2.), подпункты — со скобкой (1), 2))",
    )


@rule("text.double_spaces", category=Category.TEXT, applies=_text_enabled("forbid_double_spaces"))
def check_double_spaces(ctx: RuleContext) -> Iterable[Issue]:
    """Двойные пробелы внутри текста."""
    cfg = _text_cfg(ctx)
    findings = [
        (p, "двойные пробелы") for p in ctx.document.by_role(*_FONT_ROLES) if "  " in p.text.strip()
    ]
    return ctx.grouped(
        "text.double_spaces",
        Category.TEXT,
        severity=Severity.INFO if cfg.severity is Severity.ERROR else cfg.severity,
        reference=cfg.source,
        findings=findings,
        message=lambda _a, _n, where: f"Двойные пробелы {where}",
        fix="Главная → Заменить: два пробела → один пробел",
    )


@rule(
    "text.empty_paragraphs",
    category=Category.TEXT,
    applies=lambda p: bool(p.text and p.text.max_consecutive_empty_paragraphs is not None),
)
def check_empty_paragraphs(ctx: RuleContext) -> Iterable[Issue]:
    """Серии пустых абзацев вместо интервалов или разрыва страницы."""
    cfg = _text_cfg(ctx)
    limit = cfg.max_consecutive_empty_paragraphs
    assert limit is not None  # noqa: S101
    issues: list[Issue] = []
    run: list[Paragraph] = []
    for paragraph in [*ctx.document.paragraphs, None]:
        if paragraph is not None and paragraph.role is ParagraphRole.EMPTY:
            run.append(paragraph)
            continue
        if len(run) > limit:
            issues.append(
                ctx.issue(
                    "text.empty_paragraphs",
                    Category.TEXT,
                    severity=cfg.severity,
                    message=f"{len(run)} пустых абзацев подряд (допускается не более {limit})",
                    reference=cfg.source,
                    paragraphs=run,
                    fix="Удалите пустые абзацы; для перехода на новую страницу используйте "
                    "разрыв страницы (Ctrl+Enter), для отступов — интервалы абзаца",
                )
            )
        run = []
    return issues


@rule("text.placeholders", category=Category.TEXT, applies=_text_enabled("forbid_placeholders"))
def check_placeholders(ctx: RuleContext) -> Iterable[Issue]:
    """Незаполненные поля шаблона: <ФИО>, [дата], ХХХХ, __.__.____."""
    cfg = _text_cfg(ctx)
    issues: list[Issue] = []
    for paragraph in ctx.document.paragraphs:
        if paragraph.role is ParagraphRole.TOC:
            continue
        match = _PLACEHOLDER.search(paragraph.text)
        if match:
            issues.append(
                ctx.issue(
                    "text.placeholders",
                    Category.TEXT,
                    severity=Severity.ERROR,
                    message=f"Не заполнено поле шаблона: «{match.group(0)}»",
                    reference=cfg.source,
                    paragraphs=[paragraph],
                    actual=match.group(0),
                    quote=match.group(0),
                    fix="Замените заглушку фактическим значением",
                )
            )
    return issues
