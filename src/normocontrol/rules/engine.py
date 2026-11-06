"""Запуск всех применимых к профилю правил."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from normocontrol.logs import get_logger
from normocontrol.parser.model import Document
from normocontrol.profiles.schema import Profile
from normocontrol.report.model import Checker, CheckRun, CheckStatus, Issue
from normocontrol.rules.base import RuleContext, RuleSpec, registered_rules

log = get_logger(__name__)

# Модули со встроенными правилами: регистрация происходит при импорте.
BUILTIN_RULE_MODULES = (
    "normocontrol.rules.page",
    "normocontrol.rules.text",
    "normocontrol.rules.headings",
    "normocontrol.rules.requisites",
    "normocontrol.structure.sections",
    "normocontrol.structure.captions",
    "normocontrol.structure.bibliography",
)


def load_builtin_rules() -> list[RuleSpec]:
    for module in BUILTIN_RULE_MODULES:
        importlib.import_module(module)
    return registered_rules()


@dataclass(slots=True)
class EngineResult:
    issues: list[Issue] = field(default_factory=list)
    checks: list[CheckRun] = field(default_factory=list)


def run_rules(
    document: Document,
    profile: Profile,
    *,
    only: set[str] | None = None,
    checkers: set[Checker] | None = None,
) -> EngineResult:
    """Выполнить правила профиля. Ошибка в одном правиле не прерывает проверку."""
    result = EngineResult()
    ctx = RuleContext(document=document, profile=profile)
    for spec in load_builtin_rules():
        if only is not None and spec.rule_id not in only:
            continue
        if checkers is not None and spec.checker not in checkers:
            continue
        if not spec.applies(profile):
            result.checks.append(
                CheckRun(
                    rule_id=spec.rule_id,
                    checker=spec.checker,
                    status=CheckStatus.SKIPPED,
                    detail="требование не задано в профиле",
                )
            )
            continue
        try:
            issues = list(spec.func(ctx))
        except Exception as exc:
            log.exception("rule_failed", rule_id=spec.rule_id)
            result.checks.append(
                CheckRun(
                    rule_id=spec.rule_id,
                    checker=spec.checker,
                    status=CheckStatus.FAILED,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        result.issues.extend(issues)
        result.checks.append(
            CheckRun(
                rule_id=spec.rule_id,
                checker=spec.checker,
                status=CheckStatus.OK,
                issues=len(issues),
            )
        )
    return result
