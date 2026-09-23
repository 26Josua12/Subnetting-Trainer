"""Task 10: route summarization – the smallest summary route covering all networks."""

from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import dotted, mask_int, random_network, to_octets
from subnet_trainer.core.explain import BinaryRow, Explanation, ordinal
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_network
from subnet_trainer.core.tasks.base import Field, Task, TaskKind
from subnet_trainer.core.tasks.vlsm import Subnet, show_subnet

MAX_NETWORKS = 6


def common_prefix_length(a: int, b: int) -> int:
    """Number of equal leading bits of two 32-bit values."""
    length = 0
    for bit in range(31, -1, -1):
        if (a >> bit) & 1 != (b >> bit) & 1:
            break
        length += 1
    return length


@dataclass(frozen=True)
class SummaryTask(Task):
    networks: tuple[Subnet, ...]

    kind: ClassVar[TaskKind] = TaskKind.SUMMARY
    variant: ClassVar[str] = "summary"
    min_level: ClassVar[Level] = Level.HARD

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        match level:
            case Level.EASY:
                summary_prefix, component = rng.randint(21, 23), 24
            case Level.MEDIUM:
                summary_prefix = rng.randint(16, 23)
                component = min(24, summary_prefix + rng.randint(1, 3))
            case Level.HARD:
                summary_prefix = rng.randint(8, 27)
                component = min(30, summary_prefix + rng.randint(1, 4))
        summary = int(random_network(rng, level, summary_prefix))
        slots = 2 ** (component - summary_prefix)
        size = 2 ** (32 - component)
        if rng.random() < 0.5 and slots <= MAX_NETWORKS:
            chosen = list(range(slots))  # the classic: a complete contiguous block
        else:
            half = slots // 2
            count = rng.randint(2, min(MAX_NETWORKS, slots))
            # At least one network in each half, so the summary is exactly /summary_prefix.
            picked = {rng.randrange(half), rng.randrange(half, slots)}
            while len(picked) < count:
                picked.add(rng.randrange(slots))
            chosen = sorted(picked)
        networks = [(IPv4Address(summary + i * size), component) for i in chosen]
        if rng.random() < 0.3:
            rng.shuffle(networks)
        return cls(tuple(networks))

    @property
    def prefix(self) -> int:
        return self.solution()[0][1]

    @property
    def question(self) -> str:
        listed = "\n".join(f"  • {show_subnet(n)}" for n in self.networks)
        return f"Wie lautet die kleinste Sammelroute (Summary), die diese Netze abdeckt?\n{listed}"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (
            Field("Sammelroute", "Netz/Präfix, z. B. 172.16.8.0/21", parse_network, show_subnet),
        )

    def solution(self) -> tuple[Subnet]:
        nets = [IPv4Network((int(a), p)) for a, p in self.networks]
        summary = nets[0]
        while not all(n.subnet_of(summary) for n in nets):
            summary = summary.supernet()
        return ((summary.network_address, summary.prefixlen),)

    def hint(self) -> str:
        return (
            "Schreib das Oktett, in dem sich die Netze unterscheiden, binär auf und zähle, "
            "wie viele Bits von links bei allen gleich sind."
        )

    def explain(self) -> Explanation:
        blocks = [(int(a), int(a) + 2 ** (32 - p) - 1) for a, p in self.networks]
        low = min(b[0] for b in blocks)
        high = max(b[1] for b in blocks)
        # Every network lies within [low, high], so their common bits are the summary prefix.
        length = common_prefix_length(low, high)
        summary = low & mask_int(length)
        low_octets, high_octets = to_octets(low), to_octets(high)
        octet = next(i for i in range(4) if low_octets[i] != high_octets[i])
        lo, hi = low_octets[octet], high_octets[octet]
        full = 8 * octet
        same_bits = length - full
        steps = [
            f"Kleinste Adresse: {dotted(low)}, größte Adresse: {dotted(high)} "
            "(Broadcast des höchsten Netzes).",
        ]
        if octet:
            steps.append(
                f"Die ersten {octet} Oktett{'e' if octet != 1 else ''} sind gleich "
                f"({full} Bits). Im {ordinal(octet)} Oktett: {lo} = {lo:08b}, {hi} = {hi:08b}."
            )
        else:
            steps.append(
                f"Schon das 1. Oktett unterscheidet sich: {lo} = {lo:08b}, {hi} = {hi:08b}."
            )
        pattern = f" ({f'{lo:08b}'[:same_bits]}…)" if same_bits else ""
        steps.append(
            f"Von links sind dort {same_bits} Bit{'s' if same_bits != 1 else ''} gleich{pattern} "
            f"→ Präfix = {full} + {same_bits} = /{length}."
        )
        steps.append(
            f"Netzadresse: die gemeinsamen Bits behalten, den Rest auf 0 → "
            f"{dotted(summary)}/{length}."
        )
        binary = tuple(BinaryRow(show_subnet(n), int(n[0]), length) for n in self.networks)
        return Explanation(
            steps=tuple(steps),
            result=((IPv4Address(summary), length),),
            binary=binary,
        )
