from __future__ import annotations

from normocontrol.parser.model import Paragraph
from normocontrol.parser.pages import LibreOfficePageEstimator, match_paragraphs_to_pages


def paragraph(index: int, text: str) -> Paragraph:
    return Paragraph(id=f"p-{index}", index=index, section_index=0, text=text)


def test_paragraphs_matched_to_pdf_pages() -> None:
    paragraphs = [
        paragraph(0, "Министерство науки"),
        paragraph(1, "СОДЕРЖАНИЕ"),
        paragraph(2, "Введение в предмет исследования, длинный абзац с пере-носом"),
        paragraph(3, ""),
        paragraph(4, "Заключение"),
    ]
    pages = [
        "Министерство науки\n",
        "СОДЕРЖАНИЕ\nВведение в предмет\nисследования, длинный абзац с пере-\nносом\n2",
        "Заключение\n3",
    ]
    result = match_paragraphs_to_pages(paragraphs, pages)
    assert result == {"p-0": 1, "p-1": 2, "p-2": 2, "p-3": 2, "p-4": 3}


def test_unmatched_paragraph_keeps_current_page() -> None:
    result = match_paragraphs_to_pages(
        [paragraph(0, "Первая страница"), paragraph(1, "Текст, которого нет в PDF")],
        ["Первая страница"],
    )
    assert result == {"p-0": 1, "p-1": 1}


def test_estimator_unavailable_without_soffice() -> None:
    estimator = LibreOfficePageEstimator(soffice="definitely-not-installed-soffice")
    assert not estimator.available()
    assert estimator.estimate(b"PK", []) is None
