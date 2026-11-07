from dataclasses import asdict, replace
import json
from pathlib import Path

import numpy as np
import pytest

import move_strategy as ms
import runtime
from solo_challenge import SoloGoalState, goal_from_snapshot


BOOSTER = ms.BoosterState(current=0, maximum=7, source="memory")


@pytest.fixture(autouse=True)
def stable_calibration(monkeypatch):
    # Test the policy independently of the user's mutable learned model.
    monkeypatch.setattr(type(ms.learned_value.weights()), "future_scale", lambda *args: 1.0)
    monkeypatch.setattr(ms, "_learned_residual", lambda *args: 0.0)


def plain_three():
    board = [[(ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE)[(r + c) % 4]
              for c in range(7)] for r in range(7)]
    board[3][0] = board[3][1] = ms.RED
    board[2][2] = ms.RED
    specials = [[0] * 7 for _ in range(7)]
    after, after_special = ms.swap_cells(board, specials, (2, 2), (3, 2))
    candidate = ms.MoveCandidate((2, 2), (3, 2), ms.Direction.DOWN, after, after_special)
    return ms.evaluate_simulation(ms.simulate_candidate(candidate), ms.GameMode.NONE,
                                  include_future_value=False)


def test_debug_serializes_numpy_color_keys_and_counts():
    item = replace(plain_three(),
        cleared_color_counts={np.int16(ms.RED): np.float32(3)})
    serialized = runtime.serialize_move_evaluation(item)
    decoded = json.loads(json.dumps(serialized))
    assert decoded["cleared_color_counts"] == {str(ms.RED): 3.0}


def context(**kwargs):
    return ms.StrategyContext("solo_6", solo_challenge=True, **kwargs)


def priority(item, moves=1, ctx=None):
    return ms._weighted_priority(item, "None", BOOSTER,
        ms.TurnState(remaining_moves=moves), None, ctx or context())


def add_future(item, value=10):
    return replace(item, score=item.score + value, lookahead_bonus=item.lookahead_bonus + value)


def test_last_reliable_extra_retains_its_own_continuation():
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=1)
    assert priority(add_future(item)) > priority(item)
    ordinary = replace(item, extra_moves=0, direct_extra_moves=0)
    assert priority(add_future(ordinary)) == pytest.approx(priority(ordinary))


def test_last_uncertain_extra_does_not_invent_a_future():
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=0,
        intent_events=[dict(type="uncertain_refill_boundary", after_cascade=0),
                       dict(type="match", cascade=1, kind="four", color=ms.RED,
                            cells=[[0, c] for c in range(4)], tile_count=4)])
    assert not ms.has_reliable_same_move_extra(item)
    assert priority(add_future(item)) == pytest.approx(priority(item))


def test_extra_continuation_stays_disabled_for_versus_and_clock_expiry():
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=1)
    turn = ms.TurnState(remaining_moves=1, time_left_seconds=1, seconds_per_move=3)
    assert ms._evaluation_turn_state(item, turn, context()).remaining_moves == 1
    versus = ms.StrategyContext("versus_2")
    assert ms._evaluation_turn_state(item, ms.TurnState(remaining_moves=1), versus).remaining_moves == 1


def test_known_refill_crossing_keeps_a_future_on_the_last_move():
    goal = SoloGoalState((100, 500), score=97, refill_moves=5)
    item = plain_three()
    ctx = context(solo_goal=goal)
    turn = ms._evaluation_turn_state(item, ms.TurnState(remaining_moves=1), ctx)
    assert turn.remaining_moves == 6
    assert priority(add_future(item), ctx=ctx) > priority(item, ctx=ctx)
    no_refill = context(solo_goal=replace(goal, refill_moves=0))
    assert priority(add_future(item), ctx=no_refill) == pytest.approx(priority(item, ctx=no_refill))


def test_automatic_play_does_not_force_the_finish():
    finish = plain_three()
    better = replace(finish, candidate=replace(finish.candidate, start=(0, 0)), instant_score=2, score=100)
    ctx = context(solo_goal=SoloGoalState((100,), score=97))
    ranked = ms.prioritize_ranked_moves([finish, better], booster_state=BOOSTER,
                                        turn_state=ms.TurnState(remaining_moves=2), strategy_context=ctx)
    assert not any(item.decision_gate == "solo_target_finish_gate" for item in ranked)


def test_button_finish_outranks_charge_and_skips_ready_booster():
    finish = plain_three()
    charge = replace(finish, instant_score=2, score=100, blue_cells=7)
    ctx = context(solo_goal=SoloGoalState((100,), score=97))
    turn = ms.TurnState(remaining_moves=2)
    ranked = ms.solo_goal_priority_moves([charge, finish], "None", BOOSTER, turn, None, ctx)
    assert ranked[0].candidate == finish.candidate
    assert ranked[0].instant_score == finish.instant_score
    assert ranked[0].decision_gate == "solo_target_finish_gate"
    action, chosen, gate = runtime.select_booster_action_with_gate(
        ranked, booster_active=True, booster_immediate=True, strategy_context=ctx)
    assert action == "move" and chosen is ranked[0] and gate == "solo_target_finish_gate"


def test_stage_refill_priority_uses_current_target_and_unused_move_energy():
    item = plain_three()
    goal = SoloGoalState((100, 500), score=97, refill_moves=5)
    args = ([item], "None", BOOSTER, ms.TurnState(remaining_moves=1), None)
    assert ms.solo_goal_priority_moves(*args, context(solo_goal=goal))[0].decision_gate == "solo_target_refill_gate"
    # The button offers a crossing however many moves are left.
    assert ms.solo_goal_priority_moves([item], "None", BOOSTER,
        ms.TurnState(remaining_moves=5), None, context(solo_goal=goal))
    assert ms.solo_goal_priority_moves([item], "None", BOOSTER,
        ms.TurnState(remaining_moves=5), None,
        context(solo_goal=replace(goal, unused_moves_energy=1)))


def test_clipped_surplus_loses_its_score_value():
    ctx = context(solo_goal=SoloGoalState((100, 500), score=98, overflow=False))
    small = plain_three()
    large = replace(small, instant_score=small.instant_score + 20, score=small.score + 20)
    assert priority(large, 3, ctx) == pytest.approx(priority(small, 3, ctx))
    overflow = replace(ctx, solo_goal=replace(ctx.solo_goal, overflow=True))
    assert priority(large, 3, overflow) > priority(small, 3, overflow)


def test_target_score_units_include_the_live_multiplier():
    ctx = context(solo_goal=SoloGoalState((100,), score=70, multiplier=10))
    assert ms._solo_goal_certain_points(plain_three(), "None", None, ctx) == 30
    assert ms._solo_goal_crosses(plain_three(), "None", None, ctx)


def test_random_refill_and_objective_only_boards_do_not_promise_a_win():
    item = plain_three()
    ctx = context(solo_goal=SoloGoalState((100,), score=97))
    random = replace(item, intent_events=item.intent_events + [
        dict(type="uncertain_refill_boundary", after_cascade=1)])
    assert not ms._solo_goal_crosses(random, "None", None, ctx)
    assert not ms._solo_goal_crosses(item, ms.GameMode.CHEST, None, ctx)


def test_multiplier_investment_tapers_with_real_remaining_moves():
    item = replace(plain_three(), mode_bonus=6, lights_up_multiplier_points=1)
    with ms.lights_up_state(column=0, multiplier=1, remaining_moves=4):
        early = ms._solo_goal_multiplier_discount(item, ms.GameMode.LIGHTS_UP,
            ms.TurnState(remaining_moves=4), context())
        late = ms._solo_goal_multiplier_discount(item, ms.GameMode.LIGHTS_UP,
            ms.TurnState(remaining_moves=1), context())
    assert early == 0 and late == 6


def test_live_snapshot_and_debug_roundtrip_preserve_goal_rules():
    snapshot = dict(state=dict(is_singleplayer_board=True, players=[dict(score=97, score_multiplier=2)],
        rules=dict(solo_targets=[100, 500], solo_refill_mode=True, moves_per_turn=5,
                   engine_fields=dict(soloOverflowPastTarget=False, soloUnusedMovesEnergyWorth=1))))
    payload = goal_from_snapshot(snapshot)
    goal = SoloGoalState.from_payload(payload)
    assert goal == SoloGoalState((100, 500), 97, 5, False, False, 1, 2)
    assert ms.StrategyContext(**asdict(context(solo_goal=goal))).solo_goal == goal
    snapshot["state"]["players"].append(dict(score=0))
    assert goal_from_snapshot(snapshot) is None


@pytest.mark.parametrize("payload", [None, {}, dict(targets=[100], score=None),
    dict(targets=[float("nan")], score=1), dict(targets=[100], score=True),
    dict(targets=[100], score=1, multiplier=float("inf"))])
def test_missing_or_invalid_goal_data_falls_back(payload):
    assert SoloGoalState.from_payload(payload) is None


def test_last_move_search_keeps_one_optional_continuation_ply():
    turn = ms.TurnState(remaining_moves=1)
    assert ms.clamp_lookahead_depth(4, turn) == 1
    assert ms.clamp_lookahead_depth(4, turn, preserve_own_continuation=True) == 2


def test_overflow_clipping_preserves_final_continue_rule():
    goal = SoloGoalState((100, 500), score=98, overflow=False, continue_after_last=True)
    assert goal.credited_points(50) == 2
    assert replace(goal, score=498).credited_points(50) == 50


def test_verified_chain_is_not_erased_by_zero_generic_future_calibration(monkeypatch):
    monkeypatch.setattr(type(ms.learned_value.weights()), "future_scale", lambda *args: 0.0)
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=1)
    chain = ms._copy_evaluation_with_extra_move_chain_bonus(item, 10)
    assert priority(chain) - priority(item) == pytest.approx(10)
    assert priority(add_future(item)) == pytest.approx(priority(item))


@pytest.mark.parametrize("moves,expected", [(1, 0), (2, 5), (3, 5), (4, 1000)])
def test_solo_endgame_limits_learned_residual(moves, expected):
    turn = ms.TurnState(remaining_moves=moves)
    for sign in [-1, 1]:
        assert ms._bounded_solo_endgame_residual(sign * 1000, 20, context(), turn) == sign * expected
    assert ms._bounded_solo_endgame_residual(1000, 20, ms.StrategyContext("versus_2"), turn) == 1000


def test_certified_setup_retained_only_with_time_to_play_it(monkeypatch):
    monkeypatch.setattr(type(ms.learned_value.weights()), "future_scale", lambda *args: 0.0)
    item = plain_three()
    certified = replace(add_future(item), extra_setup_bonus=10, verified_extra_setup_bonus=10)
    assert priority(certified, moves=2) - priority(item, moves=2) == pytest.approx(10)
    assert priority(certified, moves=1) == pytest.approx(priority(item, moves=1))
    unverified = replace(certified, verified_extra_setup_bonus=0)
    assert priority(unverified, moves=2) == pytest.approx(priority(item, moves=2))


@pytest.mark.parametrize("reliable", [False, True])
def test_setup_certification_requires_reliable_followup(monkeypatch, reliable):
    item = plain_three()
    followup = replace(item, extra_moves=1, direct_extra_moves=int(reliable),
        intent_events=[] if reliable else [
            dict(type="uncertain_refill_boundary", after_cascade=0),
            dict(type="match", cascade=1, kind="four", color=ms.RED,
                 cells=[[0, c] for c in range(4)], tile_count=4)])
    monkeypatch.setattr(ms, "extra_move_chain_value", lambda *args, **kwargs: 10)
    monkeypatch.setattr(ms, "_best_next_extra_move_for_chain", lambda *args, **kwargs: followup)
    result = ms._with_extra_move_chain_bonus(item, "None", False, None, False,
        turn_state=ms.TurnState(remaining_moves=2), strategy_context=context())
    assert result.verified_extra_setup_bonus == (10 if reliable else 0)


@pytest.mark.parametrize("uncertain", [False, True])
def test_setup_credit_is_bounded_and_requires_known_source_board(monkeypatch, uncertain):
    item = plain_three()
    followup = replace(item, extra_moves=1, direct_extra_moves=1)
    if uncertain:
        item = replace(item, intent_events=[dict(type="uncertain_refill_boundary", after_cascade=0)])
    monkeypatch.setattr(ms, "extra_move_chain_value", lambda *args, **kwargs: 10000)
    monkeypatch.setattr(ms, "_best_next_extra_move_for_chain", lambda *args, **kwargs: followup)
    result = ms._with_extra_move_chain_bonus(item, "None", False, None, False,
        turn_state=ms.TurnState(remaining_moves=2), strategy_context=context())
    assert result.verified_extra_setup_bonus == (0 if uncertain else ms.EXTRA_MOVE_PRIORITY_WEIGHT)


@pytest.mark.parametrize("index", [0, 1])
def test_recorded_froggy_endgame_selects_eighteen_points(monkeypatch, index):
    from tools.rebuild_evaluation import build_states
    frames = json.loads((Path(__file__).parent / "fixtures/froggy_endgame.json").read_text())
    frame = frames[index]
    states = build_states(frame)
    monkeypatch.setattr(type(ms.learned_value.weights()), "future_scale", lambda *args: 0.0)
    # Preserve the old model's bias against the better move, independently of
    # whichever learned model happens to be installed on this machine.
    monkeypatch.setattr(ms, "_learned_residual", lambda e, *args:
        -45 if set((e.candidate.start, e.candidate.target)) == {(5, 5), (6, 5)} else -18)
    with ms.froggy_gather_region_active(7, True), ms.mushroom_multipliers_active(frame["mushroom_multipliers"]):
        candidates = ms.rank_moves(frame["board"], frame["special_board"],
            mode=states["mode"], score_rally_values=states["score_rally_values"],
            strategy_context=states["strategy_context"])
        ranked = ms.prioritize_ranked_moves(candidates, **states)
    best = ranked[0]
    assert {best.candidate.start, best.candidate.target} == {(5, 5), (6, 5)}
    assert best.instant_score * 4 == 18
    assert best.verified_extra_setup_bonus > 0
    if index == 1:
        assert priority(best, moves=1, ctx=states["strategy_context"]) == pytest.approx(4.5)


def test_terminal_threshold_does_not_invent_refill_or_extra_continuation():
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=1)
    ctx = context(solo_goal=SoloGoalState((1, 3), score=0, refill_moves=5, overflow=True))
    turn = ms.TurnState(remaining_moves=5)
    assert ms._evaluation_turn_state(item, turn, ctx).remaining_moves == 1
    assert ms.solo_goal_priority_moves([item], "None", BOOSTER, turn, None, ctx)[0].decision_gate == "solo_target_finish_gate"
    assert priority(add_future(item), moves=5, ctx=ctx) == pytest.approx(priority(item, moves=5, ctx=ctx))


@pytest.mark.parametrize("charge", [0, 7])
def test_runtime_finish_gate_preserves_perk_and_beats_ready_booster(monkeypatch, tmp_path, charge):
    seen = {}
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "create_debug_run_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "find_previous_debug_run", lambda path: None)
    monkeypatch.setattr(runtime, "write_move_debug_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *args: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *args: None)
    def forbidden(*args, **kwargs):
        raise AssertionError("a sure finish must not spend or rank an unnecessary perk")
    monkeypatch.setattr(runtime, "rank_selected_perk_actions", forbidden)
    candidate = plain_three().candidate
    board, specials = ms.swap_cells(candidate.board, candidate.special_board,
                                    candidate.start, candidate.target)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False, score_rally_values=None,
        strategy_mode="solo_6", solo_challenge=True,
        solo_goal_state=asdict(SoloGoalState((100,), score=97)),
        solo_cross_only=True,
        pre_scanned_board=board, pre_scanned_special_board=specials,
        selected_perks=(runtime.PERK_ENERGY_BOOST, runtime.PERK_NONE),
        cursor_return_position=(0, 0), jelly_zone_cells=(),
        debug_enabled=True, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False,
        booster_charge=charge, booster_maximum=7, remaining_moves=4,
        activate_booster_immediately=True,
        screen_state_read={"resolved": {"booster_ready": charge == 7, "our_score": 97,
                                       "sources": {"booster_ready": "memory", "our_score": "memory"}}},
        play_enabled=False,
    )
    runtime.run_check_best_move_request(request)
    assert seen["selected_action"] == "move"
    assert seen["decision_gate"] == "solo_target_finish_gate"
