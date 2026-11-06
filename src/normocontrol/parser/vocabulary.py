"""Словарь распознавания элементов документа на русском и казахском языках."""

from __future__ import annotations

import re
import unicodedata

# Заголовки структурных элементов (без номера). Используются парсером для эвристик:
# определение титульного листа, содержания и списка литературы.
STRUCTURAL_HEADINGS: frozenset[str] = frozenset(
    {
        # ru
        "реферат",
        "аннотация",
        "содержание",
        "оглавление",
        "введение",
        "заключение",
        "выводы",
        "термины и определения",
        "определения",
        "обозначения и сокращения",
        "перечень сокращений и обозначений",
        "перечень сокращений",
        "нормативные ссылки",
        "список исполнителей",
        "список использованных источников",
        "список литературы",
        "список использованной литературы",
        "библиографический список",
        "приложения",
        # kk
        "аңдатпа",
        "андатпа",
        "мазмұны",
        "мазмұн",
        "кіріспе",
        "қорытынды",
        "анықтамалар",
        "белгілеулер мен қысқартулар",
        "нормативтік сілтемелер",
        "пайдаланылған әдебиеттер тізімі",
        "пайдаланылған дереккөздер тізімі",
        "әдебиеттер тізімі",
        "қосымшалар",
    }
)

TOC_HEADINGS: frozenset[str] = frozenset({"содержание", "оглавление", "мазмұны", "мазмұн"})

BIBLIOGRAPHY_HEADINGS: frozenset[str] = frozenset(
    {
        "список использованных источников",
        "список литературы",
        "список использованной литературы",
        "библиографический список",
        "пайдаланылған әдебиеттер тізімі",
        "пайдаланылған дереккөздер тізімі",
        "әдебиеттер тізімі",
    }
)

APPENDIX_RE = re.compile(r"^(приложение|қосымша)(\s+[a-zа-яәғқңөұүһі0-9]{1,3})?\b", re.IGNORECASE)

# «Рисунок 1 – …», «Рис. 2.1», «Сурет 3 – …»
FIGURE_CAPTION_RE = re.compile(r"^\s*(рисунок|рис\.|сурет)\s*\d", re.IGNORECASE)
# «Таблица 1 – …», «Продолжение таблицы 2», «Кесте 1 – …», «1-кестенің жалғасы»
TABLE_CAPTION_RE = re.compile(
    r"^\s*((таблица|кесте)\s*[\dа-яa-z]|продолжение\s+таблицы|окончание\s+таблицы|\d+[-–]\s*кесте)",
    re.IGNORECASE,
)
# Нумерованный заголовок раздела: «1 Анализ», «1.2 Методы», «2.3.1. Итоги»
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+\S")

_LEADING_NUMBER_RE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+")

# Строка оглавления: текст, затем табуляция/точки и номер страницы.
TOC_LINE_RE = re.compile(r"^(?P<title>.+?)[\s.…·_\t]*(?P<page>\d{1,4})\s*$")


def normalize_title(text: str) -> str:
    """Нормализация заголовка: регистр, ё→е, без номера, пунктуации и лишних пробелов."""
    text = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    text = _LEADING_NUMBER_RE.sub("", text, count=1)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def heading_number(text: str) -> str | None:
    match = NUMBERED_HEADING_RE.match(text)
    return match.group(1) if match else None


def is_structural_heading(text: str) -> bool:
    normalized = normalize_title(text)
    return normalized in STRUCTURAL_HEADINGS or bool(APPENDIX_RE.match(normalized))


def is_bibliography_heading(text: str) -> bool:
    return normalize_title(text) in BIBLIOGRAPHY_HEADINGS


def is_toc_heading(text: str) -> bool:
    return normalize_title(text) in TOC_HEADINGS
