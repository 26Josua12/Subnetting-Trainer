from __future__ import annotations

import random
from ipaddress import IPv4Address
from pathlib import Path

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.address import NetworkTask
from subnet_trainer.core.tasks.masks import PrefixToMaskTask
from subnet_trainer.session import Session
from subnet_trainer.stats.analysis import WeakSource
from subnet_trainer.stats.models import Mode, Outcome
from subnet_trainer.ui.modes import run_exam, run_practice, run_speed

from helpers import InterruptingReader, fixed_source, make_ctx, store_at

A = IPv4Address
NET = NetworkTask(A("172.16.45.200"), 21)  # -> 172.16.40.0
MASK = PrefixToMaskTask(26)  # -> 255.255.255.192


def _session(tmp_path: Path, mode: Mode, tasks: list, level: Level = Level.MEDIUM) -> Session:
    return Session(mode, level, fixed_source(tasks), store_at(tmp_path), seed=7)


# --- exam ----------------------------------------------------------------------------------


def test_exam_hides_feedback_until_the_end(tmp_path: Path) -> None:
    ctx, out = make_ctx(
        [
            "?",  # no hints in the exam
            "172.16.40.0",  # correct
            "255.255.255.128",  # wrong
            "<TIMEOUT>",
            "s",
            "ja",  # show explanations
        ]
    )
    session = _session(tmp_path, Mode.EXAM, [NET, MASK, NET, MASK])
    run_exam(ctx, session, count=4, time_limit=60)
    text = out.getvalue()

    assert [r.outcome for r in session.records] == [
        Outcome.CORRECT,
        Outcome.WRONG,
        Outcome.TIMEOUT,
        Outcome.SKIPPED,
    ]
    assert not any(r.hint_used for r in session.records)
    assert "keine Hinweise" in text
    # No immediate right/wrong feedback during the exam ...
    during, report = text.rsplit("Auswertung", 1)
    assert "Leider falsch" not in during
    assert "255.255.255.192" not in during
    # ... but a full report at the end.
    assert "1 von 4" in report and "25 %" in report
    assert "255.255.255.192" in report
    assert "Zeit abgelaufen" in text
    # Explanations for the three non-correct answers were shown.
    assert text.count("So rechnest du es") == 3
    assert store_at(tmp_path).load().sessions[0].mode is Mode.EXAM


def test_exam_prompt_shows_remaining_time(tmp_path: Path) -> None:
    ctx, _ = make_ctx(["172.16.40.0", "nein"])
    run_exam(ctx, _session(tmp_path, Mode.EXAM, [NET]), count=1, time_limit=45)
    assert "⏱ 45 s" in ctx.read.prompts[0]  # type: ignore[attr-defined]


def test_exam_expired_deadline_counts_as_timeout(tmp_path: Path) -> None:
    ctx, _ = make_ctx(["172.16.40.0"])
    session = _session(tmp_path, Mode.EXAM, [NET])
    # A deadline in the past: the scripted reader behaves like a timed-out terminal.
    run_exam(ctx, session, count=1, time_limit=-1)
    assert session.records[0].outcome is Outcome.TIMEOUT


def test_exam_quit_and_ctrl_c(tmp_path: Path) -> None:
    ctx, out = make_ctx(["172.16.40.0", "q"])
    session = _session(tmp_path, Mode.EXAM, [NET, NET, NET])
    run_exam(ctx, session, count=3, time_limit=60)
    assert session.answered == 1
    assert "2 Fragen nicht beantwortet" in out.getvalue()

    ctx, out = make_ctx([])
    ctx.read = InterruptingReader(["172.16.40.0"])
    session = _session(tmp_path, Mode.EXAM, [NET, NET])
    run_exam(ctx, session, count=2, time_limit=60)
    assert "Abgebrochen" in out.getvalue()
    assert "So rechnest du es" not in out.getvalue()  # no review prompt after Ctrl+C


# --- speed ---------------------------------------------------------------------------------


def test_speed_counts_and_saves_highscore(tmp_path: Path) -> None:
    ctx, out = make_ctx(["", "172.16.40.0", "255.255.255.128", "172.16.40.0", "<TIMEOUT>"])
    session = _session(tmp_path, Mode.SPEED, [NET, MASK, NET, MASK])
    run_speed(ctx, session, duration=60)
    text = out.getvalue()
    # The question interrupted by the timer is not recorded.
    assert [r.outcome for r in session.records] == [
        Outcome.CORRECT,
        Outcome.WRONG,
        Outcome.CORRECT,
    ]
    assert "Richtig wäre: 255.255.255.192" in text
    assert "Neuer Highscore" in text
    assert store_at(tmp_path).highscore(Mode.SPEED, "mittel").score == 2  # type: ignore[union-attr]

    # A worse run keeps the old highscore.
    ctx, out = make_ctx(["", "172.16.40.0", "<TIMEOUT>"])
    run_speed(ctx, _session(tmp_path, Mode.SPEED, [NET, NET]), duration=60)
    assert "Neuer Highscore" not in out.getvalue()
    assert "Highscore: 2" in out.getvalue()
    assert store_at(tmp_path).highscore(Mode.SPEED, "mittel").score == 2  # type: ignore[union-attr]


def test_speed_abort_is_not_ranked(tmp_path: Path) -> None:
    ctx, out = make_ctx(["", "172.16.40.0", "172.16.40.0", "q"])
    run_speed(ctx, _session(tmp_path, Mode.SPEED, [NET, NET, NET]), duration=60)
    assert "Nicht gewertet" in out.getvalue()
    assert store_at(tmp_path).highscore(Mode.SPEED, "mittel") is None


def test_speed_no_hints(tmp_path: Path) -> None:
    ctx, out = make_ctx(["", "?", "172.16.40.0", "<TIMEOUT>"])
    session = _session(tmp_path, Mode.SPEED, [NET, NET])
    run_speed(ctx, session, duration=60)
    assert "keine Hinweise" in out.getvalue()
    assert session.records[0].hint_used is False


# --- weak ----------------------------------------------------------------------------------


def test_weak_mode_runs_with_empty_history(tmp_path: Path) -> None:
    ctx, _ = make_ctx(["s", "s", "q"])
    session = Session(Mode.WEAK, Level.EASY, lambda: NET, store_at(tmp_path), seed=1)
    session.source = WeakSource(random.Random(1), Level.EASY, [], session.records)
    run_practice(ctx, session, count=None)
    assert session.answered == 2
    assert all(r.mode is Mode.WEAK for r in session.records)
