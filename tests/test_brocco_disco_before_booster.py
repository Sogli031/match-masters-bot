"""Brocco balls outside Solo Challenge (player, 2026-10-08).

Every ball is thrown before the booster fires, the ball picks its colour for
points, and in Multiplier Mushrooms for the mushrooms it sweeps. Solo Challenge
keeps its blue-first disco policy.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402

RACE = ms.StrategyContext(ms.STRATEGY_SOLO_6)
VERSUS = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
CHALLENGE = ms.StrategyContext(ms.STRATEGY_SOLO_6, solo_challenge=True)
MMS = ms.GameMode.MULTIPLIER_MUSHROOMS


def _disco(score, mushrooms=0, extra=0.0, name=""):
    return SimpleNamespace(
        name=name, disco_moves=1, score=score, multiplier_mushrooms=mushrooms,
        extra_moves=extra, direct_extra_moves=extra, cascade_matches=[], intent_events=[],
        mode_targets=0, blue_cells=0.0, decision_gate="score_gate",
    )


def _plain(score):
    return SimpleNamespace(disco_moves=0, score=score, extra_moves=0.0, direct_extra_moves=0.0,
                           decision_gate="score_gate")


def _no_count(monkeypatch):
    monkeypatch.setattr(ms, "_disco_target_color_count", lambda evaluation: 0)


def test_mushrooms_lead_then_points(monkeypatch):
    _no_count(monkeypatch)
    big = _disco(90.0, mushrooms=1, name="big")
    shrooms = _disco(40.0, mushrooms=4, name="shrooms")
    best = ms.disco_swap_before_booster([big, shrooms], mode=MMS, strategy_context=RACE)
    assert best is shrooms
    # Outside Mushrooms the points decide.
    best = ms.disco_swap_before_booster([big, shrooms], mode=ms.GameMode.NONE, strategy_context=VERSUS)
    assert best is big


def test_a_ball_that_keeps_the_turn_still_leads(monkeypatch):
    _no_count(monkeypatch)
    big = _disco(90.0, mushrooms=4)
    keeps = _disco(10.0, extra=1.0)
    assert ms.disco_swap_before_booster([big, keeps], mode=MMS, strategy_context=RACE) is keeps


def test_solo_challenge_is_left_alone(monkeypatch):
    _no_count(monkeypatch)
    assert ms.disco_swap_before_booster([_disco(50.0)], mode=MMS, strategy_context=CHALLENGE) is None


def test_gate_throws_the_ball_before_the_booster():
    ball = _disco(30.0)
    for immediate in (True, False):
        action, chosen, gate = runtime.select_booster_action_with_gate(
            [_plain(20.0)], True, immediate, disco_before_booster=ball
        )
        assert (action, chosen, gate) == ("move", ball, "disco_before_booster_gate")
    # No ball: the booster fires as before.
    action, _chosen, _gate = runtime.select_booster_action_with_gate([_plain(20.0)], True, True)
    assert action == "activate_booster"


def test_an_extra_still_goes_before_the_ball():
    ball = _disco(30.0)
    extra = SimpleNamespace(disco_moves=0, score=10.0, extra_moves=1.0, direct_extra_moves=1.0,
                            cascade_matches=[], intent_events=[], decision_gate="score_gate")
    action, chosen, gate = runtime.select_booster_action_with_gate(
        [extra], True, False, disco_before_booster=ball
    )
    assert chosen is extra
