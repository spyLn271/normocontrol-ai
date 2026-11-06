from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from normocontrol.config.settings import RagSettings
from normocontrol.profiles.schema import RagSource
from normocontrol.rag.chunking import _successor, chunk_document, split_sections
from normocontrol.rag.evaluate import Question, evaluate_retrieval
from normocontrol.rag.extract import extract_text, strip_repeated_lines
from normocontrol.rag.indexer import index_registry, index_text
from normocontrol.rag.retriever import Retriever
from normocontrol.rag.store import QdrantStore, point_id
from tests.fakes import HashingEmbedder

STANDARD = """Содержание
1 Область применения .......... 4
2 Общие положения .......... 5
Предисловие
1 РАЗРАБОТАНА отделом методологии
2 ВНЕСЕНА отделом методологии
Глава 1. Область применения
1. Настоящая инструкция содержит требования к оформлению работ.
2. Инструкция обязательна для всех подразделений.
Глава 6. Правила оформления
47. Шрифт – Times New Roman, кегль 14. Поля: правое – 10 мм, левое – 30 мм.
1) первый подпункт;
2) второй подпункт.
48. Опечатки допускается исправлять подчисткой.
49. Заголовки разделов печатают с абзацного отступа без точки в конце.
Приложение И
Образец оформления списка использованных источников
1 Осин А.В. Мультимедиа в образовании. – М., 2024. – 320 с.
"""


def test_successor_logic() -> None:
    assert _successor(None, (1,))
    assert not _successor(None, (7,))
    assert _successor((6, 1), (6, 1, 1))
    assert _successor((6, 1, 3), (6, 2))
    assert _successor((6, 1, 3), (7,))
    assert _successor((47,), (49,))  # пропуск одного номера допустим
    assert not _successor((47,), (3,))
    assert _successor((7,), (1,), restart=True)


def test_sections_follow_clause_numbering() -> None:
    sections = split_sections(STANDARD)
    clauses = [s.clause for s in sections]
    assert "47" in clauses
    assert "48" in clauses
    assert "Приложение И" in clauses
    clause_47 = next(s for s in sections if s.clause == "47")
    assert any("второй подпункт" in line for line in clause_47.lines)  # подпункты внутри пункта
    assert clause_47.parent == "Глава 6. Правила оформления"
    assert not any("...." in line for s in sections for line in s.lines)  # оглавление выкинуто


def test_chunks_have_context_and_unique_ids() -> None:
    chunks = chunk_document(STANDARD, source="МИ", source_id="mi")
    assert len({c.id for c in chunks}) == len(chunks)
    clause = next(c for c in chunks if c.clause == "47")
    assert clause.text.startswith("Глава 6. Правила оформления\n47.")
    appendix = next(c for c in chunks if c.clause == "Приложение И")
    assert appendix.kind == "appendix"


def test_long_clause_split_with_overlap() -> None:
    sentence = "Это предложение про оформление списка литературы по правилам. "
    text = "1. " + sentence * 120
    chunks = chunk_document(text, source="S", source_id="s", max_tokens=200, overlap_tokens=20)
    parts = [c for c in chunks if c.clause == "1"]
    assert len(parts) > 2
    assert all(len(c.text) <= 200 * 3.2 + 80 for c in parts)
    assert len({c.part for c in parts}) == len(parts)


def test_repeated_page_headers_removed() -> None:
    pages = [f"Источник: ИС ПАРАГРАФ\nТекст страницы {i}\n{i}" for i in range(1, 6)]
    cleaned = strip_repeated_lines(pages)
    assert all("ПАРАГРАФ" not in page for page in cleaned)
    assert cleaned[0] == "Текст страницы 1"


def test_extract_txt(tmp_path: Path) -> None:
    path = tmp_path / "rules.txt"
    path.write_text("1. Пункт", encoding="utf-8")
    assert extract_text(path) == "1. Пункт"


async def test_index_search_filter_and_reindex() -> None:
    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    first = await index_text(
        STANDARD, source="МИ 049-2026", source_id="mi", embedder=embedder, store=store
    )
    await index_text(
        "1. Поля документа: левое поле 20 мм, правое поле 10 мм.",
        source="Правила 236",
        source_id="rules",
        embedder=embedder,
        store=store,
    )
    total = await store.count()
    again = await index_text(
        STANDARD, source="МИ 049-2026", source_id="mi", embedder=embedder, store=store
    )
    assert again.chunks == first.chunks
    assert await store.count() == total  # повторная индексация без дублей
    assert await store.sources() == {"МИ 049-2026": first.chunks, "Правила 236": 1}

    retriever = Retriever(embedder, store, RagSettings(min_score=-1, top_k=3))
    hits = await retriever.retrieve(
        "шрифт Times New Roman кегль", sources=[RagSource(source="МИ 049-2026")]
    )
    assert hits
    assert {h.source for h in hits} == {"МИ 049-2026"}
    assert hits[0].clause == "47"
    assert hits[0].citation == "МИ 049-2026, п. 47"

    await store.delete_source("rules")
    assert "Правила 236" not in await store.sources()


async def test_priority_breaks_ties() -> None:
    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    text = "1. Поля документа: левое поле 30 мм."
    await index_text(text, source="ГОСТ", source_id="gost", embedder=embedder, store=store)
    await index_text(text, source="Методичка", source_id="uni", embedder=embedder, store=store)
    retriever = Retriever(embedder, store, RagSettings(min_score=-1))
    hits = await retriever.retrieve(
        "поля документа",
        sources=[RagSource(source="Методичка", priority=1), RagSource(source="ГОСТ", priority=2)],
    )
    assert hits[0].source == "Методичка"


async def test_reranker_reorders() -> None:
    class Reverse:
        def score(self, query: str, texts: Sequence[str]) -> list[float]:
            del query
            return [float(i) for i in range(len(texts))]

    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    await index_text(STANDARD, source="МИ", source_id="mi", embedder=embedder, store=store)
    plain = await Retriever(embedder, store, RagSettings(min_score=-1)).retrieve("шрифт кегль", k=5)
    reranked = await Retriever(embedder, store, RagSettings(min_score=-1), Reverse()).retrieve(
        "шрифт кегль", k=5
    )
    assert plain[0].id != reranked[0].id


async def test_retrieval_metrics() -> None:
    store = QdrantStore.in_memory()
    embedder = HashingEmbedder()
    await index_text(STANDARD, source="МИ", source_id="mi", embedder=embedder, store=store)
    retriever = Retriever(embedder, store, RagSettings(min_score=-1))
    score = await evaluate_retrieval(
        retriever,
        [
            Question(query="шрифт Times New Roman кегль 14", expected=["МИ#47"]),
            Question(query="опечатки подчистка", expected=["МИ#48"]),
            Question(query="совершенно другая тема", expected=["МИ#999"]),
        ],
        k=3,
    )
    assert score.questions == 3
    assert score.hits == 2
    assert 0 < score.mrr <= 2 / 3
    assert len(score.misses) == 1


async def test_index_registry(tmp_path: Path) -> None:
    (tmp_path / "rules.txt").write_text("1. Шрифт Times New Roman.", encoding="utf-8")
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        "- {id: a, title: A, local_file: rules.txt, rag_source: Источник A}\n"
        "- {id: b, title: B, local_file: missing.pdf, rag_source: B}\n"
        "- {id: c, title: C}\n",
        encoding="utf-8",
    )
    store = QdrantStore.in_memory()
    results = await index_registry(
        registry, base_dir=tmp_path, embedder=HashingEmbedder(), store=store
    )
    assert [(r.source, r.chunks, r.error) for r in results] == [("Источник A", 1, None)]


async def test_index_registry_reports_unreadable_files(tmp_path: Path) -> None:
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf")
    (tmp_path / "ok.txt").write_text("1. Шрифт Times New Roman.", encoding="utf-8")
    registry = tmp_path / "sources.yaml"
    registry.write_text(
        "- {id: bad, title: Bad, local_file: broken.pdf, rag_source: Плохой}\n"
        "- {id: good, title: Good, local_file: ok.txt, rag_source: Хороший}\n",
        encoding="utf-8",
    )
    results = await index_registry(
        registry, base_dir=tmp_path, embedder=HashingEmbedder(), store=QdrantStore.in_memory()
    )
    assert results[0].error is not None
    assert "broken.pdf" in results[0].error
    assert (results[1].source, results[1].chunks, results[1].error) == ("Хороший", 1, None)


def test_point_ids_are_deterministic() -> None:
    assert point_id("a#1") == point_id("a#1")
    assert point_id("a#1") != point_id("a#2")
