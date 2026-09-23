"""Tasks 1–3: network address, broadcast address and usable host range."""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cached_property
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import dotted, mask_int, random_host
from subnet_trainer.core.explain import BlockCalc, Explanation, special_prefix_note
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_ipv4, parse_range
from subnet_trainer.core.tasks.base import Field, Task, TaskKind

_MASK_NOTATION_CHANCE = 0.3


def notation(ip: IPv4Address, prefix: int, as_mask: bool) -> str:
    """'172.16.45.200/21' or '172.16.45.200 mit Maske 255.255.248.0'."""
    if as_mask:
        return f"{ip} mit Maske {dotted(mask_int(prefix))}"
    return f"{ip}/{prefix}"


def choose_mask_notation(rng: random.Random, level: Level) -> bool:
    return level is not Level.EASY and rng.random() < _MASK_NOTATION_CHANCE


def show_range(value: tuple[IPv4Address, IPv4Address]) -> str:
    return f"{value[0]} - {value[1]}"


@dataclass(frozen=True)
class AddressTask(Task):
    """Base for tasks that give an address plus prefix."""

    ip: IPv4Address
    prefix_len: int
    as_mask: bool = False

    allow_special: ClassVar[bool] = True
    """Whether /31 and /32 may be generated (HARD only)."""

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        prefix = rng.randint(*level.prefix_range(special=cls.allow_special))
        return cls(random_host(rng, level, prefix), prefix, choose_mask_notation(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def notation(self) -> str:
        return notation(self.ip, self.prefix_len, self.as_mask)

    @cached_property
    def calc(self) -> BlockCalc:
        return BlockCalc(int(self.ip), self.prefix_len)

    @cached_property
    def reference(self) -> IPv4Network:
        return IPv4Network((int(self.ip), self.prefix_len), strict=False)

    def base_steps(self) -> list[str]:
        c = self.calc
        return [c.step_mask(), c.step_block(), c.step_multiples()]

    def hint(self) -> str:
        return self.calc.hint()


@dataclass(frozen=True)
class NetworkTask(AddressTask):
    kind: ClassVar[TaskKind] = TaskKind.NETWORK
    variant: ClassVar[str] = "network"

    @property
    def question(self) -> str:
        return f"Wie lautet die Netzadresse von {self.notation}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Netzadresse", "z. B. 192.168.1.0", parse_ipv4),)

    def solution(self) -> tuple[IPv4Address]:
        return (self.reference.network_address,)

    def explain(self) -> Explanation:
        c = self.calc
        return Explanation(
            steps=(*self.base_steps(), c.step_network()),
            result=(IPv4Address(c.network),),
            binary=c.binary_rows(),
            note=special_prefix_note(self.prefix_len),
        )


@dataclass(frozen=True)
class BroadcastTask(AddressTask):
    kind: ClassVar[TaskKind] = TaskKind.BROADCAST
    variant: ClassVar[str] = "broadcast"
    allow_special: ClassVar[bool] = False  # /31 and /32 have no broadcast address

    @property
    def question(self) -> str:
        return f"Wie lautet die Broadcast-Adresse von {self.notation}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Broadcast", "z. B. 192.168.1.255", parse_ipv4),)

    def solution(self) -> tuple[IPv4Address]:
        return (self.reference.broadcast_address,)

    def explain(self) -> Explanation:
        c = self.calc
        return Explanation(
            steps=(*self.base_steps(), c.step_network(), c.step_broadcast()),
            result=(IPv4Address(c.broadcast),),
            binary=c.binary_rows(),
        )


@dataclass(frozen=True)
class HostRangeTask(AddressTask):
    kind: ClassVar[TaskKind] = TaskKind.HOST_RANGE
    variant: ClassVar[str] = "host-range"

    @property
    def question(self) -> str:
        return (
            f"Was ist die erste und die letzte nutzbare Host-Adresse im Netz von {self.notation}?"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        if self.prefix_len == 32:
            return (
                Field(
                    "Host-Bereich",
                    "Format: erste - letzte (bei nur einer Adresse genügt diese)",
                    lambda raw: parse_range(raw, allow_single=True),
                    show_range,
                ),
            )
        return (
            Field(
                "Host-Bereich",
                "Format: erste - letzte, z. B. 10.0.0.1 - 10.0.0.14",
                parse_range,
                show_range,
            ),
        )

    def solution(self) -> tuple[tuple[IPv4Address, IPv4Address]]:
        net = self.reference
        if self.prefix_len == 32:
            return ((net[0], net[0]),)
        if self.prefix_len == 31:
            return ((net[0], net[1]),)
        return ((net[1], net[-2]),)

    def explain(self) -> Explanation:
        c = self.calc
        steps = [*self.base_steps(), c.step_network()]
        if self.prefix_len == 32:
            first = last = c.network
            steps.append(f"Bei /32 ist {dotted(first)} zugleich erste und letzte Adresse.")
        elif self.prefix_len == 31:
            first, last = c.network, c.broadcast
            steps.append(
                f"Bei /31 sind beide Adressen nutzbar: {dotted(first)} und {dotted(last)}."
            )
        else:
            steps.append(c.step_broadcast())
            first, last = c.network + 1, c.broadcast - 1
            steps.append(
                f"Erste nutzbare = Netzadresse + 1 → {dotted(first)}; "
                f"letzte nutzbare = Broadcast − 1 → {dotted(last)}."
            )
        return Explanation(
            steps=tuple(steps),
            result=((IPv4Address(first), IPv4Address(last)),),
            binary=c.binary_rows(),
            note=special_prefix_note(self.prefix_len),
        )
