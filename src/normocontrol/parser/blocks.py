"""Обход тела документа в порядке чтения.

Один и тот же обход используют парсер (нумерация абзацев ``p-N``), генератор тестовых
документов и экспорт ``.docx`` с комментариями — поэтому идентификаторы абзацев совпадают
во всех трёх местах.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from normocontrol.parser.xml import (
    W_P,
    W_SDT,
    W_SDT_CONTENT,
    W_TBL,
    Element,
    attr,
    local_name,
)

_CONTAINERS = frozenset({"tr", "tc", "customXml", "sdtContent"})
_TOC_GALLERIES = frozenset({"Table of Contents"})


@dataclass(frozen=True, slots=True)
class ParagraphBlock:
    element: Element
    top_level: bool  # прямой потомок w:body (только такие абзацы несут разрывы разделов)
    table_index: int | None
    in_toc_sdt: bool


@dataclass(frozen=True, slots=True)
class TableStart:
    element: Element
    table_index: int


@dataclass(frozen=True, slots=True)
class TableEnd:
    table_index: int


type Block = ParagraphBlock | TableStart | TableEnd


def iter_blocks(body: Element) -> Iterator[Block]:
    walker = _Walker()
    yield from walker.walk(body, top_level=True, table_index=None, in_toc=False)


def iter_paragraph_blocks(body: Element) -> Iterator[ParagraphBlock]:
    for block in iter_blocks(body):
        if isinstance(block, ParagraphBlock):
            yield block


def paragraph_id(index: int) -> str:
    return f"p-{index}"


class _Walker:
    def __init__(self) -> None:
        self._tables = 0

    def walk(
        self,
        parent: Element,
        *,
        top_level: bool,
        table_index: int | None,
        in_toc: bool,
    ) -> Iterator[Block]:
        for element in parent:
            tag = element.tag
            if tag == W_P:
                yield ParagraphBlock(element, top_level, table_index, in_toc)
            elif tag == W_TBL:
                if table_index is None:
                    index = self._tables
                    self._tables += 1
                    yield TableStart(element, index)
                    yield from self.walk(element, top_level=False, table_index=index, in_toc=in_toc)
                    yield TableEnd(index)
                else:  # вложенная таблица считается частью внешней
                    yield from self.walk(
                        element, top_level=False, table_index=table_index, in_toc=in_toc
                    )
            elif tag == W_SDT:
                content = element.find(W_SDT_CONTENT)
                if content is not None:
                    yield from self.walk(
                        content,
                        top_level=False,
                        table_index=table_index,
                        in_toc=in_toc or _is_toc_sdt(element),
                    )
            elif local_name(element) in _CONTAINERS:
                yield from self.walk(
                    element, top_level=False, table_index=table_index, in_toc=in_toc
                )


def _is_toc_sdt(sdt: Element) -> bool:
    for gallery in sdt.iter("{*}docPartGallery"):
        if attr(gallery, "w:val") in _TOC_GALLERIES:
            return True
    return False
