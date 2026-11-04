"""A Froggy lotus fires only on the performed swap's own match.

Recorded 2026-09-20 19:23:00 (Solo Challenge, Froggy Fu): the bot played a
Bomb+Bomb for a "lotus collect" off the blue three that the explosion dropped in
beside the lotus. The three happened, the lotus stayed put and the move was
spent. A special+special swap has no direct match, so `cascade_matches[0]` was
already a drop cascade there.
"""
import move_strategy as ms

BOARD = [
    [2, 1, 6, 3, 4, 5, 6],
    [1, 4, 1, 6, 3, 2, 1],
    [1, -1, 5, 4, 3, 3, 4],
    [5, 3, 1, 5, 4, 1, 2],
    [1, 3, 1, 4, 3, 2, 5],
    [5, 4, 2, 4, 5, 6, 5],
    [3, 3, 5, 5, 6, 4, 6],
]
SPECIALS = [
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 20, 0, 0, 3, 0, 3],
    [0, 0, 0, 0, 0, 0, 3],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 46, 0],
    [0, 0, 0, 0, 0, 0, 0],
]
RALLY = {6: 3.0, 4: 4.0, 3: 5.0, 2: 2.0}
BOMB_PAIR = {(2, 6), (3, 6)}


def _ranked():
    ranked = ms.rank_moves(
        BOARD, SPECIALS, allow_square_matches=True, score_rally_values=RALLY
    )
    lotus = ms.rank_froggy_lotus_moves(ranked, BOARD, SPECIALS, score_rally_values=RALLY)
    return ranked, lotus


def test_bomb_combo_has_no_direct_match_layer():
    ranked, _lotus = _ranked()
    combos = [e for e in ranked if {e.candidate.start, e.candidate.target} == BOMB_PAIR]
    assert combos
    assert all(not e.has_direct_match_layer for e in combos)


def test_cascade_three_beside_the_lotus_is_not_a_trigger():
    _ranked_moves, lotus = _ranked()
    assert lotus
    assert all({e.candidate.start, e.candidate.target} != BOMB_PAIR for e in lotus)
    # The direct blue triggers of that board are still there.
    pairs = [{e.candidate.start, e.candidate.target} for e in lotus]
    assert {(3, 0), (4, 0)} in pairs
    assert {(1, 2), (2, 2)} in pairs
