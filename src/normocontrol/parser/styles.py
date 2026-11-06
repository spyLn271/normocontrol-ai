"""Разрешение наследования форматирования.

Итоговое форматирование текста в Word складывается из уровней (слабее → сильнее):

1. ``w:docDefaults`` — значения документа по умолчанию;
2. цепочка стиля абзаца по ``w:basedOn`` (от корня к самому стилю);
3. уровень нумерации списка (``w:numbering`` → ``w:lvl/w:pPr``) — только свойства абзаца;
4. цепочка символьного стиля run'а (``w:rStyle``);
5. прямое форматирование абзаца / run'а.

Свойства-переключатели (жирный, курсив, прописные) между стилем абзаца и символьным
стилем складываются по XOR (ECMA-376, 17.7.3); прямое форматирование задаёт значение явно.
Шрифты темы (``w:asciiTheme="minorHAnsi"``) разрешаются по ``theme1.xml``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace

from normocontrol.parser.units import half_points_to_pt
from normocontrol.parser.xml import (
    Element,
    attr,
    child,
    int_attr,
    iter_children,
    on_off,
)

# Значения, которые Word подставляет, если свойство не задано нигде в иерархии.
WORD_FALLBACK_FONT = "Times New Roman"
WORD_FALLBACK_SIZE_PT = 10.0


@dataclass(frozen=True, slots=True)
class FontSlot:
    """Шрифт для одного диапазона символов: явное имя и/или ссылка на шрифт темы."""

    name: str | None = None
    theme: str | None = None


@dataclass(frozen=True, slots=True)
class RunProps:
    ascii: FontSlot | None = None
    h_ansi: FontSlot | None = None
    size_half_pt: int | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    all_caps: bool | None = None
    hidden: bool | None = None

    def merged(self, over: RunProps) -> RunProps:
        """Наложить ``over`` поверх ``self`` (заданные в ``over`` поля выигрывают)."""
        return _merge(self, over)

    @classmethod
    def from_rpr(cls, rpr: Element | None) -> RunProps:
        if rpr is None:
            return cls()
        fonts = child(rpr, "w:rFonts")
        underline = child(rpr, "w:u")
        underline_value: bool | None = None
        if underline is not None:
            underline_value = (attr(underline, "w:val") or "single") != "none"
        size = int_attr(child(rpr, "w:sz"), "w:val")
        return cls(
            ascii=_font_slot(fonts, "ascii"),
            h_ansi=_font_slot(fonts, "hAnsi"),
            size_half_pt=size,
            bold=on_off(child(rpr, "w:b")),
            italic=on_off(child(rpr, "w:i")),
            underline=underline_value,
            all_caps=on_off(child(rpr, "w:caps")),
            hidden=on_off(child(rpr, "w:vanish")),
        )


@dataclass(frozen=True, slots=True)
class ParaProps:
    alignment: str | None = None
    left_twips: int | None = None
    right_twips: int | None = None
    # абзацный отступ со знаком: firstLine > 0, hanging < 0
    first_line_twips: int | None = None
    line: tuple[int, str] | None = None  # (значение, lineRule)
    before_twips: int | None = None
    after_twips: int | None = None
    before_auto: bool | None = None
    after_auto: bool | None = None
    outline_level: int | None = None
    num_id: int | None = None
    num_level: int | None = None
    page_break_before: bool | None = None

    def merged(self, over: ParaProps) -> ParaProps:
        return _merge(self, over)

    @classmethod
    def from_ppr(cls, ppr: Element | None) -> ParaProps:
        if ppr is None:
            return cls()
        ind = child(ppr, "w:ind")
        spacing = child(ppr, "w:spacing")
        num_pr = child(ppr, "w:numPr")

        first_line: int | None = None
        if ind is not None:
            hanging = int_attr(ind, "w:hanging")
            first = int_attr(ind, "w:firstLine")
            if hanging is not None:
                first_line = -hanging
            elif first is not None:
                first_line = first

        line: tuple[int, str] | None = None
        if spacing is not None and (line_value := int_attr(spacing, "w:line")) is not None:
            line = (line_value, attr(spacing, "w:lineRule") or "auto")

        num_id = num_level = None
        if num_pr is not None:
            num_id = int_attr(child(num_pr, "w:numId"), "w:val")
            num_level = int_attr(child(num_pr, "w:ilvl"), "w:val")

        return cls(
            alignment=attr(child(ppr, "w:jc"), "w:val"),
            left_twips=_first_int(ind, "w:left", "w:start"),
            right_twips=_first_int(ind, "w:right", "w:end"),
            first_line_twips=first_line,
            line=line,
            before_twips=int_attr(spacing, "w:before"),
            after_twips=int_attr(spacing, "w:after"),
            before_auto=on_off_attr(spacing, "w:beforeAutospacing"),
            after_auto=on_off_attr(spacing, "w:afterAutospacing"),
            outline_level=int_attr(child(ppr, "w:outlineLvl"), "w:val"),
            num_id=num_id,
            num_level=num_level,
            page_break_before=on_off(child(ppr, "w:pageBreakBefore")),
        )


@dataclass(frozen=True, slots=True)
class StyleDef:
    style_id: str
    type: str
    name: str | None
    based_on: str | None
    ppr: ParaProps
    rpr: RunProps
    is_default: bool


@dataclass(frozen=True, slots=True)
class NumberingLevel:
    format: str | None
    text: str | None  # шаблон метки, например «%1.» или «%1)»
    ppr: ParaProps


class StyleSheet:
    """Стили, нумерация и тема одного документа с кэшем разрешённых цепочек."""

    def __init__(
        self,
        styles: Element | None,
        numbering: Element | None = None,
        theme: Element | None = None,
    ) -> None:
        self._styles: dict[str, StyleDef] = {}
        self.default_rpr = RunProps()
        self.default_ppr = ParaProps()
        self.default_paragraph_style: str | None = None
        self.default_character_style: str | None = None
        self._theme_fonts = _parse_theme_fonts(theme)
        self._numbering = _parse_numbering(numbering)
        self._para_cache: dict[str | None, tuple[ParaProps, RunProps]] = {}
        self._char_cache: dict[str | None, RunProps] = {}
        if styles is not None:
            self._load(styles)

    # ------------------------------------------------------------------ public API

    def style(self, style_id: str | None) -> StyleDef | None:
        if style_id is None:
            return None
        return self._styles.get(style_id)

    def style_name(self, style_id: str | None) -> str | None:
        style = self.style(style_id or self.default_paragraph_style)
        return style.name if style else None

    def paragraph_style(self, style_id: str | None) -> tuple[ParaProps, RunProps]:
        """Свойства стиля абзаца по всей цепочке basedOn (без docDefaults)."""
        key = style_id if style_id in self._styles else self.default_paragraph_style
        if key not in self._para_cache:
            ppr, rpr = ParaProps(), RunProps()
            for style in self._chain(key):
                ppr = ppr.merged(style.ppr)
                rpr = rpr.merged(style.rpr)
            self._para_cache[key] = (ppr, rpr)
        return self._para_cache[key]

    def character_style(self, style_id: str | None) -> RunProps:
        key = style_id if style_id in self._styles else self.default_character_style
        if key not in self._char_cache:
            rpr = RunProps()
            for style in self._chain(key):
                rpr = rpr.merged(style.rpr)
            self._char_cache[key] = rpr
        return self._char_cache[key]

    def numbering_level(self, num_id: int | None, level: int | None) -> NumberingLevel | None:
        if num_id is None or num_id == 0:
            return None
        return self._numbering.get((num_id, level or 0))

    def resolve_paragraph(self, style_id: str | None, direct: ParaProps) -> ParaProps:
        style_ppr, _ = self.paragraph_style(style_id)
        merged = self.default_ppr.merged(style_ppr)
        num_id = direct.num_id if direct.num_id is not None else merged.num_id
        num_level = direct.num_level if direct.num_level is not None else merged.num_level
        numbering = self.numbering_level(num_id, num_level)
        if numbering is not None:
            merged = merged.merged(numbering.ppr)
        return merged.merged(direct)

    def resolve_run(
        self,
        paragraph_style_id: str | None,
        run_style_id: str | None,
        direct: RunProps,
    ) -> RunProps:
        _, para_rpr = self.paragraph_style(paragraph_style_id)
        char_rpr = self.character_style(run_style_id)
        style_level = para_rpr.merged(char_rpr)
        # Переключатели: XOR между стилем абзаца и символьным стилем.
        style_level = replace(
            style_level,
            bold=_toggle(para_rpr.bold, char_rpr.bold),
            italic=_toggle(para_rpr.italic, char_rpr.italic),
            all_caps=_toggle(para_rpr.all_caps, char_rpr.all_caps),
        )
        return self.default_rpr.merged(style_level).merged(direct)

    def font_name(self, props: RunProps, text: str) -> str:
        """Имя шрифта, которым будет отображён ``text``.

        Кириллица (включая казахские буквы) отображается шрифтом слота ``hAnsi``,
        чистый ASCII — слотом ``ascii``.
        """
        slots = (props.h_ansi, props.ascii) if not text.isascii() else (props.ascii, props.h_ansi)
        for slot in slots:
            name = self._slot_name(slot)
            if name:
                return name
        return WORD_FALLBACK_FONT

    @staticmethod
    def size_pt(props: RunProps) -> float:
        if props.size_half_pt is None:
            return WORD_FALLBACK_SIZE_PT
        return half_points_to_pt(props.size_half_pt)

    # ------------------------------------------------------------------ internals

    def _slot_name(self, slot: FontSlot | None) -> str | None:
        if slot is None:
            return None
        if slot.theme:
            # minorHAnsi, majorAscii, ... → шрифт major/minor из схемы шрифтов темы
            themed = self._theme_fonts.get("major" if slot.theme.startswith("major") else "minor")
            if themed:
                return themed
        return slot.name

    def _chain(self, style_id: str | None) -> list[StyleDef]:
        chain: list[StyleDef] = []
        seen: set[str] = set()
        current = style_id
        while current and current not in seen and current in self._styles:
            seen.add(current)
            style = self._styles[current]
            chain.append(style)
            current = style.based_on
        chain.reverse()
        return chain

    def _load(self, styles: Element) -> None:
        doc_defaults = child(styles, "w:docDefaults")
        if doc_defaults is not None:
            self.default_rpr = RunProps.from_rpr(
                child(child(doc_defaults, "w:rPrDefault"), "w:rPr")
            )
            self.default_ppr = ParaProps.from_ppr(
                child(child(doc_defaults, "w:pPrDefault"), "w:pPr")
            )
        for element in iter_children(styles, "w:style"):
            style_id = attr(element, "w:styleId")
            if not style_id:
                continue
            style_type = attr(element, "w:type") or "paragraph"
            is_default = on_off_attr(element, "w:default") is True
            style = StyleDef(
                style_id=style_id,
                type=style_type,
                name=attr(child(element, "w:name"), "w:val"),
                based_on=attr(child(element, "w:basedOn"), "w:val"),
                ppr=ParaProps.from_ppr(child(element, "w:pPr")),
                rpr=RunProps.from_rpr(child(element, "w:rPr")),
                is_default=is_default,
            )
            self._styles[style_id] = style
            if is_default and style_type == "paragraph":
                self.default_paragraph_style = style_id
            elif is_default and style_type == "character":
                self.default_character_style = style_id


def on_off_attr(element: Element | None, name: str) -> bool | None:
    value = attr(element, name)
    if value is None:
        return None
    return value.lower() not in {"0", "false", "off"}


def _merge[T: (RunProps, ParaProps)](base: T, over: T) -> T:
    changes = {f.name: value for f in fields(over) if (value := getattr(over, f.name)) is not None}
    return replace(base, **changes) if changes else base


def _toggle(paragraph_style: bool | None, character_style: bool | None) -> bool | None:
    if paragraph_style is None:
        return character_style
    if character_style is None:
        return paragraph_style
    return paragraph_style ^ character_style


def _font_slot(fonts: Element | None, slot: str) -> FontSlot | None:
    if fonts is None:
        return None
    name = attr(fonts, f"w:{slot}")
    theme = attr(fonts, f"w:{slot}Theme")
    if name is None and theme is None:
        return None
    return FontSlot(name=name, theme=theme)


def _first_int(element: Element | None, *names: str) -> int | None:
    for name in names:
        value = int_attr(element, name)
        if value is not None:
            return value
    return None


def _parse_theme_fonts(theme: Element | None) -> dict[str, str]:
    """``{"major": "Calibri Light", "minor": "Calibri"}`` из ``a:fontScheme``."""
    result: dict[str, str] = {}
    if theme is None:
        return result
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    for kind in ("major", "minor"):
        latin = theme.find(f".//{a_ns}{kind}Font/{a_ns}latin")
        if latin is not None and latin.get("typeface"):
            result[kind] = str(latin.get("typeface"))
    return result


def _parse_numbering(numbering: Element | None) -> dict[tuple[int, int], NumberingLevel]:
    if numbering is None:
        return {}
    abstract: dict[int, dict[int, NumberingLevel]] = {}
    for element in iter_children(numbering, "w:abstractNum"):
        abstract_id = int_attr(element, "w:abstractNumId")
        if abstract_id is None:
            continue
        abstract[abstract_id] = {
            level: _numbering_level(lvl)
            for lvl in iter_children(element, "w:lvl")
            if (level := int_attr(lvl, "w:ilvl")) is not None
        }

    result: dict[tuple[int, int], NumberingLevel] = {}
    for num in iter_children(numbering, "w:num"):
        num_id = int_attr(num, "w:numId")
        abstract_id = int_attr(child(num, "w:abstractNumId"), "w:val")
        if num_id is None or abstract_id is None:
            continue
        levels = dict(abstract.get(abstract_id, {}))
        for override in iter_children(num, "w:lvlOverride"):
            level_index = int_attr(override, "w:ilvl")
            lvl = child(override, "w:lvl")
            if level_index is not None and lvl is not None:
                levels[level_index] = _numbering_level(lvl)
        for level_index, definition in levels.items():
            result[(num_id, level_index)] = definition
    return result


def _numbering_level(lvl: Element) -> NumberingLevel:
    return NumberingLevel(
        format=attr(child(lvl, "w:numFmt"), "w:val"),
        text=attr(child(lvl, "w:lvlText"), "w:val"),
        ppr=ParaProps.from_ppr(child(lvl, "w:pPr")),
    )


__all__ = [
    "WORD_FALLBACK_FONT",
    "WORD_FALLBACK_SIZE_PT",
    "FontSlot",
    "NumberingLevel",
    "ParaProps",
    "RunProps",
    "StyleDef",
    "StyleSheet",
]
