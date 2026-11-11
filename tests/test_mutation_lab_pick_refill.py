"""Mutation Lab: crossing a pick threshold buys moves, so that move is not the last.

2026-11-11 15:28:52: score 88, one move left, meter 3/7. The bot priced every
move at 0 as the match's last; the blue three it played scored 12, crossed the
100 pick, and the game gave 3 more moves with the meter carried to 6/7.
Rules: soloTargets [2100], mutationLabTargetsPerSoloTarget [[0, 100, 250, 500]],
mutationLabMovesRefill 3.
"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from solo_challenge import SoloGoalState, goal_from_snapshot, mutation_lab_pick_targets
from tests.test_solo_challenge_goals import plain_three

ENGINE = {
    "isMutationLab": True,
    "mutationLabMovesRefill": 3,
    "mutationLabTargetsPerSoloTarget": [[0, 100, 250, 500]],
    "soloOverflowPastTarget": True,
    "soloContinueAfterLastTarget": True,
}


def _snapshot(score=88, engine=ENGINE):
    return {"state": {
        "is_singleplayer_board": True,
        "players": [{"score": score, "score_multiplier": 1}],
        "rules": {"solo_targets": [2100], "solo_refill_mode": True, "moves_per_turn": 6,
                  "engine_fields": dict(engine)},
    }}


def test_pick_thresholds_become_stages_with_their_refill():
    goal = SoloGoalState.from_payload(goal_from_snapshot(_snapshot()))
    assert goal.targets == (100, 250, 500, 2100)
    assert goal.refill_moves == 3
    assert goal.next_target == 100 and goal.gap == 12


def test_other_solo_challenges_are_unchanged():
    plain = dict(ENGINE, isMutationLab=False)
    goal = SoloGoalState.from_payload(goal_from_snapshot(_snapshot(engine=plain)))
    assert goal.targets == (2100,)
    assert goal.refill_moves == 6
    assert mutation_lab_pick_targets({"isMutationLab": True, "mutationLabMovesRefill": 3,
                                      "mutationLabTargetsPerSoloTarget": "<List>"}, [2100]) == ([], 0)


def test_move_that_crosses_a_pick_on_the_last_move_keeps_a_future():
    goal = SoloGoalState.from_payload(goal_from_snapshot(_snapshot()))
    context = ms.StrategyContext("solo_6", solo_challenge=True, solo_goal=goal)
    last = ms.TurnState(1, "memory")
    base = plain_three()
    color = next(iter(base.cleared_color_counts))
    crossing = replace(base, instant_score=12.0, cleared_color_counts={color: 12})
    short = replace(base, instant_score=3.0, cleared_color_counts={color: 3})
    assert ms._evaluation_turn_state(crossing, last, context).remaining_moves >= 4
    assert ms._evaluation_turn_state(short, last, context).remaining_moves == 1


LIVE_ENGINE = dict(ENGINE, id="mutation-lab-solo-mode",
                   mutationLabTargetsPerSoloTarget="<System.Collections.Generic.List<"
                                                   "System.Collections.Generic.List<System.Int32>>>")
DECODED = {"id": "mutation-lab-solo-mode", "soloTargets": [2100], "isMutationLab": True,
           "mutationLabMovesRefill": 3, "mutationLabTargetsPerSoloTarget": [[0, 100, 250, 500]]}


def test_live_snapshot_takes_the_list_from_the_decoded_rules():
    # The snapshot's engine_fields names the nested list's type only;
    # match_profile (the exact-refill reader) decodes it.
    snapshot = _snapshot(engine=LIVE_ENGINE)
    assert SoloGoalState.from_payload(goal_from_snapshot(snapshot)).targets == (2100,)
    goal = SoloGoalState.from_payload(goal_from_snapshot(snapshot, DECODED))
    assert goal.targets == (100, 250, 500, 2100) and goal.refill_moves == 3


def test_decoded_rules_of_another_match_are_ignored():
    snapshot = _snapshot(engine=LIVE_ENGINE)
    other = dict(DECODED, id="color-crush")
    assert SoloGoalState.from_payload(goal_from_snapshot(snapshot, other)).targets == (2100,)
    other = dict(DECODED, soloTargets=[100, 350, 1150])
    assert SoloGoalState.from_payload(goal_from_snapshot(snapshot, other)).targets == (2100,)
