"""Multiplier Madness (board 22) in the planner: a purple combo raises the
multiplier by one before its cascade is paid, Color Climb's hook with purple.

Research 20261119_181039 (Rumble, Jelly SE): 12 of 13 swipes score exactly;
20261119_181938 (Solo Challenge, Foxy Roxy SE): 14 of 14 supported moves.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "multiplier_madness"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after", [("race_015", "race_016"), ("solo_008", "solo_009")])
def test_move_replays_with_the_multiplier(before, after):
    from strategy_lab import planner, simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert lab["multiplier_colors"] == (4,) and sim.plan_refusal(lab) is None
    want, nxt = observed(_record(after)), _lab(after)
    for action in planner.actions(dict(lab, booster_auto=True)):
        result = sim.step(lab, action)
        if (result["supported"] and grid(result["state"]["board"]) == want["board"]
                and result["state"]["engine_refill"].rng.counter == want["rng"]):
            break
    else:
        pytest.fail("no action replays the recorded board")
    assert result["state"]["score"] == nxt["score"]
    assert result["state"]["score_multiplier"] == nxt["score_multiplier"]


def test_planner_supports_the_mode():
    import square_solo_live as sl
    state = _record("solo_008")["snapshot_state"]
    assert sl.planner_support(state, "Multiplier Madness") is None
