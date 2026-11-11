"""With nothing charging the meter now, the bad moves work toward the next blue.

The player, 2026-11-04: with no good move the bot should play something that
joins the blues as soon as possible. The boards are random ones with no blue
match, no extra and no special on offer.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402

SPECIALS = [[0] * 7 for _ in range(7)]
RACE = ms.StrategyContext(ms.STRATEGY_SOLO_6)
RUSH = ms.StrategyContext(ms.STRATEGY_SOLO_6, booster_rush=True)
CHALLENGE = ms.StrategyContext(ms.STRATEGY_SOLO_6, solo_challenge=True)
VERSUS = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
EMPTY_METER = ms.BoosterState(current=0, maximum=7, source="memory")
FIVE_MOVES = ms.TurnState(remaining_moves=5, source="memory")

# (3,5)-(3,6) drops a blue next to the pickup; the other two moves do not.
ONE_MOVE_AWAY = [
    [1, 2, 3, 1, 1, 6, 4],
    [2, 6, 3, 4, 3, 2, 3],
    [1, 3, 2, 4, 1, 6, 2],
    [4, 6, 2, 3, 3, 4, 3],
    [3, 3, 6, 1, 2, 1, 2],
    [6, 2, 3, 2, 6, 3, 4],
    [4, 2, 1, 1, 6, 6, 4],
]
SETUP_MOVE = {(3, 5), (3, 6)}

# No move sets a pickup up, but (2,3)-(2,4) opens one for the move after.
TWO_MOVES_AWAY = [
    [2, 6, 4, 3, 4, 6, 6],
    [1, 1, 2, 2, 3, 3, 6],
    [2, 4, 3, 4, 2, 1, 2],
    [6, 4, 2, 2, 1, 4, 2],
    [1, 2, 3, 3, 4, 6, 1],
    [4, 6, 4, 3, 6, 1, 2],
    [2, 6, 4, 2, 2, 4, 3],
]
NO_PATH_MOVE = {(0, 3), (1, 3)}
FOUR_BLUE_MOVE = {(2, 3), (2, 4)}


def ranked(board):
    return ms.rank_moves(board, SPECIALS, mode="None", lookahead_candidates=0,
                         include_future_value=False)


def cells(evaluation):
    return {tuple(evaluation.candidate.start), tuple(evaluation.candidate.target)}


def credit(rows, booster=EMPTY_METER, turn=FIVE_MOVES, context=RACE):
    return ms._with_blue_setup_priority(rows, "None", False, None, False, booster, turn, context)


def by_cells(rows, wanted):
    return next(row for row in rows if cells(row[1]) == wanted)


def test_setup_is_played_on_equal_points():
    moves = ms.prioritize_ranked_moves(
        ranked(ONE_MOVE_AWAY), mode="None", booster_state=EMPTY_METER,
        turn_state=FIVE_MOVES, strategy_context=CHALLENGE)
    assert cells(moves[0]) == SETUP_MOVE
    assert moves[0].solo_blue_plan_charge == 3.0


def test_solo_collects_blue_now_when_both_plans_fill_the_meter(monkeypatch):
    moves = ranked(ONE_MOVE_AWAY)
    pickup = ms.replace(moves[0], blue_cells=3.0)
    setup = ms.replace(moves[1], score=100.0)
    meter = ms.BoosterState(current=5, maximum=7, source="memory")

    # The setup would fill the same two cells one move later.
    monkeypatch.setattr(ms, "_disco_post_board_evaluations", lambda *_: [pickup])
    ordered = ms._solo_charge_plan_order(
        [setup, pickup], "None", False, None, False, meter, FIVE_MOVES, CHALLENGE,
        free_start=False,
    )
    assert [item.solo_blue_plan_charge for item in ordered] == [2.0, 2.0]
    assert ordered[0].candidate == pickup.candidate


def test_race_keeps_a_measured_extra_setup_ahead():
    # (4,2)-(5,2) leaves an extra, priced in a race at its full 18.5.
    moves = ms.prioritize_ranked_moves(
        ranked(ONE_MOVE_AWAY), mode="None", booster_state=EMPTY_METER,
        turn_state=FIVE_MOVES, strategy_context=RACE)
    assert cells(moves[0]) == {(4, 2), (5, 2)}
    assert cells(moves[1]) == SETUP_MOVE


def test_setup_beats_a_few_more_points_but_not_a_good_move():
    moves = ranked(ONE_MOVE_AWAY)
    setup = next(item for item in moves if cells(item) == SETUP_MOVE)
    other = next(item for item in moves if cells(item) != SETUP_MOVE)
    rows, found = credit([(10.0, other), (8.0, setup)])
    assert found
    assert max(rows, key=lambda row: row[0])[1].candidate.start == setup.candidate.start
    rows, _found = credit([(60.0, other), (8.0, setup)])
    assert max(rows, key=lambda row: row[0])[1].candidate.start == other.candidate.start


def test_price_is_a_share_of_what_the_pickup_pays():
    rows, _found = credit([(0.0, item) for item in ranked(ONE_MOVE_AWAY)])
    paid = ms._blue_priority_components_for_cells(
        3.0, EMPTY_METER, ms.TurnState(remaining_moves=4, source="memory"), RACE)[0]
    assert by_cells(rows, SETUP_MOVE)[0] == pytest.approx(paid * ms.BLUE_SETUP_NEXT_MOVE_SHARE)


def test_challenge_prices_blue_higher_than_a_race():
    rows = [(0.0, item) for item in ranked(ONE_MOVE_AWAY)]
    race, _ = credit(rows, context=RACE)
    challenge, _ = credit(rows, context=CHALLENGE)
    rush, _ = credit(rows, context=RUSH)
    assert by_cells(challenge, SETUP_MOVE)[0] > by_cells(race, SETUP_MOVE)[0]
    assert by_cells(rush, SETUP_MOVE)[0] > by_cells(race, SETUP_MOVE)[0]


def test_looks_two_moves_ahead_only_with_no_setup_on_the_board():
    moves = ranked(TWO_MOVES_AWAY)
    rows, found = credit([(0.0, item) for item in moves])
    assert found
    assert by_cells(rows, FOUR_BLUE_MOVE)[0] > 0
    assert "blue_setup_2=" in by_cells(rows, FOUR_BLUE_MOVE)[1].explanation
    assert by_cells(rows, NO_PATH_MOVE)[0] == 0
    # A next-move setup is the sooner blue, and it is what gets the credit.
    rows, _found = credit([(0.0, item) for item in ranked(ONE_MOVE_AWAY)])
    assert all("blue_setup_2=" not in item.explanation for _priority, item in rows)


def test_two_move_credit_is_below_the_next_move_credit():
    turn = FIVE_MOVES
    two, _ = credit([(0.0, item) for item in ranked(TWO_MOVES_AWAY)], turn=turn)
    best_two = max(priority for priority, _item in two)
    paid = ms._blue_priority_components_for_cells(
        4.0, EMPTY_METER, ms.TurnState(remaining_moves=4, source="memory"), RACE)[0]
    assert best_two < paid * ms.BLUE_SETUP_NEXT_MOVE_SHARE


def test_expired_budget_only_drops_the_two_move_credit(monkeypatch):
    monkeypatch.setattr(ms, "BLUE_SETUP_TWO_MOVES_SECONDS", -1.0)
    rows = [(0.0, item) for item in ranked(TWO_MOVES_AWAY)]
    out, found = credit(rows)
    assert not found and out is rows


@pytest.mark.parametrize("moves,context,plies", [
    (1, RACE, 0),
    (2, RACE, 0),      # the pickup is the last move: nothing left to fire with
    (3, RACE, 1),
    (4, RACE, 2),
    (9, CHALLENGE, 2),
    (1, VERSUS, 0),
    (2, VERSUS, 1),
    (9, VERSUS, 1),    # the board is the opponent's after this turn
])
def test_how_far_a_setup_can_pay(moves, context, plies):
    turn = ms.TurnState(remaining_moves=moves, source="memory")
    assert ms._blue_setup_plies(turn, context) == plies


def test_clock_shortens_the_horizon():
    turn = ms.TurnState(remaining_moves=9, source="memory",
                        time_left_seconds=14.0, seconds_per_move=6.5)
    assert ms._blue_setup_plies(turn, RACE) == 0
    turn = ms.TurnState(remaining_moves=9, source="memory",
                        time_left_seconds=30.0, seconds_per_move=6.5)
    assert ms._blue_setup_plies(turn, RACE) == 2


@pytest.mark.parametrize("booster,turn,context", [
    (ms.BoosterState(current=7, maximum=7, source="memory"), FIVE_MOVES, RACE),
    (ms.BoosterState.unknown(), FIVE_MOVES, RACE),
    (EMPTY_METER, ms.TurnState(remaining_moves=2, source="memory"), RACE),
    (EMPTY_METER, ms.TurnState(remaining_moves=5, source="memory", is_final_round=True,
                               current_round=3, total_rounds=3), VERSUS),
])
def test_no_credit_when_charge_cannot_pay(booster, turn, context):
    rows = [(0.0, item) for item in ranked(ONE_MOVE_AWAY)]
    out, found = credit(rows, booster=booster, turn=turn, context=context)
    assert not found and out is rows


def test_charge_on_offer_goes_first():
    moves = ranked(ONE_MOVE_AWAY)
    charging = ms.replace(moves[0], blue_cells=3.0)
    rows = [(0.0, charging)] + [(0.0, item) for item in moves[1:]]
    out, found = credit(rows)
    assert not found and out is rows


def test_flag_turns_it_off(monkeypatch):
    monkeypatch.setattr(ms, "BLUE_SETUP_PRIORITY", False)
    rows = [(0.0, item) for item in ranked(ONE_MOVE_AWAY)]
    out, found = credit(rows)
    assert not found and out is rows


def test_board_motion_stays_out_of_a_setup():
    moves = ms.prioritize_ranked_moves(
        ranked(ONE_MOVE_AWAY), mode="None", booster_state=EMPTY_METER,
        turn_state=FIVE_MOVES, strategy_context=RACE)
    assert all("board_motion" not in item.explanation for item in moves)
