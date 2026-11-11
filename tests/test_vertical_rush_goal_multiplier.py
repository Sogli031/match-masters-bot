"""Vertical Rush: a move is paid at the multiplier its own direct match leaves.

Debug/runs 2026-11-09..11-10 (56 solo moves): a lone vertical direct match +1,
a lone horizontal one -1 (floor 1), anything else never below -1. 2026-11-10
04:07:22 promised a sure flag at 64 x 8 = 512 over a 465 gap; the horizontal
three dropped the multiplier to 7 and the game paid 448.
"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from solo_challenge import SoloGoalState


def _move(cells):
    group = ms.MatchGroup(frozenset(cells), 1, "three")
    return replace(_plain(), cascade_matches=[[group]])


def _plain():
    from tests.test_solo_challenge_goals import plain_three
    return plain_three()


def test_lone_vertical_match_raises_lone_horizontal_lowers():
    vertical = _move([(2, 3), (3, 3), (4, 3)])
    horizontal = _move([(4, 1), (4, 2), (4, 3)])
    assert ms._vertical_rush_move_multiplier(vertical, 8.0) == 9.0
    assert ms._vertical_rush_move_multiplier(horizontal, 8.0) == 7.0
    assert ms._vertical_rush_move_multiplier(horizontal, 1.0) == 1.0


def test_horizontal_move_no_longer_promises_the_recorded_false_flag():
    goal = SoloGoalState((465 + 1000,), 1000, multiplier=8.0)
    context = ms.StrategyContext("solo_6", solo_challenge=True, solo_goal=goal)
    move = replace(_move([(4, 1), (4, 2), (4, 3)]), instant_score=64.0)
    scale = ms._solo_goal_points_scale(move, ms.GameMode.VERTICAL_RUSH.value, goal)
    assert scale == 7.0
    assert 64.0 * scale < goal.gap
    assert not ms._solo_goal_crosses(move, ms.GameMode.VERTICAL_RUSH.value, {}, context)
