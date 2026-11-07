import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import move_strategy as ms


def evaluation(start=(1, 1), target=(1, 2), special=ms.EMPTY):
    board = [[2] * 4 for _ in range(4)]
    specials = [[ms.EMPTY] * 4 for _ in range(4)]
    # Post-swap: blue has landed at start, green at target.
    board[start[0]][start[1]] = ms.BLUE
    board[target[0]][target[1]] = 3
    specials[start[0]][start[1]] = special
    candidate = ms.MoveCandidate(start, target, ms._direction_between(start, target), board, specials)
    match = ms.MatchGroup(frozenset({start, (0, 0), (0, 1)}), ms.BLUE, 'three')
    return ms.MoveEvaluation(
        candidate, score=3, instant_score=3, special_bonus=0, blue_bonus=3,
        mode_bonus=0, extra_move_bonus=0, disco_move_bonus=0, extra_moves=0,
        disco_moves=0, cascade_count=1, board_potential=0, lookahead_bonus=0,
        explanation='', cascade_matches=[[match]],
    )


@pytest.mark.parametrize('target', [(1, 2), (1, 0), (0, 1), (2, 1)])
@pytest.mark.parametrize('special', [ms.EMPTY, ms.SPECIAL_BOMB, ms.SPECIAL_HORIZONTAL,
                                    ms.SPECIAL_LIGHTNING, ms.SPECIAL_MUSHROOM,
                                    ms.SPECIAL_XTRA_MOVE_TILE])
def test_drag_matching_tile_toward_match_in_every_direction(target, special):
    e = evaluation(target=target, special=special)
    actual = ms.oriented_swap_candidate(e)
    assert actual.start == target
    assert actual.target == e.candidate.start
    assert ms.oriented_swipe(e) == (target, ms._direction_between(target, (1, 1)).value)
    assert actual.board is e.candidate.board
    assert actual.special_board is e.candidate.special_board
    # Calling the rule again must not reverse a correctly oriented move.
    assert ms.oriented_swap_candidate(replace(e, candidate=actual)) == actual


@pytest.mark.parametrize('special', [ms.SPECIAL_DISCO_BALL, ms.SPECIAL_CLEO_BUG,
                                    ms.SPECIAL_SPRAY_SE, ms.SPECIAL_SWEEP_SE_BROOM])
def test_directional_activations_keep_evaluated_direction(special):
    e = evaluation(special=special)
    assert ms.oriented_swap_candidate(e) is e.candidate


def test_two_special_combo_keeps_evaluated_direction():
    e = evaluation(special=ms.SPECIAL_BOMB)
    e.candidate.special_board[1][2] = ms.SPECIAL_LIGHTNING
    assert ms.oriented_swap_candidate(e) is e.candidate


def test_remote_match_and_later_cascade_do_not_override_landing_match():
    e = evaluation()
    remote = ms.MatchGroup(frozenset({(3, 0), (3, 1), (3, 2)}), 3, 'three')
    e = replace(e, cascade_matches=[e.cascade_matches[0] + [remote], [remote]],
                froggy_lotus_color=3)
    assert ms.oriented_swap_candidate(e).target == (1, 1)


@pytest.mark.parametrize('field', ['froggy_lotus_color', 'mixy_code_color'])
def test_two_matches_respect_explicit_color_intent(field):
    e = evaluation()
    other = ms.MatchGroup(frozenset({(1, 2), (2, 2), (3, 2)}), 3, 'three')
    e = replace(e, cascade_matches=[e.cascade_matches[0] + [other]], **{field: 3})
    assert ms.oriented_swap_candidate(e) is e.candidate


def test_two_matches_without_explicit_intent_keep_simulated_direction():
    e = evaluation()
    other = ms.MatchGroup(frozenset({(1, 2), (2, 2), (3, 2)}), 3, 'three')
    e = replace(e, cascade_matches=[e.cascade_matches[0] + [other]])
    assert ms.oriented_swap_candidate(e) is e.candidate
    other = replace(other, cells=other.cells | {(0, 2)}, kind='four')
    e = replace(e, cascade_matches=[e.cascade_matches[0][:1] + [other]])
    assert ms.oriented_swap_candidate(e) is e.candidate


def test_spray_same_cell_and_no_matches_are_unchanged():
    e = evaluation()
    assert ms.oriented_swap_candidate(replace(e, cascade_matches=[])) is e.candidate
    candidate = replace(e.candidate, target=e.candidate.start)
    assert ms.oriented_swap_candidate(replace(e, candidate=candidate)) is candidate


def test_recorded_purple_four_bomb_mushroom_swipe_goes_up():
    # Debug 2026-09-07_02-12-06_018: bot swiped (5,2)->(6,2),
    # although purple bomb at (6,2) completes the four at (5,2).
    board = [[2] * 7 for _ in range(7)]
    specials = [[ms.EMPTY] * 7 for _ in range(7)]
    for col in (1, 2, 3, 4):
        board[5][col] = 4
    board[6][2] = 1
    specials[5][2] = ms.SPECIAL_BOMB
    specials[6][2] = ms.SPECIAL_MUSHROOM
    candidate = ms.MoveCandidate((5, 2), (6, 2), ms.Direction.DOWN, board, specials)
    match = ms.MatchGroup(frozenset((5, col) for col in (1, 2, 3, 4)), 4, 'four')
    e = replace(evaluation(), candidate=candidate, cascade_matches=[[match]])
    assert ms.oriented_swipe(e) == ((6, 2), 'up')


# --- 2026-09-19: lotus moves were the counter swipes -------------------------
# A simulated gather replaces the trigger match with the blob around the lotus,
# so the swapped cell was no longer "in a match" and the swipe kept the
# generator's left/upper end: 22 of 131 recorded lotus moves dragged the tile
# that did NOT make the match.

# (e.g. 22:38:49: red dragged from (5,4) down onto the blue that made it).
#
# 01:43:21, Multiplier Madness: orange (5,3) over purple (6,3), both matches
# touching the lotus at (5,4) -- the dragged tile decides which colour fires.
LOTUS_BOARD = [
    [5, 4, 2, 3, 1, 3, 4],
    [2, 2, 1, 1, 3, 1, 2],
    [1, -1, 3, 2, 5, 3, 3],
    [1, 1, 6, 4, 3, 2, 4],
    [3, 5, 6, 4, 2, 6, 5],
    [5, 6, 5, 6, -1, 4, 6],
    [2, 3, 4, 4, 6, 6, 4],
]


def _lotus_moves():
    specials = [[ms.EMPTY] * 7 for _ in range(7)]
    specials[2][1] = specials[5][4] = ms.SPECIAL_FROGGY_LOTUS
    with ms.froggy_gather_region_active(7, True):
        ranked = ms.rank_moves(LOTUS_BOARD, specials, mode='Multiplier Madness')
        return ms.rank_froggy_lotus_moves(ranked, LOTUS_BOARD, specials, mode='Multiplier Madness')


def test_every_lotus_move_drags_the_tile_of_the_colour_it_collects():
    moves = _lotus_moves()
    assert moves
    for move in moves:
        start, _direction = ms.oriented_swipe(move)
        assert LOTUS_BOARD[start[0]][start[1]] == move.froggy_lotus_color, move.candidate


def test_a_swap_matching_at_both_ends_offers_both_collects():
    by_swipe = {ms.oriented_swipe(move): move for move in _lotus_moves()}
    orange = by_swipe[((5, 3), 'down')]
    purple = by_swipe[((6, 3), 'up')]
    assert orange.froggy_lotus_color == ms.ORANGE
    assert purple.froggy_lotus_color == ms.PURPLE
    assert purple.froggy_lotus_collected == 9
