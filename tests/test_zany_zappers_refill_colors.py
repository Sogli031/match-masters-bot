"""Zany Zappers (ZanyZappersBoard, 33): a refilled zapper skips the players'
colours, as on Color Crystals.

refill_misses 2026-11-11 143601: without it the zapper shuffle drew one
candidate more (a red hole), the RNG ran one ahead and the new zapper landed
one cell off; with it the move replays exactly.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FOLDER = ROOT / "Debug" / "refill_misses" / "20261111_143601_678654_zany-zappers"


def test_zapper_refill_skips_player_colours():
    if not (FOLDER / "001.json").exists():
        pytest.skip("Zany Zappers recording is not on this machine")
    from tools.trace_refill_miss import trace

    out = trace(FOLDER)
    assert "RNG igra/sim: 1830 / 1830" in out
    assert "razlicita polja (red, kol, igra, sim): []" in out
    assert "razliciti specijali (red, kol, igra, sim): []" in out
