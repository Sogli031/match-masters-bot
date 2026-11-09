"""Foxy Roxy SE spray can in the exact refill (2026-11-09 Column Mania, Solo).

Frames from Debug/research/20261109_190809_column-mania: the booster drops
spray cans (SlotValue 31, the slot keeps a colour); a can's swipe paints a ray.
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms

FRAMES = Path(__file__).resolve().parent / "fixtures" / "spray_column_mania"


def _replay(monkeypatch, before, action):
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from
    record = json.loads((FRAMES / f"{before}.json").read_text(encoding="utf-8"))
    capture = capture_from(record)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    return sim.step(lab, action)


def _assert_matches(result, after):
    from tools.analyze_research import grid, observed
    want = observed(json.loads((FRAMES / f"{after}.json").read_text(encoding="utf-8")))
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]


def _spray(cell, direction):
    return {"kind": "swap", "start": list(cell), "target": list(cell), "direction": direction}


@pytest.mark.parametrize("before, after, cell, direction", [
    # Row of four painted to the left: the rocket sits on the leftmost cell.
    ("006", "007", (1, 4), "left"),
    # Row of four painted to the right: again the leftmost cell.
    ("007", "008", (5, 3), "right"),
    # Ray of five: a resting lightning.
    ("014", "015", (0, 2), "right"),
])
def test_spray_swipe_replays_exactly(monkeypatch, before, after, cell, direction):
    result = _replay(monkeypatch, before, _spray(cell, direction))
    assert result["supported"], result.get("reason")
    _assert_matches(result, after)


def test_resting_spray_can_does_not_block_ordinary_swipes(monkeypatch):
    # 006 holds two cans; before the port every swipe there was rejected.
    from strategy_lab import planner
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from
    record = json.loads((FRAMES / "006.json").read_text(encoding="utf-8"))
    capture = capture_from(record)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    results = [sim.step(lab, a) for a in planner.actions(lab) if a["start"] != a["target"]]
    assert results and any(r["supported"] for r in results)
    assert not any(r.get("reason") == "random or equipment special on board" for r in results)


def test_ray_of_seven_making_a_five_is_not_ported(monkeypatch):
    result = _replay(monkeypatch, "012", _spray((1, 7), "left"))
    assert not result["supported"]
    assert "five from the spray" in result["reason"]


def test_planner_keeps_every_spray_direction(monkeypatch):
    from strategy_lab import planner
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    record = json.loads((FRAMES / "007.json").read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record), thresholds=None)
    directions = {a["direction"] for a in planner.actions(lab) if a["start"] == a["target"] == [5, 3]}
    assert {"left", "right"} <= directions


def test_refill_board_maps_spray_can_outside_match_and_hatch():
    import engine_refill
    assert engine_refill.SIM_SPRAY_CAN == ms.SPECIAL_SPRAY_SE
    assert engine_refill.ENGINE_SPRAY_CAN in engine_refill.ENGINE_BALL_VALUES
