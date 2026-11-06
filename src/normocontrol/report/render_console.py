"""Читаемый отчёт в терминале (rich)."""

from __future__ import annotations

from itertools import groupby

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from normocontrol.profiles.schema import Severity
from normocontrol.report.model import CATEGORY_TITLES, Issue, NoticeLevel, Report
from normocontrol.rules.base import format_page_ranges

_SEVERITY_STYLE = {
    Severity.ERROR: ("bold red", "Ошибка"),
    Severity.WARNING: ("bold dark_orange", "Желательно"),
    Severity.INFO: ("blue", "Совет"),
}


def _score_style(score: int) -> str:
    if score >= 85:
        return "bold green"
    if score >= 60:
        return "bold dark_orange"
    return "bold red"


def _where(issue: Issue) -> str:
    parts = []
    if issue.location.pages:
        parts.append(f"стр. {format_page_ranges(issue.location.pages)}")
    if issue.location.paragraph_id:
        suffix = f" +{issue.count - 1}" if issue.count > 1 else ""
        parts.append(f"{issue.location.paragraph_id}{suffix}")
    elif issue.location.section_index is not None:
        parts.append(f"раздел {issue.location.section_index + 1}")
    return ", ".join(parts) or "документ"


def render_console(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    counts = report.summary.by_severity
    header = Text.assemble(
        ("Балл соответствия: ", "bold"),
        (f"{report.score}/100", _score_style(report.score)),
        "   ",
        (f"ошибок {counts.get(Severity.ERROR, 0)}", _SEVERITY_STYLE[Severity.ERROR][0]),
        " · ",
        (f"желательно исправить {counts.get(Severity.WARNING, 0)}", "dark_orange"),
        " · ",
        (f"советов {counts.get(Severity.INFO, 0)}", "blue"),
    )
    meta = Text(
        f"{report.document.filename or 'документ'} · профиль «{report.profile.title}» "
        f"· {report.duration_ms} мс",
        style="dim",
    )
    console.print(Panel(Group(header, meta), title="Normocontrol AI", expand=False))

    for notice in report.notices:
        style = "yellow" if notice.level is NoticeLevel.WARNING else "dim"
        console.print(f"[{style}]• {notice.message}[/{style}]")

    if not report.issues:
        console.print("[bold green]Нарушений не найдено.[/bold green]")
        return

    ordered = sorted(report.issues, key=lambda i: (i.category.value, i.severity.rank))
    for category, group in groupby(ordered, key=lambda i: i.category):
        table = Table(
            title=CATEGORY_TITLES.get(category, category.value),
            title_justify="left",
            show_lines=True,
            expand=True,
        )
        table.add_column("", width=11, no_wrap=True)
        table.add_column("Что не так")
        table.add_column("Где", width=16)
        table.add_column("Как исправить")
        for issue in group:
            style, label = _SEVERITY_STYLE[issue.severity]
            message = Text(issue.message)
            if issue.reference:
                message.append(f"\nОснование: {issue.reference}", style="dim")
            table.add_row(Text(label, style=style), message, _where(issue), issue.fix or "")
        console.print(table)
