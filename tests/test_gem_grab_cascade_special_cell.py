"""Gem Grab master league (specialsAutoExplode): where a cascade special goes.

Three rules, each from refill_misses 2026-11-11 (crystal-cave-master-league):

- a crystal in the combo is skipped by the cell draw (201813, 201829, 201918);
- an L/T keeps the x-major scan, not the row+column list (200834, 201152,
  201415, 202506, 202538);
- a forced auto_explode combo holds no draw rank (202726).

All nine replay exactly; none did before.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MISSES = ROOT / "Debug" / "refill_misses"


@pytest.mark.parametrize("stamp", [
    "20261111_200834_574908", "20261111_201152_951128", "20261111_201415_538801",
    "20261111_201813_316085", "20261111_201829_598035", "20261111_201918_740079",
    "20261111_202506_735482", "20261111_202538_530197", "20261111_202726_864476",
])
def test_cascade_special_cell_replays_exactly(stamp):
    folder = MISSES / f"{stamp}_crystal-cave-master-league"
    if not (folder / "001.json").exists():
        pytest.skip("Gem Grab recording is not on this machine")
    from tools.trace_refill_miss import trace

    out = trace(folder)
    assert "razlicita polja (red, kol, igra, sim): []" in out
    assert "razliciti specijali (red, kol, igra, sim): []" in out
    game, sim = out.split("RNG igra/sim: ")[1].split("\n")[0].split(" / ")
    assert game == sim
