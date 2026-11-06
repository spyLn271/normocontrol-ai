"""Наследование форматирования: docDefaults → basedOn → нумерация → символьный стиль → прямое."""

from __future__ import annotations

import pytest

from normocontrol.parser.styles import (
    WORD_FALLBACK_FONT,
    WORD_FALLBACK_SIZE_PT,
    ParaProps,
    RunProps,
    StyleSheet,
)
from normocontrol.parser.xml import NS, parse_xml

W = NS["w"]


def styles(body: str, defaults: str = "") -> StyleSheet:
    xml = f'<w:styles xmlns:w="{W}">{defaults}{body}</w:styles>'
    return StyleSheet(parse_xml(xml.encode()))


def rpr(inner: str) -> RunProps:
    return RunProps.from_rpr(parse_xml(f'<w:rPr xmlns:w="{W}">{inner}</w:rPr>'.encode()))


def ppr(inner: str) -> ParaProps:
    return ParaProps.from_ppr(parse_xml(f'<w:pPr xmlns:w="{W}">{inner}</w:pPr>'.encode()))


DEFAULTS = (
    "<w:docDefaults><w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
    "</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>"
    '<w:spacing w:after="160" w:line="259" w:lineRule="auto"/>'
    "</w:pPr></w:pPrDefault></w:docDefaults>"
)
NORMAL = (
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
    '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="28"/></w:rPr>'
    '<w:pPr><w:ind w:firstLine="709"/><w:spacing w:line="360" w:lineRule="auto"/>'
    '<w:jc w:val="both"/></w:pPr>'
    "</w:style>"
)


def test_doc_defaults_apply_without_styles() -> None:
    sheet = styles("", DEFAULTS)
    props = sheet.resolve_run(None, None, RunProps())
    assert sheet.font_name(props, "текст") == "Calibri"
    assert sheet.size_pt(props) == 11


def test_word_fallbacks_when_nothing_defined() -> None:
    sheet = styles("")
    props = sheet.resolve_run(None, None, RunProps())
    assert sheet.font_name(props, "a") == WORD_FALLBACK_FONT
    assert sheet.size_pt(props) == WORD_FALLBACK_SIZE_PT


def test_default_paragraph_style_used_when_no_pstyle() -> None:
    sheet = styles(NORMAL, DEFAULTS)
    props = sheet.resolve_run(None, None, RunProps())
    assert sheet.font_name(props, "текст") == "Times New Roman"
    assert sheet.size_pt(props) == 14


def test_paragraph_style_overrides_defaults() -> None:
    sheet = styles(NORMAL, DEFAULTS)
    props = sheet.resolve_paragraph("Normal", ParaProps())
    assert props.first_line_twips == 709
    assert props.line == (360, "auto")
    assert props.after_twips == 160  # из docDefaults: атрибуты w:spacing сливаются по отдельности
    assert props.alignment == "both"


def test_based_on_chain_inherits_and_overrides() -> None:
    sheet = styles(
        NORMAL + '<w:style w:type="paragraph" w:styleId="Child"><w:basedOn w:val="Normal"/>'
        '<w:rPr><w:sz w:val="24"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Grandchild"><w:basedOn w:val="Child"/>'
        "<w:rPr><w:b/></w:rPr></w:style>",
        DEFAULTS,
    )
    props = sheet.resolve_run("Grandchild", None, RunProps())
    assert sheet.size_pt(props) == 12
    assert props.bold is True
    assert sheet.font_name(props, "текст") == "Times New Roman"


def test_based_on_cycle_does_not_hang() -> None:
    sheet = styles(
        '<w:style w:type="paragraph" w:styleId="A"><w:basedOn w:val="B"/>'
        '<w:rPr><w:sz w:val="20"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="B"><w:basedOn w:val="A"/></w:style>'
    )
    assert sheet.size_pt(sheet.resolve_run("A", None, RunProps())) == 10


def test_unknown_style_falls_back_to_default_paragraph_style() -> None:
    sheet = styles(NORMAL, DEFAULTS)
    assert sheet.size_pt(sheet.resolve_run("Missing", None, RunProps())) == 14


def test_character_style_over_paragraph_style() -> None:
    sheet = styles(
        NORMAL + '<w:style w:type="character" w:styleId="Code"><w:rPr>'
        '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/></w:rPr></w:style>',
        DEFAULTS,
    )
    props = sheet.resolve_run("Normal", "Code", RunProps())
    assert sheet.font_name(props, "код") == "Courier New"
    assert sheet.size_pt(props) == 14


def test_direct_formatting_wins() -> None:
    sheet = styles(NORMAL, DEFAULTS)
    props = sheet.resolve_run(
        "Normal", None, rpr('<w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="24"/>')
    )
    assert sheet.font_name(props, "текст") == "Arial"
    assert sheet.size_pt(props) == 12


def test_toggle_xor_between_paragraph_and_character_style() -> None:
    sheet = styles(
        '<w:style w:type="paragraph" w:styleId="Bold"><w:rPr><w:b/></w:rPr></w:style>'
        '<w:style w:type="character" w:styleId="Strong"><w:rPr><w:b/></w:rPr></w:style>'
    )
    assert sheet.resolve_run("Bold", "Strong", RunProps()).bold is False
    assert sheet.resolve_run("Bold", None, RunProps()).bold is True


def test_direct_toggle_is_absolute() -> None:
    sheet = styles('<w:style w:type="paragraph" w:styleId="Bold"><w:rPr><w:b/></w:rPr></w:style>')
    assert sheet.resolve_run("Bold", None, rpr('<w:b w:val="0"/>')).bold is False
    assert sheet.resolve_run("Bold", None, rpr('<w:b w:val="true"/>')).bold is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, True), ("1", True), ("on", True), ("0", False), ("false", False), ("off", False)],
)
def test_on_off_values(value: str | None, expected: bool) -> None:
    attribute = f' w:val="{value}"' if value is not None else ""
    assert rpr(f"<w:i{attribute}/>").italic is expected


def test_cyrillic_uses_hansi_slot() -> None:
    sheet = styles("")
    props = rpr('<w:rFonts w:ascii="Arial" w:hAnsi="Times New Roman"/>')
    assert sheet.font_name(props, "Қазақ тілі") == "Times New Roman"
    assert sheet.font_name(props, "ASCII only") == "Arial"


def test_theme_fonts_resolved() -> None:
    theme = parse_xml(
        b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements>'
        b'<a:fontScheme name="x"><a:majorFont><a:latin typeface="Cambria"/></a:majorFont>'
        b'<a:minorFont><a:latin typeface="Calibri"/></a:minorFont></a:fontScheme>'
        b"</a:themeElements></a:theme>"
    )
    sheet = StyleSheet(None, theme=theme)
    major = rpr('<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi"/>')
    minor = rpr('<w:rFonts w:asciiTheme="minorHAnsi" w:hAnsiTheme="minorHAnsi"/>')
    assert sheet.font_name(major, "заголовок") == "Cambria"
    assert sheet.font_name(minor, "текст") == "Calibri"


def test_explicit_font_at_higher_level_replaces_inherited_theme() -> None:
    theme = parse_xml(
        b'<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:themeElements>'
        b'<a:fontScheme name="x"><a:majorFont><a:latin typeface="Cambria"/></a:majorFont>'
        b'<a:minorFont><a:latin typeface="Calibri"/></a:minorFont></a:fontScheme>'
        b"</a:themeElements></a:theme>"
    )
    xml = (
        f'<w:styles xmlns:w="{W}"><w:style w:type="paragraph" w:styleId="H"><w:rPr>'
        '<w:rFonts w:asciiTheme="majorHAnsi" w:hAnsiTheme="majorHAnsi"/></w:rPr></w:style>'
        "</w:styles>"
    )
    sheet = StyleSheet(parse_xml(xml.encode()), theme=theme)
    props = sheet.resolve_run(
        "H", None, rpr('<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>')
    )
    assert sheet.font_name(props, "текст") == "Times New Roman"


def test_hanging_indent_is_negative_and_replaces_first_line() -> None:
    sheet = styles(NORMAL)
    props = sheet.resolve_paragraph("Normal", ppr('<w:ind w:hanging="360"/>'))
    assert props.first_line_twips == -360


def test_indent_start_end_aliases() -> None:
    props = ppr('<w:ind w:start="567" w:end="283"/>')
    assert (props.left_twips, props.right_twips) == (567, 283)


def test_line_rule_defaults_to_auto() -> None:
    assert ppr('<w:spacing w:line="240"/>').line == (240, "auto")
    assert ppr('<w:spacing w:line="360" w:lineRule="exact"/>').line == (360, "exact")


def test_numbering_indent_between_style_and_direct() -> None:
    numbering = parse_xml(
        f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0">'
        '<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/>'
        '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'.encode()
    )
    sheet = StyleSheet(
        parse_xml(f'<w:styles xmlns:w="{W}">{NORMAL}</w:styles>'.encode()), numbering
    )
    props = sheet.resolve_paragraph(
        "Normal", ppr('<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>')
    )
    assert props.left_twips == 720
    assert props.first_line_twips == -360
    level = sheet.numbering_level(1, 0)
    assert level is not None
    assert (level.format, level.text) == ("decimal", "%1.")
    direct = sheet.resolve_paragraph(
        "Normal", ppr('<w:numPr><w:numId w:val="1"/></w:numPr><w:ind w:firstLine="709"/>')
    )
    assert direct.first_line_twips == 709


def test_numbering_level_override() -> None:
    numbering = parse_xml(
        f'<w:numbering xmlns:w="{W}"><w:abstractNum w:abstractNumId="0">'
        '<w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>'
        '<w:num w:numId="2"><w:abstractNumId w:val="0"/><w:lvlOverride w:ilvl="0">'
        '<w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:lvlOverride></w:num>'
        "</w:numbering>".encode()
    )
    sheet = StyleSheet(None, numbering)
    level = sheet.numbering_level(2, 0)
    assert level is not None
    assert level.format == "decimal"
    assert sheet.numbering_level(0, 0) is None  # numId=0 отменяет нумерацию


def test_outline_level_inherited_from_style() -> None:
    sheet = styles(
        NORMAL + '<w:style w:type="paragraph" w:styleId="H"><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
    )
    assert sheet.resolve_paragraph("H", ParaProps()).outline_level == 1


def test_hidden_and_caps_flags() -> None:
    props = rpr("<w:vanish/><w:caps/>")
    assert props.hidden is True
    assert props.all_caps is True


def test_underline_none_is_false() -> None:
    assert rpr('<w:u w:val="none"/>').underline is False
    assert rpr('<w:u w:val="single"/>').underline is True


def test_style_name_lookup() -> None:
    sheet = styles(
        NORMAL + '<w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/></w:style>'
    )
    assert sheet.style_name("1") == "heading 1"
    assert sheet.style_name(None) == "Normal"
