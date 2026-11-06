"""Отчёт о проверке: модель, агрегатор, вывод в консоль, JSON и .docx с комментариями."""

from normocontrol.report.aggregate import build_report, compute_score, dedupe
from normocontrol.report.model import Category, Checker, Issue, Location, Notice, Report

__all__ = [
    "Category",
    "Checker",
    "Issue",
    "Location",
    "Notice",
    "Report",
    "build_report",
    "compute_score",
    "dedupe",
]
