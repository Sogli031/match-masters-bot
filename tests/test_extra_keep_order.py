import move_strategy as ms


# Debug/runs/2026-11-13_12-27-38_475 (Color Crush, Solo Challenge, meter 7/7).
# Two sure extras: the yellow four (4,2)<->(5,2) in row 5 and the blue four
# (2,1)<->(3,1) in row 3. Yellow first drops row 3 and the blue four is gone;
# blue first leaves rows 4-5 untouched, so the yellow four is still there and
# both extras get played.
BOARD = [
    [6, 5, 3, 2, 6, 1, 6],
    [1, 6, 2, 5, 3, 2, 6],
    [4, 1, 5, 4, 6, 1, 4],
    [1, 6, 1, 1, 6, 4, 3],
    [2, 2, 3, 3, 4, 4, 5],
    [3, 3, 5, 3, 4, 3, 5],
    [4, 2, 2, 4, 2, 1, 3],
]
SPECIALS = [[0] * 7 for _ in range(7)]
SPECIALS[6][5] = 2
RALLY = {6: 3.0, 3: 5.0, 2: 2.0, 4: 4.0}


def _key(evaluation):
    return {tuple(evaluation.candidate.start), tuple(evaluation.candidate.target)}


def test_extra_that_keeps_the_other_extra_goes_first():
    context = ms.StrategyContext(
        mode="solo_6",
        booster_rush=True,
        solo_challenge=True,
        solo_goal={"targets": [800, 1650, 2775], "score": 28, "refill_moves": 0,
                   "overflow": True, "continue_after_last": True},
    )
    meter = ms.BoosterState(current=7, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=8, source="memory")
    ranked = ms.rank_moves(
        BOARD, SPECIALS, mode="Color Crush Mode", score_rally_values=RALLY,
        include_future_value=True, lookahead_candidates=10, lookahead_depth=2,
        lookahead_beam_width=3, strategy_context=context, turn_state=turn,
    )
    ranked = ms.prioritize_ranked_moves(
        ranked, mode="Color Crush Mode", score_rally_values=RALLY,
        booster_state=meter, turn_state=turn, strategy_context=context,
    )
    assert _key(ranked[0]) == {(2, 1), (3, 1)}
    assert ms.has_guaranteed_true_extra(ranked[0])
