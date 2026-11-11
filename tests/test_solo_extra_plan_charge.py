"""Solo Challenge: of two extras, the one that fills the booster goes first.

Hot Color 2026-11-11 15:04:58, meter 6/7: a blue four at the top (7 points,
fills the meter) against a yellow four lower down (16 points). The run planner
counted points only, played the yellow and needed a paid move to fill the
meter. The blue four leaves a rocket on top of the yellow column, so the yellow
does not survive it either way -- the choice is the booster now without a move.
"""
import io
import contextlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

RUN = ROOT / "Debug" / "runs" / "2026-11-11_15-04-58_473" / "move.json"


def _plan(charge_room):
    from tools.rebuild_evaluation import build_states

    move = json.loads(RUN.read_text(encoding="utf-8"))
    states = build_states(move)
    with contextlib.redirect_stdout(io.StringIO()):
        ranked = ms.rank_moves(move["board"], move["special_board"], mode=states["mode"],
                               score_rally_values=states["score_rally_values"],
                               strategy_context=states["strategy_context"])

    def simulate(board, candidate):
        return ms._simulate_created_candidate_cached(
            board, candidate, False, states["mode"], False, False, {}, {},
            states["score_rally_values"])

    rows = [(item, simulate(move["board"], item.candidate))
            for item in ranked if ms.has_reliable_same_move_extra(item)]
    pick = ms._plan_exact_extra_sequence(
        rows, simulate, None, states["mode"], False, states["score_rally_values"],
        known=lambda result: True, strategy_context=states["strategy_context"],
        turn_state=states["turn_state"], seconds=30, charge_room=charge_room)
    return tuple(pick.candidate.start), tuple(pick.candidate.target)


def test_blue_extra_that_fills_the_meter_goes_first():
    if not RUN.exists():
        pytest.skip("Hot Color recording is not on this machine")
    assert _plan(charge_room=1.0) == ((1, 3), (2, 3))


def test_without_room_the_bigger_extra_stays_first():
    if not RUN.exists():
        pytest.skip("Hot Color recording is not on this machine")
    assert _plan(charge_room=0.0) == ((3, 2), (3, 3))
