"""Интеграция с настоящим Redis: репозиторий, очередь arq и воркер (``pytest -m integration``)."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from arq.worker import Worker

from normocontrol.api.jobs import JOB_FUNCTION, ArqJobQueue
from normocontrol.api.repository import RedisCheckRepository
from normocontrol.api.schemas import CheckRecord, CheckState
from normocontrol.api.worker import run_check_job
from normocontrol.config.settings import JobBackend, JobSettings, Settings
from normocontrol.dataset.generate import generate_sample
from normocontrol.pipeline import Services
from normocontrol.profiles.loader import ProfileRegistry

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    binary = shutil.which("redis-server")
    if binary is None:
        pytest.skip("redis-server не установлен")
    port = _free_port()
    process = subprocess.Popen(  # noqa: S603
        [binary, "--port", str(port), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)
    yield f"redis://127.0.0.1:{port}/0"
    process.terminate()
    process.wait(timeout=5)


async def test_redis_repository_roundtrip(redis_url: str) -> None:
    repository = RedisCheckRepository.from_url(redis_url)
    now = datetime.now(UTC)
    record = CheckRecord(
        id="r1", profile_id="p", created_at=now, updated_at=now, expires_at=now + timedelta(hours=1)
    )
    await repository.save(record, 60)
    assert await repository.get("r1") == record
    await repository.put_upload("r1", b"data", 60)
    assert await repository.pop_upload("r1") == b"data"
    assert await repository.pop_upload("r1") is None  # файл забирается один раз
    await repository.put_annotated("r1", b"docx", 60)
    assert await repository.get_annotated("r1") == b"docx"
    await repository.delete("r1")
    assert await repository.get("r1") is None
    assert await repository.ping()
    await repository.aclose()


async def test_arq_worker_processes_check(
    redis_url: str, settings: Settings, registry: ProfileRegistry
) -> None:
    jobs = JobSettings(backend=JobBackend.ARQ, redis_url=redis_url, queue_name="nc:test")
    repository = RedisCheckRepository.from_url(redis_url)
    queue = await ArqJobQueue.connect(jobs)
    data, _ = generate_sample(registry.get("kru-mi-049-2026"), seed=1, mutations=2)
    now = datetime.now(UTC)
    record = CheckRecord(
        id="job1",
        profile_id="kru-mi-049-2026",
        filename="a.docx",
        annotate=True,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await repository.save(record, 300)
    await repository.put_upload(record.id, data, 300)
    await queue.enqueue(record.id)

    services = Services(settings.model_copy(update={"jobs": jobs}), registry)
    worker = Worker(
        functions=[run_check_job],
        redis_pool=queue._pool,
        queue_name=jobs.queue_name,
        burst=True,
        ctx={"services": services, "repository": repository},
        handle_signals=False,
        max_tries=1,
        keep_result=0,
    )
    await worker.main()
    await worker.close()

    finished = await repository.get(record.id)
    assert finished is not None
    assert finished.status is CheckState.DONE
    assert finished.report is not None
    assert finished.has_annotated
    assert await repository.get_annotated(record.id)
    assert await repository.pop_upload(record.id) is None  # исходный файл удалён
    assert run_check_job.__name__ == JOB_FUNCTION
    await repository.aclose()
