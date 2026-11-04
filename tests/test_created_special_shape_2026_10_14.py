"""MakeSpecialSlotCreated (0x5726da4): the special a combo leaves depends on its shape.

ComboType -> SlotValueType: Five->Fireworks, RShape->Bomb, FourRow->Row,
FourColumn->Column, Square->Crosshair. Before 2026-10-14 the bot carried every four
and L/T as an unresolved CREATED_SPECIAL with a bomb blast.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402


def group(cells, kind):
    return ms.MatchGroup(frozenset(cells), ms.RED, kind)


def test_four_in_a_row_leaves_a_row_special():
    match = group([(2, 0), (2, 1), (2, 2), (2, 3)], "four")
    assert ms._created_special_type(match) == ms.SPECIAL_HORIZONTAL


def test_four_in_a_column_leaves_a_column_special():
    match = group([(0, 4), (1, 4), (2, 4), (3, 4)], "four")
    assert ms._created_special_type(match) == ms.SPECIAL_VERTICAL


def test_l_and_t_leave_a_bomb():
    l_cells = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
    t_cells = [(0, 0), (0, 1), (0, 2), (1, 1), (2, 1)]
    assert ms._created_special_type(group(l_cells, "l")) == ms.SPECIAL_BOMB
    assert ms._created_special_type(group(t_cells, "t_or_cross")) == ms.SPECIAL_BOMB


def test_square_and_five_unchanged():
    square = group([(0, 0), (0, 1), (1, 0), (1, 1)], "square")
    five = group([(0, i) for i in range(5)], "five")
    assert ms._created_special_type(square) == ms.SPECIAL_CROSSHAIR
    assert ms._created_special_type(five) == ms.SPECIAL_LIGHTNING


def test_three_leaves_nothing_to_resolve():
    three = group([(0, 0), (0, 1), (0, 2)], "three")
    assert ms._created_special_type(three) == ms.CREATED_SPECIAL
