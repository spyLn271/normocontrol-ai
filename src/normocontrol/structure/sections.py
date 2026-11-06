"""Структура документа: обязательные разделы, их порядок, соответствие содержания заголовкам."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from normocontrol.parser.model import Document, Paragraph, ParagraphRole
from normocontrol.parser.vocabulary import (
    TOC_LINE_RE,
    heading_number,
    is_toc_heading,
    normalize_title,
)
from normocontrol.profiles.schema import Profile, RequiredSection, Severity, StructureConfig
from normocontrol.report.model import Category, Checker, Issue
from normocontrol.rules.base import RuleContext, rule


@dataclass(frozen=True, slots=True)
class SectionMatch:
    required: RequiredSection
    paragraph: Paragraph | None
    exact: bool = True
    score: float = 100.0


def _structure(ctx: RuleContext) -> StructureConfig:
    assert ctx.profile.structure is not None  # noqa: S101
    return ctx.profile.structure


def _has_required(profile: Profile) -> bool:
    return bool(profile.structure and profile.structure.required_sections)


def match_sections(document: Document, cfg: StructureConfig) -> list[SectionMatch]:
    """Сопоставить обязательные разделы профиля с заголовками документа."""
    headings = [h for h in document.headings if h.heading_level is None or h.heading_level <= 2]
    used: set[int] = set()
    matches: list[SectionMatch] = []
    for required in cfg.required_sections:
        if required.kind == "title_page":
            title = next(iter(document.by_role(ParagraphRole.TITLE_PAGE)), None)
            matches.append(SectionMatch(required, title))
            continue
        if required.any_heading:
            matches.append(SectionMatch(required, None))  # заполняется ниже
            continue
        matches.append(_match_heading(required, headings, used, cfg.fuzzy_threshold))

    # «Основная часть» — первый нумерованный раздел между соседними найденными разделами
    resolved: list[SectionMatch] = []
    for position, match in enumerate(matches):
        if not match.required.any_heading:
            resolved.append(match)
            continue
        lower = max(
            (m.paragraph.index for m in matches[:position] if m.paragraph is not None), default=-1
        )
        upper = min(
            (m.paragraph.index for m in matches[position + 1 :] if m.paragraph is not None),
            default=len(document.paragraphs),
        )
        numbered_headings = [h for h in headings if heading_number(h.text) is not None]
        numbered = next((h for h in numbered_headings if lower < h.index < upper), None)
        if numbered is None and numbered_headings:
            # разделы есть, но стоят не на месте — об этом скажет проверка порядка
            numbered = numbered_headings[0]
        resolved.append(SectionMatch(match.required, numbered))
    return resolved


def _match_heading(
    required: RequiredSection,
    headings: list[Paragraph],
    used: set[int],
    threshold: float,
) -> SectionMatch:
    names = [normalize_title(name) for name in (required.name, *required.aliases)]
    best: tuple[float, Paragraph] | None = None
    for heading in headings:
        if heading.index in used:
            continue
        text = normalize_title(heading.text)
        if text in names or any(text.startswith(f"{name} ") for name in names):
            used.add(heading.index)
            return SectionMatch(required, heading, exact=True)
        score = max(fuzz.ratio(text, name) for name in names)
        if score >= threshold and (best is None or score > best[0]):
            best = (score, heading)
    if best is not None:
        used.add(best[1].index)
        return SectionMatch(required, best[1], exact=False, score=best[0])
    return SectionMatch(required, None)


@rule(
    "structure.required_sections",
    category=Category.STRUCTURE,
    checker=Checker.STRUCTURE,
    applies=_has_required,
)
def check_required_sections(ctx: RuleContext) -> Iterable[Issue]:
    """Обязательные структурные элементы документа."""
    cfg = _structure(ctx)
    issues: list[Issue] = []
    for match in match_sections(ctx.document, cfg):
        required = match.required
        if match.paragraph is None:
            if required.optional:
                continue
            what = (
                "титульный лист" if required.kind == "title_page" else f"раздел «{required.name}»"
            )
            issues.append(
                ctx.issue(
                    "structure.required_sections",
                    Category.STRUCTURE,
                    severity=cfg.severity,
                    message=f"В документе отсутствует {what}",
                    reference=cfg.source,
                    expected=required.name,
                    actual="нет",
                    fix=(
                        "Добавьте основную часть — нумерованные разделы (1, 2, …)"
                        if required.any_heading
                        else f"Добавьте структурный элемент «{required.name}» отдельным заголовком"
                    ),
                    checker=Checker.STRUCTURE,
                )
            )
        elif not match.exact:
            actual = match.paragraph.text.strip()
            issues.append(
                ctx.issue(
                    "structure.section_title",
                    Category.STRUCTURE,
                    severity=Severity.WARNING,
                    message=f"Название «{actual}» отличается от требуемого «{required.name}»",
                    reference=cfg.source,
                    paragraphs=[match.paragraph],
                    expected=required.name,
                    actual=actual,
                    fix=f"Исправьте заголовок на «{required.name}»",
                    checker=Checker.STRUCTURE,
                )
            )
    return issues


def _longest_increasing(values: list[int]) -> set[int]:
    """Позиции элементов, образующих самую длинную возрастающую подпоследовательность."""
    best: list[list[int]] = []
    for position, value in enumerate(values):
        chain: list[int] = []
        for candidate in best:
            if values[candidate[-1]] < value and len(candidate) > len(chain):
                chain = candidate
        best.append([*chain, position])
    longest: list[int] = []
    for candidate in best:
        if len(candidate) > len(longest):
            longest = candidate
    return set(longest)


@rule(
    "structure.order",
    category=Category.STRUCTURE,
    checker=Checker.STRUCTURE,
    applies=lambda p: bool(_has_required(p) and p.structure and p.structure.check_order),
)
def check_order(ctx: RuleContext) -> Iterable[Issue]:
    """Порядок структурных элементов: сообщаем о тех, что стоят не на своём месте."""
    cfg = _structure(ctx)
    found = [m for m in match_sections(ctx.document, cfg) if m.paragraph is not None]
    positions = [m.paragraph.index for m in found if m.paragraph is not None]
    in_order = _longest_increasing(positions)
    issues: list[Issue] = []
    for position, match in enumerate(found):
        if position in in_order or match.paragraph is None:
            continue
        before = next((found[i] for i in range(position - 1, -1, -1) if i in in_order), None)
        after = next((found[i] for i in range(position + 1, len(found)) if i in in_order), None)
        where = []
        if before is not None:
            where.append(f"после «{before.required.name}»")
        if after is not None:
            where.append(f"перед «{after.required.name}»")
        issues.append(
            ctx.issue(
                "structure.order",
                Category.STRUCTURE,
                severity=cfg.severity,
                message=f"Нарушен порядок разделов: «{match.required.name}» должен идти "
                + " и ".join(where),
                reference=cfg.source,
                paragraphs=[match.paragraph],
                expected=" → ".join(m.required.name for m in found),
                fix="Переместите раздел в соответствии с требуемой структурой",
                checker=Checker.STRUCTURE,
            )
        )
    return issues


def toc_entries(document: Document) -> list[tuple[Paragraph, str]]:
    entries: list[tuple[Paragraph, str]] = []
    for paragraph in document.by_role(ParagraphRole.TOC):
        text = paragraph.text.strip()
        if not text:
            continue
        match = TOC_LINE_RE.match(text)
        title = match.group("title") if match else text
        title = title.rstrip(" .…·_\t")
        entries.append((paragraph, title))
    return entries


@rule(
    "structure.toc_matches",
    category=Category.STRUCTURE,
    checker=Checker.STRUCTURE,
    applies=lambda p: bool(p.structure and p.structure.toc_matches_headings),
)
def check_toc(ctx: RuleContext) -> Iterable[Issue]:
    """Содержание точно повторяет заголовки в тексте."""
    cfg = _structure(ctx)
    document = ctx.document
    toc_heading = next((h for h in document.headings if is_toc_heading(h.text)), None)
    entries = toc_entries(document)
    if toc_heading is None:
        return []
    if not entries:
        return [
            ctx.issue(
                "structure.toc_matches",
                Category.STRUCTURE,
                severity=cfg.severity,
                message="Содержание пустое или не распознано",
                reference=cfg.source,
                paragraphs=[toc_heading],
                fix="Вставьте автоматическое оглавление (Ссылки → Оглавление) и обновите его",
                checker=Checker.STRUCTURE,
            )
        ]

    headings = [
        h for h in document.headings if h.index > toc_heading.index and (h.heading_level or 1) <= 3
    ]
    heading_titles = {normalize_title(h.text): h for h in headings}
    entry_titles = {normalize_title(title): (p, title) for p, title in entries}
    issues: list[Issue] = []

    missing = [h for norm, h in heading_titles.items() if norm not in entry_titles]
    if missing:
        issues.append(
            ctx.issue(
                "structure.toc_matches",
                Category.STRUCTURE,
                severity=cfg.severity,
                message="Заголовки отсутствуют в содержании: "
                + ", ".join(f"«{h.text.strip()}»" for h in missing[:5])
                + (" и др." if len(missing) > 5 else ""),
                reference=cfg.source,
                paragraphs=missing,
                fix="Обновите оглавление (правой кнопкой → Обновить поле → Обновить целиком)",
                checker=Checker.STRUCTURE,
            )
        )
    choices = list(heading_titles)
    for norm, (paragraph, title) in entry_titles.items():
        if norm in heading_titles:
            continue
        suggestion = process.extractOne(norm, choices, scorer=fuzz.ratio) if choices else None
        hint = ""
        if suggestion is not None and suggestion[1] >= 70:
            hint = f"; в тексте: «{heading_titles[suggestion[0]].text.strip()}»"
        issues.append(
            ctx.issue(
                "structure.toc_matches",
                Category.STRUCTURE,
                severity=cfg.severity,
                message=f"Пункт содержания «{title}» не совпадает с заголовком в тексте{hint}",
                reference=cfg.source,
                paragraphs=[paragraph],
                actual=title,
                fix="Заголовки содержания должны точно повторять заголовки в тексте — "
                "обновите автоматическое оглавление",
                checker=Checker.STRUCTURE,
            )
        )
    return issues
