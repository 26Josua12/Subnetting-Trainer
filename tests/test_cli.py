from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from subnet_trainer.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("COLUMNS", "100")
    return tmp_path / "subnet-trainer" / "stats.json"


def test_help_is_german() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for text in ("Aufruf:", "Befehle", "Optionen", "drill", "exam", "speed", "weak", "stats"):
        assert text in result.output
    assert "Usage" not in result.output
    assert "Show this message" not in result.output


def test_invalid_options_are_reported_in_german() -> None:
    result = runner.invoke(app, ["drill", "--level", "extrem"])
    assert result.exit_code == 2
    assert "Unbekanntes Level 'extrem'" in result.output
    result = runner.invoke(app, ["drill", "-t", "netzadresse,quatsch"])
    assert result.exit_code == 2
    assert "Unbekannter Aufgabentyp 'quatsch'" in result.output
    result = runner.invoke(app, ["exam", "--time", "0"])
    assert "--time muss mindestens 1 sein" in result.output


def test_drill_session_is_saved(data_home: Path) -> None:
    result = runner.invoke(app, ["drill", "-n", "2", "--seed", "3", "-t", "maske"], input="s\ns\n")
    assert result.exit_code == 0, result.output
    assert "Seed 3" in result.output
    assert "Zusammenfassung" in result.output
    data = json.loads(data_home.read_text(encoding="utf-8"))
    assert [a["outcome"] for a in data["answers"]] == ["skipped", "skipped"]
    assert data["sessions"][0]["seed"] == 3


def test_seed_makes_sessions_reproducible() -> None:
    first = runner.invoke(
        app, ["drill", "-n", "3", "--seed", "99", "-l", "schwer"], input="s\n" * 3
    )
    second = runner.invoke(
        app, ["drill", "-n", "3", "--seed", "99", "-l", "schwer"], input="s\n" * 3
    )
    assert first.output == second.output


def test_default_command_is_drill() -> None:
    result = runner.invoke(app, [], input="q\n")
    assert result.exit_code == 0
    assert "Drill" in result.output


def test_ipv6_mode() -> None:
    result = runner.invoke(app, ["ipv6", "-n", "1", "--seed", "1"], input="s\n")
    assert result.exit_code == 0
    assert "IPv6" in result.output


def test_stats_and_reset(data_home: Path) -> None:
    result = runner.invoke(app, ["stats"])
    assert "Noch keine Statistik" in result.output

    runner.invoke(app, ["drill", "-n", "2", "--seed", "1"], input="s\ns\n")
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    for text in ("Überblick", "Nach Aufgabentyp", "Letzte Sessions", "Highscores"):
        assert text in result.output

    result = runner.invoke(app, ["reset"], input="nein\n")
    assert "Nichts gelöscht" in result.output
    assert data_home.exists()
    result = runner.invoke(app, ["reset"], input="vielleicht\nja\n")
    assert "Statistik gelöscht" in result.output
    assert not data_home.exists()
    result = runner.invoke(app, ["reset", "--yes"])
    assert "keine Statistik" in result.output


def test_weak_mode_shows_focus(data_home: Path) -> None:
    runner.invoke(app, ["drill", "-n", "5", "--seed", "1", "-l", "leicht"], input="s\n" * 5)
    result = runner.invoke(app, ["weak", "-l", "leicht", "-n", "1", "--seed", "2"], input="s\n")
    assert result.exit_code == 0
    assert "Fokus:" in result.output
