"""Реквизиты служебных документов и формат дат (Правила документирования РК)."""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable

from normocontrol.parser.model import Alignment, Paragraph, ParagraphRole
from normocontrol.profiles.schema import DatesConfig, Requisite, Severity
from normocontrol.report.model import Category, Issue
from normocontrol.rules.base import RuleContext, rule

_MONTHS_RU = "января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря"
_MONTHS_KK = "қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан"
_NUMERIC_DATE = re.compile(r"(?<![\d.])(\d{1,4})([./-])(\d{1,2})\2(\d{1,4})(?![\d.]*\d)")
_VERBAL_DATE = re.compile(
    rf"\b\d{{1,2}}\s+(?:{_MONTHS_RU})\s+\d{{4}}|\b\d{{4}}\s+жылғы\s+\d{{1,2}}\s+(?:{_MONTHS_KK})",
    re.IGNORECASE,
)
_SKIP_ROLES = (ParagraphRole.BIBLIOGRAPHY_ENTRY, ParagraphRole.TOC)
_ALIGN_NAMES = {"left": "по левому краю", "center": "по центру", "right": "по правому краю"}


def _search_space(ctx: RuleContext) -> list[Paragraph]:
    return [p for p in ctx.document.paragraphs if p.role not in _SKIP_ROLES and not p.is_empty]


def _check_requisite(
    ctx: RuleContext, item: Requisite, severity: Severity, section_source: str | None
) -> list[Issue]:
    pattern = re.compile(item.pattern, re.IGNORECASE)
    reference = item.source or section_source
    rule_id = f"requisites.{item.id}"
    found = [p for p in _search_space(ctx) if pattern.search(p.text.strip())]
    if not found:
        if not item.required:
            return []
        return [
            ctx.issue(
                rule_id,
                Category.REQUISITES,
                severity=severity,
                message=f"Отсутствует обязательный реквизит: {item.name}",
                reference=reference,
                expected=item.name,
                actual="нет",
                fix=f"Добавьте реквизит «{item.name}»",
            )
        ]
    paragraph = found[0]
    match = pattern.search(paragraph.text.strip())
    assert match is not None  # noqa: S101
    shown = match.group(0).strip()
    problems: list[str] = []
    if item.uppercase:
        letters = [c for c in shown if c.isalpha()]
        if letters and not paragraph.font.all_caps and not all(c.isupper() for c in letters):
            problems.append("прописными буквами")
    if item.bold and not _matched_bold(paragraph, match.group(0)):
        problems.append("полужирным шрифтом")
    if item.alignment and paragraph.alignment is not Alignment(item.alignment):
        problems.append(_ALIGN_NAMES.get(item.alignment, item.alignment))
    if not problems:
        return []
    return [
        ctx.issue(
            rule_id,
            Category.REQUISITES,
            severity=severity,
            message=f"Реквизит «{shown}» должен быть оформлен " + ", ".join(problems),
            reference=reference,
            paragraphs=[paragraph],
            expected=", ".join(problems),
            actual=shown,
            quote=shown,
            fix=f"Оформите «{shown}» " + ", ".join(problems),
        )
    ]


def _matched_bold(paragraph: Paragraph, fragment: str) -> bool:
    """Жирность проверяем у run'ов, из которых состоит найденный фрагмент."""
    target = fragment.strip()
    if not target:
        return paragraph.font.bold
    position = 0
    covering = []
    start = paragraph.text.find(target)
    end = start + len(target)
    for run in paragraph.runs:
        run_start, run_end = position, position + len(run.text)
        position = run_end
        if run_end > start and run_start < end and run.text.strip():
            covering.append(run)
    return bool(covering) and all(run.font.bold for run in covering)


@rule(
    "requisites",
    category=Category.REQUISITES,
    applies=lambda p: bool(p.requisites and p.requisites.items),
)
def check_requisites(ctx: RuleContext) -> Iterable[Issue]:
    """Наличие и оформление реквизитов документа."""
    cfg = ctx.profile.requisites
    assert cfg is not None  # noqa: S101
    issues: list[Issue] = []
    for item in cfg.items:
        issues.extend(_check_requisite(ctx, item, cfg.severity, cfg.source))
    return issues


def _valid_numeric(day: str, month: str, year: str) -> bool:
    if len(day) != 2 or len(month) != 2 or len(year) != 4:
        return False
    d, m, y = int(day), int(month), int(year)
    return 1 <= m <= 12 and 1 <= d <= calendar.monthrange(y, m)[1]


@rule("dates.format", category=Category.REQUISITES, applies=lambda p: p.dates is not None)
def check_dates(ctx: RuleContext) -> Iterable[Issue]:
    """Формат дат: ДД.ММ.ГГГГ или словесно-цифровой."""
    cfg: DatesConfig | None = ctx.profile.dates
    assert cfg is not None  # noqa: S101
    allow_numeric = "numeric" in cfg.formats
    allow_verbal = "verbal" in cfg.formats
    findings: list[tuple[Paragraph, str]] = []
    for paragraph in _search_space(ctx):
        text = paragraph.text
        if "http" in text or "www." in text:
            text = re.sub(r"\S*(https?://|www\.)\S*", " ", text)
        for match in _NUMERIC_DATE.finditer(text):
            first, separator, month, last = match.groups()
            if len(first) == 4:  # 2023-09-05 — ISO-формат
                if len(last) <= 2 and 1 <= int(month) <= 12:
                    findings.append((paragraph, match.group(0)))
                continue
            # «1.1.1» и «2.3.4» — номера пунктов, а не даты
            looks_like_date = (
                len(first) <= 2
                and len(last) in {2, 4}
                and 1 <= int(month) <= 12
                and 1 <= int(first) <= 31
            )
            if looks_like_date and (
                separator != "." or not allow_numeric or not _valid_numeric(first, month, last)
            ):
                findings.append((paragraph, match.group(0)))
        if not allow_verbal:
            findings.extend((paragraph, m.group(0)) for m in _VERBAL_DATE.finditer(text))

    expected = " или ".join(
        part
        for part, enabled in (
            ("ДД.ММ.ГГГГ (05.09.2023)", allow_numeric),
            ("«5 сентября 2023 года»", allow_verbal),
        )
        if enabled
    )
    issues: list[Issue] = []
    for paragraph, actual in findings:
        issues.append(
            ctx.issue(
                "dates.format",
                Category.REQUISITES,
                severity=cfg.severity,
                message=f"Дата «{actual}» оформлена неверно, требуется {expected}",
                reference=cfg.source,
                paragraphs=[paragraph],
                expected=expected,
                actual=actual,
                quote=actual,
                fix="День и месяц — двумя цифрами через точку, год — четырьмя: 05.09.2023",
            )
        )
    return issues
