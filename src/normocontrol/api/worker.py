"""Воркер arq: ``normocontrol worker`` (или ``arq normocontrol.api.worker.WorkerSettings``)."""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from normocontrol.api.repository import RedisCheckRepository
from normocontrol.api.runner import execute_check
from normocontrol.config.settings import get_settings
from normocontrol.logs import configure_logging, get_logger
from normocontrol.pipeline import Services

log = get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log)
    ctx["services"] = Services.from_settings(settings)
    ctx["repository"] = RedisCheckRepository.from_url(settings.jobs.redis_url)
    log.info("worker_started", concurrency=settings.jobs.max_concurrency)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["services"].aclose()
    await ctx["repository"].aclose()


async def run_check_job(ctx: dict[str, Any], check_id: str) -> None:
    await execute_check(check_id, ctx["repository"], ctx["services"])


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [run_check_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.jobs.redis_url)
    queue_name = _settings.jobs.queue_name
    max_jobs = _settings.jobs.max_concurrency
    # запас сверх таймаута проверки: arq не должен оборвать задачу раньше нашего wait_for
    job_timeout = int(_settings.jobs.timeout_s) + 30
    max_tries = 1  # повтор целой проверки не нужен: исходный файл уже удалён
    keep_result = 0  # результат храним сами (CheckRepository)
    health_check_interval = 30
