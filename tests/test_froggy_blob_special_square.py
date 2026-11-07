"""What a gathered lotus blob leaves behind when square matches are possible.

Recorded in Multiplier Madness (Debug/research/20261104_132450) and Vertical Rush
(20261104_051654): a blob holding a row and a column of three through one cell is
one RShape combo and leaves a Bomb, even with a 2x2 inside it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402


def cells(*rows):
    return {(r, c) for r, row in enumerate(rows) for c, value in enumerate(row) if value == "#"}


@pytest.mark.parametrize("blob", [
    cells(".#..", "###.", "####", "###."),   # 006, 014, 023
    cells("###", "###", ".##"),              # 011
    cells("###", "###", "###"),              # 015, 023
    cells(".###", "####", ".###"),           # 007
    cells(".##", "###", "###"),              # 026
    cells("###", "###", "###", ".#."),       # 029
])
def test_recorded_blobs_with_a_cross_leave_a_bomb(blob):
    assert ms.froggy_blob_special_shape(blob, True) == "l"
    origin, shape = ms.froggy_blob_special(blob, True)
    assert origin in blob
    assert ms._created_special_type(ms.MatchGroup(frozenset(blob), 1, shape)) == ms.SPECIAL_BOMB


@pytest.mark.parametrize("blob", [
    cells("##", "##"),
    cells("##.", "##.", ".#."),
    cells(".##", ".##", "#.."),
])
def test_a_square_without_a_cross_stays_a_square(blob):
    if ms.froggy_blob_special_shape(blob, True) == "square":
        assert not ms._has_line_cross(blob)
    assert ms.froggy_blob_special_shape(cells("##", "##"), True) == "square"


def test_five_in_a_line_still_wins():
    assert ms.froggy_blob_special_shape(cells("#####", "..#..", "..#.."), True) == "five"


def test_without_the_square_rule_nothing_changes():
    assert ms.froggy_blob_special_shape(cells("###", "###", "###"), False) == "l"


def test_other_combos_get_their_scan_origin_not_the_last_cell():
    other = ms.MatchGroup(frozenset({(4, 3), (4, 4), (4, 5), (5, 5), (6, 5)}), 2, "l")
    origin = min(other.cells, key=ms._froggy_point_key)
    assert origin == (4, 3)
    assert ms._created_special_cell(other, swap_cells=(origin,)) == (4, 3)
    assert ms._created_special_cell(other) == (6, 5)
