"""Aggregations over answer records: rates, prefix buckets and recency-weighted weaknesses."""

from __future__ import annotations

import functools
import random
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import Task, TaskKind
from subnet_trainer.core.tasks.registry import TASK_CLASSES, available_kinds
from subnet_trainer.stats.models import AnswerRecord, Outcome

K = TypeVar("K", bound=Hashable)

Bucket = tuple[int, int]
PREFIX_BUCKETS: tuple[Bucket, ...] = (
    (8, 15),
    (16, 18),
    (19, 21),
    (22, 24),
    (25, 27),
    (28, 30),
    (31, 32),
)

HALF_LIFE_DAYS = 14.0
"""An answer loses half its weight every two weeks."""
PRIOR_RATE = 0.5
PRIOR_WEIGHT = 2.0
"""Bayesian smoothing: cells without data count as 50 %, as if two answers were known."""


def bucket_of(prefix: int | None) -> Bucket | None:
    if prefix is None:
        return None
    return next((b for b in PREFIX_BUCKETS if b[0] <= prefix <= b[1]), None)


def bucket_label(bucket: Bucket) -> str:
    return f"/{bucket[0]}–/{bucket[1]}"


@functools.cache
def producible_buckets(kind: TaskKind, level: Level) -> tuple[Bucket | None, ...]:
    """Prefix buckets that tasks of this kind actually cover on this level (sampled)."""
    rng = random.Random(f"buckets-{kind}-{level}")
    seen = {
        bucket_of(rng.choice(TASK_CLASSES[kind]).generate(rng, level).prefix) for _ in range(300)
    }
    return tuple(sorted(seen, key=lambda b: (b is None, b)))


@dataclass
class Aggregate:
    count: int = 0
    score: float = 0.0
    correct: int = 0
    hints: int = 0
    skipped: int = 0
    seconds: float = 0.0
    timed: int = 0

    def add(self, record: AnswerRecord) -> None:
        self.count += 1
        self.score += record.score
        self.correct += record.outcome is Outcome.CORRECT
        self.hints += record.hint_used
        self.skipped += record.outcome is Outcome.SKIPPED
        if record.outcome is not Outcome.SKIPPED:
            self.seconds += record.seconds
            self.timed += 1

    @property
    def rate(self) -> float:
        return self.score / self.count if self.count else 0.0

    @property
    def avg_seconds(self) -> float | None:
        return self.seconds / self.timed if self.timed else None


def aggregate(
    records: Iterable[AnswerRecord], key: Callable[[AnswerRecord], K | None]
) -> dict[K, Aggregate]:
    result: dict[K, Aggregate] = {}
    for record in records:
        k = key(record)
        if k is not None:
            result.setdefault(k, Aggregate()).add(record)
    return result


def total(records: Iterable[AnswerRecord]) -> Aggregate:
    agg = Aggregate()
    for record in records:
        agg.add(record)
    return agg


def recency_weight(record: AnswerRecord, now: datetime) -> float:
    age_days = max(0.0, (now - record.time).total_seconds() / 86400)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


@dataclass(frozen=True)
class Cell:
    """Weakness estimate for one task kind and prefix bucket (bucket None = whole kind)."""

    kind: TaskKind
    bucket: Bucket | None
    rate: float
    """Recency-weighted, smoothed success rate."""
    raw_rate: float
    count: int

    @property
    def label(self) -> str:
        if self.bucket is None:
            return self.kind.label
        return f"{self.kind.label}, Präfixe {bucket_label(self.bucket)}"

    @property
    def weight(self) -> float:
        """Selection weight for the weak mode: weak cells dominate, strong ones stay possible."""
        return (1.0 - self.rate) ** 3 + 0.01


def weakness_cells(
    records: Sequence[AnswerRecord],
    level: Level,
    *,
    now: datetime | None = None,
    kinds: Iterable[TaskKind] | None = None,
) -> list[Cell]:
    """One cell per (kind, prefix bucket) that the level can produce, weakest first."""
    now = now or datetime.now(UTC)
    wanted = list(kinds) if kinds is not None else available_kinds(level)
    sums: dict[tuple[str, Bucket | None], _Sums] = {}
    for record in records:
        sums.setdefault((record.kind, bucket_of(record.prefix)), _Sums()).add(record, now)
    cells = []
    for kind in wanted:
        for bucket in producible_buckets(kind, level):
            s = sums.get((kind.value, bucket), _Sums())
            rate = (s.weighted_score + PRIOR_RATE * PRIOR_WEIGHT) / (s.weight + PRIOR_WEIGHT)
            raw = s.score / s.count if s.count else 0.0
            cells.append(Cell(kind, bucket, rate, raw, s.count))
    return sorted(cells, key=lambda c: c.rate)


@dataclass
class _Sums:
    weighted_score: float = 0.0
    weight: float = 0.0
    score: float = 0.0
    count: int = 0

    def add(self, record: AnswerRecord, now: datetime) -> None:
        w = recency_weight(record, now)
        self.weighted_score += w * record.score
        self.weight += w
        self.score += record.score
        self.count += 1


def weak_spots(
    records: Sequence[AnswerRecord],
    *,
    now: datetime | None = None,
    min_count: int = 3,
    limit: int = 5,
    threshold: float = 0.8,
) -> list[Cell]:
    """The weakest (kind, bucket) combinations with enough data, for the stats overview."""
    # HARD covers every bucket; all kinds including IPv6 are considered.
    cells = weakness_cells(records, Level.HARD, now=now, kinds=list(TASK_CLASSES))
    return [c for c in cells if c.count >= min_count and c.rate < threshold][:limit]


class WeakSource:
    """Task source for the weak mode: samples cells by weakness, then generates a fitting task."""

    def __init__(
        self,
        rng: random.Random,
        level: Level,
        history: Sequence[AnswerRecord],
        live: Sequence[AnswerRecord] = (),
        *,
        now: datetime | None = None,
    ) -> None:
        """``live`` is re-read on every call (pass the session's growing record list)."""
        self.rng = rng
        self.level = level
        self.history = history
        self.live = live
        self.now = now
        self._last: Task | None = None

    @property
    def cells(self) -> list[Cell]:
        return weakness_cells([*self.history, *self.live], self.level, now=self.now)

    def __call__(self) -> Task:
        cells = self.cells
        cell = self.rng.choices(cells, weights=[c.weight for c in cells])[0]
        task = self._task_for(cell)
        if task == self._last:
            task = self._task_for(cell)
        self._last = task
        return task

    def _task_for(self, cell: Cell) -> Task:
        classes = TASK_CLASSES[cell.kind]
        candidate: Task | None = None
        for _ in range(200):
            candidate = self.rng.choice(classes).generate(self.rng, self.level)
            if cell.bucket is None or bucket_of(candidate.prefix) == cell.bucket:
                return candidate
        assert candidate is not None
        return candidate  # the bucket is very rare for this kind; any task will do
