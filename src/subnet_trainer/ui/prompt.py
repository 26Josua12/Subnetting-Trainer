"""Terminal input: special commands, per-field parsing and optional deadlines."""

from __future__ import annotations

import contextlib
import math
import select
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

from rich.console import Console

from subnet_trainer.core.parsing import ParseError
from subnet_trainer.core.tasks.base import CheckResult, Task
from subnet_trainer.stats.models import Outcome

HINT_COMMANDS = {"?", "hinweis", "tipp"}
SKIP_COMMANDS = {"s", "skip", "weiter", "überspringen"}
QUIT_COMMANDS = {"q", "quit", "exit", "beenden", "ende"}


class QuitRequested(Exception):
    """The user typed 'q'."""


class TimeUp(Exception):
    """The deadline passed while waiting for input."""


class LineReader(Protocol):
    def __call__(self, prompt: str, deadline: float | None) -> str:
        """Show ``prompt`` (rich markup) and return one line; raise TimeUp after ``deadline``."""
        ...


class Keyboard(Protocol):
    """The subset of Windows' ``msvcrt`` module used for unbuffered key reads."""

    def kbhit(self) -> bool: ...

    def getwch(self) -> str: ...


_POLL_SECONDS = 0.02
_SPECIAL_KEY_PREFIXES = ("\x00", "\xe0")  # arrows, F-keys, Home/End ... send two codes
_ENTER = ("\r", "\n")
_BACKSPACE = "\x08"
_ESCAPE = "\x1b"
_CTRL_C = "\x03"
_CTRL_Z = "\x1a"


def read_line_polling(
    deadline: float,
    keyboard: Keyboard,
    write: Callable[[str], None],
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Line input with a deadline for consoles without ``select`` on stdin (Windows).

    Echoes typed characters itself and supports Backspace, Esc (clear line), Ctrl+C and
    Ctrl+Z (end of input on an empty line). Raises TimeUp when the deadline passes.
    """
    buffer: list[str] = []
    while True:
        while keyboard.kbhit():
            char = keyboard.getwch()
            if char in _SPECIAL_KEY_PREFIXES:
                keyboard.getwch()  # swallow the second code of the special key
            elif char in _ENTER:
                write("\n")
                return "".join(buffer)
            elif char == _CTRL_C:
                write("\n")
                raise KeyboardInterrupt
            elif char == _CTRL_Z and not buffer:
                write("\n")
                raise EOFError
            elif char == _BACKSPACE:
                if buffer:
                    buffer.pop()
                    write("\b \b")
            elif char == _ESCAPE:
                write("\b \b" * len(buffer))
                buffer.clear()
            elif char.isprintable():
                buffer.append(char)
                write(char)
        if clock() >= deadline:
            write("\n")
            while keyboard.kbhit():  # drop keys typed too late
                keyboard.getwch()
            raise TimeUp
        sleep(_POLL_SECONDS)


def _windows_console_keyboard() -> Keyboard | None:
    """``msvcrt`` if stdin is an interactive Windows console, else None."""
    if not sys.stdin.isatty():
        return None
    try:
        import msvcrt
    except ImportError:
        return None
    return msvcrt  # type: ignore[return-value]


class TerminalReader:
    """Reads from the real terminal.

    Without a deadline, the platform's normal line editing is used (readline on Linux).
    With a deadline, input is read with ``select`` on Linux/macOS and by polling the
    keyboard via ``msvcrt`` on Windows.
    """

    def __init__(
        self,
        console: Console,
        *,
        windows: bool | None = None,
        keyboard: Keyboard | None = None,
    ) -> None:
        self.console = console
        self.windows = sys.platform == "win32" if windows is None else windows
        self._keyboard = keyboard
        # Importing readline enables line editing and history for input() (not on Windows).
        with contextlib.suppress(ImportError):
            import readline  # noqa: F401

    def __call__(self, prompt: str, deadline: float | None) -> str:
        if deadline is None:
            return self.console.input(prompt)
        if deadline - time.monotonic() <= 0:
            raise TimeUp
        self.console.print(prompt, end="")
        self.console.file.flush()
        if self.windows:
            return self._read_windows(deadline)
        return self._read_select(deadline)

    def _read_select(self, deadline: float) -> str:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([sys.stdin], [], [], remaining)
        if not ready:
            self.console.print()
            _discard_pending_input()
            raise TimeUp
        return _read_stdin_line()

    def _read_windows(self, deadline: float) -> str:
        keyboard = self._keyboard or _windows_console_keyboard()
        if keyboard is None:
            # Piped input: nothing to poll. ask_task still marks late answers as timeouts.
            return _read_stdin_line()
        return read_line_polling(deadline, keyboard, self._echo)

    def _echo(self, text: str) -> None:
        self.console.file.write(text)
        self.console.file.flush()


def _read_stdin_line() -> str:
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.rstrip("\r\n")


def _discard_pending_input() -> None:
    """Drop half-typed input so it does not leak into the next question."""
    if not sys.stdin.isatty():
        return
    with contextlib.suppress(ImportError, OSError):
        import termios

        termios.tcflush(sys.stdin, termios.TCIFLUSH)


class ScriptedReader:
    """Feeds predefined lines (for tests and demos); raises EOFError when exhausted."""

    def __init__(self, lines: Iterable[str], console: Console | None = None) -> None:
        self._lines: Iterator[str] = iter(lines)
        self.console = console
        self.prompts: list[str] = []

    def __call__(self, prompt: str, deadline: float | None) -> str:
        self.prompts.append(prompt)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeUp
        try:
            line = next(self._lines)
        except StopIteration:
            raise EOFError from None
        if line == "<TIMEOUT>":
            raise TimeUp
        if self.console is not None:
            self.console.print(f"{prompt}{line}")
        return line


@dataclass
class Attempt:
    """Result of asking one task."""

    outcome: Outcome
    hint_used: bool
    seconds: float
    result: CheckResult | None = None
    """``None`` if skipped or timed out before all fields were answered."""
    given: tuple[str, ...] = ()


class HintHandler(Protocol):
    def __call__(self, task: Task, allowed: bool) -> None: ...


class MessageHandler(Protocol):
    def __call__(self, message: str) -> None: ...


def field_prompt(
    label: str, format_hint: str, deadline: float | None, timer_icon: str = "⏱"
) -> str:
    timer = ""
    if deadline is not None:
        remaining = max(0, math.ceil(deadline - time.monotonic()))
        timer = f"[dim]{timer_icon} {remaining} s[/] "
    return f"{timer}[bold]{label}[/] [dim]({format_hint})[/] [cyan]›[/] "


def ask_task(
    task: Task,
    read: LineReader,
    *,
    on_hint: HintHandler,
    on_error: MessageHandler,
    allow_hints: bool = True,
    deadline: float | None = None,
    timer_icon: str = "⏱",
) -> Attempt:
    """Ask all fields of ``task``; raises QuitRequested, KeyboardInterrupt or EOFError."""
    start = time.monotonic()
    hint_used = False
    values: list[Any] = []
    given: list[str] = []
    for field in task.fields:
        while True:
            try:
                prompt = field_prompt(field.label, field.format_hint, deadline, timer_icon)
                raw = read(prompt, deadline)
            except TimeUp:
                return Attempt(Outcome.TIMEOUT, hint_used, time.monotonic() - start)
            command = raw.strip().lower()
            if not command:
                continue
            if command in QUIT_COMMANDS:
                raise QuitRequested
            if command in SKIP_COMMANDS:
                return Attempt(Outcome.SKIPPED, hint_used, time.monotonic() - start)
            if command in HINT_COMMANDS:
                on_hint(task, allow_hints)
                hint_used = hint_used or allow_hints
                continue
            try:
                values.append(field.parse(raw))
            except ParseError as exc:
                on_error(str(exc))
                continue
            given.append(raw.strip())
            break
    seconds = time.monotonic() - start
    result = task.check(values)
    if deadline is not None and time.monotonic() > deadline:
        return Attempt(Outcome.TIMEOUT, hint_used, seconds, result, tuple(given))
    outcome = Outcome.CORRECT if result.correct else Outcome.WRONG
    return Attempt(outcome, hint_used, seconds, result, tuple(given))
