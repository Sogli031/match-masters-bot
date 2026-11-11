"""Solo Challenge: the runtime forced-extra rule must not override a Brocco
ball that leads the charge-plan ranking and keeps the turn itself.

Boards: 2026-11-11 19:10:14 (meter 3/7, ball 3 now / plan 4 lost to a plain
extra with 0 now) and 19:15:25 (meter 0/7, ball plan 7 lost to a plain extra
with plan 3). Both were played by `_forced_extra_move_candidate`.
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms
import runtime

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "solo_ball_before_forced_extra.json").read_text(encoding="utf-8")
)["cases"]


def _prioritized(case, context):
    rally = {int(k): v for k, v in case["score_rally_values"].items()}
    booster = ms.BoosterState(source="memory", **case["booster_state"])
    turn = ms.TurnState(
        remaining_moves=case["remaining_moves"], source="memory",
        time_left_seconds=case["time_left_seconds"], seconds_per_move=case["seconds_per_move"],
    )
    common = dict(mode=case["mode"], score_rally_values=rally)
    ranked = ms.rank_moves(
        case["board"], case["special_board"], lookahead_candidates=20, include_future_value=True,
        lookahead_depth=ms.clamp_lookahead_depth(3, turn), lookahead_beam_width=6,
        strategy_context=context, turn_state=turn, **common,
    )
    return ms.prioritize_ranked_moves(
        ranked, booster_state=booster, turn_state=turn, strategy_context=context, **common
    )


def _solo(case):
    return ms.StrategyContext(mode="solo_6", solo_challenge=True, solo_goal=case["solo_goal"])


@pytest.mark.parametrize("run", sorted(CASES))
def test_leading_ball_with_extra_is_not_overridden(run):
    case = CASES[run]
    context = _solo(case)
    prioritized = _prioritized(case, context)
    top = prioritized[0]
    assert top.disco_moves > 0
    assert top.solo_blue_plan_charge is not None
    assert ms.has_reliable_same_move_extra(top)
    # A plain extra is still on the list: the old rule picked it.
    assert runtime._forced_extra_move_candidate(prioritized) is not None
    assert runtime._forced_extra_move_candidate(prioritized, strategy_context=context) is None


@pytest.mark.parametrize("run", sorted(CASES))
def test_ready_booster_still_forces_direct_extras(run):
    case = CASES[run]
    context = _solo(case)
    prioritized = _prioritized(case, context)
    assert runtime._forced_extra_move_candidate(
        prioritized, direct_only=True, strategy_context=context
    ) is runtime._forced_extra_move_candidate(prioritized, direct_only=True)


def test_plain_extra_still_forced_when_it_leads():
    case = CASES["2026-11-11_19-15-25_438"]
    context = _solo(case)
    prioritized = _prioritized(case, context)
    plain = [item for item in prioritized if item.disco_moves <= 0]
    assert runtime._forced_extra_move_candidate(plain, strategy_context=context) is plain[0]
