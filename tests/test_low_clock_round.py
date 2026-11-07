import pytest


@pytest.mark.parametrize(
    "state, expected",
    [
        # GameLogic.CurrentRound is 0-based: round 1 of 3, another round follows.
        ({"rounds_total": 3, "current_round": 0}, True),
        ({"rounds_total": 3, "current_round": 1}, True),
        # Last round: the low clock plays for points only.
        ({"rounds_total": 3, "current_round": 2}, False),
        # Single-round and unknown round structure keep the points-only rule.
        ({"rounds_total": 1, "current_round": 0}, False),
        ({"rounds_total": None, "current_round": None}, False),
        ({}, False),
    ],
)
def test_later_round_follows(state, expected):
    import memory_gui as gui

    assert gui.MemoryWindow._later_round_follows(state) is expected
