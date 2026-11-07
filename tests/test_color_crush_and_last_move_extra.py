from types import SimpleNamespace

import move_strategy as ms
import runtime


def _red_board():
    # Red three in column 3 (rows 3-5) plus two stray reds elsewhere.
    R, B, G, Y, P, O = ms.RED, ms.BLUE, ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE
    return [
        [B, G, R, Y, P, O, B],
        [G, Y, P, O, B, G, Y],
        [Y, P, O, B, G, Y, P],
        [P, O, B, R, Y, P, O],
        [O, B, G, R, P, O, G],
        [B, G, Y, R, O, R, Y],
        [G, Y, P, O, B, G, P],
    ]


def _red_match():
    return [ms.MatchGroup(color=ms.RED, cells=((3, 3), (4, 3), (5, 3)), kind="three")]


def test_color_crush_wipes_red_only_on_a_single_player_board():
    board = _red_board()
    with ms.color_crush_active(True, single_player=True):
        assert ms.color_crush_inert_colors() == (ms.BLUE,)
        assert ms._color_crush_cells(board, _red_match()) == {
            (0, 2), (3, 3), (4, 3), (5, 3), (5, 5)
        }
    with ms.color_crush_active(True, single_player=False):
        assert ms.color_crush_inert_colors() == (ms.BLUE, ms.RED)
        assert ms._color_crush_cells(board, _red_match()) == set()


def test_color_crush_single_player_flag_is_restored():
    with ms.color_crush_active(True, single_player=True):
        with ms.color_crush_active(True):
            assert ms.color_crush_inert_colors() == (ms.BLUE, ms.RED)
        assert ms.color_crush_inert_colors() == (ms.BLUE,)
    assert ms.color_crush_inert_colors() == (ms.BLUE, ms.RED)


def _weak_direct_extra():
    return SimpleNamespace(
        activated_specials=0,
        multiplier_mushrooms=0,
        mode_targets=0,
        instant_score=5.0,
        disco_moves=0,
        extra_moves=1,
        direct_extra_moves=1,
    )


def test_weak_extra_goes_before_immediate_booster_on_the_last_move():
    extra = _weak_direct_extra()
    last = SimpleNamespace(remaining_moves=1)
    assert runtime._is_strong_extra_before_immediate_booster(extra, ms.GameMode.COLOR_CRUSH, last)
    assert (
        runtime._valuable_extra_before_immediate_booster(
            [extra], ms.GameMode.COLOR_CRUSH, turn_state=last
        )
        is extra
    )


def test_weak_extra_still_yields_to_immediate_booster_earlier_in_the_turn():
    extra = _weak_direct_extra()
    early = SimpleNamespace(remaining_moves=3)
    assert not runtime._is_strong_extra_before_immediate_booster(
        extra, ms.GameMode.COLOR_CRUSH, early
    )
    assert not runtime._is_strong_extra_before_immediate_booster(extra, ms.GameMode.COLOR_CRUSH)


def test_multiplier_colour_extra_goes_before_immediate_booster():
    # 2026-09-18 23:50:03: a purple match-4 (4 instant points, multiplier +1)
    # was skipped for the Froggy activation in Multiplier Madness.
    extra = _weak_direct_extra()
    extra.multiplier_madness_points = 1.0
    early = SimpleNamespace(remaining_moves=6)
    assert runtime._is_strong_extra_before_immediate_booster(
        extra, ms.GameMode.MULTIPLIER_MADNESS, early
    )
    assert (
        runtime._valuable_extra_before_immediate_booster(
            [extra], ms.GameMode.MULTIPLIER_MADNESS, turn_state=early
        )
        is extra
    )


def test_mushroom_in_the_wipe_keeps_the_cascade_extra():
    # 2026-10-31 21:27:17 (solo Color Crush): (0,3) left matches orange, the
    # wipe takes the orange mushroom at (6,5) and a blue four falls in cascade
    # 2. The game kept the turn; the mushroom clears nothing to interleave.
    board = [
        [6, 6, 3, 6, 2, 3, 2],
        [3, 3, 2, 2, 3, 1, 1],
        [5, 5, 3, 6, 2, 4, 4],
        [4, 4, 5, 1, 1, 5, 5],
        [6, 6, 2, 4, 4, 5, 5],
        [5, 5, 4, 3, 3, 1, 1],
        [6, 6, 5, 1, 1, 6, 6],
    ]
    special = [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 4, 0, 17, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 17, 0],
        [0, 0, 0, 1, 1, 1, 1],
        [0, 0, 0, 0, 0, 17, 0],
    ]
    with ms.color_crush_active(True, single_player=True):
        ranked = ms.rank_extra_move_moves(
            board, special, "Color Crush Mode",
            strategy_context=ms.StrategyContext(
                mode=ms.STRATEGY_SOLO_6, solo_challenge=True
            ),
        )
    assert any(
        {tuple(e.candidate.start), tuple(e.candidate.target)} == {(0, 2), (0, 3)}
        and ms.has_reliable_same_move_extra(e)
        for e in ranked
    )


def test_horizontal_in_the_wipe_keeps_the_cascade_extra():
    # 2026-10-31 21:34:45 (solo Color Crush, last move): (4,5) right matches
    # purple down column 6 through the horizontal at (5,6); it fires the one
    # at (5,5), the purple wipe follows and a blue five falls in cascade 2.
    # The game kept the turn.
    board = [
        [5, 5, 3, 6, 3, 5, 3],
        [6, 4, 1, 2, 6, 5, 5],
        [6, 5, 4, 2, 5, 6, 6],
        [4, 6, 6, 3, 4, 1, 2],
        [4, 5, 2, 1, 6, 4, 1],
        [1, 2, 1, 2, 1, 2, 4],
        [2, 1, 4, 4, 1, 1, 4],
    ]
    special = [
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 1, 0, 0, 0],
        [0, 2, 0, 0, 0, 0, 0],
        [17, 0, 17, 0, 0, 1, 1],
        [0, 0, 0, 17, 17, 17, 0],
    ]
    with ms.color_crush_active(True, single_player=True):
        ranked = ms.rank_extra_move_moves(
            board, special, "Color Crush Mode",
            strategy_context=ms.StrategyContext(
                mode=ms.STRATEGY_SOLO_6, solo_challenge=True
            ),
        )
    assert any(
        {tuple(e.candidate.start), tuple(e.candidate.target)} == {(4, 5), (4, 6)}
        and ms.has_reliable_same_move_extra(e)
        for e in ranked
    )
