"""Normocontrol AI — проверка оформления документов по требованиям РК."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("normocontrol")
except PackageNotFoundError:  # pragma: no cover - пакет не установлен (запуск из исходников)
    __version__ = "0.0.0"

__all__ = ["__version__"]
