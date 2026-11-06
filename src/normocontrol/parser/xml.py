"""Низкоуровневые помощники для WordprocessingML."""

from __future__ import annotations

from collections.abc import Iterator

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "v": "urn:schemas-microsoft-com:vml",
}

type Element = etree._Element


def qn(tag: str) -> str:
    """``"w:p"`` → ``"{http://...}p"``."""
    prefix, local = tag.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


W_P = qn("w:p")
W_R = qn("w:r")
W_TBL = qn("w:tbl")
W_TR = qn("w:tr")
W_TC = qn("w:tc")
W_SDT = qn("w:sdt")
W_SDT_CONTENT = qn("w:sdtContent")
W_SECT_PR = qn("w:sectPr")
W_P_PR = qn("w:pPr")
W_R_PR = qn("w:rPr")
W_VAL = qn("w:val")


def safe_parser() -> etree.XMLParser:
    """Парсер без внешних сущностей и сети — защита от XXE в загруженных файлах."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
        remove_blank_text=False,
    )


def parse_xml(blob: bytes) -> Element:
    return etree.fromstring(blob, parser=safe_parser())


def local_name(element: Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):  # комментарии и processing instructions
        return ""
    return etree.QName(tag).localname


def attr(element: Element | None, name: str) -> str | None:
    if element is None:
        return None
    value = element.get(qn(name))
    return None if value is None else str(value)


def int_attr(element: Element | None, name: str) -> int | None:
    value = attr(element, name)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def on_off(element: Element | None) -> bool | None:
    """Значение элемента-переключателя (``<w:b/>``, ``<w:b w:val="0"/>``).

    ``None`` — элемент отсутствует (значение не задано на этом уровне).
    """
    if element is None:
        return None
    value = attr(element, "w:val")
    if value is None:
        return True
    return value.lower() not in {"0", "false", "off", "none"}


def child(element: Element | None, tag: str) -> Element | None:
    if element is None:
        return None
    return element.find(qn(tag))


def iter_children(element: Element, tag: str) -> Iterator[Element]:
    yield from element.iterfind(qn(tag))
