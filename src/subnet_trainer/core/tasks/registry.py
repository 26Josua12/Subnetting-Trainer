"""Registry of all task classes and random task selection."""

from __future__ import annotations

import random
from collections.abc import Iterable

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.address import BroadcastTask, HostRangeTask, NetworkTask
from subnet_trainer.core.tasks.base import Task, TaskKind
from subnet_trainer.core.tasks.hosts import HostCountTask, PrefixForHostsTask
from subnet_trainer.core.tasks.ipv6 import (
    Ipv6CompressTask,
    Ipv6ExpandTask,
    Ipv6PrefixTask,
    Ipv6SubnetCountTask,
)
from subnet_trainer.core.tasks.masks import (
    MaskToPrefixTask,
    PrefixFromWildcardTask,
    PrefixToMaskTask,
    WildcardTask,
)
from subnet_trainer.core.tasks.same_net import SameNetTask
from subnet_trainer.core.tasks.subdivide import SubdivideTask
from subnet_trainer.core.tasks.summary import SummaryTask
from subnet_trainer.core.tasks.vlsm import VlsmTask

TASK_CLASSES: dict[TaskKind, tuple[type[Task], ...]] = {
    TaskKind.NETWORK: (NetworkTask,),
    TaskKind.BROADCAST: (BroadcastTask,),
    TaskKind.HOST_RANGE: (HostRangeTask,),
    TaskKind.HOST_COUNT: (HostCountTask, PrefixForHostsTask),
    TaskKind.MASK: (PrefixToMaskTask, MaskToPrefixTask),
    TaskKind.WILDCARD: (WildcardTask, PrefixFromWildcardTask),
    TaskKind.SAME_NET: (SameNetTask,),
    TaskKind.SUBDIVIDE: (SubdivideTask,),
    TaskKind.VLSM: (VlsmTask,),
    TaskKind.SUMMARY: (SummaryTask,),
    TaskKind.IPV6: (Ipv6CompressTask, Ipv6ExpandTask, Ipv6PrefixTask, Ipv6SubnetCountTask),
}

IPV6_KINDS: frozenset[TaskKind] = frozenset({TaskKind.IPV6})

# Quick single-answer types, used by the speed mode.
QUICK_KINDS: tuple[TaskKind, ...] = (
    TaskKind.NETWORK,
    TaskKind.BROADCAST,
    TaskKind.HOST_RANGE,
    TaskKind.HOST_COUNT,
    TaskKind.MASK,
    TaskKind.WILDCARD,
    TaskKind.SAME_NET,
)


def all_task_classes() -> list[type[Task]]:
    return [cls for classes in TASK_CLASSES.values() for cls in classes]


def available_kinds(level: Level, kinds: Iterable[TaskKind] | None = None) -> list[TaskKind]:
    """Kinds eligible for random selection.

    Explicitly requested kinds are always allowed, regardless of their ``min_level``.
    Without an explicit selection, IPv6 is excluded and ``min_level`` applies.
    """
    if kinds is not None:
        return [k for k in kinds if k in TASK_CLASSES]
    return [
        kind
        for kind, classes in TASK_CLASSES.items()
        if kind not in IPV6_KINDS and any(c.min_level.rank <= level.rank for c in classes)
    ]


def random_task(rng: random.Random, level: Level, kinds: Iterable[TaskKind] | None = None) -> Task:
    explicit = kinds is not None
    choices = available_kinds(level, kinds)
    if not choices:
        raise ValueError("no task kinds available")
    kind = rng.choice(choices)
    classes = [c for c in TASK_CLASSES[kind] if explicit or c.min_level.rank <= level.rank]
    return rng.choice(classes).generate(rng, level)
