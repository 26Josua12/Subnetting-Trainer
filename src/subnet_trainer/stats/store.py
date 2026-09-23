"""JSON persistence: $XDG_DATA_HOME/subnet-trainer/, %APPDATA%\\subnet-trainer on Windows."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TypeVar

from subnet_trainer.stats.models import (
    AnswerRecord,
    Highscore,
    Mode,
    SessionRecord,
    StatsData,
    highscore_key,
    now_iso,
)

APP_DIR = "subnet-trainer"
FILE_NAME = "stats.json"


_RETRY_ATTEMPTS = 5
T = TypeVar("T")


def _is_windows() -> bool:
    return sys.platform == "win32"


def data_dir() -> Path:
    """$XDG_DATA_HOME/subnet-trainer if set; otherwise %APPDATA% on Windows, ~/.local/share."""
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg and Path(xdg).is_absolute():
        return Path(xdg) / APP_DIR
    if _is_windows():
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / APP_DIR
    return Path.home() / ".local" / "share" / APP_DIR


def _retry_locked(action: Callable[[], T]) -> T:
    """Retry on PermissionError: on Windows, virus scanners or a second trainer can hold the
    file open for a moment, which makes reading or the atomic rename fail briefly."""
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return action()
        except PermissionError:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise AssertionError("unreachable")


class StatsStore:
    """Reads and writes the statistics file.

    Every mutating call re-reads the file, applies the change and writes it back atomically,
    so an interrupted session never loses already answered questions and two concurrently
    running trainers do not overwrite each other's answers.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / FILE_NAME
        self.warning: str | None = None
        """Set when a broken file had to be moved aside (message is German, for the UI)."""

    def load(self) -> StatsData:
        try:
            raw = _retry_locked(lambda: self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return StatsData()
        try:
            return StatsData.from_json(json.loads(raw))
        except (ValueError, KeyError, TypeError) as exc:
            backup = self.path.with_name(
                f"{self.path.name}.defekt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            self.path.replace(backup)
            self.warning = (
                f"Die Statistikdatei war beschädigt ({exc.__class__.__name__}) und wurde nach "
                f"{backup} verschoben. Es wird mit einer leeren Statistik weitergemacht."
            )
            return StatsData()

    def save(self, data: StatsData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".stats-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data.to_json(), handle, ensure_ascii=False, indent=1)
                handle.flush()
                os.fsync(handle.fileno())
            _retry_locked(lambda: os.replace(tmp, self.path))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def add_answer(self, record: AnswerRecord) -> None:
        data = self.load()
        data.answers.append(record)
        self.save(data)

    def add_session(self, record: SessionRecord) -> None:
        data = self.load()
        data.sessions = [s for s in data.sessions if s.id != record.id]
        data.sessions.append(record)
        self.save(data)

    def submit_highscore(self, mode: Mode, level: str, score: int) -> Highscore | None:
        """Store ``score`` if it beats the current highscore; returns the previous one.

        Returns ``None`` if there was no previous highscore. Use :meth:`highscore` to see
        whether the new score was accepted.
        """
        data = self.load()
        key = highscore_key(mode, level)
        previous = data.highscores.get(key)
        if previous is None or score > previous.score:
            data.highscores[key] = Highscore(score, now_iso())
            self.save(data)
        return previous

    def highscore(self, mode: Mode, level: str) -> Highscore | None:
        return self.load().highscores.get(highscore_key(mode, level))

    def reset(self) -> bool:
        """Delete all statistics; returns whether there was anything to delete."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True
