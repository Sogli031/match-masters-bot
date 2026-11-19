"""Disco ball swiped with a plain piece, a Lightning in the wiped colour.

Recorded Lightning Strike refill misses 2026-11-19 005215 and 005603: the swap
trace shows a merge (merge_outcome). Every Lightning the wipe fires draws from
a pool where the ball's old slot is empty and the slot it landed on holds a
piece. With the simulator's swapped board (piece on the old slot, ball on the
new one, which the pool skips) the count was the same but one pick slid a cell.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "disco_lightning_merge"


@pytest.mark.parametrize("name", ["005215", "005603"])
def test_recorded_disco_merge_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


def test_plain_disco_swipe_returns_the_move():
    """Lightning Strike research 20261119_010218 005 -> 006: a ball swiped with
    a plain piece, moves 7 -> 7. The simulator spent it (7 -> 6) and the live
    planner dropped its line for a new 70 s first plan."""
    import tools.analyze_research as ar
    from simulator_capture import lab_move
    from strategy_lab.simulation import step

    pair = json.loads((FIXTURES / "010218_005.json").read_text(encoding="utf-8"))
    detail = pair["after"]["refill_input"][2]
    lab = lab_move(ar.capture_from(pair["before"]))
    lab["perks"] = {}
    result = step(lab, {"kind": "swap", "start": detail["start"], "target": detail["target"],
                        "direction": detail["direction"]})
    assert result["state"]["turn_state"]["remaining_moves"] == pair["after"]["profile"]["state"]["moves"] == 7
