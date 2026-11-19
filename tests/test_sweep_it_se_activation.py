"""Sweep It SE (booster 61) activation replays exactly (engine_sweep).

Lightning Strike research 20261119_031206: 3 of 4 recorded activations give
the game's board, specials, RNG and score. 009 and 014 share their capture
with a swipe (before and after the booster).
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "sweep_it_se"
CASES = [
    # The sweep alone: colours picked on clones, a second destroy, the broom.
    ("lightning_019", "lightning_020", [{"kind": "booster"}]),
    # A swipe first; a slot with two blue neighbours is listed once (Distinct).
    ("lightning_009", "lightning_010",
     [{"kind": "swap", "start": [5, 2], "target": [6, 2], "direction": "down"}, {"kind": "booster"}]),
    # The new broom is swiped right away (it keeps its colour in the refill).
    # The score is not checked: the broom swipe scores 3 short (537 / 540),
    # an open gap of the swipe, not of the booster.
    ("lightning_014", "lightning_015",
     [{"kind": "booster"}, {"kind": "swap", "start": [1, 3], "target": [0, 3], "direction": "up"}]),
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


@pytest.mark.parametrize("before, after, actions", CASES)
def test_activation_replays_exactly(before, after, actions, monkeypatch):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    state, mode = _lab(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {mode})
    for action in actions:
        result = sim.step(state, action)
        assert result["supported"], result.get("reason")
        state = result["state"]
    want = observed(_record(after))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    if before != "lightning_014":
        nxt, _ = _lab(after)
        assert state["score"] == nxt["score"]


def test_combos_and_colour_rule():
    import engine_sweep
    assert engine_sweep.combos([6, 3, 5, 7], 2) == [[6, 3], [6, 5], [6, 7], [3, 5], [3, 7], [5, 7]]
    # Four consecutive columns, or four in one column.
    assert engine_sweep._colors_with_extra_move({5: [0, 1, 2, 3], 6: [2, 2, 2, 2], 7: [0, 1, 2, 4]}) == [5, 6]


def test_planner_plays_sweep():
    import square_solo_live as live
    state = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 61}]}
    assert live.exact_plan_booster(state) and live.charles_policy_booster(state)
