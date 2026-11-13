"""Vinnie SE heart + Lightning, Lightning + Lightning: merge swaps from the engine's swap trace.

Recorded Color Climb 2026-11-13 (Valentine Vinnie SE), all exact now:

* 144946, 145214 (research, with swap_trace): GetMergeSwapOutcome activates
  both pieces; the heart's colour area comes first, then the Lightning fires
  from the swipe's end cell (GetFireworks ignores the end cell and the heart's
  area). 145214 chains three more Lightnings and three hearts.
* 145353 (research, with swap_trace, played by hand after a booster): two
  Lightnings, a Fourth of July. Before the fix the check called it the
  booster's tail, the input counter does not move for a hand-played swipe.
* 141804, 141909, 144303, 144455: the refill misses that started this.

Every Lightning drawn inside a merge's destroy pass shuffles 48 pieces, not
49: the swipe's start slot is empty then (_merge_fireworks_board).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "heart_lightning_merge"


@pytest.mark.parametrize("name", ["141804", "141909", "144303", "144455", "144946", "145214", "145353"])
def test_recorded_merge_swap_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


def test_hand_played_move_after_a_booster_is_checked_as_a_move():
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / "145353.json").read_text(encoding="utf-8"))
    assert pair["before"]["refill_input"][:2] == pair["after"]["refill_input"][:2] == [10, "activate_booster"]
    assert check_transition(pair["before"], pair["after"])["verdict"] == "ok"


def test_merge_fireworks_board_empties_only_the_start_cell():
    import move_strategy as ms

    board = [[1] * 7 for _ in range(7)]
    candidate = ms.MoveCandidate((6, 0), (6, 1), ms.Direction("right"), board, [[0] * 7 for _ in range(7)])
    pool = ms._merge_fireworks_board(board, candidate)
    assert pool[6][0] == ms.EMPTY and pool[6][1] == 1
    assert sum(value == ms.EMPTY for row in pool for value in row) == 1
    assert board[6][0] == 1
