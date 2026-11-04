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


def test_match_the_pull_forms_goes_with_the_cluster():
    # Recorded 20261104_052333, transition 017, after the swipe: the pull shifts
    # bottom-row pieces into a three of 2s. ComputeBlobSpecials puts it in
    # otherCombos, so it does not wait for the refill.
    board = [
        [3, 1, 2, 1, 4, 5, 2],
        [4, 5, -1, 6, 5, 3, 1],
        [3, 4, 4, 4, 3, 3, 1],
        [1, 6, 4, 6, 2, 1, 2],
        [2, 1, 3, 3, 2, -1, 6],
        [3, 5, 6, 2, 6, 5, 5],
        [4, 2, 1, 2, 4, 1, 6],
    ]
    specials = [[0] * 7 for _ in range(7)]
    specials[1][2] = specials[4][5] = ms.SPECIAL_FROGGY_LOTUS
    swipe = ms.MatchGroup(frozenset({(2, 1), (2, 2), (2, 3)}), 4, "three")
    with ms.froggy_gather_region_active(7, True):
        gathered = ms.froggy_lotus_gather(board, specials, [swipe])
    cluster, *others = gathered.matches
    assert cluster.color == 4 and len(cluster.cells) == 9
    assert [(m.color, set(m.cells)) for m in others] == [(2, {(6, 2), (6, 3), (6, 4)})]


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
