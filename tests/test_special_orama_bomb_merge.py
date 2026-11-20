"""Special O'Rama: a bomb dragged onto a bomb still makes the four's special.

Frames from Debug/refill_misses/20261120_061014_497874_special-o-rama: the
swipe lines up a colour-4 row on (3,0)-(3,3) while both bombs go off, and the
game keeps the row rocket it made there -- it falls to (5,1). The simulator's
special+special path kept its own branch (bomb+bomb), so ``merge_cells`` stayed
None and the four's special was never created: one refill hole too many, board
11 cells off, RNG +7, logged as a miss.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FRAMES = Path(__file__).resolve().parent / "fixtures" / "special_orama_bomb_merge"


def test_bomb_onto_bomb_four_is_exact():
    from tools.replay_one_to_one import load, replay

    rec_a, cap_a = load(FRAMES / "000.json")
    rec_b, _ = load(FRAMES / "001.json")
    got = replay(rec_a, cap_a, rec_b)
    assert "skip" not in got, got
    assert got["cells"] == 0, got
    assert got["specials"] == 0, got
    assert got["rng"][0] == got["rng"][1], got
    assert got["moves"][0] == got["moves"][1], got
