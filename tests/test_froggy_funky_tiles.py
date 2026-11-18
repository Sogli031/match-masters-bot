"""Froggy Fu on Funky Tiles (research 20261118_110443, Solo).

The entrance never targets a funky cell and the funky markers never move onto
a lotus: with both, all 49 moves (34 swaps, 15 activations) replay with the
game's board, RNG, moves and score.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "froggy_funky_tiles"
# 002->003 activation; 005->006 and 038->039 were one RNG draw off while the
# markers could land on a lotus; 003->004 and 039->040 are swaps with a lotus.
PAIRS = [("002", "003", None), ("005", "006", None), ("038", "039", None),
         ("003", "004", ((2, 5), (3, 5))), ("039", "040", ((4, 1), (4, 2)))]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after, swap", PAIRS)
def test_move_replays_exactly(before, after, swap):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert sim.plan_refusal(lab) is None
    if swap is None:
        action = {"kind": "booster"}
    else:
        action = next(a for a in sim.legal_actions(lab)[1]
                      if {tuple(a["start"]), tuple(a["target"])} == set(swap))
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record(after)), _lab(after)
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["score"] == nxt["score"]


def test_refill_monitor_checks_froggy_activations():
    """Froggy Fu activations were all "booster, ne moze da se proveri"."""
    from refill_monitor import check_transition
    verdict = check_transition(_record("002"), _record("003"))
    assert verdict["verdict"] == "ok", verdict


def test_unread_funky_cells_refuse_the_plan():
    from strategy_lab import simulation as sim
    lab = _lab("002")
    lab["funky_cells"] = None
    assert "Funky" in sim.plan_refusal(lab)
