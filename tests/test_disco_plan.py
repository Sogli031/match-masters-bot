"""Brocco disco planning under the solo blue-first policy (2026-09-14 fixes).

Boards are the recorded ones from the 2026-09-14 23:26-23:31 Brocco solo match
(Debug/runs), board and special board exactly as the bot saw them.
"""
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
    service = ms._disco_plan_service(cashes, "None", False, RALLY, booster, SOLO, baseline)
    assert service >= 3.0


BOARD_23_30_32 = [
    [2, 2, 5, 5, 6, 6, 5], [3, 5, 4, 3, 2, 2, 1], [4, 3, 1, 6, 1, 4, 2],
    [3, 1, 4, 3, 6, 1, 1], [1, 3, 4, 4, 99, 3, 6], [4, 6, 2, 4, 2, 1, 6],
    [1, 6, 3, 6, 6, 3, 4],
]
SPECIAL_23_30_32 = [
    [0] * 7, [0] * 7, [0] * 7, [0] * 7, [0, 0, 0, 0, 16, 0, 0],
    [0, 0, 0, 1, 0, 0, 0], [0, 0, 0, 0, 3, 0, 0],
]


def test_solo_disco_uses_points_when_none_charges_now():
    evaluations = _evaluations(BOARD_23_30_32, SPECIAL_23_30_32)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=4, source="memory")
    ranked = ms._rank_disco_fallback_moves(
        evaluations, score_rally_values=RALLY, booster_state=booster,
        strategy_context=SOLO, turn_state=turn,
    )
    assert all(ms._solo_disco_reliable_charge(item, booster, "None") == 0 for item in ranked)
    assert ranked[0].score == max(item.score for item in ranked)


@pytest.mark.parametrize("remaining_moves", [4, 1])
def test_solo_disco_charges_before_scoring_points(remaining_moves):
    evaluations = _evaluations(BOARD_23_29_53, SPECIAL_23_29_53)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    ranked = ms._rank_disco_fallback_moves(
        evaluations, score_rally_values=RALLY, booster_state=booster,
        strategy_context=SOLO, turn_state=ms.TurnState(remaining_moves=remaining_moves, source="memory"),
    )
    assert ms._solo_disco_reliable_charge(ranked[0], booster, "None") == 3
    assert all(ms._solo_disco_reliable_charge(item, booster, "None") == 0 for item in ranked[3:])
