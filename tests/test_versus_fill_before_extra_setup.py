"""Versus: a booster fill with a move left beats a next-move extra setup.

Debug/runs 2026-11-11_21-56-57_900 (Multiplier Mushrooms, round 3/4, 2 moves,
6/7): the bot set up a four with a red three instead of the blue three that
filled the meter, then played that blue three on the last move and fired the
booster only after the opponent's turn.
"""

import json
from dataclasses import replace
from pathlib import Path

import move_strategy as ms
from tools.rebuild_evaluation import build_evaluation, build_states

FRAME = json.loads((Path(__file__).parent / "fixtures/versus_fill_before_extra_setup.json")
                   .read_text(encoding="utf-8"))
FILL = ((6, 5), (6, 4))
SETUP = ((0, 1), (1, 1))


def _ranked(**turn_changes):
    states = build_states(FRAME)
    turn = replace(states["turn_state"], **turn_changes)
    evaluations = [build_evaluation(c, FRAME["board"], FRAME["special_board"])
                   for c in FRAME["candidates"]]
    ranked = ms.prioritize_ranked_moves(
        evaluations, mode=states["mode"], score_rally_values=states["score_rally_values"],
        booster_state=states["booster_state"], turn_state=turn,
        strategy_context=states["strategy_context"],
    )
    return ranked


def _order(ranked):
    return [(e.candidate.start, e.candidate.target) for e in ranked]


def test_fill_with_a_move_left_goes_before_the_extra_setup():
    order = _order(_ranked())
    assert order[0] == FILL
    assert order.index(FILL) < order.index(SETUP)


def test_no_setup_strip_on_the_last_move_of_the_turn():
    # Nothing is left to fire the booster with; the setup is already worth
    # nothing there (final phase), so the strip must not touch it.
    ranked = _ranked(remaining_moves=1)
    assert not any("extra_setup_for_fill" in e.explanation for e in ranked)


MUSHROOM = ((3, 3), (2, 3))  # +4 multiplier points, mode bonus 46 at x10


def _mushroom_mode_bonus(multiplier, moves_left_in_match):
    states = build_states(FRAME)
    turn = replace(states["turn_state"], moves_left_in_match=moves_left_in_match)
    candidate = next(c for c in FRAME["candidates"]
                     if (tuple(c["start"]), tuple(c["target"])) == MUSHROOM)
    evaluation = build_evaluation(candidate, FRAME["board"], FRAME["special_board"])
    with ms.mushroom_multipliers_active(True), ms.score_multiplier_state(multiplier):
        return ms._phase_adjusted_mode_bonus(evaluation, states["mode"], turn)


def test_versus_mushroom_point_is_priced_by_the_moves_left_in_the_match():
    # x10, 4 moves left in the match: 3 moves after this one at ~15.5 base each.
    expected = 4 * ms.MEASURED_MOVE_VALUE * 3 / 10
    assert abs(_mushroom_mode_bonus(10, 4) - expected) < 1e-6


def test_unknown_match_horizon_keeps_the_old_price():
    assert _mushroom_mode_bonus(10, None) == 46.0
