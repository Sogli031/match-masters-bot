"""DestroyRowOnHorizontalMatch on an L/T: only the row the match runs along.

Mutation Lab refill_misses 2026-11-14 220707-221451 (mutations 22 and 30 in
force). 220923: an L of colour 5, run on row 2 and leg down column 4. The game
cleared row 2 and every colour 5 (mutation 30); the simulator also swept rows
3 and 4, the leg's rows, 8 cells too many, and drew 56 refills too many.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

FIXTURES = ROOT / "tests" / "fixtures" / "mutation_lab_row_sweep"
L_SHAPE = frozenset({(2, 4), (2, 5), (2, 6), (3, 4), (4, 4)})


def _board():
    return [[1] * 7 for _ in range(7)]


def test_l_sweeps_only_its_run_row():
    cells = ms._line_destruction_cells(_board(), [ms.MatchGroup(L_SHAPE, 5, "l")],
                                       sweep_rows=True, sweep_columns=False)
    assert {row for row, _ in cells} == {2}


def test_l_sweeps_only_its_leg_column():
    cells = ms._line_destruction_cells(_board(), [ms.MatchGroup(L_SHAPE, 5, "l")],
                                       sweep_rows=False, sweep_columns=True)
    assert {col for _, col in cells} == {4}


def test_arcade_man_still_sweeps_every_line():
    cells = ms._arcade_man_cells(_board(), [ms.MatchGroup(L_SHAPE, 5, "l")])
    assert {row for row, _ in cells} == set(range(7))


@pytest.mark.parametrize("name", ["220923", "221451"])
def test_recorded_miss_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
