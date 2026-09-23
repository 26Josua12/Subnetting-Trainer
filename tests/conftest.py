from __future__ import annotations

import random

import pytest

from subnet_trainer.core.levels import Level
from subnet_trainer.core.tasks.base import Task

SAMPLES = 1000


def generate_many(cls: type[Task], level: Level, n: int = SAMPLES) -> list[Task]:
    rng = random.Random(f"{cls.__name__}-{level}")
    return [cls.generate(rng, level) for _ in range(n)]


@pytest.fixture(params=list(Level), ids=lambda lv: lv.value)
def level(request: pytest.FixtureRequest) -> Level:
    return request.param
