"""Mutation Lab: the row sweep fires on every match of the move, and a disco
swipe's first match takes the swap rules (2026-11-07 21:32, Brocco + mutations
22 and 30)."""
import json
from pathlib import Path

import pytest

from refill_monitor import check_transition

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "mutation_lab_lines"


@pytest.mark.parametrize("name", [
    "20261107_213216_620381_mutation-lab-solo-mode",     # disco swipe, then a row
    "20261107_213247_073402_mutation-lab-solo-mode",     # a cascade row sweep
])
def test_recorded_move_replays(name):
    before, after = (json.loads((FIXTURES / name / f).read_text(encoding="utf-8"))
                     for f in ("000.json", "001.json"))
    verdict = check_transition(before, after)
    assert verdict and verdict["verdict"] == "ok", verdict
