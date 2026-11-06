"""Настройки приложения.

Источники в порядке приоритета (сильнее → слабее): аргументы конструктора →
переменные окружения ``NC_*`` → ``.env`` → ``config.yaml`` → значения по умолчанию.

Вложенные поля переопределяются через ``__``: ``NC_LLM__MODEL=qwen3:4b``.
Путь к YAML задаётся переменной ``NC_CONFIG_FILE`` (по умолчанию ``./config.yaml``).
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_FILE_ENV = "NC_CONFIG_FILE"
DEFAULT_CONFIG_FILE = Path("config.yaml")


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class LLMProvider(StrEnum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"  # vLLM, llama.cpp server, LM Studio


class LogSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_format: bool = False


class LLMSettings(BaseModel):
    enabled: bool = True
    provider: LLMProvider = LLMProvider.OLLAMA
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:8b"
    api_key: SecretStr | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    num_ctx: int = Field(default=8192, ge=512)
    think: bool = False
    keep_alive: str = "10m"
    timeout_s: float = Field(default=120, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_concurrency: int = Field(default=2, ge=1)
    batch_size: int = Field(default=5, ge=1, le=50)
    # Логи промптов и ответов содержат фрагменты документов (персональные данные) —
    # включать только осознанно, для отладки промптов.
    log_dir: Path | None = None
    cache_size: int = Field(default=2048, ge=0)


class EmbeddingSettings(BaseModel):
    provider: LLMProvider = LLMProvider.OLLAMA
    base_url: str = "http://localhost:11434"
    model: str = "bge-m3"
    api_key: SecretStr | None = None
    # Префиксы нужны e5-моделям (``query: `` / ``passage: ``); для bge-m3 — пустые.
    query_prefix: str = ""
    passage_prefix: str = ""
    batch_size: int = Field(default=16, ge=1)
    timeout_s: float = Field(default=60, gt=0)


class RerankerSettings(BaseModel):
    enabled: bool = False
    model: str = "BAAI/bge-reranker-v2-m3"
    device: str | None = None


class VectorStoreSettings(BaseModel):
    backend: Literal["qdrant"] = "qdrant"
    # ``url`` — сервер Qdrant (прод); иначе встроенный режим с хранением в ``path``.
    url: str | None = None
    api_key: SecretStr | None = None
    path: Path = Path("data/vectors")
    collection: str = "standards"


class RagSettings(BaseModel):
    enabled: bool = True
    top_k: int = Field(default=5, ge=1, le=20)
    candidates: int = Field(default=20, ge=1, le=200)
    min_score: float = Field(default=0.3, ge=-1, le=1)
    max_chunk_tokens: int = Field(default=800, ge=100)
    chunk_overlap_tokens: int = Field(default=80, ge=0)


class PagesSettings(BaseModel):
    """Оценка номеров страниц через конвертацию в PDF (LibreOffice headless)."""

    mode: Literal["auto", "on", "off"] = "auto"
    soffice_path: str = "soffice"
    timeout_s: float = Field(default=90, gt=0)


class JobBackend(StrEnum):
    INLINE = "inline"  # фоновые задачи в процессе API — для разработки и одного узла
    ARQ = "arq"  # очередь в Redis + отдельные воркеры — для продакшена


class JobSettings(BaseModel):
    backend: JobBackend = JobBackend.INLINE
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "normocontrol:checks"
    max_concurrency: int = Field(default=2, ge=1)  # одновременных проверок на процесс/воркер
    max_pending: int = Field(default=100, ge=1)  # больше — API отвечает 503 «очередь заполнена»
    timeout_s: float = Field(default=600, gt=0)
    # сколько хранится отчёт (и .docx с комментариями); исходный файл удаляется сразу
    result_ttl_s: int = Field(default=3600, ge=60)


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)
    root_path: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_upload_mb: float = Field(default=20, gt=0, le=200)
    docs_enabled: bool = True
    metrics_enabled: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NC_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    env: Environment = Environment.DEV
    log: LogSettings = Field(default_factory=LogSettings)
    profiles_dir: Path = Path("profiles")
    default_profile: str = "gost-7.32-2017"
    llm: LLMSettings = Field(default_factory=LLMSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    reranker: RerankerSettings = Field(default_factory=RerankerSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    pages: PagesSettings = Field(default_factory=PagesSettings)
    jobs: JobSettings = Field(default_factory=JobSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    @field_validator("profiles_dir")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = Path(os.environ.get(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE))
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ]
        if yaml_path.is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path))
        return tuple(sources)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный экземпляр настроек процесса."""
    return Settings()
