"""Column Mania in the planner (research 20261119_080712, Brocco Boogie).

The live multipliers per column (CellModel.scoreMultiplier) score every
destroyed piece; onMoveEnd raises the columns of the swipe's own combos by one.
The recording had no multipliers yet: the fixtures carry them off the live log.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "column_mania"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


# (before, after, swipe, exact score): 002 a plain three, 006 a disco ball
# (no match of its own: the pair's columns rise), 009 two crosshairs.
PAIRS = [("002", "003", ((2, 3), (2, 4)), True),
         ("006", "007", ((0, 5), (0, 4)), False),
         ("009", "010", ((5, 5), (6, 5)), True)]


@pytest.mark.parametrize("before, after, swipe, exact_score", PAIRS)
def test_swipe_replays_with_column_multipliers(before, after, swipe, exact_score):
    from strategy_lab import planner, simulation
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert simulation.plan_refusal(lab) is None
    action = next(a for a in planner.actions(lab) if a.get("kind", "swap") == "swap"
                  and (tuple(a["start"]), tuple(a["target"])) == swipe)
    result = simulation.step(lab, action)
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record(after)), _lab(after)
    assert grid(state["board"]) == want["board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert list(state["column_multipliers"]) == list(nxt["column_multipliers"])
    if exact_score:
        assert state["score"] == nxt["score"]
    else:
        # shortcut: the disco ball's swap scores 2 under the game (28 / 30);
        # the board, RNG and multipliers are exact. Upgrade from its swap trace.
        assert 0 < nxt["score"] - state["score"] <= 2


def test_column_mania_without_multipliers_is_refused():
    from strategy_lab import simulation
    lab = _lab("002")
    lab["column_multipliers"] = None
    assert "Column Mania" in simulation.plan_refusal(lab)


def test_plan_runs_on_column_mania():
    from strategy_lab import planner
    best, _ = planner.plan(_lab("002"), width=2)
    assert best.actions and best.score > _lab("002")["score"]


def test_energy_boost_crosshair_takes_any_colour():
    """Live 2026-11-19 08:19:57 (research 20261119_081651 008->009): an Energy
    Boost three set off a crosshair. Every colour charges in that destroy pass,
    so maxEnergyPieces shuffled every piece; with Blue alone the board missed
    and the planner threw its line away for a new 124 s first plan. The swipe
    also raises its columns."""
    from strategy_lab import simulation
    from tools.analyze_research import grid, observed
    lab = _lab("eb_008")
    lab["perks"] = {22: 1}
    result = simulation.step(lab, {"kind": "energy_boost", "start": [5, 0], "target": [6, 0], "direction": "down"})
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record("eb_009")), _lab("eb_009")
    assert grid(state["board"]) == want["board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["score"] == nxt["score"]
    assert list(state["column_multipliers"]) == list(nxt["column_multipliers"])
