"""FastAPI-приложение: ``uvicorn normocontrol.api.app:create_app --factory``."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from normocontrol import __version__
from normocontrol.api.errors import error_body, install_error_handlers
from normocontrol.api.jobs import ArqJobQueue, InlineJobQueue, JobQueue
from normocontrol.api.metrics import HTTP_DURATION
from normocontrol.api.repository import CheckRepository, MemoryCheckRepository, RedisCheckRepository
from normocontrol.api.routes import health_router, router
from normocontrol.api.state import AppState
from normocontrol.config.settings import JobBackend, Settings, get_settings
from normocontrol.logs import configure_logging, get_logger
from normocontrol.pipeline import Services

log = get_logger(__name__)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-site",
}


def create_app(
    settings: Settings | None = None,
    *,
    services: Services | None = None,
    repository: CheckRepository | None = None,
    queue: JobQueue | None = None,
) -> FastAPI:
    """Фабрика приложения. Зависимости можно подменить в тестах."""
    settings = settings or get_settings()
    configure_logging(settings.log)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_services = services or Services.from_settings(settings)
        if settings.jobs.backend is JobBackend.ARQ:
            app_repository = repository or RedisCheckRepository.from_url(settings.jobs.redis_url)
            app_queue = queue or await ArqJobQueue.connect(settings.jobs)
        else:
            app_repository = repository or MemoryCheckRepository()
            app_queue = queue or InlineJobQueue(app_repository, app_services, settings.jobs)
        app.state.normocontrol = AppState(settings, app_services, app_repository, app_queue)
        log.info(
            "api_started",
            version=__version__,
            jobs=settings.jobs.backend.value,
            llm=settings.llm.enabled,
            profiles=len(app_services.profiles.ids()),
        )
        try:
            yield
        finally:
            await app_queue.aclose()
            await app_repository.aclose()
            await app_services.aclose()

    docs = settings.api.docs_enabled
    app = FastAPI(
        title="Normocontrol AI",
        version=__version__,
        description="Проверка оформления документов по требованиям Республики Казахстан.",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        root_path=settings.api.root_path,
    )
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(health_router)

    if settings.api.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    _install_middleware(app, settings)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api.cors_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    return app


def _install_middleware(app: FastAPI, settings: Settings) -> None:
    max_body = int(settings.api.max_upload_mb * 1024 * 1024) + 64 * 1024

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_body:
                response: Response = JSONResponse(
                    error_body("file_too_large", "Запрос слишком большой"), status_code=413
                )
            else:
                response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        elapsed = time.perf_counter() - started
        route = _route_template(request)
        HTTP_DURATION.labels(request.method, route, str(response.status_code)).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if route.startswith("/api/checks"):
            response.headers["Cache-Control"] = "no-store"  # в отчётах персональные данные
        if route not in {"/healthz", "/readyz", "/metrics"}:
            log.info(
                "http_request",
                method=request.method,
                route=route,
                status=response.status_code,
                ms=round(elapsed * 1000, 1),
            )
        return response


def _route_template(request: Request) -> str:
    """Шаблон маршрута (``/api/checks/{check_id}``) без id — иначе метрики разрастаются без предела.

    Маршрутизатор кладёт найденный маршрут в ``scope["route"]``; для неизвестных путей —
    ``unmatched``.
    """
    route = request.scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return str(template) if template else "unmatched"
