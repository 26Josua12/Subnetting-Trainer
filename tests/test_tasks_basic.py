"""Tasks 1–7: 1000 random tasks per class and level, validated against ``ipaddress``."""

from __future__ import annotations

from collections import Counter
from ipaddress import IPv4Address, IPv4Interface, IPv4Network

import pytest

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.address import BroadcastTask, HostRangeTask, NetworkTask
from subnet_trainer.core.tasks.base import Task
from subnet_trainer.core.tasks.hosts import HostCountTask, PrefixForHostsTask
from subnet_trainer.core.tasks.masks import (
    MaskToPrefixTask,
    PrefixFromWildcardTask,
    PrefixToMaskTask,
    WildcardTask,
)
from subnet_trainer.core.tasks.same_net import SameNetTask

from conftest import generate_many

BASIC_CLASSES: list[type[Task]] = [
    NetworkTask,
    BroadcastTask,
    HostRangeTask,
    HostCountTask,
    PrefixForHostsTask,
    PrefixToMaskTask,
    MaskToPrefixTask,
    WildcardTask,
    PrefixFromWildcardTask,
    SameNetTask,
]


def _independent_reference(task: Task) -> tuple[object, ...]:
    """Solution computed in the test itself, via a different ``ipaddress`` route."""
    match task:
        case NetworkTask(ip=ip, prefix_len=p):
            return (IPv4Interface(f"{ip}/{p}").network.network_address,)
        case BroadcastTask(ip=ip, prefix_len=p):
            return (IPv4Interface(f"{ip}/{p}").network.broadcast_address,)
        case HostRangeTask(ip=ip, prefix_len=p):
            net = IPv4Interface(f"{ip}/{p}").network
            if p >= 20:
                hosts = list(net.hosts()) or [net.network_address]
                return ((hosts[0], hosts[-1]),)
            return ((net.network_address + 1, net.broadcast_address - 1),)
        case HostCountTask(prefix_len=p):
            net = IPv4Network(f"0.0.0.0/{p}")
            return ({31: 2, 32: 1}.get(p, net.num_addresses - 2),)
        case PrefixForHostsTask(hosts=n):
            fitting = [
                p for p in range(1, 31) if IPv4Network(f"0.0.0.0/{p}").num_addresses - 2 >= n
            ]
            return (max(fitting),)
        case PrefixToMaskTask(prefix_len=p):
            return (IPv4Network(f"0.0.0.0/{p}").netmask,)
        case MaskToPrefixTask(mask=mask):
            return (IPv4Network(f"0.0.0.0/{mask}").prefixlen,)
        case WildcardTask(prefix_len=p):
            return (IPv4Network(f"0.0.0.0/{p}").hostmask,)
        case PrefixFromWildcardTask(wildcard=wildcard):
            mask = IPv4Address(int(IPv4Address(wildcard)) ^ 0xFFFFFFFF)
            return (IPv4Network(f"0.0.0.0/{mask}").prefixlen,)
        case SameNetTask(first=a, second=b, prefix_len=p):
            return (IPv4Interface(f"{a}/{p}").network == IPv4Interface(f"{b}/{p}").network,)
    raise AssertionError(f"no reference for {task!r}")


def _wrong(value: object) -> object:
    """A plausible but wrong answer of the same type."""
    match value:
        case bool():
            return not value
        case int():
            return value + 1
        case IPv4Address():
            return value + 1 if int(value) < 0xFFFFFFFF else value - 1
        case (IPv4Address() as first, IPv4Address() as last):
            return (first, last + 1 if int(last) < 0xFFFFFFFF else last - 1)
    raise AssertionError(f"cannot perturb {value!r}")


@pytest.mark.parametrize("cls", BASIC_CLASSES, ids=lambda c: c.__name__)
def test_solution_matches_ipaddress_and_explanation(cls: type[Task], level: Level) -> None:
    for task in generate_many(cls, level):
        solution = task.solution()
        assert solution == _independent_reference(task), task
        explanation = task.explain()
        assert explanation.result == solution, task
        assert explanation.steps, task
        assert task.question and task.hint()


@pytest.mark.parametrize("cls", BASIC_CLASSES, ids=lambda c: c.__name__)
def test_check_accepts_solution_and_rejects_wrong(cls: type[Task], level: Level) -> None:
    for task in generate_many(cls, level, 200):
        solution = task.solution()
        assert task.check(solution).correct, task
        wrong = tuple(_wrong(v) for v in solution)
        result = task.check(wrong)
        assert not result.correct, task
        assert [f.expected for f in result.fields] == list(task.solution_text())


@pytest.mark.parametrize("cls", BASIC_CLASSES, ids=lambda c: c.__name__)
def test_displayed_solution_can_be_typed_back(cls: type[Task], level: Level) -> None:
    """What the trainer shows as solution must be accepted as input."""
    for task in generate_many(cls, level, 200):
        parsed = tuple(
            field.parse(text) for field, text in zip(task.fields, task.solution_text(), strict=True)
        )
        assert task.check(parsed).correct, task


@pytest.mark.parametrize("cls", BASIC_CLASSES, ids=lambda c: c.__name__)
def test_prefix_within_level_range(cls: type[Task], level: Level) -> None:
    low, high = level.prefix_range(special=True)
    for task in generate_many(cls, level, 300):
        assert task.prefix is not None
        assert low <= task.prefix <= high, task


def test_special_prefixes_only_on_hard() -> None:
    for level in (Level.EASY, Level.MEDIUM):
        for cls in BASIC_CLASSES:
            assert all(t.prefix is not None and t.prefix <= 30 for t in generate_many(cls, level))
    hard = [
        t.prefix for cls in (NetworkTask, HostRangeTask) for t in generate_many(cls, Level.HARD)
    ]
    assert 31 in hard and 32 in hard


def test_broadcast_never_asked_for_31_or_32() -> None:
    assert all(t.prefix <= 30 for t in generate_many(BroadcastTask, Level.HARD))


def test_easy_level_uses_class_c_addresses() -> None:
    for task in generate_many(NetworkTask, Level.EASY):
        assert isinstance(task, NetworkTask)
        assert 192 <= int(task.ip) >> 24 <= 223, task
        assert not task.as_mask


@pytest.mark.parametrize("level", list(Level), ids=lambda lv: lv.value)
def test_addresses_look_realistic(level: Level) -> None:
    tasks = [t for t in generate_many(NetworkTask, level) if isinstance(t, NetworkTask)]
    private = sum(t.ip.is_private for t in tasks)
    assert private / len(tasks) > 0.6
    for t in tasks:
        assert t.ip.is_private or t.ip.is_global, t
    # The given address is rarely the network or broadcast address itself.
    trivial = sum(
        t.prefix_len <= 30 and t.ip in (t.reference.network_address, t.reference.broadcast_address)
        for t in tasks
    )
    assert trivial / len(tasks) < 0.08


def test_medium_private_networks_stay_inside_their_pool() -> None:
    for task in generate_many(NetworkTask, Level.MEDIUM):
        assert isinstance(task, NetworkTask)
        if task.ip.is_private:
            assert task.reference.network_address.is_private, task


def test_same_net_is_balanced() -> None:
    counts = Counter(t.solution()[0] for t in generate_many(SameNetTask, Level.MEDIUM))
    assert 400 < counts[True] < 600


def test_same_net_addresses_are_distinct_hosts() -> None:
    for task in generate_many(SameNetTask, Level.HARD):
        assert isinstance(task, SameNetTask)
        assert task.first != task.second


def test_prefix_for_hosts_hits_boundaries() -> None:
    tasks = [t for t in generate_many(PrefixForHostsTask, Level.MEDIUM)]
    exact = sum(
        isinstance(t, PrefixForHostsTask) and t.hosts == 2 ** (32 - t.solution()[0]) - 2
        for t in tasks
    )
    assert exact > 100


def test_wildcard_context_network_is_a_real_network() -> None:
    for task in generate_many(WildcardTask, Level.HARD):
        assert isinstance(task, WildcardTask)
        if task.context in ("acl", "ospf"):
            assert task.network is not None
            IPv4Network(f"{task.network}/{task.prefix_len}")  # strict: raises on host bits
            assert str(task.network) in task.question


def test_seed_makes_generation_reproducible() -> None:
    first = generate_many(NetworkTask, Level.HARD, 50)
    second = generate_many(NetworkTask, Level.HARD, 50)
    assert first == second
