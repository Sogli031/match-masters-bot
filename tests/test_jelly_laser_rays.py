"""Jelly SE in Laser Matches: the rays leave the swipe's own matches on the
board before the jelly repaints (LightsabersBoard.AfterPerformedSwap).

Recording Debug/research 20261111_205245_laser-matches: final-use jelly moves
7 of 8 exact with it, 0 with rays from the repainted blob (the simulator
cleared 1-5 cells too many). Fixtures are copied from it.
"""
from pathlib import Path

import pytest

from refill_monitor import check_transition
from tools.analyze_research import load, observed, try_transition

FIXTURES = Path(__file__).parent / "fixtures" / "jelly_laser"


@pytest.mark.parametrize("index", [4, 7, 17])
def test_final_use_jelly_swipe_replays_exactly(index):
    _, capture = load(FIXTURES / f"{index:03}.json")
    after, _ = load(FIXTURES / f"{index + 1:03}.json")
    matches, closest, reasons = try_transition(capture, observed(after))
    assert matches, (closest, reasons)


def test_renewal_move_board_is_exact_with_the_recorded_zone_trace():
    before, _ = load(FIXTURES / "003.json")
    after, _ = load(FIXTURES / "004.json")
    result = check_transition(before, after)
    assert result["verdict"] == "ok", result
