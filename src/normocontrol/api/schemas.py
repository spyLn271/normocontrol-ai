"""Модели API: состояние проверки и описание профилей."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from normocontrol.pipeline import STEP_TITLES, CheckStep
from normocontrol.profiles.schema import Profile, RagSource
from normocontrol.report.model import Report


class CheckState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    EXPIRED = "expired"


class StepState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    SKIPPED = "skipped"


class ErrorInfo(BaseModel):
    code: str
    message: str


class CheckRecord(BaseModel):
    """То, что хранится в репозитории (Redis / память) на время жизни результата."""

    model_config = ConfigDict(extra="ignore")

    id: str
    status: CheckState = CheckState.QUEUED
    step: CheckStep | None = None
    completed_steps: list[CheckStep] = Field(default_factory=list)
    filename: str | None = None
    profile_id: str
    annotate: bool = False
    use_llm: bool | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: ErrorInfo | None = None
    report: Report | None = None
    has_annotated: bool = False


class StepView(BaseModel):
    id: CheckStep
    title: str
    state: StepState


class CheckStatus(BaseModel):
    id: str
    status: CheckState
    step: CheckStep | None
    steps: list[StepView]
    filename: str | None
    profile_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    error: ErrorInfo | None
    report: Report | None
    annotated_url: str | None

    @classmethod
    def from_record(cls, record: CheckRecord, *, prefix: str = "/api") -> CheckStatus:
        steps: list[StepView] = []
        for step in CheckStep:
            if step in record.completed_steps:
                state = StepState.DONE
            elif record.step is step and record.status is CheckState.RUNNING:
                state = StepState.ACTIVE
            elif record.status in {CheckState.DONE, CheckState.FAILED}:
                state = StepState.SKIPPED
            else:
                state = StepState.PENDING
            steps.append(StepView(id=step, title=STEP_TITLES[step], state=state))
        return cls(
            id=record.id,
            status=record.status,
            step=record.step,
            steps=steps,
            filename=record.filename,
            profile_id=record.profile_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            expires_at=record.expires_at,
            error=record.error,
            report=record.report,
            annotated_url=(
                f"{prefix}/checks/{record.id}/annotated.docx" if record.has_annotated else None
            ),
        )


class ProfileSummary(BaseModel):
    id: str
    title: str
    status: str
    version: str | None
    description: str | None
    doc_types: list[str]
    languages: list[str]
    rag_sources: list[RagSource]

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileSummary:
        return cls(
            id=profile.id,
            title=profile.title,
            status=profile.status.value,
            version=profile.version,
            description=profile.description,
            doc_types=profile.doc_types,
            languages=list(profile.languages),
            rag_sources=profile.rag_sources,
        )


class Health(BaseModel):
    status: str
    version: str
    components: dict[str, str] = Field(default_factory=dict)
