"""Windows support, tested on any OS with a simulated keyboard (``msvcrt`` stand-in)."""

from __future__ import annotations

import io
import sys
import time
from ipaddress import IPv4Address
from pathlib import Path

import pytest
from rich.console import Console

from subnet_trainer import cli
from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.address import NetworkTask
from subnet_trainer.session import Session
from subnet_trainer.stats import store as store_module
from subnet_trainer.stats.models import Mode, Outcome, StatsData
from subnet_trainer.stats.store import StatsStore, data_dir
from subnet_trainer.ui.modes import ModeContext, run_exam, run_speed
from subnet_trainer.ui.prompt import TerminalReader, TimeUp, read_line_polling
from subnet_trainer.ui.render import THEME, Renderer
from subnet_trainer.ui.symbols import PLAIN, UNICODE, symbols_for

from helpers import fixed_source

NET = NetworkTask(IPv4Address("172.16.45.200"), 21)  # -> 172.16.40.0


class ScriptedKeyboard:
    """Keys that become available at given (fake) times, like msvcrt.kbhit/getwch."""

    def __init__(self, events: list[tuple[float, str]], clock: FakeClock) -> None:
        self.keys = [(t, ch) for t, text in events for ch in text]
        self.clock = clock

    def kbhit(self) -> bool:
        return bool(self.keys) and self.keys[0][0] <= self.clock.now

    def getwch(self) -> str:
        return self.keys.pop(0)[1]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class InstantKeyboard:
    """All keys are available immediately (for tests with the real clock)."""

    def __init__(self, text: str) -> None:
        self.keys = list(text)

    def kbhit(self) -> bool:
        return bool(self.keys)

    def getwch(self) -> str:
        return self.keys.pop(0)


def _read(events: list[tuple[float, str]], deadline: float = 10.0) -> tuple[str, str]:
    clock = FakeClock()
    echo: list[str] = []
    line = read_line_polling(
        deadline,
        ScriptedKeyboard(events, clock),
        echo.append,
        clock=clock,
        sleep=clock.sleep,
    )
    return line, "".join(echo)


# --- the polling line editor ---------------------------------------------------------------


def test_typing_and_enter() -> None:
    line, echo = _read([(0, "172.16.40.0\r")])
    assert line == "172.16.40.0"
    assert echo == "172.16.40.0\n"


def test_keys_arriving_over_time() -> None:
    line, _ = _read([(0.5, "17"), (2.0, "2.16"), (3.0, "\r")])
    assert line == "172.16"


def test_backspace_and_escape() -> None:
    line, echo = _read([(0, "12\x083\r")])
    assert line == "13"
    assert "\b \b" in echo
    line, _ = _read([(0, "falsch\x1bja\r")])
    assert line == "ja"


def test_special_keys_are_ignored() -> None:
    # Arrow left (\xe0 K), F1 (\x00 ;) and Delete (\xe0 S) send two codes each.
    line, echo = _read([(0, "1\xe0K2\x00;3\xe0S\r")])
    assert line == "123"
    assert "K" not in echo and ";" not in echo


def test_timeout_raises_timeup_and_drops_partial_input() -> None:
    with pytest.raises(TimeUp):
        _read([(0.2, "10.0.")], deadline=1.0)


def test_ctrl_c_and_ctrl_z() -> None:
    with pytest.raises(KeyboardInterrupt):
        _read([(0, "12\x03")])
    with pytest.raises(EOFError):
        _read([(0, "\x1a")])
    # Ctrl+Z in the middle of a line is ignored rather than ending the input.
    assert _read([(0, "1\x1a2\r")])[0] == "12"


def test_carriage_return_newline_pair() -> None:
    assert _read([(0, "ja\r\n")])[0] == "ja"


# --- TerminalReader on Windows -------------------------------------------------------------


def _console() -> tuple[Console, io.StringIO]:
    out = io.StringIO()
    return Console(file=out, width=100, theme=THEME, color_system=None), out


def test_terminal_reader_uses_keyboard_on_windows() -> None:
    console, out = _console()
    reader = TerminalReader(console, windows=True, keyboard=InstantKeyboard("abc\r"))
    assert reader("Frage › ", time.monotonic() + 5) == "abc"
    assert out.getvalue() == "Frage › abc\n"


def test_terminal_reader_times_out_on_windows() -> None:
    console, _ = _console()
    reader = TerminalReader(console, windows=True, keyboard=InstantKeyboard(""))
    start = time.monotonic()
    with pytest.raises(TimeUp):
        reader("Frage › ", start + 0.2)
    assert 0.15 < time.monotonic() - start < 2


def test_terminal_reader_windows_piped_input(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without an interactive console (e.g. piped input) there is nothing to poll."""
    monkeypatch.setattr(sys, "stdin", io.StringIO("10.0.0.1\r\n"))
    console, _ = _console()
    reader = TerminalReader(console, windows=True)
    assert reader("› ", time.monotonic() + 5) == "10.0.0.1"


def _windows_ctx(
    keys: str, monkeypatch: pytest.MonkeyPatch, stdin: str
) -> tuple[ModeContext, io.StringIO]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))  # used for prompts without deadline
    console, out = _console()
    reader = TerminalReader(console, windows=True, keyboard=InstantKeyboard(keys))
    return ModeContext(Renderer(console), reader), out


def test_exam_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx, out = _windows_ctx("172.16.40.0\r", monkeypatch, stdin="nein\n")
    session = Session(
        Mode.EXAM, Level.MEDIUM, fixed_source([NET, NET]), StatsStore(tmp_path / "s.json")
    )
    run_exam(ctx, session, count=2, time_limit=1)
    assert [r.outcome for r in session.records] == [Outcome.CORRECT, Outcome.TIMEOUT]
    assert "1 von 2" in out.getvalue()


def test_speed_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ctx, out = _windows_ctx("172.16.40.0\r172.16.40.0\r", monkeypatch, stdin="\n")
    store = StatsStore(tmp_path / "s.json")
    session = Session(Mode.SPEED, Level.MEDIUM, fixed_source([NET, NET, NET]), store)
    run_speed(ctx, session, duration=1)
    assert session.count(Outcome.CORRECT) == 2
    assert "Neuer Highscore" in out.getvalue()
    assert store.highscore(Mode.SPEED, "mittel").score == 2  # type: ignore[union-attr]


# --- symbols -------------------------------------------------------------------------------


def test_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("WT_SESSION", "TERM_PROGRAM", "CONEMUANSI", "SUBNET_TRAINER_EINFACH"):
        monkeypatch.delenv(name, raising=False)
    terminal = Console(file=io.StringIO(), force_terminal=True)
    redirected = Console(file=io.StringIO())
    # Classic Windows console: plain symbols; everything else keeps Unicode.
    assert symbols_for(terminal, windows=True) is PLAIN
    assert symbols_for(redirected, windows=True) is UNICODE
    assert symbols_for(terminal, windows=False) is UNICODE
    monkeypatch.setenv("WT_SESSION", "1")  # Windows Terminal
    assert symbols_for(terminal, windows=True) is UNICODE
    monkeypatch.setenv("SUBNET_TRAINER_EINFACH", "1")
    assert symbols_for(terminal, windows=False) is PLAIN
    monkeypatch.setenv("SUBNET_TRAINER_EINFACH", "0")
    monkeypatch.delenv("WT_SESSION")
    assert symbols_for(terminal, windows=True) is UNICODE


def test_plain_symbols_are_ascii() -> None:
    """Displayable in every Windows console, whatever font or code page (e.g. cp850)."""
    for field in ("ok", "wrong", "skip", "timer", "hint", "warn", "info", "trophy"):
        getattr(PLAIN, field).encode("ascii")


def test_renderer_uses_plain_symbols() -> None:
    console, out = _console()
    renderer = Renderer(console, symbols=PLAIN)
    renderer.input_error("Test")
    assert out.getvalue().startswith("! Test")


# --- storage -------------------------------------------------------------------------------


def test_data_dir_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module, "_is_windows", lambda: True)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert data_dir() == tmp_path / "Roaming" / "subnet-trainer"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))  # an explicit XDG path wins
    assert data_dir() == tmp_path / "xdg" / "subnet-trainer"
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.delenv("APPDATA")
    assert data_dir() == Path.home() / ".local" / "share" / "subnet-trainer"


def test_locked_file_is_retried(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store_module.time, "sleep", lambda _: None)
    real_replace = store_module.os.replace
    failures = iter([True, True, False])

    def flaky_replace(src: str, dst: Path) -> None:
        if next(failures):
            raise PermissionError("[WinError 5] Zugriff verweigert")
        real_replace(src, dst)

    monkeypatch.setattr(store_module.os, "replace", flaky_replace)
    store = StatsStore(tmp_path / "stats.json")
    store.save(StatsData())
    assert store.load() == StatsData()


def test_permanently_locked_file_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(store_module.time, "sleep", lambda _: None)

    def locked(src: str, dst: Path) -> None:
        raise PermissionError("[WinError 5] Zugriff verweigert")

    monkeypatch.setattr(store_module.os, "replace", locked)
    with pytest.raises(PermissionError):
        StatsStore(tmp_path / "stats.json").save(StatsData())
    assert list(tmp_path.iterdir()) == []  # no temp file left behind


# --- output encoding -----------------------------------------------------------------------


def test_redirected_output_is_switched_to_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    """`subnet-trainer stats > datei.txt` on Windows writes with the ANSI code page."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    cli._ensure_utf8_output()
    print("Blockgröße → 8 ✔", file=sys.stdout)
    sys.stdout.flush()
    assert "Blockgröße → 8 ✔" in raw.getvalue().decode("utf-8")
