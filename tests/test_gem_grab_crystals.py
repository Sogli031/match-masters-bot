"""Gem Grab (CrystalCaveBoard, boardModelName 3) in the exact refill (2026-11-11).

A crystal is BoardSpecial (SlotValue 16) on a purple piece, its number in
SlotModel.score. The refill carries it like a tile; CrystalCaveBoard.onMoveStart
0x5983b80 then tops the crystals up to MaxBoardSpecialTiles: one Chance, then
ConvertSlots 0x59836d4 -> GetSlotPrioritize over plain purple pieces, topmost
row first, each new crystal numbered nextBoardSpecialScore++.

Fixtures from research 20261111_163705_crystal-cave-master-league:
- row_*   (002->003): one crystal replaced, from the top row of purple pieces;
- order_* (005->006): two replaced, numbered in pick order (27 before 28);
- rest_*  (008->009): the top purple row holds one, the second comes from the
  shuffled rest of the board.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "gem_grab"


@pytest.mark.parametrize("name, move", [
    ("row", "red 4 kol 5 -> red 4 kol 6"),
    ("order", "red 5 kol 1 -> red 5 kol 2"),
    ("rest", "red 5 kol 0 -> red 5 kol 1"),
])
def test_gem_grab_move_replays_exactly(monkeypatch, name, move):
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
    assert not state["engine_refill"].is_approximate


def test_full_board_rolls_nothing():
    import move_strategy as ms
    from engine_refill import EngineRefill
    from tools.analyze_research import capture_from

    record = json.loads((FRAMES / "row_000.json").read_text(encoding="utf-8"))
    capture = capture_from(record)
    model = EngineRefill.from_profile(capture["profile"], thresholds={})
    board = capture["simulator_input"]["board"]
    special = capture["simulator_input"]["special_board"]
    assert sum(ms.is_purple_gem_special(v) for row in special for v in row) == 2
    before = model.rng.counter
    assert model.crystal_move_start(board, special) == [list(row) for row in special]
    assert model.rng.counter == before
