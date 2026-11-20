"""Billie Boom (41): what the 2026-11-20 recordings already prove.

The colour-pair pick is not ported yet (``simulation.BILLIE_BOOM_PORTED`` is
False, so ``step`` refuses the activation). These tests do not depend on the
pick: they force the pair the game played and check the parts that are settled.

* The settled board must be exact for all 14 activations of the Solo Super
  Sized game (the sucked set is every plain piece of the two colours;
  ``suckSpecials`` is false, so specials on those cells stay).
* ``DronePiecePosition`` must put the drone exactly where the recording has it:
  13 activations on (7, 4) = (Columns - 1, Rows / 2), and 042->043 on (7, 5)
  because (7, 4) was not a plain piece there.

Fixtures live in ``tests/fixtures/billie_boom`` because ``Debug/research`` is
deleted between sessions.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

import engine_billie_boom as eb
from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
from strategy_lab import simulation
from tools.analyze_research import grid, load, observed

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "tests/fixtures/billie_boom/20261120_112013_super-sized"

# before-activation file -> the colour pair the game sucked (measured by
# forcing every pair, Debug/billie_truth.py).
PLAYED = {
    3: (3, 6), 6: (2, 4), 8: (4, 6), 11: (2, 4), 14: (3, 6), 17: (2, 6),
    19: (3, 6), 22: (2, 6), 25: (2, 4), 27: (2, 3), 29: (2, 6), 33: (2, 6),
    35: (2, 4), 42: (2, 6),
}

pytestmark = pytest.mark.skipif(not SESSION.is_dir(),
                                reason="Billie Boom recording not present")


def _board(record):
    return [[int(v) for v in row] for row in record["board"]]


def _specials(record):
    return [[int(v) for v in row] for row in record["special_board"]]


@lru_cache(maxsize=1)
def activations():
    """[(before_no, after_no, pair)] for every activation in the session."""
    out = []
    for before_no, pair in sorted(PLAYED.items()):
        after_no = before_no + 1
        if not (SESSION / f"{after_no:03d}.json").is_file():
            continue
        out.append((before_no, after_no, pair))
    return out


def _settle(before_no, after_no, pair):
    """Step the activation with ``pair`` forced; returns the diff against the next record."""
    rec_a, cap_a = load(SESSION / f"{before_no:03d}.json")
    rec_b, _ = load(SESSION / f"{after_no:03d}.json")
    certified = simulation.PREFIX_MODES
    ported = simulation.BILLIE_BOOM_PORTED
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    simulation.BILLIE_BOOM_PORTED = True
    original = eb.choose

    def forced(board, specials, params, evaluate, activation=1):
        return pair, eb.group_cells(board, specials, pair), []

    eb.choose = forced
    try:
        resolved = resolve_refill_overrides(cap_a["profile"])
        thresholds = None if resolved.get("resolved") else next(
            iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
        lab = lab_move(cap_a, thresholds=thresholds)
        lab["check_cascade_timing"] = True
        lab["booster_type"] = 41
        result = simulation.step(lab, {"kind": "booster"})
    finally:
        eb.choose = original
        simulation.PREFIX_MODES = certified
        simulation.BILLIE_BOOM_PORTED = ported
    if not result.get("supported"):
        return {"skip": result.get("reason")}
    state = result["state"]
    want = observed(rec_b)
    board, special = grid(state["board"]), grid(state["special_board"])
    return {
        "cells": sum(board[r][c] != want["board"][r][c]
                     for r in range(len(board)) for c in range(len(board[r]))),
        "specials": sum(special[r][c] != want["special_board"][r][c]
                        for r in range(len(special)) for c in range(len(special[r]))),
        "pair": pair,
    }


@pytest.fixture(scope="module")
def settled():
    results = []
    for before_no, after_no, pair in activations():
        results.append((before_no, _settle(before_no, after_no, pair)))
    return results


def test_all_fourteen_activations_are_in_the_fixtures():
    assert len(activations()) == 14
    for before_no, after_no, _ in activations():
        assert (SESSION / f"{before_no:03d}.json").is_file()
        assert (SESSION / f"{after_no:03d}.json").is_file()


def test_played_pair_settles_the_board_exactly(settled):
    """The game's own pair reproduces the board in 14 of 14 activations."""
    assert len(settled) == 14
    misses = [(before_no, got) for before_no, got in settled
              if got.get("skip") or got["cells"]]
    assert not misses, misses


def test_drone_position_matches_the_recording():
    """DronePiecePosition: (Columns - 1, Rows / 2), else the nearest plain cell."""
    positions = []
    for before_no, after_no, _ in activations():
        rec_a = json.loads((SESSION / f"{before_no:03d}.json").read_text(encoding="utf-8"))
        rec_b = json.loads((SESSION / f"{after_no:03d}.json").read_text(encoding="utf-8"))
        position = eb.drone_position(_board(rec_a), _specials(rec_a))
        drones = [(r, c) for r in range(len(_specials(rec_b)))
                  for c in range(len(_specials(rec_b)[r])) if _specials(rec_b)[r][c] == eb.BILLIE_DRONE]
        assert drones == [position], (before_no, position, drones)
        positions.append(position)
    assert positions.count((7, 4)) == 13
    assert positions.count((7, 5)) == 1
