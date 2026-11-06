from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from normocontrol import __version__
from normocontrol.cli import app
from normocontrol.config.settings import get_settings
from normocontrol.dataset.generate import generate_sample
from normocontrol.profiles.loader import ProfileRegistry

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NC_LLM__ENABLED", "false")
    monkeypatch.setenv("NC_PAGES__MODE", "off")
    monkeypatch.setenv("NC_LOG__LEVEL", "WARNING")
    get_settings.cache_clear()


@pytest.fixture
def sample(tmp_path: Path, registry: ProfileRegistry) -> Path:
    data, _ = generate_sample(registry.get("kru-mi-049-2026"), seed=2, mutations=2)
    path = tmp_path / "work.docx"
    path.write_bytes(data)
    return path


@pytest.fixture
def clean(tmp_path: Path, registry: ProfileRegistry) -> Path:
    data, _ = generate_sample(registry.get("kru-mi-049-2026"), seed=2, mutations=0)
    path = tmp_path / "clean.docx"
    path.write_bytes(data)
    return path


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_profiles_commands() -> None:
    assert "kru-mi-049-2026" in runner.invoke(app, ["profiles", "list"]).stdout
    shown = runner.invoke(app, ["profiles", "show", "kz-order-236-2023"])
    assert shown.exit_code == 0
    assert "ПРИКАЗЫВАЮ" in shown.stdout
    assert runner.invoke(app, ["profiles", "validate"]).exit_code == 0
    assert runner.invoke(app, ["profiles", "show", "missing"]).exit_code == 2


def test_parse_to_file(sample: Path, tmp_path: Path) -> None:
    out = tmp_path / "model.json"
    result = runner.invoke(app, ["parse", str(sample), "-o", str(out)])
    assert result.exit_code == 0, result.output
    model = json.loads(out.read_text(encoding="utf-8"))
    assert model["sections"][0]["paper_size"] == "A4"
    assert model["paragraphs"][0]["id"] == "p-0"


def test_check_json_and_exit_codes(sample: Path, clean: Path, tmp_path: Path) -> None:
    annotated = tmp_path / "annotated.docx"
    result = runner.invoke(
        app,
        [
            "check",
            str(sample),
            "-p",
            "kru-mi-049-2026",
            "--format",
            "json",
            "--annotate",
            str(annotated),
        ],
    )
    report = json.loads(result.stdout)
    assert report["profile"]["id"] == "kru-mi-049-2026"
    assert annotated.stat().st_size > 0
    has_errors = any(i["severity"] == "error" for i in report["issues"])
    assert result.exit_code == (1 if has_errors else 0)
    never = runner.invoke(
        app, ["check", str(sample), "-p", "kru-mi-049-2026", "--fail-on", "never"]
    )
    assert never.exit_code == 0
    assert "Балл соответствия" in never.stdout
    assert runner.invoke(app, ["check", str(clean), "-p", "kru-mi-049-2026"]).exit_code == 0


def test_check_errors(tmp_path: Path, clean: Path) -> None:
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"not a docx")
    assert runner.invoke(app, ["check", str(broken)]).exit_code == 2
    assert runner.invoke(app, ["check", str(clean), "-p", "missing"]).exit_code == 2


def test_dataset_and_eval(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    generated = runner.invoke(
        app, ["dataset", "generate", "--out", str(out), "-p", "kz-order-236-2023", "--count", "8"]
    )
    assert generated.exit_code == 0, generated.output
    assert len(list(out.rglob("*.docx"))) == 8
    markdown = tmp_path / "bench.md"
    evaluated = runner.invoke(
        app, ["eval", str(out), "--out", str(markdown), "--min-precision", "0.95"]
    )
    assert evaluated.exit_code == 0, evaluated.output
    assert "| rule_id |" in markdown.read_text(encoding="utf-8")
