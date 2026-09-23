from __future__ import annotations

import io
from collections.abc import Iterable
from pathlib import Path

from rich.console import Console

from subnet_trainer.core.tasks.base import Task
from subnet_trainer.stats.store import StatsStore
from subnet_trainer.ui.modes import ModeContext
from subnet_trainer.ui.prompt import ScriptedReader, TimeUp
from subnet_trainer.ui.render import THEME, Renderer


def make_ctx(lines: Iterable[str]) -> tuple[ModeContext, io.StringIO]:
    out = io.StringIO()
    console = Console(file=out, width=100, theme=THEME, color_system=None, highlight=False)
    return ModeContext(Renderer(console), ScriptedReader(lines, console)), out


def fixed_source(tasks: Iterable[Task]):
    iterator = iter(tasks)
    return lambda: next(iterator)


def store_at(tmp_path: Path) -> StatsStore:
    return StatsStore(tmp_path / "stats.json")


class InterruptingReader:
    """Answers with the given lines, then simulates Ctrl+C."""

    def __init__(self, lines: Iterable[str], exc: type[BaseException] = KeyboardInterrupt):
        self._lines = iter(lines)
        self._exc = exc

    def __call__(self, prompt: str, deadline: float | None) -> str:
        try:
            return next(self._lines)
        except StopIteration:
            raise self._exc from None


__all__ = ["InterruptingReader", "TimeUp", "fixed_source", "make_ctx", "store_at"]
