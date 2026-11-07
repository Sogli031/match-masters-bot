"""Jelly SE with the drop known: keep the zone when a better conversion follows."""
from types import SimpleNamespace as NS

import move_strategy as ms

ZONE = {(0, 0), (0, 1)}


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
