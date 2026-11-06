from __future__ import annotations

from pathlib import Path

import pytest

from normocontrol.config.settings import JobBackend, Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.llm.model == "qwen3:8b"
    assert settings.embeddings.model == "bge-m3"
    assert settings.jobs.backend is JobBackend.INLINE


def test_env_overrides_nested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_LLM__MODEL", "qwen3:4b")
    monkeypatch.setenv("NC_JOBS__BACKEND", "arq")
    monkeypatch.setenv("NC_API__CORS_ORIGINS", '["https://example.kz"]')
    settings = Settings()
    assert settings.llm.model == "qwen3:4b"
    assert settings.jobs.backend is JobBackend.ARQ
    assert settings.api.cors_origins == ["https://example.kz"]


def test_yaml_file_and_env_priority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n  model: gemma3:12b\n  temperature: 0.0\nrag:\n  top_k: 7\n", encoding="utf-8"
    )
    monkeypatch.setenv("NC_CONFIG_FILE", str(config))
    assert Settings().llm.model == "gemma3:12b"
    assert Settings().rag.top_k == 7
    monkeypatch.setenv("NC_LLM__MODEL", "qwen3:4b")
    assert Settings().llm.model == "qwen3:4b"  # переменные окружения сильнее YAML


def test_repository_config_yaml_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("NC_CONFIG_FILE", str(root / "config.yaml"))
    settings = Settings()
    assert settings.llm.model == "qwen3:8b"
    assert settings.profiles_dir == Path("profiles")


def test_invalid_values_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_LLM__TEMPERATURE", "5")
    with pytest.raises(ValueError, match="temperature"):
        Settings()
