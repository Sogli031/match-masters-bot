"""Funky Tiles master league: the refill spawns Zany Zappers (SlotValue 17).

The simulator splits a zapper by hit points (26 two left, 25 one); both are
engine 17 and a fresh one has two. Funky cells are a board-cell layer
(CellModel.cellType 3) the research recorder now keeps as ``cell_types``; a
recording without it is not checkable instead of a false miss.
Recorded 2026-11-07 18:02 (Debug/research 20261107_180231): 003->004 exact.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAIR = json.loads((ROOT / "tests/fixtures/funky_tiles_zapper_refill.json").read_text(encoding="utf-8"))


def _allow(monkeypatch):
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(PAIR["before"]["profile"]).value})


def test_zapper_maps_both_ways():
    import engine_refill

    assert engine_refill.SIM_SPECIAL_TO_ENGINE[25] == engine_refill.SIM_SPECIAL_TO_ENGINE[26] == 17
    assert engine_refill.ENGINE_SPECIAL_TO_SIM[17] == 26


def test_recorded_zapper_refill_is_exact(monkeypatch):
    from refill_monitor import check_transition

    _allow(monkeypatch)
    assert (check_transition(PAIR["before"], PAIR["after"]) or {}).get("verdict") == "ok"


def test_funky_board_without_cell_types_is_not_checkable(monkeypatch):
    from engine_refill import UnsupportedRefill
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from

    record = copy.deepcopy(PAIR["before"])
    record.pop("cell_types")
    with pytest.raises(UnsupportedRefill, match="Funky Tiles"):
        lab_move(capture_from(record))
    assert lab_move(capture_from(PAIR["before"]))["funky_cells"] == [(2, 2), (2, 3)]
