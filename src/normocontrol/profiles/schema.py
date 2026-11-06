"""Схема профиля требований (YAML → Pydantic).

Каждый раздел профиля несёт ``severity`` и ``source`` — пункт официального документа,
на котором основано требование. Раздел, которого нет в профиле, не проверяется.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class Severity(StrEnum):
    ERROR = "error"  # документ точно вернут
    WARNING = "warning"  # желательно исправить
    INFO = "info"  # рекомендация

    @property
    def rank(self) -> int:
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class ProfileStatus(StrEnum):
    DRAFT = "draft"  # значения не сверены с официальным текстом
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _RuleSection(_Strict):
    severity: Severity = Severity.ERROR
    source: str | None = None


def _regex(value: str) -> str:
    try:
        re.compile(value)
    except re.error as exc:
        raise ValueError(f"некорректное регулярное выражение: {exc}") from exc
    return value


Regex = Annotated[str, BeforeValidator(_regex)]
PaperSize = Literal["A3", "A4", "A5", "Letter", "Legal"]
AlignmentName = Literal["left", "center", "right", "justify"]
Case = Literal["upper", "sentence", "capitalized", "upper_or_sentence", "any"]
Cm = Annotated[float, Field(ge=0, le=15)]
DateFormat = Literal["numeric", "verbal"]
Language = Literal["ru", "kk", "en"]


# ---------------------------------------------------------------------- page


class Margins(_Strict):
    left: Cm
    right: Cm
    top: Cm
    bottom: Cm


class PageNumbering(_Strict):
    required: bool = True
    position: Literal[
        "bottom-center", "bottom-right", "bottom-left", "top-center", "top-right", "top-left"
    ] = "bottom-center"
    arabic: bool = True
    # Номер на первой странице (титульный лист / первый лист документа)
    title_page_numbered: bool = False


class PageConfig(_RuleSection):
    size: list[PaperSize] = Field(default_factory=lambda: list[PaperSize](["A4"]))
    orientation: Literal["portrait", "landscape", "any"] = "portrait"
    margins_cm: Margins | None = None
    # exact — поля равны заданным (± tolerance); min — «не менее»
    margins_mode: Literal["exact", "min"] = "exact"
    tolerance_cm: float = Field(default=0.1, ge=0, le=2)
    numbering: PageNumbering | None = None

    @field_validator("size", mode="before")
    @classmethod
    def _size_list(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


# ---------------------------------------------------------------------- text


class FontSize(_Strict):
    min: float | None = Field(default=None, gt=0, le=72)
    max: float | None = Field(default=None, gt=0, le=72)
    recommended: float | None = Field(default=None, gt=0, le=72)

    @model_validator(mode="before")
    @classmethod
    def _from_number(cls, value: object) -> object:
        if isinstance(value, int | float):  # «font_size_pt: 14» — ровно 14
            return {"min": value, "max": value}
        return value

    @model_validator(mode="after")
    def _check(self) -> FontSize:
        if self.min is None and self.max is None and self.recommended is None:
            raise ValueError("укажите min, max или recommended")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min не может быть больше max")
        return self


class BodyTextConfig(_RuleSection):
    font_family: list[str] | None = None
    font_size_pt: FontSize | None = None
    line_spacing: float | None = Field(default=None, gt=0, le=4)
    line_spacing_tolerance: float = Field(default=0.05, ge=0, le=1)
    first_line_indent_cm: float | None = Field(default=None, ge=0, le=5)
    indent_tolerance_cm: float = Field(default=0.1, ge=0, le=2)
    alignment: AlignmentName | None = None

    @field_validator("font_family", mode="before")
    @classmethod
    def _family_list(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


class TextConfig(_RuleSection):
    """Требования к тексту, не связанные со шрифтом."""

    forbid_dash_paragraphs: bool = False
    forbid_double_spaces: bool = False
    max_consecutive_empty_paragraphs: int | None = Field(default=None, ge=0)
    forbid_placeholders: bool = False


# ---------------------------------------------------------------------- headings


class HeadingRule(_Strict):
    case: Case = "any"
    trailing_dot: bool | None = False
    bold: bool | None = None
    underline: bool | None = False
    alignment: AlignmentName | None = None
    # first_line — с абзацного отступа; none — от левого поля без отступа
    indent: Literal["first_line", "none"] | None = None
    new_page: bool | None = None
    number_trailing_dot: bool | None = None  # «1.» vs «1»


class HeadingsConfig(_RuleSection):
    section: HeadingRule | None = None  # нумерованные разделы 1-го уровня
    subsection: HeadingRule | None = None  # подразделы и пункты (1.1, 1.1.1)
    structural: HeadingRule | None = None  # «Введение», «Заключение», …


# ---------------------------------------------------------------------- structure


class RequiredSection(_Strict):
    name: str
    aliases: list[str] = Field(default_factory=list)
    optional: bool = False
    # «Основная часть» — любой нумерованный раздел между соседними обязательными
    any_heading: bool = False
    # «Титульный лист» распознаётся не по заголовку, а по структуре документа
    kind: Literal["heading", "title_page"] = "heading"


class StructureConfig(_RuleSection):
    required_sections: list[RequiredSection] = Field(default_factory=list)
    check_order: bool = True
    toc_matches_headings: bool = False
    fuzzy_threshold: float = Field(default=85, ge=50, le=100)


# ---------------------------------------------------------------------- captions


class CaptionConfig(_RuleSection):
    severity: Severity = Severity.WARNING
    caption_pattern: Regex | None = None
    caption_position: Literal["above", "below"] | None = None
    caption_alignment: AlignmentName | None = None
    caption_indent: Literal["first_line", "none"] | None = None
    numbering: Literal["continuous", "per_section", "any"] = "any"
    require_reference: bool = False


# ---------------------------------------------------------------------- bibliography


class BibliographyConfig(_RuleSection):
    severity: Severity = Severity.WARNING
    standard: str | None = None
    checker: Literal["rule", "llm"] = "rule"
    require_citation_in_text: bool = False
    citation_style: Literal["square_brackets"] = "square_brackets"
    order: Literal["appearance", "alphabetical", "any"] = "any"
    entry_number_trailing_dot: bool | None = None  # «1 Иванов» vs «1. Иванов»


# ---------------------------------------------------------------------- requisites


class Requisite(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z0-9_.-]+$")]
    name: str
    pattern: Regex
    required: bool = False
    uppercase: bool | None = None
    bold: bool | None = None
    alignment: AlignmentName | None = None
    single_line: bool = False
    source: str | None = None


class RequisitesConfig(_RuleSection):
    items: list[Requisite] = Field(default_factory=list)


class DatesConfig(_RuleSection):
    severity: Severity = Severity.WARNING
    # numeric — «05.09.2023»; verbal — «5 сентября 2023 года»
    formats: list[DateFormat] = Field(default_factory=lambda: list[DateFormat](["numeric"]))


# ---------------------------------------------------------------------- profile


class RagSource(_Strict):
    source: str
    priority: int = Field(default=1, ge=1, le=10)


class Profile(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")]
    title: str
    status: ProfileStatus = ProfileStatus.DRAFT
    version: str | None = None
    extends: str | None = None
    description: str | None = None
    jurisdiction: str = "KZ"
    doc_types: list[str] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=lambda: list[Language](["ru", "kk"]))
    abstract: bool = False  # базовый профиль, не показывается пользователю для выбора

    page: PageConfig | None = None
    body_text: BodyTextConfig | None = None
    text: TextConfig | None = None
    headings: HeadingsConfig | None = None
    structure: StructureConfig | None = None
    figures: CaptionConfig | None = None
    tables: CaptionConfig | None = None
    bibliography: BibliographyConfig | None = None
    requisites: RequisitesConfig | None = None
    dates: DatesConfig | None = None
    rag_sources: list[RagSource] = Field(default_factory=list)

    @property
    def is_draft(self) -> bool:
        return self.status is ProfileStatus.DRAFT
