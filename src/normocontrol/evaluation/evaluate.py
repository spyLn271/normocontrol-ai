"""Оценка качества: прогон по датасету и precision / recall по каждому ``rule_id``.

Единица сравнения — пара (документ, rule_id). Предсказание засчитывается как верное,
если в документе ожидалась ошибка этого правила и (когда ожидание привязано к абзацам)
хотя бы один абзац совпал. Замечания уровня ``info`` не оцениваются.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from normocontrol.dataset.generate import EXPECTED_SUFFIX, Sample
from normocontrol.parser.docx_parser import parse_docx
from normocontrol.profiles.loader import ProfileRegistry
from normocontrol.profiles.schema import Severity
from normocontrol.report.model import Issue
from normocontrol.rules.engine import run_rules


@dataclass(slots=True)
class RuleScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0


@dataclass(slots=True)
class Mismatch:
    sample: str
    rule_id: str
    kind: str  # fp | fn
    detail: str


@dataclass(slots=True)
class Evaluation:
    documents: int = 0
    rules: dict[str, RuleScore] = field(default_factory=lambda: defaultdict(RuleScore))
    mismatches: list[Mismatch] = field(default_factory=list)

    @property
    def total(self) -> RuleScore:
        total = RuleScore()
        for score in self.rules.values():
            total.tp += score.tp
            total.fp += score.fp
            total.fn += score.fn
        return total


def _matches(issue: Issue, paragraph_ids: list[str]) -> bool:
    return not paragraph_ids or bool(set(issue.location.paragraph_ids) & set(paragraph_ids))


def evaluate_sample(
    data: bytes, sample: Sample, registry: ProfileRegistry, result: Evaluation
) -> None:
    profile = registry.get(sample.profile)
    document = parse_docx(data, sample.name)
    predicted = [i for i in run_rules(document, profile).issues if i.severity is not Severity.INFO]
    result.documents += 1

    expected_by_rule: dict[str, list[list[str]]] = defaultdict(list)
    for item in sample.expected:
        expected_by_rule[item.rule_id].append(item.paragraph_ids)
    predicted_by_rule: dict[str, list[Issue]] = defaultdict(list)
    for issue in predicted:
        predicted_by_rule[issue.rule_id].append(issue)

    for rule_id in expected_by_rule.keys() | predicted_by_rule.keys():
        score = result.rules[rule_id]
        expectations = expected_by_rule.get(rule_id, [])
        issues = predicted_by_rule.get(rule_id, [])
        if expectations and issues:
            hit = any(_matches(issue, ids) for ids in expectations for issue in issues)
            if hit:
                score.tp += 1
            else:
                score.fn += 1
                score.fp += 1
                result.mismatches.append(
                    Mismatch(sample.name, rule_id, "fp", "не те абзацы: " + issues[0].message)
                )
        elif expectations:
            score.fn += 1
            result.mismatches.append(
                Mismatch(sample.name, rule_id, "fn", f"мутации: {', '.join(sample.mutations)}")
            )
        elif issues:
            score.fp += 1
            result.mismatches.append(Mismatch(sample.name, rule_id, "fp", issues[0].message))


def evaluate_directory(directory: Path, registry: ProfileRegistry) -> Evaluation:
    result = Evaluation()
    for expected_path in sorted(directory.rglob(f"*{EXPECTED_SUFFIX}")):
        sample = Sample.from_file(expected_path)
        docx_path = expected_path.with_name(
            expected_path.name.removesuffix(EXPECTED_SUFFIX) + ".docx"
        )
        evaluate_sample(docx_path.read_bytes(), sample, registry, result)
    return result


def to_markdown(result: Evaluation, *, title: str = "Оценка качества правил") -> str:
    total = result.total
    lines = [
        f"# {title}",
        "",
        f"Дата: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · документов: {result.documents}",
        "",
        (
            f"**Итого:** precision {total.precision:.3f} · recall {total.recall:.3f} "
            f"(TP {total.tp}, FP {total.fp}, FN {total.fn})"
        ),
        "",
        "| rule_id | precision | recall | TP | FP | FN |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for rule_id in sorted(result.rules):
        score = result.rules[rule_id]
        lines.append(
            f"| `{rule_id}` | {score.precision:.3f} | {score.recall:.3f} "
            f"| {score.tp} | {score.fp} | {score.fn} |"
        )
    if result.mismatches:
        lines += ["", "## Расхождения (первые 50)", ""]
        lines += [
            f"- `{m.sample}` · `{m.rule_id}` · {m.kind}: {m.detail}" for m in result.mismatches[:50]
        ]
    return "\n".join(lines) + "\n"
