"""Cascade L/T that also closes a 2x2 square: the L listing, then the square's extra cell.

Square Match refill_misses 2026-11-14 212812: row 3 cols 1-3, column 1 rows
3-5 and (4, 2). Placement draw % 6 == 5; the game put the bomb on (4, 2), the
x-major scan on (3, 3), and every refill after that was a different board.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

FIXTURE = ROOT / "tests" / "fixtures" / "square_match_lt" / "212812.json"
SHAPE = frozenset({(3, 1), (3, 2), (3, 3), (4, 1), (4, 2), (5, 1)})


def test_square_cell_comes_after_the_l_listing(monkeypatch):
    monkeypatch.setattr(ms, "_ENGINE_PEEK_DRAWS", lambda n: [477072953] * n)
    match = ms.MatchGroup(SHAPE, 3, "l")
    assert ms._created_special_cell(match, (), [match]) == (4, 2)


def test_recorded_miss_is_exact():
    from refill_monitor import check_transition

    pair = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
