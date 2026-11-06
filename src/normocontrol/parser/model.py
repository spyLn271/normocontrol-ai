"""Модель документа — единый формат, с которым работают все проверки.

Модель не зависит от формата файла: парсер ``.docx`` (а позже PDF) заполняет её,
правила читают только её. Все размеры — в сантиметрах и пунктах.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

DOCUMENT_SCHEMA_VERSION = "1.0"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Alignment(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"
    DISTRIBUTE = "distribute"


class Orientation(StrEnum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class LineSpacingRule(StrEnum):
    MULTIPLE = "multiple"  # w:lineRule="auto": значение — множитель строки (1.0, 1.5)
    EXACT = "exact"  # точно N pt
    AT_LEAST = "at_least"  # минимум N pt


class HeadingSource(StrEnum):
    STYLE = "style"
    OUTLINE = "outline"
    HEURISTIC = "heuristic"


class ParagraphRole(StrEnum):
    """Роль абзаца в документе: от неё зависит, какие правила к нему применимы."""

    BODY = "body"
    HEADING = "heading"
    TITLE_PAGE = "title_page"
    TOC = "toc"
    FIGURE_CAPTION = "figure_caption"
    TABLE_CAPTION = "table_caption"
    TABLE_CELL = "table_cell"
    LIST_ITEM = "list_item"
    BIBLIOGRAPHY_ENTRY = "bibliography_entry"
    IMAGE = "image"
    FORMULA = "formula"
    EMPTY = "empty"


class HeaderFooterKind(StrEnum):
    HEADER = "header"
    FOOTER = "footer"


class HeaderFooterVariant(StrEnum):
    DEFAULT = "default"
    FIRST = "first"
    EVEN = "even"


class Font(_Model):
    name: str | None = None
    size_pt: float | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    all_caps: bool = False


class Run(_Model):
    text: str
    font: Font


class LineSpacing(_Model):
    rule: LineSpacingRule
    value: float  # множитель для MULTIPLE, пункты для EXACT / AT_LEAST


class Numbering(_Model):
    num_id: int
    level: int
    format: str | None = None  # decimal, bullet, russianLower, ...
    label: str | None = None  # шаблон метки уровня: «%1.», «%1)», «•»


class Paragraph(_Model):
    id: str
    index: int
    section_index: int
    text: str
    style_id: str | None = None
    style_name: str | None = None
    runs: list[Run] = Field(default_factory=list)
    font: Font = Field(default_factory=Font)
    fonts_used: list[str] = Field(default_factory=list)
    sizes_used: list[float] = Field(default_factory=list)
    alignment: Alignment = Alignment.LEFT
    first_line_indent_cm: float = 0.0  # отрицательное значение — выступ (hanging)
    left_indent_cm: float = 0.0
    right_indent_cm: float = 0.0
    line_spacing: LineSpacing = Field(
        default_factory=lambda: LineSpacing(rule=LineSpacingRule.MULTIPLE, value=1.0)
    )
    space_before_pt: float = 0.0
    space_after_pt: float = 0.0
    page_break_before: bool = False
    contains_page_break: bool = False
    ends_section: bool = False
    outline_level: int | None = None
    is_heading: bool = False
    heading_level: int | None = None
    heading_source: HeadingSource | None = None
    numbering: Numbering | None = None
    in_table: bool = False
    table_id: str | None = None
    has_drawing: bool = False
    has_formula: bool = False
    in_toc_field: bool = False
    role: ParagraphRole = ParagraphRole.BODY
    page_estimate: int | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


class Margins(_Model):
    left_cm: float
    right_cm: float
    top_cm: float
    bottom_cm: float
    gutter_cm: float = 0.0


class Section(_Model):
    index: int
    page_width_cm: float
    page_height_cm: float
    orientation: Orientation
    paper_size: str | None = None  # A4, A5, Letter или None, если формат нестандартный
    margins: Margins
    header_distance_cm: float | None = None
    footer_distance_cm: float | None = None
    title_page: bool = False  # w:titlePg — особый колонтитул первой страницы
    first_paragraph_index: int
    last_paragraph_index: int


class Table(_Model):
    id: str
    index: int
    rows: int
    cols: int
    # индекс последнего абзаца основного текста перед таблицей (-1 — таблица в начале)
    preceding_paragraph_index: int
    following_paragraph_index: int | None = None
    cell_paragraph_ids: list[str] = Field(default_factory=list)


class Image(_Model):
    id: str
    paragraph_id: str
    width_cm: float | None = None
    height_cm: float | None = None
    inline: bool = True


class HeaderFooter(_Model):
    section_index: int
    kind: HeaderFooterKind
    variant: HeaderFooterVariant
    text: str
    has_page_field: bool
    page_field_alignment: Alignment | None = None
    inherited: bool = False  # взят из предыдущего раздела (linked to previous)


class Footnote(_Model):
    id: str
    text: str


class DocumentStats(_Model):
    paragraphs: int
    words: int
    characters: int
    tables: int
    images: int
    pages_estimated: int | None = None
    page_source: str | None = None  # libreoffice | word_render | breaks


class Document(_Model):
    schema_version: str = DOCUMENT_SCHEMA_VERSION
    filename: str | None = None
    sections: list[Section]
    paragraphs: list[Paragraph]
    tables: list[Table] = Field(default_factory=list)
    images: list[Image] = Field(default_factory=list)
    headers_footers: list[HeaderFooter] = Field(default_factory=list)
    footnotes: list[Footnote] = Field(default_factory=list)
    even_and_odd_headers: bool = False
    stats: DocumentStats

    _paragraph_index: dict[str, Paragraph] | None = PrivateAttr(default=None)

    def paragraph(self, paragraph_id: str) -> Paragraph | None:
        return self._index().get(paragraph_id)

    def by_role(self, *roles: ParagraphRole) -> list[Paragraph]:
        return [p for p in self.paragraphs if p.role in roles]

    @property
    def body_paragraphs(self) -> list[Paragraph]:
        """Абзацы основного текста — к ним применяются правила оформления текста."""
        return self.by_role(ParagraphRole.BODY)

    @property
    def headings(self) -> list[Paragraph]:
        return self.by_role(ParagraphRole.HEADING)

    def section_of(self, paragraph: Paragraph) -> Section:
        return self.sections[paragraph.section_index]

    def headers_footers_of(self, section_index: int) -> list[HeaderFooter]:
        return [hf for hf in self.headers_footers if hf.section_index == section_index]

    def _index(self) -> dict[str, Paragraph]:
        if self._paragraph_index is None:
            self._paragraph_index = {p.id: p for p in self.paragraphs}
        return self._paragraph_index
