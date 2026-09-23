from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address

import pytest

from subnet_trainer.core.parsing import (
    ParseError,
    parse_address_list,
    parse_dotted,
    parse_int,
    parse_ipv4,
    parse_ipv6,
    parse_ipv6_network,
    parse_mask,
    parse_network,
    parse_network_list,
    parse_prefix,
    parse_prefix_or_mask,
    parse_range,
    parse_yes_no,
)

A = IPv4Address


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.168.1.0", "192.168.1.0"),
        ("  10.0.0.1 ", "10.0.0.1"),
        ("10. 0. 0. 1", "10.0.0.1"),
        ("192.168.010.001", "192.168.10.1"),
        ("0.0.0.0", "0.0.0.0"),
        ("255.255.255.255", "255.255.255.255"),
    ],
)
def test_parse_ipv4_ok(raw: str, expected: str) -> None:
    assert parse_ipv4(raw) == A(expected)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "1.2.3",
        "1.2.3.4.5",
        "256.1.1.1",
        "a.b.c.d",
        "1.2.3.-4",
        "10.0.0.0/24",
        "1..2.3",
        "192.168.1.1 0",
    ],
)
def test_parse_ipv4_errors(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_ipv4(raw)


def test_parse_ipv4_error_mentions_prefix() -> None:
    with pytest.raises(ParseError, match="ohne Präfix"):
        parse_ipv4("10.0.0.0/8")


@pytest.mark.parametrize(
    ("raw", "expected"), [("/27", 27), ("27", 27), (" / 27 ", 27), ("0", 0), ("/32", 32)]
)
def test_parse_prefix(raw: str, expected: int) -> None:
    assert parse_prefix(raw) == expected


@pytest.mark.parametrize("raw", ["/33", "abc", "", "//24", "255.255.255.0", "2 4"])
def test_parse_prefix_errors(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_prefix(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("255.255.255.224", 27),
        ("255.255.248.0", 21),
        ("255.0.0.0", 8),
        ("0.0.0.0", 0),
        ("255.255.255.255", 32),
        ("255.255.255.254", 31),
    ],
)
def test_parse_mask(raw: str, expected: int) -> None:
    assert parse_mask(raw) == expected


@pytest.mark.parametrize("raw", ["255.0.255.0", "255.255.253.0", "0.255.255.255", "255.255.255"])
def test_parse_mask_rejects_non_contiguous_or_invalid(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_mask(raw)


@pytest.mark.parametrize(
    ("raw", "expected"), [("/23", 23), ("23", 23), ("255.255.254.0", 23), (" 255.255.254.0 ", 23)]
)
def test_prefix_and_mask_are_interchangeable(raw: str, expected: int) -> None:
    assert parse_prefix_or_mask(raw) == expected


def test_parse_dotted_accepts_any_quad_but_not_prefix() -> None:
    assert parse_dotted("0.0.3.255") == A("0.0.3.255")
    assert parse_dotted("0.255.0.255") == A("0.255.0.255")  # parseable, just wrong
    with pytest.raises(ParseError, match="Punktschreibweise"):
        parse_dotted("/24")


@pytest.mark.parametrize(
    "raw",
    [
        "10.0.0.1 - 10.0.0.14",
        "10.0.0.1-10.0.0.14",
        "10.0.0.1 – 10.0.0.14",
        "10.0.0.1 bis 10.0.0.14",
        "10.0.0.1, 10.0.0.14",
        "10.0.0.1 10.0.0.14",
        "  10.0.0.1   -   10.0.0.14  ",
    ],
)
def test_parse_range_formats(raw: str) -> None:
    assert parse_range(raw) == (A("10.0.0.1"), A("10.0.0.14"))


def test_parse_range_single_address() -> None:
    with pytest.raises(ParseError, match="erste - letzte"):
        parse_range("10.0.0.1")
    assert parse_range("10.0.0.1", allow_single=True) == (A("10.0.0.1"), A("10.0.0.1"))


def test_parse_range_three_addresses_is_error() -> None:
    with pytest.raises(ParseError):
        parse_range("10.0.0.1 - 10.0.0.2 - 10.0.0.3")


@pytest.mark.parametrize("raw", ["j", "ja", "JA", " Ja ", "y", "yes"])
def test_yes(raw: str) -> None:
    assert parse_yes_no(raw) is True


@pytest.mark.parametrize("raw", ["n", "nein", "Nein", "no"])
def test_no(raw: str) -> None:
    assert parse_yes_no(raw) is False


def test_yes_no_error() -> None:
    with pytest.raises(ParseError, match="ja"):
        parse_yes_no("vielleicht")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30", 30),
        (" 510 ", 510),
        ("16.777.214", 16_777_214),
        ("16,777,214", 16_777_214),
        ("65 534", 65_534),
        ("62 Hosts", 62),
    ],
)
def test_parse_int(raw: str, expected: int) -> None:
    assert parse_int(raw) == expected


@pytest.mark.parametrize("raw", ["", "-3", "3.5", "zwölf", "1.2345"])
def test_parse_int_errors(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_int(raw)


@pytest.mark.parametrize(
    "raw",
    ["192.168.1.64/26", "192.168.1.64 /26", "192.168.1.64 / 26", "192.168.1.64 255.255.255.192"],
)
def test_parse_network(raw: str) -> None:
    assert parse_network(raw) == (A("192.168.1.64"), 26)


def test_parse_network_keeps_host_bits() -> None:
    assert parse_network("192.168.1.65/26") == (A("192.168.1.65"), 26)


def test_parse_network_errors() -> None:
    with pytest.raises(ParseError):
        parse_network("192.168.1.0")


def test_parse_lists() -> None:
    assert parse_address_list("10.0.0.0, 10.0.0.32;10.0.0.64 10.0.0.96") == [
        A("10.0.0.0"),
        A("10.0.0.32"),
        A("10.0.0.64"),
        A("10.0.0.96"),
    ]
    assert parse_network_list("10.0.0.0 /27, 10.0.0.32/27") == [
        (A("10.0.0.0"), 27),
        (A("10.0.0.32"), 27),
    ]
    with pytest.raises(ParseError):
        parse_address_list("   ")


def test_parse_ipv6() -> None:
    assert parse_ipv6(" 2001:db8::1 ") == IPv6Address("2001:db8::1")
    assert parse_ipv6_network("2001:DB8:acad::/48") == (IPv6Address("2001:db8:acad::"), 48)
    with pytest.raises(ParseError):
        parse_ipv6("2001:db8:::1")
    with pytest.raises(ParseError):
        parse_ipv6_network("2001:db8::")
    with pytest.raises(ParseError):
        parse_ipv6_network("2001:db8::/129")
