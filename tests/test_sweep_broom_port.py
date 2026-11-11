"""Recorded Sweep SE broom swipes and match shapes."""
import json
from pathlib import Path

import pytest

import move_strategy as ms

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_054854_column-mania"


@pytest.mark.skipif(not RECORDING.is_dir(), reason="broom recording not present")
@pytest.mark.parametrize(
    ("index", "start", "target", "direction"),
    [(3, [3, 0], [3, 1], "right"), (22, [3, 0], [2, 0], "up")],
)
def test_broom_swipe_replays_exactly(monkeypatch, index, start, target, direction):
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from, grid, observed
    monkeypatch.setattr(ms, "SWEEP_EXACT_PORTED", True)
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    capture = capture_from(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    result = sim.step(lab, {"kind": "swap", "start": start, "target": target, "direction": direction})
    assert result["supported"], result.get("reason")
    want = observed(after)
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    rng = state["engine_refill"].rng.to_capture()
    assert rng == {key: want["rng_state"][key] for key in rng}


def test_broom_swipe_is_unpredictable_with_port_disabled(monkeypatch):
    import refill_monitor
    monkeypatch.setattr(ms, "SWEEP_EXACT_PORTED", False)
    board = lambda brooms: {"special_board": [[ms.SPECIAL_SWEEP_SE_BROOM] * brooms + [0] * (3 - brooms)]}
    assert refill_monitor._broom_swiped(board(2), board(1))
    assert not refill_monitor._broom_swiped(board(1), board(1))


BULLSEYE = Path(__file__).resolve().parent / "fixtures/broom_bullseye"


@pytest.mark.parametrize(
    ("recording", "index", "start", "target", "direction"),
    [("", 8, [4, 0], [5, 0], "down"),     # row-5 three over a row-6 six
     ("", 21, [6, 2], [5, 2], "up"),      # split L; a T of another colour stays a bomb
     ("", 30, [5, 2], [4, 2], "up"),      # split L; lightning on the 6-row's first cell
     ("20261109_160222", 3, [4, 0], [4, 1], "right"),
     ("20261109_160222", 20, [3, 0], [2, 0], "up"),    # short L stays a bomb
     ("20261109_160222", 25, [0, 5], [1, 5], "down"),  # short L with no other combo
     ("20261109_160222", 31, [2, 6], [2, 5], "left"), # single swept run still draws twice
     ("20261109_154641", 5, [6, 3], [6, 4], "right"),
     ("20261109_154641", 14, [0, 6], [0, 5], "left"), # sweeps a lightning and fires another
     ("20261109_154641", 17, [5, 4], [5, 3], "left"),
     ("20261109_154641", 25, [4, 6], [4, 5], "left"),
     ("20261109_161238", 4, [5, 6], [6, 6], "down"),
     ("20261109_161238", 14, [0, 2], [0, 1], "left"), # a target crosses the broom's hole
     ("20261109_161238", 18, [6, 0], [5, 0], "up"),
     ("20261109_161238", 25, [6, 0], [5, 0], "up"),
     ("20261109_161238", 33, [6, 0], [6, 1], "right"),
     ("20261109_161238", 37, [4, 1], [4, 0], "left"),
     ("20261109_161238", 41, [1, 1], [1, 2], "right"),
     ("20261109_161238", 46, [6, 4], [6, 5], "right")],
)
def test_bullseye_broom_first_layer_replays_exactly(monkeypatch, recording, index, start, target, direction):
    """Bullseye Bash broom swipes, including chained lightning."""
    from strategy_lab import simulation as sim
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from, grid, observed
    before, after = (json.loads((BULLSEYE / recording / f"{i:03d}.json").read_text(encoding="utf-8"))
                     for i in (index, index + 1))
    capture = capture_from(before)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    result = sim.step(lab, {"kind": "swap", "start": start, "target": target, "direction": direction})
    assert result["supported"], result.get("reason")
    want = observed(after)
    state = result["state"]
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    rng = state["engine_refill"].rng.to_capture()
    assert rng == {key: want["rng_state"][key] for key in rng}


def test_split_line_combos_breaks_an_l_into_its_runs():
    l_shape = ms.MatchGroup(frozenset({(0, c) for c in range(1, 7)} | {(1, 6), (2, 6)}), 2, "five")
    runs = ms._split_line_combos([l_shape])
    assert sorted(len(m.cells) for m in runs) == [3, 6]
    assert {m.kind for m in runs} == {"three", "five"}


def test_drillin_down_broom_replays_without_drilling_or_extra_rocket(monkeypatch):
    from simulator_capture import lab_move
    from strategy_lab import simulation
    from tools.analyze_research import capture_from, grid

    path = Path(__file__).resolve().parent / "fixtures/drill_down_broom.json"
    replay = json.loads(path.read_text(encoding="utf-8"))
    lab = lab_move(capture_from(replay["before"]))
    monkeypatch.setattr(simulation, "PREFIX_MODES", simulation.PREFIX_MODES | {lab["mode"]})
    result = simulation.step(lab, replay["action"])

    assert result["supported"], result.get("reason")
    state, expected = result["state"], replay["after"]
    assert grid(state["board"]) == expected["board"]
    assert grid(state["special_board"]) == expected["special_board"]
    rng = state["engine_refill"].rng.to_capture()
    assert rng == {key: expected["rng"][key] for key in rng}
