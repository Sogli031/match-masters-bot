"""Jelly SE conversion charge: every blue repainted to another colour counts.

The player (2026-09-15): two blue in the zone and an orange conversion is +2 on
the meter. Board recorded 2026-09-15 00:08:32 (Debug/runs); the move converted
the zone to orange and the meter rose by exactly 2.
"""
import move_strategy as ms

BOARD = [
    [4, 2, 6, 6, 2, 1, 6], [6, 6, 2, 3, 1, 4, 1], [4, 6, 3, 1, 3, 4, 4],
    [2, 2, 3, 4, 5, 3, 2], [4, 3, 1, 3, 1, 1, 5], [4, 6, 6, 5, 4, 5, 2],
    [5, 5, 2, 5, 6, 5, 3],
]
SPECIAL = [
    [0] * 7, [0] * 7, [0, 0, 0, 0, 0, 17, 0], [0] * 7,
    [0, 4, 0, 0, 0, 0, 0], [0] * 7, [0, 0, 0, 0, 2, 0, 0],
]
ZONE = [(1, 0), (1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3), (2, 4),
        (3, 1), (3, 2), (3, 3), (4, 2)]


def test_two_lines_make_one_cross_on_the_swipe_end_cell():
    # Engine GetMergeSwapOutcome: H+V (and H+H, V+V) is one Cross, the full
    # row and column through the cell the dragged piece lands on.
    size = 7
    board = [[2 + (row * 3 + col) % 5 for col in range(size)] for row in range(size)]
    special_board = [[ms.EMPTY] * size for _ in range(size)]
    special_board[5][5] = ms.SPECIAL_VERTICAL    # dragged, from (5,5) up
    special_board[4][5] = ms.SPECIAL_HORIZONTAL
    post_board, post_special = ms.swap_cells(board, special_board, (5, 5), (4, 5))
    candidate = ms.MoveCandidate((5, 5), (4, 5), ms.Direction.UP, post_board, post_special)
    events = []
    cells = ms._merge_swap_effect_cells(
        post_board, post_special, candidate, post_special[5][5], post_special[4][5], events
    )
    expected = {(4, col) for col in range(size)} | {(row, 5) for row in range(size)}
    assert cells == expected
    assert events and events[0]["special"] == "line_cross"


def test_non_blue_conversion_charges_the_blue_it_repaints():
    with ms.jelly_zone_cells(ZONE):
        evaluations = ms.rank_moves(
            BOARD, SPECIAL, mode="None", lookahead_candidates=0, include_future_value=False
        )
    played = next(
        item for item in evaluations
        if {tuple(item.candidate.start), tuple(item.candidate.target)} == {(0, 2), (1, 2)}
        and any(e.get("type") == ms.JELLY_ZONE_CONVERSION_EVENT for e in item.intent_events)
    )
    conversion = next(
        e for e in played.intent_events if e.get("type") == ms.JELLY_ZONE_CONVERSION_EVENT
    )
    assert conversion["color"] == ms.ORANGE
    assert conversion["charge_converted"] == 2
    charge = [
        e for e in played.intent_events
        if e.get("type") == ms.MEASURED_CHARGE_EVENT and e.get("source") == "jelly_zone_conversion"
    ]
    assert charge and charge[0]["blue_cells"] == 2.0
