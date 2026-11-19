"""Vertical Rush in the exact planner: the swipe's own combos move the multiplier.

Before, the planner's simulator kept no multiplier for board 23, so a vertical
and a horizontal match were worth the same and the multiplier slid 10 -> 7
(research 20261119_090048). The game moves it before paying the move.
"""
import json
from pathlib import Path

import pytest

from simulator_capture import lab_move
from strategy_lab.simulation import step
from tools.analyze_research import capture_from

FIXTURES = Path(__file__).parent / "fixtures" / "vertical_rush_multiplier"
DIRECTIONS = {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}


def _me(record):
    return next(p for p in record["snapshot_state"]["players"] if p.get("player_type") == 0)


@pytest.mark.parametrize("before, after, multiplier", [
    ("007", "008", 10), ("012", "013", 9),
    ("056", "057", 12),     # a vertical and a horizontal three: +1, not 0
    ("058", "059", 11),     # two horizontal threes: -1, not -2
])
def test_swipe_moves_the_multiplier_before_it_pays(before, after, multiplier):
    a = json.loads((FIXTURES / f"{before}.json").read_text())
    b = json.loads((FIXTURES / f"{after}.json").read_text())
    played = b["refill_input"][2]
    start, target = played["start"], played["target"]
    result = step(lab_move(capture_from(a)), {
        "start": start, "target": target,
        "direction": DIRECTIONS[(target[0] - start[0], target[1] - start[1])]})
    assert _me(b)["score_multiplier"] == multiplier
    assert result["state"]["score_multiplier"] == multiplier
    assert round(result["score_gain"]) == _me(b)["score"] - _me(a)["score"]
