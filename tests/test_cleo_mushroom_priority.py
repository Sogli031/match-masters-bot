import pytest

import move_strategy as ms
import runtime


# Player, 2026-09-26: in Mighty Mushrooms (memory reader: Multiplier Mushrooms)
# a Cleo swap with a mushroom -- either direction -- is played whenever there
# is one, ahead of a sure extra and a ready booster.
def _board():
    board = [[(row + 2 * col) % 6 + 1 for col in range(7)] for row in range(7)]
    color = board[6][0]
    # (5,2)->(6,2) completes a bottom-row four: a sure direct extra.
    board[6][1] = color
    board[6][3] = color
    board[5][2] = color
    specials = [[0] * 7 for _ in range(7)]
    specials[2][3] = ms.SPECIAL_CLEO_BUG
    specials[2][4] = ms.SPECIAL_MUSHROOM
    return board, specials


def _prioritized(mode):
    board, specials = _board()
    ranked = ms.rank_moves(
        board, specials, mode=mode, include_future_value=True, strategy_context="versus_2"
    )
    return ms.prioritize_ranked_moves(ranked, mode=mode, strategy_context="versus_2")


def _pair(item):
    return {tuple(item.candidate.start), tuple(item.candidate.target)}


def test_cleo_mushroom_swap_goes_first_in_mushrooms_mode():
    moves = _prioritized("Multiplier Mushrooms Studio")
    assert _pair(moves[0]) == {(2, 3), (2, 4)}
    assert moves[0].decision_gate == ms.CLEO_MUSHROOM_DECISION_GATE
    assert moves[0].cleo_before_booster
    # Both directions are offered, best chance then points first.
    assert all(_pair(item) == {(2, 3), (2, 4)} for item in moves)

    action, chosen, gate = runtime.select_booster_action_with_gate(moves, True, True)
    assert action == "move" and chosen is moves[0]


def test_sure_extra_that_keeps_the_pair_goes_first():
    # Debug/runs/2026-09-26_21-00-59_549: a 40% Cleo+mushroom (5,1)/(6,1) was
    # played over the sure extra (1,5)->(2,5), which leaves the pair standing.
    board = [[5, 2, 4, 99, 3, 6, 4], [6, 3, 1, 2, 2, 4, 2], [3, 4, 1, 6, 1, 2, 1],
             [6, 3, 6, 1, 2, 3, 6], [5, 5, 4, 2, 5, 5, 3], [4, 2, 1, 6, 1, 6, 4],
             [1, 99, 1, 5, 1, 3, 1]]
    specials = [[0, 0, 0, 13, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], [0, 15, 0, 17, 0, 0, 0],
                [0, 15, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], [0, 17, 0, 17, 3, 15, 0],
                [0, 13, 0, 0, 0, 0, 0]]
    mode = "Multiplier Mushrooms Studio"
    ranked = ms.rank_moves(board, specials, mode=mode, include_future_value=True, strategy_context="solo_6")
    moves = ms.prioritize_ranked_moves(ranked, mode=mode, strategy_context="solo_6")
    assert _pair(moves[0]) == {(1, 5), (2, 5)}
    assert ms.has_guaranteed_true_extra(moves[0])


def test_other_modes_keep_the_sure_extra_first():
    moves = _prioritized("None")
    assert _pair(moves[0]) == {(5, 2), (6, 2)}


def _weak_cleo_case(mode):
    # Debug/runs/2026-10-08_11-37-21_678: the bot played a 10-point move (30
    # points) next to a 44-point Cleo swap. Native prevent chance on the first
    # use is 16%, so this board is only weak (below CLEO_PLAY_MIN_CHANCE) from
    # the third figure of a turn on.
    board = [[3, 3, 6, 5, 1, 2, 6], [6, 2, 4, 2, 3, 1, 2], [5, 5, 3, 4, 5, 4, 6],
             [2, 4, 6, 6, 3, 5, 4], [3, 1, 1, 4, 2, 99, 3], [4, 2, 3, 1, 6, 6, 1],
             [1, 5, 2, 1, 4, 3, 5]]
    specials = [[0, 0, 0, 0, 0, 17, 0], [0] * 7, [0] * 7, [0] * 7,
                [3, 0, 0, 0, 0, 13, 0], [0] * 7, [0, 0, 0, 0, 0, 2, 0]]
    kw = dict(mode=mode, score_rally_values={3: 5.0, 6: 3.0, 2: 2.0, 4: 4.0})
    with ms.cleo_odds_active({"uses": 3}):
        ranked = ms.rank_moves(board, specials, include_future_value=True, strategy_context="solo_6", **kw)
    return ms.prioritize_ranked_moves(
        ranked,
        booster_state=ms.BoosterState(current=3, maximum=7, source="memory"),
        turn_state=ms.TurnState(remaining_moves=4, source="memory"),
        strategy_context="solo_6",
        **kw,
    )


def test_weak_cleo_competes_on_points_in_mushrooms_mode():
    # Player, 2026-10-08: Cleo is the strongest piece in Mushrooms. It keeps its
    # place in the pool without the Cleo tier; here 36 points lose to 39.
    best = _weak_cleo_case("Multiplier Mushrooms Studio")[0]
    assert best.decision_gate != ms.CLEO_DECISION_GATE
    board = [[3, 3, 6, 5, 1, 2, 6], [6, 2, 4, 2, 3, 1, 2], [5, 5, 3, 4, 5, 4, 6],
             [2, 4, 6, 6, 3, 5, 4], [3, 1, 1, 4, 2, 99, 3], [4, 2, 3, 1, 6, 6, 1],
             [1, 5, 2, 1, 4, 3, 5]]
    specials = [[0, 0, 0, 0, 0, 17, 0], [0] * 7, [0] * 7, [0] * 7,
                [3, 0, 0, 0, 0, 13, 0], [0] * 7, [0, 0, 0, 0, 0, 2, 0]]
    mode = "Multiplier Mushrooms Studio"
    with ms.cleo_odds_active({"uses": 3}):
        ranked = ms.rank_moves(board, specials, include_future_value=True, mode=mode, strategy_context="solo_6")
    tier, pool = ms._rank_cleo_policy_moves(
        ranked, mode, None, None, ms.TurnState(remaining_moves=4, source="memory"), "solo_6")
    assert not tier
    assert any(ms.cleo_effective_chance(item) is not None for item in pool)


def test_second_figure_of_a_turn_clears_the_threshold_third_does_not():
    board = [[3, 3, 6, 5, 1, 2, 6], [6, 2, 4, 2, 3, 1, 2], [5, 5, 3, 4, 5, 4, 6],
             [2, 4, 6, 6, 3, 5, 4], [3, 1, 1, 4, 2, 99, 3], [4, 2, 3, 1, 6, 6, 1],
             [1, 5, 2, 1, 4, 3, 5]]
    specials = [[0, 0, 0, 0, 0, 17, 0], [0] * 7, [0] * 7, [0] * 7,
                [3, 0, 0, 0, 0, 13, 0], [0] * 7, [0, 0, 0, 0, 0, 2, 0]]
    turn = ms.TurnState(remaining_moves=4, source="memory")

    def tier(uses):
        with ms.cleo_odds_active({"uses": uses}):
            ranked = ms.rank_moves(board, specials, include_future_value=True, mode="None",
                                   strategy_context="solo_6")
        return ms._rank_cleo_policy_moves(ranked, "None", None, None, turn, "solo_6")[0]

    assert tier(2) and ms.cleo_effective_chance(tier(2)[0]) == pytest.approx(0.58, abs=0.01)
    assert not tier(3)


def test_weak_cleo_still_skipped_in_other_modes():
    best = _weak_cleo_case("None")[0]
    assert ms.cleo_effective_chance(best) is None
