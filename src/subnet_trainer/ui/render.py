"""Rich rendering of tasks, feedback, explanations and summaries (German output)."""

from __future__ import annotations

from collections import Counter

from rich import box
from rich.console import Console, Group, RenderableType
from rich.highlighter import RegexHighlighter
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from subnet_trainer.core.addressing import dotted
from subnet_trainer.core.explain import BinaryRow, Explanation
from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import CheckResult, Task, TaskKind
from subnet_trainer.session import Session
from subnet_trainer.stats.models import Highscore, Mode, Outcome
from subnet_trainer.ui.prompt import Attempt
from subnet_trainer.ui.symbols import Symbols, symbols_for

THEME = Theme(
    {
        "net": "bold cyan",
        "host": "yellow",
        "good": "bold green",
        "bad": "bold red",
        "warn": "yellow",
        "muted": "dim",
        "tutor.ip": "bold cyan",
        "tutor.prefix": "bold magenta",
        "tutor.arrow": "bold",
        "tutor.formula": "green",
    }
)


class TutorHighlighter(RegexHighlighter):
    """Highlights addresses, prefixes and the key arithmetic in explanation steps."""

    base_style = "tutor."
    highlights = [  # noqa: RUF012 - rich API expects a plain class attribute
        r"(?P<ip>\b\d{1,3}(?:\.\d{1,3}){3}\b)",
        r"(?P<ip>\b[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}\b)",
        r"(?P<prefix>(?<![\w.])/\d{1,3}\b)",
        r"(?P<arrow>→)",
        r"(?P<formula>256 − \d+ = \d+)",
    ]


def make_console() -> Console:
    return Console(theme=THEME, highlight=False)


def de_float(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def de_percent(value: float) -> str:
    return f"{de_float(value * 100, 0)} %"


def fmt_seconds(seconds: float) -> str:
    return f"{de_float(seconds)} s"


COMMANDS_HELP = "[muted]?[/] Hinweis · [muted]s[/] überspringen · [muted]q[/] beenden"


class Renderer:
    def __init__(
        self, console: Console, *, show_binary: bool = True, symbols: Symbols | None = None
    ) -> None:
        self.console = console
        self.show_binary = show_binary
        self.highlighter = TutorHighlighter()
        self.symbols = symbols or symbols_for(console)

    # --- session frame ---------------------------------------------------------------------

    def intro(
        self,
        mode: Mode,
        level: Level,
        *,
        seed: int | None,
        kinds: list[TaskKind] | None = None,
        details: str | None = None,
        commands: str = COMMANDS_HELP,
    ) -> None:
        parts = [f"[bold]{mode.label}[/]", f"Level [bold]{level.label}[/]"]
        if kinds:
            parts.append(", ".join(k.label for k in kinds))
        if seed is not None:
            parts.append(f"[muted]Seed {seed}[/]")
        body = " · ".join(parts)
        if details:
            body += f"\n{details}"
        if commands:
            body += f"\n{commands}"
        self.console.print(Panel(body, title="subnet-trainer", border_style="cyan", expand=False))

    def task(self, task: Task, number: int, total: int | None, level: Level) -> None:
        counter = f"{number}/{total}" if total else str(number)
        title = f"Aufgabe {counter} · {task.kind.label}"
        self.console.print()
        self.console.print(
            Panel(
                Text(task.question),
                title=title,
                title_align="left",
                border_style="blue",
                subtitle=f"[muted]{level.label}[/]",
                subtitle_align="right",
            )
        )

    # --- feedback --------------------------------------------------------------------------

    def hint(self, task: Task, allowed: bool) -> None:
        if not allowed:
            self.console.print("[warn]In diesem Modus gibt es keine Hinweise.[/]")
            return
        self.console.print(
            Text.assemble(
                (f"{self.symbols.hint} Hinweis: ", "warn"), self.highlighter(task.hint())
            ),
            "[muted](zählt als halber Fehler)[/]",
        )

    def input_error(self, message: str) -> None:
        self.console.print(f"[warn]{self.symbols.warn} {message}[/]")

    def feedback(self, task: Task, attempt: Attempt, *, explain: bool = True) -> None:
        time_text = f"[muted]({fmt_seconds(attempt.seconds)})[/]"
        match attempt.outcome:
            case Outcome.CORRECT:
                extra = " – mit Hinweis, zählt halb" if attempt.hint_used else ""
                self.console.print(f"[good]{self.symbols.ok} Richtig![/]{extra} {time_text}")
                return
            case Outcome.WRONG:
                self.console.print(f"[bad]{self.symbols.wrong} Leider falsch.[/] {time_text}")
            case Outcome.SKIPPED:
                self.console.print(f"[warn]{self.symbols.skip} Übersprungen.[/]")
            case Outcome.TIMEOUT:
                self.console.print(f"[bad]{self.symbols.timer} Zeit abgelaufen.[/]")
        self.answer_table(task, attempt.result)
        if explain:
            self.explanation(task.explain())

    def answer_table(self, task: Task, result: CheckResult | None) -> None:
        table = Table(box=box.SIMPLE, show_edge=False, pad_edge=False)
        table.add_column("")
        if result is not None:
            table.add_column("Deine Antwort")
        table.add_column("Richtig", style="good")
        if result is not None:
            for field in result.fields:
                style = "good" if field.correct else "bad"
                table.add_row(field.label, Text(field.given, style=style), field.expected)
        else:
            for field, expected in zip(task.fields, task.solution_text(), strict=True):
                table.add_row(field.label, expected)
        self.console.print(table)

    def explanation(self, explanation: Explanation) -> None:
        parts: list[RenderableType] = []
        steps = Table.grid(padding=(0, 1))
        steps.add_column(style="bold", justify="right")
        steps.add_column()
        for number, step in enumerate(explanation.steps, 1):
            steps.add_row(f"{number}.", self.highlighter(step))
        parts.append(steps)
        if self.show_binary and explanation.binary:
            parts.append(Text())
            parts.append(binary_table(explanation.binary))
        if explanation.note:
            parts.append(Text())
            parts.append(Text(f"{self.symbols.info} {explanation.note}", style="warn"))
        self.console.print(
            Panel(Group(*parts), title="So rechnest du es", title_align="left", border_style="dim")
        )

    # --- exam ------------------------------------------------------------------------------

    def exam_ack(self, attempt: Attempt) -> None:
        match attempt.outcome:
            case Outcome.TIMEOUT:
                self.console.print(f"[bad]{self.symbols.timer} Zeit abgelaufen.[/]")
            case Outcome.SKIPPED:
                self.console.print(f"[muted]{self.symbols.skip} Übersprungen.[/]")
            case _:
                self.console.print(
                    f"[muted]Antwort gespeichert ({fmt_seconds(attempt.seconds)}).[/]"
                )

    def exam_report(self, results: list[tuple[Task, Attempt]], planned: int) -> None:
        self.console.print()
        if not results:
            self.console.print("[muted]Keine Fragen beantwortet.[/]")
            return
        table = Table(title="Auswertung", box=box.SIMPLE_HEAD, title_justify="left")
        table.add_column("Nr.", justify="right")
        table.add_column("Typ")
        table.add_column("Deine Antwort", overflow="fold")
        table.add_column("Lösung", overflow="fold")
        table.add_column("", justify="center")
        table.add_column("Zeit", justify="right")
        for number, (task, attempt) in enumerate(results, 1):
            given = " / ".join(attempt.given) or "–"
            solution = " / ".join(task.solution_text())
            mark = {
                Outcome.CORRECT: f"[good]{self.symbols.ok}[/]",
                Outcome.WRONG: f"[bad]{self.symbols.wrong}[/]",
                Outcome.SKIPPED: f"[warn]{self.symbols.skip}[/]",
                Outcome.TIMEOUT: f"[bad]{self.symbols.timer}[/]",
            }[attempt.outcome]
            if attempt.outcome is Outcome.TIMEOUT and attempt.result is None:
                given = "[muted]Zeit abgelaufen[/]"
            table.add_row(
                str(number), task.kind.label, given, solution, mark, fmt_seconds(attempt.seconds)
            )
        self.console.print(table)
        correct = sum(a.outcome is Outcome.CORRECT for _, a in results)
        rate = correct / planned
        times = [a.seconds for _, a in results]
        verdict = (
            "[good]Stark – das sitzt prüfungsreif![/]"
            if rate >= 0.85
            else "[warn]Knapp – ein paar Runden Training schaden nicht.[/]"
            if rate >= 0.7
            else "[bad]Da geht noch was – übe gezielt mit 'subnet-trainer weak'.[/]"
        )
        lines = [
            f"[bold]{correct} von {planned}[/] richtig ({rate_text(rate)})",
            f"Ø Zeit pro Frage: {fmt_seconds(sum(times) / len(times))}",
        ]
        if len(results) < planned:
            lines.append(f"[warn]{planned - len(results)} Fragen nicht beantwortet.[/]")
        lines.append(verdict)
        self.console.print(
            Panel("\n".join(lines), title="Ergebnis", border_style="cyan", expand=False)
        )

    def review(self, task: Task, attempt: Attempt, number: int) -> None:
        self.console.print()
        self.console.print(
            Panel(
                Text(task.question),
                title=f"Frage {number} · {task.kind.label}",
                title_align="left",
                border_style="blue",
            )
        )
        self.answer_table(task, attempt.result)
        self.explanation(task.explain())

    # --- speed -----------------------------------------------------------------------------

    def speed_task(self, task: Task, number: int) -> None:
        self.console.print(f"\n[bold cyan]{number}.[/] {task.question}")

    def speed_feedback(self, task: Task, attempt: Attempt) -> None:
        if attempt.outcome is Outcome.CORRECT:
            self.console.print(
                f"[good]{self.symbols.ok}[/] [muted]{fmt_seconds(attempt.seconds)}[/]"
            )
        else:
            solution = " / ".join(task.solution_text())
            self.console.print(f"[bad]{self.symbols.wrong}[/] Richtig wäre: [good]{solution}[/]")

    def speed_result(
        self, score: int, previous: Highscore | None, *, finished: bool, new_record: bool
    ) -> None:
        lines = [f"[bold]{score}[/] richtige Antwort{'en' if score != 1 else ''}"]
        if new_record:
            lines.append(f"[good]{self.symbols.trophy} Neuer Highscore![/]")
            if previous is not None:
                lines.append(f"[muted]Bisher: {previous.score}[/]")
        elif previous is not None:
            lines.append(f"Highscore: {previous.score}")
        if not finished:
            lines.append("[muted]Nicht gewertet, weil die Runde abgebrochen wurde.[/]")
        self.console.print(
            Panel("\n".join(lines), title="Speed", border_style="cyan", expand=False)
        )

    # --- summary ---------------------------------------------------------------------------

    def summary(self, session: Session, *, title: str = "Zusammenfassung") -> None:
        self.console.print()
        if not session.records:
            self.console.print("[muted]Keine Aufgaben beantwortet – bis zum nächsten Mal![/]")
            return
        table = Table(box=box.SIMPLE_HEAD, show_header=False)
        table.add_column(style="bold")
        table.add_column(justify="right")
        table.add_row("Aufgaben", str(session.answered))
        table.add_row("Richtig", f"[good]{session.count(Outcome.CORRECT)}[/]")
        table.add_row("Falsch", f"[bad]{session.count(Outcome.WRONG)}[/]")
        if skipped := session.count(Outcome.SKIPPED):
            table.add_row("Übersprungen", str(skipped))
        if timeouts := session.count(Outcome.TIMEOUT):
            table.add_row("Zeit abgelaufen", str(timeouts))
        if session.hints_used:
            table.add_row("Mit Hinweis", str(session.hints_used))
        table.add_row("Quote", rate_text(session.rate))
        if (avg := session.average_seconds) is not None:
            table.add_row("Ø Antwortzeit", fmt_seconds(avg))
        kinds = Counter(r.kind for r in session.records)
        parts: list[RenderableType] = [table]
        if len(kinds) > 1:
            parts.append(kind_breakdown(session))
        self.console.print(Panel(Group(*parts), title=title, border_style="cyan", expand=False))
        if session.storage_error:
            self.console.print(f"[warn]{self.symbols.warn} {session.storage_error}[/]")


def rate_text(rate: float) -> str:
    style = "good" if rate >= 0.8 else "warn" if rate >= 0.6 else "bad"
    return f"[{style}]{de_percent(rate)}[/]"


def kind_breakdown(session: Session) -> Table:
    table = Table(box=box.SIMPLE, title="Nach Aufgabentyp", title_justify="left")
    table.add_column("Typ")
    table.add_column("Aufgaben", justify="right")
    table.add_column("Quote", justify="right")
    by_kind: dict[str, list[float]] = {}
    for record in session.records:
        by_kind.setdefault(record.kind, []).append(record.score)
    for kind, scores in sorted(by_kind.items(), key=lambda kv: sum(kv[1]) / len(kv[1])):
        table.add_row(TaskKind(kind).label, str(len(scores)), rate_text(sum(scores) / len(scores)))
    return table


def binary_bits(row: BinaryRow) -> Text:
    """Bits grouped per octet; network part colored, a '|' marks the prefix boundary."""
    text = Text()
    for i in range(32):
        if i and i == row.prefix:
            text.append("|", style="bold")
        elif i and i % 8 == 0:
            text.append(".", style="muted")
        bit = (row.value >> (31 - i)) & 1
        text.append(str(bit), style="net" if i < row.prefix else "host")
    return text


def binary_table(rows: tuple[BinaryRow, ...]) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold", justify="right")
    table.add_column(justify="right")
    table.add_column()
    for row in rows:
        table.add_row(row.label, dotted(row.value), binary_bits(row))
    legend = Text.assemble(("Netzteil", "net"), " | ", ("Hostteil", "host"))
    table.add_row("", "", legend)
    return table
