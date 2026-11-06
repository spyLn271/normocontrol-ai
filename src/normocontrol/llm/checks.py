"""ИИ-проверки с RAG и защитой от галлюцинаций (docs/RAG.md).

Каждое замечание модели принимается, только если:

1. ``paragraph_id`` — один из фрагментов, отправленных в этом запросе;
2. ``rule_ref`` — номер правила, которое реально было в промпте;
3. ``quote`` дословно (с точностью до пробелов) встречается в тексте фрагмента;
4. ``fix`` что-то меняет: исправление, совпадающее с исходным текстом, — признак выдуманной ошибки;
5. фрагмент не совпадает с образцом из официального источника, найденного RAG
   (образец оформления по определению правильный).

Иначе замечание отбрасывается и логируется.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from normocontrol.llm.client import LLMClient, LLMError
from normocontrol.llm.templates import load_prompt
from normocontrol.logs import get_logger
from normocontrol.parser.model import Document, Paragraph, ParagraphRole
from normocontrol.profiles.schema import Profile, Severity
from normocontrol.rag.embeddings import EmbeddingError
from normocontrol.rag.retriever import RetrievedChunk, Retriever
from normocontrol.report.model import (
    Category,
    Checker,
    CheckRun,
    CheckStatus,
    Issue,
    Location,
    Notice,
    NoticeLevel,
)

log = get_logger(__name__)

BIBLIOGRAPHY_RULE = "bibliography.format"
_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "–": "-", "—": "-"})


class LLMFinding(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paragraph_id: str
    rule_ref: int
    quote: str = Field(min_length=1)
    message: str = Field(min_length=3)
    fix: str = ""
    severity: Literal["error", "warning"] = "warning"


class LLMFindings(BaseModel):
    issues: list[LLMFinding]


FINDINGS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paragraph_id": {"type": "string"},
                    "rule_ref": {"type": "integer"},
                    "quote": {"type": "string"},
                    "message": {"type": "string"},
                    "fix": {"type": "string"},
                    "severity": {"type": "string", "enum": ["error", "warning"]},
                },
                "required": ["paragraph_id", "rule_ref", "quote", "message", "fix", "severity"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["issues"],
    "additionalProperties": False,
}


@dataclass(slots=True)
class LLMRunResult:
    issues: list[Issue] = field(default_factory=list)
    checks: list[CheckRun] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.translate(_QUOTES)).strip().casefold()


_ENTRY_NUMBER = re.compile(r"^\s*\d{1,3}\.?\s+")


def _matches_exemplar(text: str, rules: Sequence[RetrievedChunk]) -> bool:
    """Запись слово в слово повторяет образец из официального текста (без номера)."""
    body = _normalize(_ENTRY_NUMBER.sub("", text))
    return len(body) >= 30 and any(body in _normalize(chunk.text) for chunk in rules)


def validate_findings(
    findings: Sequence[LLMFinding],
    paragraphs: dict[str, Paragraph],
    rules: Sequence[RetrievedChunk],
) -> tuple[list[tuple[LLMFinding, Paragraph, RetrievedChunk]], int]:
    """Отфильтровать замечания по трём правилам защиты. Возвращает (принятые, отброшено)."""
    accepted: list[tuple[LLMFinding, Paragraph, RetrievedChunk]] = []
    rejected = 0
    for finding in findings:
        paragraph = paragraphs.get(finding.paragraph_id)
        if paragraph is None:
            log.info("llm_reject", reason="unknown_paragraph", paragraph_id=finding.paragraph_id)
            rejected += 1
            continue
        if not 1 <= finding.rule_ref <= len(rules):
            log.info("llm_reject", reason="unknown_rule", rule_ref=finding.rule_ref)
            rejected += 1
            continue
        if _normalize(finding.quote) not in _normalize(paragraph.text):
            log.info("llm_reject", reason="quote_not_found", paragraph_id=paragraph.id)
            rejected += 1
            continue
        if finding.fix and _normalize(_ENTRY_NUMBER.sub("", finding.fix)) in {
            _normalize(_ENTRY_NUMBER.sub("", finding.quote)),
            _normalize(_ENTRY_NUMBER.sub("", paragraph.text)),
        }:
            log.info("llm_reject", reason="noop_fix", paragraph_id=paragraph.id)
            rejected += 1
            continue
        if _matches_exemplar(paragraph.text, rules):
            log.info("llm_reject", reason="matches_exemplar", paragraph_id=paragraph.id)
            rejected += 1
            continue
        accepted.append((finding, paragraph, rules[finding.rule_ref - 1]))
    return accepted, rejected


class LLMChecker:
    def __init__(
        self,
        client: LLMClient,
        retriever: Retriever | None,
        *,
        batch_size: int = 5,
        rag_top_k: int = 5,
    ) -> None:
        self.client = client
        self.retriever = retriever
        self.batch_size = batch_size
        self.rag_top_k = rag_top_k

    async def run(self, document: Document, profile: Profile) -> LLMRunResult:
        result = LLMRunResult()
        bibliography = profile.bibliography
        entries = document.by_role(ParagraphRole.BIBLIOGRAPHY_ENTRY)
        if bibliography is None or bibliography.checker != "llm":
            return result
        if not entries:
            result.checks.append(
                CheckRun(
                    rule_id=BIBLIOGRAPHY_RULE,
                    checker=Checker.LLM,
                    status=CheckStatus.SKIPPED,
                    detail="в документе нет списка литературы",
                )
            )
            return result
        await self._check_bibliography(entries, profile, result)
        return result

    async def _rules_for(self, query: str, profile: Profile) -> list[RetrievedChunk]:
        if self.retriever is None:
            return []
        return await self.retriever.retrieve(query, sources=profile.rag_sources, k=self.rag_top_k)

    async def _check_bibliography(
        self, entries: list[Paragraph], profile: Profile, result: LLMRunResult
    ) -> None:
        bibliography = profile.bibliography
        assert bibliography is not None  # noqa: S101
        query = (
            "правила оформления библиографической записи в списке использованных источников: "
            + " ".join(e.text for e in entries[:3])
        )
        try:
            rules = await self._rules_for(query, profile)
        except EmbeddingError as exc:
            result.checks.append(_failed(f"RAG недоступен: {exc}"))
            result.notices.append(
                Notice(
                    code="rag_unavailable",
                    level=NoticeLevel.WARNING,
                    message="ИИ-проверка литературы пропущена: недоступен сервис эмбеддингов",
                )
            )
            return
        if not rules:
            result.checks.append(
                CheckRun(
                    rule_id=BIBLIOGRAPHY_RULE,
                    checker=Checker.LLM,
                    status=CheckStatus.SKIPPED,
                    detail="нет текста стандарта в базе знаний (RAG)",
                )
            )
            result.notices.append(
                Notice(
                    code="rag_empty",
                    level=NoticeLevel.WARNING,
                    message="ИИ-проверка списка литературы пропущена: в базе знаний нет текста "
                    "требований для этого профиля (normocontrol rag index …)",
                )
            )
            return

        prompt = load_prompt(BIBLIOGRAPHY_RULE)
        rules_text = "\n".join(
            f"[{i}] {chunk.citation}: {chunk.text}" for i, chunk in enumerate(rules, start=1)
        )
        batches = [
            entries[i : i + self.batch_size] for i in range(0, len(entries), self.batch_size)
        ]

        async def run_batch(batch: list[Paragraph]) -> tuple[list[Issue], int]:
            fragments = "\n".join(f'(paragraph_id={p.id}) "{p.text.strip()}"' for p in batch)
            system, user = prompt.render(rules=rules_text, fragments=fragments)
            raw = await self.client.complete_json(system=system, user=user, schema=FINDINGS_SCHEMA)
            parsed = LLMFindings.model_validate(raw)
            accepted, rejected = validate_findings(parsed.issues, {p.id: p for p in batch}, rules)
            issues = [
                _to_issue(finding, paragraph, chunk, bibliography.severity)
                for finding, paragraph, chunk in accepted
            ]
            return issues, rejected

        try:
            outcomes = await asyncio.gather(*(run_batch(batch) for batch in batches))
        except (LLMError, ValidationError) as exc:
            log.warning("llm_check_failed", rule_id=BIBLIOGRAPHY_RULE, error=str(exc))
            result.checks.append(_failed(str(exc)))
            result.notices.append(
                Notice(
                    code="llm_failed",
                    level=NoticeLevel.WARNING,
                    message="ИИ-проверка списка литературы не выполнена: модель недоступна "
                    "или вернула некорректный ответ",
                )
            )
            return

        issues = [issue for batch_issues, _ in outcomes for issue in batch_issues]
        rejected = sum(count for _, count in outcomes)
        result.issues.extend(issues)
        result.checks.append(
            CheckRun(
                rule_id=BIBLIOGRAPHY_RULE,
                checker=Checker.LLM,
                status=CheckStatus.OK,
                issues=len(issues),
                detail=f"записей: {len(entries)}, отброшено неподтверждённых замечаний: {rejected}",
            )
        )


def _failed(detail: str) -> CheckRun:
    return CheckRun(
        rule_id=BIBLIOGRAPHY_RULE, checker=Checker.LLM, status=CheckStatus.FAILED, detail=detail
    )


def _to_issue(
    finding: LLMFinding, paragraph: Paragraph, chunk: RetrievedChunk, profile_severity: Severity
) -> Issue:
    # ИИ не может повысить серьёзность выше заданной в профиле
    severity = Severity(finding.severity)
    if severity.rank < profile_severity.rank:
        severity = profile_severity
    excerpt = chunk.text if len(chunk.text) <= 400 else chunk.text[:399] + "…"
    return Issue(
        rule_id=BIBLIOGRAPHY_RULE,
        category=Category.BIBLIOGRAPHY,
        severity=severity,
        checker=Checker.LLM,
        message=finding.message,
        fix=finding.fix or None,
        actual=finding.quote,
        reference=chunk.citation,
        reference_quote=excerpt,
        location=Location(
            paragraph_ids=[paragraph.id],
            pages=[paragraph.page_estimate] if paragraph.page_estimate else [],
            quote=finding.quote,
        ),
    )
