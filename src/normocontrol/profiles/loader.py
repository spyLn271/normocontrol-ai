"""Загрузка профилей из YAML с наследованием ``extends`` (глубокое слияние словарей)."""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from normocontrol.profiles.schema import Profile


class ProfileError(ValueError):
    """Профиль не найден, содержит ошибки или цикл наследования."""


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Слить словари: вложенные словари — рекурсивно, списки и скаляры — заменяются."""
    result: dict[str, Any] = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def format_validation_error(profile_id: str, error: ValidationError) -> str:
    lines = [f"Профиль «{profile_id}» содержит ошибки:"]
    for item in error.errors(include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "<корень>"
        value = item.get("input")
        shown = f" (значение: {value!r})" if not isinstance(value, dict | list) else ""
        lines.append(f"  • {location}: {item['msg']}{shown}")
    return "\n".join(lines)


class ProfileRegistry:
    """Все профили каталога; разрешённые (с учётом extends) профили кэшируются."""

    def __init__(self, raw: Mapping[str, dict[str, Any]], origins: Mapping[str, Path]) -> None:
        self._raw = dict(raw)
        self._origins = dict(origins)
        self._resolved: dict[str, Profile] = {}

    @classmethod
    def from_directory(cls, directory: Path) -> ProfileRegistry:
        if not directory.is_dir():
            raise ProfileError(f"Каталог профилей не найден: {directory}")
        raw: dict[str, dict[str, Any]] = {}
        origins: dict[str, Path] = {}
        for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
            data = _read_yaml(path)
            profile_id = data.get("id")
            if not isinstance(profile_id, str):
                raise ProfileError(f"{path.name}: не задан строковый id профиля")
            if profile_id in raw:
                raise ProfileError(
                    f"Профиль «{profile_id}» объявлен дважды: {origins[profile_id]} и {path}"
                )
            raw[profile_id] = data
            origins[profile_id] = path
        return cls(raw, origins)

    def __contains__(self, profile_id: object) -> bool:
        return profile_id in self._raw

    def __iter__(self) -> Iterator[Profile]:
        for profile_id in self._raw:
            yield self.get(profile_id)

    def ids(self) -> list[str]:
        return list(self._raw)

    def get(self, profile_id: str) -> Profile:
        if profile_id not in self._resolved:
            data = self._merged(profile_id, ())
            try:
                self._resolved[profile_id] = Profile.model_validate(data)
            except ValidationError as exc:
                raise ProfileError(format_validation_error(profile_id, exc)) from exc
        return self._resolved[profile_id]

    def selectable(self) -> list[Profile]:
        return [profile for profile in self if not profile.abstract]

    def validate_all(self) -> dict[str, str | None]:
        """``{id: None}`` для корректных профилей и ``{id: текст ошибки}`` для остальных."""
        report: dict[str, str | None] = {}
        for profile_id in self._raw:
            try:
                self.get(profile_id)
            except ProfileError as exc:
                report[profile_id] = str(exc)
            else:
                report[profile_id] = None
        return report

    def origin(self, profile_id: str) -> Path | None:
        return self._origins.get(profile_id)

    def _merged(self, profile_id: str, chain: tuple[str, ...]) -> dict[str, Any]:
        if profile_id not in self._raw:
            known = ", ".join(sorted(self._raw)) or "—"
            raise ProfileError(f"Профиль «{profile_id}» не найден. Доступные: {known}")
        if profile_id in chain:
            cycle = " → ".join((*chain, profile_id))
            raise ProfileError(f"Цикл наследования профилей: {cycle}")
        data = self._raw[profile_id]
        parent_id = data.get("extends")
        if not parent_id:
            return copy.deepcopy(data)
        parent = self._merged(str(parent_id), (*chain, profile_id))
        # абстрактность и статус не наследуются: дочерний профиль задаёт их сам
        parent.pop("abstract", None)
        parent.pop("status", None)
        return deep_merge(parent, data)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path.name}: некорректный YAML — {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path.name}: корень профиля должен быть словарём")
    return data
