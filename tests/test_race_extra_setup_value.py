"""Timed race: a move that sets up our own next extra keeps its full value.

Setups delivered an extra on the next board 84% of the time (34% without one)
over 1347 race moves; the learned future scale (0.25) priced them as a guess,
and 2026-10-08 10:21:18 passed a setup for 9 more points in a Showdown that
then ran out of moves with 61 s on the clock.
"""

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402

RACE = ms.StrategyContext(ms.STRATEGY_SOLO_6)
CHALLENGE = ms.StrategyContext(ms.STRATEGY_SOLO_6, solo_challenge=True)
BOOSTER = ms.BoosterState(current=0, maximum=7, source="memory")


def _plain_three():
    board = [[[ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE][(r + c) % 4] for c in range(7)] for r in range(7)]
    board[3][0] = board[3][1] = ms.RED
    board[2][2] = ms.RED
    specials = [[0] * 7 for _ in range(7)]
    after, after_special = ms.swap_cells(board, specials, (2, 2), (3, 2))
    candidate = ms.MoveCandidate((2, 2), (3, 2), ms.Direction.DOWN, after, after_special)
    return ms.evaluate_simulation(ms.simulate_candidate(candidate), ms.GameMode.NONE,
                                  include_future_value=False)


def _priority(evaluation, context, moves):
    turn = ms.TurnState(remaining_moves=moves, source="memory")
    return ms._weighted_priority(evaluation, ms.GameMode.NONE, BOOSTER, turn, None, context)


def _with_setup(evaluation, value):
    return replace(evaluation, score=evaluation.score + value,
                   lookahead_bonus=evaluation.lookahead_bonus + value,
                   extra_setup_bonus=value)


def test_race_counts_the_setup_in_full():
    base = _plain_three()
    setup = _with_setup(base, 20.0)
    gain = _priority(setup, RACE, 4) - _priority(base, RACE, 4)
    assert abs(gain - 20.0) < 1e-6


def test_challenge_keeps_the_learned_future_scale():
    base = _plain_three()
    setup = _with_setup(base, 20.0)
    gain = _priority(setup, CHALLENGE, 4) - _priority(base, CHALLENGE, 4)
    assert gain < 20.0 - 1e-6


def test_last_move_of_the_round_gets_nothing():
    base = _plain_three()
    setup = _with_setup(base, 20.0)
    assert abs(_priority(setup, RACE, 1) - _priority(base, RACE, 1)) < 1e-6
