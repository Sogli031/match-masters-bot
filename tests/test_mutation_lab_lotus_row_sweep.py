"""Mutation Lab (mutation 22, destroyRowOnHorizontalMatch) with a Froggy lotus:
the cluster sweeps only the row of its special, and only when a horizontal match
fired the lotus; a straight match the pull formed elsewhere sweeps its own row
(`froggy_line_destruction_matches`).

Recorded 2026-11-11 14:21-14:25 (Debug/refill_misses): sweeping every row of the
cluster set off specials the game left standing; 0 of 7 lotus moves were exact,
5 of 7 are now. Open: 142210 and 142528, where the swipe's second match
(assignedSecondary) is pulled to other cells than in the game.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MISSES = ROOT / "Debug" / "refill_misses"
EXACT = [
    "20261111_142124_400747_mutation-lab-solo-mode",
    "20261111_142130_801142_mutation-lab-solo-mode",
    "20261111_142337_500949_mutation-lab-solo-mode",
    "20261111_142408_553964_mutation-lab-solo-mode",
    "20261111_142559_310985_mutation-lab-solo-mode",
]


@pytest.mark.parametrize("name", EXACT)
def test_lotus_move_replays_exactly(name):
    folder = MISSES / name
    if not (folder / "001.json").exists():
        pytest.skip("Mutation Lab recording is not on this machine")
    from tools.trace_refill_miss import trace

    out = trace(folder)
    assert "froggy_lotus_gather" in out
    assert "razlicita polja (red, kol, igra, sim): []" in out
    assert "razliciti specijali (red, kol, igra, sim): []" in out
