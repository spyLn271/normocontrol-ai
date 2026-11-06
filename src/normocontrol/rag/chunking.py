"""Чанкинг по пунктам стандарта: один чанк = один пункт (6.1.1 или «31.») с родительским заголовком.

Номер пункта принимается, только если он «следует» за предыдущим (1 → 2, 6.1 → 6.1.1,
6.1.3 → 6.2, …). Так нумерованные строки списков, таблиц и оглавления не рвут пункт на части.
Приложения («Приложение И») — отдельные чанки с ``kind="appendix"``: в них образцы оформления.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CLAUSE_RE = re.compile(r"^(?P<num>\d{1,3}(?:\.\d{1,3}){0,4})\.?\s+(?P<rest>\S.*)$")
_PARENT_RE = re.compile(r"^(Глава|Параграф|Раздел|Бөлім|Тарау)\s+\d+", re.IGNORECASE)
_APPENDIX_RE = re.compile(
    r"^(Приложение|Қосымша)\s+([А-ЯA-Z0-9]{1,3})(\s+к\s+.*|\s*)$", re.IGNORECASE
)
_TOC_LINE_RE = re.compile(r"(\.{4,}|…{2,}|_{4,}).{0,8}\d{1,4}\s*$")
_EXAMPLE_RE = re.compile(r"^(Пример|Примеры|Мысал)", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")
CHARS_PER_TOKEN = 3.2  # грубая оценка для кириллицы


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    text: str
    source: str
    source_id: str
    clause: str
    kind: str = "rule"
    part: int = 0
    metadata: dict[str, str | list[str]] = field(default_factory=dict)

    def payload(self) -> dict[str, object]:
        return {
            "text": self.text,
            "source": self.source,
            "source_id": self.source_id,
            "clause": self.clause,
            "kind": self.kind,
            "part": self.part,
            **self.metadata,
        }


@dataclass(slots=True)
class _Section:
    clause: str
    kind: str
    lines: list[str]
    parent: str | None


def _successor(
    previous: tuple[int, ...] | None, candidate: tuple[int, ...], *, restart: bool = False
) -> bool:
    if restart and (
        candidate in {(1,), (1, 1)}
        or (len(candidate) == 1 and (previous is None or candidate[0] > previous[0]))
    ):
        # после «Глава N» нумерация начинается заново или продолжается с пропуском
        return True
    if previous is None:
        return candidate in {(1,), (1, 1)}
    if candidate == (*previous, 1):  # первый подпункт
        return True
    for depth in range(len(previous)):
        sibling = (*previous[:depth], previous[depth] + 1)
        if candidate == sibling:
            return True
        # пропуск одного номера допускаем (опечатки, отменённые пункты)
        if candidate == (*previous[:depth], previous[depth] + 2):
            return True
    return False


def split_sections(text: str) -> list[_Section]:
    sections: list[_Section] = []
    current = _Section(clause="intro", kind="intro", lines=[], parent=None)
    previous: tuple[int, ...] | None = None
    parent: str | None = None
    restart = False  # после «Глава 1» нумерация может начаться заново (после предисловия)
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _TOC_LINE_RE.search(line):
            continue
        if _PARENT_RE.match(line):
            parent = line
            restart = True
            continue
        appendix = _APPENDIX_RE.match(line)
        if appendix:
            sections.append(current)
            clause = f"Приложение {appendix.group(2).upper()}"
            current = _Section(clause=clause, kind="appendix", lines=[line], parent=None)
            previous = None
            parent = None
            continue
        match = _CLAUSE_RE.match(line)
        if match and current.kind != "appendix":
            number = tuple(int(part) for part in match.group("num").split("."))
            if _successor(previous, number, restart=restart):
                sections.append(current)
                previous = number
                restart = False
                current = _Section(
                    clause=match.group("num"), kind="rule", lines=[line], parent=parent
                )
                continue
        current.lines.append(line)
    sections.append(current)
    return [s for s in sections if s.lines]


def _split_long(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = _SENTENCE_END.split(text)
    parts: list[str] = []
    buffer = ""
    for sentence in sentences:
        if buffer and len(buffer) + len(sentence) + 1 > max_chars:
            parts.append(buffer)
            tail = buffer[-overlap_chars:] if overlap_chars else ""
            tail = tail[tail.find(" ") + 1 :] if " " in tail else ""  # перекрытие — по словам
            buffer = f"{tail} {sentence}".strip()
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        parts.append(buffer)
    return parts


def chunk_document(
    text: str,
    *,
    source: str,
    source_id: str,
    max_tokens: int = 800,
    overlap_tokens: int = 80,
    metadata: dict[str, str | list[str]] | None = None,
) -> list[Chunk]:
    max_chars = int(max_tokens * CHARS_PER_TOKEN)
    overlap_chars = int(overlap_tokens * CHARS_PER_TOKEN)
    titles: dict[str, str] = {}
    chunks: list[Chunk] = []
    for sequence, section in enumerate(split_sections(text)):
        body = " ".join(section.lines)
        if section.kind == "rule":
            titles[section.clause] = section.lines[0][:160]
        parent_clause = section.clause.rsplit(".", 1)[0] if "." in section.clause else None
        context = [p for p in (section.parent, titles.get(parent_clause or "")) if p]
        kind = "example" if _EXAMPLE_RE.match(section.lines[0]) else section.kind
        for part, piece in enumerate(_split_long(body, max_chars, overlap_chars)):
            chunk_text = "\n".join([*context, piece]) if context else piece
            chunks.append(
                Chunk(
                    id=f"{source_id}#{sequence}#{section.clause}#{part}",
                    text=chunk_text,
                    source=source,
                    source_id=source_id,
                    clause=section.clause,
                    kind=kind,
                    part=part,
                    metadata=dict(metadata or {}),
                )
            )
    return chunks
