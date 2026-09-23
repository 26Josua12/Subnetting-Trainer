"""Common task interface."""

from __future__ import annotations

import operator
import random
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar, Generic, Self, TypeVar

from subnet_trainer.core.explain import Explanation
from subnet_trainer.core.levels import Level

T = TypeVar("T")


class TaskKind(StrEnum):
    """Task types; the values double as ``--type`` options on the command line."""

    NETWORK = "netzadresse"
    BROADCAST = "broadcast"
    HOST_RANGE = "hostbereich"
    HOST_COUNT = "hostanzahl"
    MASK = "maske"
    WILDCARD = "wildcard"
    SAME_NET = "gleiches-netz"
    SUBDIVIDE = "aufteilen"
    VLSM = "vlsm"
    SUMMARY = "summarization"
    IPV6 = "ipv6"

    @property
    def label(self) -> str:
        return _KIND_LABELS[self]


_KIND_LABELS = {
    TaskKind.NETWORK: "Netzadresse",
    TaskKind.BROADCAST: "Broadcast-Adresse",
    TaskKind.HOST_RANGE: "Host-Bereich",
    TaskKind.HOST_COUNT: "Anzahl Hosts",
    TaskKind.MASK: "CIDR ↔ Maske",
    TaskKind.WILDCARD: "Wildcard-Maske",
    TaskKind.SAME_NET: "Gleiches Netz?",
    TaskKind.SUBDIVIDE: "Subnetze aufteilen",
    TaskKind.VLSM: "VLSM",
    TaskKind.SUMMARY: "Summarization",
    TaskKind.IPV6: "IPv6",
}


@dataclass(frozen=True)
class Field(Generic[T]):
    """One input the user has to provide for a task."""

    label: str
    format_hint: str
    parse: Callable[[str], T]
    """Turns raw input into a value; raises ``ParseError`` if the input is unintelligible."""
    show: Callable[[T], str] = str
    equals: Callable[[T, T], bool] = operator.eq


@dataclass(frozen=True)
class FieldResult:
    label: str
    correct: bool
    given: str
    expected: str


@dataclass(frozen=True)
class CheckResult:
    fields: tuple[FieldResult, ...]

    @property
    def correct(self) -> bool:
        return all(f.correct for f in self.fields)


class Task(ABC):
    """A single exercise.

    ``solution()`` is the ground truth computed with ``ipaddress``; ``explain()`` performs the
    tutor-style calculation independently and must arrive at the same result.
    """

    kind: ClassVar[TaskKind]
    variant: ClassVar[str]
    min_level: ClassVar[Level] = Level.EASY
    """Lowest level at which this task is part of the random pool."""

    @classmethod
    @abstractmethod
    def generate(cls, rng: random.Random, level: Level) -> Self: ...

    @property
    @abstractmethod
    def question(self) -> str: ...

    @property
    @abstractmethod
    def fields(self) -> tuple[Field[Any], ...]: ...

    @property
    def prefix(self) -> int | None:
        """The prefix the task revolves around (used for statistics), if any."""
        return None

    @abstractmethod
    def solution(self) -> tuple[Any, ...]: ...

    @abstractmethod
    def hint(self) -> str: ...

    @abstractmethod
    def explain(self) -> Explanation: ...

    def check(self, answer: Sequence[Any]) -> CheckResult:
        """Compare parsed answers (one per field) against the solution."""
        fields = self.fields
        expected = self.solution()
        if len(answer) != len(fields):
            raise ValueError(f"expected {len(fields)} answers, got {len(answer)}")
        return CheckResult(
            tuple(
                FieldResult(
                    label=f.label,
                    correct=f.equals(given, exp),
                    given=f.show(given),
                    expected=f.show(exp),
                )
                for f, given, exp in zip(fields, answer, expected, strict=True)
            )
        )

    def solution_text(self) -> tuple[str, ...]:
        return tuple(f.show(v) for f, v in zip(self.fields, self.solution(), strict=True))
