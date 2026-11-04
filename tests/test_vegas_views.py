import board_source
import move_strategy as ms

VEGAS = ms.GameMode.VEGAS_VIEWS


def plain_three():
    """A red three on row 3, columns 0..2, made by dropping (2,2) into (3,2)."""
    board = [[(ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE)[(r + c) % 4]
              for c in range(7)] for r in range(7)]
    board[3][0] = board[3][1] = ms.RED
    board[2][2] = ms.RED
    specials = [[0] * 7 for _ in range(7)]
    after, after_special = ms.swap_cells(board, specials, (2, 2), (3, 2))
    candidate = ms.MoveCandidate((2, 2), (3, 2), ms.Direction.DOWN, after, after_special)
    return ms.simulate_candidate(candidate)


def evaluate(result, mode=VEGAS):
    return ms.evaluate_simulation(result, mode, include_future_value=False)


def test_snapshot_reads_vegas_cell_and_defaults_to_triple():
    grid = [[0] * 7 for _ in range(7)]
    grid[4][2] = board_source.CELL_TYPE_VEGAS
    state = board_source.vegas_views_state({"cell_types": grid})
    assert state == {"cells": ((4, 2),), "multiplier": 3, "multiplier_source": "default"}
    assert board_source.vegas_views_state({}) is None


def test_snapshot_takes_the_extra_data_override():
    grid = [[0] * 7 for _ in range(7)]
    state = board_source.vegas_views_state(
        {"cell_types": grid, "board_extra_data": {"SCORE_MULTIPLIER": "2"}}
    )
    assert state["cells"] == ()
    assert (state["multiplier"], state["multiplier_source"]) == (2, "extraData")


def test_combo_through_the_tile_pays_the_whole_combo_times_multiplier():
    result = plain_three()
    plain = evaluate(result)
    with ms.vegas_views_cells([(3, 0)], 3):
        vegas = evaluate(result)
    # Three tiles x (3 - 1) extra, on top of the plain three.
    assert vegas.vegas_bonus == 6.0
    assert vegas.instant_score == plain.instant_score + 6.0


def test_combo_off_the_tile_and_other_modes_get_nothing():
    result = plain_three()
    with ms.vegas_views_cells([(5, 5)], 3):
        assert evaluate(result).vegas_bonus == 0.0
    with ms.vegas_views_cells([(3, 0)], 3):
        assert evaluate(result, ms.GameMode.NONE).vegas_bonus == 0.0


def test_ability_move_does_not_fire_the_tile(monkeypatch):
    monkeypatch.setattr(ms, "_ABILITY_USED_THIS_MOVE", True)
    with ms.vegas_views_cells([(3, 0)], 3):
        assert evaluate(plain_three()).vegas_bonus == 0.0


def test_context_restores_previous_state():
    with ms.vegas_views_cells([(1, 1)], 3):
        pass
    assert ms._VEGAS_CELLS == frozenset()
    assert ms._VEGAS_MULTIPLIER == 1.0
