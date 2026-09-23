"""Tasks 8–11: 1000 random tasks per class and level, validated against ``ipaddress``."""

from __future__ import annotations

import itertools
import random
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, collapse_addresses

import pytest

from subnet_trainer.core.levels import Level
from subnet_trainer.core.parsing import ParseError
from subnet_trainer.core.tasks.base import Task, TaskKind
from subnet_trainer.core.tasks.ipv6 import (
    Ipv6CompressTask,
    Ipv6ExpandTask,
    Ipv6PrefixTask,
    Ipv6SubnetCountTask,
    compress,
    to_hextets,
)
from subnet_trainer.core.tasks.registry import available_kinds, random_task
from subnet_trainer.core.tasks.subdivide import SubdivideTask
from subnet_trainer.core.tasks.summary import SummaryTask
from subnet_trainer.core.tasks.vlsm import Requirement, VlsmTask

from conftest import generate_many

A = IPv4Address
ADVANCED_CLASSES: list[type[Task]] = [
    SubdivideTask,
    VlsmTask,
    SummaryTask,
    Ipv6CompressTask,
    Ipv6ExpandTask,
    Ipv6PrefixTask,
    Ipv6SubnetCountTask,
]


def _independent_reference(task: Task) -> tuple[object, ...]:
    match task:
        case SubdivideTask(network=net, base_prefix=base, count=count):
            parent = IPv4Network(f"{net}/{base}")
            for prefix in range(base, 33):
                subnets = list(parent.subnets(new_prefix=prefix)) if prefix - base <= 8 else []
                if len(subnets) >= count:
                    return prefix, [s.network_address for s in subnets[: task.listed]]
        case SummaryTask(networks=networks):
            nets = [IPv4Network(f"{a}/{p}") for a, p in networks]
            first = min(n.network_address for n in nets)
            last = max(n.broadcast_address for n in nets)
            prefix = 32
            while last not in IPv4Network(f"{first}/{prefix}", strict=False):
                prefix -= 1
            summary = IPv4Network(f"{first}/{prefix}", strict=False)
            return ((summary.network_address, summary.prefixlen),)
        case Ipv6CompressTask(address=address):
            return (IPv6Address(address.exploded).compressed,)
        case Ipv6ExpandTask(address=address):
            return (IPv6Address(str(address)).exploded,)
        case Ipv6PrefixTask(address=address, prefix_len=p):
            net = IPv6Network(f"{address}/{p}", strict=False)
            return ((net.network_address, p),)
        case Ipv6SubnetCountTask(site_prefix=site, subnet_prefix=sub):
            parent = IPv6Network(f"2001:db8::/{site}")
            return (parent.num_addresses // IPv6Network(f"2001:db8::/{sub}").num_addresses,)
    raise AssertionError(f"no reference for {task!r}")


def _check_vlsm_with_ipaddress(task: VlsmTask) -> None:
    """Validate the allocation rules directly instead of recomputing it."""
    parent = IPv4Network(f"{task.network}/{task.base_prefix}")
    by_name = dict(zip((r.name for r in task.requirements), task.solution(), strict=True))
    nets = []
    for req in task.ordered:
        address, prefix = by_name[req.name]
        net = IPv4Network(f"{address}/{prefix}")  # strict: must be a network address
        assert net.subnet_of(parent)
        assert net.num_addresses - 2 >= req.hosts  # big enough
        assert prefix == 30 or IPv4Network(f"0.0.0.0/{prefix + 1}").num_addresses - 2 < req.hosts
        nets.append(net)
    # Largest first, gapless from the first address, no overlap.
    assert nets[0].network_address == parent.network_address
    for previous, current in itertools.pairwise(nets):
        assert previous.num_addresses >= current.num_addresses
        assert current.network_address == previous.broadcast_address + 1
    assert len(list(collapse_addresses(nets))) <= len(nets)


@pytest.mark.parametrize("cls", ADVANCED_CLASSES, ids=lambda c: c.__name__)
def test_solution_matches_ipaddress_and_explanation(cls: type[Task], level: Level) -> None:
    for task in generate_many(cls, level):
        solution = task.solution()
        if isinstance(task, VlsmTask):
            _check_vlsm_with_ipaddress(task)
        else:
            assert solution == _independent_reference(task), task
        assert task.explain().result == solution, task
        assert task.question and task.hint()


@pytest.mark.parametrize("cls", ADVANCED_CLASSES, ids=lambda c: c.__name__)
def test_displayed_solution_can_be_typed_back(cls: type[Task], level: Level) -> None:
    for task in generate_many(cls, level, 200):
        parsed = [f.parse(t) for f, t in zip(task.fields, task.solution_text(), strict=True)]
        assert task.check(parsed).correct, task


def test_subdivide_generation_is_valid(level: Level) -> None:
    for task in generate_many(SubdivideTask, level):
        assert isinstance(task, SubdivideTask)
        IPv4Network(f"{task.network}/{task.base_prefix}")  # strict
        assert task.new_prefix <= 30
        assert 2 <= task.count <= 16
        assert len(task.fields) == 2


def test_subdivide_known_example() -> None:
    task = SubdivideTask(A("192.168.10.0"), 24, 6)
    prefix, addresses = task.solution()
    assert prefix == 27
    assert addresses == [A(f"192.168.10.{i * 32}") for i in range(6)]
    text = "\n".join(task.explain().steps)
    assert "2^3 = 8 ≥ 6" in text and "/27" in text and "2 bleiben als Reserve" in text


def test_subdivide_accepts_any_order_and_prefix_suffix() -> None:
    task = SubdivideTask(A("10.0.0.0"), 24, 3)
    prefix_field, list_field = task.fields
    answer = [
        prefix_field.parse("255.255.255.192"),
        list_field.parse("10.0.0.128/26, 10.0.0.0 10.0.0.64"),
    ]
    assert task.check(answer).correct
    with pytest.raises(ParseError, match="genau 3"):
        list_field.parse("10.0.0.0, 10.0.0.64")


def test_vlsm_known_example() -> None:
    reqs = (
        Requirement("LAN B", 60),
        Requirement("LAN A", 120),
        Requirement("WAN 1", 2),
        Requirement("LAN C", 25),
    )
    task = VlsmTask(A("192.168.1.0"), 24, reqs)
    assert task.solution() == (
        (A("192.168.1.128"), 26),
        (A("192.168.1.0"), 25),
        (A("192.168.1.224"), 30),
        (A("192.168.1.192"), 27),
    )
    assert task.explain().result == task.solution()


def test_vlsm_same_size_requirements_may_be_swapped() -> None:
    reqs = (Requirement("LAN A", 50), Requirement("LAN B", 40), Requirement("WAN 1", 2))
    task = VlsmTask(A("10.0.0.0"), 24, reqs)
    assert task.solution()[:2] == ((A("10.0.0.0"), 26), (A("10.0.0.64"), 26))
    swapped = [(A("10.0.0.64"), 26), (A("10.0.0.0"), 26), (A("10.0.0.128"), 30)]
    assert task.check(swapped).correct
    # ... but the same subnet may not be used twice.
    twice = [(A("10.0.0.0"), 26), (A("10.0.0.0"), 26), (A("10.0.0.128"), 30)]
    result = task.check(twice)
    assert not result.correct
    assert [f.correct for f in result.fields] == [True, False, True]


def test_vlsm_wrong_order_is_wrong() -> None:
    reqs = (Requirement("LAN A", 100), Requirement("LAN B", 20))
    task = VlsmTask(A("10.0.0.0"), 24, reqs)
    # Smallest first is a valid-looking plan, but not what was asked.
    result = task.check([(A("10.0.0.128"), 25), (A("10.0.0.0"), 27)])
    assert not result.correct


def test_vlsm_requirements_are_distinct_and_fit(level: Level) -> None:
    for task in generate_many(VlsmTask, level, 300):
        assert isinstance(task, VlsmTask)
        lans = [r.hosts for r in task.requirements if r.name.startswith("LAN")]
        assert len(lans) == len(set(lans))
        assert len({r.name for r in task.requirements}) == len(task.requirements)


def test_summary_known_examples() -> None:
    nets = tuple((A(f"172.16.{i}.0"), 24) for i in range(8, 16))
    task = SummaryTask(nets)
    assert task.solution() == ((A("172.16.8.0"), 21),)
    assert task.explain().result == task.solution()
    task = SummaryTask(((A("10.1.4.0"), 24), (A("10.1.7.0"), 24)))
    assert task.solution() == ((A("10.1.4.0"), 22),)
    task = SummaryTask(((A("10.1.3.0"), 24), (A("10.1.4.0"), 24)))
    assert task.solution() == ((A("10.1.0.0"), 21),)
    assert task.explain().result == task.solution()


def test_summary_generation_is_exact(level: Level) -> None:
    """Generated networks are distinct and the summary is never longer than needed."""
    for task in generate_many(SummaryTask, level, 300):
        assert isinstance(task, SummaryTask)
        assert len(set(task.networks)) == len(task.networks) >= 2
        (summary,) = task.solution()
        halves = list(IPv4Network(f"{summary[0]}/{summary[1]}").subnets())
        nets = [IPv4Network(f"{a}/{p}") for a, p in task.networks]
        assert any(n.subnet_of(halves[0]) for n in nets)
        assert any(n.subnet_of(halves[1]) for n in nets)


@pytest.mark.parametrize(
    ("full", "short"),
    [
        ("2001:0db8:0000:0000:0000:ff00:0042:8329", "2001:db8::ff00:42:8329"),
        ("2001:0db8:0000:0001:0000:0000:0000:0001", "2001:db8:0:1::1"),
        ("2001:0db8:0000:0000:0001:0000:0000:0001", "2001:db8::1:0:0:1"),
        ("0000:0000:0000:0000:0000:0000:0000:0001", "::1"),
        ("0000:0000:0000:0000:0000:0000:0000:0000", "::"),
        ("fe80:0000:0000:0000:0000:0000:0000:0000", "fe80::"),
        ("2001:0db8:0001:0000:0001:0000:0001:0000", "2001:db8:1:0:1:0:1:0"),
    ],
)
def test_ipv6_compress_rules(full: str, short: str) -> None:
    address = IPv6Address(full)
    assert compress(to_hextets(address)) == short == address.compressed
    task = Ipv6CompressTask(address)
    (field,) = task.fields
    assert task.check([field.parse(short.upper())]).correct
    assert task.explain().result == (short,)


def test_ipv6_compress_rejects_valid_but_long_form() -> None:
    task = Ipv6CompressTask(IPv6Address("2001:db8::1"))
    (field,) = task.fields
    assert not task.check([field.parse("2001:0db8::1")]).correct
    with pytest.raises(ParseError):
        field.parse("2001:db8:::1")


def test_ipv6_prefix_non_nibble() -> None:
    task = Ipv6PrefixTask(IPv6Address("2001:db8:acad:ffff::1"), 50)
    assert task.solution() == ((IPv6Address("2001:db8:acad:c000::"), 50),)
    assert task.explain().result == task.solution()


def test_ipv6_subnet_count() -> None:
    assert Ipv6SubnetCountTask(48).solution() == (65_536,)
    assert Ipv6SubnetCountTask(56).solution() == (256,)
    assert Ipv6SubnetCountTask(48, 56).explain().result == (256,)


def test_random_pool_per_level() -> None:
    easy = set(available_kinds(Level.EASY))
    hard = set(available_kinds(Level.HARD))
    assert TaskKind.VLSM not in easy and TaskKind.SUMMARY not in easy
    assert TaskKind.SUBDIVIDE in easy
    assert {TaskKind.VLSM, TaskKind.SUMMARY} <= hard
    assert TaskKind.IPV6 not in hard  # own mode only
    # Explicitly requested types are allowed on every level.
    task = random_task(random.Random(1), Level.EASY, [TaskKind.VLSM])
    assert task.kind is TaskKind.VLSM
    task = random_task(random.Random(1), Level.EASY, [TaskKind.IPV6])
    assert task.kind is TaskKind.IPV6
