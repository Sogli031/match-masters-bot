"""Purple Gem: a collected gem respawns one higher, so collecting early pays twice."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402


def gem_board(*values):
    board = [[0] * ms.BOARD_SIZE for _ in range(ms.BOARD_SIZE)]
    for col, value in enumerate(values):
        board[0][col] = ms.make_purple_gem_special(value, exact=True)
    return board


def blank_result(**kwargs):
    return ms.SimulationResult(candidate=None, board=[], special_board=[], **kwargs)


def bonus(mode_targets):
    return ms._mode_target_bonus_value(
        blank_result(mode_targets=mode_targets),
        ms.GameMode.PURPLE_GEM,
        ms.MODE_WEIGHTS[ms.GameMode.PURPLE_GEM],
    )


def test_growth_scales_with_moves_left():
    with ms.purple_gem_state(gem_board(10, 10), remaining_moves=10):
        early = bonus(10)
    with ms.purple_gem_state(gem_board(10, 10), remaining_moves=2):
        late = bonus(10)
    assert early == 10 + 9 * ms.PURPLE_GEM_FUTURE_COLLECTS_PER_MOVE
    assert 10 < late < early


def test_both_gems_count_twice():
    with ms.purple_gem_state(gem_board(10, 10), remaining_moves=6):
        one = bonus(10) - 10
        both = bonus(20) - 20
    assert both == 2 * one


def test_no_growth_on_last_move_or_without_state():
    with ms.purple_gem_state(gem_board(10, 10), remaining_moves=1):
        assert bonus(10) == 10
    assert bonus(10) == 10
    with ms.purple_gem_state(None, remaining_moves=8):
        assert bonus(10) == 10


def test_other_modes_untouched():
    with ms.purple_gem_state(gem_board(10, 10), remaining_moves=10):
        value = ms._mode_target_bonus_value(
            blank_result(mode_targets=2),
            ms.GameMode.GREEN_LEAF,
            ms.MODE_WEIGHTS[ms.GameMode.GREEN_LEAF],
        )
    assert value == 2 * ms.MODE_WEIGHTS[ms.GameMode.GREEN_LEAF]["mode_target"]


def test_energy_colours_pay_nothing_when_the_override_has_a_zero():
    values = ms.effective_score_rally_values_for_mode(
        ms.GameMode.PURPLE_GEM,
        {ms.GREEN: 0.0, ms.YELLOW: 5.0, ms.PURPLE: 0.0, ms.ORANGE: 0.0},
    )
    assert values[ms.BLUE] == 0.0 and values[ms.RED] == 0.0
    assert values[ms.YELLOW] == 5.0


def test_energy_colours_keep_the_default_on_a_fully_paid_override():
    rally = {ms.GREEN: 2.0, ms.YELLOW: 5.0, ms.PURPLE: 4.0, ms.ORANGE: 3.0}
    values = ms.effective_score_rally_values_for_mode(ms.GameMode.NONE, rally)
    assert values == rally


def test_zero_point_board_still_returns_a_legal_move():
    # 2026-10-31 12:41:01, last move of a Purple Gem game: every legal swap
    # matched only colours paid 0, the ranking came back empty and the game
    # spent the move by itself.
    board = [
        [3, 2, 6, 1, 5, 5, 3],
        [5, 4, 1, 4, 3, 5, 2],
        [5, 4, 6, 5, 5, 4, 1],
        [2, 6, 6, 5, 3, 2, 5],
        [6, 1, 4, 4, 1, 6, 1],
        [2, 3, 1, 6, 3, 3, 6],
        [2, 2, 3, 6, 4, 1, 1],
    ]
    special = [[0] * 7 for _ in range(7)]
    special[1][3] = ms.make_purple_gem_special(30, exact=True)
    special[6][4] = ms.make_purple_gem_special(27, exact=True)
    rally = ms.effective_score_rally_values_for_mode(
        ms.GameMode.PURPLE_GEM,
        {ms.GREEN: 0.0, ms.YELLOW: 5.0, ms.PURPLE: 0.0, ms.ORANGE: 0.0},
    )
    ranked = ms.rank_moves(board, special, mode=ms.GameMode.PURPLE_GEM, score_rally_values=rally)
    assert ranked
