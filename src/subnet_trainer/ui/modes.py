"""Interactive training modes built on :class:`~subnet_trainer.session.Session`."""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass

from subnet_trainer.core.parsing import ParseError, parse_yes_no
from subnet_trainer.core.tasks.base import Task, TaskKind
from subnet_trainer.session import Session
from subnet_trainer.stats.models import Mode, Outcome
from subnet_trainer.ui.prompt import Attempt, LineReader, QuitRequested, TimeUp, ask_task
from subnet_trainer.ui.render import Renderer

SPEED_SECONDS = 120


@dataclass
class ModeContext:
    renderer: Renderer
    read: LineReader
    kinds: list[TaskKind] | None = None
    intro_details: str | None = None


def run_practice(ctx: ModeContext, session: Session, count: int | None) -> None:
    """Drill-style loop (drill, weak, ipv6): immediate feedback and explanations, hints allowed."""
    r = ctx.renderer
    r.intro(
        session.mode, session.level, seed=session.seed, kinds=ctx.kinds, details=ctx.intro_details
    )
    number = 0
    try:
        while count is None or number < count:
            task = session.next_task()
            number += 1
            r.task(task, number, count, session.level)
            attempt = ask_task(task, ctx.read, on_hint=r.hint, on_error=r.input_error)
            session.record(
                task, attempt.outcome, hint_used=attempt.hint_used, seconds=attempt.seconds
            )
            r.feedback(task, attempt)
    except QuitRequested:
        pass
    except (KeyboardInterrupt, EOFError):
        r.console.print("\n[muted]Abgebrochen – dein Fortschritt ist gespeichert.[/]")
    finally:
        session.finish()
    r.summary(session)


def run_exam(ctx: ModeContext, session: Session, count: int, time_limit: int) -> None:
    """Exam simulation: fixed number of questions, time limit, no hints, results at the end."""
    r = ctx.renderer
    r.intro(
        session.mode,
        session.level,
        seed=session.seed,
        details=(
            f"{count} Fragen · {time_limit} s pro Frage · keine Hinweise · Auswertung erst am Ende"
        ),
        commands="[muted]s[/] überspringen · [muted]q[/] Prüfung abbrechen",
    )
    results: list[tuple[Task, Attempt]] = []
    interrupted = False
    try:
        for number in range(1, count + 1):
            task = session.next_task()
            r.task(task, number, count, session.level)
            deadline = time.monotonic() + time_limit
            attempt = ask_task(
                task,
                ctx.read,
                on_hint=r.hint,
                on_error=r.input_error,
                allow_hints=False,
                deadline=deadline,
                timer_icon=r.symbols.timer,
            )
            session.record(task, attempt.outcome, hint_used=False, seconds=attempt.seconds)
            results.append((task, attempt))
            r.exam_ack(attempt)
    except QuitRequested:
        r.console.print("[warn]Prüfung abgebrochen.[/]")
    except (KeyboardInterrupt, EOFError):
        interrupted = True
        r.console.print("\n[muted]Abgebrochen – deine Antworten sind gespeichert.[/]")
    finally:
        session.finish()
    r.exam_report(results, count)
    wrong = [
        (number, task, attempt)
        for number, (task, attempt) in enumerate(results, 1)
        if attempt.outcome is not Outcome.CORRECT
    ]
    if (
        wrong
        and not interrupted
        and confirm(ctx, "Erklärungen zu den falschen Antworten anzeigen?")
    ):
        for number, task, attempt in wrong:
            r.review(task, attempt, number)


def run_speed(ctx: ModeContext, session: Session, duration: int = SPEED_SECONDS) -> None:
    """As many correct answers as possible within ``duration`` seconds; keeps a highscore."""
    r = ctx.renderer
    store = session.store
    previous = None
    if store is not None:
        with contextlib.suppress(OSError):
            previous = store.highscore(Mode.SPEED, session.level.value)
    minutes = f"{duration // 60} Minuten" if duration % 60 == 0 else f"{duration} Sekunden"
    record_line = f"Highscore ({session.level.label}): {previous.score}" if previous else ""
    r.intro(
        session.mode,
        session.level,
        seed=session.seed,
        details=f"{minutes} · so viele richtige Antworten wie möglich · keine Hinweise"
        + (f"\n{record_line}" if record_line else ""),
        commands="[muted]s[/] überspringen · [muted]q[/] abbrechen",
    )
    try:
        ctx.read("[bold]Enter[/] drücken, um zu starten … ", None)
    except (KeyboardInterrupt, EOFError):
        return
    deadline = time.monotonic() + duration
    finished = False
    number = 0
    try:
        while time.monotonic() < deadline:
            task = session.next_task()
            number += 1
            r.speed_task(task, number)
            attempt = ask_task(
                task,
                ctx.read,
                on_hint=r.hint,
                on_error=r.input_error,
                allow_hints=False,
                deadline=deadline,
                timer_icon=r.symbols.timer,
            )
            if attempt.outcome is Outcome.TIMEOUT:
                break  # the unfinished last question does not count
            session.record(task, attempt.outcome, hint_used=False, seconds=attempt.seconds)
            r.speed_feedback(task, attempt)
        finished = True
    except QuitRequested:
        r.console.print("[warn]Abgebrochen – ohne Wertung für den Highscore.[/]")
    except (KeyboardInterrupt, EOFError):
        r.console.print("\n[muted]Abgebrochen – ohne Wertung für den Highscore.[/]")
    finally:
        session.finish()
    score = session.count(Outcome.CORRECT)
    new_record = False
    if finished:
        r.console.print(f"\n[bold]{r.symbols.timer} Zeit ist um![/]")
        if store is not None:
            try:
                store.submit_highscore(Mode.SPEED, session.level.value, score)
                new_record = score > 0 and (previous is None or score > previous.score)
            except OSError as exc:
                session.storage_error = f"Highscore konnte nicht gespeichert werden: {exc}"
    r.speed_result(score, previous, finished=finished, new_record=new_record)
    r.summary(session)


def confirm(ctx: ModeContext, question: str) -> bool:
    """Ask a yes/no question; Ctrl+C or EOF count as 'no'."""
    prompt = f"{question} [muted](ja/nein)[/] [cyan]›[/] "
    while True:
        try:
            raw = ctx.read(prompt, None)
        except (KeyboardInterrupt, EOFError, TimeUp):
            return False
        try:
            return parse_yes_no(raw)
        except ParseError as exc:
            ctx.renderer.input_error(str(exc))
