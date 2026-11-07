"""Solo Challenge: the lotus takes blue when the meter has room.

Two recorded boards where the bot fired the lotus on yellow instead (2026-11-06/07):
* the last move: blue-first switched off in the final phase, although the lotus
  keeps the turn and the meter it fills can still be spent;
* Lightning Strike: a yellow collect whose created Lightning was *expected* to
  hit 7.4 blue tied the blue collect that gathers 8 for certain.
"""
import move_strategy as ms

SOLO = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)


def _specials(cells):
    grid = [[0] * 7 for _ in range(7)]
    for row, col, value in cells:
        grid[row][col] = value
    return grid


def _top_lotus(board, specials, mode, rally, remaining, lightning=False, current=0):
    booster = ms.BoosterState(current=current, maximum=7)
    turn = ms.TurnState(remaining_moves=remaining)
    with ms.froggy_gather_region_active(7, True), ms.all_specials_lightning_active(lightning):
        ranked = ms.rank_moves(board, specials, mode=mode, score_rally_values=rally,
                               strategy_context=SOLO)
        lotus = ms.rank_froggy_lotus_moves(ranked, board, specials, mode=mode,
                                           score_rally_values=rally, booster_state=booster,
                                           turn_state=turn, strategy_context=SOLO)
    return lotus[0]


# 2026-11-06 15:07:46, Arcade Man Mode, meter 0/7, one move left.
LAST_MOVE_BOARD = [
    [2, 1, 4, 3, 5, 6, 6],
    [3, 5, 1, 1, 5, 5, 4],
    [5, 3, -1, 4, 3, 5, 2],
    [1, 6, 3, 6, 3, 1, 2],
    [2, 6, 1, 3, 5, 4, 6],
    [2, 4, 2, 6, 2, 4, 3],
    [3, 1, 5, 1, 1, 6, 4],
]
LAST_MOVE_SPECIALS = _specials([(2, 1, 19), (2, 2, ms.SPECIAL_FROGGY_LOTUS), (6, 2, 1)])
LAST_MOVE_RALLY = {2: 2.0, 4: 4.0, 3: 5.0, 6: 3.0}


def test_last_move_lotus_still_fills_the_meter_on_blue():
    top = _top_lotus(LAST_MOVE_BOARD, LAST_MOVE_SPECIALS, "Arcade Man Mode",
                     LAST_MOVE_RALLY, remaining=1)
    assert top.froggy_lotus_color == ms.BLUE


def test_full_meter_on_the_last_move_goes_back_to_points():
    top = _top_lotus(LAST_MOVE_BOARD, LAST_MOVE_SPECIALS, "Arcade Man Mode",
                     LAST_MOVE_RALLY, remaining=1, current=7)
    assert top.froggy_lotus_color != ms.BLUE


# 2026-11-07 02:18:26, Lightning Strike, meter 0/7, six moves left.
LIGHTNING_BOARD = [
    [5, 5, 2, 1, 6, 5, 4],
    [3, 3, 4, 3, 4, 2, 4],
    [1, 2, 1, 1, 2, 1, 6],
    [5, 6, -1, 5, 6, 4, 1],
    [3, 1, 3, 6, 2, 6, 5],
    [1, 3, 6, 4, 5, 4, 4],
    [6, 2, 3, 4, 6, 5, 3],
]
LIGHTNING_SPECIALS = _specials([
    (3, 2, ms.SPECIAL_FROGGY_LOTUS),
    (4, 1, ms.SPECIAL_LIGHTNING), (5, 1, ms.SPECIAL_LIGHTNING),
    (6, 4, ms.SPECIAL_LIGHTNING), (6, 6, ms.SPECIAL_LIGHTNING),
])
LIGHTNING_RALLY = {2: 5.0, 6: 1.0, 4: 1.0, 3: 1.0}


def test_certain_blue_collect_beats_blue_a_lightning_might_hit():
    top = _top_lotus(LIGHTNING_BOARD, LIGHTNING_SPECIALS, "Lightning Strike",
                     LIGHTNING_RALLY, remaining=6, lightning=True)
    assert top.froggy_lotus_color == ms.BLUE

