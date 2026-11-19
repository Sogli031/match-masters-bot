"""Versus refill thresholds keep the spawnBonus correction under explicit overrides.

Mighty Mushrooms (refillLogicOverride 90/100, opponent spawnBonus -20), research
2026-11-19: while our turn goes on the game prevents with 70/80
(FillAllEmptySlots 0x5a08e00/0x5a08e44: match - bonus, combo -bonus while
moves >= 1); a refill after the turn's last move counts the opponent as
current with 0 moves: 100/80. With 90/100 these moves missed and the round
plan was searched again.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "versus_spawn_bonus"
CASES = [
    "mighty_162620_019",   # turn goes on: match must be 70
    "mighty_162620_020",   # turn goes on (extra move): combo must be 80
    "mighty_161717_005",   # last move: match 100
    "mighty_162921_007",   # last move: combo 80
]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _after(name):
    prefix, number = name.rsplit("_", 1)
    return f"{prefix}_{int(number) + 1:03d}"


def test_resolved_thresholds():
    from simulator_capture import resolve_refill_overrides
    resolved = resolve_refill_overrides(_record("mighty_162620_019")["profile"])
    assert resolved["prevention_thresholds"]["match"] == 70
    assert resolved["prevention_thresholds"]["combo"] == 80
    assert resolved["turn_end_thresholds"]["match"] == 100
    assert resolved["turn_end_thresholds"]["combo"] == 80


@pytest.mark.parametrize("before", CASES)
def test_move_replays_exactly(before, monkeypatch):
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import simulation as sim
    from tools.analyze_research import capture_from, grid, observed
    after = _record(_after(before))
    capture = capture_from(_record(before))
    state = lab_move(capture, thresholds=None)
    state["perks"] = {}
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    move = after["refill_input"][2]
    result = sim.step(state, {"kind": "swap", "start": move["start"], "target": move["target"],
                              "direction": move["direction"]})
    assert result["supported"], result.get("reason")
    want = observed(after)
    assert grid(result["state"]["board"]) == want["board"]
    assert grid(result["state"]["special_board"]) == want["special_board"]
    assert result["state"]["engine_refill"].rng.counter == want["rng"]
