"""Модели эмбеддингов: Ollama ``/api/embed`` и OpenAI-совместимый ``/v1/embeddings``."""

from __future__ import annotations

from typing import Protocol

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from normocontrol.config.settings import EmbeddingSettings, LLMProvider


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    model: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def aclose(self) -> None: ...


class HttpEmbedder:
    def __init__(self, settings: EmbeddingSettings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.model = settings.model
        headers = {}
        if settings.api_key is not None:
            headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"
        self._http = http or httpx.AsyncClient(
            base_url=settings.base_url, timeout=settings.timeout_s, headers=headers
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [self.settings.passage_prefix + text for text in texts]
        vectors: list[list[float]] = []
        size = self.settings.batch_size
        for start in range(0, len(prefixed), size):
            vectors.extend(await self._embed(prefixed[start : start + size]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([self.settings.query_prefix + text]))[0]

    async def _embed(self, batch: list[str]) -> list[list[float]]:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception_type(httpx.TransportError),
                reraise=True,
            ):
                with attempt:
                    vectors = await self._request(batch)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Сервис эмбеддингов недоступен: {exc}") from exc
        if len(vectors) != len(batch):
            raise EmbeddingError("Количество векторов не совпадает с количеством текстов")
        return vectors

    async def _request(self, batch: list[str]) -> list[list[float]]:
        if self.settings.provider is LLMProvider.OPENAI_COMPATIBLE:
            response = await self._http.post(
                "/v1/embeddings", json={"model": self.model, "input": batch}
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            return [list(map(float, item["embedding"])) for item in data]
        response = await self._http.post("/api/embed", json={"model": self.model, "input": batch})
        response.raise_for_status()
        return [list(map(float, vector)) for vector in response.json()["embeddings"]]


def create_embedder(settings: EmbeddingSettings) -> Embedder:
    return HttpEmbedder(settings)
