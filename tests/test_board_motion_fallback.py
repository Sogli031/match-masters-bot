from dataclasses import replace

import pytest
import move_strategy as ms


def evaluation(row):
    board = [[2 + (r + c) % 4 for c in range(7)] for r in range(7)]
    candidate = ms.MoveCandidate((row, 0), (row, 1), ms.Direction.RIGHT,
                                 board, [[0] * 7 for _ in range(7)])
    return ms.MoveEvaluation(candidate, 3, 3, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, "test",
        intent_events=[dict(type="match", cascade=1, kind="three",
                            cells=[[row, c] for c in range(3)])])


def fallback(items, moves=4, current=0, context="solo_6"):
    return ms._with_board_motion_fallback(items, "None", False, None, False,
        ms.BoosterState(current=current), ms.TurnState(remaining_moves=moves), context)


def test_actual_fall_distance_and_blocker():
    assert ms._plain_match_fall_distance(evaluation(1)) == 3
    assert ms._plain_match_fall_distance(evaluation(5)) == 15
    item = evaluation(5)
    for c in range(3):
        item.candidate.board[3][c] = ms.BLOCKED
    assert ms._plain_match_fall_distance(item) == 3


def test_close_nonblue_moves_prefer_more_motion(monkeypatch):
    monkeypatch.setattr(ms, "_best_next_blue_cells_after_disco", lambda *a: 0)
    top, bottom = evaluation(1), evaluation(5)
    result = sorted(fallback([(3, top), (3, bottom)]), key=lambda x: x[0], reverse=True)
    assert result[0][1].candidate.start == bottom.candidate.start
    assert "fall_distance=15" in result[0][1].explanation
    assert result[0][0] < 4


@pytest.mark.parametrize("moves,current,context", [(1,0,"solo_6"), (4,7,"solo_6"), (4,0,"versus")])
def test_disabled_without_useful_future(monkeypatch, moves, current, context):
    monkeypatch.setattr(ms, "_best_next_blue_cells_after_disco", lambda *a: 0)
    items = [(3, evaluation(1)), (3, evaluation(5))]
    assert fallback(items, moves, current, context) == items


def test_blue_pickup_or_setup_keeps_order(monkeypatch):
    items = [(3, replace(evaluation(1), blue_cells=3)), (3, evaluation(5))]
    assert fallback(items) == items
    items = [(3, evaluation(1)), (3, evaluation(5))]
    monkeypatch.setattr(ms, "_best_next_blue_cells_after_disco", lambda *a: 3)
    assert fallback(items) == items


def test_strong_move_cannot_be_overtaken(monkeypatch):
    monkeypatch.setattr(ms, "_best_next_blue_cells_after_disco", lambda *a: 0)
    result = fallback([(5, evaluation(1)), (3, evaluation(6))])
    assert result[0][0] > result[1][0]


def test_special_effect_geometry_is_not_guessed():
    item = evaluation(5)
    item.intent_events.append(dict(type="special_activation"))
    assert ms._plain_match_fall_distance(item) == 0
