"""Мутации: внесение в правильный документ известных ошибок.

Мутация = функция ``apply(generated, rng) -> list[Expected]``. Раз ошибку внесли мы сами,
ответ известен точно — из него собирается ``expected_issues.json``.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from normocontrol.dataset.builders import Generated, set_font
from normocontrol.profiles.schema import Profile


@dataclass(slots=True)
class Expected:
    rule_id: str
    elements: list[Any] = field(default_factory=list)  # lxml-элементы абзацев (w:p)


type Apply = Callable[[Generated, random.Random], list[Expected]]
type Applies = Callable[[Generated], bool]


@dataclass(frozen=True, slots=True)
class Mutation:
    name: str
    applies: Applies
    apply: Apply
    # что меняет мутация; мутации с общими «touches» вместе не применяются
    touches: frozenset[str]


MUTATIONS: dict[str, Mutation] = {}


def mutation(
    name: str, *, applies: Applies, touches: tuple[str, ...] = ()
) -> Callable[[Apply], Apply]:
    def decorator(func: Apply) -> Apply:
        MUTATIONS[name] = Mutation(
            name=name, applies=applies, apply=func, touches=frozenset(touches or (name,))
        )
        return func

    return decorator


def _p(paragraph: Any) -> Any:
    return paragraph._p


def _report(generated: Generated) -> bool:
    return bool(generated.anchors.sections)


def _order(generated: Generated) -> bool:
    return "prikazyvayu" in generated.anchors.requisites


def _requisite(item_id: str, *, required: bool = False) -> Applies:
    def applies(generated: Generated) -> bool:
        requisites = generated.profile.requisites
        if not _order(generated) or requisites is None:
            return False
        return any(i.id == item_id and (i.required or not required) for i in requisites.items)

    return applies


def _cfg(attr: str, field_name: str | None = None) -> Applies:
    def applies(generated: Generated) -> bool:
        section = getattr(generated.profile, attr)
        if section is None:
            return False
        return field_name is None or bool(getattr(section, field_name))

    return applies


def _both(*checks: Applies) -> Applies:
    return lambda generated: all(check(generated) for check in checks)


def _sample(rng: random.Random, items: list[Any], low: int = 2, high: int = 5) -> list[Any]:
    count = min(len(items), rng.randint(low, high))
    return rng.sample(items, k=count)


def _remove(paragraph: Any) -> None:
    element = _p(paragraph)
    element.getparent().remove(element)


# ---------------------------------------------------------------------- page


@mutation("margin_left_2cm", applies=_cfg("page", "margins_cm"), touches=("margins",))
def margin_left(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    profile: Profile = generated.profile
    assert profile.page is not None  # noqa: S101
    assert profile.page.margins_cm is not None  # noqa: S101
    expected = profile.page.margins_cm.left
    generated.document.sections[0].left_margin = Cm(max(expected - 1.0, 0.5))
    return [Expected("page.margins")]


@mutation(
    "margin_right_wide",
    applies=lambda g: bool(
        g.profile.page and g.profile.page.margins_cm and g.profile.page.margins_mode == "exact"
    ),
    touches=("margins",),
)
def margin_right(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    page = generated.profile.page
    assert page is not None  # noqa: S101
    assert page.margins_cm is not None  # noqa: S101
    generated.document.sections[0].right_margin = Cm(page.margins_cm.right + 1.0)
    return [Expected("page.margins")]


@mutation(
    "orientation_landscape",
    applies=lambda g: bool(g.profile.page and g.profile.page.orientation == "portrait"),
    touches=("page_geometry",),
)
def orientation(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    section = generated.document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    return [Expected("page.orientation")]


@mutation("paper_letter", applies=_cfg("page"), touches=("page_geometry",))
def paper_letter(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    section = generated.document.sections[0]
    section.page_width, section.page_height = Cm(21.59), Cm(27.94)
    return [Expected("page.size")]


@mutation(
    "no_page_numbers",
    applies=lambda g: bool(_report(g) and g.profile.page and g.profile.page.numbering),
    touches=("numbering",),
)
def no_page_numbers(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    section = generated.document.sections[0]
    for container in (section.footer, section.header):
        for paragraph in container.paragraphs:
            for field_element in list(_p(paragraph).iter("{*}fldSimple")):
                field_element.getparent().remove(field_element)
    return [Expected("page.numbering")]


@mutation(
    "number_on_title_page",
    applies=lambda g: bool(
        _report(g)
        and g.profile.page
        and g.profile.page.numbering
        and not g.profile.page.numbering.title_page_numbered
    ),
    touches=("numbering",),
)
def number_on_title(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    generated.document.sections[0].different_first_page_header_footer = False
    return [Expected("page.numbering")]


# ---------------------------------------------------------------------- text


@mutation("font_family_arial", applies=_cfg("body_text", "font_family"), touches=("font_family",))
def font_family(generated: Generated, rng: random.Random) -> list[Expected]:
    profile = generated.profile
    assert profile.body_text is not None  # noqa: S101
    allowed = {name.casefold() for name in profile.body_text.font_family or []}
    wrong = next(f for f in ("Arial", "Calibri", "Courier New") if f.casefold() not in allowed)
    targets = _sample(rng, generated.anchors.body)
    for paragraph in targets:
        for run in paragraph.runs:
            set_font(run._r, wrong)
    return [Expected("font.family", [_p(p) for p in targets])]


@mutation("font_size_small", applies=_cfg("body_text", "font_size_pt"), touches=("font_size",))
def font_size(generated: Generated, rng: random.Random) -> list[Expected]:
    profile = generated.profile
    assert profile.body_text is not None  # noqa: S101
    assert profile.body_text.font_size_pt is not None  # noqa: S101
    size = profile.body_text.font_size_pt
    wrong = (size.min or size.recommended or 14) - 2
    targets = _sample(rng, generated.anchors.body)
    for paragraph in targets:
        for run in paragraph.runs:
            run.font.size = Pt(wrong)
    return [Expected("font.size", [_p(p) for p in targets])]


@mutation("line_spacing_wrong", applies=_cfg("body_text", "line_spacing"), touches=("spacing",))
def line_spacing(generated: Generated, rng: random.Random) -> list[Expected]:
    profile = generated.profile
    assert profile.body_text is not None  # noqa: S101
    expected = profile.body_text.line_spacing or 1.0
    wrong = 2.0 if expected < 1.5 else 1.0
    targets = _sample(rng, generated.anchors.body)
    for paragraph in targets:
        paragraph.paragraph_format.line_spacing = wrong
    return [Expected("paragraph.line_spacing", [_p(p) for p in targets])]


@mutation("indent_zero", applies=_cfg("body_text", "first_line_indent_cm"), touches=("indent",))
def indent_zero(generated: Generated, rng: random.Random) -> list[Expected]:
    targets = _sample(rng, generated.anchors.body)
    for paragraph in targets:
        paragraph.paragraph_format.first_line_indent = Cm(0)
    return [Expected("paragraph.first_line_indent", [_p(p) for p in targets])]


@mutation("indent_spaces", applies=_cfg("body_text", "first_line_indent_cm"), touches=("indent",))
def indent_spaces(generated: Generated, rng: random.Random) -> list[Expected]:
    targets = _sample(rng, generated.anchors.body, 1, 3)
    for paragraph in targets:
        paragraph.paragraph_format.first_line_indent = Cm(0)
        first = paragraph.runs[0]
        first.text = "      " + first.text
    return [Expected("paragraph.first_line_indent", [_p(p) for p in targets])]


@mutation("alignment_center", applies=_cfg("body_text", "alignment"), touches=("alignment",))
def alignment_center(generated: Generated, rng: random.Random) -> list[Expected]:
    targets = _sample(rng, generated.anchors.body)
    for paragraph in targets:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return [Expected("paragraph.alignment", [_p(p) for p in targets])]


@mutation("dash_paragraphs", applies=_cfg("text", "forbid_dash_paragraphs"))
def dash_paragraphs(generated: Generated, rng: random.Random) -> list[Expected]:
    targets = _sample(rng, generated.anchors.body, 1, 2)
    for paragraph in targets:
        paragraph.runs[0].text = "- " + paragraph.runs[0].text
    return [Expected("text.dash_paragraphs", [_p(p) for p in targets])]


@mutation("placeholder_left", applies=_cfg("text", "forbid_placeholders"))
def placeholder(generated: Generated, rng: random.Random) -> list[Expected]:
    preamble = generated.anchors.requisites.get("prikazyvayu")
    target = rng.choice([p for p in generated.anchors.body if p is not preamble])
    target.add_run(" Ответственный: <ФИО>.")
    return [Expected("text.placeholders", [_p(target)])]


# ---------------------------------------------------------------------- headings


@mutation(
    "heading_trailing_dot",
    applies=_both(_report, lambda g: bool(g.profile.headings and g.profile.headings.section)),
)
def heading_dot(generated: Generated, rng: random.Random) -> list[Expected]:
    target = rng.choice(generated.anchors.sections)
    target.runs[-1].text += "."
    return [Expected("heading.trailing_dot", [_p(target)])]


@mutation(
    "heading_not_bold",
    applies=lambda g: bool(
        _report(g)
        and g.profile.headings
        and g.profile.headings.structural
        and g.profile.headings.structural.bold
    ),
    touches=("conclusion",),
)
def heading_not_bold(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    target = generated.anchors.headings["conclusion"]
    for run in target.runs:
        run.bold = False
    return [Expected("heading.bold", [_p(target)])]


@mutation(
    "heading_uppercase",
    applies=lambda g: bool(
        _report(g)
        and g.profile.headings
        and g.profile.headings.structural
        and g.profile.headings.structural.case == "sentence"
    ),
    touches=("intro_case",),
)
def heading_upper(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    target = generated.anchors.headings["intro"]
    for run in target.runs:
        run.text = run.text.upper()
    return [Expected("heading.case", [_p(target)])]


@mutation(
    "heading_no_new_page",
    applies=lambda g: bool(
        _report(g)
        and g.profile.headings
        and g.profile.headings.structural
        and g.profile.headings.structural.new_page
    ),
    touches=("conclusion",),
)
def heading_no_new_page(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    target = generated.anchors.headings["conclusion"]
    target.paragraph_format.page_break_before = False
    return [Expected("heading.new_page", [_p(target)])]


# ---------------------------------------------------------------------- structure


@mutation(
    "remove_conclusion",
    applies=_both(_report, _cfg("structure", "required_sections")),
    touches=("structure", "conclusion"),
)
def remove_conclusion(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    heading = generated.anchors.headings["conclusion"]
    element = _p(heading)
    following = element.getnext()
    _remove(heading)
    if following is not None and following.tag.endswith("}p"):
        following.getparent().remove(following)
    expected = [Expected("structure.required_sections")]
    if generated.profile.structure and generated.profile.structure.toc_matches_headings:
        expected.append(Expected("structure.toc_matches"))
    return expected


@mutation(
    "swap_intro_conclusion",
    applies=_both(_report, _cfg("structure", "check_order")),
    touches=("structure", "intro"),
)
def swap_sections(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    intro = _p(generated.anchors.headings["intro"])
    conclusion = _p(generated.anchors.headings["conclusion"])
    intro_block = [intro]
    node = intro.getnext()
    while node is not None and node is not _p(generated.anchors.sections[0]):
        intro_block.append(node)
        node = node.getnext()
    bibliography = _p(generated.anchors.headings["bibliography"])
    for element in intro_block:
        bibliography.addprevious(element)
    del conclusion
    expected = [Expected("structure.order", [intro])]
    bibliography_cfg = generated.profile.bibliography
    if bibliography_cfg is not None and bibliography_cfg.order == "appearance":
        # ссылки [1], [2] из введения теперь появляются после [3]…
        expected.append(Expected("bibliography.order"))
    return expected


@mutation(
    "toc_mismatch",
    applies=_both(_report, _cfg("structure", "toc_matches_headings")),
    touches=("structure",),
)
def toc_mismatch(generated: Generated, rng: random.Random) -> list[Expected]:
    target = rng.choice(generated.anchors.toc[1:-2])
    text = target.runs[0].text
    title, page = text.split("\t")
    target.runs[0].text = f"{title} и перспективы\t{page}"
    return [Expected("structure.toc_matches", [_p(target)])]


# ---------------------------------------------------------------------- figures & tables


@mutation("figure_caption_format", applies=_both(_report, _cfg("figures", "caption_pattern")))
def figure_caption_format(generated: Generated, rng: random.Random) -> list[Expected]:
    target = rng.choice(generated.anchors.figure_captions)
    run = target.runs[0]
    run.text = run.text.replace(" – ", ". ", 1)
    return [Expected("figures.caption_format", [_p(target)])]


@mutation(
    "figure_caption_above",
    applies=_both(
        _report, lambda g: bool(g.profile.figures and g.profile.figures.caption_position == "below")
    ),
)
def figure_caption_above(generated: Generated, rng: random.Random) -> list[Expected]:
    index = rng.randrange(len(generated.anchors.figure_captions))
    caption = _p(generated.anchors.figure_captions[index])
    image = _p(generated.anchors.figure_images[index])
    image.addprevious(caption)
    return [Expected("figures.caption_position", [caption])]


@mutation(
    "table_caption_below",
    applies=_both(
        _report, lambda g: bool(g.profile.tables and g.profile.tables.caption_position == "above")
    ),
    touches=("table_caption",),
)
def table_caption_below(generated: Generated, rng: random.Random) -> list[Expected]:
    index = rng.randrange(len(generated.anchors.table_captions))
    caption = _p(generated.anchors.table_captions[index])
    table = generated.anchors.tables[index]._tbl
    table.addnext(caption)
    return [Expected("tables.caption_position", [caption])]


@mutation(
    "table_caption_missing", applies=_both(_report, _cfg("tables")), touches=("table_caption",)
)
def table_caption_missing(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    # последняя подпись: удаление средней сломало бы ещё и сквозную нумерацию
    _remove(generated.anchors.table_captions[-1])
    return [Expected("tables.caption_missing")]


def _drop_reference(paragraph: Any) -> None:
    """«… текст (см. рисунок 2).» → «… текст.»"""
    run = paragraph.runs[0]
    cut = run.text.rfind(" (")
    if cut > 0:
        run.text = run.text[:cut] + "."


@mutation("figure_unreferenced", applies=_both(_report, _cfg("figures", "require_reference")))
def figure_unreferenced(generated: Generated, rng: random.Random) -> list[Expected]:
    index = rng.randrange(len(generated.anchors.figure_refs))
    _drop_reference(generated.anchors.figure_refs[index])
    caption = _p(generated.anchors.figure_captions[index])
    return [Expected("figures.referenced", [caption])]


@mutation(
    "table_unreferenced",
    applies=_both(_report, _cfg("tables", "require_reference")),
    touches=("table_caption",),
)
def table_unreferenced(generated: Generated, rng: random.Random) -> list[Expected]:
    index = rng.randrange(len(generated.anchors.table_refs))
    _drop_reference(generated.anchors.table_refs[index])
    caption = _p(generated.anchors.table_captions[index])
    return [Expected("tables.referenced", [caption])]


# ---------------------------------------------------------------------- bibliography


@mutation(
    "bibliography_uncited",
    applies=_both(_report, _cfg("bibliography", "require_citation_in_text")),
    touches=("citations",),
)
def bibliography_uncited(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    anchors = generated.anchors
    last = len(anchors.bibliography)
    paragraph = anchors.citations[last]
    for run in paragraph.runs:
        run.text = run.text.replace(f" [{last}]", "").replace(f"[{last}]", "")
    return [Expected("bibliography.cited", [_p(anchors.bibliography[last - 1])])]


@mutation(
    "bibliography_unknown_citation",
    applies=_both(_report, _cfg("bibliography", "require_citation_in_text")),
)
def bibliography_unknown(generated: Generated, rng: random.Random) -> list[Expected]:
    target = rng.choice(generated.anchors.body)
    target.add_run(" [99]")
    return [Expected("bibliography.unknown_citation", [_p(target)])]


@mutation(
    "bibliography_order",
    applies=lambda g: bool(
        _report(g) and g.profile.bibliography and g.profile.bibliography.order == "appearance"
    ),
    touches=("citations",),
)
def bibliography_order(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    intro = generated.anchors.citations[1]
    for run in intro.runs:
        run.text = run.text.replace("[1]", "[§]").replace("[2]", "[1]").replace("[§]", "[2]")
    return [Expected("bibliography.order")]


@mutation(
    "bibliography_number_dot",
    applies=lambda g: bool(
        _report(g)
        and g.profile.bibliography
        and g.profile.bibliography.entry_number_trailing_dot is False
    ),
)
def bibliography_dot(generated: Generated, rng: random.Random) -> list[Expected]:
    targets = _sample(rng, generated.anchors.bibliography, 1, 3)
    for paragraph in targets:
        run = paragraph.runs[0]
        number, rest = run.text.split(" ", 1)
        run.text = f"{number}. {rest}"
    return [Expected("bibliography.numbering", [_p(p) for p in targets])]


# ---------------------------------------------------------------------- requisites: приказ


@mutation(
    "order_prikazyvayu_not_bold",
    applies=_requisite("order_prikazyvayu"),
    touches=("prikazyvayu",),
)
def prikazyvayu_not_bold(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    paragraph = generated.anchors.requisites["prikazyvayu"]
    for run in paragraph.runs:
        run.bold = False
    return [Expected("requisites.order_prikazyvayu", [_p(paragraph)])]


@mutation(
    "order_prikazyvayu_lowercase",
    applies=_requisite("order_prikazyvayu"),
    touches=("prikazyvayu",),
)
def prikazyvayu_lowercase(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    paragraph = generated.anchors.requisites["prikazyvayu"]
    paragraph.runs[-1].text = "приказываю:"
    return [Expected("requisites.order_prikazyvayu", [_p(paragraph)])]


@mutation("order_type_missing", applies=_requisite("doc_type_name", required=True))
def order_type_missing(generated: Generated, rng: random.Random) -> list[Expected]:
    del rng
    _remove(generated.anchors.requisites["type"])
    return [Expected("requisites.doc_type_name")]


@mutation("date_format_wrong", applies=_both(_order, _cfg("dates")))
def date_wrong(generated: Generated, rng: random.Random) -> list[Expected]:
    paragraph = generated.anchors.requisites["date"]
    run = paragraph.runs[0]
    wrong = rng.choice(["5.9.2023", "05.09.23", "05/09/2023", "2023-09-05"])
    run.text = run.text.replace("05.09.2023", wrong)
    return [Expected("dates.format", [_p(paragraph)])]


def applicable(generated: Generated) -> list[Mutation]:
    return [m for m in MUTATIONS.values() if m.applies(generated)]


def clone(generated: Generated) -> Generated:
    return copy.deepcopy(generated)
