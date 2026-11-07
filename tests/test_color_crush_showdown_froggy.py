"""Color Crush in Showdown with Froggy Fu (recorded 2026-11-07, 16:32-16:33).

* Showdown is pvpMode 2 with one player on the board: IsSingleplayerBoard, so
  red is wiped like any colour. The refill check read pvpMode 1 only and kept
  red inert; the game wiped every red (163217).
* A swipe that fires a lotus wipes no colour: the gather replaces the swap's
  own resolution. With the wipe the simulator cleared 5 extra cells (163238).
Both read as refill misses before; both are exact now.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAIRS = json.loads((ROOT / "tests" / "fixtures" / "color_crush_showdown_froggy.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["163217_694035", "163238_149515"])
def test_recorded_color_crush_showdown_moves_are_exact(monkeypatch, name):
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    pair = PAIRS[name]
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(pair["before"]["profile"]).value})
    assert (check_transition(pair["before"], pair["after"]) or {}).get("verdict") == "ok"


def test_showdown_board_counts_as_single_player():
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from

    record = PAIRS["163217_694035"]["before"]
    assert record["profile"]["rules"]["pvpMode"] == 2
    assert lab_move(capture_from(record))["single_player_board"] is True
