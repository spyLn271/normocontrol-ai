"""Конвейер проверки: парсинг → правила → структура → ИИ → отчёт (→ .docx с комментариями)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from normocontrol.config.settings import Settings
from normocontrol.llm.checks import LLMChecker
from normocontrol.llm.client import LLMClient, create_llm_client
from normocontrol.logs import get_logger
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.parser.model import Document
from normocontrol.parser.pages import LibreOfficePageEstimator, PageEstimator
from normocontrol.profiles.loader import ProfileRegistry
from normocontrol.profiles.schema import Profile
from normocontrol.rag.embeddings import create_embedder
from normocontrol.rag.retriever import CrossEncoderReranker, Retriever
from normocontrol.rag.store import QdrantStore
from normocontrol.report.aggregate import build_report
from normocontrol.report.model import (
    Checker,
    CheckRun,
    CheckStatus,
    Issue,
    Notice,
    NoticeLevel,
    Report,
)
from normocontrol.report.render_docx import annotate_docx
from normocontrol.rules.engine import run_rules

log = get_logger(__name__)


class CheckStep(StrEnum):
    PARSE = "parse"
    RULES = "rules"
    STRUCTURE = "structure"
    LLM = "llm"
    REPORT = "report"


STEP_TITLES: dict[CheckStep, str] = {
    CheckStep.PARSE: "Чтение файла",
    CheckStep.RULES: "Правила оформления",
    CheckStep.STRUCTURE: "Структура документа",
    CheckStep.LLM: "ИИ-проверки",
    CheckStep.REPORT: "Формирование отчёта",
}

type ProgressCallback = Callable[[CheckStep], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class CheckOptions:
    profile_id: str
    filename: str | None = None
    use_llm: bool | None = None  # None — как в настройках (llm.enabled)
    annotate: bool = False


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    report: Report
    document: Document
    annotated: bytes | None = None


class Services:
    """Долгоживущие зависимости проверки — создаются один раз на процесс."""

    def __init__(
        self,
        settings: Settings,
        profiles: ProfileRegistry,
        *,
        page_estimator: PageEstimator | None = None,
        llm_client: LLMClient | None = None,
        retriever: Retriever | None = None,
    ) -> None:
        self.settings = settings
        self.profiles = profiles
        self.page_estimator = page_estimator
        self.llm_client = llm_client
        self.retriever = retriever

    @classmethod
    def from_settings(cls, settings: Settings) -> Services:
        profiles = ProfileRegistry.from_directory(settings.profiles_dir)
        estimator: PageEstimator | None = None
        if settings.pages.mode != "off":
            libreoffice = LibreOfficePageEstimator(
                settings.pages.soffice_path, settings.pages.timeout_s
            )
            if libreoffice.available():
                estimator = libreoffice
            elif settings.pages.mode == "on":
                log.warning("libreoffice_unavailable", soffice=settings.pages.soffice_path)
        llm_client = create_llm_client(settings.llm) if settings.llm.enabled else None
        retriever: Retriever | None = None
        if settings.llm.enabled and settings.rag.enabled:
            reranker = (
                CrossEncoderReranker(settings.reranker) if settings.reranker.enabled else None
            )
            retriever = Retriever(
                create_embedder(settings.embeddings),
                QdrantStore.from_settings(settings.vector_store),
                settings.rag,
                reranker,
            )
        return cls(
            settings,
            profiles,
            page_estimator=estimator,
            llm_client=llm_client,
            retriever=retriever,
        )

    def llm_checker(self) -> LLMChecker | None:
        if self.llm_client is None:
            return None
        return LLMChecker(
            self.llm_client,
            self.retriever,
            batch_size=self.settings.llm.batch_size,
            rag_top_k=self.settings.rag.top_k,
        )

    async def aclose(self) -> None:
        if self.llm_client is not None:
            await self.llm_client.aclose()
        if self.retriever is not None:
            await self.retriever.embedder.aclose()
            await self.retriever.store.aclose()


async def _noop(_: CheckStep) -> None:
    return None


def _notices(document: Document, profile: Profile, checks: list[CheckRun]) -> list[Notice]:
    notices: list[Notice] = []
    if profile.is_draft:
        notices.append(
            Notice(
                code="profile_draft",
                level=NoticeLevel.WARNING,
                message="Профиль-черновик: требования ещё не сверены с официальным текстом, "
                "результаты предварительные",
            )
        )
    source = document.stats.page_source
    if source is None:
        notices.append(
            Notice(
                code="pages_unknown",
                message="Номера страниц не определены: ошибки привязаны к абзацам",
            )
        )
    elif source == "breaks":
        notices.append(
            Notice(
                code="pages_approximate",
                message="Номера страниц оценены приблизительно (по разрывам страниц)",
            )
        )
    failed = [c.rule_id for c in checks if c.status is CheckStatus.FAILED]
    if failed:
        notices.append(
            Notice(
                code="checks_failed",
                level=NoticeLevel.WARNING,
                message="Не выполнены проверки: " + ", ".join(failed),
            )
        )
    return notices


async def run_check(
    data: bytes,
    options: CheckOptions,
    services: Services,
    progress: ProgressCallback | None = None,
) -> CheckOutcome:
    report_progress = progress or _noop
    started = time.perf_counter()
    created_at = datetime.now(UTC)
    profile = services.profiles.get(options.profile_id)

    await report_progress(CheckStep.PARSE)
    document = await asyncio.to_thread(
        parse_docx, data, options.filename, page_estimator=services.page_estimator
    )

    issues: list[Issue] = []
    checks: list[CheckRun] = []
    await report_progress(CheckStep.RULES)
    rules = await asyncio.to_thread(run_rules, document, profile, checkers={Checker.RULE})
    issues += rules.issues
    checks += rules.checks

    await report_progress(CheckStep.STRUCTURE)
    structure = await asyncio.to_thread(run_rules, document, profile, checkers={Checker.STRUCTURE})
    issues += structure.issues
    checks += structure.checks

    extra_notices: list[Notice] = []
    use_llm = services.settings.llm.enabled if options.use_llm is None else options.use_llm
    checker = services.llm_checker() if use_llm else None
    llm_model: str | None = None
    if checker is not None:
        await report_progress(CheckStep.LLM)
        llm = await checker.run(document, profile)
        issues += llm.issues
        checks += llm.checks
        extra_notices += llm.notices
        llm_model = checker.client.model
    elif profile.bibliography is not None and profile.bibliography.checker == "llm":
        extra_notices.append(
            Notice(
                code="llm_disabled",
                message="ИИ-проверки отключены: оформление записей "
                "списка литературы не проверялось",
            )
        )

    await report_progress(CheckStep.REPORT)
    report = build_report(
        document=document,
        profile=profile,
        issues=issues,
        checks=checks,
        notices=[*_notices(document, profile, checks), *extra_notices],
        created_at=created_at,
        duration_ms=round((time.perf_counter() - started) * 1000),
        llm_model=llm_model,
        embedding_model=(
            services.retriever.embedder.model if checker and services.retriever else None
        ),
    )
    annotated = await asyncio.to_thread(annotate_docx, data, report) if options.annotate else None
    log.info(
        "check_done",
        profile=profile.id,
        issues=len(report.issues),
        score=report.score,
        ms=report.duration_ms,
    )
    return CheckOutcome(report=report, document=document, annotated=annotated)


def run_check_sync(data: bytes, options: CheckOptions, services: Services) -> CheckOutcome:
    async def _run() -> CheckOutcome:
        try:
            return await run_check(data, options, services)
        finally:
            await services.aclose()

    return asyncio.run(_run())
