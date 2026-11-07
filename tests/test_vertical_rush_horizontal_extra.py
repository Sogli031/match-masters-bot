"""Vertical Rush: a horizontal extra is not played for the turn it keeps.

Player rule (2026-09-20): vertical matches are +1 on the multiplier, horizontal
ones -1, a square counts as vertical, and only the swap's own (direct) matches
count. An extra move whose own match is horizontal therefore costs a multiplier
point and is avoided -- unless it fills the booster.
"""
import move_strategy as ms

SIZE = 7
MODE = ms.GameMode.VERTICAL_RUSH
FOUR_SWAP = {(4, 3), (5, 3)}
VERTICAL_SWAPS = ({(2, 6), (3, 6)}, {(1, 6), (2, 6)})


def _board(four_color):
    """A lattice with no moves of its own, plus one horizontal four (row 5,
    columns 1-4, by dropping (4,3)) and a vertical yellow three in column 6."""
    board = [[((col + 2 * row) % 6) + 1 for col in range(SIZE)] for row in range(SIZE)]
    for row, col in ((5, 1), (5, 2), (5, 4), (4, 3)):
        board[row][col] = four_color
    for row, col in ((0, 6), (1, 6), (3, 6)):
        board[row][col] = ms.YELLOW
    return board


def _specials():
    return [[0] * SIZE for _ in range(SIZE)]


def _pair(evaluation):
    return {evaluation.candidate.start, evaluation.candidate.target}


def _prioritized(four_color, booster_state=None):
    board = _board(four_color)
    ranked = ms.rank_moves(board, _specials(), mode=MODE)
    four = [e for e in ranked if _pair(e) == FOUR_SWAP]
    assert four and four[0].direct_extra_moves >= 1
    return ms.prioritize_ranked_moves(ranked, mode=MODE, booster_state=booster_state)


def test_square_counts_as_vertical():
    square = ms.MatchGroup(
        cells=frozenset({(1, 1), (1, 2), (2, 1), (2, 2)}), color=ms.RED, kind="square"
    )
    four = ms.MatchGroup(
        cells=frozenset({(5, 1), (5, 2), (5, 3), (5, 4)}), color=ms.RED, kind="four"
    )
    assert ms._match_orientation_counts(square) == (0, 1)
    assert ms._match_orientation_counts(four) == (1, 0)
    weights = ms.MODE_WEIGHTS[MODE]
    assert ms._match_group_mode_bonus([square], weights) == weights["vertical_match"]


def test_horizontal_extra_is_not_played_for_the_turn():
    prioritized = _prioritized(ms.ORANGE)
    assert _pair(prioritized[0]) in VERTICAL_SWAPS
    four = next(e for e in prioritized if _pair(e) == FOUR_SWAP)
    # Still in the pool as a plain horizontal match, behind the moves that
    # keep the multiplier, with the rejection on record.
    assert four.extra_moves == 0 and four.direct_extra_moves == 0
    assert four.extra_move_bonus == 0
    assert ms._is_multiplier_losing_extra(four)
    assert not ms.has_reliable_same_move_extra(four)


def test_horizontal_extra_that_fills_the_booster_is_played():
    booster = ms.BoosterState(current=3, maximum=7, source="memory")
    prioritized = _prioritized(ms.BLUE, booster)
    assert _pair(prioritized[0]) == FOUR_SWAP
    assert prioritized[0].direct_extra_moves >= 1
    assert not ms._is_multiplier_losing_extra(prioritized[0])


def test_cascade_orientation_does_not_count():
    # Direct layer vertical, a horizontal four only in a later cascade: +1, and
    # the extra is kept.
    vertical = ms.MatchGroup(
        cells=frozenset({(0, 6), (1, 6), (2, 6)}), color=ms.YELLOW, kind="three"
    )
    four = ms.MatchGroup(
        cells=frozenset({(5, 1), (5, 2), (5, 3), (5, 4)}), color=ms.RED, kind="four"
    )
    ranked = ms.rank_moves(_board(ms.ORANGE), _specials(), mode=MODE)
    template = next(e for e in ranked if _pair(e) in VERTICAL_SWAPS)
    evaluation = ms.replace(
        template, cascade_matches=[[vertical], [four]], extra_moves=1.0
    )
    assert not ms._loses_directional_multiplier(evaluation, MODE)
    kept = ms._without_multiplier_losing_extras([evaluation], MODE)
    assert kept[0].extra_moves == 1.0


def test_other_modes_are_untouched():
    ranked = ms.rank_moves(_board(ms.ORANGE), _specials())
    assert ms._without_multiplier_losing_extras(ranked, ms.GameMode.NONE) is ranked
    best = ms.prioritize_ranked_moves(ranked)[0]
    assert _pair(best) == FOUR_SWAP and best.direct_extra_moves >= 1


def test_extra_move_button_prefers_an_extra_that_keeps_the_multiplier():
    board = _board(ms.ORANGE)
    # A second, vertical four in column 0: (3,1) slides left between the greens.
    for row, col in ((1, 0), (2, 0), (4, 0), (3, 1)):
        board[row][col] = ms.GREEN
    ranked = ms.rank_extra_move_moves(board, _specials(), mode=MODE)
    assert ranked
    assert not ms._loses_directional_multiplier(ranked[0], MODE)
    assert any(ms._loses_directional_multiplier(e, MODE) for e in ranked)
