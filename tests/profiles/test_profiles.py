from __future__ import annotations

from pathlib import Path

import pytest

from normocontrol.profiles.loader import ProfileError, ProfileRegistry, deep_merge
from normocontrol.profiles.schema import ProfileStatus, Severity


def write(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.yaml").write_text(text, encoding="utf-8")


def test_repository_profiles_are_valid(registry: ProfileRegistry) -> None:
    assert registry.validate_all() == dict.fromkeys(registry.ids())


def test_every_active_profile_cites_sources(registry: ProfileRegistry) -> None:
    for profile in registry:
        if profile.status is not ProfileStatus.ACTIVE:
            continue
        sections = [
            profile.page,
            profile.body_text,
            profile.text,
            profile.headings,
            profile.structure,
            profile.figures,
            profile.tables,
            profile.bibliography,
            profile.requisites,
            profile.dates,
        ]
        for section in sections:
            if section is not None:
                assert section.source, f"{profile.id}: у раздела нет source"
                assert "TODO" not in section.source


def test_deep_merge_replaces_lists_and_merges_dicts() -> None:
    merged = deep_merge(
        {"page": {"margins": {"left": 3, "right": 1.5}, "size": ["A4"]}, "a": 1},
        {"page": {"margins": {"right": 1.0}, "size": ["A5"]}},
    )
    assert merged == {"page": {"margins": {"left": 3, "right": 1.0}, "size": ["A5"]}, "a": 1}


def test_extends_inherits_and_overrides(registry: ProfileRegistry) -> None:
    order = registry.get("kz-order-236-2023")
    base = registry.get("kz-rules-236-2023")
    assert order.body_text == base.body_text
    assert order.text == base.text
    assert order.requisites is not None
    assert {i.id for i in order.requisites.items} == {"doc_type_name", "order_prikazyvayu"}
    assert order.requisites.severity is Severity.ERROR
    assert order.status is ProfileStatus.ACTIVE


def test_invalid_value_gives_readable_error(tmp_path: Path) -> None:
    write(
        tmp_path,
        "bad",
        "id: bad\ntitle: Bad\npage:\n  margins_cm: {left: три, right: 1, top: 2, bottom: 2}\n",
    )
    with pytest.raises(ProfileError) as info:
        ProfileRegistry.from_directory(tmp_path).get("bad")
    message = str(info.value)
    assert "page.margins_cm.left" in message
    assert "три" in message


def test_unknown_keys_rejected(tmp_path: Path) -> None:
    write(tmp_path, "typo", "id: typo\ntitle: T\nbody_text:\n  font_famly: [Arial]\n")
    with pytest.raises(ProfileError, match="font_famly"):
        ProfileRegistry.from_directory(tmp_path).get("typo")


def test_invalid_regex_rejected(tmp_path: Path) -> None:
    write(tmp_path, "rx", 'id: rx\ntitle: R\nfigures:\n  caption_pattern: "^(Рисунок"\n')
    with pytest.raises(ProfileError, match="регулярное выражение"):
        ProfileRegistry.from_directory(tmp_path).get("rx")


def test_extends_cycle_detected(tmp_path: Path) -> None:
    write(tmp_path, "a", "id: a\ntitle: A\nextends: b\n")
    write(tmp_path, "b", "id: b\ntitle: B\nextends: a\n")
    with pytest.raises(ProfileError, match="Цикл"):
        ProfileRegistry.from_directory(tmp_path).get("a")


def test_missing_parent_and_profile(tmp_path: Path) -> None:
    write(tmp_path, "a", "id: a\ntitle: A\nextends: ghost\n")
    registry = ProfileRegistry.from_directory(tmp_path)
    with pytest.raises(ProfileError, match="ghost"):
        registry.get("a")
    with pytest.raises(ProfileError, match="не найден"):
        registry.get("nothing")


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    write(tmp_path, "one", "id: same\ntitle: 1\n")
    write(tmp_path, "two", "id: same\ntitle: 2\n")
    with pytest.raises(ProfileError, match="дважды"):
        ProfileRegistry.from_directory(tmp_path)


def test_broken_yaml_rejected(tmp_path: Path) -> None:
    write(tmp_path, "broken", "id: [unclosed\n")
    with pytest.raises(ProfileError, match="YAML"):
        ProfileRegistry.from_directory(tmp_path)


def test_font_size_shorthand(tmp_path: Path) -> None:
    write(tmp_path, "s", "id: s\ntitle: S\nbody_text:\n  font_size_pt: 14\n  font_family: Arial\n")
    profile = ProfileRegistry.from_directory(tmp_path).get("s")
    assert profile.body_text is not None
    assert profile.body_text.font_size_pt is not None
    assert (profile.body_text.font_size_pt.min, profile.body_text.font_size_pt.max) == (14, 14)
    assert profile.body_text.font_family == ["Arial"]


def test_abstract_profiles_not_selectable(tmp_path: Path) -> None:
    write(tmp_path, "base", "id: base\ntitle: Base\nabstract: true\n")
    write(tmp_path, "child", "id: child\ntitle: Child\nextends: base\n")
    registry = ProfileRegistry.from_directory(tmp_path)
    assert [p.id for p in registry.selectable()] == ["child"]
