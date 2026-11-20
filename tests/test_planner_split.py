"""Root parallelism (planner.PLAN_WORKERS): each worker plans from the root
over its share of the first actions; the split keeps the best of them."""
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parent / "fixtures" / "monkey_joojoo" / "20261120_111530_super-sized" / "003.json"


@pytest.fixture
def lab():
    from tools.plan_reference import load
    return load(BOARD)


def test_root_actions_limit_the_first_step(lab):
    from strategy_lab import planner
    from strategy_lab.simulation import step
    first = [a for a in planner.actions(lab) if step(lab, a)["supported"]][:2]
    best, stats = planner.plan(lab, width=4, max_steps=3, root_actions=first)
    assert best.actions[0] in first
    assert all(line.actions[0] in first for line in stats["lines"] if line.actions)


def test_split_keeps_the_best_worker(lab, monkeypatch):
    from strategy_lab import planner
    with planner.rules(lab):
        first = planner.actions(lab)
    alone = [planner.plan(lab, width=2, max_steps=3, root_actions=first[i::2])[0] for i in range(2)]
    monkeypatch.setattr(planner, "PLAN_WORKERS", 2)
    monkeypatch.setattr(planner, "SPLIT_MIN_WIDTH", 1)
    try:
        best, stats = planner.plan(lab, width=2, max_steps=3)
    finally:
        planner._SPLIT_POOL.terminate()
        planner._SPLIT_POOL = None
    assert stats["workers"] == 2
    assert best.value == max(line.value for line in alone)
    assert best.actions in [line.actions for line in alone]
