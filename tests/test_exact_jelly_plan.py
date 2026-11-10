"""Jelly SE with the drop known: keep the zone when a better conversion follows."""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import move_strategy as ms

ZONE = {(0, 0), (0, 1)}


def test_lava_purple_four_keeps_jelly_for_the_next_move():
    path = Path(__file__).resolve().parents[1] / "Debug/runs/2026-11-10_04-39-37_936/move.json"
    if not path.is_file():
        pytest.skip("Lava Jelly SE decision recording not present")
    move = json.loads(path.read_text(encoding="utf-8"))
    with (ms.jelly_zone_cells(move["jelly_zone_cells"]),
          ms.floor_lava_checked_columns(column - 1 for column in move["floor_lava_state"]["columns"])):
        best = ms.rank_moves(move["board"], move["special_board"], move["mode"])[0]
    assert {best.candidate.start, best.candidate.target} == {(5, 0), (5, 1)}
    assert ms.has_guaranteed_true_extra(best)
    assert ms.jelly_conversion_tiles(best) == 0


def _result(name, points, *, conversion=False, extra=0, blue=0.0):
    events = [{"type": ms.JELLY_ZONE_CONVERSION_EVENT, "converted_tiles": 4}] if conversion else []
    return NS(name=name, points=points, intent_events=events, extra_moves=extra, blue_cells=blue,
              board=[[name]], special_board=[[0]], exact_refill_supported=True, disco_moves=0)


def _plan(monkeypatch, rows, following, **session):
    """``following``: what each next-board candidate does, per board name."""
    monkeypatch.setattr(ms, "_exact_plan_points", lambda result, *a: result.points)
    monkeypatch.setattr(ms, "generate_candidates",
                        lambda board, special: [NS(board=board[0][0], i=i)
                                                for i in range(len(following.get(board[0][0], ())))])
    seen_zones = []

    def simulate(board, candidate):
        seen_zones.append(set(ms._JELLY_ZONE_CELLS))
        return following[candidate.board][candidate.i]

    fake = NS(knows=lambda board: True, blue_missing=session.get("blue_missing", 99))
    with ms.jelly_zone_cells(ZONE):
        return ms._exact_jelly_plan(rows, simulate, fake, "None", False, None), seen_zones


def _row(result):
    return (NS(name=result.name, disco_moves=0), result)


def test_keeps_the_zone_when_the_next_conversion_is_clearly_better(monkeypatch):
    convert = _result("conv", 30, conversion=True, extra=1)
    outside = _result("out", 20, extra=1)
    following = {"conv": [_result("x", 10)],                          # 30 + 10 = 40
                 "out": [_result("big", 60, conversion=True), _result("y", 90)]}   # 20 + 60 = 80
    (pick, reason), zones = _plan(monkeypatch, [_row(convert), _row(outside)], following)
    assert pick.name == "out" and "jelly sledeci potez" in reason
    # After the conversion the zone is spent; after the outside swap it is not,
    # and only conversions count there (the 90-point plain move does not).
    assert set() in zones and ZONE in zones


def test_converts_now_when_waiting_is_not_clearly_better(monkeypatch):
    convert = _result("conv", 30, conversion=True, extra=1)
    outside = _result("out", 20, extra=1)
    following = {"conv": [_result("x", 10)], "out": [_result("c", 25, conversion=True)]}   # 45 vs 40
    assert _plan(monkeypatch, [_row(convert), _row(outside)], following)[0] is None


def test_never_waits_with_a_swap_that_gives_the_turn_away(monkeypatch):
    convert = _result("conv", 30, conversion=True, extra=1)
    outside = _result("out", 20, extra=0)
    following = {"conv": [], "out": [_result("c", 200, conversion=True)]}
    assert _plan(monkeypatch, [_row(convert), _row(outside)], following)[0] is None


def test_does_not_trade_charge_for_points(monkeypatch):
    convert = _result("conv", 30, conversion=True, extra=1, blue=4)
    outside = _result("out", 20, extra=1)
    following = {"conv": [], "out": [_result("c", 200, conversion=True, blue=1)]}
    assert _plan(monkeypatch, [_row(convert), _row(outside)], following, blue_missing=6)[0] is None


def test_followed_board_after_an_extra_even_with_an_opponent():
    from engine_refill import ExactRefillSession

    model = NS(clone=lambda: model, reset_action=lambda: None, random_specials=False, profile={})
    session = ExactRefillSession(model, [[1]], follow_moves=False)
    session.begin([[1]])
    session.finish(NS(board=[[2]], special_board=None, extra_moves=1, intent_events=(),
                      cleared_color_counts={}))
    assert session.knows([[2]])
    session.begin([[1]])
    session.finish(NS(board=[[3]], special_board=None, extra_moves=0, intent_events=(),
                      cleared_color_counts={}))
    assert not session.knows([[3]])


# --- which conversion, and whether now (_exact_jelly_conversion_choice) -------

BOARD = [[1, 2, 3], [4, 5, 6], [1, 2, 3]]
GOAL = dict(targets=[150, 550, 2175], score=149, refill_moves=6, overflow=False,
            continue_after_last=True)


def _choice_row(name, points, *, conversion=False, extra=0, blue=0.0, board=None, swap=((2, 0), (2, 1))):
    events = [{"type": ms.JELLY_ZONE_CONVERSION_EVENT, "converted_tiles": 4}] if conversion else []
    result = NS(name=name, points=points, intent_events=events, extra_moves=extra, blue_cells=blue,
                board=board or BOARD, special_board=None, exact_refill_supported=True, disco_moves=0)
    return (NS(name=name, disco_moves=0, candidate=NS(start=swap[0], target=swap[1])), result)


def _choose(monkeypatch, rows, goal=None, blue_missing=7, moves_left=4, solo=True):
    monkeypatch.setattr(ms, "_exact_plan_points", lambda result, *a: result.points)
    session = NS(solo=solo, blue_missing=blue_missing, moves_left=moves_left)
    with ms.jelly_zone_cells(ZONE):
        pick = ms._exact_jelly_conversion_choice(rows, session, "None", False, None, goal, BOARD, None)
    return pick and (pick[0].name, pick[1])


def test_conversion_that_fills_the_meter_beats_more_points(monkeypatch):
    # Bullseye Bash 20261109_174229 011: 105 points and 6 blue against 47 and 17.
    rows = [_choice_row("points", 105, conversion=True, blue=6),
            _choice_row("fill", 47, conversion=True, blue=17)]
    assert _choose(monkeypatch, rows)[0] == "fill"


def test_same_moves_to_fill_is_decided_by_points(monkeypatch):
    # 20261110_013425 018: 30 points played over 68 for the same 4 blue; and
    # 5 blue is no closer to a full meter than 4 (one more move either way).
    rows = [_choice_row("low", 30, conversion=True, blue=4),
            _choice_row("high", 68, conversion=True, blue=4),
            _choice_row("bluer", 50, conversion=True, blue=5)]
    assert _choose(monkeypatch, rows)[0] == "high"


def test_conversion_marked_as_extra_does_not_jump_the_queue(monkeypatch):
    # 20261110_043451 018: 12 points and 2 blue (an "extra") over 29 and 5.
    rows = [_choice_row("extra", 12, conversion=True, extra=1, blue=2),
            _choice_row("better", 29, conversion=True, blue=5)]
    assert _choose(monkeypatch, rows)[0] == "better"


def test_charge_that_cannot_fill_in_the_moves_left_counts_for_nothing(monkeypatch):
    rows = [_choice_row("blue", 20, conversion=True, blue=4),
            _choice_row("points", 60, conversion=True, blue=1)]
    assert _choose(monkeypatch, rows, moves_left=1)[0] == "points"
    assert _choose(monkeypatch, rows, moves_left=3)[0] == "blue"


def test_plain_move_crosses_the_stage_target_and_keeps_the_zone(monkeypatch):
    # 20261109_170604 003: 149/150, the conversion took 1 point of its 100.
    rows = [_choice_row("conv", 100, conversion=True, blue=5),
            _choice_row("big", 6), _choice_row("three", 3, blue=3)]
    name, reason = _choose(monkeypatch, rows, GOAL)
    assert name == "three" and "prag 150" in reason
    # Nothing plain reaches the target: the conversion goes as before.
    assert _choose(monkeypatch, rows, dict(GOAL, score=120))[0] == "conv"
    # The target does not cut this conversion.
    assert _choose(monkeypatch, rows, dict(GOAL, score=10))[0] == "conv"
    # Overflow kept, or the last target with play going on: nothing is cut.
    assert _choose(monkeypatch, rows, dict(GOAL, overflow=True))[0] == "conv"
    assert _choose(monkeypatch, rows, dict(GOAL, score=2170))[0] == "conv"


def test_outside_extra_goes_first_only_when_the_conversion_survives_it(monkeypatch):
    conv = _choice_row("conv", 60, conversion=True, blue=3)
    moved = [[9, 9, 9], [4, 5, 6], [1, 2, 3]]        # the zone (row 0) changed
    kept = [[1, 2, 3], [9, 9, 9], [1, 2, 3]]
    assert _choose(monkeypatch, [conv, _choice_row("wrecks", 35, extra=1, blue=6, board=moved)])[0] == "conv"
    name, reason = _choose(monkeypatch, [conv, _choice_row("free", 8, extra=1, board=kept)])
    assert name == "free" and reason == "extra pre jelly konverzije"
    # A conversion that fills the meter by itself is taken at once.
    full = _choice_row("full", 60, conversion=True, blue=9)
    assert _choose(monkeypatch, [full, _choice_row("free", 8, extra=1, board=kept)])[0] == "full"


def test_only_in_solo_and_only_with_a_conversion(monkeypatch):
    rows = [_choice_row("conv", 60, conversion=True, blue=3)]
    assert _choose(monkeypatch, rows, solo=False) is None
    assert _choose(monkeypatch, [_choice_row("plain", 60)]) is None


def test_plan_points_are_column_sums_only_where_columns_pay(monkeypatch):
    monkeypatch.setattr(ms, "evaluate_simulation",
                        lambda *a, **k: NS(instant_score=25.0, crazy_columns_score=79.0))
    assert ms._exact_plan_points(None, "None", False, None) == 25.0
    assert ms._exact_plan_points(None, ms.GameMode.CRAZY_COLUMNS, False, None) == 79.0


def test_ranking_crosses_the_stage_target_before_a_cut_conversion():
    from dataclasses import replace

    board = [[(ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE)[(r + c) % 4] for c in range(7)] for r in range(7)]
    board[3][0] = board[3][1] = board[2][2] = ms.RED
    specials = [[0] * 7 for _ in range(7)]
    after, after_special = ms.swap_cells(board, specials, (2, 2), (3, 2))
    candidate = ms.MoveCandidate((2, 2), (3, 2), ms.Direction.DOWN, after, after_special)
    plain = ms.evaluate_simulation(ms.simulate_candidate(candidate), ms.GameMode.NONE,
                                   include_future_value=False)
    conversion = replace(plain, instant_score=40.0, intent_events=plain.intent_events + [
        {"type": ms.JELLY_ZONE_CONVERSION_EVENT, "converted_tiles": 10, "cascade": 1}])
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=3)

    def crossing(score):
        context = ms.StrategyContext("solo_6", solo_challenge=True, solo_goal=dict(GOAL, score=score))
        return ms._jelly_stage_crossing_moves(conversion, [conversion, plain], "None", booster, turn,
                                              None, context)

    picked = crossing(149)
    assert [item.decision_gate for item in picked] == [ms.JELLY_STAGE_CROSS_GATE]
    assert ms.jelly_conversion_tiles(picked[0]) == 0
    assert crossing(140) == []      # the three does not reach the target
    assert crossing(10) == []       # the conversion is not cut
