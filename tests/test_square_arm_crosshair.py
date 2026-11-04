"""A 2x2 block plus an arm (square-match mode) leaves a Crosshair, not a Bomb.

Debug/runs 2026-10-31_11-44-20_880 (Multiplier Mushrooms, versus): the swipe
(4,4)->(4,3) matched (3,2),(3,3),(4,1),(4,2),(4,3) in colour 3 -- a square with
one extra tile. The simulator left a Bomb (3) at (4,3); the next board read from
memory had a Crosshair (46) there. Over 2026-10-01..31 the same shape left a
Crosshair 76 times and a Bomb twice, while a real L/T (row of three and column
of three through one cell) that contains a square left a Bomb 5/5.
"""

import move_strategy as ms

BOARD = [
    [4, 3, 6, 1, 5, 4, 4],
    [5, 2, 1, 6, 6, 1, 4],
    [3, 2, 1, 5, 6, 3, 3],
    [5, 4, 3, 3, 5, 4, 4],
    [2, 3, 3, 6, 3, 3, 2],
    [1, 5, 2, 4, 6, 2, 2],
    [1, 2, 5, 4, 2, 4, 5],
]
SPECIALS = [
    [0, 0, 0, 0, 0, 0, 0],
    [0, 17, 0, 0, 0, 0, 0],
    [0, 17, 0, 0, 0, 0, 0],
    [0, 17, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
]


def test_recorded_square_with_arm_creates_crosshair():
    candidate = next(
        c for c in ms.generate_candidates(BOARD, SPECIALS)
        if {c.start, c.target} == {(4, 3), (4, 4)}
    )
    for oriented in (candidate, ms.flip_swap_candidate(candidate)):
        if oriented.target != (4, 3):
            continue
        with ms.mushroom_multipliers_active(True):
            result = ms._simulate_created_candidate(
                BOARD, oriented, allow_square_matches=True,
                mode="Multiplier Mushrooms Studio", include_future_value=False,
            )
        assert result.special_board[4][3] == ms.SPECIAL_CROSSHAIR
        break
    else:  # pragma: no cover
        raise AssertionError("no orientation lands on (4,3)")


def test_shape_rule():
    square_arm = ms.MatchGroup(frozenset({(3, 2), (3, 3), (4, 1), (4, 2), (4, 3)}), 3, "l")
    assert ms._created_special_type(square_arm) == ms.SPECIAL_CROSSHAIR
    # Row of three and column of three through (2,0), also containing a 2x2.
    real_l = ms.MatchGroup(frozenset({(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (1, 1)}), 3, "l")
    assert ms._created_special_type(real_l) == ms.SPECIAL_BOMB
    plain_l = ms.MatchGroup(frozenset({(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)}), 3, "l")
    assert ms._created_special_type(plain_l) == ms.SPECIAL_BOMB
