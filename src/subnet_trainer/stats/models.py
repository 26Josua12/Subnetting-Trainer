"""Persistent statistics records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1


class Outcome(StrEnum):
    CORRECT = "correct"
    WRONG = "wrong"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class Mode(StrEnum):
    DRILL = "drill"
    EXAM = "exam"
    SPEED = "speed"
    WEAK = "weak"
    IPV6 = "ipv6"

    @property
    def label(self) -> str:
        return _MODE_LABELS[self]


_MODE_LABELS = {
    Mode.DRILL: "Drill",
    Mode.EXAM: "Prüfung",
    Mode.SPEED: "Speed",
    Mode.WEAK: "Schwächen",
    Mode.IPV6: "IPv6",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def answer_score(outcome: Outcome, hint_used: bool) -> float:
    """1 for correct, 0.5 for correct with hint (a hint counts as half a mistake), else 0."""
    if outcome is not Outcome.CORRECT:
        return 0.0
    return 0.5 if hint_used else 1.0


@dataclass(frozen=True)
class AnswerRecord:
    timestamp: str
    kind: str
    variant: str
    level: str
    prefix: int | None
    outcome: Outcome
    hint_used: bool
    seconds: float
    mode: Mode
    session_id: str

    @property
    def score(self) -> float:
        return answer_score(self.outcome, self.hint_used)

    @property
    def time(self) -> datetime:
        return parse_iso(self.timestamp)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AnswerRecord:
        return cls(
            timestamp=str(data["timestamp"]),
            kind=str(data["kind"]),
            variant=str(data.get("variant", "")),
            level=str(data["level"]),
            prefix=None if data.get("prefix") is None else int(data["prefix"]),
            outcome=Outcome(data["outcome"]),
            hint_used=bool(data.get("hint_used", False)),
            seconds=float(data.get("seconds", 0.0)),
            mode=Mode(data.get("mode", Mode.DRILL)),
            session_id=str(data.get("session_id", "")),
        )


@dataclass(frozen=True)
class SessionRecord:
    id: str
    mode: Mode
    level: str
    started: str
    ended: str
    answered: int
    correct: int
    score: float
    seed: int | None = None

    @property
    def rate(self) -> float:
        return self.score / self.answered if self.answered else 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SessionRecord:
        return cls(
            id=str(data["id"]),
            mode=Mode(data["mode"]),
            level=str(data["level"]),
            started=str(data["started"]),
            ended=str(data["ended"]),
            answered=int(data["answered"]),
            correct=int(data["correct"]),
            score=float(data["score"]),
            seed=None if data.get("seed") is None else int(data["seed"]),
        )


@dataclass(frozen=True)
class Highscore:
    score: int
    timestamp: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Highscore:
        return cls(score=int(data["score"]), timestamp=str(data["timestamp"]))


@dataclass
class StatsData:
    answers: list[AnswerRecord] = field(default_factory=list)
    sessions: list[SessionRecord] = field(default_factory=list)
    highscores: dict[str, Highscore] = field(default_factory=dict)
    """Keyed by '<mode>:<level>', e.g. 'speed:mittel'."""

    def to_json(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "answers": [a.to_json() for a in self.answers],
            "sessions": [s.to_json() for s in self.sessions],
            "highscores": {k: v.to_json() for k, v in self.highscores.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> StatsData:
        version = data.get("version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported stats schema version: {version!r}")
        return cls(
            answers=[AnswerRecord.from_json(a) for a in data.get("answers", [])],
            sessions=[SessionRecord.from_json(s) for s in data.get("sessions", [])],
            highscores={
                str(k): Highscore.from_json(v) for k, v in data.get("highscores", {}).items()
            },
        )


def highscore_key(mode: Mode, level: str) -> str:
    return f"{mode}:{level}"
