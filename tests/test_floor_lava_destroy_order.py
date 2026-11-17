"""The Floor Is Lava: erupted columns lead the swipe's destroy pass.

Recorded refill_misses 2026-11-17 (the-floor-is-lava, Charles), both exact now:

* 115710: a horizontal (3,4) and a knight (6,5) in the erupted columns fire
  before the vertical (5,3) of the swipe's own three.
* 130953: a horizontal swiped into a four fired before the knight (2,3) in
  the erupted column 3 and took 10 draws too many; the lava leads even the
  swiped specials (SWAP_SPECIALS_FIRST).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "floor_lava_order"


@pytest.mark.parametrize("name", ["115710", "130953"])
def test_recorded_floor_lava_move_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert (check_transition(pair["before"], pair["after"]) or {}).get("verdict") == "ok"
