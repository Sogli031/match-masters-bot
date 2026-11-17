"""Merge Two (game 5.900): a same-colour pair merges and returns the move."""
from types import SimpleNamespace

import move_strategy as ms
from runtime import MERGE_TWO_RESERVE_SECONDS_PER_MOVE, merge_two_enabled_for_turn


def _board_with_one_pair():
    colors = list(range(ms.BLUE, ms.WHITE + 1))[:6]
    # Neighbours differ by 2 across and 1 down: no match, no pair.
    board = [[colors[(row + 2 * col) % 6] for col in range(8)] for row in range(8)]
    board[0][1] = board[0][0]
    assert not ms.find_matches(board)
    return board, [[ms.EMPTY] * 8 for _ in range(8)]


def _merges(results):
    return [
        (evaluation, result)
        for evaluation, result in results
        if any(match.kind == ms.MERGE_TWO_KIND for match in result.matches)
    ]


def _rank(board, special_board):
    return ms._rank_candidate_results(board, special_board, "None", False, None, False, {})


def test_pair_is_a_move_only_in_merge_two():
    board, special_board = _board_with_one_pair()
    assert not _merges(_rank(board, special_board))
    with ms.merge_two_active(True):
        merges = _merges(_rank(board, special_board))
    assert len(merges) == 1
    evaluation, result = merges[0]
    assert {evaluation.candidate.start, evaluation.candidate.target} == {(0, 0), (0, 1)}
    assert evaluation.direct_extra_moves == 1
    assert result.cleared_cells >= 2


def test_two_classic_specials_are_not_a_merge_two_pair():
    board, special_board = _board_with_one_pair()
    special_board[0][0] = ms.SPECIAL_BOMB
    special_board[0][1] = ms.SPECIAL_HORIZONTAL
    with ms.merge_two_active(True):
        assert ms._merge_two_pair_color(board, special_board, (0, 0), (0, 1)) is None
        special_board[0][1] = ms.EMPTY
        assert ms._merge_two_pair_color(board, special_board, (0, 0), (0, 1)) == board[0][0]


def test_merges_stop_when_the_clock_must_cover_the_real_moves():
    reserve = MERGE_TWO_RESERVE_SECONDS_PER_MOVE
    plenty = SimpleNamespace(time_left_seconds=reserve * 2 + 1, remaining_moves=2)
    short = SimpleNamespace(time_left_seconds=reserve * 2 - 0.5, remaining_moves=2)
    assert merge_two_enabled_for_turn(True, plenty)
    assert not merge_two_enabled_for_turn(True, short)
    assert not merge_two_enabled_for_turn(False, plenty)
    assert merge_two_enabled_for_turn(True, SimpleNamespace(time_left_seconds=None, remaining_moves=2))
