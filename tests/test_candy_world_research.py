"""Candy World recording 20261113_123727: the candy refill and its matching.

Each pair is one played move; the simulator must reproduce board, specials
and RNG counter. 010->011 (two stacked disco balls) is still open, and the
BroccoBoogie booster steps are not ported.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "Debug" / "research" / "20261113_123727_candy-world-master-league"

pytestmark = pytest.mark.skipif(not FOLDER.is_dir(), reason="recording not on this machine")


# 000-008: first target (candy conversion, every match is special);
# 011: a red disco wipe takes the blue candies; 012: the cascade special
# skips the candy; 015: refilled slots under a candy are not available.
@pytest.mark.parametrize("index", [0, 1, 2, 4, 5, 6, 7, 8, 11, 12, 13, 15, 16])
def test_recorded_candy_world_move_is_exact(index):
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import analyze_research as ar

    before, capture = ar.load(FOLDER / f"{index:03d}.json")
    after, _ = ar.load(FOLDER / f"{index + 1:03d}.json")
    matches, closest, _reasons = ar.try_transition(capture, ar.observed(after))
    assert matches, closest
