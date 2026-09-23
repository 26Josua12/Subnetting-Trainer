from __future__ import annotations

import itertools
import random
from ipaddress import IPv4Address
from pathlib import Path

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.address import HostRangeTask, NetworkTask
from subnet_trainer.core.tasks.base import TaskKind
from subnet_trainer.core.tasks.same_net import SameNetTask
from subnet_trainer.session import Session, random_source
from subnet_trainer.stats.models import Mode, Outcome
from subnet_trainer.ui.modes import run_practice

from helpers import InterruptingReader, fixed_source, make_ctx, store_at

A = IPv4Address
NET = NetworkTask(A("172.16.45.200"), 21)
RANGE = HostRangeTask(A("192.168.1.130"), 25)
SAME = SameNetTask(A("10.1.1.1"), A("10.1.1.5"), 30)


def _session(tmp_path: Path, tasks: list) -> Session:
    return Session(Mode.DRILL, Level.MEDIUM, fixed_source(tasks), store_at(tmp_path), seed=1)


def test_correct_wrong_hint_skip_and_quit(tmp_path: Path) -> None:
    ctx, out = make_ctx(
        [
            " 172.16.40.0 ",  # correct
            "192.168.1.129-192.168.1.253",  # wrong
            "?",  # hint
            "vielleicht",  # parse error -> asked again, not counted
            "nein",  # correct with hint
            "s",  # skip
            "q",
        ]
    )
    session = _session(tmp_path, [NET, RANGE, SAME, NET, RANGE])
    run_practice(ctx, session, count=None)
    text = out.getvalue()

    outcomes = [(r.outcome, r.hint_used) for r in session.records]
    assert outcomes == [
        (Outcome.CORRECT, False),
        (Outcome.WRONG, False),
        (Outcome.CORRECT, True),
        (Outcome.SKIPPED, False),
    ]
    assert session.score == 1.5
    assert "✔ Richtig!" in text
    assert "✘ Leider falsch." in text
    assert "192.168.1.129 - 192.168.1.254" in text  # the correct solution is shown
    assert "256 − 128 = 128" in text  # with an explanation
    assert "Hinweis" in text and "zählt halb" in text
    assert "Bitte mit 'ja' oder 'nein'" in text
    assert "Übersprungen" in text
    assert "Zusammenfassung" in text

    saved = store_at(tmp_path).load()
    assert len(saved.answers) == 4
    assert saved.answers[0].kind == TaskKind.NETWORK
    assert saved.answers[0].prefix == 21
    assert len(saved.sessions) == 1
    assert saved.sessions[0].answered == 4
    assert saved.sessions[0].seed == 1


def test_count_limits_session(tmp_path: Path) -> None:
    ctx, out = make_ctx(["172.16.40.0", "172.16.40.0"])
    session = _session(tmp_path, [NET, NET, NET])
    run_practice(ctx, session, count=2)
    assert session.answered == 2
    assert "Aufgabe 2/2" in out.getvalue()


def test_ctrl_c_saves_and_shows_summary(tmp_path: Path) -> None:
    ctx, out = make_ctx([])
    ctx.read = InterruptingReader(["172.16.40.0"])
    session = _session(tmp_path, [NET, NET])
    run_practice(ctx, session, count=None)  # must not raise
    assert "Abgebrochen" in out.getvalue()
    assert "Zusammenfassung" in out.getvalue()
    saved = store_at(tmp_path).load()
    assert len(saved.answers) == 1 and len(saved.sessions) == 1


def test_eof_behaves_like_quit(tmp_path: Path) -> None:
    ctx, _ = make_ctx(["172.16.40.0"])  # reader raises EOFError afterwards
    session = _session(tmp_path, [NET, NET])
    run_practice(ctx, session, count=None)
    assert session.answered == 1


def test_quit_immediately_stores_nothing(tmp_path: Path) -> None:
    ctx, out = make_ctx(["q"])
    session = _session(tmp_path, [NET])
    run_practice(ctx, session, count=None)
    assert "Keine Aufgaben beantwortet" in out.getvalue()
    assert store_at(tmp_path).load().sessions == []


def test_storage_failure_does_not_crash(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    ctx, out = make_ctx(["172.16.40.0", "q"])
    session = Session(Mode.DRILL, Level.MEDIUM, fixed_source([NET, NET]), store_at(blocker))
    run_practice(ctx, session, count=None)
    assert session.answered == 1
    assert "konnte nicht gespeichert werden" in out.getvalue()


def test_random_source_is_reproducible_and_respects_kinds() -> None:
    kinds = [TaskKind.WILDCARD, TaskKind.SAME_NET]
    first = random_source(random.Random(42), Level.HARD, kinds)
    second = random_source(random.Random(42), Level.HARD, kinds)
    tasks = [first() for _ in range(100)]
    assert tasks == [second() for _ in range(100)]
    assert {t.kind for t in tasks} == set(kinds)
    assert all(a != b for a, b in itertools.pairwise(tasks))
