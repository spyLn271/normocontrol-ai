"""Поиск пунктов стандартов: эмбеддинг → top-N кандидатов → (reranker) → приоритеты профиля."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from normocontrol.config.settings import RagSettings, RerankerSettings
from normocontrol.profiles.schema import RagSource
from normocontrol.rag.embeddings import Embedder
from normocontrol.rag.store import SearchHit, VectorStore

# Бонус за приоритет источника: методичка вуза (priority 1) важнее базового ГОСТа (2).
PRIORITY_BONUS = 0.05


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    text: str
    source: str
    clause: str
    kind: str
    score: float

    @property
    def citation(self) -> str:
        """«МИ 049-2026, п. 45», «МИ 049-2026, Приложение И» или просто источник."""
        clause = self.clause
        if clause.replace(".", "").isdigit():
            return f"{self.source}, п. {clause}"
        if clause and clause != "intro":
            return f"{self.source}, {clause}"
        return self.source


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    """Cross-encoder (bge-reranker-v2-m3) через sentence-transformers — extra «rerank»."""

    def __init__(self, settings: RerankerSettings) -> None:
        try:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            raise RuntimeError("Reranker включён, но не установлен extra «rerank»") from exc
        self._model: Any = CrossEncoder(settings.model, device=settings.device)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        scores = self._model.predict([(query, text) for text in texts])
        return [float(s) for s in scores]


class Retriever:
    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        settings: RagSettings,
        reranker: Reranker | None = None,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.settings = settings
        self.reranker = reranker

    async def retrieve(
        self,
        query: str,
        *,
        sources: Sequence[RagSource] = (),
        k: int | None = None,
    ) -> list[RetrievedChunk]:
        limit = k or self.settings.top_k
        vector = await self.embedder.embed_query(query)
        names = [s.source for s in sources]
        hits = await self.store.search(
            vector, limit=max(self.settings.candidates, limit), sources=names or None
        )
        hits = [h for h in hits if h.score >= self.settings.min_score]
        if not hits:
            return []
        scores = [h.score for h in hits]
        if self.reranker is not None:
            reranker = self.reranker
            texts = [str(h.payload.get("text", "")) for h in hits]
            scores = await asyncio.to_thread(reranker.score, query, texts)
        priorities = {s.source: s.priority for s in sources}
        worst = max(priorities.values(), default=1)
        ranked = sorted(
            zip(hits, scores, strict=True),
            key=lambda pair: (
                pair[1]
                + PRIORITY_BONUS
                * (worst - priorities.get(str(pair[0].payload.get("source")), worst))
            ),
            reverse=True,
        )
        return [_to_chunk(hit, score) for hit, score in ranked[:limit]]


def _to_chunk(hit: SearchHit, score: float) -> RetrievedChunk:
    payload = hit.payload
    return RetrievedChunk(
        id=str(payload.get("chunk_id", hit.id)),
        text=str(payload.get("text", "")),
        source=str(payload.get("source", "")),
        clause=str(payload.get("clause", "")),
        kind=str(payload.get("kind", "rule")),
        score=score,
    )
