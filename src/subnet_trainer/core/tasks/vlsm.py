"""Task 9: VLSM – allocate subnets for several host requirements, largest first."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import dotted, random_network, usable_hosts
from subnet_trainer.core.explain import Explanation
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_network
from subnet_trainer.core.tasks.base import CheckResult, Field, FieldResult, Task, TaskKind

Subnet = tuple[IPv4Address, int]


@dataclass(frozen=True)
class Requirement:
    name: str
    hosts: int


def show_subnet(value: Subnet) -> str:
    return f"{value[0]}/{value[1]}"


def host_prefix(hosts: int) -> int:
    """Longest prefix with enough usable hosts (at most /30), by own arithmetic."""
    host_bits = 2
    while 2**host_bits - 2 < hosts:
        host_bits += 1
    return 32 - host_bits


def _reference_prefix(hosts: int) -> int:
    return max(p for p in range(1, 31) if IPv4Network((0, p)).num_addresses - 2 >= hosts)


@dataclass(frozen=True)
class VlsmTask(Task):
    network: IPv4Address
    base_prefix: int
    requirements: tuple[Requirement, ...]
    """In the order they are presented (and asked)."""

    kind: ClassVar[TaskKind] = TaskKind.VLSM
    variant: ClassVar[str] = "vlsm"
    min_level: ClassVar[Level] = Level.HARD

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        match level:
            case Level.EASY:
                base, lans, wans = 24, rng.randint(2, 3), 0
            case Level.MEDIUM:
                base, lans, wans = rng.choice((23, 24)), rng.randint(3, 4), rng.randint(0, 1)
            case Level.HARD:
                base, lans, wans = rng.randint(20, 24), rng.randint(3, 5), rng.randint(1, 2)
        capacity = 2 ** (32 - base)
        while True:
            hosts = _distinct_host_counts(rng, lans, capacity)
            sizes = [2 ** (32 - host_prefix(h)) for h in hosts] + [4] * wans
            used = sum(sizes)
            # Fits, and uses a good part of the space so the plan is not trivial.
            if used <= capacity and used >= capacity // 2:
                break
        reqs = [Requirement(f"LAN {chr(ord('A') + i)}", h) for i, h in enumerate(hosts)]
        reqs += [Requirement(f"WAN {i + 1}", 2) for i in range(wans)]
        rng.shuffle(reqs)
        return cls(random_network(rng, level, base), base, tuple(reqs))

    @property
    def prefix(self) -> int:
        return self.base_prefix

    @property
    def ordered(self) -> list[Requirement]:
        """Allocation order: most hosts first (ties keep presentation order)."""
        return sorted(self.requirements, key=lambda r: -r.hosts)

    @property
    def question(self) -> str:
        lines = [
            f"Plane das Netz {self.network}/{self.base_prefix} mit VLSM. Vergib die Subnetze "
            "lückenlos ab der ersten Adresse, das größte zuerst:"
        ]
        lines += [
            f"  • {r.name}: {r.hosts} Host{'s' if r.hosts != 1 else ''}"
            + (" (Punkt-zu-Punkt-Link)" if r.name.startswith("WAN") else "")
            for r in self.requirements
        ]
        return "\n".join(lines)

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return tuple(
            Field(f"{r.name} ({r.hosts} Hosts)", "Netz/Präfix", parse_network, show_subnet)
            for r in self.requirements
        )

    def _allocation(self) -> dict[str, Subnet]:
        """Reference allocation computed with ipaddress."""
        allocation: dict[str, Subnet] = {}
        current = IPv4Network((int(self.network), self.base_prefix)).network_address
        for req in self.ordered:
            subnet = IPv4Network((int(current), _reference_prefix(req.hosts)))  # strict
            allocation[req.name] = (subnet.network_address, subnet.prefixlen)
            current = subnet.broadcast_address + 1
        return allocation

    def solution(self) -> tuple[Subnet, ...]:
        allocation = self._allocation()
        return tuple(allocation[r.name] for r in self.requirements)

    def check(self, answer: Sequence[Any]) -> CheckResult:
        """Requirements that need the same block size may be swapped among each other."""
        expected = self.solution()
        pools: dict[int, list[Subnet]] = {}
        for subnet in expected:
            pools.setdefault(subnet[1], []).append(subnet)
        fields = []
        for field, given, exp in zip(self.fields, answer, expected, strict=True):
            pool = pools.get(exp[1], [])
            correct = given[1] == exp[1] and given in pool
            if correct:
                pool.remove(given)  # each subnet may be used only once
            fields.append(
                FieldResult(
                    label=field.label,
                    correct=correct,
                    given=show_subnet(given),
                    expected=show_subnet(exp),
                )
            )
        return CheckResult(tuple(fields))

    def hint(self) -> str:
        first = self.ordered[0]
        return (
            f"Sortiere nach Größe und fang mit {first.name} ({first.hosts} Hosts) an: "
            "kleinste Zweierpotenz mit 2^h − 2 ≥ Hosts, Präfix = 32 − h."
        )

    def explain(self) -> Explanation:
        order = ", ".join(f"{r.name} ({r.hosts})" for r in self.ordered)
        steps = [f"Nach Hostanzahl sortieren, größte zuerst: {order}."]
        allocation: dict[str, Subnet] = {}
        current = int(self.network)
        end = current + 2 ** (32 - self.base_prefix)
        for req in self.ordered:
            prefix = host_prefix(req.hosts)
            size = 2 ** (32 - prefix)
            host_bits = 32 - prefix
            allocation[req.name] = (IPv4Address(current), prefix)
            steps.append(
                f"{req.name}: {req.hosts} Hosts → 2^{host_bits} − 2 = {usable_hosts(prefix)} "
                f"reicht → /{prefix} (Block {size}) → {dotted(current)}/{prefix} "
                f"bis {dotted(current + size - 1)}."
            )
            current += size
        if current < end:
            steps.append(f"Frei für später: ab {dotted(current)}.")
        else:
            steps.append("Das Netz ist damit komplett belegt.")
        steps.append(
            "Weil jeder Block eine Zweierpotenz ist und die Größen absteigen, liegt jedes "
            "Subnetz automatisch auf einer gültigen Blockgrenze."
        )
        return Explanation(
            steps=tuple(steps),
            result=tuple(allocation[r.name] for r in self.requirements),
        )


def _distinct_host_counts(rng: random.Random, count: int, capacity: int) -> list[int]:
    """Realistic, pairwise different host counts that fit into ``capacity`` addresses."""
    largest = min(capacity // 2 - 2, 1000)
    hosts: set[int] = set()
    while len(hosts) < count:
        # Log-uniform: small LANs are as common as big ones.
        upper_bits = max(3, largest.bit_length())
        bits = rng.randint(3, upper_bits)
        value = rng.randint(2 ** (bits - 1) - 1, min(2**bits - 2, largest))
        if value >= 3:
            hosts.add(value)
    return sorted(hosts, reverse=True)
