"""Free swaps still reward match-4 with clock time."""
import move_strategy as ms


def board():
    result = [[((c + 2 * r) % 6) + 1 for c in range(7)] for r in range(7)]
    for r, c in ((5, 1), (5, 2), (5, 4), (4, 3)):
        result[r][c] = ms.RED
    for r, c in ((0, 6), (1, 6), (3, 6)):
        result[r][c] = ms.BLUE
    return result


def test_disabled_extra_moves_still_prioritize_five_second_match_four():
    specials = [[0] * 7 for _ in range(7)]
    turn = ms.TurnState(remaining_moves=99, time_left_seconds=7, seconds_per_move=6.5)
    with ms.extra_moves_enabled_active(False, bonus_time=5):
        moves = ms.rank_moves(board(), specials, mode=ms.INFINITE_MOVES_MODE)
        extra = next(m for m in moves if m.direct_extra_moves == 1)
        assert extra.direct_extra_moves == 1
        ranked = ms.prioritize_ranked_moves(
            moves, mode=ms.INFINITE_MOVES_MODE, turn_state=turn, strategy_context="solo_6")
        assert ranked
        assert all(ms.has_guaranteed_true_extra(m) for m in ranked)
    with ms.extra_moves_enabled_active(False):
        moves = ms.rank_moves(board(), specials, mode=ms.INFINITE_MOVES_MODE)
        assert all(m.extra_moves == 0 for m in moves)
    assert ms._EXTRA_MOVE_BONUS_TIME == 0
