"""Очередь проверок.

* :class:`InlineJobQueue` — asyncio-задачи внутри процесса API с ограничением параллелизма;
* :class:`ArqJobQueue` — задачи в Redis, выполняются отдельными воркерами (``normocontrol worker``).
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from normocontrol.api.repository import CheckRepository
from normocontrol.api.runner import execute_check
from normocontrol.config.settings import JobSettings
from normocontrol.logs import get_logger
from normocontrol.pipeline import Services

log = get_logger(__name__)

JOB_FUNCTION = "run_check_job"


class QueueFullError(RuntimeError):
    pass


class JobQueue(Protocol):
    async def enqueue(self, check_id: str) -> None: ...

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


class InlineJobQueue:
    def __init__(
        self, repository: CheckRepository, services: Services, settings: JobSettings
    ) -> None:
        self._repository = repository
        self._services = services
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._max_pending = settings.max_pending
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, check_id: str) -> None:
        if len(self._tasks) >= self._max_pending:
            raise QueueFullError
        task = asyncio.create_task(self._run(check_id), name=f"check:{check_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, check_id: str) -> None:
        async with self._semaphore:
            await execute_check(check_id, self._repository, self._services)

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)


class ArqJobQueue:
    def __init__(self, pool: ArqRedis, settings: JobSettings) -> None:
        self._pool = pool
        self._settings = settings

    @classmethod
    async def connect(cls, settings: JobSettings) -> ArqJobQueue:
        pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url), default_queue_name=settings.queue_name
        )
        return cls(pool, settings)

    async def enqueue(self, check_id: str) -> None:
        queued = await self._pool.zcard(self._settings.queue_name)
        if queued >= self._settings.max_pending:
            raise QueueFullError
        await self._pool.enqueue_job(
            JOB_FUNCTION, check_id, _job_id=check_id, _queue_name=self._settings.queue_name
        )

    async def ping(self) -> bool:
        try:
            return bool(await self._pool.ping())
        except OSError:
            return False

    async def aclose(self) -> None:
        await self._pool.aclose()
