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
