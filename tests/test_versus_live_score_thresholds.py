"""Versus refill thresholds read the score at refill time.

FillAllEmptySlots computes the adaptive prevention thresholds from the score
difference when it runs, after DestroyMatches has already paid the action's
waves. Mighty Mushrooms refill_misses 2026-11-20 041307: a Froggy Fu lotus
gather took the player from 2029 to 3154 (opponent 2343); with the captured
score the simulator kept 0/25 and drew 140 too many, with the live score it is
100/100 and the move replays exactly (board, specials, RNG 2419).
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MISS = ROOT / "Debug" / "refill_misses" / "20261120_041307_585838_mighty-mushrooms"


def _before():
    if not MISS.is_dir():
        pytest.skip("recording not on this machine")
    return json.loads((MISS / "000.json").read_text(encoding="utf-8"))


def test_live_points_flip_the_thresholds():
    from simulator_capture import fill_all_empty_slots_thresholds

    profile = _before()["profile"]
    start = fill_all_empty_slots_thresholds(profile, 2)
    assert (start["match"], start["combo"]) == (0, 25)          # 314 behind
    live = fill_all_empty_slots_thresholds(profile, 2, 1125)
    assert (live["match"], live["combo"]) == (100, 100)


def test_no_move_left_flips_the_match_threshold_only():
    """Answer 15: with Moves == 0 the match threshold takes the negated difference
    and the moves-dependent slope; the combo threshold keeps the plain one."""
    from simulator_capture import fill_all_empty_slots_thresholds

    profile = _before()["profile"]
    ahead = fill_all_empty_slots_thresholds(profile, 0, 1125)
    assert (ahead["match"], ahead["combo"]) == (0, 100)


def test_lotus_gather_replays_exactly():
    import refill_monitor

    before = _before()
    after = json.loads((MISS / "001.json").read_text(encoding="utf-8"))
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "ok", result


@pytest.mark.parametrize("name", ["20261120_003034_062648_mighty-mushrooms",
                                  "20261120_052438_295640_mighty-mushrooms",
                                  # turn end: thresholds with 0 moves left, then RevertLotuses (+1 draw)
                                  "20261120_044447_084520_mighty-mushrooms",
                                  # live moves (GetScoreDifference turnsLeft parity)
                                  "20261119_235847_405397_mighty-mushrooms"])
def test_lotus_gather_walks_the_pulled_cluster_first(name):
    """The gather's destroy walk follows GetPulledClusterPositionsList (ring, targets in
    pull order, lotus): in 003034 the crosshair (2,1) fires before the Lightning (2,0)."""
    import refill_monitor

    miss = ROOT / "Debug" / "refill_misses" / name
    if not miss.is_dir():
        pytest.skip("recording not on this machine")
    before = json.loads((miss / "000.json").read_text(encoding="utf-8"))
    after = json.loads((miss / "001.json").read_text(encoding="utf-8"))
    result = refill_monitor.check_transition(before, after)
    # 044447 ends the turn: the board is exact, the monitor's move counter
    # still reads the old turn's 0 where the game already dealt the next 2.
    allowed = ("ok", "resources") if name.startswith("20261120_044447") else ("ok",)
    assert result["verdict"] in allowed, result
