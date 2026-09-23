"""Tasks 5 and 6: CIDR <-> subnet mask, and wildcard masks."""

from __future__ import annotations

import random
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network
from typing import Any, ClassVar, Literal, Self

from subnet_trainer.core.addressing import (
    MASK_OCTET_VALUES,
    dotted,
    from_octets,
    mask_int,
    mask_octets,
    octet_bits,
    random_network,
    wildcard_octets,
)
from subnet_trainer.core.explain import Explanation, mask_bits_sum, mask_octet_sum
from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import parse_dotted, parse_prefix
from subnet_trainer.core.tasks.base import Field, Task, TaskKind
from subnet_trainer.core.tasks.hosts import prefix_field, show_prefix

_MASK_SEQUENCE = ", ".join(str(v) for v in MASK_OCTET_VALUES[1:])


def _mask_steps(prefix: int) -> list[str]:
    """How to build a mask from a prefix, octet by octet."""
    octets = mask_octets(prefix)
    full = prefix // 8
    rest = prefix % 8
    steps = [f"/{prefix} = {mask_bits_sum(prefix)} Bits."]
    if full:
        steps.append(
            f"{full} volle{'s' if full == 1 else ''} Oktett{'e' if full > 1 else ''} → "
            f"{full} × 255."
        )
    if rest:
        value = octets[full]
        total = f"{mask_octet_sum(value)} = {value}" if rest > 1 else str(value)
        steps.append(
            f"Im {full + 1}. Oktett {rest} Bit{'s' if rest > 1 else ''}: "
            f"{total} (Merkreihe: {_MASK_SEQUENCE})."
        )
    if prefix < 32:
        steps.append(f"Restliche Oktette 0 → {'.'.join(str(o) for o in octets)}.")
    else:
        steps.append(f"Ergebnis: {'.'.join(str(o) for o in octets)}.")
    return steps


def _prefix_from_mask_steps(prefix: int) -> list[str]:
    """How to count the bits of a mask."""
    parts = []
    for value in mask_octets(prefix):
        bits = octet_bits(value)
        parts.append(f"{value} = {bits} Bit{'s' if bits != 1 else ''}")
    return [
        "Bits pro Oktett zählen: " + ", ".join(parts) + ".",
        f"Summe: {mask_bits_sum(prefix)} = /{prefix}.",
    ]


def _level_prefix(rng: random.Random, level: Level) -> int:
    return rng.randint(*level.prefix_range(special=True))


@dataclass(frozen=True)
class PrefixToMaskTask(Task):
    prefix_len: int

    kind: ClassVar[TaskKind] = TaskKind.MASK
    variant: ClassVar[str] = "prefix->mask"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        return cls(_level_prefix(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def question(self) -> str:
        return f"Wie lautet die Subnetzmaske zu /{self.prefix_len}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Subnetzmaske", "z. B. 255.255.255.0", parse_dotted),)

    def solution(self) -> tuple[IPv4Address]:
        return (IPv4Network((0, self.prefix_len)).netmask,)

    def hint(self) -> str:
        return f"Pro volles Oktett 255, im angebrochenen Oktett die Merkreihe {_MASK_SEQUENCE}."

    def explain(self) -> Explanation:
        return Explanation(
            steps=tuple(_mask_steps(self.prefix_len)),
            result=(IPv4Address(from_octets(mask_octets(self.prefix_len))),),
        )


@dataclass(frozen=True)
class MaskToPrefixTask(Task):
    prefix_len: int

    kind: ClassVar[TaskKind] = TaskKind.MASK
    variant: ClassVar[str] = "mask->prefix"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        return cls(_level_prefix(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def mask(self) -> str:
        return dotted(mask_int(self.prefix_len))

    @property
    def question(self) -> str:
        return f"Welches CIDR-Präfix entspricht der Maske {self.mask}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Präfix", "z. B. /27 oder 27", parse_prefix, show_prefix),)

    def solution(self) -> tuple[int]:
        return (IPv4Network(f"0.0.0.0/{self.mask}").prefixlen,)

    def hint(self) -> str:
        return f"Zähle die Einsen: 255 = 8 Bits, in der Merkreihe {_MASK_SEQUENCE} je eins mehr."

    def explain(self) -> Explanation:
        total = sum(octet_bits(v) for v in mask_octets(self.prefix_len))
        return Explanation(steps=tuple(_prefix_from_mask_steps(self.prefix_len)), result=(total,))


WildcardContext = Literal["plain", "mask", "acl", "ospf"]


@dataclass(frozen=True)
class WildcardTask(Task):
    """Prefix (optionally in an ACL/OSPF context) -> wildcard mask."""

    prefix_len: int
    context: WildcardContext = "plain"
    network: IPv4Address | None = None
    acl_number: int = 10

    kind: ClassVar[TaskKind] = TaskKind.WILDCARD
    variant: ClassVar[str] = "prefix->wildcard"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        prefix = _level_prefix(rng, level)
        context: WildcardContext = rng.choice(("plain", "mask", "acl", "ospf"))
        if context in ("acl", "ospf"):
            return cls(
                prefix,
                context,
                random_network(rng, level, prefix),
                rng.choice((1, 10, 15, 20, 50, 99)),
            )
        return cls(prefix, context)

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def question(self) -> str:
        p = self.prefix_len
        match self.context:
            case "acl":
                return (
                    f"Die Standard-ACL soll genau das Netz {self.network}/{p} erlauben. "
                    f"Ergänze die Wildcard-Maske:\n"
                    f"  access-list {self.acl_number} permit {self.network} ___"
                )
            case "ospf":
                return (
                    f"OSPF soll auf allen Interfaces im Netz {self.network}/{p} aktiviert werden. "
                    f"Ergänze die Wildcard-Maske:\n"
                    f"  router ospf 1\n"
                    f"   network {self.network} ___ area 0"
                )
            case "mask":
                return f"Wie lautet die Wildcard-Maske zur Subnetzmaske {dotted(mask_int(p))}?"
            case _:
                return f"Wie lautet die Wildcard-Maske zu /{p}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (Field("Wildcard-Maske", "z. B. 0.0.0.255", parse_dotted),)

    def solution(self) -> tuple[IPv4Address]:
        return (IPv4Network((0, self.prefix_len)).hostmask,)

    def hint(self) -> str:
        return "Wildcard = 255.255.255.255 − Subnetzmaske, Oktett für Oktett."

    def explain(self) -> Explanation:
        p = self.prefix_len
        mask = mask_octets(p)
        wild = wildcard_octets(p)
        diffs = " . ".join(f"255−{m}={w}" for m, w in zip(mask, wild, strict=True))
        steps = [
            f"/{p} = Maske {'.'.join(str(o) for o in mask)}.",
            f"Wildcard = 255 − Maskenoktett, für jedes Oktett: {diffs}.",
            f"→ {'.'.join(str(o) for o in wild)}.",
        ]
        if p % 8 > 0:
            block = 256 - mask[p // 8]
            steps.append(
                f"Probe: Im interessanten Oktett steht Blockgröße − 1 = {block} − 1 = {block - 1}."
            )
        if self.context == "acl" and p == 32:
            steps.append("Tipp: 0.0.0.0 entspricht in einer ACL dem Schlüsselwort 'host'.")
        return Explanation(steps=tuple(steps), result=(IPv4Address(from_octets(wild)),))


@dataclass(frozen=True)
class PrefixFromWildcardTask(Task):
    """Wildcard mask -> prefix."""

    prefix_len: int

    kind: ClassVar[TaskKind] = TaskKind.WILDCARD
    variant: ClassVar[str] = "wildcard->prefix"

    @classmethod
    def generate(cls, rng: random.Random, level: Level) -> Self:
        return cls(_level_prefix(rng, level))

    @property
    def prefix(self) -> int:
        return self.prefix_len

    @property
    def wildcard(self) -> str:
        return ".".join(str(o) for o in wildcard_octets(self.prefix_len))

    @property
    def question(self) -> str:
        return f"Welches Präfix entspricht der Wildcard-Maske {self.wildcard}?"

    @property
    def fields(self) -> tuple[Field[Any], ...]:
        return (prefix_field(),)

    def solution(self) -> tuple[int]:
        # Not "0.0.0.0/<wildcard>": ipaddress would read wildcard 0.0.0.0 as netmask /0.
        wildcard = IPv4Address(self.wildcard)
        return (next(p for p in range(33) if IPv4Network((0, p)).hostmask == wildcard),)

    def hint(self) -> str:
        return "Erst die Maske bilden (255 − Wildcard je Oktett), dann die Einsen zählen."

    def explain(self) -> Explanation:
        wild = wildcard_octets(self.prefix_len)
        mask = tuple(255 - w for w in wild)
        diffs = " . ".join(f"255−{w}={m}" for w, m in zip(wild, mask, strict=True))
        total = sum(octet_bits(v) for v in mask)
        steps = [
            f"Maske = 255 − Wildcard, für jedes Oktett: {diffs}.",
            *_prefix_from_mask_steps(self.prefix_len),
        ]
        return Explanation(steps=tuple(steps), result=(total,))
