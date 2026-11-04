import move_strategy as ms

# Debug/runs/2026-09-29_19-52-19_254 (Chest Mode, solo): moves that drop chests.
BOARD = [[5, 2, 6, 4, 4, 1, 6], [3, 6, 2, 2, 1, 4, 2], [4, 1, 5, 3, 2, 5, 3], [3, 2, 3, 8, 5, 3, 6], [1, 5, 3, 1, 2, 4, 5], [1, 5, 5, 6, 8, 6, 4], [4, 4, 3, 1, 4, 6, 4]]
SPECIALS = [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], [0, 0, 35, 9, 0, 39, 0], [1, 0, 41, 0, 46, 0, 0], [0, 0, 0, 0, 9, 0, 0], [0, 0, 0, 0, 0, 34, 0]]


def test_helper_is_off_outside_solo_chest():
    assert ms._chest_blue(2) == 0.0
    with ms.chest_charge_active(3.0):
        assert ms._chest_blue(2) == 6.0
    assert ms._chest_blue(2) == 0.0


def test_chest_drop_pays_three_blue_in_solo_only():
    def chest_moves(strategy):
        ranked = ms.rank_moves(BOARD, SPECIALS, mode="Chest Mode", strategy_context=strategy)
        return {(tuple(m.candidate.start), tuple(m.candidate.target)): m
                for m in ranked if m.chest_drops > 0}

    solo = chest_moves("solo_6")
    versus = chest_moves("versus_2")
    assert solo
    for key, move in solo.items():
        assert abs((move.blue_cells - versus[key].blue_cells) - 3.0 * move.chest_drops) < 1e-6
