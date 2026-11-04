from engine_spawn_predicates import (
    combo_count_at, highrank_patterns, is_part_of_combo,
    is_part_of_possible_highrank_combo, matches_with_color,
)


def blank(size=7):
    return [[0] * size for _ in range(size)]


def test_lines_work_at_each_position_and_out_count_saturates_at_three():
    board = blank()
    board[2][:5] = [3] * 5
    for x in range(5):
        assert is_part_of_combo(board, x, 2)
        assert combo_count_at(board, x, 2) == 3
    assert not is_part_of_combo(board, 5, 2)


def test_square_is_separate_from_line_and_can_be_disabled():
    board = blank()
    for x, y in ((1, 1), (2, 1), (1, 2), (2, 2)):
        board[y][x] = 6
    assert combo_count_at(board, 1, 1) == 4
    assert not is_part_of_combo(board, 1, 1, square=False)


def test_axis_hit_takes_priority_over_square_for_out_count():
    board = blank()
    for x, y in ((1, 1), (2, 1), (1, 2), (2, 2), (1, 3)):
        board[y][x] = 6
    assert combo_count_at(board, 1, 1) == 3


def test_center_not_matchable_rejects_combo_but_colored_specials_match():
    board = blank()
    board[0][:3] = [3, {"color": 3, "value": 6, "canBeMatched": False}, 3]
    assert not is_part_of_combo(board, 1, 0)
    board[0][1]["canBeMatched"] = True
    assert is_part_of_combo(board, 1, 0)


def test_secondary_color_and_all_follow_slot_model_rules():
    assert matches_with_color({"color": 6, "color2": 3, "value": 0}, 3)
    assert matches_with_color({"color": 12, "value": 0}, 5)
    assert not matches_with_color({"color": 1, "color2": 3, "value": 0}, 3)
    assert not matches_with_color({"color": 3, "value": 25}, 3)


def test_four_sequence_pattern_is_potential_not_existing_line():
    board = blank()
    coords = [(2, 1), (2, 2), (3, 3), (2, 4)]
    for x, y in coords:
        board[y][x] = 5
    for x, y in coords:
        assert is_part_of_possible_highrank_combo(board, x, y, 1)
        assert not is_part_of_combo(board, x, y)
    board[3][3] = 6
    assert not is_part_of_possible_highrank_combo(board, 2, 1, 1)


def test_square_move_pattern_and_rotation_match_only_rank_two():
    board = blank()
    coords = [(2, 1), (1, 2), (1, 3), (2, 3)]
    for x, y in coords:
        board[y][x] = 7
    assert is_part_of_possible_highrank_combo(board, 2, 1, 2)
    assert not is_part_of_possible_highrank_combo(board, 2, 1, 1)
    rotated = blank()
    for x, y in coords:
        rotated[x][6 - y] = 7
    assert is_part_of_possible_highrank_combo(rotated, 5, 2, 2)


def test_highrank_requires_all_cells_matchable_and_does_not_require_movable():
    board = blank()
    for x, y in [(2, 1), (2, 2), (3, 3), (2, 4)]:
        board[y][x] = {"color": 3, "value": 0, "canBeMatched": True, "movable": False}
    assert is_part_of_possible_highrank_combo(board, 2, 1, 1)
    board[3][3]["canBeMatched"] = False
    assert not is_part_of_possible_highrank_combo(board, 2, 1, 1)


def test_pattern_catalog_has_32_anchored_patterns_per_kind_and_bounds_are_safe():
    assert len(highrank_patterns(1)) == len(highrank_patterns(2)) == 32
    assert highrank_patterns(3) == ()
    board = [[3, 3], [3, 3]]
    assert not is_part_of_possible_highrank_combo(board, 0, 0, 1)
    assert not is_part_of_possible_highrank_combo(board, 0, 0, 2)
