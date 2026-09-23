"""Status icons, with a plain fallback for Windows consoles whose fonts lack emoji."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from rich.console import Console

# Set to 1 to force the plain symbols, 0 to force the Unicode/emoji ones.
PLAIN_ENV = "SUBNET_TRAINER_EINFACH"


@dataclass(frozen=True)
class Symbols:
    ok: str = "✔"
    wrong: str = "✘"
    skip: str = "↷"
    timer: str = "⏱"
    hint: str = "💡"
    warn: str = "⚠"
    info: str = "ℹ"
    trophy: str = "🏆"


UNICODE = Symbols()
# Plain ASCII: displayable by every Windows console font and code page.
PLAIN = Symbols(
    ok="OK", wrong="X", skip=">>", timer="Zeit", hint="->", warn="!", info="i", trophy="*"
)


def _modern_windows_terminal() -> bool:
    """Windows Terminal, VS Code and ConEmu render emoji; the classic console host does not."""
    return bool(
        os.environ.get("WT_SESSION")
        or os.environ.get("TERM_PROGRAM") == "vscode"
        or os.environ.get("CONEMUANSI") == "ON"  # Windows env names are case-insensitive
    )


def symbols_for(console: Console, *, windows: bool | None = None) -> Symbols:
    override = os.environ.get(PLAIN_ENV, "").strip()
    if override in ("1", "0"):
        return PLAIN if override == "1" else UNICODE
    windows = sys.platform == "win32" if windows is None else windows
    if windows and console.is_terminal and not _modern_windows_terminal():
        return PLAIN
    return UNICODE
