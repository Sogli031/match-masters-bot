"""Candy World (everyMatchIsSpecial): draw order of cascade specials and Lightning.

Recorded refill_misses 2026-11-13 (candy-world-master-league), all exact now:

* 134046: a cascade first draws every plain three's type, then one placement
  draw per combo, both x-major (types consecutive, not interleaved).
* 134715: the swipe's own threes draw their types with the combo holding the
  dragged piece's target cell first.
* 135234, 135401: a Lightning in that cascade shuffles after the combos'
  placement draws also when the move started with a disco ball, and takes
  every occupied, damageable piece (cells already being destroyed included).
* 133105, 140758: two combos of different colours sharing a candy -- the
  bigger keeps it, the other is no combo (140758 was the first miss of the
  restarted bot).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "candy_world_every_match"


@pytest.mark.parametrize("name", ["133105", "134046", "134715", "135234", "135401", "140758"])
def test_recorded_candy_world_move_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert (check_transition(pair["before"], pair["after"]) or {}).get("verdict") == "ok"
