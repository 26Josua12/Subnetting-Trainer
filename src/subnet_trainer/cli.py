"""Command line interface (German output)."""

from __future__ import annotations

import contextlib
import random
import sys
from typing import Annotated, Any, NoReturn

import typer
import typer.rich_utils
from typer.core import TyperCommand, TyperGroup

from subnet_trainer import __version__
from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import TaskKind
from subnet_trainer.core.tasks.registry import QUICK_KINDS
from subnet_trainer.session import Session, TaskSource, random_source
from subnet_trainer.stats.analysis import WeakSource, weakness_cells
from subnet_trainer.stats.models import Mode, StatsData
from subnet_trainer.stats.store import StatsStore
from subnet_trainer.ui.modes import ModeContext, confirm, run_exam, run_practice, run_speed
from subnet_trainer.ui.prompt import TerminalReader
from subnet_trainer.ui.render import Renderer, de_percent, make_console
from subnet_trainer.ui.stats_view import render_stats

# --- German help output --------------------------------------------------------------------

_RICH_TEXTS = {
    "OPTIONS_PANEL_TITLE": "Optionen",
    "COMMANDS_PANEL_TITLE": "Befehle",
    "ARGUMENTS_PANEL_TITLE": "Argumente",
    "ERRORS_PANEL_TITLE": "Fehler",
    "DEFAULT_STRING": "[Standard: {}]",
    "REQUIRED_LONG_STRING": "[Pflicht]",
    "ABORTED_TEXT": "Abgebrochen.",
    "RICH_HELP": "Hilfe gibt es mit [blue]'{command_path} {help_option}'[/].",
}
for _name, _text in _RICH_TEXTS.items():
    if hasattr(typer.rich_utils, _name):
        setattr(typer.rich_utils, _name, _text)

_HELP_TEXT = "Diese Hilfe anzeigen und beenden."
OPTIONS_METAVAR = "[OPTIONEN]"


class _GermanMixin:
    """Translates the two help strings Click hard-codes ('Usage:' and the --help text).

    The formatter and option types live in Typer's private vendored Click, hence ``Any``.
    """

    def format_usage(self, ctx: typer.Context, formatter: Any) -> None:  # noqa: ANN401
        pieces = self.collect_usage_pieces(ctx)  # type: ignore[attr-defined]
        formatter.write_usage(ctx.command_path, " ".join(pieces), prefix="Aufruf: ")

    def get_help_option(self, ctx: typer.Context) -> Any:  # noqa: ANN401
        option = super().get_help_option(ctx)  # type: ignore[misc]
        if option is not None:
            option.help = _HELP_TEXT
        return option


class GermanGroup(_GermanMixin, TyperGroup):
    pass


class GermanCommand(_GermanMixin, TyperCommand):
    pass


app = typer.Typer(
    cls=GermanGroup,
    options_metavar=OPTIONS_METAVAR,
    subcommand_metavar="BEFEHL [ARGUMENTE]...",
    help="Subnetting-Trainer fürs Terminal – Vorbereitung auf die CCNA-Prüfung.",
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def command() -> Any:  # noqa: ANN401 - Typer's decorator type
    return app.command(cls=GermanCommand, options_metavar=OPTIONS_METAVAR)


# --- shared options ------------------------------------------------------------------------
# Level and type are plain strings so that invalid values produce German error messages.

IPV4_KINDS = [k for k in TaskKind if k is not TaskKind.IPV6]

LevelOpt = Annotated[
    str,
    typer.Option(
        "--level", "-l", metavar="LEVEL", help="Schwierigkeit: leicht, mittel oder schwer."
    ),
]
TypeOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--type",
        "-t",
        metavar="TYP",
        help=(
            "Aufgabentyp, mehrfach angebbar (ohne Angabe: gemischt). Mögliche Werte: "
            + ", ".join(k.value for k in IPV4_KINDS)
            + "."
        ),
        show_default=False,
    ),
]
SeedOpt = Annotated[
    int | None,
    typer.Option(
        "--seed", metavar="ZAHL", help="Startwert für reproduzierbare Aufgaben.", show_default=False
    ),
]
BinaryOpt = Annotated[
    bool,
    typer.Option("--binaer/--ohne-binaer", help="Binärdarstellung in den Erklärungen anzeigen."),
]
CountOpt = Annotated[
    int | None,
    typer.Option(
        "--count",
        "-n",
        metavar="ANZAHL",
        help="Anzahl Aufgaben (Standard: bis du 'q' eingibst).",
        show_default=False,
    ),
]

_LEVEL_ALIASES = {
    "l": Level.EASY,
    "m": Level.MEDIUM,
    "s": Level.HARD,
    "easy": Level.EASY,
    "medium": Level.MEDIUM,
    "hard": Level.HARD,
}


def _fail(message: str) -> NoReturn:
    make_console().print(f"[bad]Fehler:[/] {message}")
    raise typer.Exit(2)


def parse_level(value: str) -> Level:
    text = value.strip().lower()
    if text in _LEVEL_ALIASES:
        return _LEVEL_ALIASES[text]
    try:
        return Level(text)
    except ValueError:
        _fail(f"Unbekanntes Level '{value}'. Möglich sind: leicht, mittel, schwer.")


def parse_kinds(values: list[str] | None, allowed: list[TaskKind]) -> list[TaskKind] | None:
    """'-t netzadresse -t broadcast' and '-t netzadresse,broadcast' both work."""
    if not values:
        return None
    result: list[TaskKind] = []
    for raw in values:
        for part in raw.split(","):
            text = part.strip().lower()
            if not text:
                continue
            kind = next((k for k in allowed if k.value == text), None)
            if kind is None:
                _fail(
                    f"Unbekannter Aufgabentyp '{part.strip()}'. Möglich sind: "
                    + ", ".join(k.value for k in allowed)
                    + "."
                )
            if kind not in result:
                result.append(kind)
    return result or None


def _positive(value: int | None, option: str) -> None:
    if value is not None and value < 1:
        _fail(f"{option} muss mindestens 1 sein.")


def _seed(seed: int | None) -> int:
    return seed if seed is not None else random.SystemRandom().randrange(1, 1_000_000)


def _open_store(ctx: ModeContext) -> tuple[StatsStore, StatsData]:
    store = StatsStore()
    console = ctx.renderer.console
    warn = ctx.renderer.symbols.warn
    try:
        data = store.load()
    except OSError as exc:
        console.print(f"[warn]{warn} Statistik nicht lesbar: {exc}[/]")
        data = StatsData()
    if store.warning:
        console.print(f"[warn]{warn} {store.warning}[/]")
    return store, data


def _context(show_binary: bool = True, kinds: list[TaskKind] | None = None) -> ModeContext:
    console = make_console()
    return ModeContext(Renderer(console, show_binary=show_binary), TerminalReader(console), kinds)


# --- commands ------------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def _default(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", help="Version anzeigen und beenden.")
    ] = False,
) -> None:
    """Ohne Befehl startet der Drill-Modus mit Standardeinstellungen."""
    if version:
        make_console().print(f"subnet-trainer {__version__}")
        raise typer.Exit
    if ctx.invoked_subcommand is None:
        drill()


@command()
def drill(
    kinds: TypeOpt = None,
    level: LevelOpt = "mittel",
    count: CountOpt = None,
    seed: SeedOpt = None,
    binary: BinaryOpt = True,
) -> None:
    """Zufällige Aufgaben mit sofortigem Feedback und Erklärung (Standardmodus)."""
    lvl = parse_level(level)
    selected = parse_kinds(kinds, IPV4_KINDS)
    _positive(count, "--count")
    seed = _seed(seed)
    ctx = _context(binary, selected)
    store, _ = _open_store(ctx)
    source = random_source(random.Random(seed), lvl, selected)
    run_practice(ctx, Session(Mode.DRILL, lvl, source, store, seed), count)


@command()
def exam(
    level: LevelOpt = "mittel",
    count: Annotated[
        int, typer.Option("--count", "-n", metavar="ANZAHL", help="Anzahl Fragen.")
    ] = 20,
    time_limit: Annotated[
        int,
        typer.Option("--time", metavar="SEKUNDEN", help="Zeitlimit pro Frage in Sekunden."),
    ] = 60,
    kinds: TypeOpt = None,
    seed: SeedOpt = None,
    binary: BinaryOpt = True,
) -> None:
    """Prüfungssimulation: feste Fragenzahl, Zeitlimit, keine Hinweise, Auswertung am Ende."""
    lvl = parse_level(level)
    selected = parse_kinds(kinds, IPV4_KINDS)
    _positive(count, "--count")
    _positive(time_limit, "--time")
    seed = _seed(seed)
    ctx = _context(binary, selected)
    store, _ = _open_store(ctx)
    source = random_source(random.Random(seed), lvl, selected)
    run_exam(ctx, Session(Mode.EXAM, lvl, source, store, seed), count, time_limit)


@command()
def speed(level: LevelOpt = "mittel", seed: SeedOpt = None) -> None:
    """So viele richtige Antworten wie möglich in 2 Minuten – mit Highscore."""
    lvl = parse_level(level)
    seed = _seed(seed)
    ctx = _context()
    store, _ = _open_store(ctx)
    source = random_source(random.Random(seed), lvl, QUICK_KINDS)
    run_speed(ctx, Session(Mode.SPEED, lvl, source, store, seed))


@command()
def weak(
    level: LevelOpt = "mittel",
    count: CountOpt = None,
    seed: SeedOpt = None,
    binary: BinaryOpt = True,
) -> None:
    """Trainiert gezielt die Aufgabentypen und Präfixbereiche mit der schlechtesten Quote."""
    lvl = parse_level(level)
    _positive(count, "--count")
    seed = _seed(seed)
    ctx = _context(binary)
    store, data = _open_store(ctx)
    session = Session(Mode.WEAK, lvl, _unset_source, store, seed)
    # The source also sees this session's answers, so the focus adapts while you practise.
    session.source = WeakSource(random.Random(seed), lvl, data.answers, session.records)
    focus = [c for c in weakness_cells(data.answers, lvl) if c.count][:3]
    ctx.intro_details = (
        "Fokus: " + "; ".join(f"{c.label} ({de_percent(c.rate)})" for c in focus)
        if focus
        else "Noch keine Statistik für dieses Level – die Auswahl wird mit jeder Antwort gezielter."
    )
    run_practice(ctx, session, count)


def _unset_source() -> NoReturn:
    raise RuntimeError("task source not configured")


@command()
def ipv6(
    level: LevelOpt = "mittel",
    count: CountOpt = None,
    seed: SeedOpt = None,
) -> None:
    """IPv6-Grundlagen: Adressen kürzen/ausschreiben, Präfixe bestimmen, /64-Subnetze zählen."""
    lvl = parse_level(level)
    _positive(count, "--count")
    seed = _seed(seed)
    ctx = _context()
    store, _ = _open_store(ctx)
    source: TaskSource = random_source(random.Random(seed), lvl, [TaskKind.IPV6])
    run_practice(ctx, Session(Mode.IPV6, lvl, source, store, seed), count)


@command()
def stats() -> None:
    """Übersicht: Quoten pro Typ und Präfixbereich, Verlauf, Highscores, Schwachstellen."""
    ctx = _context()
    store, data = _open_store(ctx)
    render_stats(ctx.renderer.console, data, store.path)


@command()
def reset(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Ohne Rückfrage löschen.")] = False,
) -> None:
    """Alle Statistiken und Highscores löschen (mit Bestätigung)."""
    ctx = _context()
    console = ctx.renderer.console
    store = StatsStore()
    if not store.path.exists():
        console.print("[muted]Es gibt keine Statistik, die gelöscht werden könnte.[/]")
        return
    question = "Wirklich [bold]alle[/] Statistiken und Highscores löschen? Das ist endgültig."
    if not yes and not confirm(ctx, question):
        console.print("[muted]Nichts gelöscht.[/]")
        return
    store.reset()
    console.print("[good]Statistik gelöscht.[/] Zeit für einen Neustart!")


def _ensure_utf8_output() -> None:
    """Redirected output (``> datei.txt``) uses the ANSI code page on Windows, which cannot
    encode symbols like '→'. Switch such streams to UTF-8 instead of crashing."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            with contextlib.suppress(OSError, ValueError):
                stream.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    """Console entry point: never show a traceback for Ctrl+C."""
    _ensure_utf8_output()
    try:
        app()
    except KeyboardInterrupt:
        make_console().print("\n[muted]Abgebrochen.[/]")
        sys.exit(130)


if __name__ == "__main__":
    main()
