"""Brocco Boogie (booster 44) activation replays exactly (engine_brocco).

Research 20261113-20261118: 146 of 147 recorded activations give the game's
board, specials and RNG. One pair per rule that a miss pinned down.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "brocco_boogie"
PAIRS = [
    # Mutation Lab 20261118_202716 034->035: a ball's neighbour is a ball; the
    # game reads the colour the slot keeps under it.
    ("lab_034", "lab_035"),
    # Candy World 20261113_123727 014->015: a red/blue tile matches blue, so a
    # cell next to it touches blue.
    ("candy_014", "candy_015"),
    # Multiplier Mushrooms 20261113_150011 004->005: mushrooms are destroy candidates.
    ("mushrooms_004", "mushrooms_005"),
    # Funky Tiles 20261113_143157 009->010: the destroy fires a funky marker,
    # and the markers never move onto a ball.
    ("funky_009", "funky_010"),
    # Color Crystals 20261120_063436: crystals are destroy candidates.
    ("crystals_000", "crystals_001"),
]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from
    capture = capture_from(_record(name))
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    return lab, capture_mode(capture["profile"]).value


@pytest.mark.parametrize("before, after", PAIRS)
def test_activation_replays_exactly(before, after, monkeypatch):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab, mode = _lab(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {mode})
    result = sim.step(lab, {"kind": "booster"})
    assert result["supported"], result.get("reason")
    state, want = result["state"], observed(_record(after))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    nxt, _ = _lab(after)
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["score"] == nxt["score"]


def test_planner_plays_brocco():
    import square_solo_live as live
    state = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 44}]}
    assert live.exact_plan_booster(state) and live.charles_policy_booster(state)
