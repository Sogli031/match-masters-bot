"""Versus final round: a meter-completing move with a move left to fire it.

It carries the measured value of an activation (VERSUS_FINAL_ROUND_ACTIVATION_VALUE,
~20 ranking units over the move that follows) instead of the generic fill premium
(BOOSTER_FILL_PRIORITY_BONUS, 2 cells = ~11). Recorded case:
Debug/runs 2026-11-10_09-51-27_582 (Color Crystals, final round, 2 moves, 6/7).
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import move_strategy as ms
from tools.rebuild_evaluation import build_evaluation, build_states

FRAME = json.loads((Path(__file__).parent / "fixtures/versus_final_fill_activation.json")
                   .read_text(encoding="utf-8"))
FILL = ((4, 5), (4, 6))


def _ranked(**turn_changes):
    states = build_states(FRAME)
    turn = replace(states["turn_state"], **turn_changes)
    evaluations = [build_evaluation(c, FRAME["board"], FRAME["special_board"])
                   for c in FRAME["candidates"]]
    return ms.prioritize_ranked_moves(
        evaluations, mode=states["mode"], score_rally_values=states["score_rally_values"],
        booster_state=states["booster_state"], turn_state=turn,
        strategy_context=states["strategy_context"],
    )


def _fill(ranked):
    return next(e for e in ranked if (e.candidate.start, e.candidate.target) == FILL)


def test_fill_with_a_move_left_carries_the_measured_activation_value():
    fill = _fill(_ranked())
    assert fill.booster_fill_bonus == pytest.approx(ms.VERSUS_FINAL_ROUND_ACTIVATION_VALUE)
    assert ms.VERSUS_FINAL_ROUND_ACTIVATION_VALUE > ms.BOOSTER_FILL_PRIORITY_BONUS


def test_fill_on_the_last_move_of_the_match_has_no_value():
    fill = _fill(_ranked(remaining_moves=1))
    assert fill.booster_fill_bonus == 0
