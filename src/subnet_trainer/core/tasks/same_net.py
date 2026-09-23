"""Task 7: do two addresses share a subnet?"""

from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import ALL_ONES, block_size, dotted, mask_int, random_host
from subnet_trainer.core.explain import BinaryRow, BlockCalc, Explanation
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_yes_no
from subnet_trainer.core.tasks.address import choose_mask_notation
from subnet_trainer.core.tasks.base import Field, Task, TaskKind


def show_yes_no(value: bool) -> str:
    return "ja" if value else "nein"


@dataclass(frozen=True)
class SameNetTask(Task):
    first: IPv4Address
    second: IPv4Address
    prefix_len: int
    as_mask: bool = False

    kind: ClassVar[TaskKind] = TaskKind.SAME_NET
    variant: ClassVar[str] = "same-net"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        prefix = rng.randint(*level.prefix_range())
        first = int(random_host(rng, level, prefix))
        size = block_size(prefix)
        network = first & mask_int(prefix)
        if rng.random() < 0.5:
            # Same subnet: another usable host of the same block.
            second = network + _other_offset(rng, size, first - network)
        else:
            # Neighbouring subnet: close enough to be tempting.
            direction = rng.choice((-1, 1))
            neighbour = network + direction * size
            if not 0 <= neighbour <= ALL_ONES - size + 1:
                neighbour = network - direction * size
            second = neighbour + rng.randint(1, size - 2)
        pair = (IPv4Address(first), IPv4Address(second))
        if rng.random() < 0.5:
            pair = pair[::-1]
        return cls(pair[0], pair[1], prefix, choose_mask_notation(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def question(self) -> str:
        mask = (
            f"der Maske {dotted(mask_int(self.prefix_len))}"
            if self.as_mask
            else f"dem Präfix /{self.prefix_len}"
        )
        return f"Liegen {self.first} und {self.second} bei {mask} im selben Subnetz?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Gleiches Subnetz?", "ja oder nein", parse_yes_no, show_yes_no),)

    def solution(self) -> tuple[bool]:
        return (self.second in IPv4Network((int(self.first), self.prefix_len), strict=False),)

    def hint(self) -> str:
        c = BlockCalc(int(self.first), self.prefix_len)
        return f"Berechne für beide Adressen die Netzadresse. {c.hint()}"

    def explain(self) -> Explanation:
        a = BlockCalc(int(self.first), self.prefix_len)
        b = BlockCalc(int(self.second), self.prefix_len)
        same = a.network == b.network
        steps = [
            a.step_mask(),
            a.step_block(),
            f"{a.step_multiples(str(self.first))} Netz {dotted(a.network)}.",
            f"{b.step_multiples(str(self.second))} Netz {dotted(b.network)}.",
            (
                f"Beide Netzadressen sind gleich ({dotted(a.network)}) → ja, gleiches Subnetz."
                if same
                else f"{dotted(a.network)} ≠ {dotted(b.network)} → nein, verschiedene Subnetze."
            ),
        ]
        binary = (
            BinaryRow(str(self.first), a.address, self.prefix_len),
            BinaryRow(str(self.second), b.address, self.prefix_len),
            BinaryRow("Maske", a.mask, self.prefix_len),
        )
        return Explanation(steps=tuple(steps), result=(same,), binary=binary)


def _other_offset(rng: random.Random, size: int, taken: int) -> int:
    while True:
        offset = rng.randint(1, size - 2)
        if offset != taken:
            return offset
