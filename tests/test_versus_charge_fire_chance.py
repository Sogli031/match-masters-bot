"""Versus prices charge that may never fire at the measured fire chance, and
the handover rules know when our turn closes the match.

Crazy Columns 2026-11-10 05:08:18: meter 0/7, 3 match moves left. A 15-point
blue three won the categorical blue tier over a 30-point move; the meter ended
the match at 6/7. At 05:08:48, the closing move of the match, the opponent
reply was still charged (moves_left_in_match is None on the final round).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402

VERSUS = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
EMPTY = ms.BoosterState(current=0, maximum=7, source="memory")


def _blue(cells, booster, turn):
    return ms._base_blue_priority_components_for_cells(cells, booster, turn, VERSUS)[0]


def test_far_charge_two_moves_after_is_priced_at_fire_chance():
    # Round 2 handover: 1 move this round + one estimated 2-move round = 3.
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=3)
    expected = 3.0 * ms.VERSUS_FAR_BLUE_PRIORITY_WEIGHT * ms.VERSUS_FIRE_CHANCE_TWO_MOVES_FAR
    assert abs(_blue(3.0, EMPTY, turn) - expected) < 1e-9


def test_near_charge_two_moves_after_uses_near_chance():
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=3)
    booster = ms.BoosterState(current=4, maximum=7, source="memory")
    expected = 2.0 * ms.NEAR_FILL_BLUE_PRIORITY_WEIGHT * ms.VERSUS_FIRE_CHANCE_TWO_MOVES_NEAR
    assert abs(_blue(2.0, booster, turn) - expected) < 1e-9


def test_long_horizon_keeps_full_weight():
    turn = ms.TurnState(remaining_moves=2, source="memory", moves_left_in_match=6)
    assert _blue(3.0, EMPTY, turn) == 3.0 * ms.VERSUS_FAR_BLUE_PRIORITY_WEIGHT


def test_round_clock_caps_only_current_round():
    turn = ms.TurnState(1, "memory", 5, time_left_seconds=8, seconds_per_move=4)
    assert ms._charge_horizon_effective_moves(turn) == 5
    assert ms._versus_charge_fire_chance(turn, 4) == 1.0
    assert ms._charge_horizon_effective_moves(ms.TurnState(3, "memory", 7, time_left_seconds=4,
                                                          seconds_per_move=4)) == 5
    assert ms._charge_horizon_effective_moves(ms.TurnState(3, "memory", 7)) == 7
    # With unknown round structure, only the current round is available.
    assert ms._charge_horizon_effective_moves(ms.TurnState(3, "memory", time_left_seconds=4,
                                                          seconds_per_move=4)) == 1


def test_fill_is_not_discounted():
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=3)
    booster = ms.BoosterState(current=5, maximum=7, source="memory")
    _p, fill, _w, _phase = ms._base_blue_priority_components_for_cells(3.0, booster, turn, VERSUS)
    assert fill == ms.BOOSTER_FILL_PRIORITY_BONUS


def test_closing_turn_of_match_has_no_handover():
    last = ms.TurnState(remaining_moves=1, source="memory", is_final_round=True,
                        opponent_turn_follows=False)
    assert not ms._versus_handover_threat_active(last, VERSUS)
    # We open the final round: the opponent still plays after us.
    first = ms.TurnState(remaining_moves=1, source="memory", is_final_round=True,
                         opponent_turn_follows=True)
    assert ms._versus_handover_threat_active(first, VERSUS)
    unknown = ms.TurnState(remaining_moves=1, source="memory", is_final_round=True)
    assert ms._versus_handover_threat_active(unknown, VERSUS)


def test_runtime_reads_turn_counter():
    def follows(turns):
        _booster, turn = runtime.resolve_strategy_states(
            0, 1, None, total_rounds=3, current_round=3, turns_left_in_match=turns
        )
        return turn.opponent_turn_follows

    assert follows(1) is False
    assert follows(2) is True
    assert follows(None) is None


def _exact_pick(monkeypatch, moves, moves_left, blue_missing=7, solo=True):
    """moves: {name: blue}; no extras, no setups -- only the blue tier decides."""
    from types import SimpleNamespace

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", lambda board, candidate, *args: SimpleNamespace(
        extra_moves=0, blue_cells=moves[candidate.start], board="after", special_board=None))
    monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [])
    session = SimpleNamespace(knows=lambda board: True, blue_missing=blue_missing,
                              moves_left=moves_left, solo=solo)
    evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t")) for name in moves]
    with ms.exact_refill_active(session):
        pick = ms.exact_refill_choice(evaluations, "root", None)
    return None if pick is None else (pick[0].candidate.start, pick[1])


def test_solo_exact_blue_that_cannot_fire_keeps_the_bots_pick(monkeypatch):
    # Color Crystals 05:37:46: 2 moves left, meter 0/7, 3 blue.
    assert _exact_pick(monkeypatch, {"points": 0, "blue": 3}, moves_left=2) is None
    # Filling now still fires on the next move.
    assert _exact_pick(monkeypatch, {"points": 0, "blue": 3}, moves_left=2, blue_missing=3) == ("blue", "plave")
    # Enough moves left to finish the meter.
    assert _exact_pick(monkeypatch, {"points": 0, "blue": 3}, moves_left=4) == ("blue", "plave")
    # Versus: the counter is one round, the charge carries on.
    assert _exact_pick(monkeypatch, {"points": 0, "blue": 3}, moves_left=2, solo=False) == ("blue", "plave")


def test_cascade_cross_lists_row_run_then_column_run():
    # Five Colors 2026-11-10 05:51:27: row of 4 crossed by a column of 3; the
    # game put the bomb on index draw % 7 of row+column (centre twice).
    cells = [(3, 1), (3, 2), (3, 3), (3, 4), (2, 2), (4, 2)]
    order = ms._lt_row_then_column_cells(cells)
    assert order == [(3, 1), (3, 2), (3, 3), (3, 4), (2, 2), (3, 2), (4, 2)]
    assert order[1437642772 % len(order)] == (4, 2)
    assert ms._lt_row_then_column_cells([(0, 0), (0, 1), (1, 1)]) is None
    assert ms._lt_listed_cells(order, ms.CASCADE_LT_CELL_ORDER) == order


def test_cascade_l_lists_its_corner_once():
    # Mutation Lab refill_misses 2026-11-11 161931: an L whose column ends on
    # the row. With the corner listed twice the bomb went on (5,3), the game
    # put it on (5,5); with the corner once the whole board is exact.
    cells = [(3, 5), (4, 5), (5, 3), (5, 4), (5, 5)]
    order = ms._lt_row_then_column_cells(cells)
    assert order == [(5, 3), (5, 4), (5, 5), (3, 5), (4, 5), (5, 5)]
    assert ms._lt_listed_cells(order, ms.CASCADE_LT_CELL_ORDER) == [
        (5, 3), (5, 4), (5, 5), (3, 5), (4, 5)]


def test_spray_on_a_mushroom_board_is_not_ported():
    from engine_refill import spray_five_unported

    three = [{"type": "spray_se_conversion", "converted_cells": [[0, 1], [0, 2], [0, 3]]},
             {"type": "match", "cascade": 1, "kind": "three"}]
    mushrooms = {"rules": {"boardModelName": 30}}
    assert spray_five_unported(three, mushrooms)
    assert not spray_five_unported(three, {"rules": {"boardModelName": 3}})
    assert not spray_five_unported(three)
    assert not spray_five_unported([{"type": "match", "cascade": 1, "kind": "three"}], mushrooms)
