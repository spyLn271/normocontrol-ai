"""Оценка поиска (RAG) отдельно от системы: Hit@k и MRR на наборе вопросов.

Формат ``tests/rag/questions.yaml``::

    - query: "поля документа на бумажном носителе"
      sources: ["Правила документирования № 236"]   # необязательно
      expected: ["Правила документирования № 236#7"]  # источник#пункт
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from normocontrol.profiles.schema import RagSource
from normocontrol.rag.retriever import Retriever


class Question(BaseModel):
    query: str
    expected: list[str] = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class RetrievalScore:
    questions: int = 0
    hits: int = 0
    reciprocal_ranks: float = 0.0
    misses: list[str] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.questions if self.questions else 0.0

    @property
    def mrr(self) -> float:
        return self.reciprocal_ranks / self.questions if self.questions else 0.0


def load_questions(path: Path) -> list[Question]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [Question.model_validate(item) for item in data]


async def evaluate_retrieval(
    retriever: Retriever, questions: list[Question], *, k: int = 5
) -> RetrievalScore:
    score = RetrievalScore()
    for question in questions:
        sources = [RagSource(source=name) for name in question.sources]
        chunks = await retriever.retrieve(question.query, sources=sources, k=k)
        keys = [f"{chunk.source}#{chunk.clause}" for chunk in chunks]
        score.questions += 1
        rank = next((i for i, key in enumerate(keys, start=1) if key in question.expected), None)
        if rank is None:
            score.misses.append(f"{question.query} → {', '.join(keys[:3]) or 'ничего'}")
            continue
        score.hits += 1
        score.reciprocal_ranks += 1 / rank
    return score
