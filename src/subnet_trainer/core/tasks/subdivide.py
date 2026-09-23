"""Task 8: split a network into N equally sized subnets."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import dotted, german_int, mask_int, random_network
from subnet_trainer.core.explain import BlockCalc, Explanation, ordinal
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import ParseError, parse_ipv4, parse_network, split_list
from subnet_trainer.core.tasks.base import Field, Task, TaskKind
from subnet_trainer.core.tasks.hosts import prefix_field

MAX_LISTED = 6


def show_addresses(addresses: Sequence[IPv4Address]) -> str:
    return ", ".join(str(a) for a in addresses)


def parse_subnet_addresses(raw: str, expected_count: int) -> list[IPv4Address]:
    """A list of network addresses; a '/nn' suffix per entry is tolerated and ignored."""
    addresses = [parse_network(p)[0] if "/" in p else parse_ipv4(p) for p in split_list(raw)]
    if len(addresses) != expected_count:
        raise ParseError(
            f"Bitte genau {expected_count} Netzadressen eingeben (du hast {len(addresses)})."
        )
    return addresses


def bits_needed(count: int) -> int:
    """Borrowed bits so that 2^bits >= count (own arithmetic, no logarithms)."""
    bits = 0
    while 2**bits < count:
        bits += 1
    return bits


@dataclass(frozen=True)
class SubdivideTask(Task):
    network: IPv4Address
    base_prefix: int
    count: int

    kind: ClassVar[TaskKind] = TaskKind.SUBDIVIDE
    variant: ClassVar[str] = "subdivide"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        match level:
            case Level.EASY:
                base, max_count = 24, 8
            case Level.MEDIUM:
                base, max_count = rng.randint(16, 24), 12
            case Level.HARD:
                base, max_count = rng.randint(8, 26), 16
        # Prefer counts that are not a power of two: they are the interesting ones.
        counts = [c for c in range(3, max_count + 1) if c & (c - 1)]
        count = rng.choice(counts) if rng.random() < 0.8 else rng.choice((2, 4, 8))
        while base + bits_needed(count) > 30:
            count = max(2, count // 2)
        return cls(random_network(rng, level, base), base, count)

    @property
    def listed(self) -> int:
        return min(self.count, MAX_LISTED)

    @property
    def new_prefix(self) -> int:
        return self.base_prefix + bits_needed(self.count)

    @property
    def prefix(self) -> int:
        return self.new_prefix

    @property
    def question(self) -> str:
        which = (
            f"alle {self.count} Subnetze"
            if self.listed == self.count
            else f"die ersten {self.listed} Subnetze"
        )
        return (
            f"Teile {self.network}/{self.base_prefix} in {self.count} gleich große Subnetze "
            f"(so groß wie möglich). Welches Präfix haben die Subnetze, und wie lauten die "
            f"Netzadressen für {which}?"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        n = self.listed
        return (
            prefix_field("Neues Präfix"),
            Field(
                "Netzadressen",
                f"{n} Adressen, durch Komma getrennt",
                lambda raw: parse_subnet_addresses(raw, n),
                show_addresses,
                lambda given, expected: sorted(given) == sorted(expected),
            ),
        )

    def solution(self) -> tuple[int, list[IPv4Address]]:
        net = IPv4Network((int(self.network), self.base_prefix))
        prefix = next(
            p
            for p in range(self.base_prefix, 33)
            if net.num_addresses // IPv4Network((0, p)).num_addresses >= self.count
        )
        subnets = net.subnets(new_prefix=prefix)
        return prefix, [next(subnets).network_address for _ in range(self.listed)]

    def hint(self) -> str:
        return (
            f"Wie viele Bits musst du leihen, damit 2^Bits ≥ {self.count}? "
            f"Neues Präfix = /{self.base_prefix} + geliehene Bits."
        )

    def explain(self) -> Explanation:
        bits = bits_needed(self.count)
        prefix = self.base_prefix + bits
        calc = BlockCalc(int(self.network), prefix)
        step = calc.block_size * 256 ** (3 - calc.octet_index)
        addresses = [int(self.network) + i * step for i in range(self.listed)]
        host_bits = 32 - prefix
        steps = [
            f"{self.count} Subnetze: 2^{bits} = {2**bits} ≥ {self.count}"
            + (f", 2^{bits - 1} = {2 ** (bits - 1)} reicht nicht" if bits > 1 else "")
            + f" → {bits} Bit{'s' if bits != 1 else ''} leihen.",
            f"Neues Präfix: /{self.base_prefix} + {bits} = /{prefix} "
            f"(Maske {dotted(mask_int(prefix))}).",
        ]
        if calc.on_octet_boundary:
            steps.append(
                f"Das Präfix endet an der Oktettgrenze: die Subnetze zählen im "
                f"{ordinal(calc.octet_index)} Oktett in 1er-Schritten hoch."
            )
        else:
            steps.append(calc.step_block())
        listed = ", ".join(dotted(a) for a in addresses)
        steps.append(
            f"Ab {self.network} in Schritten von {calc.block_size} im "
            f"{ordinal(calc.octet_index)} Oktett: {listed}"
            + (" …" if self.listed < 2**bits else "")
            + "."
        )
        spare = 2**bits - self.count
        steps.append(
            f"Es entstehen {2**bits} Subnetze mit je {german_int(2**host_bits)} Adressen "
            f"({german_int(max(0, 2**host_bits - 2))} nutzbare Hosts)"
            + (f"; {spare} bleiben als Reserve." if spare else ".")
        )
        return Explanation(
            steps=tuple(steps),
            result=(prefix, [IPv4Address(a) for a in addresses]),
        )
