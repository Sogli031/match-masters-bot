"""Brocco disco planning under the solo blue-first policy (2026-09-14 fixes).

Boards are the recorded ones from the 2026-09-14 23:26-23:31 Brocco solo match
(Debug/runs), board and special board exactly as the bot saw them.
"""
from dataclasses import replace

import pytest

import move_strategy as ms

SOLO = ms.StrategyContext(mode="solo_6", solo_challenge=True)
# The score legend the bot had on screen in that match.
RALLY = {2: 1.0, 4: 1.0, 6: 1.0, 3: 3.0}


def _evaluations(board, special_board):
    return ms.rank_moves(
        board, special_board, mode="None", score_rally_values=RALLY,
        lookahead_candidates=0, include_future_value=False,
    )


def _disco(evaluations, start, target):
    for item in evaluations:
        if (
            item.disco_moves > 0
            and list(item.candidate.start) == start
            and list(item.candidate.target) == target
        ):
            return item
    raise AssertionError(f"no disco swap {start}->{target}")


def test_a_blast_leaves_another_disco_ball_standing():
    size = 7
    board = [[2 + (row * 3 + col) % 5 for col in range(size)] for row in range(size)]
    special_board = [[ms.EMPTY] * size for _ in range(size)]
    special_board[3][3] = ms.SPECIAL_BOMB
    board[3][4] = ms.DISCO_BALL
    special_board[3][4] = ms.SPECIAL_DISCO_BALL
    cleared, _activated = ms._resolve_special_chain(
        [list(r) for r in board], [list(r) for r in special_board], {(3, 3)}
    )
    assert (3, 4) not in cleared
    assert (3, 2) in cleared  # the bomb itself still clears around it
    # The ball being swapped is the one exception.
    cleared, _activated = ms._resolve_special_chain(
        [list(r) for r in board],
        [list(r) for r in special_board],
        {(3, 3), (3, 4)},
        consumed_disco_cells={(3, 4)},
    )
    assert (3, 4) in cleared


def test_second_ball_survives_the_recorded_disco_bomb_swap():
    # 23:26:38: ball (5,0) dragged onto the bomb at (6,0); ball (6,1) is in
    # the blast. The game kept it (snapshots 21:26:41-48 UTC); so must the plan.
    board = [
        [2, 5, 5, 6, 3, 1, 4], [1, 6, 1, 2, 3, 4, 5], [4, 1, 1, 6, 5, 1, 3],
        [6, 4, 3, 3, 1, 3, 2], [2, 6, 5, 1, 6, 3, 6], [99, 4, 5, 4, 2, 5, 6],
        [6, 99, 4, 6, 5, 2, 4],
    ]
    special_board = [[0] * 7 for _ in range(5)] + [
        [16, 0, 0, 0, 0, 0, 0], [3, 16, 1, 0, 0, 0, 0],
    ]
    swap = _disco(_evaluations(board, special_board), [5, 0], [6, 0])
    follow_ups = ms._disco_post_board_evaluations(swap, "None", False, RALLY)
    assert follow_ups is not None
    assert any(item.disco_moves > 0 for item in follow_ups)


def test_direct_extra_goes_before_a_disco_with_a_refill_extra(monkeypatch):
    # Score Market at 04:08:08. The exact refill gave the ball a cascade extra,
    # so the Solo charge planner could pick it over the direct four.
    board = [
        [4, 2, 5, 2, 1, 5, 2], [2, 5, 99, 2, 2, 3, 3], [1, 4, 99, 5, 4, 5, 3],
        [3, 1, 4, 5, 1, 3, 1], [5, 5, 6, 4, 6, 2, 2], [4, 6, 1, 6, 3, 6, 2],
        [1, 3, 6, 4, 6, 6, 1],
    ]
    specials = [[0] * 7 for _ in board]
    for row, col, value in [(0, 0, 17), (0, 6, 17), (1, 2, 16), (2, 2, 16),
                            (3, 3, 17), (5, 5, 17), (6, 1, 1)]:
        specials[row][col] = value
    evaluations = _evaluations(board, specials)
    disco = replace(_disco(evaluations, [2, 2], [2, 1]), extra_moves=1, exact_refill=True,
                    intent_events=[{"type": "exact_prefix_extra"}])
    extra = next(item for item in evaluations
                 if (item.candidate.start, item.candidate.target) == ((5, 3), (6, 3)))
    assert extra.direct_extra_moves == 1
    assert ms.has_reliable_same_move_extra(disco)

    def favor_disco_for_charge(moves, *args):
        return sorted(moves, key=lambda item: item.disco_moves, reverse=True)

    monkeypatch.setattr(ms, "_solo_charge_plan_order", favor_disco_for_charge)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=5, source="memory")
    ranked = ms.prioritize_ranked_moves([disco, extra], booster_state=booster,
                                      turn_state=turn, strategy_context=SOLO)
    assert ranked[0].candidate is extra.candidate
    assert ms.prioritize_ranked_moves([disco], strategy_context=SOLO)[0].disco_moves == 1


def test_special_pair_converts_jelly_only_when_the_dragged_piece_lands_inside():
    # 2026-09-15 00:01:55: two lightnings, (3,0) inside the jelly zone and
    # (4,0) outside. Dragging the outside one in converts the zone to ITS
    # colour; dragging the inside one out just detonates the pair.
    board = [
        [1, 5, 3, 5, 6, 4, 6], [3, 6, 5, 2, 1, 6, 5], [2, 3, 6, 5, 3, 5, 2],
        [5, 1, 2, 3, 2, 5, 1], [3, 6, 6, 4, 1, 6, 4], [3, 2, 1, 2, 4, 6, 3],
        [4, 1, 5, 2, 6, 1, 4],
    ]
    special_board = [
        [0] * 7, [0] * 7, [0] * 7, [4, 0, 0, 0, 0, 0, 0],
        [4, 17, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0], [0, 0, 0, 0, 2, 0, 0],
    ]
    zone = [(0, 0), (1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2), (3, 0),
            (3, 1), (3, 2), (3, 3), (4, 2)]
    with ms.jelly_zone_cells(zone):
        evaluations = _evaluations(board, special_board)

    def conversions(start, target):
        item = next(
            e for e in evaluations
            if list(e.candidate.start) == start and list(e.candidate.target) == target
        )
        return [x for x in item.intent_events if x.get("type") == ms.JELLY_ZONE_CONVERSION_EVENT]

    inward = conversions([4, 0], [3, 0])
    assert inward and inward[0]["color"] == board[4][0]
    assert conversions([3, 0], [4, 0]) == []


BOARD_23_29_53 = [
    [2, 6, 4, 6, 4, 1, 2], [2, 5, 4, 4, 6, 1, 2], [4, 99, 5, 5, 1, 3, 6],
    [1, 2, 5, 5, 1, 3, 4], [3, 3, 1, 3, 2, 1, 2], [99, 3, 5, 3, 6, 3, 5],
    [3, 2, 1, 6, 5, 5, 2],
]
SPECIAL_23_29_53 = [
    [0] * 7, [0] * 7, [0, 16, 0, 0, 0, 0, 0], [0] * 7, [0] * 7,
    [16, 0, 0, 0, 0, 0, 0], [0] * 7,
]


def test_blue_a_cascade_cashes_for_free_is_not_booked_as_lost():
    evaluations = _evaluations(BOARD_23_29_53, SPECIAL_23_29_53)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    baseline = ms._best_plain_charge(evaluations, booster, "None", RALLY)
    assert baseline == 3.0
    cashes = _disco(evaluations, [5, 0], [4, 0])  # its cascade takes the 3 blue
    service = ms._solo_charge_plan(cashes, "None", False, RALLY, booster, SOLO)
    assert service.charge >= 3.0


BOARD_23_30_32 = [
    [2, 2, 5, 5, 6, 6, 5], [3, 5, 4, 3, 2, 2, 1], [4, 3, 1, 6, 1, 4, 2],
    [3, 1, 4, 3, 6, 1, 1], [1, 3, 4, 4, 99, 3, 6], [4, 6, 2, 4, 2, 1, 6],
    [1, 6, 3, 6, 6, 3, 4],
]
SPECIAL_23_30_32 = [
    [0] * 7, [0] * 7, [0] * 7, [0] * 7, [0, 0, 0, 0, 16, 0, 0],
    [0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 0, 3, 0, 0],
]


def test_solo_disco_uses_points_when_no_charge_plan_can_be_seen(monkeypatch):
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=4, source="memory")
    monkeypatch.setattr(ms, "_disco_post_board_evaluations", lambda *args: None)
    ranked = ms._rank_disco_fallback_moves(
        evaluations, score_rally_values=RALLY, booster_state=booster,
        strategy_context=SOLO, turn_state=turn,
    )
    assert all(ms._solo_disco_reliable_charge(item, booster, "None") == 0 for item in ranked)
    assert ranked[0].score == max(item.score for item in ranked)


def test_solo_disco_plans_a_blue_pickup_even_when_no_ball_charges_now():
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._rank_disco_fallback_moves(
        evaluations, score_rally_values=RALLY, booster_state=booster,
        strategy_context=SOLO, turn_state=ms.TurnState(4, "memory"),
    )
    assert all(ms._solo_disco_reliable_charge(item, booster, "None") == 0 for item in ranked)
    assert ranked[0].solo_blue_plan_charge == 7
    assert ranked[0].score < max(item.score for item in ranked)


@pytest.mark.parametrize("remaining_moves", [4, 1])
def test_solo_looks_past_first_disco_ball_to_bank_more_blue(remaining_moves):
    evaluations = _evaluations(BOARD_23_29_53, SPECIAL_23_29_53)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._rank_disco_fallback_moves(
        evaluations, score_rally_values=RALLY, booster_state=booster,
        strategy_context=SOLO, turn_state=ms.TurnState(
            remaining_moves=remaining_moves, source="memory",
            time_left_seconds=12, seconds_per_move=3,
        ),
    )
    assert ms._solo_disco_reliable_charge(ranked[0], booster, "None") == 0
    assert ranked[0].solo_blue_plan_charge == 6
    assert any(ms._solo_disco_reliable_charge(item, booster, "None") == 3 for item in ranked[1:])


def test_disco_looks_three_actions_ahead_for_blue_when_clock_allows(monkeypatch):
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    near = replace(_disco(evaluations, [4, 4], [4, 3]), blue_cells=4)
    far = replace(_disco(evaluations, [4, 4], [4, 5]), blue_cells=0)
    extra = next(item for item in evaluations if not item.disco_moves)
    first = replace(extra, candidate=replace(extra.candidate), blue_cells=0, direct_extra_moves=1)
    second = replace(extra, candidate=replace(extra.candidate), blue_cells=0, direct_extra_moves=1)
    pickup = replace(extra, candidate=replace(extra.candidate), blue_cells=7, direct_extra_moves=1)
    options = {id(far.candidate): [first], id(first.candidate): [second],
               id(second.candidate): [pickup]}
    monkeypatch.setattr(ms, "_disco_post_board_evaluations",
                        lambda item, *args: options.get(id(item.candidate)))
    monkeypatch.setattr(ms, "_solo_move_charge", lambda item, meter, *args: min(item.blue_cells, meter.remaining))
    booster = ms.BoosterState(current=0, maximum=7, source="memory")

    def ranked(time_left, immediate_charge):
        turn = ms.TurnState(5, "memory", time_left_seconds=time_left, seconds_per_move=3)
        start = replace(near, blue_cells=immediate_charge)
        return ms._solo_charge_plan_order([start, far], "None", False, RALLY, False, booster, turn, SOLO)

    assert ranked(60, 4)[0].candidate is near.candidate
    assert ranked(60, 0)[0].candidate is far.candidate
    assert ranked(9, 0)[0].candidate is near.candidate


def test_disco_prefers_a_full_meter_without_spending_a_move(monkeypatch):
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    paid = replace(_disco(evaluations, [4, 4], [4, 3]), blue_cells=4)
    free = replace(_disco(evaluations, [4, 4], [4, 5]), blue_cells=0)
    plain = next(item for item in evaluations if not item.disco_moves)
    pickup = replace(plain, blue_cells=3, extra_moves=0, direct_extra_moves=0)
    first_extra = replace(plain, candidate=replace(plain.candidate), blue_cells=4, direct_extra_moves=1)
    second_extra = replace(plain, candidate=replace(plain.candidate), blue_cells=3, direct_extra_moves=1)
    options = {id(paid.candidate): [pickup], id(free.candidate): [first_extra],
               id(first_extra.candidate): [second_extra]}
    monkeypatch.setattr(ms, "_disco_post_board_evaluations",
                        lambda item, *args: options.get(id(item.candidate)))
    monkeypatch.setattr(ms, "_solo_move_charge", lambda item, meter, *args: min(item.blue_cells, meter.remaining))
    monkeypatch.setattr(ms, "_best_plain_charge",
                        lambda items, meter, *args: max(min(item.blue_cells, meter.remaining) for item in items))
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._solo_charge_plan_order([paid, free], "None", False, RALLY, False, booster,
                                       ms.TurnState(5, "memory"), SOLO)
    assert [item.solo_blue_plan_charge for item in ranked] == [7, 7]
    assert ranked[0].candidate is free.candidate
    assert "solo_blue_paid=0, solo_blue_actions=3" in ranked[0].explanation
    assert "solo_blue_paid=1, solo_blue_actions=2" in ranked[1].explanation


def test_disco_that_fills_immediately_skips_all_followup_search(monkeypatch):
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    setup = replace(_disco(evaluations, [4, 4], [4, 3]), blue_cells=0)
    immediate = replace(_disco(evaluations, [4, 4], [4, 5]), blue_cells=3)
    tied = replace(_disco(evaluations, [4, 4], [3, 4]), blue_cells=3)
    booster = ms.BoosterState(current=4, maximum=7, source="memory")

    def unexpected_search(*args, **kwargs):
        pytest.fail("A one-action full meter needs no follow-up search")

    monkeypatch.setattr(ms, "_solo_charge_plan", unexpected_search)
    ranked = ms._solo_charge_plan_order([setup, immediate, tied], "None", False, RALLY,
                                       False, booster, ms.TurnState(5, "memory"), SOLO)
    assert [id(item.candidate) for item in ranked] == [
        id(immediate.candidate), id(tied.candidate), id(setup.candidate),
    ]
    assert ranked[0].solo_blue_plan_charge == 3
    assert "solo_blue_paid=0, solo_blue_actions=1" in ranked[0].explanation
    assert ranked[2].solo_blue_plan_charge is None


def test_solo_charge_plan_saves_paid_moves_without_disco(monkeypatch):
    plain = [item for item in _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
             if not item.disco_moves and not ms.has_reliable_same_move_extra(item)]
    quick_pickup = replace(plain[0], blue_cells=3)
    extra_setup = replace(plain[1], blue_cells=0)
    paid_pickup = replace(plain[2], blue_cells=4)
    first_extra = replace(plain[3], blue_cells=3, direct_extra_moves=1)
    second_extra = replace(plain[4], blue_cells=4, direct_extra_moves=1)
    options = {id(quick_pickup.candidate): [paid_pickup], id(extra_setup.candidate): [first_extra],
               id(first_extra.candidate): [second_extra]}
    monkeypatch.setattr(ms, "_disco_post_board_evaluations",
                        lambda item, *args: options.get(id(item.candidate)))
    monkeypatch.setattr(ms, "_solo_move_charge", lambda item, meter, *args: min(item.blue_cells, meter.remaining))
    monkeypatch.setattr(ms, "_best_plain_charge",
                        lambda items, meter, *args: max(min(item.blue_cells, meter.remaining) for item in items))
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._solo_charge_plan_order([quick_pickup, extra_setup], "None", False, RALLY, False,
                                       booster, ms.TurnState(5, "memory"), SOLO, free_start=False)
    assert [item.solo_blue_plan_charge for item in ranked] == [7, 7]
    assert ranked[0].candidate is extra_setup.candidate
    assert "solo_blue_paid=1, solo_blue_actions=3" in ranked[0].explanation
    assert "solo_blue_paid=2, solo_blue_actions=2" in ranked[1].explanation


def test_partial_charge_tie_prefers_the_line_without_a_paid_move(monkeypatch):
    # Score Market 2026-11-12 05:13:09: neither line reaches 7/7 and both bank
    # 6. The ball that picked up 3 now and needed a paid move for the rest won
    # on its immediate pickup over the one that banked the same 6 for free.
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    pickup_now = replace(_disco(evaluations, [4, 4], [4, 3]), blue_cells=3)
    setup = replace(_disco(evaluations, [4, 4], [4, 5]), blue_cells=0)
    plain = next(item for item in evaluations if not item.disco_moves)
    paid_pickup = replace(plain, candidate=replace(plain.candidate), blue_cells=3,
                          extra_moves=0, direct_extra_moves=0)
    first_extra = replace(plain, candidate=replace(plain.candidate), blue_cells=3, direct_extra_moves=1)
    second_extra = replace(plain, candidate=replace(plain.candidate), blue_cells=3, direct_extra_moves=1)
    options = {id(pickup_now.candidate): [paid_pickup], id(setup.candidate): [first_extra],
               id(first_extra.candidate): [second_extra]}
    monkeypatch.setattr(ms, "_disco_post_board_evaluations",
                        lambda item, *args: options.get(id(item.candidate)))
    monkeypatch.setattr(ms, "_solo_move_charge", lambda item, meter, *args: min(item.blue_cells, meter.remaining))
    monkeypatch.setattr(ms, "_best_plain_charge",
                        lambda items, meter, *args: max(min(item.blue_cells, meter.remaining) for item in items))
    monkeypatch.setattr(ms, "has_reliable_same_move_extra", lambda item: item.direct_extra_moves > 0)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._solo_charge_plan_order([pickup_now, setup], "None", False, RALLY, False, booster,
                                       ms.TurnState(5, "memory"), SOLO)
    assert [item.solo_blue_plan_charge for item in ranked] == [6, 6]
    assert ranked[0].candidate is setup.candidate
    assert "solo_blue_paid=0" in ranked[0].explanation
    assert "solo_blue_paid=1" in ranked[1].explanation
