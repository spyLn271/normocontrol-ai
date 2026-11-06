"""Исходный ``.docx`` с комментариями Word на месте каждой ошибки."""

from __future__ import annotations

import io
from typing import Any

import docx
from docx.text.paragraph import Paragraph as DocxParagraph

from normocontrol.parser.blocks import iter_paragraph_blocks, paragraph_id
from normocontrol.profiles.schema import Severity
from normocontrol.report.model import Issue, Report

COMMENT_AUTHOR = "Normocontrol AI"
COMMENT_INITIALS = "NC"
MAX_COMMENTS_PER_ISSUE = 10
_SEVERITY_LABEL = {
    Severity.ERROR: "Ошибка",
    Severity.WARNING: "Желательно исправить",
    Severity.INFO: "Совет",
}


def _comment_text(issue: Issue, remaining: int) -> str:
    lines = [f"[{_SEVERITY_LABEL[issue.severity]}] {issue.message}"]
    if issue.fix:
        lines.append(f"Как исправить: {issue.fix}")
    if issue.reference:
        lines.append(f"Основание: {issue.reference}")
    if remaining > 0:
        lines.append(f"Ещё мест с этой ошибкой: {remaining}")
    return "\n".join(lines)


def annotate_docx(
    data: bytes,
    report: Report,
    *,
    author: str = COMMENT_AUTHOR,
    max_comments_per_issue: int = MAX_COMMENTS_PER_ISSUE,
) -> bytes:
    document: Any = docx.Document(io.BytesIO(data))
    part = document.part
    paragraphs = {
        paragraph_id(index): DocxParagraph(block.element, part)  # type: ignore[arg-type]
        for index, block in enumerate(iter_paragraph_blocks(document.element.body))
    }
    fallback = next((pid for pid, p in paragraphs.items() if p.text.strip()), None)

    for issue in report.issues:
        targets = issue.location.paragraph_ids[:max_comments_per_issue]
        if not targets and fallback is not None:
            targets = [fallback]  # ошибка уровня документа (поля, нумерация, разделы)
        remaining = max(issue.count - len(targets), 0)
        for position, pid in enumerate(targets):
            paragraph = paragraphs.get(pid)
            if paragraph is None:
                continue
            runs = [run for run in paragraph.runs if run.text]
            if not runs:
                runs = [paragraph.add_run("")]
            text = _comment_text(issue, remaining if position == 0 else 0)
            document.add_comment(runs, text=text, author=author, initials=COMMENT_INITIALS)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
