"""Plunder Pirates chest timing in the exact refill (2026-11-09).

- A chest on the bottom row is collected only once the board has no matches;
  its column then gets a refill of its own (settle_*, refill_misses
  20261109_192641).
- The same holds after a disco swipe and the other special paths (disco_*,
  refill_misses 20261107_050611: the chest used to stay on the floor).
- The chest's spawnChance is rolled once, before the cell shuffle (chance_*,
  research 20261107_233829 008->009).
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "plunder_chest"


@pytest.mark.parametrize("name, move", [
    ("settle", "red 6 kol 2 -> red 7 kol 2"),
    ("disco", "red 6 kol 0 -> red 6 kol 1"),
    ("chance", "red 2 kol 1 -> red 3 kol 1"),
])
def test_chest_move_replays_exactly(monkeypatch, name, move):
    from strategy_lab import planner
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from, grid, observed
    files = sorted(FRAMES.glob(f"{name}_*.json"))
    before, after = (json.loads(f.read_text(encoding="utf-8")) for f in files)
    capture = capture_from(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    action = next(a for a in planner.actions(lab) if planner.describe(a) == move)
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    want = observed(after)
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
