"""Square Match with the Cleo booster, measured by the refill check (research 2026-11-13).

* 160012_003: a bomb dragged onto the booster's Cleo (square board 0, the
  wide clone branch with square matches on).
* 160012_004: the clone cascade fires a resting crosshair and a bomb; the
  destroy pass walks x-major, so the crosshair at (3,2) goes before the bomb
  at (4,3) and draws other targets.
* 160414_000: two bombs merged (value 12) next to a Cleo figure: the figure is
  not damageable, the merge's start slot is empty for the Lightning and the
  four crosshairs it sets off, and a crosshair never picks the Cleo.
* 160012_021: a bomb partner with the prevention drawn (Chance(50) true): the
  clone avoids the colour whose conversion makes an extra-move combo.

Since 2026-11-13 17:10 the planner takes this branch too (every Cleo swipe the
bot played that day replayed exact: Square Match 18 of 18, Super Sized 3 of 3);
Color Crush stays with the refill check (``measure_only``).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "square_match_cleo"


@pytest.mark.parametrize("name", ["160012_003", "160012_004", "160414_000", "160012_021"])
def test_recorded_square_match_move_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
