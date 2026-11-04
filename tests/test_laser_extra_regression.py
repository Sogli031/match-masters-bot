"""Laser extra-button regression: 2026-10-28_06-43-17_660, moves 6 -> 5."""

import json
from pathlib import Path

import move_strategy as ms


BOARD = [
    [3, 4, 2, 1, 1, 2, 6],
    [3, 5, 6, 6, 1, 1, 6],
    [5, 6, 5, 6, 5, 3, 5],
    [4, 2, 3, 2, 5, 5, 3],
    [1, 1, 3, 2, 6, 1, 2],
    [4, 3, 2, 3, 2, 4, 3],
    [3, 2, 1, 6, 4, 4, 2],
]


def specials():
    result = [[0] * 7 for _ in range(7)]
    result[6][3] = ms.SPECIAL_VERTICAL
    return result


def test_laser_settle_does_not_claim_the_recorded_false_extra():
    ranked = ms.rank_moves(BOARD, specials(), mode=ms.GameMode.LASER,
                           lookahead_candidates=0)
    move = next(item for item in ranked
                if item.candidate.start == (5, 2)
                and item.candidate.target == (5, 3))
    assert move.direct_extra_moves == 0
    assert move.extra_moves == 0
    assert not ms.has_reliable_same_move_extra(move)
    assert not any(event.get("reason") == "laser_clear_unverified_settle"
                   for event in move.intent_events)
    assert not any(event.get("kind") == "l" for event in move.intent_events)


def test_extra_button_does_nothing_on_the_recorded_board():
    assert ms.rank_extra_move_moves(BOARD, specials(), mode=ms.GameMode.LASER,
                                    lookahead_candidates=0) == []


def test_laser_direct_four_still_qualifies_for_extra_button():
    board = [row[:] for row in BOARD]
    board[0][:4] = [ms.RED, ms.RED, ms.GREEN, ms.RED]
    board[1][2] = ms.RED
    ranked = ms.rank_extra_move_moves(board, specials(), mode=ms.GameMode.LASER,
                                      lookahead_candidates=0)
    move = next(item for item in ranked
                if {item.candidate.start, item.candidate.target}
                == {(0, 2), (1, 2)})
    assert move.direct_extra_moves >= 1
    assert ms.has_reliable_same_move_extra(move)


def test_both_matched_colours_emit_lasers_but_block_each_other():
    board = [[ms.YELLOW] * 7 for _ in range(7)]
    # Adjacent red and green vertical threes. Each emits outwards. Neither
    # may fire through the other original match to a same-colour endpoint.
    for row in (2, 3, 4):
        board[row][2] = ms.RED
        board[row][3] = ms.GREEN
    board[2][0] = ms.RED
    board[2][5] = ms.GREEN
    board[3][0] = ms.GREEN
    board[3][6] = ms.RED
    matches = [
        ms.MatchGroup(color=ms.RED, cells=((2, 2), (3, 2), (4, 2)), kind="three"),
        ms.MatchGroup(color=ms.GREEN, cells=((2, 3), (3, 3), (4, 3)), kind="three"),
    ]
    cells = ms._laser_effect_cells(board, matches)
    assert {(2, 0), (2, 1), (2, 4), (2, 5)} <= cells
    assert not {(3, 0), (3, 1), (3, 4), (3, 5), (3, 6)} & cells


def test_blue_lasers_cross_intervening_tiles_as_in_the_reference_image():
    board = [[ms.RED] * 7 for _ in range(7)]
    for row in (1, 2, 3):
        board[row][1] = ms.BLUE
    board[1][3] = ms.BLUE
    board[3][4] = ms.BLUE
    match = ms.MatchGroup(color=ms.BLUE, cells=((1, 1), (2, 1), (3, 1)), kind="three")
    assert ms._laser_effect_cells(board, [match]) == {
        (1, 2), (1, 3), (3, 2), (3, 3), (3, 4)
    }


def test_laser_ray_colour_order_is_native_down_up_right_left():
    # One source with a same-colour endpoint on each ray. The first victim
    # colour must come from the downward ray, even if a rightward one exists.
    board = [[ms.YELLOW] * 5 for _ in range(5)]
    for row, col in ((2, 2), (4, 2), (0, 2), (2, 4), (2, 0)):
        board[row][col] = ms.RED
    board[3][2], board[1][2], board[2][3], board[2][1] = (
        ms.ORANGE, ms.GREEN, ms.BLUE, ms.PURPLE
    )
    match = ms.MatchGroup(color=ms.RED, cells=frozenset({(2, 2)}), kind="three")
    paths = ms._laser_effect_paths(board, [match])
    assert paths == [((3, 2), (4, 2)), ((1, 2), (0, 2)),
                     ((2, 3), (2, 4)), ((2, 1), (2, 0))]
    special_board = [[ms.EMPTY] * 5 for _ in range(5)]
    colours = ms._ufo_laser_colors(board, special_board, [match], ((2, 2),))
    assert ms._ufo_abduction_colors([ms.RED] + colours, set(), 2) == [ms.RED, ms.ORANGE]
    # As in BeforeCombosDestroy, a Cleo victim does not contribute its colour.
    special_board[3][2] = ms.SPECIAL_CLEO_BUG
    colours = ms._ufo_laser_colors(board, special_board, [match], ((2, 2),))
    assert ms._ufo_abduction_colors([ms.RED] + colours, set(), 2) == [ms.RED, ms.GREEN]


def test_recorded_false_extra_and_real_cascade_extras():
    cases = json.loads((Path(__file__).parent / "fixtures" /
                        "laser_recorded_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        ranked = ms.rank_moves(case["board"], case["special_board"],
                               mode=ms.GameMode.LASER, lookahead_candidates=0)
        move = next(item for item in ranked
                    if {item.candidate.start, item.candidate.target}
                    == {tuple(case["start"]), tuple(case["target"])})
        assert move.direct_extra_moves == 0, case["run"]
        assert move.extra_moves == case["extra"], case["run"]
        assert ms.has_reliable_same_move_extra(move) == bool(case["extra"]), case["run"]
