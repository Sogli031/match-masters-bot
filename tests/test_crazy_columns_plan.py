"""Crazy Columns (board 19) in the exact planner, research 20261118_215913.

A destroyed piece scores its colour value x (column + 1). Board, RNG, moves
and score replay exactly on these moves.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "crazy_columns"
# 004->005: three in column 6 (+21); 010->011: three in column 2 (+9);
# 007->008: a Foxy Roxy SE activation.
PAIRS = [("004", "005"), ("010", "011"), ("007", "008")]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after", PAIRS)
def test_move_replays_with_column_score(before, after):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert lab["mode"] in sim.PREFIX_MODES and sim.plan_refusal(lab) is None
    played = _record(after)["refill_input"]
    detail = played[2]
    action = ({"kind": "booster"} if played[1] == "activate_booster" else
              {"kind": "swap", "start": detail["start"], "target": detail["target"],
               "direction": detail["direction"]})
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record(after)), _lab(after)
    assert grid(state["board"]) == want["board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["score"] == nxt["score"]


def test_column_score_only_inside_the_simulator():
    import move_strategy as ms
    assert ms._CRAZY_COLUMNS_CELL_SCORE is False
