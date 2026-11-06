from __future__ import annotations

import re
from typing import Any

import pytest

from normocontrol.config.settings import RagSettings
from normocontrol.dataset.generate import generate_sample
from normocontrol.llm.checks import LLMChecker, LLMFinding, validate_findings
from normocontrol.llm.client import LLMError
from normocontrol.llm.templates import load_prompt
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.parser.model import Document, ParagraphRole
from normocontrol.profiles.schema import Profile, Severity
from normocontrol.rag.indexer import index_text
from normocontrol.rag.retriever import RetrievedChunk, Retriever
from normocontrol.rag.store import QdrantStore
from normocontrol.report.model import Checker, CheckStatus
from tests.fakes import FakeLLM, HashingEmbedder

RULES_TEXT = """Глава 5. Содержание и структура работы
45. Список использованных источников должен содержать сведения об источниках. Сведения об
источниках следует нумеровать арабскими цифрами без точки и печатать с абзацного отступа.
Список использованных источников оформляется по определенным правилам библиографической записи.
"""


def chunk(n: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"c{n}", text="правило", source="МИ", clause="45", kind="rule", score=1
    )


def document(profile: Profile) -> Document:
    data, _ = generate_sample(profile, seed=2, mutations=0)
    return parse_docx(data)


def test_prompt_template_loads() -> None:
    prompt = load_prompt("bibliography.format")
    system, user = prompt.render(rules="[1] правило", fragments="(paragraph_id=p-1) «текст»")
    assert prompt.version == "2"
    assert "Не сообщай" in system or "не сообщай" in system
    assert "[1] правило" in user
    assert "p-1" in user


def test_guards_reject_hallucinations(kru: Profile) -> None:
    doc = document(kru)
    entry = doc.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY)[0]
    paragraphs = {entry.id: entry}
    quote = entry.text.split()[1]
    findings = [
        LLMFinding(paragraph_id=entry.id, rule_ref=1, quote=quote, message="настоящая ошибка"),
        LLMFinding(paragraph_id="p-9999", rule_ref=1, quote=quote, message="чужой абзац"),
        LLMFinding(paragraph_id=entry.id, rule_ref=7, quote=quote, message="правила нет"),
        LLMFinding(
            paragraph_id=entry.id, rule_ref=1, quote="выдуманная цитата", message="нет цитаты"
        ),
    ]
    accepted, rejected = validate_findings(findings, paragraphs, [chunk()])
    assert [f.message for f, _, _ in accepted] == ["настоящая ошибка"]
    assert rejected == 3


def test_noop_fix_and_exemplar_rejected(kru: Profile) -> None:
    doc = document(kru)
    entry = doc.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY)[0]
    quote = entry.text.split()[1]
    noop = LLMFinding(
        paragraph_id=entry.id, rule_ref=1, quote=entry.text, message="ошибка", fix=entry.text
    )
    assert validate_findings([noop], {entry.id: entry}, [chunk()]) == ([], 1)
    exemplar = RetrievedChunk(
        id="x",
        text="Образцы: " + entry.text.split(" ", 1)[1],
        source="МИ",
        clause="Приложение И",
        kind="appendix",
        score=1,
    )
    finding = LLMFinding(paragraph_id=entry.id, rule_ref=1, quote=quote, message="ошибка", fix="x")
    assert validate_findings([finding], {entry.id: entry}, [exemplar]) == ([], 1)


def test_quote_comparison_tolerates_typography(kru: Profile) -> None:
    doc = document(kru)
    entry = doc.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY)[0]
    quote = entry.text[entry.text.index("–") - 3 : entry.text.index("–") + 5].replace("–", "-")
    findings = [LLMFinding(paragraph_id=entry.id, rule_ref=1, quote=quote, message="тире")]
    accepted, _ = validate_findings(findings, {entry.id: entry}, [chunk()])
    assert len(accepted) == 1


async def _retriever(text: str = RULES_TEXT) -> Retriever:
    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    await index_text(text, source="МИ 049-2026", source_id="mi", embedder=embedder, store=store)
    return Retriever(embedder, store, RagSettings(min_score=-1))


def _respond_first_entry(_: str, user: str) -> dict[str, Any]:
    match = re.search(r'\(paragraph_id=(p-\d+)\) "(\S+ \S+)', user)
    assert match is not None
    return {
        "issues": [
            {
                "paragraph_id": match.group(1),
                "rule_ref": 1,
                "quote": match.group(2),
                "message": "Нет пробела",
                "fix": "Добавьте пробел",
                "severity": "error",
            },
            {
                "paragraph_id": match.group(1),
                "rule_ref": 1,
                "quote": "цитаты нет в тексте",
                "message": "Галлюцинация",
                "fix": "",
                "severity": "error",
            },
        ]
    }


async def test_llm_checker_end_to_end(kru: Profile) -> None:
    llm = FakeLLM(_respond_first_entry)
    checker = LLMChecker(llm, await _retriever(), batch_size=2)
    doc = document(kru)
    result = await checker.run(doc, kru)
    entries = doc.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY)
    assert len(llm.calls) == -(-len(entries) // 2)
    assert result.issues
    assert all(i.checker is Checker.LLM for i in result.issues)
    assert all(i.rule_id == "bibliography.format" for i in result.issues)
    first = result.issues[0]
    assert first.reference == "МИ 049-2026, п. 45"
    assert first.reference_quote
    # профиль задаёт warning — модель не может поднять серьёзность до error
    assert first.severity is Severity.WARNING
    check = result.checks[0]
    assert check.status is CheckStatus.OK
    assert "отброшено неподтверждённых замечаний" in (check.detail or "")


async def test_llm_checker_without_rules_skips(kru: Profile) -> None:
    store = QdrantStore.in_memory()
    retriever = Retriever(HashingEmbedder(), store, RagSettings())
    llm = FakeLLM(_respond_first_entry)
    result = await LLMChecker(llm, retriever).run(document(kru), kru)
    assert llm.calls == []
    assert result.checks[0].status is CheckStatus.SKIPPED
    assert result.notices[0].code == "rag_empty"


async def test_llm_failure_is_reported_not_raised(kru: Profile) -> None:
    def broken(_: str, __: str) -> dict[str, Any]:
        raise LLMError("down")

    result = await LLMChecker(FakeLLM(broken), await _retriever()).run(document(kru), kru)
    assert result.issues == []
    assert result.checks[0].status is CheckStatus.FAILED
    assert result.notices[0].code == "llm_failed"


async def test_profile_without_llm_checks_does_nothing(order: Profile) -> None:
    llm = FakeLLM(_respond_first_entry)
    result = await LLMChecker(llm, None).run(document(order), order)
    assert (result.issues, result.checks, llm.calls) == ([], [], [])


@pytest.mark.llm
async def test_real_ollama_returns_valid_json() -> None:
    """Запуск: ``pytest -m llm`` при работающей Ollama с моделью из настроек."""
    from normocontrol.config.settings import Settings  # noqa: PLC0415
    from normocontrol.llm.client import create_llm_client  # noqa: PLC0415

    client = create_llm_client(Settings().llm)
    try:
        data = await client.complete_json(
            system="Отвечай JSON.",
            user='Верни {"answer": 4} для вопроса «2+2».',
            schema={
                "type": "object",
                "properties": {"answer": {"type": "integer"}},
                "required": ["answer"],
            },
        )
    finally:
        await client.aclose()
    assert data["answer"] == 4
