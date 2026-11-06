"""Векторное хранилище за маленьким интерфейсом ``VectorStore``.

Реализация — Qdrant: встроенный режим (файлы в ``data/vectors``) для разработки
и сервер (``vector_store.url``) для продакшена. Смена БД = новая реализация протокола.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient, models

from normocontrol.config.settings import VectorStoreSettings
from normocontrol.rag.chunking import Chunk

_ID_NAMESPACE = uuid.UUID("6f1c2f1e-3a51-4c49-9d0a-2b7c5e1d9a10")


@dataclass(frozen=True, slots=True)
class SearchHit:
    id: str
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    async def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None: ...

    async def delete_source(self, source_id: str) -> None: ...

    async def search(
        self, vector: Sequence[float], *, limit: int, sources: Sequence[str] | None = None
    ) -> list[SearchHit]: ...

    async def count(self) -> int: ...

    async def sources(self) -> dict[str, int]: ...

    async def aclose(self) -> None: ...


def point_id(chunk_id: str) -> str:
    """Детерминированный UUID: повторная индексация обновляет точки, а не плодит дубли."""
    return str(uuid.uuid5(_ID_NAMESPACE, chunk_id))


class QdrantStore:
    def __init__(self, client: AsyncQdrantClient, collection: str, *, local: bool = False) -> None:
        self._client = client
        self._collection = collection
        self._local = local  # встроенный режим: индексы payload не поддерживаются

    @classmethod
    def from_settings(cls, settings: VectorStoreSettings) -> QdrantStore:
        if settings.url:
            api_key = settings.api_key.get_secret_value() if settings.api_key else None
            return cls(AsyncQdrantClient(url=settings.url, api_key=api_key), settings.collection)
        settings.path.mkdir(parents=True, exist_ok=True)
        return cls(AsyncQdrantClient(path=str(settings.path)), settings.collection, local=True)

    @classmethod
    def in_memory(cls, collection: str = "standards") -> QdrantStore:
        return cls(AsyncQdrantClient(location=":memory:"), collection, local=True)

    async def aclose(self) -> None:
        await self._client.close()

    async def _ensure(self, dimension: int) -> None:
        if await self._client.collection_exists(self._collection):
            return
        await self._client.create_collection(
            self._collection,
            vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
        )
        if self._local:
            return
        for field in ("source", "source_id", "kind"):
            await self._client.create_payload_index(
                self._collection, field, field_schema=models.PayloadSchemaType.KEYWORD
            )

    async def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if not chunks:
            return
        await self._ensure(len(vectors[0]))
        points = [
            models.PointStruct(
                id=point_id(chunk.id),
                vector=list(vector),
                payload={"chunk_id": chunk.id, **chunk.payload()},
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        for start in range(0, len(points), 256):
            await self._client.upsert(self._collection, points=points[start : start + 256])

    async def delete_source(self, source_id: str) -> None:
        if not await self._client.collection_exists(self._collection):
            return
        await self._client.delete(
            self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="source_id", match=models.MatchValue(value=source_id)
                        )
                    ]
                )
            ),
        )

    async def search(
        self, vector: Sequence[float], *, limit: int, sources: Sequence[str] | None = None
    ) -> list[SearchHit]:
        if not await self._client.collection_exists(self._collection):
            return []
        query_filter = None
        if sources:
            query_filter = models.Filter(
                must=[models.FieldCondition(key="source", match=models.MatchAny(any=list(sources)))]
            )
        response = await self._client.query_points(
            self._collection,
            query=list(vector),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            SearchHit(id=str(point.id), score=float(point.score), payload=dict(point.payload or {}))
            for point in response.points
        ]

    async def count(self) -> int:
        if not await self._client.collection_exists(self._collection):
            return 0
        return (await self._client.count(self._collection, exact=True)).count

    async def sources(self) -> dict[str, int]:
        if not await self._client.collection_exists(self._collection):
            return {}
        result: dict[str, int] = {}
        offset: Any = None
        while True:
            points, offset = await self._client.scroll(
                self._collection, limit=512, offset=offset, with_payload=["source"]
            )
            for point in points:
                source = str((point.payload or {}).get("source", "?"))
                result[source] = result.get(source, 0) + 1
            if offset is None:
                return result
