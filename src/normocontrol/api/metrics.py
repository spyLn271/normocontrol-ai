"""Метрики Prometheus (``GET /metrics``)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

CHECKS_TOTAL = Counter(
    "normocontrol_checks_total", "Завершённые проверки документов", ["status", "profile"]
)
CHECK_DURATION = Histogram(
    "normocontrol_check_duration_seconds",
    "Длительность проверки документа",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
CHECKS_IN_PROGRESS = Gauge("normocontrol_checks_in_progress", "Проверки в работе")
ISSUES_TOTAL = Counter("normocontrol_issues_total", "Найденные нарушения", ["severity", "checker"])
HTTP_DURATION = Histogram(
    "normocontrol_http_request_duration_seconds",
    "Длительность HTTP-запросов",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
