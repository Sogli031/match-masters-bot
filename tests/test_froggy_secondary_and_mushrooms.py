"""Froggy Fu, Bombs Away / Multiplier Mushrooms 2026-11-18."""
import move_strategy as ms
import engine_froggy_placement as fp


def test_colour_pull_leaves_the_secondary_combo_its_cells():
    """Bombs Away 20:52:06: the swap's second three (column 2, rows 1-3)
    keeps its cells; the colour blob grows to (1,3) and (3,1) instead."""
    board = [[6, 5, 5, 1, 5, 5, 1],
             [5, -1, 2, 2, 4, 5, 4],
             [2, 3, 2, 3, 6, 6, 3],
             [4, 3, 2, 1, 2, 6, 1],     # after the swap (3,1) <-> (3,2)
             [3, 3, 1, 1, 3, 1, 6],
             [3, 6, 4, 4, 5, 4, 1],
             [4, 5, 4, 4, 6, 2, 2]]
    secondary = frozenset({(1, 2), (2, 2), (3, 2)})
    landed, after, _specials, secondary_landed = ms.froggy_pull_apply(
        board, (1, 1), 3, 7, True, secondary=secondary)
    assert landed == {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 3), (2, 0), (2, 1), (3, 1)}
    assert secondary_landed == secondary and all(after[r][c] == 2 for r, c in secondary)


def test_placement_reads_a_mushroom_as_a_coloured_piece():
    """Multiplier Mushrooms 20:54: a mushroom made the booster unsupported."""
    sim_to_engine = {1: 4, 2: 3, 3: 5, 4: 7, 5: 2, 6: 6}
    grid = fp.native_grid([[3, 1]], [[fp.SIM_MUSHROOM, 0]], sim_to_engine)
    mushroom = grid[0][0]
    assert (mushroom.color, mushroom.value, mushroom.movable, mushroom.matchable) == (5, fp.MUSHROOM_ENGINE, True, True)
    assert (0, 0) not in fp.lotus_candidates(grid)
