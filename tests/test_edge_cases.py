"""Hand-picked edge cases: /8, /31, /32, octet boundaries and 0.0.0.0."""

from __future__ import annotations

from ipaddress import IPv4Address

import pytest

from subnet_trainer.core.addressing import (
    mask_octets,
    prefix_from_mask_octets,
    usable_hosts,
    wildcard_octets,
)
from subnet_trainer.core.explain import BlockCalc
from subnet_trainer.core.tasks.address import BroadcastTask, HostRangeTask, NetworkTask
from subnet_trainer.core.tasks.hosts import HostCountTask, PrefixForHostsTask
from subnet_trainer.core.tasks.masks import (
    MaskToPrefixTask,
    PrefixFromWildcardTask,
    PrefixToMaskTask,
    WildcardTask,
)
from subnet_trainer.core.tasks.same_net import SameNetTask

A = IPv4Address


def _consistent(task: NetworkTask | BroadcastTask | HostRangeTask) -> None:
    assert task.explain().result == task.solution()


@pytest.mark.parametrize(
    ("ip", "prefix", "network", "broadcast", "first", "last"),
    [
        ("172.16.45.200", 21, "172.16.40.0", "172.16.47.255", "172.16.40.1", "172.16.47.254"),
        ("10.200.3.4", 8, "10.0.0.0", "10.255.255.255", "10.0.0.1", "10.255.255.254"),
        ("0.0.1.5", 16, "0.0.0.0", "0.0.255.255", "0.0.0.1", "0.0.255.254"),
        ("0.0.0.0", 24, "0.0.0.0", "0.0.0.255", "0.0.0.1", "0.0.0.254"),
        ("192.168.1.255", 24, "192.168.1.0", "192.168.1.255", "192.168.1.1", "192.168.1.254"),
        ("192.168.1.130", 25, "192.168.1.128", "192.168.1.255", "192.168.1.129", "192.168.1.254"),
        ("10.1.1.6", 30, "10.1.1.4", "10.1.1.7", "10.1.1.5", "10.1.1.6"),
        ("200.10.255.200", 9, "200.0.0.0", "200.127.255.255", "200.0.0.1", "200.127.255.254"),
        (
            "255.255.255.254",
            30,
            "255.255.255.252",
            "255.255.255.255",
            "255.255.255.253",
            "255.255.255.254",
        ),
    ],
)
def test_known_values(
    ip: str, prefix: int, network: str, broadcast: str, first: str, last: str
) -> None:
    net_task = NetworkTask(A(ip), prefix)
    bc_task = BroadcastTask(A(ip), prefix)
    range_task = HostRangeTask(A(ip), prefix)
    assert net_task.solution() == (A(network),)
    assert bc_task.solution() == (A(broadcast),)
    assert range_task.solution() == ((A(first), A(last)),)
    for task in (net_task, bc_task, range_task):
        _consistent(task)


def test_slash_31() -> None:
    task = HostRangeTask(A("10.0.0.7"), 31)
    assert task.solution() == ((A("10.0.0.6"), A("10.0.0.7")),)
    explanation = task.explain()
    assert explanation.result == task.solution()
    assert explanation.note is not None and "RFC 3021" in explanation.note
    assert NetworkTask(A("10.0.0.7"), 31).solution() == (A("10.0.0.6"),)
    assert HostCountTask(31).solution() == (2,)
    assert HostCountTask(31).explain().result == (2,)


def test_slash_32() -> None:
    task = HostRangeTask(A("10.9.8.7"), 32)
    assert task.solution() == ((A("10.9.8.7"), A("10.9.8.7")),)
    assert task.explain().result == task.solution()
    # A single address is accepted as answer for /32.
    (field,) = task.fields
    assert task.check([field.parse("10.9.8.7")]).correct
    assert NetworkTask(A("10.9.8.7"), 32).solution() == (A("10.9.8.7"),)
    assert NetworkTask(A("10.9.8.7"), 32).explain().note is not None
    assert HostCountTask(32).solution() == (1,)
    assert HostCountTask(32).explain().result == (1,)
    assert WildcardTask(32).solution() == (A("0.0.0.0"),)
    assert PrefixFromWildcardTask(32).solution() == (32,)
    assert PrefixFromWildcardTask(32).explain().result == (32,)


def test_slash_8_masks() -> None:
    assert PrefixToMaskTask(8).solution() == (A("255.0.0.0"),)
    assert PrefixToMaskTask(8).explain().result == (A("255.0.0.0"),)
    assert MaskToPrefixTask(8).solution() == (8,)
    assert WildcardTask(8).solution() == (A("0.255.255.255"),)
    assert HostCountTask(8).solution() == (16_777_214,)
    assert PrefixForHostsTask(16_777_214).solution() == (8,)
    assert PrefixForHostsTask(16_777_215).solution() == (7,)


@pytest.mark.parametrize(
    ("hosts", "prefix"),
    [(2, 30), (3, 29), (6, 29), (7, 28), (62, 26), (63, 25), (500, 23), (510, 23), (511, 22)],
)
def test_prefix_for_hosts(hosts: int, prefix: int) -> None:
    task = PrefixForHostsTask(hosts)
    assert task.solution() == (prefix,)
    assert task.explain().result == (prefix,)


def test_mask_helpers_for_all_prefixes() -> None:
    for p in range(33):
        octets = mask_octets(p)
        assert prefix_from_mask_octets(octets) == p
        assert all(m + w == 255 for m, w in zip(octets, wildcard_octets(p), strict=True))
    assert prefix_from_mask_octets((255, 0, 255, 0)) is None
    assert prefix_from_mask_octets((255, 255, 253, 0)) is None


def test_usable_hosts() -> None:
    assert [usable_hosts(p) for p in (24, 30, 31, 32)] == [254, 2, 2, 1]


def test_block_calc_boundaries() -> None:
    calc = BlockCalc(int(A("172.16.45.200")), 21)
    assert (calc.octet_index, calc.mask_octet, calc.block_size, calc.network_octet) == (
        2,
        248,
        8,
        40,
    )
    boundary = BlockCalc(int(A("192.168.7.9")), 24)
    assert boundary.on_octet_boundary and boundary.block_size == 1
    assert "Oktettgrenze" in boundary.step_mask()
    with pytest.raises(ValueError):
        BlockCalc(0, 0)


def test_explanation_mentions_block_size_and_result() -> None:
    explanation = NetworkTask(A("172.16.45.200"), 21).explain()
    text = "\n".join(explanation.steps)
    assert "256 − 248 = 8" in text
    assert "45 liegt im Block 40–47" in text
    assert text.rstrip(".").endswith("172.16.40.0")


def test_same_net_edge_cases() -> None:
    assert SameNetTask(A("10.1.1.1"), A("10.1.1.2"), 30).solution() == (True,)
    assert SameNetTask(A("10.1.1.2"), A("10.1.1.5"), 30).solution() == (False,)
    # Same interesting octet block, but an earlier octet differs.
    task = SameNetTask(A("10.1.1.1"), A("10.2.1.1"), 24)
    assert task.solution() == (False,)
    assert task.explain().result == (False,)
    task = SameNetTask(A("0.0.0.1"), A("0.0.0.2"), 8)
    assert task.solution() == (True,)
    assert task.explain().result == (True,)
