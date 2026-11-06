"""Список литературы: ссылки в тексте на каждый источник, порядок, нумерация записей."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from normocontrol.parser.model import Document, Paragraph, ParagraphRole
from normocontrol.profiles.schema import BibliographyConfig
from normocontrol.report.model import Category, Checker, Issue
from normocontrol.rules.base import RuleContext, plural, rule

_ENTRY_NUMBER_RE = re.compile(r"^\s*(\d{1,3})(\.)?[\s\t]+\S")
_CITATION_RE = re.compile(r"\[([^\[\]\n]{1,80})\]")
_RANGE_RE = re.compile(r"^\s*(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*$")
_SINGLE_RE = re.compile(r"^\s*(\d{1,3})\s*$")
_CITING_ROLES = (
    ParagraphRole.BODY,
    ParagraphRole.LIST_ITEM,
    ParagraphRole.TABLE_CELL,
    ParagraphRole.FIGURE_CAPTION,
    ParagraphRole.TABLE_CAPTION,
    ParagraphRole.HEADING,
)


@dataclass(frozen=True, slots=True)
class Entry:
    paragraph: Paragraph
    number: int
    manual: bool  # номер набран вручную, а не автонумерацией Word
    trailing_dot: bool


def entries(document: Document) -> list[Entry]:
    result: list[Entry] = []
    for ordinal, paragraph in enumerate(document.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY), 1):
        match = _ENTRY_NUMBER_RE.match(paragraph.text)
        if match:
            result.append(Entry(paragraph, int(match.group(1)), True, bool(match.group(2))))
        else:
            label = paragraph.numbering.label if paragraph.numbering else None
            result.append(
                Entry(paragraph, ordinal, False, bool(label and label.rstrip().endswith(".")))
            )
    return result


def citations(document: Document) -> list[tuple[int, Paragraph]]:
    """Номера источников из ссылок вида [1], [1, с. 25], [2; 5], [3–6] в порядке появления."""
    result: list[tuple[int, Paragraph]] = []
    for paragraph in document.by_role(*_CITING_ROLES):
        for match in _CITATION_RE.finditer(paragraph.text):
            for part in re.split(r"[;,]", match.group(1)):
                if range_match := _RANGE_RE.match(part):
                    start, end = int(range_match.group(1)), int(range_match.group(2))
                    if 0 < end - start < 50:
                        result.extend((n, paragraph) for n in range(start, end + 1))
                elif single := _SINGLE_RE.match(part):
                    result.append((int(single.group(1)), paragraph))
    return result


def _cfg(ctx: RuleContext) -> BibliographyConfig:
    assert ctx.profile.bibliography is not None  # noqa: S101
    return ctx.profile.bibliography


@rule(
    "bibliography.cited",
    category=Category.BIBLIOGRAPHY,
    checker=Checker.STRUCTURE,
    applies=lambda p: bool(p.bibliography and p.bibliography.require_citation_in_text),
)
def check_cited(ctx: RuleContext) -> Iterable[Issue]:
    """На каждый источник есть ссылка в тексте, и каждая ссылка ведёт к источнику."""
    cfg = _cfg(ctx)
    items = entries(ctx.document)
    if not items:
        return []
    cited = citations(ctx.document)
    cited_numbers = {number for number, _ in cited}
    known = {entry.number for entry in items}
    issues: list[Issue] = []

    uncited = [entry for entry in items if entry.number not in cited_numbers]
    if uncited:
        numbers = ", ".join(str(e.number) for e in uncited[:15])
        issues.append(
            ctx.issue(
                "bibliography.cited",
                Category.BIBLIOGRAPHY,
                severity=cfg.severity,
                message=f"Нет ссылок в тексте на источники: {numbers}"
                + (" и др." if len(uncited) > 15 else ""),
                reference=cfg.source,
                paragraphs=[e.paragraph for e in uncited],
                fix="Добавьте ссылку в квадратных скобках, например [3], или удалите источник",
                checker=Checker.STRUCTURE,
            )
        )
    unknown: dict[int, Paragraph] = {}
    for number, paragraph in cited:
        if number not in known:
            unknown.setdefault(number, paragraph)
    if unknown:
        issues.append(
            ctx.issue(
                "bibliography.unknown_citation",
                Category.BIBLIOGRAPHY,
                severity=cfg.severity,
                message="Ссылки на отсутствующие в списке источники: "
                + ", ".join(f"[{n}]" for n in sorted(unknown)),
                reference=cfg.source,
                paragraphs=list({p.id: p for p in unknown.values()}.values()),
                fix="Проверьте номера ссылок или добавьте источники в список",
                checker=Checker.STRUCTURE,
            )
        )
    return issues


@rule(
    "bibliography.order",
    category=Category.BIBLIOGRAPHY,
    checker=Checker.STRUCTURE,
    applies=lambda p: bool(p.bibliography and p.bibliography.order != "any"),
)
def check_order(ctx: RuleContext) -> Iterable[Issue]:
    """Порядок источников: по появлению ссылок или по алфавиту."""
    cfg = _cfg(ctx)
    items = entries(ctx.document)
    if len(items) < 2:
        return []
    if cfg.order == "alphabetical":
        names = [re.sub(r"^\s*\d{1,3}\.?\s*", "", e.paragraph.text).casefold() for e in items]
        if names != sorted(names):
            return [
                ctx.issue(
                    "bibliography.order",
                    Category.BIBLIOGRAPHY,
                    severity=cfg.severity,
                    message="Источники должны располагаться в алфавитном порядке",
                    reference=cfg.source,
                    paragraphs=[items[0].paragraph],
                    fix="Отсортируйте список (Главная → Сортировка)",
                    checker=Checker.STRUCTURE,
                )
            ]
        return []

    known = {e.number for e in items}
    first_seen: list[int] = []
    for number, _ in citations(ctx.document):
        if number in known and number not in first_seen:
            first_seen.append(number)
    for previous, current in pairwise(first_seen):
        if current < previous:
            entry = next(e for e in items if e.number == current)
            return [
                ctx.issue(
                    "bibliography.order",
                    Category.BIBLIOGRAPHY,
                    severity=cfg.severity,
                    message=(
                        f"Источники нумеруются в порядке появления ссылок: [{previous}] "
                        f"упоминается в тексте раньше, чем [{current}]"
                    ),
                    reference=cfg.source,
                    paragraphs=[entry.paragraph],
                    fix="Перенумеруйте источники в порядке первого упоминания в тексте",
                    checker=Checker.STRUCTURE,
                )
            ]
    return []


@rule(
    "bibliography.numbering",
    category=Category.BIBLIOGRAPHY,
    checker=Checker.STRUCTURE,
    applies=lambda p: bool(p.bibliography and p.bibliography.entry_number_trailing_dot is not None),
)
def check_numbering(ctx: RuleContext) -> Iterable[Issue]:
    """Номер записи списка литературы: «1 Иванов…» без точки (или с точкой — по профилю)."""
    cfg = _cfg(ctx)
    want_dot = cfg.entry_number_trailing_dot
    wrong = [e for e in entries(ctx.document) if e.trailing_dot != want_dot]
    if not wrong:
        return []
    expected = "с точкой («1. Иванов…»)" if want_dot else "без точки («1 Иванов…»)"
    return [
        ctx.issue(
            "bibliography.numbering",
            Category.BIBLIOGRAPHY,
            severity=cfg.severity,
            message=f"Источники нумеруют арабскими цифрами {expected} — нарушено в "
            f"{len(wrong)} {plural(len(wrong), 'записи', 'записях', 'записях')}",
            reference=cfg.source,
            paragraphs=[e.paragraph for e in wrong],
            expected=expected,
            fix="Измените формат номера списка (Главная → Нумерация → Определить новый формат)",
            checker=Checker.STRUCTURE,
        )
    ]


__all__ = ["Entry", "citations", "entries"]
