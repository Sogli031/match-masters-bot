"""A square made in a cascade leaves its crosshair on cell (draw % 4) clockwise.

The exact refill draws one number per cascade combo; the combo's special goes on
cell ``draw % size``. For a 2x2 square the cells count clockwise from the top
left. In scan order (column, then row) index 3 was the bottom right; the game put
the crosshair bottom left. Recorded Crazy Columns 026->027 (Debug/research
20261107_161715_crazy-columns): draw 1342814139, square rows 4-5 x cols 2-3,
crosshair at (5, 2). Over 17 square-match sessions: 5 moves fixed, none lost.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

FIXTURE = ROOT / "tests" / "fixtures" / "cascade_square_crosshair.json"


def test_cascade_square_counts_its_cells_clockwise(monkeypatch):
    square = ms.MatchGroup(cells=frozenset({(4, 2), (4, 3), (5, 2), (5, 3)}), color=2, kind="square")
    draws = {0: (4, 2), 1: (4, 3), 2: (5, 3), 3: (5, 2)}
    for draw, cell in draws.items():
        monkeypatch.setattr(ms, "_ENGINE_PEEK_DRAWS", lambda count, draw=draw: [draw] * count)
        assert ms._created_special_cell(square, (), (square,)) == cell


def test_recorded_crazy_columns_cascade_square(monkeypatch):
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    pair = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(pair["before"]["profile"]).value})
    assert (check_transition(pair["before"], pair["after"]) or {}).get("verdict") == "ok"
