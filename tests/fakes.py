"""Детерминированные подделки LLM и эмбеддингов для тестов без внешних сервисов."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Callable
from typing import Any

DIMENSION = 64
_WORD = re.compile(r"\w+", re.UNICODE)


def _stem(word: str) -> str:
    return word.casefold()[:5]


class HashingEmbedder:
    """«Мешок основ слов» → вектор: похожие по словам тексты дают близкие векторы."""

    model = "hashing-test"

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * DIMENSION
        for word in _WORD.findall(text):
            digest = hashlib.md5(_stem(word).encode(), usedforsecurity=False).digest()
            vector[digest[0] % DIMENSION] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    async def aclose(self) -> None:
        return None


class FakeLLM:
    """LLM, отвечающая функцией от (system, user)."""

    model = "fake-llm"

    def __init__(self, respond: Callable[[str, str], dict[str, Any]]) -> None:
        self.respond = respond
        self.calls: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        del schema
        self.calls.append(user)
        return self.respond(system, user)

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
