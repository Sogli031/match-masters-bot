"""Mighty Mushrooms: the refill spawns two tile types, mushroom 19 and bomb 6.

RandomSpawnSpecialSlots 0x5a04c2c shuffles the tile types with the game RNG
(ArrayExtensions.Shuffle 0x3c137a0) before ProcessSpecialTile runs on each.
Without that shuffle no recorded move matched (the RNG ran 2 draws short and a
mushroom spawned that the game never made); with it 34 of 34 do
(Debug/research 20261107_155618_mighty-mushrooms, 2026-11-07).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "mighty_mushrooms_refill.json"
RESEARCH = ROOT / "Debug" / "research" / "20261107_155618_mighty-mushrooms"


def _allow_mode(monkeypatch, record):
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(record["profile"]).value})


def test_two_tile_types_are_shuffled_before_spawning(monkeypatch):
    """007->008: no mushroom spawns and the RNG ends exactly where the game's did."""
    from refill_monitor import check_transition

    pair = json.loads(FIXTURE.read_text(encoding="utf-8"))
    _allow_mode(monkeypatch, pair["before"])
    assert (check_transition(pair["before"], pair["after"]) or {}).get("verdict") == "ok"


def test_single_tile_type_draws_no_shuffle():
    """One type: Shuffle returns the list unchanged, no draw (hearts, bombs, mushrooms)."""
    from engine_rng import EngineRNG

    rng = EngineRNG.from_seed(1234)
    before = rng.counter
    assert rng.shuffled([("19", {})]) == [("19", {})]
    assert rng.counter == before


def test_recorded_mighty_mushrooms_session_replays(monkeypatch):
    from refill_monitor import check_transition

    files = sorted(RESEARCH.glob("[0-9][0-9][0-9].json"))
    if not files:
        pytest.skip("Mighty Mushrooms recording is not on this machine")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    _allow_mode(monkeypatch, records[0])
    verdicts = [(check_transition(records[i - 1], records[i]) or {}).get("verdict")
                for i in range(1, len(records))]
    assert verdicts.count("ok") >= 30
    # 031->032 (moves 1 -> 5) is the turn change: the refill for the next turn
    # is a separate branch, and the board before it was never read.
    misses = [i for i, verdict in enumerate(verdicts, 1) if verdict == "miss"]
    moves = lambda record: (record.get("snapshot_state") or {}).get("moves")
    assert all(moves(records[i]) > moves(records[i - 1]) for i in misses)
