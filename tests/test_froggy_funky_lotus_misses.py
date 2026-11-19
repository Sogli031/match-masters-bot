"""Froggy Fu on Funky Tiles, refill misses 2026-11-19, all exact now.

* 001528, 003841: a cascade of rows 3 and 4 + column 5 around a 2x2 (seven
  cells, draw % 7 == 2). The combo's first x-major cell is in neither run, so
  the column leads the listing (_lt_listed_cells ``first``); the row-first
  list put the bomb on the row's end.
* 004054, 004341: a Lightning swapped with a plain piece and no line is no
  possible move for the lotus planner, so the piece next to it gets no swap
  penalty and wins the tie as the first x-major cell.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "froggy_funky_lotus"


@pytest.mark.parametrize("name", ["001528", "003841", "004054", "004341"])
def test_recorded_froggy_activation_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


def test_lightning_swap_without_a_line_is_no_lotus_move():
    import engine_froggy_placement as fp

    plain = lambda color: fp.Slot(color, 0, True, True)
    grid = [[plain(2 + (x + y) % 3) for x in range(5)] for y in range(5)]
    grid[2][2] = fp.Slot(3, fp.LIGHTNING, True, True)
    moves = fp.possible_moves(grid)
    assert not any((2, 2) in (a, b) and combos == [[a, b]] for a, b, combos in moves)
