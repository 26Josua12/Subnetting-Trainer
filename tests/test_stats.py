from __future__ import annotations

import json
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import TaskKind
from subnet_trainer.stats import store as store_module
from subnet_trainer.stats.analysis import (
    WeakSource,
    aggregate,
    bucket_of,
    producible_buckets,
    total,
    weak_spots,
    weakness_cells,
)
from subnet_trainer.stats.models import (
    AnswerRecord,
    Highscore,
    Mode,
    Outcome,
    SessionRecord,
    StatsData,
    answer_score,
)
from subnet_trainer.stats.store import StatsStore, data_dir

NOW = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)


def record(
    kind: TaskKind = TaskKind.NETWORK,
    prefix: int | None = 24,
    outcome: Outcome = Outcome.CORRECT,
    *,
    hint: bool = False,
    days_ago: float = 0,
    seconds: float = 5.0,
) -> AnswerRecord:
    return AnswerRecord(
        timestamp=(NOW - timedelta(days=days_ago)).isoformat(timespec="seconds"),
        kind=kind.value,
        variant="v",
        level=Level.MEDIUM.value,
        prefix=prefix,
        outcome=outcome,
        hint_used=hint,
        seconds=seconds,
        mode=Mode.DRILL,
        session_id="s1",
    )


# --- persistence ---------------------------------------------------------------------------


def test_roundtrip(tmp_path: Path) -> None:
    store = StatsStore(tmp_path / "sub" / "stats.json")
    data = StatsData(
        answers=[record(), record(TaskKind.IPV6, None, Outcome.SKIPPED, hint=True)],
        sessions=[SessionRecord("s1", Mode.EXAM, "schwer", "a", "b", 2, 1, 1.0, seed=42)],
        highscores={"speed:mittel": Highscore(17, "2026-09-01T10:00:00+00:00")},
    )
    store.save(data)
    assert store.load() == data
    # Human-readable JSON with a schema version.
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["answers"][0]["outcome"] == "correct"
    assert list(store.path.parent.iterdir()) == [store.path]  # no temp files left behind


def test_missing_file_is_empty(tmp_path: Path) -> None:
    assert StatsStore(tmp_path / "nope.json").load() == StatsData()


@pytest.mark.parametrize(
    "content", ["{kaputt", '{"version": 99}', '{"version": 1, "answers": [{}]}']
)
def test_broken_file_is_moved_aside(tmp_path: Path, content: str) -> None:
    path = tmp_path / "stats.json"
    path.write_text(content, encoding="utf-8")
    store = StatsStore(path)
    assert store.load() == StatsData()
    assert store.warning is not None and "beschädigt" in store.warning
    backups = list(tmp_path.glob("stats.json.defekt-*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == content


def test_add_answer_rereads_file(tmp_path: Path) -> None:
    """Two trainers running at the same time must not overwrite each other's answers."""
    path = tmp_path / "stats.json"
    first, second = StatsStore(path), StatsStore(path)
    first.add_answer(record())
    second.add_answer(record(TaskKind.MASK))
    first.add_answer(record(TaskKind.WILDCARD))
    assert [a.kind for a in StatsStore(path).load().answers] == ["netzadresse", "maske", "wildcard"]


def test_add_session_replaces_same_id(tmp_path: Path) -> None:
    store = StatsStore(tmp_path / "stats.json")
    store.add_session(SessionRecord("x", Mode.DRILL, "mittel", "a", "b", 1, 1, 1.0))
    store.add_session(SessionRecord("x", Mode.DRILL, "mittel", "a", "c", 2, 1, 1.0))
    assert [s.answered for s in store.load().sessions] == [2]


def test_highscores(tmp_path: Path) -> None:
    store = StatsStore(tmp_path / "stats.json")
    assert store.submit_highscore(Mode.SPEED, "mittel", 10) is None
    assert store.submit_highscore(Mode.SPEED, "mittel", 7).score == 10  # type: ignore[union-attr]
    assert store.highscore(Mode.SPEED, "mittel").score == 10  # type: ignore[union-attr]
    store.submit_highscore(Mode.SPEED, "mittel", 12)
    assert store.highscore(Mode.SPEED, "mittel").score == 12  # type: ignore[union-attr]
    assert store.highscore(Mode.SPEED, "schwer") is None


def test_reset(tmp_path: Path) -> None:
    store = StatsStore(tmp_path / "stats.json")
    assert store.reset() is False
    store.add_answer(record())
    assert store.reset() is True
    assert store.load() == StatsData()


def test_data_dir_respects_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module, "_is_windows", lambda: False)  # Linux/macOS behaviour
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert data_dir() == tmp_path / "subnet-trainer"
    monkeypatch.setenv("XDG_DATA_HOME", "relativ/ist/ungueltig")
    assert data_dir() == Path.home() / ".local" / "share" / "subnet-trainer"
    monkeypatch.delenv("XDG_DATA_HOME")
    assert data_dir() == Path.home() / ".local" / "share" / "subnet-trainer"


# --- scoring and analysis ------------------------------------------------------------------


def test_answer_score() -> None:
    assert answer_score(Outcome.CORRECT, False) == 1.0
    assert answer_score(Outcome.CORRECT, True) == 0.5  # a hint counts as half a mistake
    assert answer_score(Outcome.WRONG, True) == 0.0
    assert answer_score(Outcome.SKIPPED, False) == 0.0
    assert answer_score(Outcome.TIMEOUT, False) == 0.0


def test_buckets() -> None:
    assert bucket_of(8) == (8, 15)
    assert bucket_of(21) == (19, 21)
    assert bucket_of(32) == (31, 32)
    assert bucket_of(None) is None
    assert bucket_of(48) is None


def test_aggregate() -> None:
    records = [
        record(outcome=Outcome.CORRECT, seconds=4),
        record(outcome=Outcome.CORRECT, hint=True, seconds=6),
        record(outcome=Outcome.SKIPPED, seconds=99),
        record(TaskKind.MASK, outcome=Outcome.WRONG),
    ]
    agg = aggregate(records, lambda r: r.kind)["netzadresse"]
    assert agg.count == 3 and agg.correct == 2 and agg.hints == 1 and agg.skipped == 1
    assert agg.rate == pytest.approx(0.5)
    assert agg.avg_seconds == pytest.approx(5.0)  # skipped answers do not count for time
    assert total(records).count == 4


def test_newer_answers_count_more() -> None:
    old_mistakes = [record(prefix=20, outcome=Outcome.WRONG, days_ago=60) for _ in range(10)]
    recent_success = [record(prefix=20, days_ago=1) for _ in range(5)]
    cells = {
        (c.kind, c.bucket): c
        for c in weakness_cells(old_mistakes + recent_success, Level.MEDIUM, now=NOW)
    }
    cell = cells[(TaskKind.NETWORK, (19, 21))]
    assert cell.raw_rate == pytest.approx(5 / 15)
    assert cell.rate > 0.75  # the old mistakes have mostly faded

    recent_mistakes = [record(prefix=20, outcome=Outcome.WRONG, days_ago=1) for _ in range(10)]
    old_success = [record(prefix=20, days_ago=60) for _ in range(5)]
    cells = {
        (c.kind, c.bucket): c
        for c in weakness_cells(recent_mistakes + old_success, Level.MEDIUM, now=NOW)
    }
    assert cells[(TaskKind.NETWORK, (19, 21))].rate < 0.2


def test_unseen_cells_count_as_medium() -> None:
    cells = weakness_cells([], Level.EASY, now=NOW)
    assert cells and all(c.rate == pytest.approx(0.5) and c.count == 0 for c in cells)
    # Easy only has /24–/30 (and no VLSM in the random pool).
    assert {c.bucket for c in cells} <= {(22, 24), (25, 27), (28, 30)}
    assert TaskKind.VLSM not in {c.kind for c in cells}


def test_producible_buckets() -> None:
    assert producible_buckets(TaskKind.BROADCAST, Level.HARD)[-1] != (31, 32)
    assert (31, 32) in producible_buckets(TaskKind.HOST_COUNT, Level.HARD)
    assert (8, 15) not in producible_buckets(TaskKind.VLSM, Level.HARD)
    assert producible_buckets(TaskKind.IPV6, Level.MEDIUM) == (None,)


def _history() -> list[AnswerRecord]:
    """Terrible at network addresses with /19–/21, great at everything else."""
    history = [record(TaskKind.NETWORK, 20, Outcome.WRONG, days_ago=1) for _ in range(20)]
    for kind in (TaskKind.NETWORK, TaskKind.MASK, TaskKind.BROADCAST, TaskKind.SAME_NET):
        for prefix in (17, 23, 26, 29):
            history += [record(kind, prefix, days_ago=1) for _ in range(20)]
    return history


def test_weak_spots() -> None:
    spots = weak_spots(_history(), now=NOW)
    assert spots[0].kind is TaskKind.NETWORK and spots[0].bucket == (19, 21)
    assert "Netzadresse, Präfixe /19–/21" in spots[0].label
    assert all(s.count >= 3 for s in spots)


def test_weak_source_focuses_on_weak_cell() -> None:
    source = WeakSource(random.Random(3), Level.MEDIUM, _history(), now=NOW)
    tasks = [source() for _ in range(300)]
    hits = Counter((t.kind, bucket_of(t.prefix)) for t in tasks)[(TaskKind.NETWORK, (19, 21))]
    assert hits > 40  # far above the uniform share (~40 cells -> ~8 hits)
    # Strong areas remain possible, too.
    assert len({t.kind for t in tasks}) > 3


def test_weak_source_adapts_to_live_answers() -> None:
    live: list[AnswerRecord] = []
    source = WeakSource(random.Random(3), Level.MEDIUM, _history(), live, now=NOW)
    before = source.cells[0]
    live += [record(TaskKind.NETWORK, 20, days_ago=0) for _ in range(60)]
    assert source.cells[0] != before
