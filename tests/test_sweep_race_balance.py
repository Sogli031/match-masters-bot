"""Sweep SE in point races (Versus, Showdown, Party), player 2026-11-07."""
from types import SimpleNamespace as NS

import move_strategy as ms


def _ev(points, charge, broom=False):
    return NS(instant_score=points, score=points, charge=charge, broom=broom)


def test_broom_line_is_points_plus_a_few_useful_blues(monkeypatch):
    monkeypatch.setattr(ms, "_booster_points_first", lambda *a: True)
    monkeypatch.setattr(ms, "_useful_total_charge_cells", lambda item, *a: item.charge)
    monkeypatch.setattr(ms, "_sweep_se_target_color", lambda e: 1 if e.broom else None)
    moves = [_ev(50, 0, True), _ev(60, 0), _ev(45, 3, True)]       # 50 vs 45 + 3*4 = 57
    out = ms._race_sweep_balanced_order(moves, "None", None, None, None, None)
    assert [m.instant_score for m in out] == [45, 60, 50]
    monkeypatch.setattr(ms, "_booster_points_first", lambda *a: False)
    assert ms._race_sweep_balanced_order(moves, "None", None, None, None, None) is moves


def test_broom_goes_before_an_extra_when_it_fills_or_scores_big(monkeypatch):
    monkeypatch.setattr(ms, "_useful_total_charge_cells", lambda item, *a: item.charge)
    booster = ms.BoosterState(current=4, maximum=7)                 # 3 to go
    go = lambda broom, extra: ms._race_broom_goes_now(broom, [extra], "None", booster, None, None, None)
    assert go(_ev(20, 3), _ev(30, 0))          # fills the booster now
    assert go(_ev(60, 0), _ev(30, 0))          # 60 >= 40 and >= 1.5 * 30
    assert not go(_ev(40, 0), _ev(30, 0))      # not 1.5x the extra
    assert not go(_ev(30, 1), _ev(10, 0))      # under 40 points, no fill
