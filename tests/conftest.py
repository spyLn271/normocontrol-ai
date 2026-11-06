from __future__ import annotations

import io
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import docx
import pytest

from normocontrol.config.settings import (
    LLMSettings,
    LogSettings,
    PagesSettings,
    Settings,
    VectorStoreSettings,
)
from normocontrol.profiles.loader import ProfileRegistry
from normocontrol.profiles.schema import Profile

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Тесты не читают локальные .env / config.yaml разработчика."""
    for key in list(os.environ):
        if key.startswith("NC_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NC_CONFIG_FILE", str(tmp_path / "absent-config.yaml"))
    monkeypatch.chdir(ROOT)


@pytest.fixture(scope="session")
def registry() -> ProfileRegistry:
    return ProfileRegistry.from_directory(PROFILES_DIR)


@pytest.fixture(scope="session")
def kru(registry: ProfileRegistry) -> Profile:
    return registry.get("kru-mi-049-2026")


@pytest.fixture(scope="session")
def gost(registry: ProfileRegistry) -> Profile:
    return registry.get("gost-7.32-2017")


@pytest.fixture(scope="session")
def order(registry: ProfileRegistry) -> Profile:
    return registry.get("kz-order-236-2023")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        llm=LLMSettings(enabled=False),
        pages=PagesSettings(mode="off"),
        vector_store=VectorStoreSettings(path=tmp_path / "vectors"),
        log=LogSettings(level="WARNING"),
    )


def save(document: Any) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def make_docx() -> Callable[[Callable[[Any], None]], bytes]:
    """Собрать .docx из функции, которая наполняет документ python-docx."""

    def build(fill: Callable[[Any], None]) -> bytes:
        document = docx.Document()
        fill(document)
        return save(document)

    return build
