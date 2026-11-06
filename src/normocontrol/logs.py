"""Структурированное логирование (structlog поверх stdlib logging)."""

from __future__ import annotations

import logging
import sys

import structlog

from normocontrol.config.settings import LogSettings


def configure_logging(settings: LogSettings) -> None:
    """Настроить structlog и stdlib так, чтобы uvicorn/arq писали в тот же формат."""
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if settings.json_format
        # plain_traceback: без значений локальных переменных — в них может быть текст документа
        else structlog.dev.ConsoleRenderer(
            colors=sys.stderr.isatty(), exception_formatter=structlog.dev.plain_traceback
        )
    )

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "arq"):
        lib_logger = logging.getLogger(name)
        lib_logger.handlers.clear()
        lib_logger.propagate = True
    # httpx на уровне INFO пишет каждый запрос к LLM — это шум.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
