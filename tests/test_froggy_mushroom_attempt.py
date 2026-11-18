"""Froggy Fu on Multiplier Mushrooms: each entrance attempt's points carry the
mushroom multiplier (research 20261118_223923 001->002, the game took attempt 5)."""
import json
from pathlib import Path

FRAMES = Path(__file__).resolve().parent / "fixtures" / "froggy_mushrooms"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def test_activation_picks_the_games_attempt():
    from simulator_capture import lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from, grid, observed
    lab = lab_move(capture_from(_record("001")), thresholds=None)
    lab["perks"] = {}
    result = sim.step(lab, {"kind": "booster"})
    assert result["supported"], result.get("reason")
    entrance = next(e for e in result["events"] if e["type"] == "froggy_entrance")
    assert entrance["attempt"] == 4     # zero-based: the game's attempt 5
    state, want = result["state"], observed(_record("002"))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
