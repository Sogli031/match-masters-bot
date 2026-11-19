"""Match & Hatch hatched figures in the exact planner (strategy_lab.simulation).

Research 20261119_092747: every recorded swipe that set off a Bandit, a
skull or a Foxy can replays exactly (board, specials, RNG). The score is
not checked: in this game plain swipes miss it by 1-4 points as well. The
Bandit draws its targets from the engine RNG (EngineRefill.bandit_targets),
a skull fires along its colour's directions, a can's ray makes the shape's
own special (not a hatched one) and may run the whole column. Cleo is still
refused (041 misses, 088 does not).
"""
import pytest


import json
from pathlib import Path

FRAMES = Path(__file__).resolve().parent / "fixtures" / "match_and_hatch"
CASES = [
    # A skull swiped down fires a cross and sets off the Bandit (32 draws).
    ("hatch_002", "hatch_003", {"start": [3, 6], "target": [4, 6], "direction": "down"}),
    # A can's ray of four: a plain vertical, no hatched draw.
    ("hatch_011", "hatch_012", {"start": [2, 4], "target": [2, 4], "direction": "down"}),
    # A Brocco piece swiped, the Bandit fires in the cascade.
    ("hatch_039", "hatch_040", {"start": [6, 3], "target": [6, 4], "direction": "right"}),
    # Cans painting a whole column (a line of seven).
    ("hatch_044", "hatch_045", {"start": [6, 3], "target": [6, 3], "direction": "up"}),
    ("hatch_081", "hatch_082", {"start": [6, 4], "target": [6, 4], "direction": "up"}),
    # A green skull fires diagonally.
    ("hatch_077", "hatch_078", {"start": [5, 0], "target": [5, 1], "direction": "right"}),
    # A can's ray onto a row special makes a T with two Lightnings.
    ("hatch_090", "hatch_091", {"start": [4, 1], "target": [4, 1], "direction": "right"}),
]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from
    capture = capture_from(_record(name))
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    return lab, capture_mode(capture["profile"]).value


def _action(state, wanted):
    from strategy_lab import planner
    return next(a for a in planner.actions(state) if a.get("kind", "swap") == "swap"
                and list(a["start"]) == wanted["start"] and list(a["target"]) == wanted["target"]
                and a.get("direction") == wanted["direction"])


@pytest.mark.parametrize("before, after, wanted", CASES)
def test_hatched_figure_replays_exactly(before, after, wanted, monkeypatch):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    state, mode = _lab(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {mode})
    result = sim.step(state, _action(state, wanted))
    assert result["supported"], result.get("reason")
    state = result["state"]
    want = observed(_record(after))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
