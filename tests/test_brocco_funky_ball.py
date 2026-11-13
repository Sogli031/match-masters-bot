"""Brocco's ball on a Funky Tiles marker: the marker under the ball's start cell does not blast.

Recorded Funky Tiles 2026-11-13 (research 20261113_150917, with the engine's
swap trace). The ball dragged off a marker wipes its colour, the piece swapped
onto the marker included, but the game shows no Funky blast there: 044, 113
and 134 are exact only without it. 004 is a ball move off a plain cell (it was
exact before and stays so). A marker the wipe takes elsewhere still fires
(refill_misses 131758 / 131900, test_funky_disco_wave).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "brocco_funky_ball"


@pytest.mark.parametrize("name", ["004", "044", "113", "134"])
def test_recorded_ball_move_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
