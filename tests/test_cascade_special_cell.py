import move_strategy as ms
from move_strategy import MatchGroup


def group(cells):
    return MatchGroup(color=1, cells=cells, kind="four")


LEFT = group({(3, 0), (3, 1), (3, 2), (3, 3)})
RIGHT = group({(5, 3), (5, 4), (5, 5), (5, 6)})


def test_cascade_special_sits_on_its_combos_draw():
    with ms.engine_refill_active(lambda *a: a, lambda count: [6, 9][:count]):
        assert ms._created_special_cell(LEFT, (), [RIGHT, LEFT]) == (3, 2)    # first combo scanned: 6 % 4
        assert ms._created_special_cell(RIGHT, (), [RIGHT, LEFT]) == (5, 4)   # second: 9 % 4


def test_swap_cell_wins_and_no_rng_keeps_the_last_cell():
    with ms.engine_refill_active(lambda *a: a, lambda count: [0] * count):
        assert ms._created_special_cell(LEFT, ((3, 1),), ()) == (3, 1)
    assert ms._created_special_cell(LEFT, (), [LEFT]) == (3, 3)
