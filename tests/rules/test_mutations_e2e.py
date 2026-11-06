"""Сквозная проверка правил: каждая мутация ловится своим правилом и только им."""

from __future__ import annotations

import random

import pytest

from normocontrol.dataset.builders import build_document
from normocontrol.dataset.generate import generate_sample
from normocontrol.dataset.mutations import MUTATIONS, applicable
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.profiles.loader import ProfileRegistry
from normocontrol.profiles.schema import Severity
from normocontrol.rules.engine import run_rules

PROFILES = ["kru-mi-049-2026", "gost-7.32-2017", "kz-order-236-2023", "kz-rules-236-2023"]


def _cases(registry: ProfileRegistry) -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for profile_id in PROFILES:
        generated = build_document(registry.get(profile_id), random.Random(0))  # noqa: S311
        cases.extend((profile_id, m.name) for m in applicable(generated))
    return cases


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "mutation_case" in metafunc.fixturenames:
        from tests.conftest import PROFILES_DIR  # noqa: PLC0415

        registry = ProfileRegistry.from_directory(PROFILES_DIR)
        cases = _cases(registry)
        metafunc.parametrize("mutation_case", cases, ids=[f"{p}:{m}" for p, m in cases])


@pytest.mark.parametrize("profile_id", PROFILES)
@pytest.mark.parametrize("language", ["ru", "kk"])
def test_clean_document_has_no_issues(
    registry: ProfileRegistry, profile_id: str, language: str
) -> None:
    profile = registry.get(profile_id)
    data, sample = generate_sample(profile, seed=1, mutations=0, language=language)  # type: ignore[arg-type]
    result = run_rules(parse_docx(data), profile)
    problems = [i for i in result.issues if i.severity is not Severity.INFO]
    assert problems == [], [i.message for i in problems]
    assert not [c for c in result.checks if c.status.value == "failed"]
    assert sample.expected == []


def test_mutation_detected_precisely(
    registry: ProfileRegistry, mutation_case: tuple[str, str]
) -> None:
    profile_id, name = mutation_case
    profile = registry.get(profile_id)
    data, sample = generate_sample(profile, seed=5, mutations=1, only=[name])
    assert sample.mutations == [name]
    issues = [
        i for i in run_rules(parse_docx(data), profile).issues if i.severity is not Severity.INFO
    ]
    predicted = {i.rule_id for i in issues}
    expected = {e.rule_id for e in sample.expected}
    assert predicted == expected, [i.message for i in issues]
    for item in sample.expected:
        if item.paragraph_ids:
            hits = [i for i in issues if i.rule_id == item.rule_id]
            assert any(set(i.location.paragraph_ids) & set(item.paragraph_ids) for i in hits)


def test_every_mutation_is_exercised(registry: ProfileRegistry) -> None:
    covered = {name for _, name in _cases(registry)}
    assert covered == set(MUTATIONS)


def test_generation_is_reproducible(registry: ProfileRegistry) -> None:
    profile = registry.get("kru-mi-049-2026")
    first_data, first = generate_sample(profile, seed=99, mutations=3)
    second_data, second = generate_sample(profile, seed=99, mutations=3)
    assert first == second
    first_text = [p.text for p in parse_docx(first_data).paragraphs]
    assert first_text == [p.text for p in parse_docx(second_data).paragraphs]
