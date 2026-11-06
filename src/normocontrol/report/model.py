"""Формат ошибки и отчёта — общий для всех проверок, CLI, API и фронтенда."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from normocontrol.profiles.schema import Severity

REPORT_SCHEMA_VERSION = "1.0"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Checker(StrEnum):
    RULE = "rule"  # детерминированная проверка кодом
    STRUCTURE = "structure"  # структура документа (разделы, нумерация, ссылки)
    LLM = "llm"  # локальная языковая модель + RAG


class Category(StrEnum):
    PAGE = "page"
    FONT = "font"
    PARAGRAPH = "paragraph"
    TEXT = "text"
    HEADING = "heading"
    STRUCTURE = "structure"
    FIGURES = "figures"
    TABLES = "tables"
    BIBLIOGRAPHY = "bibliography"
    REQUISITES = "requisites"
    OTHER = "other"


CATEGORY_TITLES: dict[Category, str] = {
    Category.PAGE: "Параметры страницы",
    Category.FONT: "Шрифт",
    Category.PARAGRAPH: "Абзацы",
    Category.TEXT: "Текст",
    Category.HEADING: "Заголовки",
    Category.STRUCTURE: "Структура",
    Category.FIGURES: "Рисунки",
    Category.TABLES: "Таблицы",
    Category.BIBLIOGRAPHY: "Список литературы",
    Category.REQUISITES: "Реквизиты",
    Category.OTHER: "Прочее",
}


class Location(_Model):
    paragraph_ids: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)
    section_index: int | None = None
    quote: str | None = None  # фрагмент текста, к которому относится ошибка

    @property
    def paragraph_id(self) -> str | None:
        return self.paragraph_ids[0] if self.paragraph_ids else None


class Issue(_Model):
    rule_id: str
    category: Category
    severity: Severity
    checker: Checker = Checker.RULE
    message: str
    expected: str | None = None
    actual: str | None = None
    fix: str | None = None
    reference: str | None = None  # основание: пункт стандарта / методички
    reference_quote: str | None = None  # цитата основания (из RAG)
    location: Location = Field(default_factory=Location)
    count: int = Field(default=1, ge=1)  # сколько мест сгруппировано в одну ошибку

    @property
    def fingerprint(self) -> tuple[str, tuple[str, ...], int | None, str]:
        return (
            self.rule_id,
            tuple(self.location.paragraph_ids),
            self.location.section_index,
            self.actual or self.message,
        )


class NoticeLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"


class Notice(_Model):
    code: str
    level: NoticeLevel = NoticeLevel.INFO
    message: str


class CheckStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


class CheckRun(_Model):
    rule_id: str
    checker: Checker
    status: CheckStatus
    issues: int = 0
    detail: str | None = None


class DocumentInfo(_Model):
    filename: str | None
    paragraphs: int
    words: int
    tables: int
    images: int
    sections: int
    pages_estimated: int | None = None
    page_source: str | None = None


class ProfileInfo(_Model):
    id: str
    title: str
    status: str
    version: str | None = None


class EngineInfo(_Model):
    version: str
    llm_model: str | None = None
    embedding_model: str | None = None


class Summary(_Model):
    total: int
    by_severity: dict[Severity, int]
    by_category: dict[Category, int]


class Report(_Model):
    schema_version: str = REPORT_SCHEMA_VERSION
    created_at: datetime
    duration_ms: int
    document: DocumentInfo
    profile: ProfileInfo
    engine: EngineInfo
    score: int = Field(ge=0, le=100)
    summary: Summary
    issues: list[Issue]
    notices: list[Notice] = Field(default_factory=list)
    checks: list[CheckRun] = Field(default_factory=list)
