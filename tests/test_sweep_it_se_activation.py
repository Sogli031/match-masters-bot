"""Sweep It SE (booster 61) activation replays exactly (engine_sweep).

Lightning Strike research 20261119_031206: 4 of 4 recorded activations give
the game's board, specials, RNG and score. 009 and 014 share their capture
with a swipe (before and after the booster).
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "sweep_it_se"
CASES = [
    # A blast leaves the broom, and a Lightning's hits fire in pick order
    # (Special O'Rama refill_misses 20261119_050728, a plain swipe).
    ("broom_survives_000", "broom_survives_001", [{"kind": "swap", "start": [4, 1], "target": [5, 1], "direction": "down"}]),
    # Special O'Rama broom swipes: the layer's two draws, then the threes'
    # types (refill_misses 20261119_045018 and 045748); a three on a
    # six's end joins it (050042: no type, one Lightning); two threes take
    # their types after the layer's two draws (050533).
    # The threes take their types x-major, not in the broom's conversion
    # order (refill_misses 20261119_054106: column 1 before column 3).
    ("xorder_000", "xorder_001", [{"kind": "swap", "start": [0, 2], "target": [0, 3], "direction": "right"}]),
    # A four on a six's cell joins the six: one type draw, not two
    # (refill_misses 20261119_054734).
    ("four_joins_000", "four_joins_001", [{"kind": "swap", "start": [5, 6], "target": [6, 6], "direction": "down"}]),
    ("orama_broom4_000", "orama_broom4_001", [{"kind": "swap", "start": [5, 1], "target": [5, 0], "direction": "left"}]),
    ("orama_broom3_000", "orama_broom3_001", [{"kind": "swap", "start": [4, 6], "target": [4, 5], "direction": "left"}]),
    ("orama_broom2_000", "orama_broom2_001", [{"kind": "swap", "start": [6, 6], "target": [6, 5], "direction": "left"}]),
    ("orama_broom_000", "orama_broom_001", [{"kind": "swap", "start": [5, 1], "target": [5, 0], "direction": "left"}]),
    # Special O'Rama: a blue broom next to a slot does not list it as blue
    # (canBeMatched false; refill_misses 20261119_044450, 4 draws more).
    ("blue_broom_000", "blue_broom_001", [{"kind": "booster"}]),
    # A broom already on the board: its slot keeps a colour the broom
    # placement reads (refill_misses 20261119_043626).
    ("second_broom_000", "second_broom_001", [{"kind": "booster"}]),
    # Two brooms in a column, the lower one swiped: the upper one falls with
    # its own colour (refill_misses 20261119_043526).
    ("spent_broom_000", "spent_broom_001", [{"kind": "swap", "start": [6, 4], "target": [6, 3], "direction": "left"}]),
    # A piece dragged onto the broom is the broom dragged back (live
    # 2026-11-19 04:27: the game took only that; one draw short otherwise).
    ("onto_000", "onto_001", [{"kind": "swap", "start": [3, 5], "target": [3, 6], "direction": "right"}]),
    # One combo joins three lines (refill_misses 20261119_042300): each
    # special sits on its combo's first x-major cell, not the first moved one.
    ("xmajor_000", "xmajor_001", [{"kind": "booster"}]),
    # The first activation: the energy colour's refill weight drops (1 -> 0)
    # before the booster's own refill.
    ("lightning_003", "lightning_004", [{"kind": "booster"}]),
    # Vertical Rush refill_misses 20261119_122958: a broom swipe; the row
    # threes through the column five join its combo (Lightning on (4, 4)).
    ("vr_broom_join_000", "vr_broom_join_001",
     [{"kind": "swap", "start": [2, 2], "target": [2, 3], "direction": "right"}]),
    # Vertical Rush 123058 (x3) and 123246 (x10): the clone's score rise is
    # paid at the multiplier, the specials left are not.
    ("vr_multiplier3_000", "vr_multiplier3_001", [{"kind": "booster"}]),
    ("vr_multiplier10_000", "vr_multiplier10_001", [{"kind": "booster"}]),
    # The sweep alone: colours picked on clones, a second destroy, the broom.
    ("lightning_019", "lightning_020", [{"kind": "booster"}]),
    # A swipe first; a slot with two blue neighbours is listed once (Distinct).
    ("lightning_009", "lightning_010",
     [{"kind": "swap", "start": [5, 2], "target": [6, 2], "direction": "down"}, {"kind": "booster"}]),
    # The new broom is swiped right away (it keeps its colour in the refill).
    # The broom itself scores the swept colour's value (+3 here).
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
    nxt, _ = _lab(after)
    assert state["score"] == nxt["score"]


def test_planned_line_keeps_the_dropped_weight(monkeypatch):
    """Research 20261119_041029 (live, 04:14): the plan carried the booster's
    state into an Energy Boost broom swipe; with the old weight its refill
    differed, the next planned swipe was illegal and the plan was thrown away."""
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    state, mode = _lab("chain_002")
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {mode})
    state["perks"] = {sim.PERK_ENERGY_BOOST: 1}
    for action in ({"kind": "booster"},
                   {"kind": "energy_boost", "start": [4, 0], "target": [4, 1], "direction": "right"}):
        result = sim.step(state, action)
        assert result["supported"], result.get("reason")
        state = result["state"]
    want = observed(_record("chain_004"))
    assert grid(state["board"]) == want["board"]
    assert state["engine_refill"].rng.counter == want["rng"]


def test_combos_and_colour_rule():
    import engine_sweep
    assert engine_sweep.combos([6, 3, 5, 7], 2) == [[6, 3], [6, 5], [6, 7], [3, 5], [3, 7], [5, 7]]
    # Four consecutive columns, or four in one column.
    assert engine_sweep._colors_with_extra_move({5: [0, 1, 2, 3], 6: [2, 2, 2, 2], 7: [0, 1, 2, 4]}) == [5, 6]


def test_planner_plays_sweep():
    import square_solo_live as live
    state = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 61}]}
    assert live.exact_plan_booster(state) and live.charles_policy_booster(state)


def test_swipe_onto_broom_drags_the_broom():
    import square_solo_live as live
    special = [[0] * 7 for _ in range(7)]
    special[3][6] = 45
    move = {"kind": "swap", "start": (3, 5), "target": (3, 6), "direction": "right"}
    assert live.broom_first(special, move) == {"kind": "swap", "start": (3, 6), "target": (3, 5),
                                               "direction": "left"}
    plain = {"kind": "swap", "start": (2, 5), "target": (2, 6), "direction": "right"}
    assert live.broom_first(special, plain) is plain


def test_broom_packing_only_other_colours_is_a_move():
    """Live 2026-11-19 05:22:46: the broom at (3,1) swept 4 right and packed
    a column of six 6s. The heuristic dropped non-target matches, the plan's
    swipe had no evaluation and the bot waited 3x, then lost the plan."""
    import recognition
    import runtime

    board = [[1, 2, 3, 6, 2, 5, 5], [2, 6, 2, 4, 6, 5, 6], [2, 3, 3, 6, 5, 1, 5], [1, 99, 4, 4, 3, 6, 1],
             [2, 4, 3, 4, 2, 6, 5], [2, 3, 1, 6, 3, 3, 5], [1, 2, 1, 4, 5, 1, 3]]
    special = [[0] * 7 for _ in range(7)]
    special[3][1] = 45
    assert runtime.evaluate_plan_pair(board, special, ((3, 1), (3, 2)), recognition.GameMode.SPECIAL_O_RAMA,
                                      include_future_value=False) is not None
