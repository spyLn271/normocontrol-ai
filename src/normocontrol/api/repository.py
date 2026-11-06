"""Хранилище проверок с TTL: состояние, загруженный файл (до обработки), .docx с комментариями.

* :class:`MemoryCheckRepository` — один процесс (разработка, тесты, backend ``inline``);
* :class:`RedisCheckRepository` — общий для API и воркеров (backend ``arq``).

Загруженный документ живёт только до начала обработки: воркер забирает его и удаляет.
"""

from __future__ import annotations

import asyncio
import time
from typing import Protocol

from redis.asyncio import Redis

from normocontrol.api.schemas import CheckRecord

_PREFIX = "nc"


class CheckRepository(Protocol):
    async def save(self, record: CheckRecord, ttl_s: int) -> None: ...

    async def get(self, check_id: str) -> CheckRecord | None: ...

    async def delete(self, check_id: str) -> None: ...

    async def put_upload(self, check_id: str, data: bytes, ttl_s: int) -> None: ...

    async def pop_upload(self, check_id: str) -> bytes | None: ...

    async def put_annotated(self, check_id: str, data: bytes, ttl_s: int) -> None: ...

    async def get_annotated(self, check_id: str) -> bytes | None: ...

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


class MemoryCheckRepository:
    def __init__(self) -> None:
        self._records: dict[str, tuple[float, str]] = {}
        self._blobs: dict[str, tuple[float, bytes]] = {}
        self._lock = asyncio.Lock()

    def _alive(self, expires: float) -> bool:
        return expires > time.monotonic()

    async def _purge(self) -> None:
        now = time.monotonic()
        for store in (self._records, self._blobs):
            for key in [k for k, (expires, _) in store.items() if expires <= now]:
                store.pop(key, None)

    async def save(self, record: CheckRecord, ttl_s: int) -> None:
        async with self._lock:
            await self._purge()
            self._records[record.id] = (time.monotonic() + ttl_s, record.model_dump_json())

    async def get(self, check_id: str) -> CheckRecord | None:
        item = self._records.get(check_id)
        if item is None or not self._alive(item[0]):
            return None
        return CheckRecord.model_validate_json(item[1])

    async def delete(self, check_id: str) -> None:
        async with self._lock:
            self._records.pop(check_id, None)
            self._blobs.pop(f"upload:{check_id}", None)
            self._blobs.pop(f"annotated:{check_id}", None)

    async def put_upload(self, check_id: str, data: bytes, ttl_s: int) -> None:
        self._blobs[f"upload:{check_id}"] = (time.monotonic() + ttl_s, data)

    async def pop_upload(self, check_id: str) -> bytes | None:
        item = self._blobs.pop(f"upload:{check_id}", None)
        return item[1] if item and self._alive(item[0]) else None

    async def put_annotated(self, check_id: str, data: bytes, ttl_s: int) -> None:
        self._blobs[f"annotated:{check_id}"] = (time.monotonic() + ttl_s, data)

    async def get_annotated(self, check_id: str) -> bytes | None:
        item = self._blobs.get(f"annotated:{check_id}")
        return item[1] if item and self._alive(item[0]) else None

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class RedisCheckRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    @classmethod
    def from_url(cls, url: str) -> RedisCheckRepository:
        return cls(Redis.from_url(url))

    @staticmethod
    def _key(kind: str, check_id: str) -> str:
        return f"{_PREFIX}:{kind}:{check_id}"

    async def save(self, record: CheckRecord, ttl_s: int) -> None:
        await self._redis.set(self._key("check", record.id), record.model_dump_json(), ex=ttl_s)

    async def get(self, check_id: str) -> CheckRecord | None:
        raw = await self._redis.get(self._key("check", check_id))
        return CheckRecord.model_validate_json(raw) if raw else None

    async def delete(self, check_id: str) -> None:
        await self._redis.delete(
            self._key("check", check_id),
            self._key("upload", check_id),
            self._key("annotated", check_id),
        )

    async def put_upload(self, check_id: str, data: bytes, ttl_s: int) -> None:
        await self._redis.set(self._key("upload", check_id), data, ex=ttl_s)

    async def pop_upload(self, check_id: str) -> bytes | None:
        # GET + DEL в транзакции MULTI: атомарно и работает на любой версии Redis (GETDEL — с 6.2)
        key = self._key("upload", check_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            raw, _ = await pipe.execute()
        return bytes(raw) if raw else None

    async def put_annotated(self, check_id: str, data: bytes, ttl_s: int) -> None:
        await self._redis.set(self._key("annotated", check_id), data, ex=ttl_s)

    async def get_annotated(self, check_id: str) -> bytes | None:
        raw = await self._redis.get(self._key("annotated", check_id))
        return bytes(raw) if raw else None

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except OSError:
            return False

    async def aclose(self) -> None:
        await self._redis.aclose()
