"""Единицы измерения OOXML.

* twip (dxa) — 1/20 пункта, 1440 на дюйм → 1 см ≈ 566.93 twips;
* полупункт — размер шрифта ``w:sz`` хранится в полупунктах (28 = 14 pt);
* EMU — English Metric Unit, 360 000 на сантиметр (размеры рисунков);
* интервал ``w:line`` при ``lineRule="auto"`` — в 1/240 строки.
"""

from __future__ import annotations

TWIPS_PER_INCH = 1440
CM_PER_INCH = 2.54
TWIPS_PER_CM = TWIPS_PER_INCH / CM_PER_INCH
TWIPS_PER_PT = 20
EMU_PER_CM = 360_000
LINE_UNITS_PER_LINE = 240


def twips_to_cm(value: float) -> float:
    return round(value / TWIPS_PER_CM, 3)


def cm_to_twips(value: float) -> int:
    return round(value * TWIPS_PER_CM)


def twips_to_pt(value: float) -> float:
    return round(value / TWIPS_PER_PT, 2)


def half_points_to_pt(value: float) -> float:
    return value / 2


def emu_to_cm(value: float) -> float:
    return round(value / EMU_PER_CM, 3)


def line_units_to_multiple(value: float) -> float:
    return round(value / LINE_UNITS_PER_LINE, 3)
