"""Агрегатор: дедупликация, сортировка, балл соответствия, сводка."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime

from normocontrol import __version__
from normocontrol.parser.model import Document
from normocontrol.profiles.schema import Profile, Severity
from normocontrol.report.model import (
    CheckRun,
    DocumentInfo,
    EngineInfo,
    Issue,
    Notice,
    ProfileInfo,
    Report,
    Summary,
)

# Штраф за ошибку; сгруппированная ошибка («в 40 абзацах») весит больше одиночной,
# но логарифмически — чтобы одна системная ошибка не обнуляла балл.
SEVERITY_WEIGHTS: dict[Severity, float] = {
    Severity.ERROR: 8.0,
    Severity.WARNING: 3.0,
    Severity.INFO: 0.0,
}


def dedupe(issues: Iterable[Issue]) -> list[Issue]:
    """Убрать дубли (первым остаётся результат детерминированной проверки)."""
    seen: set[tuple[object, ...]] = set()
    result: list[Issue] = []
    for issue in issues:
        key = issue.fingerprint
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def sort_issues(issues: Sequence[Issue], document: Document) -> list[Issue]:
    order = {p.id: p.index for p in document.paragraphs}

    def key(issue: Issue) -> tuple[int, int, str]:
        first = issue.location.paragraph_id
        position = order.get(first, -1) if first else -1
        return (issue.severity.rank, position, issue.rule_id)

    return sorted(issues, key=key)


def compute_score(issues: Iterable[Issue]) -> int:
    """Балл 0–100: ``100 − Σ вес × (1 + ½·log₂(число мест))``."""
    penalty = sum(
        SEVERITY_WEIGHTS[issue.severity] * (1 + 0.5 * math.log2(issue.count)) for issue in issues
    )
    return max(0, min(100, round(100 - penalty)))


def summarize(issues: Sequence[Issue]) -> Summary:
    by_severity = Counter(issue.severity for issue in issues)
    by_category = Counter(issue.category for issue in issues)
    return Summary(
        total=len(issues),
        by_severity={severity: by_severity.get(severity, 0) for severity in Severity},
        by_category=dict(sorted(by_category.items(), key=lambda item: -item[1])),
    )


def build_report(
    *,
    document: Document,
    profile: Profile,
    issues: Iterable[Issue],
    checks: Sequence[CheckRun],
    notices: Sequence[Notice],
    created_at: datetime,
    duration_ms: int,
    llm_model: str | None = None,
    embedding_model: str | None = None,
) -> Report:
    unique = sort_issues(dedupe(issues), document)
    return Report(
        created_at=created_at,
        duration_ms=duration_ms,
        document=DocumentInfo(
            filename=document.filename,
            paragraphs=document.stats.paragraphs,
            words=document.stats.words,
            tables=document.stats.tables,
            images=document.stats.images,
            sections=len(document.sections),
            pages_estimated=document.stats.pages_estimated,
            page_source=document.stats.page_source,
        ),
        profile=ProfileInfo(
            id=profile.id,
            title=profile.title,
            status=profile.status.value,
            version=profile.version,
        ),
        engine=EngineInfo(
            version=__version__, llm_model=llm_model, embedding_model=embedding_model
        ),
        score=compute_score(unique),
        summary=summarize(unique),
        issues=unique,
        notices=list(notices),
        checks=list(checks),
    )
