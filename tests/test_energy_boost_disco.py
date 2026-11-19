"""Energy Boost + a disco ball swiped with a plain piece.

The swipe is free, so the disco's move refund adds nothing, and the wipe is the
swipe's own effect, so it charges the meter. Before: the plan predicted moves +1
and no charge, the game kept the moves and filled the meter, and the carried
line was dropped for a new 90 s first plan (Vertical Rush 2026-11-19 09:02).
"""
import json
from pathlib import Path

import pytest

import square_solo_live as sq
from simulator_capture import lab_move
from strategy_lab.simulation import PERK_ENERGY_BOOST, step
from tools.analyze_research import capture_from

FIXTURES = Path(__file__).parent / "fixtures" / "energy_boost_disco"
DIRECTIONS = {(-1, 0): "up", (1, 0): "down", (0, -1): "left", (0, 1): "right"}


@pytest.mark.parametrize("name", ["vertical_rush", "lightning"])
def test_energy_boost_disco_matches_the_game(name):
    before_file, after_file = sorted(FIXTURES.glob(f"{name}_*.json"))
    before = json.loads(before_file.read_text())
    after = json.loads(after_file.read_text())
    lab = lab_move(capture_from(before))
    lab["perks"] = {PERK_ENERGY_BOOST: 1}
    follow = after["refill_input"][2]["follow_up"]
    delta = (follow["target"][0] - follow["start"][0], follow["target"][1] - follow["start"][1])
    result = step(lab, {"kind": "energy_boost", "start": follow["start"], "target": follow["target"],
                        "direction": DIRECTIONS[delta]})
    assert result["supported"]
    game = lab_move(capture_from(after))
    game["perks"] = {}
    assert sq._plan_key(result["state"]) == sq._plan_key(game)
