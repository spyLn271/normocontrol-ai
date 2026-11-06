"""Клиенты локальной LLM со строгим JSON-ответом по схеме.

* :class:`OllamaClient` — ``POST /api/chat`` с параметром ``format`` (JSON Schema);
* :class:`OpenAICompatibleClient` — ``POST /v1/chat/completions`` с ``response_format``
  (vLLM, llama.cpp server, LM Studio и облачные API, если клиент разрешил).

Транспортные ошибки и 5xx повторяются с экспоненциальной паузой; невалидный JSON —
повторный запрос не более ``max_retries`` раз, затем :class:`LLMError`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from normocontrol.config.settings import LLMProvider, LLMSettings
from normocontrol.logs import get_logger

log = get_logger(__name__)

type JSON = dict[str, Any]


class LLMError(RuntimeError):
    """LLM недоступна или не вернула валидный JSON."""


class LLMClient(Protocol):
    model: str

    async def complete_json(self, *, system: str, user: str, schema: JSON) -> JSON: ...

    async def health(self) -> bool: ...

    async def aclose(self) -> None: ...


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class _ResponseCache:
    """LRU-кэш ответов по хэшу запроса: одинаковые фрагменты не проверяются дважды."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._items: OrderedDict[str, JSON] = OrderedDict()

    def get(self, key: str) -> JSON | None:
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        return None

    def put(self, key: str, value: JSON) -> None:
        if self._size <= 0:
            return
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._size:
            self._items.popitem(last=False)


def _parse_object(content: str) -> JSON:
    data = json.loads(content)  # JSONDecodeError — подкласс ValueError
    if not isinstance(data, dict):
        raise ValueError("ответ модели — не JSON-объект")  # noqa: TRY004 — единый тип ошибки
    return data


class _BaseClient:
    def __init__(self, settings: LLMSettings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.model = settings.model
        headers = {}
        if settings.api_key is not None:
            headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"
        self._http = http or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.timeout_s, connect=10.0),
            headers=headers,
        )
        self._owns_http = http is None
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._cache = _ResponseCache(settings.cache_size)

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def complete_json(self, *, system: str, user: str, schema: JSON) -> JSON:
        key = hashlib.sha256(
            json.dumps([self.model, system, user, schema], ensure_ascii=False).encode()
        ).hexdigest()
        if (cached := self._cache.get(key)) is not None:
            return cached

        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            started = time.perf_counter()
            async with self._semaphore:
                content = await self._post_with_retries(system, user, schema)
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            try:
                data = _parse_object(content)
            except ValueError as exc:
                last_error = exc
                log.warning("llm_invalid_json", attempt=attempt + 1, model=self.model)
                self._log_exchange(system, user, content, elapsed_ms, error=str(exc))
                continue
            self._log_exchange(system, user, content, elapsed_ms)
            log.debug("llm_ok", model=self.model, ms=elapsed_ms)
            self._cache.put(key, data)
            return data
        raise LLMError(f"Модель {self.model} не вернула валидный JSON: {last_error}")

    async def _post_with_retries(self, system: str, user: str, schema: JSON) -> str:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception(_retryable),
                reraise=True,
            ):
                with attempt:
                    return await self._post(system, user, schema)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM недоступна ({self.settings.base_url}): {exc}") from exc
        raise LLMError("недостижимо")  # pragma: no cover

    async def _post(self, system: str, user: str, schema: JSON) -> str:
        raise NotImplementedError

    def _log_exchange(
        self, system: str, user: str, response: str, elapsed_ms: int, error: str | None = None
    ) -> None:
        log_dir = self.settings.log_dir
        if log_dir is None:
            return
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "model": self.model,
            "ms": elapsed_ms,
            "system": system,
            "user": user,
            "response": response,
            "error": error,
        }
        path = Path(log_dir) / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


class OllamaClient(_BaseClient):
    async def _post(self, system: str, user: str, schema: JSON) -> str:
        response = await self._http.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": schema,
                "stream": False,
                "think": self.settings.think,
                "keep_alive": self.settings.keep_alive,
                "options": {
                    "temperature": self.settings.temperature,
                    "num_ctx": self.settings.num_ctx,
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("message", {}).get("content", ""))

    async def health(self) -> bool:
        try:
            response = await self._http.get("/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        names = {m.get("name") for m in response.json().get("models", [])}
        return self.model in names or f"{self.model}:latest" in names


class OpenAICompatibleClient(_BaseClient):
    async def _post(self, system: str, user: str, schema: JSON) -> str:
        response = await self._http.post(
            "/v1/chat/completions",
            json={
                "model": self.model,
                "temperature": self.settings.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "schema": schema, "strict": True},
                },
            },
        )
        response.raise_for_status()
        choices = response.json().get("choices") or [{}]
        return str(choices[0].get("message", {}).get("content", ""))

    async def health(self) -> bool:
        try:
            response = await self._http.get("/v1/models", timeout=5)
        except httpx.HTTPError:
            return False
        return response.is_success


def create_llm_client(settings: LLMSettings) -> LLMClient:
    if settings.provider is LLMProvider.OPENAI_COMPATIBLE:
        return OpenAICompatibleClient(settings)
    return OllamaClient(settings)
