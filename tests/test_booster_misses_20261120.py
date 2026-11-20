"""Booster refill misses of 2026-11-20 that now replay exactly.

foxy_crystal: Mighty Mushrooms, Foxy Roxy SE; a colour crystal takes part in
the paint (engine_foxy.participates), 15 of 15 activations that morning.
froggy_energized: Energized, Froggy Fu; the entrance is picked by the score at
the player's multiplier (simulator_capture.ENERGIZED_BOARD), 11 of 16.
froggy_dustville: Dustville Duel, Froggy Fu with wanted tiles (sim 9) on the board.
swipe_match-and-hatch: two fours, random specials drawn target combo first.
swipe_column-mania: a cascade T + square, the corner listed twice (draw % 7).
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "booster_misses_20261120"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["foxy_crystal", "froggy_energized", "froggy_dustville",
                                  "swipe_match-and-hatch", "swipe_column-mania"])
def test_booster_replays_exactly(name, monkeypatch):
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from, grid, observed
    capture = capture_from(_record(f"{name}_000"))
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    played = _record(f"{name}_001")["refill_input"]
    detail = played[2]
    action = ({"kind": "booster"} if played[1] == "activate_booster" else
              {"kind": "swap", "start": detail["start"], "target": detail["target"],
               "direction": detail["direction"]})
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    want = observed(_record(f"{name}_001"))
    assert grid(result["state"]["board"]) == want["board"]
    assert grid(result["state"]["special_board"]) == want["special_board"]
    assert result["state"]["engine_refill"].rng.counter == want["rng"]
