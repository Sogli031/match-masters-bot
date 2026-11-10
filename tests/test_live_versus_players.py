"""Live Square Match Versus: the refill thresholds need both players' spawnBonus.

The periodic snapshot leaves spawn_bonus null; the memory profile has it.
2026-11-10 02:20 every live move fell back to the base thresholds while the
recorder (manual dump) resolved the Versus formula.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulator_capture import resolve_refill_overrides, versus_adaptive_thresholds
from square_solo_live import _profile_players

FRAME = Path(__file__).resolve().parent / "fixtures" / "square_versus_players" / "000.json"


def _live_snapshot(record):
    players = []
    for player in record["profile"]["players"]:
        model = player["model"]
        players.append({"index": model["index"], "player_type": player["player_type"],
                        "score": model["score"], "spawn_bonus": None, "slot_type": model["slotType"]})
    return {"state": {"players": players}}


def test_missing_spawn_bonus_comes_from_the_memory_profile():
    record = json.loads(FRAME.read_text(encoding="utf-8"))
    profile = copy.deepcopy(record["profile"])
    snapshot = _live_snapshot(record)

    profile["players"] = _profile_players(snapshot)
    assert versus_adaptive_thresholds(profile) is None   # the 02:20 fallback

    profile["players"] = _profile_players(snapshot, record["profile"]["players"])
    assert versus_adaptive_thresholds(profile) is not None
    assert resolve_refill_overrides(profile)["resolved"]


def test_snapshot_values_win_over_the_memory_profile():
    record = json.loads(FRAME.read_text(encoding="utf-8"))
    snapshot = _live_snapshot(record)
    snapshot["state"]["players"][0]["spawn_bonus"] = 7
    players = _profile_players(snapshot, record["profile"]["players"])
    assert players[0]["model"]["spawnBonus"] == 7
