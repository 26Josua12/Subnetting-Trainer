"""Explanation model and the building blocks of the magic-number (block size) method.

All calculations here use octet arithmetic the way a tutor does it on the whiteboard;
nothing is delegated to ``ipaddress``. Tests verify the results against ``ipaddress``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from subnet_trainer.core.addressing import (
    MASK_OCTET_VALUES,
    Octets,
    dotted,
    from_octets,
    mask_octets,
    to_octets,
)


@dataclass(frozen=True)
class BinaryRow:
    """One row of the binary view; the UI colors the first ``prefix`` bits as network part."""

    label: str
    value: int
    prefix: int


@dataclass(frozen=True)
class Explanation:
    steps: tuple[str, ...]
    result: tuple[Any, ...]
    """The solution the step-by-step calculation arrives at (must equal ``Task.solution()``)."""
    binary: tuple[BinaryRow, ...] = ()
    note: str | None = None


def ordinal(index: int) -> str:
    """0-based octet index -> '3.'"""
    return f"{index + 1}."


def mask_bits_sum(prefix: int) -> str:
    """'/21' -> '8 + 8 + 5'"""
    parts = [8] * (prefix // 8)
    if prefix % 8:
        parts.append(prefix % 8)
    return " + ".join(str(p) for p in parts) if parts else "0"


def mask_octet_sum(value: int) -> str:
    """248 -> '128 + 64 + 32 + 16 + 8'"""
    bits = MASK_OCTET_VALUES.index(value)
    return " + ".join(str(128 >> i) for i in range(bits)) if bits else "0"


def _join_octets(parts: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in parts)


@dataclass(frozen=True)
class BlockCalc:
    """The magic-number method for one address and prefix (1 <= prefix <= 32).

    The *interesting octet* is the octet in which the prefix ends. For prefixes on an octet
    boundary (/8, /16, /24, /32) that octet has mask value 255 and block size 1.
    """

    address: int
    prefix: int
    _octets: Octets = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 1 <= self.prefix <= 32:
            raise ValueError(f"prefix out of range: {self.prefix}")
        object.__setattr__(self, "_octets", to_octets(self.address))

    @property
    def octet_index(self) -> int:
        return (self.prefix - 1) // 8

    @property
    def bits_in_octet(self) -> int:
        return self.prefix - 8 * self.octet_index

    @property
    def mask_octet(self) -> int:
        return MASK_OCTET_VALUES[self.bits_in_octet]

    @property
    def block_size(self) -> int:
        return 256 - self.mask_octet

    @property
    def address_octet(self) -> int:
        return self._octets[self.octet_index]

    @property
    def network_octet(self) -> int:
        return self.address_octet // self.block_size * self.block_size

    @property
    def broadcast_octet(self) -> int:
        return self.network_octet + self.block_size - 1

    @cached_property
    def mask(self) -> int:
        return from_octets(mask_octets(self.prefix))

    @cached_property
    def network(self) -> int:
        i = self.octet_index
        return from_octets((*self._octets[:i], self.network_octet, *[0] * (3 - i)))

    @cached_property
    def broadcast(self) -> int:
        i = self.octet_index
        return from_octets((*self._octets[:i], self.broadcast_octet, *[255] * (3 - i)))

    @property
    def on_octet_boundary(self) -> bool:
        return self.bits_in_octet == 8

    # --- whiteboard sentences --------------------------------------------------------------

    def _net_part(self) -> str:
        return _join_octets(self._octets[: self.octet_index + 1])

    def step_mask(self) -> str:
        o = ordinal(self.octet_index)
        head = f"/{self.prefix} = {mask_bits_sum(self.prefix)} Bits → Maske {dotted(self.mask)}."
        if self.prefix == 32:
            return f"{head} Alle 32 Bits sind Netzbits."
        if self.on_octet_boundary:
            return f"{head} Das Präfix endet genau an der Oktettgrenze nach dem {o} Oktett."
        return (
            f"{head} Das interessante Oktett ist das {o} – dort steht {self.mask_octet} "
            f"({self.bits_in_octet} Netzbit{'s' if self.bits_in_octet > 1 else ''}: "
            f"{mask_octet_sum(self.mask_octet)})."
        )

    def step_block(self) -> str:
        if self.prefix == 32:
            return "Es gibt keinen Hostteil – die Adresse ist ihr eigenes Netz."
        if self.on_octet_boundary:
            return (
                f"Kein angebrochenes Oktett: die ersten {self.octet_index + 1} Oktette sind "
                "Netzteil, der Rest ist Hostteil. Eine Blockgröße braucht man hier nicht."
            )
        o = ordinal(self.octet_index)
        return (
            f"Blockgröße (Magic Number) im {o} Oktett = "
            f"256 − {self.mask_octet} = {self.block_size}."
        )

    def step_multiples(self, label: str | None = None) -> str:
        who = f"{label}: " if label else ""
        if self.on_octet_boundary:
            return f"{who}Netzteil ist {self._net_part()}."
        o = ordinal(self.octet_index)
        b, v, n = self.block_size, self.address_octet, self.network_octet
        start = max(0, n - 2 * b)
        stop = min(256, n + 2 * b)
        seq = ", ".join(str(m) for m in range(start, stop + 1, b))
        lead = "… " if start > 0 else ""
        tail = " …" if stop < 256 else ""
        return (
            f"{who}Vielfache von {b} im {o} Oktett: {lead}{seq}{tail} → "
            f"{v} liegt im Block {n}–{n + b - 1}."
        )

    def _step_edge(self, what: str, octet_value: int, fill: int, value: int, extra: str) -> str:
        """Shared wording for network (fill 0) and broadcast (fill 255) address."""
        if self.prefix == 32:
            return f"{what} = die Adresse selbst → {dotted(value)}."
        if self.on_octet_boundary:
            return (
                f"{what}: Netzteil {self._net_part()} übernehmen, Hostteil auf {fill} "
                f"→ {dotted(value)}."
            )
        i = self.octet_index
        parts = []
        if i > 0:
            parts.append(f"Oktette davor übernehmen ({_join_octets(self._octets[:i])})")
        parts.append(f"das {ordinal(i)} Oktett wird {octet_value}{extra}")
        if i < 3:
            parts.append(f"alle Oktette danach werden {fill}")
        return f"{what}: {', '.join(parts)} → {dotted(value)}."

    def step_network(self) -> str:
        return self._step_edge("Netzadresse", self.network_octet, 0, self.network, "")

    def step_broadcast(self) -> str:
        nxt = self.network_octet + self.block_size
        extra = f" (eins vor dem nächsten Block bei {nxt})"
        return self._step_edge("Broadcast", self.broadcast_octet, 255, self.broadcast, extra)

    def hint(self) -> str:
        if self.on_octet_boundary:
            return (
                "Das Präfix endet an einer Oktettgrenze: Netzteil übernehmen, "
                "Hostteil ist 0 (Netz) bzw. 255 (Broadcast)."
            )
        return (
            f"Das interessante Oktett ist das {ordinal(self.octet_index)} "
            f"(Maskenwert {self.mask_octet}). Blockgröße = 256 − {self.mask_octet}."
        )

    def binary_rows(self) -> tuple[BinaryRow, ...]:
        return (
            BinaryRow("Adresse", self.address, self.prefix),
            BinaryRow("Maske", self.mask, self.prefix),
            BinaryRow("Netz", self.network, self.prefix),
        )


def special_prefix_note(prefix: int) -> str | None:
    if prefix == 31:
        return (
            "Sonderfall /31 (RFC 3021): wird für Punkt-zu-Punkt-Links genutzt. Es gibt keine "
            "Netz- und keine Broadcastadresse im klassischen Sinn – beide Adressen sind nutzbar."
        )
    if prefix == 32:
        return (
            "Sonderfall /32: eine Host-Route bzw. ein einzelnes Interface (z. B. Loopback). "
            "Das „Netz“ besteht aus genau einer Adresse."
        )
    return None
