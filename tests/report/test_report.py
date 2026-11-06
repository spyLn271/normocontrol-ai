from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

from rich.console import Console

from normocontrol.dataset.generate import generate_sample
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.profiles.schema import Profile, Severity
from normocontrol.report.aggregate import build_report, compute_score, dedupe, summarize
from normocontrol.report.model import Category, Issue, Location
from normocontrol.report.render_console import render_console
from normocontrol.report.render_docx import annotate_docx
from normocontrol.rules.base import fmt_num, format_page_ranges, plural
from normocontrol.rules.engine import run_rules


def issue(rule_id: str, severity: Severity, count: int = 1, ids: tuple[str, ...] = ()) -> Issue:
    return Issue(
        rule_id=rule_id,
        category=Category.PAGE,
        severity=severity,
        message=rule_id,
        location=Location(paragraph_ids=list(ids)),
        count=count,
    )


def test_score_weights() -> None:
    assert compute_score([]) == 100
    assert compute_score([issue("a", Severity.INFO)]) == 100
    assert compute_score([issue("a", Severity.ERROR)]) == 92
    assert compute_score([issue("a", Severity.WARNING)]) == 97
    assert compute_score([issue("a", Severity.ERROR, count=16)]) == 76  # 8 × (1 + ½·4)
    assert compute_score([issue(str(i), Severity.ERROR) for i in range(20)]) == 0


def test_dedupe_keeps_first() -> None:
    first = issue("a", Severity.ERROR, ids=("p-1",))
    assert dedupe(
        [first, issue("a", Severity.ERROR, ids=("p-1",)), issue("b", Severity.ERROR)]
    ) == [
        first,
        issue("b", Severity.ERROR),
    ]


def test_summary_counts() -> None:
    summary = summarize(
        [issue("a", Severity.ERROR), issue("b", Severity.WARNING), issue("c", Severity.ERROR)]
    )
    assert summary.total == 3
    assert summary.by_severity == {Severity.ERROR: 2, Severity.WARNING: 1, Severity.INFO: 0}
    assert summary.by_category == {Category.PAGE: 3}


def test_formatting_helpers() -> None:
    assert format_page_ranges([5, 1, 2, 3, 7, 8]) == "1–3, 5, 7–8"
    assert format_page_ranges([]) == ""
    assert fmt_num(1.5) == "1,5"
    assert fmt_num(3.0) == "3"
    assert fmt_num(1.25) == "1,25"
    assert [plural(n, "запись", "записи", "записей") for n in (1, 2, 5, 11, 21, 22, 112)] == [
        "запись",
        "записи",
        "записей",
        "записей",
        "запись",
        "записи",
        "записей",
    ]


def _report(profile: Profile, mutations: int = 4) -> tuple[bytes, object]:
    data, _ = generate_sample(profile, seed=3, mutations=mutations)
    document = parse_docx(data, "work.docx")
    result = run_rules(document, profile)
    report = build_report(
        document=document,
        profile=profile,
        issues=result.issues,
        checks=result.checks,
        notices=[],
        created_at=datetime.now(UTC),
        duration_ms=1,
    )
    return data, report


def test_report_sorted_by_severity(kru: Profile) -> None:
    _, report = _report(kru, mutations=5)
    ranks = [i.severity.rank for i in report.issues]  # type: ignore[attr-defined]
    assert ranks == sorted(ranks)


def test_annotated_docx_has_comments(kru: Profile) -> None:
    data, report = _report(kru)
    annotated = annotate_docx(data, report)  # type: ignore[arg-type]
    with zipfile.ZipFile(io.BytesIO(annotated)) as archive:
        comments = archive.read("word/comments.xml").decode()
    assert comments.count("<w:comment ") >= len(report.issues)  # type: ignore[attr-defined]
    assert "Normocontrol AI" in comments
    # документ по-прежнему открывается и читается
    assert parse_docx(annotated).stats.paragraphs == parse_docx(data).stats.paragraphs


def test_console_render(kru: Profile) -> None:
    _, report = _report(kru)
    console = Console(record=True, width=120)
    render_console(report, console)  # type: ignore[arg-type]
    text = console.export_text()
    assert "Балл соответствия" in text
    assert "Основание" in text
