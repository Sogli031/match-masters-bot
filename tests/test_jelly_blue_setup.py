"""Jelly SE: a move that sets up a blue conversion for the next move.

With the zone up the meter is empty (the jelly is the booster), and a blue
conversion banks the whole zone. When nothing on the board fills the meter now,
a swipe that leaves the zone alone and a blue match into it on the next board
fills it one move later. Recorded Score Market research 20261111_212641 013:
the bot played (2,3)->(2,4) (4 blue now); (3,5)->(4,5) leaves a blue
conversion worth the full meter.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import move_strategy as ms

FIXTURE = Path(__file__).parent / "fixtures" / "jelly_blue_setup" / "013.json"


def _session(monkeypatch, record):
    import square_solo_live as live
    from tools.analyze_research import capture_from

    capture = capture_from(record)
    board = record["board"]
    snapshot = {"columns": len(board), "state": record["snapshot_state"], "slots": record["raw_slots"],
                "special_board": record["special_board"],
                "board_extra_data": {e["key"]: str(e["value"]) for e in record["board_extra_data"]["entries"]}}
    monkeypatch.setattr(live, "_resting_profile", lambda *_: (capture["profile"].copy(), None))
    session, reason = live.exact_refill_session(None, None, snapshot, board)
    assert session is not None, reason
    return session, capture


def test_recorded_board_plays_the_blue_setup(monkeypatch):
    from tools.analyze_research import load, observed

    record, capture = load(FIXTURE)
    session, _ = _session(monkeypatch, record)
    assert session.max_plies == 1
    session.blue_missing = 7
    mode = capture["simulator_input"].get("mode") or "None"
    board, specials = record["board"], record["special_board"]
    goal = ms.SoloGoalState(targets=(10**6,), score=0)
    context = ms.StrategyContext(mode="solo_6", solo_challenge=True, booster_rush=True, solo_goal=goal)
    with ms.exact_refill_active(session), ms.jelly_zone_cells(session.jelly_cells):
        ranked = ms.rank_moves(board, specials, mode)
        pick = ms.exact_refill_choice(
            ranked, board, specials, mode=mode, solo_goal=goal,
            booster_state=ms.BoosterState(current=0, maximum=7, source="memory"),
            turn_state=ms.TurnState(remaining_moves=observed(record)["moves"], source="memory"),
            strategy_context=context)
    assert pick is not None
    evaluation, reason = pick
    assert {evaluation.candidate.start, evaluation.candidate.target} == {(3, 5), (4, 5)}
    assert "jelly plava" in reason


def _result(name, *, blue=0.0, convert=None, extra=0):
    events = [{"type": ms.JELLY_ZONE_CONVERSION_EVENT, "converted_tiles": 5}] if convert is not None else []
    return NS(name=name, blue_cells=blue, jelly_converted_color=convert, intent_events=events,
              extra_moves=extra, disco_moves=0, exact_refill_supported=True,
              board=[[name]], special_board=[[0]])


def _setup(monkeypatch, rows, following, moves=4, missing=7):
    monkeypatch.setattr(ms, "generate_candidates",
                        lambda board, special: [NS(board=board[0][0], i=i)
                                                for i in range(len(following.get(board[0][0], ())))])
    monkeypatch.setattr(ms, "has_reliable_same_move_extra", lambda item: False)
    simulate = lambda board, candidate: following[candidate.board][candidate.i]
    session = NS(knows=lambda *a: True, blue_missing=missing, use_special_keys=True)
    with ms.jelly_zone_cells({(0, 0)}):
        return ms._exact_jelly_blue_setup(
            [(NS(name=r.name), r) for r in rows], simulate, session, NS(remaining_moves=moves))


def test_paid_setup_wins_when_it_fills_the_meter(monkeypatch):
    rows = [_result("now", blue=4, convert=3), _result("setup", blue=1)]
    following = {"setup": [_result("blue", blue=12, convert=ms.BLUE), _result("x", blue=2)]}
    pick, reason = _setup(monkeypatch, rows, following)
    assert pick.name == "setup" and "7 plavih prema 4" in reason


def test_no_setup_when_the_meter_fills_now(monkeypatch):
    rows = [_result("now", blue=9, convert=ms.BLUE), _result("setup", blue=1)]
    following = {"setup": [_result("blue", blue=12, convert=ms.BLUE)]}
    assert _setup(monkeypatch, rows, following) is None


def test_no_paid_setup_without_a_move_left_for_the_conversion(monkeypatch):
    rows = [_result("now", blue=4, convert=3), _result("setup", blue=1)]
    following = {"setup": [_result("blue", blue=12, convert=ms.BLUE)]}
    assert _setup(monkeypatch, rows, following, moves=1) is None


def test_other_colour_conversion_next_is_not_a_blue_setup(monkeypatch):
    rows = [_result("now", blue=4, convert=3), _result("setup", blue=1)]
    following = {"setup": [_result("green", blue=12, convert=3)]}
    assert _setup(monkeypatch, rows, following) is None


def test_no_setup_when_it_does_not_fill_the_meter(monkeypatch):
    rows = [_result("now", blue=3, convert=3), _result("setup", blue=0)]
    following = {"setup": [_result("blue", blue=5, convert=ms.BLUE)]}
    assert _setup(monkeypatch, rows, following) is None
