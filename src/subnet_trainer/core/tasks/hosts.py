"""Task 4: usable hosts for a prefix, and the prefix needed for a number of hosts."""

from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import dotted, german_int, mask_int, usable_hosts
from subnet_trainer.core.explain import Explanation, special_prefix_note
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_int, parse_prefix_or_mask
from subnet_trainer.core.tasks.address import choose_mask_notation
from subnet_trainer.core.tasks.base import Field, Task, TaskKind


def show_prefix(prefix: int) -> str:
    return f"/{prefix}"


def prefix_field(label: str = "Präfix") -> Field[int]:
    return Field(label, "z. B. /23 oder 255.255.254.0", parse_prefix_or_mask, show_prefix)


def reference_usable_hosts(prefix: int) -> int:
    """Usable hosts according to ``ipaddress`` (with the RFC 3021 view of /31)."""
    net = IPv4Network((0, prefix))
    if prefix >= 31:
        return len(list(net.hosts())) or 1  # /32: some Python versions yield nothing
    return net.num_addresses - 2


@dataclass(frozen=True)
class HostCountTask(Task):
    """Prefix -> number of usable hosts."""

    prefix_len: int
    as_mask: bool = False

    kind: ClassVar[TaskKind] = TaskKind.HOST_COUNT
    variant: ClassVar[str] = "prefix->hosts"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        prefix = rng.randint(*level.prefix_range(special=True))
        return cls(prefix, choose_mask_notation(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def question(self) -> str:
        what = (
            f"der Maske {dotted(mask_int(self.prefix_len))}"
            if self.as_mask
            else f"dem Präfix /{self.prefix_len}"
        )
        return f"Wie viele nutzbare Host-Adressen hat ein Subnetz mit {what}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Anzahl Hosts", "eine Zahl, z. B. 30", parse_int, german_int),)

    def solution(self) -> tuple[int]:
        return (reference_usable_hosts(self.prefix_len),)

    def hint(self) -> str:
        return "Hostbits = 32 − Präfix. Nutzbare Hosts = 2^Hostbits − 2 (Netz und Broadcast)."

    def explain(self) -> Explanation:
        p = self.prefix_len
        h = 32 - p
        steps = []
        if self.as_mask:
            steps.append(f"Maske {dotted(mask_int(p))} = /{p}.")
        steps.append(f"Hostbits = 32 − {p} = {h}.")
        steps.append(f"2^{h} = {german_int(2**h)} Adressen im Block.")
        if p <= 30:
            steps.append(
                f"Minus Netzadresse und Broadcast: {german_int(2**h)} − 2 = "
                f"{german_int(2**h - 2)} nutzbare Hosts."
            )
        elif p == 31:
            steps.append("Bei /31 wird nichts abgezogen (RFC 3021): 2 nutzbare Adressen.")
        else:
            steps.append("Bei /32 gibt es genau eine Adresse – den Host selbst.")
        return Explanation(
            steps=tuple(steps), result=(usable_hosts(p),), note=special_prefix_note(p)
        )


@dataclass(frozen=True)
class PrefixForHostsTask(Task):
    """Required hosts -> longest prefix that still fits."""

    hosts: int

    kind: ClassVar[TaskKind] = TaskKind.HOST_COUNT
    variant: ClassVar[str] = "hosts->prefix"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        low, high = level.prefix_range()
        prefix = rng.randint(low, min(high, 30))
        most = usable_hosts(prefix)
        least = usable_hosts(prefix + 1) + 1 if prefix < 30 else 2
        roll = rng.random()
        if roll < 0.15:
            hosts = most  # exactly fits: 62 -> /26
        elif roll < 0.3:
            hosts = least  # just one too many for the smaller subnet: 63 -> /25
        else:
            hosts = rng.randint(least, most)
        return cls(hosts)

    @property
    def prefix(self) -> int:
        return self.solution()[0]

    @property
    def question(self) -> str:
        return (
            f"Ein Subnetz muss mindestens {german_int(self.hosts)} Hosts aufnehmen. "
            "Welches ist das längste Präfix (also das kleinste Subnetz), das reicht?"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (prefix_field(),)

    def solution(self) -> tuple[int]:
        for prefix in range(30, 0, -1):
            if IPv4Network((0, prefix)).num_addresses - 2 >= self.hosts:
                return (prefix,)
        raise ValueError(f"{self.hosts} hosts do not fit into IPv4")

    def hint(self) -> str:
        return (
            f"Suche die kleinste Zweierpotenz, für die 2^h − 2 ≥ {german_int(self.hosts)} gilt. "
            "Präfix = 32 − h."
        )

    def explain(self) -> Explanation:
        n = self.hosts
        h = 2
        while 2**h - 2 < n:
            h += 1
        steps = [f"Gesucht: die wenigsten Hostbits h mit 2^h − 2 ≥ {german_int(n)}."]
        if h > 2:
            steps.append(
                f"h = {h - 1}: 2^{h - 1} − 2 = {german_int(2 ** (h - 1) - 2)} – "
                f"zu wenig für {german_int(n)}."
            )
        steps.append(f"h = {h}: 2^{h} − 2 = {german_int(2**h - 2)} – reicht.")
        steps.append(f"Präfix = 32 − {h} = /{32 - h} (Maske {dotted(mask_int(32 - h))}).")
        return Explanation(steps=tuple(steps), result=(32 - h,))
