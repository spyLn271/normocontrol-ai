"""Оценка номеров страниц.

``.docx`` не хранит разбивку на страницы, поэтому есть три источника (от точного к грубому):

1. ``libreoffice`` — документ конвертируется в PDF (LibreOffice headless), текст абзацев
   сопоставляется с текстом страниц;
2. ``word_render`` — метки ``w:lastRenderedPageBreak``, которые Word оставляет при сохранении;
3. ``breaks`` — только явные разрывы страниц и разделов (нижняя оценка).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from normocontrol.logs import get_logger

if TYPE_CHECKING:
    from normocontrol.parser.model import Paragraph

log = get_logger(__name__)

_PROBE_CHARS = 32
_LOOKAHEAD_PAGES = 3
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


class PageEstimator(Protocol):
    name: str

    def estimate(self, data: bytes, paragraphs: list[Paragraph]) -> dict[str, int] | None: ...


def _norm(text: str) -> str:
    return _NON_ALNUM.sub("", text.casefold().replace("ё", "е"))


def match_paragraphs_to_pages(paragraphs: list[Paragraph], page_texts: list[str]) -> dict[str, int]:
    """Последовательно найти начало каждого абзаца в тексте страниц."""
    pages = [_norm(text) for text in page_texts]
    result: dict[str, int] = {}
    page, offset = 0, 0
    for paragraph in paragraphs:
        probe = _norm(paragraph.text)[:_PROBE_CHARS]
        if len(probe) < 3:
            result[paragraph.id] = page + 1
            continue
        found = False
        for candidate in range(page, min(page + _LOOKAHEAD_PAGES, len(pages))):
            start = offset if candidate == page else 0
            position = pages[candidate].find(probe, start)
            if position >= 0:
                page, offset = candidate, position + len(probe)
                found = True
                break
        result[paragraph.id] = page + 1
        if not found:
            log.debug("page_match_miss", paragraph_id=paragraph.id)
    return result


class LibreOfficePageEstimator:
    name = "libreoffice"

    def __init__(self, soffice: str = "soffice", timeout_s: float = 90) -> None:
        self._soffice = soffice
        self._timeout = timeout_s

    def available(self) -> bool:
        if shutil.which(self._soffice) is None:
            return False
        try:
            import pypdfium2  # noqa: F401, PLC0415 — необязательная зависимость (extra «pdf»)
        except ImportError:
            return False
        return True

    def estimate(self, data: bytes, paragraphs: list[Paragraph]) -> dict[str, int] | None:
        executable = shutil.which(self._soffice)
        if executable is None:
            return None
        with tempfile.TemporaryDirectory(prefix="nc-pages-") as tmp:
            workdir = Path(tmp)
            source = workdir / "document.docx"
            source.write_bytes(data)
            command = [
                executable,
                "--headless",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation=file://{workdir / 'profile'}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(workdir),
                str(source),
            ]
            try:
                subprocess.run(  # noqa: S603 — аргументы формируем сами, без shell
                    command,
                    check=True,
                    capture_output=True,
                    timeout=self._timeout,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                log.warning("libreoffice_conversion_failed", error=str(exc))
                return None
            pdf_path = workdir / "document.pdf"
            if not pdf_path.is_file():
                return None
            page_texts = extract_pdf_page_texts(pdf_path)
        if not page_texts:
            return None
        return match_paragraphs_to_pages(paragraphs, page_texts)


def extract_pdf_page_texts(path: Path) -> list[str]:
    import pypdfium2 as pdfium  # noqa: PLC0415 — необязательная зависимость

    document = pdfium.PdfDocument(str(path))
    try:
        texts: list[str] = []
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return texts
    finally:
        document.close()


def estimate_from_breaks(
    paragraphs: list[Paragraph],
    rendered: dict[str, tuple[int, bool]],
) -> tuple[dict[str, int], str | None]:
    """Номера страниц по меткам Word, а если их нет — по явным разрывам."""
    if any(count for count, _ in rendered.values()):
        pages: dict[str, int] = {}
        page = 1
        for paragraph in paragraphs:
            count, at_start = rendered.get(paragraph.id, (0, False))
            if at_start:
                page += 1
                count -= 1
            pages[paragraph.id] = page
            page += max(count, 0)
        return pages, "word_render"

    pages = {}
    page = 1
    for paragraph in paragraphs:
        if paragraph.page_break_before and paragraph.index > 0:
            page += 1
        pages[paragraph.id] = page
        if paragraph.contains_page_break or paragraph.ends_section:
            page += 1
    if page == 1:
        # разрывов нет: документ на одной странице или свёрстан сплошным текстом — не гадаем
        return {}, None
    return pages, "breaks"
