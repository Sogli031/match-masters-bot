from dataclasses import replace
import json
from pathlib import Path

import pytest
import move_strategy as ms
import runtime
from tools.rebuild_evaluation import build_states

FRAMES = json.loads((Path(__file__).parent / "fixtures/arena_deadline_regressions.json").read_text())


def dust_evaluation():
    frame = FRAMES["dust"]
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"],
        mode=states["mode"], score_rally_values=states["score_rally_values"])
    key = {tuple(frame["best_move"]["start"]), tuple(frame["best_move"]["target"])}
    return next(e for e in candidates if {e.candidate.start, e.candidate.target} == key)


def test_recorded_wanted_shots_do_not_guarantee_later_four():
    item = dust_evaluation()
    assert not ms.has_reliable_same_move_extra(item)
    assert any(e.get("reason") == "dustville_random_shots" for e in item.intent_events)
    assert ms._dustville_wanted_charge(item, ms.GameMode.DUSTVILLE_DUEL) == 4
    # A four formed by the swipe itself still precedes the random shots.
    assert ms.has_reliable_same_move_extra(replace(item, extra_moves=1, direct_extra_moves=1))


@pytest.mark.parametrize("seconds,expected", [(24.133999618527014, 54), (110, 36)])
def test_recorded_lotus_prefers_points_only_under_short_clock(seconds, expected):
    frame = FRAMES["lotus"]
    states = build_states(frame)
    states["turn_state"] = replace(states["turn_state"], time_left_seconds=seconds)
    with ms.froggy_gather_region_active(7, True), ms.mushroom_multipliers_active(True), \
            ms.score_multiplier_state(frame["observed_multiplier"]):
        candidates = ms.rank_moves(frame["board"], frame["special_board"],
            mode=states["mode"], score_rally_values=states["score_rally_values"],
            strategy_context=states["strategy_context"])
        ranked = ms.rank_froggy_lotus_moves(candidates, frame["board"], frame["special_board"], **states)
    assert ranked[0].instant_score == expected
    assert ms.has_reliable_same_move_extra(ranked[0])


def test_deadline_score_does_not_change_challenge_or_unknown_clock():
    item = replace(dust_evaluation(), score=100, instant_score=10)
    short = ms.TurnState(remaining_moves=2, time_left_seconds=1, seconds_per_move=6.5)
    assert ms._froggy_deadline_score(item, short, ms.StrategyContext("solo_6", solo_challenge=True)) == 100
    assert ms._froggy_deadline_score(item, ms.TurnState(remaining_moves=2), ms.StrategyContext("solo_6")) == 100
    assert ms._froggy_deadline_score(item, short, ms.StrategyContext("solo_6")) == 10
    discounted = replace(item, score=5)
    assert ms._froggy_deadline_score(discounted, short, ms.StrategyContext("solo_6")) == 5


def test_mixy_known_cascade_is_refund_proof_but_random_cascade_is_not():
    base = dust_evaluation()
    three = ms.MatchGroup(frozenset((0, c) for c in range(3)), ms.GREEN, "three")
    four = ms.MatchGroup(frozenset((1, c) for c in range(4)), ms.GREEN, "four")
    refund_only = replace(base, extra_moves=1, direct_extra_moves=1,
        cascade_matches=[[three]], intent_events=[], mixy_code_color=ms.GREEN)
    own = replace(refund_only, extra_moves=2, cascade_matches=[[three], [four]])
    assert runtime._prefer_refund_proof_mixy_extra([refund_only, own], True) is own
    uncertain = replace(own, intent_events=[dict(type="uncertain_refill_boundary", after_cascade=1,
                                               reason="dustville_random_shots")])
    assert runtime._prefer_refund_proof_mixy_extra([refund_only, uncertain], True) is refund_only
