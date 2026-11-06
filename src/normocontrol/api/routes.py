"""HTTP-маршруты: проверки, профили, здоровье."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse

from normocontrol import __version__
from normocontrol.api.errors import APIError
from normocontrol.api.jobs import QueueFullError
from normocontrol.api.schemas import CheckRecord, CheckState, CheckStatus, Health, ProfileSummary
from normocontrol.api.state import AppState, get_state
from normocontrol.parser.safety import InvalidDocumentError, validate_docx_bytes
from normocontrol.profiles.loader import ProfileError

router = APIRouter(prefix="/api")
health_router = APIRouter()

DOCX_MEDIA_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",  # часть браузеров и curl не знают тип .docx
    "",
}
_CHUNK = 1024 * 1024


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise APIError(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "file_too_large",
                f"Файл больше {limit // (1024 * 1024)} МБ",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base[:255] or None


@router.post(
    "/checks",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CheckStatus,
    summary="Загрузить .docx на проверку",
)
async def create_check(
    request: Request,
    file: Annotated[UploadFile, File(description="Документ .docx")],
    profile_id: Annotated[str, Form(min_length=1, max_length=100)],
    annotate: Annotated[bool, Form()] = False,
    use_llm: Annotated[bool | None, Form()] = None,
) -> CheckStatus:
    state = get_state(request)
    settings = state.settings
    filename = _safe_filename(file.filename)
    if not (filename or "").lower().endswith(".docx"):
        raise APIError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "unsupported_media_type",
            "Поддерживаются только документы Word в формате .docx",
        )
    if (file.content_type or "") not in DOCX_MEDIA_TYPES:
        raise APIError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "unsupported_media_type",
            f"Неподдерживаемый тип файла: {file.content_type}",
        )
    try:
        state.services.profiles.get(profile_id)
    except ProfileError as exc:
        raise APIError(status.HTTP_404_NOT_FOUND, "profile_not_found", str(exc)) from exc

    data = await _read_limited(file, int(settings.api.max_upload_mb * 1024 * 1024))
    try:
        validate_docx_bytes(data)
    except InvalidDocumentError as exc:
        raise APIError(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_document", str(exc)) from exc

    now = datetime.now(UTC)
    ttl = settings.jobs.result_ttl_s
    record = CheckRecord(
        id=secrets.token_urlsafe(18),  # непредсказуемый id — ссылка на отчёт и есть доступ
        filename=filename,
        profile_id=profile_id,
        annotate=annotate,
        use_llm=use_llm,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=ttl),
    )
    await state.repository.save(record, ttl)
    await state.repository.put_upload(record.id, data, int(settings.jobs.timeout_s) + ttl)
    try:
        await state.queue.enqueue(record.id)
    except QueueFullError as exc:
        await state.repository.delete(record.id)
        raise APIError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "queue_full",
            "Сервис перегружен, попробуйте через минуту",
        ) from exc
    return CheckStatus.from_record(record)


async def _record(state: AppState, check_id: str) -> CheckRecord:
    if len(check_id) > 64:
        raise APIError(status.HTTP_404_NOT_FOUND, "check_not_found", "Проверка не найдена")
    record = await state.repository.get(check_id)
    if record is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND,
            "check_not_found",
            "Проверка не найдена или срок хранения результата истёк",
        )
    return record


@router.get("/checks/{check_id}", response_model=CheckStatus, summary="Статус и отчёт проверки")
async def get_check(request: Request, check_id: str) -> CheckStatus:
    record = await _record(get_state(request), check_id)
    if record.expires_at < datetime.now(UTC):
        record = record.model_copy(update={"status": CheckState.EXPIRED, "report": None})
    return CheckStatus.from_record(record)


@router.get(
    "/checks/{check_id}/annotated.docx",
    summary="Документ с комментариями на месте ошибок",
    response_class=Response,
)
async def get_annotated(request: Request, check_id: str) -> Response:
    state = get_state(request)
    record = await _record(state, check_id)
    data = await state.repository.get_annotated(check_id)
    if data is None:
        raise APIError(
            status.HTTP_404_NOT_FOUND,
            "annotated_not_found",
            "Документ с комментариями не формировался или удалён",
        )
    stem = (record.filename or "document.docx").rsplit(".", 1)[0]
    ascii_name = "annotated.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''"
                + quote(f"{stem}_нормоконтроль.docx", safe="")
            )
        },
    )


@router.delete(
    "/checks/{check_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить результаты проверки досрочно",
)
async def delete_check(request: Request, check_id: str) -> Response:
    state = get_state(request)
    await _record(state, check_id)
    await state.repository.delete(check_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/profiles", response_model=list[ProfileSummary], summary="Доступные профили")
async def list_profiles(request: Request) -> list[ProfileSummary]:
    profiles = get_state(request).services.profiles
    return [ProfileSummary.from_profile(p) for p in profiles.selectable()]


@router.get("/profiles/{profile_id}", summary="Профиль целиком (с учётом extends)")
async def get_profile(request: Request, profile_id: str) -> JSONResponse:
    try:
        profile = get_state(request).services.profiles.get(profile_id)
    except ProfileError as exc:
        raise APIError(status.HTTP_404_NOT_FOUND, "profile_not_found", str(exc)) from exc
    return JSONResponse(profile.model_dump(mode="json", exclude_none=True))


@health_router.get("/healthz", response_model=Health, summary="Liveness")
async def healthz() -> Health:
    return Health(status="ok", version=__version__)


@health_router.get("/readyz", response_model=Health, summary="Readiness")
async def readyz(request: Request, response: Response) -> Health:
    state = get_state(request)
    components: dict[str, str] = {
        "profiles": f"ok ({len(state.services.profiles.ids())})",
        "queue": "ok" if await state.queue.ping() else "down",
        "storage": "ok" if await state.repository.ping() else "down",
    }
    client = state.services.llm_client
    if client is not None:
        components["llm"] = "ok" if await client.health() else "unavailable"
    critical_down = components["queue"] == "down" or components["storage"] == "down"
    if critical_down:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    degraded = any(value != "ok" and not value.startswith("ok") for value in components.values())
    overall = "down" if critical_down else ("degraded" if degraded else "ok")
    return Health(status=overall, version=__version__, components=components)
