"""Task 11 (own mode): IPv6 basics – compress/expand, prefixes, counting /64 subnets."""

from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv6Address, IPv6Network
from typing import Any, ClassVar, Self

from subnet_trainer.core.addressing import german_int
from subnet_trainer.core.explain import Explanation
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_int, parse_ipv6, parse_ipv6_network
from subnet_trainer.core.tasks.base import Field, Task, TaskKind

Hextets = tuple[int, int, int, int, int, int, int, int]


def to_hextets(address: IPv6Address) -> Hextets:
    value = int(address)
    parts = [(value >> (16 * (7 - i))) & 0xFFFF for i in range(8)]
    return parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]


def from_hextets(parts: tuple[int, ...]) -> IPv6Address:
    value = 0
    for part in parts:
        value = (value << 16) | part
    return IPv6Address(value)


def longest_zero_run(parts: tuple[int, ...]) -> tuple[int, int]:
    """(start, length) of the first longest run of zero blocks; length 0 if none."""
    best_start, best_len = -1, 0
    start = None
    for i, part in enumerate((*parts, 1)):  # sentinel closes a trailing run
        if part == 0 and start is None:
            start = i
        elif part != 0 and start is not None:
            if i - start > best_len:
                best_start, best_len = start, i - start
            start = None
    return best_start, best_len


def compress(parts: tuple[int, ...]) -> str:
    """RFC 5952: drop leading zeros, replace the longest run (>= 2 blocks) with '::'."""
    texts = [f"{p:x}" for p in parts]
    start, length = longest_zero_run(parts)
    if length < 2:
        return ":".join(texts)
    return ":".join(texts[:start]) + "::" + ":".join(texts[start + length :])


def expand(parts: tuple[int, ...]) -> str:
    return ":".join(f"{p:04x}" for p in parts)


def parse_ipv6_text(raw: str) -> str:
    """Validate an IPv6 address but keep the notation the user typed (lowercased)."""
    parse_ipv6(raw)
    return "".join(raw.split()).lower()


def show_ipv6_network(value: tuple[IPv6Address, int]) -> str:
    return f"{value[0]}/{value[1]}"


_GLOBAL_PREFIXES: tuple[tuple[int, int], ...] = (
    (0x2001, 0x0DB8),  # documentation prefix, as used in Cisco material
    (0x2001, 0x0DB8),
    (0x2001, 0x0470),
    (0x2A02, 0x08E0),
    (0x2600, 0x1F18),
)


def random_ipv6(rng: random.Random, *, zero_runs: bool = True) -> IPv6Address:
    """A realistic address with the zero runs and small blocks that make compression fun."""
    if rng.random() < 0.15:
        first = (0xFD00 | rng.randrange(256), rng.randrange(0x10000))  # ULA
    else:
        first = rng.choice(_GLOBAL_PREFIXES)

    def block() -> int:
        # Mostly small values, so leading zeros appear in the full notation.
        return rng.choice((rng.randrange(0x10), rng.randrange(0x100), rng.randrange(0x10000)))

    parts = [*first] + [block() for _ in range(6)]
    if zero_runs:
        for _ in range(rng.randint(1, 2)):
            start = rng.randint(2, 7)
            length = rng.randint(1, 8 - start)
            parts[start : start + length] = [0] * length
        if parts[7] == 0 and rng.random() < 0.5:
            parts[7] = rng.choice((1, 2, 0x10, 0xA))
    return from_hextets(tuple(parts))


@dataclass(frozen=True)
class Ipv6CompressTask(Task):
    address: IPv6Address

    kind: ClassVar[TaskKind] = TaskKind.IPV6
    variant: ClassVar[str] = "ipv6-compress"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        return cls(random_ipv6(rng))

    @property
    def question(self) -> str:
        return (
            f"Kürze diese IPv6-Adresse so weit wie möglich:\n  {expand(to_hextets(self.address))}"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Kurzform", "z. B. 2001:db8::1", parse_ipv6_text),)

    def solution(self) -> tuple[str]:
        return (self.address.compressed,)

    def hint(self) -> str:
        return (
            "Führende Nullen jedes Blocks weglassen, dann die längste Folge von Null-Blöcken "
            "(mindestens zwei) durch '::' ersetzen – nur einmal!"
        )

    def explain(self) -> Explanation:
        parts = to_hextets(self.address)
        dropped = ":".join(f"{p:x}" for p in parts)
        start, length = longest_zero_run(parts)
        steps = [
            f"Führende Nullen in jedem Block weglassen: {dropped}.",
        ]
        if length >= 2:
            steps.append(
                f"Längste Folge von Null-Blöcken: Block {start + 1} bis {start + length} "
                f"({length} Blöcke) → durch '::' ersetzen."
            )
        elif length == 1:
            steps.append(
                "Es gibt nur einzelne Null-Blöcke – '::' ersetzt laut RFC 5952 erst ab zwei "
                "Blöcken, also bleibt die 0 stehen."
            )
        else:
            steps.append("Keine Null-Blöcke – hier gibt es kein '::'.")
        result = compress(parts)
        steps.append(f"Ergebnis: {result}.")
        steps.append(
            "Regeln: '::' nur einmal pro Adresse; bei gleich langen Folgen die erste; "
            "Kleinbuchstaben bevorzugt."
        )
        return Explanation(steps=tuple(steps), result=(result,))


@dataclass(frozen=True)
class Ipv6ExpandTask(Task):
    address: IPv6Address

    kind: ClassVar[TaskKind] = TaskKind.IPV6
    variant: ClassVar[str] = "ipv6-expand"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        return cls(random_ipv6(rng))

    @property
    def question(self) -> str:
        return (
            "Schreibe die Adresse vollständig aus (8 Blöcke mit je 4 Hex-Ziffern):\n"
            f"  {self.address.compressed}"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Langform", "z. B. 2001:0db8:0000:…", parse_ipv6_text),)

    def solution(self) -> tuple[str]:
        return (self.address.exploded,)

    def hint(self) -> str:
        return (
            "Jeden Block auf 4 Ziffern auffüllen; '::' steht für so viele 0000-Blöcke, "
            "bis es 8 sind."
        )

    def explain(self) -> Explanation:
        compressed = compress(to_hextets(self.address))
        left, _, right = compressed.partition("::")
        steps = []
        if "::" in compressed:
            n_left = len(left.split(":")) if left else 0
            n_right = len(right.split(":")) if right else 0
            missing = 8 - n_left - n_right
            steps.append(
                f"Vor '::' stehen {n_left}, danach {n_right} Blöcke → '::' ersetzt "
                f"8 − {n_left} − {n_right} = {missing} Null-Blöcke."
            )
        else:
            steps.append("Kein '::' – es sind schon alle 8 Blöcke da.")
        steps.append("Jeden Block mit führenden Nullen auf 4 Hex-Ziffern auffüllen.")
        result = expand(to_hextets(self.address))
        steps.append(f"Ergebnis: {result}.")
        return Explanation(steps=tuple(steps), result=(result,))


@dataclass(frozen=True)
class Ipv6PrefixTask(Task):
    address: IPv6Address
    prefix_len: int

    kind: ClassVar[TaskKind] = TaskKind.IPV6
    variant: ClassVar[str] = "ipv6-prefix"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        match level:
            case Level.EASY:
                prefix = rng.choice((48, 64))
            case Level.MEDIUM:
                prefix = rng.choice((32, 48, 52, 56, 60, 64))
            case Level.HARD:
                prefix = rng.choice((rng.randint(33, 63), 48, 56, 64))
        address = random_ipv6(rng, zero_runs=rng.random() < 0.5)
        # Make sure the prefix actually cuts through non-zero bits.
        parts = list(to_hextets(address))
        full, rest = divmod(prefix, 16)
        for i in range(2, full):
            parts[i] = parts[i] or rng.randrange(1, 0x10000)
        if rest:
            parts[full] = rng.randrange(0x1000, 0x10000)
        return cls(from_hextets(tuple(parts)), prefix)

    @property
    def question(self) -> str:
        return f"Wie lautet das Präfix (die Netzadresse) von {self.address}/{self.prefix_len}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (
            Field(
                "Präfix",
                "Netz/Präfixlänge, z. B. 2001:db8:acad::/48",
                parse_ipv6_network,
                show_ipv6_network,
            ),
        )

    def solution(self) -> tuple[tuple[IPv6Address, int]]:
        net = IPv6Network((int(self.address), self.prefix_len), strict=False)
        return ((net.network_address, net.prefixlen),)

    def hint(self) -> str:
        full, rest = divmod(self.prefix_len, 16)
        split = f"{full} ganze Blöcke" + (f" + {rest} Bits" if rest else "")
        return f"Jeder Block hat 16 Bits, jede Hex-Ziffer 4 Bits. /{self.prefix_len} = {split}."

    def explain(self) -> Explanation:
        p = self.prefix_len
        parts = list(to_hextets(self.address))
        full, rest = divmod(p, 16)
        steps = [f"/{p} = {full} × 16 Bits" + (f" + {rest} Bits." if rest else ".")]
        kept = parts[:full]
        if rest:
            value = parts[full]
            mask = (0xFFFF << (16 - rest)) & 0xFFFF
            kept.append(value & mask)
            if rest % 4 == 0:
                digits = rest // 4
                steps.append(
                    f"Im {full + 1}. Block ({value:04x}) bleiben die ersten {digits} Hex-Ziffer"
                    f"{'n' if digits != 1 else ''}, der Rest wird 0 → {value & mask:04x}."
                )
            else:
                steps.append(
                    f"Im {full + 1}. Block: {value:04x} = {value:016b}; die ersten {rest} Bits "
                    f"behalten → {value & mask:016b} = {value & mask:04x}."
                )
        else:
            steps.append(f"Die ersten {full} Blöcke bleiben, alle weiteren werden 0.")
        result = tuple(kept + [0] * (8 - len(kept)))
        network = from_hextets(result)
        steps.append(f"Ergebnis: {compress(result)}/{p}.")
        return Explanation(steps=tuple(steps), result=((network, p),))


@dataclass(frozen=True)
class Ipv6SubnetCountTask(Task):
    site_prefix: int
    subnet_prefix: int = 64

    kind: ClassVar[TaskKind] = TaskKind.IPV6
    variant: ClassVar[str] = "ipv6-subnet-count"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        match level:
            case Level.EASY:
                return cls(rng.choice((48, 56, 60)), 64)
            case Level.MEDIUM:
                site = rng.choice((32, 40, 44, 48, 52, 56))
                return cls(site, rng.choice((64, 64, min(64, site + 8))))
            case Level.HARD:
                site = rng.randint(32, 60)
                return cls(site, rng.randint(site + 1, min(site + 24, 64)))

    @property
    def question(self) -> str:
        return (
            f"Wie viele /{self.subnet_prefix}-Subnetze kannst du aus einem "
            f"/{self.site_prefix}-Präfix bilden?"
        )

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Anzahl Subnetze", "eine Zahl, z. B. 256", parse_int, german_int),)

    def solution(self) -> tuple[int]:
        site = IPv6Network(("2001:db8::", self.site_prefix)).num_addresses
        subnet = IPv6Network(("2001:db8::", self.subnet_prefix)).num_addresses
        return (site // subnet,)

    def hint(self) -> str:
        return "Anzahl = 2^(Subnetz-Präfix − Site-Präfix)."

    def explain(self) -> Explanation:
        bits = self.subnet_prefix - self.site_prefix
        count = 2**bits
        steps = [
            f"Subnetz-Bits = {self.subnet_prefix} − {self.site_prefix} = {bits}.",
            f"2^{bits} = {german_int(count)} Subnetze.",
        ]
        if self.subnet_prefix == 64 and bits % 4 == 0:
            steps.append(
                f"Anschaulich: {bits // 4} Hex-Ziffer{'n' if bits // 4 != 1 else ''} für die "
                f"Subnetz-ID → 16^{bits // 4} = {german_int(count)}."
            )
        return Explanation(steps=tuple(steps), result=(count,))
