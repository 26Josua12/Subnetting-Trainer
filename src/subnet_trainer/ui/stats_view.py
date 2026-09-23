"""Rendering of the `stats` command."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import TaskKind
from subnet_trainer.stats.analysis import (
    PREFIX_BUCKETS,
    Aggregate,
    aggregate,
    bucket_label,
    bucket_of,
    total,
    weak_spots,
)
from subnet_trainer.stats.models import Mode, StatsData, highscore_key, parse_iso
from subnet_trainer.ui.render import de_percent, fmt_seconds, rate_text

RECENT_WINDOW = 10
BUCKET_WEAK_THRESHOLD = 0.7
BUCKET_MIN_COUNT = 5


def local_time(value: str) -> str:
    return parse_iso(value).astimezone().strftime("%d.%m.%Y %H:%M")


def rate_bar(rate: float, width: int = 12) -> Text:
    filled = round(rate * width)
    style = "good" if rate >= 0.8 else "warn" if rate >= 0.6 else "bad"
    return Text("█" * filled, style=style) + Text("░" * (width - filled), style="muted")


def _avg(agg: Aggregate) -> str:
    return fmt_seconds(agg.avg_seconds) if agg.avg_seconds is not None else "–"


def render_stats(
    console: Console, data: StatsData, path: Path, *, now: datetime | None = None
) -> None:
    now = now or datetime.now(UTC)
    answers = data.answers
    if not answers:
        console.print("Noch keine Statistik vorhanden – starte mit [bold]subnet-trainer drill[/]!")
        return

    overall = total(answers)
    days = {parse_iso(a.timestamp).astimezone().date() for a in answers}
    overview = Table.grid(padding=(0, 2))
    overview.add_column(style="bold")
    overview.add_column()
    overview.add_row("Antworten", str(overall.count))
    overview.add_row("Trefferquote", rate_text(overall.rate))
    overview.add_row("Ø Antwortzeit", _avg(overall))
    overview.add_row("Sessions", str(len(data.sessions)))
    overview.add_row("Trainingstage", str(len(days)))
    overview.add_row(
        "Zeitraum", f"{local_time(answers[0].timestamp)} – {local_time(answers[-1].timestamp)}"
    )
    console.print(Panel(overview, title="Überblick", border_style="cyan", expand=False))

    # Per task type, with the most recent answers as a trend indicator.
    by_kind = aggregate(answers, lambda a: a.kind)
    recent = {
        kind: total([a for a in answers if a.kind == kind][-RECENT_WINDOW:]) for kind in by_kind
    }
    kinds = Table(title="Nach Aufgabentyp", box=box.SIMPLE_HEAD, title_justify="left")
    kinds.add_column("Typ", no_wrap=True)
    kinds.add_column("Antworten", justify="right")
    kinds.add_column("Quote", justify="right")
    kinds.add_column(f"Letzte {RECENT_WINDOW}", justify="right", no_wrap=True)
    kinds.add_column("Ø Zeit", justify="right")
    kinds.add_column("Hinweis/Skip", justify="right")
    for kind in TaskKind:
        agg = by_kind.get(kind.value)
        if agg is None:
            continue
        kinds.add_row(
            kind.label,
            str(agg.count),
            rate_text(agg.rate),
            _trend(recent[kind.value].rate, agg.rate),
            _avg(agg),
            f"{agg.hints}/{agg.skipped}",
        )
    console.print(kinds)

    by_bucket = aggregate(answers, lambda a: bucket_of(a.prefix) if a.kind != "ipv6" else None)
    if by_bucket:
        buckets = Table(
            title="Nach Präfixbereich (IPv4)", box=box.SIMPLE_HEAD, title_justify="left"
        )
        buckets.add_column("Präfixe")
        buckets.add_column("Antworten", justify="right")
        buckets.add_column("Quote", justify="right")
        buckets.add_column("", no_wrap=True)
        buckets.add_column("Ø Zeit", justify="right")
        for bucket in PREFIX_BUCKETS:
            if agg := by_bucket.get(bucket):
                buckets.add_row(
                    bucket_label(bucket),
                    str(agg.count),
                    rate_text(agg.rate),
                    rate_bar(agg.rate),
                    _avg(agg),
                )
        console.print(buckets)

    weak_lines = [
        f"• Präfixe {bucket_label(bucket)}: {de_percent(agg.rate)} ({agg.count} Antworten)"
        for bucket, agg in sorted(by_bucket.items(), key=lambda kv: kv[1].rate)
        if agg.count >= BUCKET_MIN_COUNT and agg.rate < BUCKET_WEAK_THRESHOLD
    ]
    weak_lines += [
        f"• {cell.label}: {de_percent(cell.rate)} gewichtet ({cell.count} Antworten)"
        for cell in weak_spots(answers, now=now)
    ]
    if weak_lines:
        body = (
            "\n".join(weak_lines)
            + "\n[muted]Tipp: 'subnet-trainer weak' übt genau diese Bereiche.[/]"
        )
        console.print(Panel(body, title="Schwachstellen", border_style="red", expand=False))
    else:
        console.print("[good]Keine auffälligen Schwachstellen – weiter so![/]")

    if data.sessions:
        sessions = Table(title="Letzte Sessions", box=box.SIMPLE_HEAD, title_justify="left")
        sessions.add_column("Datum")
        sessions.add_column("Modus")
        sessions.add_column("Level")
        sessions.add_column("Aufgaben", justify="right")
        sessions.add_column("Quote", justify="right")
        for s in data.sessions[-10:][::-1]:
            sessions.add_row(
                local_time(s.started),
                s.mode.label,
                _level_label(s.level),
                str(s.answered),
                rate_text(s.rate),
            )
        console.print(sessions)

    scores = Table(title="Highscores (Speed, 2 Minuten)", box=box.SIMPLE_HEAD, title_justify="left")
    scores.add_column("Level")
    scores.add_column("Richtige", justify="right")
    scores.add_column("Datum")
    for level in Level:
        entry = data.highscores.get(highscore_key(Mode.SPEED, level.value))
        scores.add_row(
            level.label,
            str(entry.score) if entry else "–",
            local_time(entry.timestamp) if entry else "",
        )
    console.print(scores)
    console.print(f"[muted]Daten: {path}[/]", soft_wrap=True)


def _level_label(value: str) -> str:
    try:
        return Level(value).label
    except ValueError:
        return value


def _trend(recent: float, overall: float) -> str:
    arrow = "↑" if recent > overall + 0.05 else "↓" if recent < overall - 0.05 else "→"
    return f"{rate_text(recent)} {arrow}"
