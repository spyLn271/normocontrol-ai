"""Выполнение одной проверки — общий код для фоновых задач API и воркеров arq."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

from normocontrol.api.metrics import CHECK_DURATION, CHECKS_IN_PROGRESS, CHECKS_TOTAL, ISSUES_TOTAL
from normocontrol.api.repository import CheckRepository
from normocontrol.api.schemas import CheckRecord, CheckState, ErrorInfo
from normocontrol.logs import get_logger
from normocontrol.parser.safety import InvalidDocumentError
from normocontrol.pipeline import CheckOptions, CheckStep, Services, run_check
from normocontrol.profiles.loader import ProfileError

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


async def execute_check(check_id: str, repository: CheckRepository, services: Services) -> None:
    settings = services.settings.jobs
    stored = await repository.get(check_id)
    if stored is None:
        log.warning("check_missing", check_id=check_id)
        return
    record: CheckRecord = stored
    data = await repository.pop_upload(check_id)
    if data is None:
        await _fail(
            repository,
            record,
            "upload_expired",
            "Файл не найден: истёк срок ожидания",
            settings.result_ttl_s,
        )
        return

    record = record.model_copy(update={"status": CheckState.RUNNING, "updated_at": _now()})
    await repository.save(record, settings.result_ttl_s)

    async def progress(step: CheckStep) -> None:
        nonlocal record
        completed = list(record.completed_steps)
        if record.step is not None and record.step not in completed:
            completed.append(record.step)
        record = record.model_copy(
            update={"step": step, "completed_steps": completed, "updated_at": _now()}
        )
        await repository.save(record, settings.result_ttl_s)

    started = time.perf_counter()
    CHECKS_IN_PROGRESS.inc()
    try:
        outcome = await asyncio.wait_for(
            run_check(
                data,
                CheckOptions(
                    profile_id=record.profile_id,
                    filename=record.filename,
                    use_llm=record.use_llm,
                    annotate=record.annotate,
                ),
                services,
                progress,
            ),
            timeout=settings.timeout_s,
        )
    except InvalidDocumentError as exc:
        await _fail(repository, record, "invalid_document", str(exc), settings.result_ttl_s)
        return
    except ProfileError as exc:
        await _fail(repository, record, "profile_not_found", str(exc), settings.result_ttl_s)
        return
    except TimeoutError:
        await _fail(
            repository,
            record,
            "timeout",
            "Проверка заняла слишком много времени",
            settings.result_ttl_s,
        )
        return
    except Exception:
        log.exception("check_failed", check_id=check_id)
        await _fail(
            repository,
            record,
            "internal_error",
            "Внутренняя ошибка проверки",
            settings.result_ttl_s,
        )
        return
    finally:
        CHECKS_IN_PROGRESS.dec()
        del data  # исходный документ не храним

    CHECK_DURATION.observe(time.perf_counter() - started)
    CHECKS_TOTAL.labels(status="done", profile=record.profile_id).inc()
    for issue in outcome.report.issues:
        ISSUES_TOTAL.labels(severity=issue.severity.value, checker=issue.checker.value).inc()
    if outcome.annotated is not None:
        await repository.put_annotated(check_id, outcome.annotated, settings.result_ttl_s)
    completed = list(record.completed_steps)
    if record.step is not None and record.step not in completed:
        completed.append(record.step)
    record = record.model_copy(
        update={
            "status": CheckState.DONE,
            "step": None,
            "completed_steps": completed,
            "report": outcome.report,
            "has_annotated": outcome.annotated is not None,
            "updated_at": _now(),
            "expires_at": _now() + timedelta(seconds=settings.result_ttl_s),
        }
    )
    await repository.save(record, settings.result_ttl_s)


async def _fail(
    repository: CheckRepository, record: CheckRecord, code: str, message: str, ttl_s: int
) -> None:
    CHECKS_TOTAL.labels(status="failed", profile=record.profile_id).inc()
    log.info("check_failed", check_id=record.id, code=code)
    failed = record.model_copy(
        update={
            "status": CheckState.FAILED,
            "error": ErrorInfo(code=code, message=message),
            "updated_at": _now(),
        }
    )
    await repository.save(failed, ttl_s)
