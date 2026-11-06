"""Каркас Rule Engine: декоратор ``@rule``, реестр, контекст и группировка ошибок.

Новое правило — это функция в любом модуле пакета ``normocontrol.rules``::

    @rule("page.margins", category=Category.PAGE, applies=lambda p: p.page is not None)
    def check_margins(ctx: RuleContext) -> Iterable[Issue]: ...

Движок менять не нужно: модуль регистрируется при импорте пакета.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from normocontrol.parser.model import Document, Paragraph
from normocontrol.profiles.schema import Profile, Severity
from normocontrol.report.model import Category, Checker, Issue, Location

type RuleFunc = Callable[[RuleContext], Iterable[Issue]]
type AppliesFunc = Callable[[Profile], bool]
type Noun = tuple[str, str, str]  # предложный падеж: 1 / 2–4 / 5+

PARAGRAPH_NOUN: Noun = ("абзаце", "абзацах", "абзацах")
HEADING_NOUN: Noun = ("заголовке", "заголовках", "заголовках")
CAPTION_NOUN: Noun = ("подписи", "подписях", "подписях")


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_id: str
    category: Category
    checker: Checker
    applies: AppliesFunc
    func: RuleFunc
    description: str


_REGISTRY: dict[str, RuleSpec] = {}


def rule(
    rule_id: str,
    *,
    category: Category,
    applies: AppliesFunc,
    checker: Checker = Checker.RULE,
    description: str = "",
) -> Callable[[RuleFunc], RuleFunc]:
    def decorator(func: RuleFunc) -> RuleFunc:
        if rule_id in _REGISTRY and _REGISTRY[rule_id].func is not func:
            raise ValueError(f"Правило {rule_id} зарегистрировано дважды")
        doc = (func.__doc__ or "").strip()
        _REGISTRY[rule_id] = RuleSpec(
            rule_id=rule_id,
            category=category,
            checker=checker,
            applies=applies,
            func=func,
            description=description or (doc.splitlines()[0] if doc else ""),
        )
        return func

    return decorator


def registered_rules() -> list[RuleSpec]:
    return list(_REGISTRY.values())


@dataclass(frozen=True, slots=True)
class RuleContext:
    document: Document
    profile: Profile

    def issue(
        self,
        rule_id: str,
        category: Category,
        *,
        severity: Severity,
        message: str,
        reference: str | None = None,
        paragraphs: Sequence[Paragraph] = (),
        section_index: int | None = None,
        expected: str | None = None,
        actual: str | None = None,
        fix: str | None = None,
        quote: str | None = None,
        checker: Checker = Checker.RULE,
    ) -> Issue:
        return Issue(
            rule_id=rule_id,
            category=category,
            severity=severity,
            checker=checker,
            message=message,
            expected=expected,
            actual=actual,
            fix=fix,
            reference=reference,
            location=Location(
                paragraph_ids=[p.id for p in paragraphs],
                pages=pages_of(paragraphs),
                section_index=section_index,
                quote=quote if quote is not None else _quote(paragraphs),
            ),
            count=max(len(paragraphs), 1),
        )

    def grouped(
        self,
        rule_id: str,
        category: Category,
        *,
        severity: Severity,
        reference: str | None,
        findings: Iterable[tuple[Paragraph, str]],
        message: Callable[[str, int, str], str],
        expected: str | None = None,
        fix: str | None = None,
        checker: Checker = Checker.RULE,
        noun: Noun = PARAGRAPH_NOUN,
    ) -> list[Issue]:
        """Сгруппировать однотипные нарушения по фактическому значению.

        Вместо 300 одинаковых ошибок — одна: «шрифт 12 pt в 47 абзацах на стр. 5–19».
        ``message(actual, count, where)`` формирует текст для группы.
        """
        groups: dict[str, list[Paragraph]] = defaultdict(list)
        for paragraph, actual in findings:
            groups[actual].append(paragraph)
        issues: list[Issue] = []
        for actual, paragraphs in groups.items():
            issues.append(
                self.issue(
                    rule_id,
                    category,
                    severity=severity,
                    message=message(actual, len(paragraphs), describe_where(paragraphs, noun)),
                    reference=reference,
                    paragraphs=paragraphs,
                    expected=expected,
                    actual=actual,
                    fix=fix,
                    checker=checker,
                )
            )
        return issues


def pages_of(paragraphs: Sequence[Paragraph]) -> list[int]:
    return sorted({p.page_estimate for p in paragraphs if p.page_estimate is not None})


def format_page_ranges(pages: Sequence[int]) -> str:
    """``[1, 2, 3, 5, 7, 8]`` → ``"1–3, 5, 7–8"``."""
    if not pages:
        return ""
    ordered = sorted(set(pages))
    ranges: list[str] = []
    start = prev = ordered[0]
    for page in [*ordered[1:], None]:
        if page is not None and page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}–{prev}" if prev != start else str(start))
        if page is not None:
            start = prev = page
    return ", ".join(ranges)


def describe_where(paragraphs: Sequence[Paragraph], noun: Noun = PARAGRAPH_NOUN) -> str:
    count = len(paragraphs)
    pages = format_page_ranges(pages_of(paragraphs))
    where = f"в {count} {plural(count, *noun)}"
    if pages:
        where += f" (стр. {pages})"
    return where


def plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def fmt_num(value: float, digits: int = 2) -> str:
    """Число в русской записи без лишних нулей: 1.50 → «1,5»."""
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if text else "0"


def _quote(paragraphs: Sequence[Paragraph], limit: int = 120) -> str | None:
    for paragraph in paragraphs:
        text = paragraph.text.strip()
        if text:
            return text if len(text) <= limit else text[: limit - 1] + "…"
    return None
