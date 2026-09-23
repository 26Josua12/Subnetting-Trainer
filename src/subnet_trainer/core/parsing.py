"""Lenient parsers for user input.

Every parser raises :class:`ParseError` with a German message when the input cannot be
understood at all. A *parseable but wrong* answer is not a parse error; it is simply
checked and marked as wrong.
"""

from __future__ import annotations

import re
from ipaddress import IPv4Address, IPv6Address

from subnet_trainer.core.addressing import prefix_from_mask_octets


class ParseError(ValueError):
    """Input could not be parsed; the message is shown to the user (German)."""


_WS = re.compile(r"\s+")


def _clean(raw: str) -> str:
    return _WS.sub(" ", raw.strip())


def _compact(raw: str) -> str:
    """Trim and drop blanks around dots and slashes ('10. 0 .0.1' -> '10.0.0.1').

    Blanks *between digits* are kept, so '192.168.1.1 0' stays invalid instead of
    silently becoming '192.168.1.10'.
    """
    return re.sub(r"\s*([./])\s*", r"\1", _clean(raw))


def _octets(text: str) -> tuple[int, int, int, int] | None:
    parts = text.split(".")
    if len(parts) != 4 or not all(p.isdigit() and len(p) <= 3 for p in parts):
        return None
    values = tuple(int(p) for p in parts)
    if any(v > 255 for v in values):
        return None
    return values[0], values[1], values[2], values[3]


def parse_ipv4(raw: str) -> IPv4Address:
    """A dotted-quad IPv4 address (leading zeros like 010 are tolerated)."""
    text = _compact(raw)
    if "/" in text:
        raise ParseError("Bitte nur die Adresse eingeben, ohne Präfix (z. B. 192.168.1.0).")
    octets = _octets(text)
    if octets is None:
        raise ParseError(f"'{raw.strip()}' ist keine gültige IPv4-Adresse (z. B. 192.168.1.0).")
    return IPv4Address(".".join(str(o) for o in octets))


def parse_dotted(raw: str) -> IPv4Address:
    """A dotted-quad value such as a subnet mask or wildcard mask (not validated further)."""
    text = _compact(raw)
    if re.fullmatch(r"/?\d{1,2}", text):
        raise ParseError("Bitte in Punktschreibweise eingeben, z. B. 255.255.255.0.")
    octets = _octets(text)
    if octets is None:
        raise ParseError(f"'{raw.strip()}' ist keine gültige Punktschreibweise (z. B. 0.0.0.255).")
    return IPv4Address(".".join(str(o) for o in octets))


def parse_prefix(raw: str) -> int:
    """A CIDR prefix length: '/27', '27' or '/ 27'."""
    text = _compact(raw)
    match = re.fullmatch(r"/?(\d{1,2})", text)
    if not match:
        if "." in text:
            raise ParseError("Bitte als Präfix eingeben, z. B. /27 oder 27.")
        raise ParseError(f"'{raw.strip()}' ist kein gültiges Präfix (z. B. /27).")
    value = int(match.group(1))
    if value > 32:
        raise ParseError("Ein IPv4-Präfix liegt zwischen /0 und /32.")
    return value


def parse_mask(raw: str) -> int:
    """A dotted subnet mask, returned as prefix length. The ones must be contiguous."""
    octets = _octets(_compact(raw))
    if octets is None:
        raise ParseError(f"'{raw.strip()}' ist keine gültige Subnetzmaske (z. B. 255.255.255.0).")
    prefix = prefix_from_mask_octets(octets)
    if prefix is None:
        raise ParseError(
            f"'{raw.strip()}' ist keine gültige Subnetzmaske – die Einsen müssen zusammenhängen."
        )
    return prefix


def parse_prefix_or_mask(raw: str) -> int:
    """Either '/27', '27' or '255.255.255.224' – all yield 27."""
    return parse_mask(raw) if "." in raw else parse_prefix(raw)


_RANGE_SPLIT = re.compile(r"\s*(?:-|–|—|\bbis\b|,|;|\s)\s*")


def parse_range(raw: str, *, allow_single: bool = False) -> tuple[IPv4Address, IPv4Address]:
    """Two addresses 'first - last' (also 'first-last', 'first bis last', 'first, last')."""
    parts = [p for p in _RANGE_SPLIT.split(_clean(raw)) if p]
    if allow_single and len(parts) == 1:
        address = parse_ipv4(parts[0])
        return address, address
    if len(parts) != 2:
        raise ParseError(
            "Bitte zwei Adressen eingeben: erste - letzte (z. B. 10.0.0.1 - 10.0.0.14)."
        )
    return parse_ipv4(parts[0]), parse_ipv4(parts[1])


_YES = {"j", "ja", "y", "yes", "jo", "jep", "true", "1"}
_NO = {"n", "nein", "no", "nö", "ne", "false", "0"}


def parse_yes_no(raw: str) -> bool:
    text = _clean(raw).lower()
    if text in _YES:
        return True
    if text in _NO:
        return False
    raise ParseError("Bitte mit 'ja' oder 'nein' antworten (j/n geht auch).")


_THOUSANDS = re.compile(r"\d{1,3}(?:[.,' ]\d{3})+")


def parse_int(raw: str) -> int:
    """A non-negative integer; German/English thousands separators are tolerated."""
    text = _clean(raw)
    text = re.sub(r"\s*(hosts?|adressen|subnetze|netze)$", "", text, flags=re.IGNORECASE)
    if _THOUSANDS.fullmatch(text):
        text = re.sub(r"[.,' ]", "", text)
    if not text.isdigit():
        raise ParseError(f"'{raw.strip()}' ist keine ganze Zahl.")
    return int(text)


def parse_network(raw: str) -> tuple[IPv4Address, int]:
    """A network as '192.168.1.0/25', '192.168.1.0 /25' or '192.168.1.0 255.255.255.128'.

    Host bits are *not* validated here: '192.168.1.5/25' parses fine and is simply wrong.
    """
    text = _clean(raw)
    match = re.fullmatch(r"(\S+?)\s*/\s*(\d{1,2})", text)
    if match:
        return parse_ipv4(match.group(1)), parse_prefix(match.group(2))
    parts = text.split(" ")
    if len(parts) == 2 and "." in parts[1]:
        return parse_ipv4(parts[0]), parse_mask(parts[1])
    raise ParseError("Bitte als Netz/Präfix eingeben, z. B. 192.168.1.0/26.")


def split_list(raw: str) -> list[str]:
    """Split a comma/semicolon/whitespace separated list, keeping 'a.b.c.d /nn' together."""
    text = re.sub(r"\s*/\s*", "/", _clean(raw))
    parts = [p for p in re.split(r"\s*[,;]\s*|\s+", text) if p]
    if not parts:
        raise ParseError("Bitte mindestens einen Wert eingeben.")
    return parts


def parse_address_list(raw: str) -> list[IPv4Address]:
    return [parse_ipv4(p) for p in split_list(raw)]


def parse_network_list(raw: str) -> list[tuple[IPv4Address, int]]:
    return [parse_network(p) for p in split_list(raw)]


def parse_ipv6(raw: str) -> IPv6Address:
    text = _clean(raw).replace(" ", "")
    try:
        return IPv6Address(text)
    except ValueError:
        raise ParseError(f"'{raw.strip()}' ist keine gültige IPv6-Adresse.") from None


def parse_ipv6_network(raw: str) -> tuple[IPv6Address, int]:
    """An IPv6 prefix like '2001:db8:acad::/48'; host bits are not validated here."""
    text = _clean(raw).replace(" ", "")
    address, sep, length = text.partition("/")
    if not sep:
        raise ParseError("Bitte mit Präfix eingeben, z. B. 2001:db8:acad::/48.")
    if not length.isdigit() or int(length) > 128:
        raise ParseError("Ein IPv6-Präfix liegt zwischen /0 und /128.")
    return parse_ipv6(address), int(length)
