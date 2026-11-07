"""Solo Challenge: an extra that leaves blue next to the lotus goes first.

The player (2026-11-07): with a lotus on the board, a free extra elsewhere whose
settled board offers a blue trigger on the lotus is played before the lotus.
The extra keeps the turn and the lotus still fills the meter on blue next move.
Solo Challenge only ("ne u trci samo u solo").
"""
import move_strategy as ms

# 2026-11-06 13:34:22, Solo Challenge, meter 0/7, lotus at (1, 1).
BOARD = [
    [3, 6, 3, 2, 4, 1, 5],
    [2, -1, 1, 6, 3, 6, 2],
    [3, 4, 1, 4, 5, 4, 2],
    [1, 1, 2, 4, 5, 6, 4],
    [1, 3, 3, 5, 6, 5, 4],
    [5, 5, 1, 4, 4, 6, 6],
    [2, 2, 3, 99, 5, 6, 2],
]
SPECIALS = [[0] * 7 for _ in range(7)]
SPECIALS[1][1] = ms.SPECIAL_FROGGY_LOTUS
SPECIALS[4][0] = ms.SPECIAL_BOMB
SPECIALS[5][3] = ms.SPECIAL_VERTICAL
SPECIALS[6][3] = ms.SPECIAL_DISCO_BALL
RALLY = {3: 5.0, 6: 3.0, 2: 2.0, 4: 4.0}
SOLO = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)
RACE = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6)


def _pick(context, current=0):
    booster = ms.BoosterState(current=current, maximum=7)
    with ms.froggy_gather_region_active(7, True):
        ranked = ms.rank_moves(BOARD, SPECIALS, score_rally_values=RALLY,
                               strategy_context=context, include_future_value=False)
        lotus = ms.rank_froggy_lotus_moves(ranked, BOARD, SPECIALS, score_rally_values=RALLY,
                                           booster_state=booster, strategy_context=context)
        pick = ms.blue_setup_extra_before_lotus(
            ranked, lotus, SPECIALS, score_rally_values=RALLY,
            booster_state=booster, strategy_context=context)
    return lotus, pick


def test_solo_plays_the_extra_that_leaves_a_blue_lotus_collect():
    lotus, pick = _pick(SOLO)
    assert lotus and lotus[0].froggy_lotus_color == ms.BLUE
    assert pick is not None
    assert ms.has_reliable_same_move_extra(pick)
    swipes = {(item.candidate.start, item.candidate.target) for item in lotus}
    assert (pick.candidate.start, pick.candidate.target) not in swipes
    # The board the extra leaves still offers a blue collect on the lotus.
    result = ms._simulate_post_move_result(pick, "None", False, RALLY, False)
    assert ms._count_lotus_pieces(result.special_board) == 1
    with ms.froggy_gather_region_active(7, True):
        assert ms._best_blue_lotus_charge_on_board(
            result.board, result.special_board, "None", False, RALLY, False, float("inf")) > 0


def test_point_race_is_left_alone():
    _lotus, pick = _pick(RACE)
    assert pick is None


def test_full_meter_fires_the_lotus_as_before():
    _lotus, pick = _pick(SOLO, current=7)
    assert pick is None
