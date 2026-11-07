"""Checkmate Charles knights clear far more than the three modelled cells.

Measured 2026-10-08 (modes without a multiplier, since 2026-09-01): a move with
one knight scored 2.83x its prediction, +12.6 cells; moves without a knight in
the same games were exact. The gap is added as an expectation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402


def _result(knights):
    board = [[ms.GREEN] * 4 for _ in range(4)]
    specials = [[0] * 4 for _ in range(4)]
    candidate = ms.MoveCandidate((0, 0), (0, 1), ms.Direction.RIGHT, board, specials)
    result = ms.SimulationResult(candidate, board, specials, cleared_cells=6,
                                 cleared_color_counts={ms.GREEN: 6})
    result.intent_events = [
        {"type": "special_activation", "cascade": 1, "special": "knight", "cell": [0, i]}
        for i in range(knights)
    ]
    return ms._apply_knight_charge_expectation(result)


def test_one_knight_adds_the_measured_cells():
    r = _result(1)
    assert r.expected_extra_cells == ms.KNIGHT_EXPECTED_EXTRA_CELLS[1]
    rally = {ms.GREEN: 2.0, ms.RED: 4.0}
    assert ms._instant_score(r, rally) == 6 * 2.0 + 12.0 * 3.0
    assert ms._instant_score(r) == 6 + 12.0


def test_three_or_more_knights_use_the_last_band():
    assert _result(5).expected_extra_cells == ms.KNIGHT_EXPECTED_EXTRA_CELLS[3]


def test_no_knight_no_change():
    r = _result(0)
    assert r.expected_extra_cells == 0.0
    assert ms._instant_score(r) == 6
