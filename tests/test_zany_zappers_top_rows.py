"""Zany Zappers (ZanyZappersBoard, 33): a refilled zapper only lands at y < 4.

ZanyZappersBoard.GetConvertPoints 0x59c9664 filters with <>c.b__13_1
0x59c99c4 (point.y < 4, MAX_ROW_FILL) and intersects with the refill's hole
list, so the shuffle runs over the top-four-row holes in row order.

refill_misses 2026-11-11: 192204 (one zapper, game drew one key fewer per
lower-row hole) and 192306 (three zappers in rows 0 and 1) replay exactly.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MISSES = ROOT / "Debug" / "refill_misses"


@pytest.mark.parametrize("name", [
    "20261111_192204_112898_zany-zappers",
    "20261111_192306_783004_zany-zappers",
])
def test_zapper_spawns_in_top_rows(name):
    folder = MISSES / name
    if not (folder / "001.json").exists():
        pytest.skip("Zany Zappers recording is not on this machine")
    from tools.trace_refill_miss import trace

    out = trace(folder)
    assert "razlicita polja (red, kol, igra, sim): []" in out
    assert "razliciti specijali (red, kol, igra, sim): []" in out
    game, sim = out.split("RNG igra/sim: ")[1].split("\n")[0].split(" / ")
    assert game == sim
