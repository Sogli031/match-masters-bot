"""Laser Matches (board 18) in the planner: the swipe's own match fires the
laser rays, and the moves come back like the game's.

Research 20261119_190737 (Solo Challenge, Brocco Boogie): board, RNG, moves
and score 11 of 11 swipes and activations (the other move a Teleport perk).
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "laser_matches"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after, booster", [("001", "002", False), ("008", "009", True)])
def test_move_replays(before, after, booster):
    from strategy_lab import planner, simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert sim.plan_refusal(lab) is None
    want, nxt = observed(_record(after)), _lab(after)
    for action in planner.actions(dict(lab, booster_auto=booster)):
        result = sim.step(lab, action)
        if (result["supported"] and grid(result["state"]["board"]) == want["board"]
                and result["state"]["engine_refill"].rng.counter == want["rng"]):
            break
    else:
        pytest.fail("no action replays the recorded board")
    assert result["state"]["score"] == nxt["score"]
    assert result["state"]["turn_state"]["remaining_moves"] == want["moves"]


def test_planner_supports_the_mode():
    import square_solo_live as sl
    assert sl.planner_support(_record("001")["snapshot_state"], "Laser Mode") is None
