"""A move in hand is ranked at the line's score multiplier (Vertical Rush, 2026-11-19)."""
from strategy_lab.planner import Line, _rank


def _line(multiplier):
    return Line({"score": 1000, "turn_state": {"remaining_moves": 3}, "rank_move_value": 100,
                 "score_multiplier": multiplier})


def test_move_value_follows_the_multiplier():
    assert _rank(_line(None)) == 1000 + 3 * 100
    assert _rank(_line(20)) == 1000 + 3 * 100 * 20
    assert _rank(_line(0)) == 1000 + 3 * 100
