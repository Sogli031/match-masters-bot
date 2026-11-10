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


def test_automatic_play_takes_a_sure_finish_over_a_higher_heuristic_score():
    finish = plain_three()
    better = replace(finish, candidate=replace(finish.candidate, start=(0, 0)), instant_score=2, score=100)
    ctx = context(solo_goal=SoloGoalState((100,), score=97))
    ranked = ms.prioritize_ranked_moves([finish, better], booster_state=BOOSTER,
                                        turn_state=ms.TurnState(remaining_moves=2), strategy_context=ctx)
    assert ranked[0].candidate == finish.candidate
    assert ranked[0].decision_gate == "solo_target_finish_gate"


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
        dict(type="uncertain_refill_boundary", after_cascade=0)])
    assert not ms._solo_goal_crosses(random, "None", None, ctx)
    assert not ms._solo_goal_crosses(item, ms.GameMode.CHEST, None, ctx)


def test_approximate_refill_can_only_certify_the_initiating_match():
    item = plain_three()
    guess = replace(item, instant_score=10, cleared_color_counts={ms.RED: 10}, approximate_refill=True)
    ctx = context(solo_goal=SoloGoalState((100,), score=95))
    assert ms._solo_goal_certain_points(guess, "None", None, ctx) == 3
    assert not ms._solo_goal_crosses(guess, "None", None, ctx)


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


def test_snapshot_uses_engine_fields_when_the_normalized_goal_fields_are_missing():
    snapshot = {"state": {
        "is_singleplayer_board": True,
        "players": [{"score": 99}],
        "rules": {"solo_targets": None, "solo_refill_mode": None, "moves_per_turn": None,
                  "engine_fields": {"soloTargets": [100, 200], "soloRefillMode": True,
                                    "movesPerTurn": 4}},
    }}
    assert SoloGoalState.from_payload(goal_from_snapshot(snapshot)) == SoloGoalState(
        (100, 200), 99, refill_moves=4,
    )


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
    if index == 1:
        assert best.verified_extra_setup_bonus == 0
        assert priority(best, moves=1, ctx=states["strategy_context"]) == pytest.approx(4.5)
    else:
        assert best.verified_extra_setup_bonus > 0


def test_terminal_threshold_does_not_invent_refill_or_extra_continuation():
    item = replace(plain_three(), extra_moves=1, direct_extra_moves=1)
    ctx = context(solo_goal=SoloGoalState((1, 3), score=0, refill_moves=5, overflow=True))
    turn = ms.TurnState(remaining_moves=5)
    assert ms._evaluation_turn_state(item, turn, ctx).remaining_moves == 1
    assert ms.solo_goal_priority_moves([item], "None", BOOSTER, turn, None, ctx)[0].decision_gate == "solo_target_finish_gate"
    assert priority(add_future(item), moves=5, ctx=ctx) == pytest.approx(priority(item, moves=5, ctx=ctx))


@pytest.mark.parametrize("charge", [0, 7])
@pytest.mark.parametrize("button", [False, True])
@pytest.mark.parametrize("completed", [False, True])
def test_runtime_finish_gate_preserves_perk_and_beats_ready_booster(monkeypatch, tmp_path, charge, button,
                                                                   completed):
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
        solo_goal_state=asdict(SoloGoalState((100,), score=100 if completed else 97)),
        solo_cross_only=button,
        engine_plan_move=((0, 0), (0, 1)),
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
    assert seen["selected_action"] == ("none" if completed else "move")
    assert seen["decision_gate"] == (
        ("solo_target_no_move_gate" if button else "solo_target_complete_gate")
        if completed else "solo_target_finish_gate"
    )


def test_completed_target_has_no_further_progress_and_allows_explicit_continuation():
    item = plain_three()
    done = SoloGoalState((100, 500), score=500)
    assert done.progress_points(30) == 0
    assert not ms.prioritize_ranked_moves([item], strategy_context=context(solo_goal=done))
    assert ms.prioritize_ranked_moves(
        [item], strategy_context=context(solo_goal=replace(done, continue_after_last=True))
    )


def test_last_move_crosses_current_stage_for_refill_without_counting_clipped_surplus():
    crossing = plain_three()
    tempting = replace(crossing, instant_score=1, score=100, blue_cells=7)
    goal = SoloGoalState((100, 200), score=98, overflow=False, refill_moves=5)
    ranked = ms.prioritize_ranked_moves(
        [tempting, crossing], turn_state=ms.TurnState(1), strategy_context=context(solo_goal=goal),
    )
    assert ranked[0].instant_score == 3
    assert ranked[0].decision_gate == "solo_target_refill_gate"
    assert goal.after_points(1000).next_target == 200
    assert goal.after_points(1000).score == 100


@pytest.mark.parametrize(("meter", "moves", "expected_blue"), [(0, 4, 0), (5, 2, 3), (5, 1, 0), (7, 3, 0)])
def test_paid_moves_compare_points_against_spendable_charge(meter, moves, expected_blue):
    points = plain_three()
    points = replace(points, instant_score=30, score=30)
    blue = replace(plain_three(), instant_score=3, score=6, blue_bonus=3,
                   blue_cells=3, direct_blue_cells=3,
                   candidate=replace(points.candidate, start=(5, 5), target=(5, 6)))
    ctx = context(solo_goal=SoloGoalState((1000,), 0))
    turn = ms.TurnState(moves)
    ranked = ms.prioritize_ranked_moves(
        [blue, points], booster_state=ms.BoosterState(meter, 7),
        turn_state=turn, strategy_context=ctx,
    )
    assert ranked[0].blue_cells == expected_blue


def test_exact_extra_plan_can_choose_the_line_with_a_paid_winning_followup(monkeypatch):
    first = plain_three().candidate
    second = replace(first, start=(1, 1), target=(1, 2))
    def result(candidate, marker, points, extra):
        return ms.SimulationResult(
            candidate, [[marker]], [[0]], cleared_cells=points,
            cleared_color_counts={ms.RED: points}, extra_moves=extra, direct_extra_moves=extra,
        )
    a, b = result(first, 1, 4, 1), result(second, 2, 3, 1)
    rows = [(ms.evaluate_simulation(r, "None", include_future_value=False), r) for r in (a, b)]
    def simulate(board, candidate):
        following = result(candidate, 3, 4 if board == [[1]] else 6, int(board == [[1]]))
        following.exact_refill_supported = True
        return following
    monkeypatch.setattr(ms, "generate_candidates", lambda board, specials: [first] if board != [[3]] else [])
    ctx = context(solo_goal=SoloGoalState((100,), 91))
    assert ms._plan_exact_extra_sequence(
        rows, simulate, object(), "None", False, None, known=lambda result: True,
        strategy_context=ctx, turn_state=ms.TurnState(1),
    ) is rows[1][0]
    assert ms._plan_exact_extra_sequence(
        rows, simulate, object(), "None", False, None, known=lambda result: True,
        strategy_context=ctx, turn_state=ms.TurnState(1, time_left_seconds=2, seconds_per_move=2),
    ) is None


def test_exact_refill_cannot_replace_a_goal_pick_with_a_paid_blue_move(monkeypatch):
    top = plain_three()
    other = replace(top, candidate=replace(top.candidate, start=(0, 0), target=(0, 1)), blue_cells=3)
    from types import SimpleNamespace
    session = SimpleNamespace(knows=lambda board: True, moves_left=2, blue_missing=3, solo=True)
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", lambda board, candidate, *args:
                        SimpleNamespace(blue_cells=3 if candidate == other.candidate else 0,
                                        extra_moves=0, board="after", special_board=[]))
    monkeypatch.setattr(ms, "generate_candidates", lambda *args: [])
    with ms.exact_refill_active(session):
        assert ms.exact_refill_choice([top, other], "root", []) == (other, "plave")
        assert ms.exact_refill_choice(
            [top, other], "root", [], strategy_context=context(solo_goal=SoloGoalState((100,), 70)),
            turn_state=ms.TurnState(2),
        ) is None


def test_winning_perk_beats_wasteful_teleport_and_can_be_used_with_ready_booster():
    baseline = plain_three()
    candidate = baseline.candidate
    board, specials = ms.swap_cells(candidate.board, candidate.special_board,
                                    candidate.start, candidate.target)
    ctx = context(solo_goal=SoloGoalState((100,), 92))
    decision = runtime.decide_auto_perk(
        board, specials, (ms.PERK_TELEPORT, ms.PERK_REMOVE_CROSS), normal_baseline=baseline,
        decision_context=ms.PerkDecisionContext(turn=ms.TurnState(1), booster=BOOSTER),
        strategy_context=ctx, booster_active=True,
    )
    assert decision.gate == "solo_perk_finishes_goal_gate"
    assert decision.selected.perk_key == ms.PERK_REMOVE_CROSS
    assert decision.selected.horizon_value == 8
    saved = runtime.decide_auto_perk(
        board, specials, (ms.PERK_TELEPORT, ms.PERK_NONE), normal_baseline=baseline,
        decision_context=ms.PerkDecisionContext(turn=ms.TurnState(1), booster=BOOSTER),
        strategy_context=ctx,
    )
    assert saved.selected is None


def test_perk_and_a_known_followup_can_finish_without_claiming_an_unknown_drop():
    swipe = plain_three()
    ctx = context(solo_goal=SoloGoalState((100,), 94))
    decision_context = ms.PerkDecisionContext(
        turn=ms.TurnState(1), objective=ms.PerkObjective.SOLO_GOAL,
    )
    action = ms.PerkAction(ms.PERK_MINI_COBRA, 1, 0, 0, 0, 0, follow_up=swipe,
                           effect_evaluation=swipe, follow_up_certain=True)
    winning = ms._with_perk_objective_value(action, swipe, decision_context, "None", None, ctx)
    uncertain = ms._with_perk_objective_value(
        replace(action, follow_up_certain=False), swipe, decision_context, "None", None, ctx,
    )
    assert winning.goal_finish and winning.horizon_value == 6
    assert not uncertain.goal_finish and uncertain.horizon_value < 6


def test_exact_refill_rejects_same_move_count_from_a_different_solo_snapshot():
    from square_solo_live import exact_refill_session
    snapshot = {"state": {"moves": 1, "moves_made_this_turn": 3,
                          "players": [{"score": 95, "energy": 2}]}}
    profile = {"state": {"moves": 1, "<MovesMadeThisTurn>k__BackingField": 4},
               "players": [{"model": {"score": 101, "energy": 2}}]}
    session, reason = exact_refill_session(
        None, None, snapshot, [], resting_profile=profile, validate_solo_state=True,
    )
    assert session is None and "nisu iz istog poteza" in reason


@pytest.mark.parametrize(("points", "selected_action"), [(1, "move"), (6, "activate_booster")])
def test_last_solo_swipe_compares_dragon_as_a_paid_move(monkeypatch, tmp_path, points, selected_action):
    seen = {}
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "create_debug_run_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "find_previous_debug_run", lambda path: None)
    monkeypatch.setattr(runtime, "write_move_debug_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *args: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *args: None)
    item = plain_three()
    monkeypatch.setattr(runtime, "choose_dragon_move",
                        lambda *args, **kwargs: replace(item, instant_score=points, score=points))
    candidate = item.candidate
    board, specials = ms.swap_cells(candidate.board, candidate.special_board,
                                    candidate.start, candidate.target)
    runtime.run_check_best_move_request(runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False, score_rally_values=None,
        strategy_mode="solo_6", solo_challenge=True, solo_goal_state=asdict(SoloGoalState((100,), 90)),
        pre_scanned_board=board, pre_scanned_special_board=specials,
        selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE), cursor_return_position=(0, 0),
        jelly_zone_cells=(), debug_enabled=True, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False, booster_charge=7, booster_maximum=7,
        remaining_moves=1, booster_action_mode=runtime.BOOSTER_ACTION_DRAGON,
        screen_state_read={"resolved": {"booster_ready": True, "sources": {"booster_ready": "memory"}}},
        play_enabled=False,
    ))
    assert seen["selected_action"] == selected_action
    if selected_action == "move":
        assert seen["decision_gate"] == "solo_dragon_progress_below_move_gate"


def test_unused_move_energy_prefers_a_finish_that_keeps_the_turn():
    plain = plain_three()
    extra = replace(plain, candidate=replace(plain.candidate, start=(5, 5), target=(5, 6)),
                    extra_moves=1, direct_extra_moves=1)
    assert ms.has_reliable_same_move_extra(extra)
    goal = SoloGoalState((100,), score=97)
    turn = ms.TurnState(remaining_moves=3)
    ranked = ms.solo_goal_priority_moves([plain, extra], "None", BOOSTER, turn, None,
                                         context(solo_goal=replace(goal, unused_moves_energy=1)))
    assert ranked[0].candidate == extra.candidate
    assert ranked[0].decision_gate == "solo_target_finish_gate"
    # Without energy the finish order is untouched (the bot's own order wins).
    ranked = ms.solo_goal_priority_moves([plain, extra], "None", BOOSTER, turn, None, context(solo_goal=goal))
    assert ranked[0].candidate == plain.candidate
