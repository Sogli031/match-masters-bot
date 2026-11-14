"""A cascade combo of three lines (row, column, row) keeps the x-major scan.

refill_misses 2026-11-14 204404 (Color Crush): seven blue cells, row 4 from
column 4, column 4 down to row 6, row 6 from column 2. The placement draw was
0 mod 7 and the game put the bomb on (6, 2), the scan's first cell. The L/T
listing (one row + one column) left (6, 2) and (6, 3) out and put it on the
corner (4, 4); every cascade after that was a different board.
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms

ROOT = Path(__file__).resolve().parents[1]
MISS = ROOT / "Debug" / "refill_misses" / "20261114_204404_682423_color-crush"
Z_SHAPE = frozenset({(4, 4), (4, 5), (4, 6), (5, 4), (6, 2), (6, 3), (6, 4)})


def test_three_line_combo_draws_over_the_scan(monkeypatch):
    monkeypatch.setattr(ms, "_ENGINE_PEEK_DRAWS", lambda n: [227404030] * n)
    match = ms.MatchGroup(Z_SHAPE, 1, "l")
    assert ms._created_special_cell(match, (), [match]) == (6, 2)


def test_plain_l_still_uses_its_listing(monkeypatch):
    monkeypatch.setattr(ms, "_ENGINE_PEEK_DRAWS", lambda n: [0] * n)
    l_shape = frozenset({(4, 4), (4, 5), (4, 6), (5, 4), (6, 4)})
    match = ms.MatchGroup(l_shape, 1, "l")
    listing = ms._lt_listed_cells(ms._lt_row_then_column_cells(l_shape), ms.CASCADE_LT_CELL_ORDER)
    assert ms._created_special_cell(match, (), [match]) == listing[0]


def test_recorded_miss_is_exact():
    if not MISS.is_dir():
        pytest.skip("recording not on this machine")
    import refill_monitor

    before = json.loads((MISS / "000.json").read_text(encoding="utf-8"))
    after = json.loads((MISS / "001.json").read_text(encoding="utf-8"))
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "ok", result
