"""Извлечение текста стандартов и методичек (PDF, DOCX, TXT/MD) для индексации."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import docx

_PAGE_NUMBER_LINE = re.compile(r"^\s*\d{1,4}\s*$")
_WHITESPACE = re.compile(r"[ \t ]+")


class ExtractionError(ValueError):
    pass


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from normocontrol.parser.pages import extract_pdf_page_texts  # noqa: PLC0415

        try:
            pages = extract_pdf_page_texts(path)
        except ImportError as exc:
            raise ExtractionError("Для PDF установите extra «pdf»: uv sync --extra pdf") from exc
        except Exception as exc:  # pypdfium2.PdfiumError и ошибки доступа к файлу
            raise ExtractionError(f"Не удалось прочитать PDF {path.name}: {exc}") from exc
        return "\n".join(strip_repeated_lines(pages))
    try:
        if suffix == ".docx":
            document = docx.Document(str(path))
            return "\n".join(p.text for p in document.paragraphs)
        if suffix in {".txt", ".md"}:
            return path.read_text(encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        raise ExtractionError(f"Не удалось прочитать {path.name}: {exc}") from exc
    raise ExtractionError(f"Неподдерживаемый формат: {path.suffix}")


def strip_repeated_lines(pages: list[str], threshold: float = 0.5) -> list[str]:
    """Убрать колонтитулы: строки, повторяющиеся на большинстве страниц, и номера страниц."""
    cleaned_pages = [[_clean(line) for line in page.splitlines()] for page in pages]
    if len(pages) >= 3:
        counts = Counter(line for page in cleaned_pages for line in set(page) if line)
        limit = max(2, int(len(pages) * threshold))
        repeated = {line for line, count in counts.items() if count >= limit}
    else:
        repeated = set()
    result = []
    for page in cleaned_pages:
        lines = [
            line
            for line in page
            if line and line not in repeated and not _PAGE_NUMBER_LINE.match(line)
        ]
        result.append("\n".join(lines))
    return result


def _clean(line: str) -> str:
    # pypdfium2 отдаёт U+FFFE на месте мягкого переноса: «нормативно￾справочной»
    line = line.replace("￾", "").replace("­", "").replace("\r", "")
    return _WHITESPACE.sub(" ", line).strip()
