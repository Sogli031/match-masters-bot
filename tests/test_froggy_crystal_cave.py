"""Froggy Fu on Gem Grab (research 20261119_173349, Crystal Cave).

A crystal (SlotModel value 16) is a coloured piece the entrance never targets:
the entrance refused it ("special 105 not ported"), so all 6 activations went
unchecked and the planner could not play the mode. A destroyed crystal scores
its number alone -- no colour value, no lotus stamp: 4 points high per crystal
in 8 of 21 moves before.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "froggy_crystal_cave"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


# 002->003: activation, no crystal hit; 021->022: two crystals in the cascade;
# 003->004: a lotus swipe that pulls two crystals into the stamped blob.
@pytest.mark.parametrize("before, after, swap", [
    ("002", "003", None), ("021", "022", None), ("003", "004", ((3, 4), (3, 3)))])
def test_move_with_crystals_replays_exactly(before, after, swap):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    action = {"kind": "booster"} if swap is None else next(
        a for a in sim.legal_actions(lab)[1] if (tuple(a["start"]), tuple(a["target"])) == swap)
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    state, want = result["state"], observed(_record(after))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["score"] == _lab(after)["score"]


def test_refill_monitor_checks_activation_with_crystals():
    from refill_monitor import check_transition
    assert check_transition(_record("002"), _record("003"))["verdict"] == "ok"
