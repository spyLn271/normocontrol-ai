"""Индексация стандартов: файл → текст → чанки по пунктам → эмбеддинги → векторная БД.

Повторный запуск не создаёт дублей: перед загрузкой точки источника удаляются,
а идентификаторы точек детерминированы.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from normocontrol.logs import get_logger
from normocontrol.rag.chunking import chunk_document
from normocontrol.rag.embeddings import Embedder
from normocontrol.rag.extract import ExtractionError, extract_text
from normocontrol.rag.store import VectorStore

log = get_logger(__name__)


class SourceRecord(BaseModel):
    """Запись реестра ``research/sources.yaml`` (поля из docs/RESEARCH.md)."""

    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    type: str = "standard"
    jurisdiction: str = "KZ"
    status: str = "active"
    edition_date: str | None = None
    official_url: str | None = None
    access: str | None = None
    local_file: str | None = None
    rag_source: str | None = None  # имя источника для profile.rag_sources
    applies_to: list[str] = Field(default_factory=list)
    used_in_kz: bool | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class IndexResult:
    source: str
    chunks: int
    error: str | None = None


async def index_text(
    text: str,
    *,
    source: str,
    source_id: str,
    embedder: Embedder,
    store: VectorStore,
    max_tokens: int = 800,
    overlap_tokens: int = 80,
    metadata: dict[str, str | list[str]] | None = None,
) -> IndexResult:
    chunks = chunk_document(
        text,
        source=source,
        source_id=source_id,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        metadata=metadata,
    )
    vectors = await embedder.embed_documents([chunk.text for chunk in chunks])
    await store.delete_source(source_id)
    await store.upsert(chunks, vectors)
    log.info("source_indexed", source=source, chunks=len(chunks))
    return IndexResult(source=source, chunks=len(chunks))


async def index_file(
    path: Path,
    *,
    source: str,
    source_id: str,
    embedder: Embedder,
    store: VectorStore,
    max_tokens: int = 800,
    overlap_tokens: int = 80,
    metadata: dict[str, str | list[str]] | None = None,
) -> IndexResult:
    return await index_text(
        extract_text(path),
        source=source,
        source_id=source_id,
        embedder=embedder,
        store=store,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        metadata=metadata,
    )


def load_registry(path: Path) -> list[SourceRecord]:
    data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise TypeError(f"{path}: реестр источников должен быть списком")
    return [SourceRecord.model_validate(item) for item in data]


async def index_registry(
    registry: Path,
    *,
    base_dir: Path,
    embedder: Embedder,
    store: VectorStore,
    max_tokens: int = 800,
    overlap_tokens: int = 80,
) -> list[IndexResult]:
    results: list[IndexResult] = []
    for record in load_registry(registry):
        if not record.local_file or not record.rag_source:
            continue
        path = (base_dir / record.local_file).resolve()
        if not path.is_file():
            log.warning("source_file_missing", source=record.id, path=str(path))
            continue
        try:
            result = await index_file(
                path,
                source=record.rag_source,
                source_id=record.id,
                embedder=embedder,
                store=store,
                max_tokens=max_tokens,
                overlap_tokens=overlap_tokens,
                metadata={"jurisdiction": record.jurisdiction, "doc_type": record.applies_to},
            )
        except ExtractionError as exc:
            # один нечитаемый файл не должен останавливать загрузку остальных
            log.warning("source_index_failed", source=record.id, error=str(exc))
            result = IndexResult(source=record.rag_source, chunks=0, error=str(exc))
        results.append(result)
    return results
