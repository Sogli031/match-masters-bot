"""Sweep SE broom swipe port (2026-11-07 Column Mania, pvpMode Solo)."""
import json
from pathlib import Path

import pytest

import move_strategy as ms

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_054854_column-mania"


@pytest.mark.skipif(not RECORDING.is_dir(), reason="broom recording not present")
def test_broom_swipe_22_replays_exactly(monkeypatch):
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from, grid, observed
    monkeypatch.setattr(ms, "SWEEP_EXACT_PORTED", True)
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (22, 23))
    capture = capture_from(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    result = sim.step(lab, {"kind": "swap", "start": [3, 0], "target": [2, 0], "direction": "up"})
    want = observed(after)
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]


def test_broom_swipe_is_unpredictable_until_fully_ported():
    import refill_monitor
    assert not ms.SWEEP_EXACT_PORTED
    board = lambda brooms: {"special_board": [[ms.SPECIAL_SWEEP_SE_BROOM] * brooms + [0] * (3 - brooms)]}
    assert refill_monitor._broom_swiped(board(2), board(1))
    assert not refill_monitor._broom_swiped(board(1), board(1))
