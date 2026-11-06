"""Генерация датасета: правильный документ + 0/1/3/5 случайных мутаций, фиксированный seed."""

from __future__ import annotations

import io
import json
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from normocontrol.dataset.builders import Language, build_document
from normocontrol.dataset.mutations import Expected, Mutation, applicable
from normocontrol.parser.blocks import iter_paragraph_blocks, paragraph_id
from normocontrol.profiles.loader import ProfileRegistry
from normocontrol.profiles.schema import Profile

DEFAULT_MUTATION_COUNTS = (0, 1, 3, 5)
EXPECTED_SUFFIX = ".expected.json"


@dataclass(slots=True)
class ExpectedIssue:
    rule_id: str
    paragraph_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Sample:
    name: str
    profile: str
    language: str
    seed: int
    mutations: list[str]
    expected: list[ExpectedIssue]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_file(cls, path: Path) -> Sample:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        data["expected"] = [ExpectedIssue(**item) for item in data["expected"]]
        return cls(**data)


def _choose(mutations: list[Mutation], count: int, rng: random.Random) -> list[Mutation]:
    chosen: list[Mutation] = []
    used: set[str] = set()
    for mutation in rng.sample(mutations, k=len(mutations)):
        if len(chosen) == count:
            break
        if mutation.touches & used:
            continue
        chosen.append(mutation)
        used |= mutation.touches
    return chosen


def generate_sample(
    profile: Profile,
    *,
    seed: int,
    mutations: int,
    language: Language = "ru",
    name: str | None = None,
    only: Sequence[str] | None = None,
) -> tuple[bytes, Sample]:
    rng = random.Random(seed)  # noqa: S311 — воспроизводимость, не криптография
    generated = build_document(profile, rng, language)
    pool = applicable(generated)
    if only is not None:
        pool = [m for m in pool if m.name in only]
    chosen = _choose(pool, mutations, rng) if mutations else []
    raw_expected: list[Expected] = []
    for mutation in chosen:
        raw_expected.extend(mutation.apply(generated, rng))

    body = generated.document.element.body
    ids = {
        id(block.element): paragraph_id(index)
        for index, block in enumerate(iter_paragraph_blocks(body))
    }
    expected = [
        ExpectedIssue(
            rule_id=item.rule_id,
            paragraph_ids=[ids[id(element)] for element in item.elements if id(element) in ids],
        )
        for item in raw_expected
    ]
    buffer = io.BytesIO()
    generated.document.save(buffer)
    sample = Sample(
        name=name or f"{profile.id}-{language}-{seed:05d}",
        profile=profile.id,
        language=language,
        seed=seed,
        mutations=[m.name for m in chosen],
        expected=expected,
    )
    return buffer.getvalue(), sample


def generate_dataset(
    registry: ProfileRegistry,
    out_dir: Path,
    *,
    profiles: Sequence[str],
    count: int,
    seed: int = 42,
    languages: Sequence[Language] = ("ru", "kk"),
    mutation_counts: Sequence[int] = DEFAULT_MUTATION_COUNTS,
) -> list[Sample]:
    """``count`` документов на профиль; число мутаций и язык чередуются по кругу."""
    samples: list[Sample] = []
    for profile_id in profiles:
        profile = registry.get(profile_id)
        target = out_dir / profile_id
        target.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            sample_seed = seed * 100_003 + index
            language = languages[index % len(languages)]
            if profile.requisites is not None:
                language = "ru"  # шаблоны служебных документов пока только на русском
            data, sample = generate_sample(
                profile,
                seed=sample_seed,
                mutations=mutation_counts[index % len(mutation_counts)],
                language=language,
                name=f"{profile_id}-{index:04d}",
            )
            (target / f"{sample.name}.docx").write_bytes(data)
            (target / f"{sample.name}{EXPECTED_SUFFIX}").write_text(
                sample.to_json(), encoding="utf-8"
            )
            samples.append(sample)
    manifest = {
        "seed": seed,
        "profiles": list(profiles),
        "count_per_profile": count,
        "mutation_counts": list(mutation_counts),
        "samples": len(samples),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return samples
