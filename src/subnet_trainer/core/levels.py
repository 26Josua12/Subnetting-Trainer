"""Difficulty levels and the prefix ranges they allow."""

from __future__ import annotations

from enum import StrEnum


class Level(StrEnum):
    EASY = "leicht"
    MEDIUM = "mittel"
    HARD = "schwer"

    @property
    def rank(self) -> int:
        return list(Level).index(self)

    @property
    def label(self) -> str:
        return self.value.capitalize()

    def prefix_range(self, *, special: bool = False) -> tuple[int, int]:
        """Inclusive prefix range for this level.

        ``special`` allows the /31 and /32 special cases, which only appear on HARD.
        """
        match self:
            case Level.EASY:
                return 24, 30
            case Level.MEDIUM:
                return 16, 30
            case Level.HARD:
                return 8, 32 if special else 30
