"""UI-independent session bookkeeping: task source, answer records and persistence."""

from __future__ import annotations

import random
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import Task, TaskKind
from subnet_trainer.core.tasks.registry import random_task
from subnet_trainer.stats.models import (
    AnswerRecord,
    Mode,
    Outcome,
    SessionRecord,
    now_iso,
)
from subnet_trainer.stats.store import StatsStore

TaskSource = Callable[[], Task]


def random_source(
    rng: random.Random, level: Level, kinds: Iterable[TaskKind] | None = None
) -> TaskSource:
    """Random tasks; avoids asking the exact same task twice in a row."""
    selected = list(kinds) if kinds is not None else None
    last: list[Task] = []

    def next_task() -> Task:
        for _ in range(10):
            task = random_task(rng, level, selected)
            if not last or task != last[0]:
                break
        last[:] = [task]
        return task

    return next_task


@dataclass
class Session:
    mode: Mode
    level: Level
    source: TaskSource
    store: StatsStore | None = None
    seed: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: str = field(default_factory=now_iso)
    records: list[AnswerRecord] = field(default_factory=list)
    storage_error: str | None = None
    """German message if saving failed; the session keeps running regardless."""
    _finished: SessionRecord | None = field(default=None, repr=False)

    def next_task(self) -> Task:
        return self.source()

    def record(
        self, task: Task, outcome: Outcome, *, hint_used: bool, seconds: float
    ) -> AnswerRecord:
        record = AnswerRecord(
            timestamp=now_iso(),
            kind=task.kind.value,
            variant=task.variant,
            level=self.level.value,
            prefix=task.prefix,
            outcome=outcome,
            hint_used=hint_used,
            seconds=round(seconds, 2),
            mode=self.mode,
            session_id=self.id,
        )
        self.records.append(record)
        if self.store is not None:
            try:
                self.store.add_answer(record)
            except OSError as exc:
                self.storage_error = f"Statistik konnte nicht gespeichert werden: {exc}"
        return record

    @property
    def answered(self) -> int:
        return len(self.records)

    def count(self, outcome: Outcome) -> int:
        return sum(r.outcome is outcome for r in self.records)

    @property
    def hints_used(self) -> int:
        return sum(r.hint_used for r in self.records)

    @property
    def score(self) -> float:
        return sum(r.score for r in self.records)

    @property
    def rate(self) -> float:
        return self.score / self.answered if self.answered else 0.0

    @property
    def average_seconds(self) -> float | None:
        times = [r.seconds for r in self.records if r.outcome is not Outcome.SKIPPED]
        return sum(times) / len(times) if times else None

    def finish(self) -> SessionRecord | None:
        """Persist the session summary (once). Empty sessions are not stored."""
        if self._finished is not None or not self.records:
            return self._finished
        self._finished = SessionRecord(
            id=self.id,
            mode=self.mode,
            level=self.level.value,
            started=self.started,
            ended=now_iso(),
            answered=self.answered,
            correct=self.count(Outcome.CORRECT),
            score=self.score,
            seed=self.seed,
        )
        if self.store is not None:
            try:
                self.store.add_session(self._finished)
            except OSError as exc:
                self.storage_error = f"Statistik konnte nicht gespeichert werden: {exc}"
        return self._finished
