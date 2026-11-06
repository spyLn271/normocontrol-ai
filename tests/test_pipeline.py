from __future__ import annotations

import pytest

from normocontrol.config.settings import RagSettings, Settings
from normocontrol.dataset.generate import generate_sample
from normocontrol.parser.safety import InvalidDocumentError
from normocontrol.pipeline import CheckOptions, CheckStep, Services, run_check
from normocontrol.profiles.loader import ProfileError, ProfileRegistry
from normocontrol.rag.indexer import index_text
from normocontrol.rag.retriever import Retriever
from normocontrol.rag.store import QdrantStore
from tests.fakes import FakeLLM, HashingEmbedder
from tests.llm.test_checks import RULES_TEXT, _respond_first_entry


async def test_pipeline_steps_and_notices(settings: Settings, registry: ProfileRegistry) -> None:
    services = Services(settings, registry)
    data, _ = generate_sample(registry.get("gost-7.32-2017"), seed=4, mutations=3)
    steps: list[CheckStep] = []

    async def progress(step: CheckStep) -> None:
        steps.append(step)

    outcome = await run_check(
        data,
        CheckOptions(profile_id="gost-7.32-2017", filename="r.docx", annotate=True),
        services,
        progress,
    )
    assert steps == [CheckStep.PARSE, CheckStep.RULES, CheckStep.STRUCTURE, CheckStep.REPORT]
    codes = {n.code for n in outcome.report.notices}
    assert "profile_draft" in codes
    assert "llm_disabled" in codes
    assert outcome.annotated is not None
    assert outcome.report.document.filename == "r.docx"
    assert outcome.report.profile.status == "draft"


async def test_pipeline_with_llm(settings: Settings, registry: ProfileRegistry) -> None:
    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    await index_text(
        RULES_TEXT, source="МИ 049-2026", source_id="mi", embedder=embedder, store=store
    )
    llm = FakeLLM(_respond_first_entry)
    services = Services(
        settings,
        registry,
        llm_client=llm,
        retriever=Retriever(embedder, store, RagSettings(min_score=-1)),
    )
    data, _ = generate_sample(registry.get("kru-mi-049-2026"), seed=4, mutations=0)
    steps: list[CheckStep] = []

    async def progress(step: CheckStep) -> None:
        steps.append(step)

    outcome = await run_check(
        data, CheckOptions(profile_id="kru-mi-049-2026", use_llm=True), services, progress
    )
    assert CheckStep.LLM in steps
    assert any(i.rule_id == "bibliography.format" for i in outcome.report.issues)
    assert outcome.report.engine.llm_model == "fake-llm"
    assert outcome.report.engine.embedding_model == "hashing-test"


async def test_pipeline_errors(settings: Settings, registry: ProfileRegistry) -> None:
    services = Services(settings, registry)
    with pytest.raises(ProfileError):
        await run_check(b"PK", CheckOptions(profile_id="missing"), services)
    with pytest.raises(InvalidDocumentError):
        await run_check(b"not a docx", CheckOptions(profile_id="kru-mi-049-2026"), services)


def test_services_from_settings_without_llm(settings: Settings) -> None:
    services = Services.from_settings(settings)
    assert services.llm_client is None
    assert services.retriever is None
    assert services.llm_checker() is None
    assert "kru-mi-049-2026" in services.profiles
