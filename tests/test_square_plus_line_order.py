"""A 2x2 square plus one cell in line: the part with the first x-major cell leads.

Traced Square Match refill_misses 2026-11-14 233403 (cascade 2): square
(5,3)-(6,4) plus (6,5). The engine listed the square clockwise from its top
left, then (6,5), and the crosshair (draw % 5 == 2) went on (6,4). The traced
161938 combo, whose first cell (2,0) is in the run, keeps the run first.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

FIXTURE = ROOT / "tests" / "fixtures" / "square_plus_line_order" / "233403.json"


def test_square_leads_when_its_cell_is_scanned_first():
    cells = {(5, 3), (5, 4), (6, 3), (6, 4), (6, 5)}
    assert ms._square_plus_line_cells(cells) == [(5, 3), (5, 4), (6, 4), (6, 3), (6, 5)]


def test_run_leads_when_its_cell_is_scanned_first():
    cells = {(2, 0), (3, 0), (4, 0), (3, 1), (4, 1)}
    assert ms._square_plus_line_cells(cells) == [(2, 0), (3, 0), (4, 0), (3, 1), (4, 1)]


def test_recorded_miss_is_exact():
    from refill_monitor import check_transition

    pair = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
