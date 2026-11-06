"""Правила заголовков: регистр, точка в конце, жирность, выравнивание, отступ, новая страница."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

from normocontrol.parser.model import Alignment, Document, Paragraph
from normocontrol.parser.vocabulary import is_structural_heading
from normocontrol.profiles.schema import HeadingRule, HeadingsConfig, Profile
from normocontrol.report.model import Category, Issue
from normocontrol.rules.base import HEADING_NOUN, RuleContext, rule

type HeadingKind = Literal["structural", "section", "subsection"]

_NUMBER_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})(\.?)\s+")
_KIND_NAMES = {
    "structural": "структурного элемента",
    "section": "раздела",
    "subsection": "подраздела",
}
_ALIGN_NAMES = {
    Alignment.LEFT: "по левому краю",
    Alignment.CENTER: "по центру",
    Alignment.RIGHT: "по правому краю",
    Alignment.JUSTIFY: "по ширине",
    Alignment.DISTRIBUTE: "по ширине",
}
_DEFAULT_INDENT_CM = 1.25
_INDENT_TOLERANCE_CM = 0.15


def heading_kind(paragraph: Paragraph) -> HeadingKind:
    if is_structural_heading(paragraph.text):
        return "structural"
    match = _NUMBER_RE.match(paragraph.text)
    if match:
        return "subsection" if "." in match.group(1) else "section"
    return "section" if (paragraph.heading_level or 1) <= 1 else "subsection"


def _rule_for(cfg: HeadingsConfig, kind: HeadingKind) -> HeadingRule | None:
    return {"structural": cfg.structural, "section": cfg.section, "subsection": cfg.subsection}[
        kind
    ]


def _letters(paragraph: Paragraph) -> str:
    text = _NUMBER_RE.sub("", paragraph.text.strip(), count=1)
    if paragraph.font.all_caps:
        text = text.upper()
    return "".join(ch for ch in text if ch.isalpha())


def _case_ok(letters: str, case: str) -> bool:
    if not letters or case == "any":
        return True
    first_upper = letters[0].isupper()
    all_upper = letters.isupper()
    if case == "upper":
        return all_upper
    if case == "sentence":
        return first_upper and (len(letters) < 2 or not all_upper)
    return first_upper  # capitalized, upper_or_sentence


_CASE_NAMES = {
    "upper": "прописными буквами",
    "sentence": "с прописной (заглавной) буквы, остальные строчные",
    "capitalized": "с прописной буквы",
    "upper_or_sentence": "с прописной буквы или прописными буквами",
}


def _starts_new_page(document: Document, paragraph: Paragraph) -> bool:
    if paragraph.page_break_before or paragraph.index == 0:
        return True
    for previous in reversed(document.paragraphs[: paragraph.index]):
        if previous.in_table:
            return False
        if previous.contains_page_break or previous.ends_section:
            return True
        if not previous.is_empty:
            return False
    return True


def _headings_by_kind(ctx: RuleContext) -> list[tuple[Paragraph, HeadingRule, HeadingKind]]:
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    result = []
    for paragraph in ctx.document.headings:
        kind = heading_kind(paragraph)
        heading_rule = _rule_for(cfg, kind)
        if heading_rule is not None:
            result.append((paragraph, heading_rule, kind))
    return result


def _applies(profile: Profile) -> bool:
    return profile.headings is not None


@rule("heading.case", category=Category.HEADING, applies=_applies)
def check_case(ctx: RuleContext) -> Iterable[Issue]:
    """Регистр заголовков."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings: dict[HeadingKind, list[tuple[Paragraph, str]]] = {}
    for paragraph, heading_rule, kind in _headings_by_kind(ctx):
        if not _case_ok(_letters(paragraph), heading_rule.case):
            findings.setdefault(kind, []).append((paragraph, paragraph.text.strip()))
    issues: list[Issue] = []
    for kind, items in findings.items():
        kind_rule = _rule_for(cfg, kind)
        assert kind_rule is not None  # noqa: S101
        expected = _CASE_NAMES.get(kind_rule.case, kind_rule.case)
        issues.append(
            ctx.issue(
                "heading.case",
                Category.HEADING,
                severity=cfg.severity,
                message=f"Заголовок {_KIND_NAMES[kind]} должен быть набран {expected}: "
                + ", ".join(f"«{text}»" for _, text in items[:5])
                + (" и др." if len(items) > 5 else ""),
                reference=cfg.source,
                paragraphs=[p for p, _ in items],
                expected=expected,
                actual=items[0][1],
                fix="Перепечатайте заголовок в нужном регистре (Главная → Регистр) "
                "и проверьте, что в шрифте не включены «Все прописные»",
            )
        )
    return issues


@rule("heading.trailing_dot", category=Category.HEADING, applies=_applies)
def check_trailing_dot(ctx: RuleContext) -> Iterable[Issue]:
    """Точка в конце заголовка."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings: list[tuple[Paragraph, str]] = []
    for paragraph, heading_rule, _kind in _headings_by_kind(ctx):
        if heading_rule.trailing_dot is None:
            continue
        text = paragraph.text.strip()
        has_dot = text.endswith(".") and not text.endswith("..")
        if has_dot and not heading_rule.trailing_dot:
            findings.append((paragraph, "точка в конце"))
        elif not has_dot and heading_rule.trailing_dot:
            findings.append((paragraph, "нет точки в конце"))
    return ctx.grouped(
        "heading.trailing_dot",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        message=lambda actual, _n, where: (
            f"Точка в конце заголовка не ставится — {where}"
            if actual == "точка в конце"
            else f"В конце заголовка требуется точка — {where}"
        ),
        fix="Удалите точку в конце заголовка",
    )


@rule("heading.bold", category=Category.HEADING, applies=_applies)
def check_bold(ctx: RuleContext) -> Iterable[Issue]:
    """Полужирное начертание заголовков."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings: list[tuple[Paragraph, str]] = []
    for paragraph, heading_rule, _kind in _headings_by_kind(ctx):
        if heading_rule.bold is not None and paragraph.font.bold != heading_rule.bold:
            findings.append((paragraph, "не полужирный" if heading_rule.bold else "полужирный"))
    return ctx.grouped(
        "heading.bold",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        message=lambda actual, _n, where: (
            f"Заголовок должен быть полужирным — {where}"
            if actual == "не полужирный"
            else f"Заголовок не должен быть полужирным — {where}"
        ),
        fix="Выделите заголовок и включите/выключите полужирное начертание (Ctrl+B)",
    )


@rule("heading.underline", category=Category.HEADING, applies=_applies)
def check_underline(ctx: RuleContext) -> Iterable[Issue]:
    """Подчёркивание заголовков."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings = [
        (paragraph, "подчёркнут")
        for paragraph, heading_rule, _ in _headings_by_kind(ctx)
        if heading_rule.underline is False and paragraph.font.underline
    ]
    return ctx.grouped(
        "heading.underline",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        message=lambda _a, _n, where: f"Заголовки не подчёркивают — {where}",
        fix="Снимите подчёркивание (Ctrl+U)",
    )


@rule("heading.alignment", category=Category.HEADING, applies=_applies)
def check_heading_alignment(ctx: RuleContext) -> Iterable[Issue]:
    """Выравнивание заголовков."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings: list[tuple[Paragraph, str]] = []
    expected_names: set[str] = set()
    for paragraph, heading_rule, _kind in _headings_by_kind(ctx):
        if heading_rule.alignment is None:
            continue
        expected = Alignment(heading_rule.alignment)
        accepted = {expected, Alignment.DISTRIBUTE} if expected is Alignment.JUSTIFY else {expected}
        if paragraph.alignment not in accepted:
            findings.append((paragraph, _ALIGN_NAMES[paragraph.alignment]))
            expected_names.add(_ALIGN_NAMES[expected])
    expected_text = ", ".join(sorted(expected_names))
    return ctx.grouped(
        "heading.alignment",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        expected=expected_text or None,
        message=lambda actual, _n, where: (
            f"Заголовок выровнен {actual}, требуется {expected_text} — {where}"
        ),
        fix=f"Выровняйте заголовок {expected_text}",
    )


@rule("heading.indent", category=Category.HEADING, applies=_applies)
def check_heading_indent(ctx: RuleContext) -> Iterable[Issue]:
    """Абзацный отступ заголовков разделов."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    body = ctx.profile.body_text
    indent = body.first_line_indent_cm if body and body.first_line_indent_cm else _DEFAULT_INDENT_CM
    findings: list[tuple[Paragraph, str]] = []
    for paragraph, heading_rule, _kind in _headings_by_kind(ctx):
        if heading_rule.indent is None or paragraph.alignment is Alignment.CENTER:
            continue
        actual = paragraph.first_line_indent_cm + paragraph.left_indent_cm
        if heading_rule.indent == "first_line" and abs(actual - indent) > _INDENT_TOLERANCE_CM:
            findings.append((paragraph, "без абзацного отступа"))
        elif heading_rule.indent == "none" and abs(actual) > _INDENT_TOLERANCE_CM:
            findings.append((paragraph, "с отступом"))
    return ctx.grouped(
        "heading.indent",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        message=lambda actual, _n, where: (
            f"Заголовок напечатан {actual}, требуется "
            + ("с абзацного отступа" if actual == "без абзацного отступа" else "без отступа")
            + f" — {where}"
        ),
        fix="Абзац → Отступ первой строки",
    )


@rule("heading.number_format", category=Category.HEADING, applies=_applies)
def check_number_format(ctx: RuleContext) -> Iterable[Issue]:
    """Точка после номера раздела («1.» вместо «1»)."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings: list[tuple[Paragraph, str]] = []
    for paragraph, heading_rule, _kind in _headings_by_kind(ctx):
        if heading_rule.number_trailing_dot is None:
            continue
        match = _NUMBER_RE.match(paragraph.text)
        if not match:
            continue
        has_dot = bool(match.group(2))
        if has_dot != heading_rule.number_trailing_dot:
            findings.append((paragraph, f"{match.group(1)}{match.group(2)}"))
    want_dot = bool(cfg.section and cfg.section.number_trailing_dot)
    return ctx.grouped(
        "heading.number_format",
        Category.HEADING,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=HEADING_NOUN,
        message=lambda actual, _n, where: (
            f"Номер «{actual}»: "
            + (
                "после номера ставится точка"
                if want_dot
                else "точка после номера раздела не ставится"
            )
            + f" — {where}"
        ),
        fix="Исправьте номер: «1», «1.1» без точки в конце"
        if not want_dot
        else "Добавьте точку после номера",
    )


@rule("heading.new_page", category=Category.HEADING, applies=_applies)
def check_new_page(ctx: RuleContext) -> Iterable[Issue]:
    """Разделы и структурные элементы начинаются с новой страницы."""
    cfg = ctx.profile.headings
    assert cfg is not None  # noqa: S101
    findings = [
        (paragraph, paragraph.text.strip())
        for paragraph, heading_rule, _kind in _headings_by_kind(ctx)
        if heading_rule.new_page and not _starts_new_page(ctx.document, paragraph)
    ]
    issues: list[Issue] = []
    for paragraph, text in findings:
        issues.append(
            ctx.issue(
                "heading.new_page",
                Category.HEADING,
                severity=cfg.severity,
                message=f"«{text}» должен начинаться с новой страницы",
                reference=cfg.source,
                paragraphs=[paragraph],
                fix="Поставьте курсор перед заголовком и вставьте разрыв страницы (Ctrl+Enter) "
                "или включите «С новой страницы» в параметрах абзаца",
            )
        )
    return issues
