"""Рисунки и таблицы: формат и положение подписей, нумерация, ссылки в тексте."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from normocontrol.parser.model import Alignment, Document, Paragraph, ParagraphRole, Table
from normocontrol.profiles.schema import CaptionConfig, Profile
from normocontrol.report.model import Category, Checker, Issue
from normocontrol.rules.base import CAPTION_NOUN, AppliesFunc, RuleContext, rule

type Kind = Literal["figures", "tables"]

_NUMBER_RE = re.compile(
    r"^\s*(?:рисунок|рис\.|сурет|таблица|кесте)\s*(?P<letter>[А-ЯA-Z](?=[\s.]?\d))?[\s.]?"
    r"(?P<number>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_KZ_NUMBER_RE = re.compile(r"^\s*(?P<number>\d+(?:\.\d+)?)\s*[-–]\s*(?:сурет|кесте)", re.IGNORECASE)
_CONTINUATION_RE = re.compile(r"^\s*(продолжение|окончание)\s+таблицы|жалғасы", re.IGNORECASE)
_REF_KEYWORDS: dict[Kind, str] = {
    "figures": r"(?:рисун\w*|рис\.|сурет\w*)",
    "tables": r"(?:таблиц\w*|табл\.|кесте\w*)",
}
_NUM = r"(?:[А-ЯA-Z]\s?\.?\s?)?\d+(?:\.\d+)?"
_NAMES: dict[Kind, tuple[str, str]] = {
    "figures": ("Рисунок", "рисунок"),
    "tables": ("Таблица", "таблицу"),
}
_ALIGN_NAMES = {
    Alignment.LEFT: "по левому краю",
    Alignment.CENTER: "по центру",
    Alignment.RIGHT: "по правому краю",
    Alignment.JUSTIFY: "по ширине",
    Alignment.DISTRIBUTE: "по ширине",
}


@dataclass(frozen=True, slots=True)
class Caption:
    paragraph: Paragraph
    number: str | None
    appendix_letter: str | None
    continuation: bool


def _cfg(ctx: RuleContext, kind: Kind) -> CaptionConfig:
    cfg: CaptionConfig | None = getattr(ctx.profile, kind)
    assert cfg is not None  # noqa: S101
    return cfg


def captions(document: Document, kind: Kind) -> list[Caption]:
    role = ParagraphRole.FIGURE_CAPTION if kind == "figures" else ParagraphRole.TABLE_CAPTION
    result = []
    for paragraph in document.by_role(role):
        text = paragraph.text.strip()
        match = _NUMBER_RE.match(text) or _KZ_NUMBER_RE.match(text)
        letter = match.groupdict().get("letter") if match else None
        result.append(
            Caption(
                paragraph=paragraph,
                number=match.group("number") if match else None,
                appendix_letter=letter.upper() if letter else None,
                continuation=bool(_CONTINUATION_RE.search(text)),
            )
        )
    return result


def _applies(kind: Kind) -> AppliesFunc:
    def applies(profile: Profile) -> bool:
        return getattr(profile, kind) is not None

    return applies


def _neighbour(document: Document, index: int, step: int, limit: int = 3) -> Paragraph | None:
    """Ближайший непустой абзац вне таблиц (или абзац-рисунок) в направлении ``step``."""
    position = index + step
    checked = 0
    while 0 <= position < len(document.paragraphs) and checked < limit:
        paragraph = document.paragraphs[position]
        position += step
        if paragraph.in_table:
            continue
        checked += 1
        if paragraph.role is ParagraphRole.IMAGE or not paragraph.is_empty:
            return paragraph
    return None


# ---------------------------------------------------------------------- format


def _check_format(ctx: RuleContext, kind: Kind) -> list[Issue]:
    cfg = _cfg(ctx, kind)
    if cfg.caption_pattern is None:
        return []
    pattern = re.compile(cfg.caption_pattern)
    findings = [
        (c.paragraph, c.paragraph.text.strip())
        for c in captions(ctx.document, kind)
        if not c.continuation and not pattern.match(c.paragraph.text.strip())
    ]
    title, _ = _NAMES[kind]
    issues = []
    for paragraph, text in findings:
        issues.append(
            ctx.issue(
                f"{kind}.caption_format",
                Category.FIGURES if kind == "figures" else Category.TABLES,
                severity=cfg.severity,
                message=f"Подпись «{text}» оформлена не по образцу «{title} 1 – Название»",
                reference=cfg.source,
                paragraphs=[paragraph],
                actual=text,
                expected=f"{title} N – Название",
                fix=f"Оформите подпись: «{title} 1 – Название» (номер, пробел, тире, название)",
                checker=Checker.STRUCTURE,
            )
        )
    return issues


@rule(
    "figures.caption_format",
    category=Category.FIGURES,
    checker=Checker.STRUCTURE,
    applies=_applies("figures"),
)
def check_figure_format(ctx: RuleContext) -> Iterable[Issue]:
    """Формат подписи рисунка."""
    return _check_format(ctx, "figures")


@rule(
    "tables.caption_format",
    category=Category.TABLES,
    checker=Checker.STRUCTURE,
    applies=_applies("tables"),
)
def check_table_format(ctx: RuleContext) -> Iterable[Issue]:
    """Формат названия таблицы."""
    return _check_format(ctx, "tables")


# ---------------------------------------------------------------------- position & missing


def _table_caption_above(document: Document, table: Table) -> Paragraph | None:
    if table.preceding_paragraph_index < 0:
        return None
    candidate = document.paragraphs[table.preceding_paragraph_index]
    if candidate.is_empty:
        candidate = _neighbour(document, candidate.index, -1, limit=1) or candidate
    return candidate if candidate.role is ParagraphRole.TABLE_CAPTION else None


def _table_caption_below(document: Document, table: Table) -> Paragraph | None:
    if table.following_paragraph_index is None:
        return None
    candidate = document.paragraphs[table.following_paragraph_index]
    if candidate.is_empty:
        candidate = _neighbour(document, candidate.index, 1, limit=1) or candidate
    return candidate if candidate.role is ParagraphRole.TABLE_CAPTION else None


def _is_layout_table(document: Document, table: Table) -> bool:
    if table.rows < 2:
        return True
    cells = [document.paragraph(pid) for pid in table.cell_paragraph_ids]
    return any(c is not None and c.role is ParagraphRole.TITLE_PAGE for c in cells)


@rule(
    "tables.caption_position",
    category=Category.TABLES,
    checker=Checker.STRUCTURE,
    applies=_applies("tables"),
)
def check_table_position(ctx: RuleContext) -> Iterable[Issue]:
    """Название таблицы над таблицей; таблицы без названия."""
    cfg = _cfg(ctx, "tables")
    document = ctx.document
    issues: list[Issue] = []
    for table in document.tables:
        if _is_layout_table(document, table):
            continue
        above = _table_caption_above(document, table)
        below = _table_caption_below(document, table)
        cells = [p for pid in table.cell_paragraph_ids[:1] if (p := document.paragraph(pid))]
        if above is None and below is None:
            issues.append(
                ctx.issue(
                    "tables.caption_missing",
                    Category.TABLES,
                    severity=cfg.severity,
                    message=f"У таблицы {table.index + 1} нет названия «Таблица N – …»",
                    reference=cfg.source,
                    paragraphs=cells,
                    fix="Добавьте над таблицей строку «Таблица 1 – Название»",
                    checker=Checker.STRUCTURE,
                )
            )
            continue
        position = cfg.caption_position
        wrong = (position == "above" and above is None) or (position == "below" and below is None)
        if position and wrong:
            caption = below or above
            assert caption is not None  # noqa: S101
            issues.append(
                ctx.issue(
                    "tables.caption_position",
                    Category.TABLES,
                    severity=cfg.severity,
                    message=f"Название «{caption.text.strip()}» должно располагаться "
                    + ("над таблицей" if position == "above" else "под таблицей"),
                    reference=cfg.source,
                    paragraphs=[caption],
                    fix="Перенесите название таблицы "
                    + ("над" if position == "above" else "под")
                    + " таблицу",
                    checker=Checker.STRUCTURE,
                )
            )
    return issues


@rule(
    "figures.caption_position",
    category=Category.FIGURES,
    checker=Checker.STRUCTURE,
    applies=_applies("figures"),
)
def check_figure_position(ctx: RuleContext) -> Iterable[Issue]:
    """Подпись рисунка под рисунком; рисунки без подписи."""
    cfg = _cfg(ctx, "figures")
    document = ctx.document
    issues: list[Issue] = []
    for paragraph in document.by_role(ParagraphRole.IMAGE):
        before = _neighbour(document, paragraph.index, -1, limit=2)
        after = _neighbour(document, paragraph.index, 1, limit=2)
        has_after = after is not None and after.role is ParagraphRole.FIGURE_CAPTION
        has_before = before is not None and before.role is ParagraphRole.FIGURE_CAPTION
        if not has_after and not has_before:
            issues.append(
                ctx.issue(
                    "figures.caption_missing",
                    Category.FIGURES,
                    severity=cfg.severity,
                    message="У рисунка нет подписи «Рисунок N – …»",
                    reference=cfg.source,
                    paragraphs=[paragraph],
                    fix="Добавьте под рисунком подпись «Рисунок 1 – Название»",
                    checker=Checker.STRUCTURE,
                )
            )
        elif cfg.caption_position == "below" and has_before and not has_after:
            assert before is not None  # noqa: S101
            issues.append(
                ctx.issue(
                    "figures.caption_position",
                    Category.FIGURES,
                    severity=cfg.severity,
                    message=f"Подпись «{before.text.strip()}» должна располагаться под рисунком",
                    reference=cfg.source,
                    paragraphs=[before],
                    fix="Перенесите подпись под рисунок",
                    checker=Checker.STRUCTURE,
                )
            )
    return issues


# ---------------------------------------------------------------------- alignment & indent


def _check_alignment(ctx: RuleContext, kind: Kind) -> list[Issue]:
    cfg = _cfg(ctx, kind)
    findings: list[tuple[Paragraph, str]] = []
    for caption in captions(ctx.document, kind):
        paragraph = caption.paragraph
        if caption.continuation:
            continue
        if cfg.caption_alignment is not None:
            expected = Alignment(cfg.caption_alignment)
            if paragraph.alignment is not expected:
                findings.append((paragraph, f"выравнивание {_ALIGN_NAMES[paragraph.alignment]}"))
                continue
        if cfg.caption_indent == "none":
            indent = paragraph.first_line_indent_cm + paragraph.left_indent_cm
            if paragraph.alignment is not Alignment.CENTER and abs(indent) > 0.1:
                findings.append((paragraph, "абзацный отступ"))
    expected_parts = []
    if cfg.caption_alignment:
        expected_parts.append(_ALIGN_NAMES[Alignment(cfg.caption_alignment)])
    if cfg.caption_indent == "none":
        expected_parts.append("без абзацного отступа")
    expected_text = ", ".join(expected_parts)
    category = Category.FIGURES if kind == "figures" else Category.TABLES
    return ctx.grouped(
        f"{kind}.caption_alignment",
        category,
        severity=cfg.severity,
        reference=cfg.source,
        findings=findings,
        noun=CAPTION_NOUN,
        expected=expected_text,
        checker=Checker.STRUCTURE,
        message=lambda actual, _n, where: f"Подпись: {actual}, требуется {expected_text} — {where}",
        fix=f"Оформите подпись: {expected_text}",
    )


@rule(
    "figures.caption_alignment",
    category=Category.FIGURES,
    checker=Checker.STRUCTURE,
    applies=_applies("figures"),
)
def check_figure_alignment(ctx: RuleContext) -> Iterable[Issue]:
    """Выравнивание подписей рисунков."""
    return _check_alignment(ctx, "figures")


@rule(
    "tables.caption_alignment",
    category=Category.TABLES,
    checker=Checker.STRUCTURE,
    applies=_applies("tables"),
)
def check_table_alignment(ctx: RuleContext) -> Iterable[Issue]:
    """Выравнивание и отступ названий таблиц."""
    return _check_alignment(ctx, "tables")


# ---------------------------------------------------------------------- numbering


def _numbering_problem(numbers: list[str], mode: str) -> str | None:
    if not numbers:
        return None
    if len(set(numbers)) != len(numbers):
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        return "повторяются номера " + ", ".join(duplicates)
    continuous_ok = all("." not in n for n in numbers) and [int(n) for n in numbers] == list(
        range(1, len(numbers) + 1)
    )
    per_section_ok = _per_section_ok(numbers)
    if mode == "continuous" and not continuous_ok:
        return "нумерация должна быть сквозной (1, 2, 3…), сейчас: " + ", ".join(numbers[:8])
    if mode == "per_section" and not per_section_ok:
        return "нумерация должна быть в пределах раздела (1.1, 1.2, 2.1…), сейчас: " + ", ".join(
            numbers[:8]
        )
    if mode == "any" and not (continuous_ok or per_section_ok):
        return "нарушен порядок нумерации: " + ", ".join(numbers[:8])
    return None


def _per_section_ok(numbers: list[str]) -> bool:
    last: dict[int, int] = {}
    previous_section = 0
    for number in numbers:
        if "." not in number:
            return False
        section_text, item_text = number.split(".", 1)
        section, item = int(section_text), int(item_text)
        if section < previous_section or item != last.get(section, 0) + 1:
            return False
        last[section] = item
        previous_section = section
    return True


def _check_numbering(ctx: RuleContext, kind: Kind) -> list[Issue]:
    cfg = _cfg(ctx, kind)
    items = [
        c
        for c in captions(ctx.document, kind)
        if not c.continuation and c.appendix_letter is None and c.number
    ]
    problem = _numbering_problem([c.number for c in items if c.number], cfg.numbering)
    if problem is None:
        return []
    title, _ = _NAMES[kind]
    return [
        ctx.issue(
            f"{kind}.numbering",
            Category.FIGURES if kind == "figures" else Category.TABLES,
            severity=cfg.severity,
            message=f"{title}: {problem}",
            reference=cfg.source,
            paragraphs=[c.paragraph for c in items],
            fix="Перенумеруйте подписи по порядку (лучше — через Ссылки → Вставить название)",
            checker=Checker.STRUCTURE,
        )
    ]


@rule(
    "figures.numbering",
    category=Category.FIGURES,
    checker=Checker.STRUCTURE,
    applies=_applies("figures"),
)
def check_figure_numbering(ctx: RuleContext) -> Iterable[Issue]:
    """Нумерация рисунков."""
    return _check_numbering(ctx, "figures")


@rule(
    "tables.numbering",
    category=Category.TABLES,
    checker=Checker.STRUCTURE,
    applies=_applies("tables"),
)
def check_table_numbering(ctx: RuleContext) -> Iterable[Issue]:
    """Нумерация таблиц."""
    return _check_numbering(ctx, "tables")


# ---------------------------------------------------------------------- references


def _norm_number(raw: str) -> str:
    return re.sub(r"[\s]", "", raw).replace("..", ".").upper()


def referenced_numbers(document: Document, kind: Kind) -> set[str]:
    keyword = _REF_KEYWORDS[kind]
    forward = re.compile(
        rf"{keyword}\s*(?P<first>{_NUM})(?P<rest>(?:\s*(?:,|и|–|—|-)\s*{_NUM})*)", re.IGNORECASE
    )
    backward = re.compile(rf"(?P<first>\d+(?:\.\d+)?)\s*[-–]\s*{keyword}", re.IGNORECASE)
    found: set[str] = set()
    for paragraph in document.by_role(ParagraphRole.BODY, ParagraphRole.LIST_ITEM):
        text = paragraph.text
        for match in forward.finditer(text):
            numbers = [match.group("first"), *re.findall(_NUM, match.group("rest") or "")]
            normalized = [_norm_number(n) for n in numbers]
            found.update(normalized)
            rest = match.group("rest") or ""
            if (
                re.search(r"[–—-]", rest)
                and len(normalized) == 2
                and all(n.isdigit() for n in normalized)
            ):
                start, end = int(normalized[0]), int(normalized[1])
                found.update(str(i) for i in range(start, end + 1) if end - start < 50)
        for match in backward.finditer(text):
            found.add(_norm_number(match.group("first")))
    return found


def _check_references(ctx: RuleContext, kind: Kind) -> list[Issue]:
    cfg = _cfg(ctx, kind)
    if not cfg.require_reference:
        return []
    refs = referenced_numbers(ctx.document, kind)
    unreferenced = []
    for caption in captions(ctx.document, kind):
        if caption.continuation or caption.number is None:
            continue
        key = _norm_number((caption.appendix_letter or "") + caption.number)
        alt = (
            _norm_number(f"{caption.appendix_letter}.{caption.number}")
            if caption.appendix_letter
            else key
        )
        if key not in refs and alt not in refs:
            unreferenced.append(caption)
    if not unreferenced:
        return []
    title, accusative = _NAMES[kind]
    numbers = ", ".join((c.appendix_letter or "") + (c.number or "") for c in unreferenced[:10])
    return [
        ctx.issue(
            f"{kind}.referenced",
            Category.FIGURES if kind == "figures" else Category.TABLES,
            severity=cfg.severity,
            message=f"{title} {numbers}: нет ссылки в тексте",
            reference=cfg.source,
            paragraphs=[c.paragraph for c in unreferenced],
            fix=f"Добавьте в текст ссылку, например «(см. {accusative} 1)»",
            checker=Checker.STRUCTURE,
        )
    ]


@rule(
    "figures.referenced",
    category=Category.FIGURES,
    checker=Checker.STRUCTURE,
    applies=_applies("figures"),
)
def check_figure_references(ctx: RuleContext) -> Iterable[Issue]:
    """На каждый рисунок есть ссылка в тексте."""
    return _check_references(ctx, "figures")


@rule(
    "tables.referenced",
    category=Category.TABLES,
    checker=Checker.STRUCTURE,
    applies=_applies("tables"),
)
def check_table_references(ctx: RuleContext) -> Iterable[Issue]:
    """На каждую таблицу есть ссылка в тексте."""
    return _check_references(ctx, "tables")
