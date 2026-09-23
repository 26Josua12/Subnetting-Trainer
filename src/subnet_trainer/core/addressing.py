"""IPv4 helpers based on plain octet arithmetic, plus realistic random address generation.

The arithmetic here deliberately mirrors how the magic-number method works on paper.
``ipaddress`` is only used to *filter* generated addresses (e.g. ``is_global``), never to
compute solutions.
"""

from __future__ import annotations

import ipaddress
import random
from collections.abc import Sequence
from ipaddress import IPv4Address

from subnet_trainer.core.levels import Level

ALL_ONES = 0xFFFFFFFF

# Values a single mask octet can take, from 0 to 8 network bits.
MASK_OCTET_VALUES: tuple[int, ...] = (0, 128, 192, 224, 240, 248, 252, 254, 255)

Octets = tuple[int, int, int, int]


def to_octets(value: int) -> Octets:
    return (value >> 24) & 255, (value >> 16) & 255, (value >> 8) & 255, value & 255


def from_octets(parts: Sequence[int]) -> int:
    if len(parts) != 4 or any(not 0 <= p <= 255 for p in parts):
        raise ValueError(f"invalid octets: {parts!r}")
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def dotted(value: int) -> str:
    return ".".join(str(o) for o in to_octets(value))


def mask_octets(prefix: int) -> Octets:
    """Subnet mask as octets, built octet by octet (8 bits per full octet)."""
    if not 0 <= prefix <= 32:
        raise ValueError(f"invalid prefix: {prefix}")
    parts = []
    remaining = prefix
    for _ in range(4):
        bits = min(8, max(0, remaining))
        parts.append(MASK_OCTET_VALUES[bits])
        remaining -= bits
    return parts[0], parts[1], parts[2], parts[3]


def mask_int(prefix: int) -> int:
    return from_octets(mask_octets(prefix))


def wildcard_octets(prefix: int) -> Octets:
    m = mask_octets(prefix)
    return 255 - m[0], 255 - m[1], 255 - m[2], 255 - m[3]


def prefix_from_mask_octets(parts: Sequence[int]) -> int | None:
    """Count the network bits of a mask; ``None`` if the mask is not contiguous."""
    total = 0
    seen_partial = False
    for part in parts:
        if part not in MASK_OCTET_VALUES:
            return None
        bits = MASK_OCTET_VALUES.index(part)
        if seen_partial and bits:
            return None
        if bits < 8:
            seen_partial = True
        total += bits
    return total


def octet_bits(value: int) -> int:
    """Number of network bits encoded by a single mask octet value (e.g. 248 -> 5)."""
    return MASK_OCTET_VALUES.index(value)


def usable_hosts(prefix: int) -> int:
    """Usable host addresses; /31 (RFC 3021) and /32 are special cases."""
    if prefix == 32:
        return 1
    if prefix == 31:
        return 2
    return 2 ** (32 - prefix) - 2


def block_size(prefix: int) -> int:
    """Number of addresses in a subnet with this prefix."""
    return 2 ** (32 - prefix)


def german_int(n: int) -> str:
    """Format an integer with German thousands separators (16.777.214)."""
    return f"{n:,}".replace(",", ".")


# --- Random generation -------------------------------------------------------------------

_PRIVATE_POOLS: tuple[tuple[int, int, float], ...] = (
    (from_octets((10, 0, 0, 0)), 8, 0.4),
    (from_octets((172, 16, 0, 0)), 12, 0.3),
    (from_octets((192, 168, 0, 0)), 16, 0.3),
)

_PUBLIC_SHARE = {Level.EASY: 0.15, Level.MEDIUM: 0.10, Level.HARD: 0.25}

# Small chance to keep an address that is itself the network/broadcast address,
# which makes for a good trick question now and then.
_TRICK_CHANCE = 0.03


def _random_private(rng: random.Random, level: Level, prefix: int) -> int:
    if level is Level.EASY:
        base, pool_prefix = from_octets((192, 168, 0, 0)), 16
    else:
        # Only pools that fully contain the subnet keep the network realistic
        # (e.g. no 192.168.x.x with a /12).
        pools = [p for p in _PRIVATE_POOLS if p[1] <= prefix] or [_PRIVATE_POOLS[0]]
        base, pool_prefix, _ = rng.choices(pools, weights=[p[2] for p in pools])[0]
    return base + rng.randrange(2 ** (32 - pool_prefix))


def _random_public(rng: random.Random, level: Level) -> int:
    low, high = (192, 223) if level is Level.EASY else (1, 223)
    while True:
        value = from_octets(
            (rng.randint(low, high), rng.randrange(256), rng.randrange(256), rng.randrange(256))
        )
        if ipaddress.IPv4Address(value).is_global:
            return value


def random_host(rng: random.Random, level: Level, prefix: int) -> IPv4Address:
    """A realistic-looking address, usually not the network or broadcast address itself."""
    value = 0
    for _ in range(50):
        if rng.random() < _PUBLIC_SHARE[level]:
            value = _random_public(rng, level)
        else:
            value = _random_private(rng, level, prefix)
        if prefix >= 31:
            break
        host_part = value & (ALL_ONES >> prefix)
        if host_part not in (0, ALL_ONES >> prefix) or rng.random() < _TRICK_CHANCE:
            break
    return IPv4Address(value)


def random_network(rng: random.Random, level: Level, prefix: int) -> IPv4Address:
    """Network address of a random realistic subnet with the given prefix."""
    host = int(random_host(rng, level, prefix))
    return IPv4Address(host & mask_int(prefix))
