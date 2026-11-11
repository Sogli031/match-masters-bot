from dataclasses import replace
import json
from pathlib import Path

import pytest

import move_strategy as ms
import runtime
from engine_refill import EngineRefill, ExactRefillSession


BLUE_SWAP = ((4, 6), (5, 6))
POINTS_SWAP = ((1, 0), (1, 1))
OTHER_SWAP = ((5, 3), (6, 3))
POINT_VALUES = {1: 1, 2: 5, 3: 5, 4: 5, 5: 5, 6: 5}


def _board():
    # Debug/runs 2026-09-19_03-08-20_779: one blue pickup at (4,6)->(5,6), which
    # the blue tier played as its only candidate without pricing the handover.
    return [
        [2, 4, 4, 2, 3, 6, 2],
        [5, 2, 4, 3, 6, 6, 5],
        [2, 6, 3, 5, 4, 3, 1],
        [1, 5, 6, 1, 2, 5, 5],
        [1, 4, 1, 5, 4, 4, 1],
        [4, 4, 2, 6, 1, 1, 3],
        [2, 1, 5, 3, 6, 6, 5],
    ]


def _empty_specials():
    return [[0] * 7 for _ in range(7)]


def _evaluations():
    ranked = ms.rank_moves(_board(), _empty_specials(), lookahead_depth=1)
    blue = [item for item in ranked if item.blue_cells > 0]
    plain = [item for item in ranked if item.blue_cells == 0]
    assert blue and len(plain) >= 2
    return blue[0], plain[0], plain[1]


def _handover():
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=3)
    return turn, ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)


def _key(evaluation):
    return (evaluation.candidate.start, evaluation.candidate.target)


def _order(monkeypatch, decorated, head_size, replies):
    monkeypatch.setattr(
        ms,
        "_versus_handover_reply",
        lambda evaluation, *args: replies[_key(evaluation)],
    )
    turn, context = _handover()
    return ms._versus_handover_threat_order(
        decorated, "None", False, None, False, turn, context, head_size=head_size
    )


def _pick(turn, meter, points=POINT_VALUES):
    _, context = _handover()
    ranked = ms.rank_moves(_board(), _empty_specials(), score_rally_values=points, lookahead_depth=1)
    return ms.prioritize_ranked_moves(
        ranked, score_rally_values=points, turn_state=turn, strategy_context=context,
        booster_state=ms.BoosterState(meter, 7, "memory"),
    )[0]


@pytest.mark.parametrize(("turn", "meter", "expected"), [
    (ms.TurnState(2, "memory", 4), 0, POINTS_SWAP),
    (ms.TurnState(2, "memory", is_final_round=True), 5, BLUE_SWAP),
    (ms.TurnState(2, "memory", is_final_round=True, time_left_seconds=6, seconds_per_move=4),
     5, POINTS_SWAP),
    (ms.TurnState(1, "memory", is_final_round=True, opponent_turn_follows=False), 5, POINTS_SWAP),
    (ms.TurnState(1, "memory", 5, time_left_seconds=8, seconds_per_move=4), 5, BLUE_SWAP),
])
def test_versus_compares_points_and_spendable_charge(turn, meter, expected):
    assert _key(_pick(turn, meter)) == expected


def test_opponent_completion_changes_the_handover_only_if_they_can_fire():
    turn = ms.TurnState(
        1, "memory", is_final_round=True, opponent_turn_follows=True,
        opponent_booster=ms.BoosterState(5, 7, "memory"), opponent_charge_colors=(2,),
        opponent_next_turn_moves=2,
    )
    points = {1: 0.8, 2: 1, 3: 0.7, 4: 1, 5: 1, 6: 1.3}
    assert _key(_pick(turn, 7, points)) == POINTS_SWAP
    for no_activation in (
        replace(turn, opponent_next_turn_moves=1),
        replace(turn, opponent_booster=ms.BoosterState(0, 7, "memory")),
        replace(turn, opponent_booster=None),
        replace(turn, opponent_turn_follows=False),
    ):
        assert _key(_pick(no_activation, 7, points)) == OTHER_SWAP


def test_safe_extra_does_not_simulate_an_opponent_reply(monkeypatch):
    blue, strong, _ = _evaluations()
    extra = replace(blue, direct_extra_moves=1)
    ordered = _order(monkeypatch, [(10, extra), (8, strong)], 2, {_key(strong): (40, False)})
    assert ordered[0] == (10, extra)
    assert "opp_reply=" not in ordered[0][1].explanation


@pytest.mark.parametrize(("exact", "safe_points", "safer_wins"), [
    (True, 10.0, True),
    (False, 10.0, False),
    (True, 2.0, False),
])
def test_large_handover_threat_can_outweigh_fill_without_sacrificing_points(
    monkeypatch, exact, safe_points, safer_wins
):
    # Multiplier Mushrooms 2026-11-11 17:57:48: the fill ranked 40.45
    # against 18.0 even though it scored less and left a much stronger board.
    fill, safer, _ = _evaluations()
    fill = replace(fill, exact_refill=exact, instant_score=3.0, direct_extra_moves=0, extra_moves=0)
    safer = replace(safer, exact_refill=exact, instant_score=safe_points, direct_extra_moves=0, extra_moves=0)
    ordered = _order(
        monkeypatch, [(40.45, fill), (18.0, safer)], 2,
        {_key(fill): (135.1, False), _key(safer): (15.6, False)},
    )
    assert _key(ordered[0][1]) == _key(safer if safer_wins else fill)


def test_recorded_mushroom_handover_avoids_the_red_extra():
    path = Path(__file__).parent / "fixtures" / "mushroom_versus_red_handover.json"
    frame = json.loads(path.read_text(encoding="utf-8"))
    board, specials = frame["board"], frame["special_board"]
    session = ExactRefillSession(
        EngineRefill.from_profile(frame["profile"]), board, special_board=specials,
        follow_moves=False, max_plies=3,
    )
    turn = ms.TurnState(
        1, "memory", moves_left_in_match=7, opponent_turn_follows=True,
        opponent_booster=ms.BoosterState(7, 7, "memory"), opponent_next_turn_moves=2,
        opponent_score_multiplier=5,
    )
    context = ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)
    mode = ms.GameMode.MULTIPLIER_MUSHROOMS
    with ms.exact_refill_active(session), ms.mushroom_multipliers_active(True), ms.score_multiplier_state(4, 1):
        ranked = ms.rank_moves(board, specials, mode=mode, strategy_context=context)
        ordered = ms.prioritize_ranked_moves(
            ranked, mode=mode, booster_state=ms.BoosterState(3, 7, "memory"),
            turn_state=turn, strategy_context=context,
        )
    assert set(_key(ordered[0])) == {(6, 2), (6, 3)}
    assert ordered[0].exact_refill
    assert "opp_charge_extra" not in ordered[0].explanation
    played = next(item for item in ordered if _key(item) == ((3, 5), (3, 6)))
    assert "opp_charge_extra" in played.explanation


def test_recorded_mushroom_handover_collects_blue_with_the_real_opponent_multiplier():
    path = Path(__file__).parent / "fixtures" / "magic_wand_refill.json"
    frame = json.loads(path.read_text(encoding="utf-8"))["after"]
    board, specials = frame["board"], frame["special_board"]
    session = ExactRefillSession(
        EngineRefill.from_profile(frame["profile"]), board, special_board=specials,
        follow_moves=False, max_plies=3,
    )
    turn = ms.TurnState(
        1, "memory", moves_left_in_match=5, opponent_turn_follows=True,
        opponent_booster=ms.BoosterState(7, 7, "memory"), opponent_next_turn_moves=2,
        opponent_score_multiplier=3,
    )
    context = ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2, score_strategy="ahead",
                                 our_score=599, opponent_score=112)
    mode = ms.GameMode.MULTIPLIER_MUSHROOMS
    with ms.exact_refill_active(session), ms.mushroom_multipliers_active(True), ms.score_multiplier_state(10, 1):
        ranked = ms.rank_moves(board, specials, mode=mode, strategy_context=context)
        ordered = ms.prioritize_ranked_moves(
            ranked, mode=mode, booster_state=ms.BoosterState(0, 7, "memory"),
            turn_state=turn, strategy_context=context,
        )
    assert set(_key(ordered[0])) == {(6, 3), (5, 3)}
    assert ordered[0].blue_cells == 3


@pytest.mark.parametrize(("fill_bonus", "exact", "adjusted_score"), [
    (10.0, True, 15.0),
    (0.0, True, 15.0),  # 3 sure blue: blue-first rule (2026-11-11)
    (10.0, False, 32.25),
])
def test_mushroom_setup_does_not_outweigh_a_spendable_fill(fill_bonus, exact, adjusted_score):
    fill, mushroom, _ = _evaluations()
    fill = replace(fill, blue_cells=3, direct_blue_cells=0, booster_fill_bonus=fill_bonus, exact_refill=exact)
    mushroom = replace(mushroom, multiplier_mushrooms=3, phase_adjusted_mode_bonus=17.25)
    _, context = _handover()
    with ms.mushroom_multipliers_active(True), ms.score_multiplier_state(5, 1):
        ranked = ms._versus_mushroom_fill_order(
            [(40.4544, fill), (32.25, mushroom)], ms.GameMode.MULTIPLIER_MUSHROOMS,
            ms.BoosterState(4, 7, "memory"), context,
        )
    assert ranked[0][0] == 40.4544
    assert ranked[1][0] == adjusted_score


def test_captured_versus_refill_updates_points_and_keeps_the_safe_extra():
    path = Path(__file__).parent / "fixtures" / "square_versus_players" / "000.json"
    frame = json.loads(path.read_text(encoding="utf-8"))
    board, specials = frame["board"], frame["special_board"]
    session = ExactRefillSession(
        EngineRefill.from_profile(frame["profile"]), board, special_board=specials,
        follow_moves=False, max_plies=3,
    )
    turn, context = _handover()
    booster = ms.BoosterState(3, 7, "memory")

    def pick():
        candidates = ms.rank_moves(board, specials, allow_square_matches=True, lookahead_depth=1,
                                   strategy_context=context)
        return ms.prioritize_ranked_moves(
            candidates, allow_square_matches=True, booster_state=booster, turn_state=turn,
            strategy_context=context,
        )[0]

    plain = pick()
    with ms.exact_refill_active(session):
        exact = pick()
    assert _key(plain) == _key(exact) == ((3, 4), (4, 4))
    assert plain.instant_score == 11 and exact.instant_score == 15
    assert exact.exact_refill and ms.has_reliable_same_move_extra(exact)


@pytest.mark.parametrize(("moves", "exact", "bonus_clear", "expected", "gate"), [
    (2, True, False, POINTS_SWAP, "exact_refill_priority"),
    (1, True, True, BLUE_SWAP, "exact_refill_priority"),
    (1, False, True, POINTS_SWAP, "score_gate"),
])
def test_runtime_late_refill_uses_versus_policy(monkeypatch, tmp_path, moves, exact, bonus_clear,
                                               expected, gate):
    class Session:
        blue_missing = 7
        moves_left = moves
        solo = False

        def knows(self, board):
            return [list(row) for row in board] == _board()

    session = Session()
    simulate = ms._simulate_created_candidate_cached

    def simulate_with_known_drop(board, candidate, *args, **kwargs):
        active = ms._EXACT_REFILL is session
        with ms.exact_refill_active(None):
            result = simulate(board, candidate, *args, **kwargs)
        if active and result is not None and session.knows(board):
            result = replace(result, cleared_color_counts=dict(result.cleared_color_counts))
            result.exact_refill_supported = exact
            if bonus_clear and (candidate.start, candidate.target) == BLUE_SWAP:
                result.cleared_color_counts[2] = 4
                result.cleared_cells += 4
        return result

    seen = {}
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate_with_known_drop)
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "create_debug_run_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "find_previous_debug_run", lambda path: None)
    monkeypatch.setattr(runtime, "write_move_debug_report", lambda *a, **kw: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kw: seen.update(kw))
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *a: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *a: None)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False, score_rally_values=POINT_VALUES,
        pre_scanned_board=_board(), pre_scanned_special_board=_empty_specials(),
        selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE), cursor_return_position=(0, 0),
        allow_perk_activation=False, force_no_booster=True, debug_enabled=True, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False, booster_charge=0, booster_maximum=7,
        remaining_moves=moves, total_rounds=3, current_round=1, strategy_mode="versus_2",
        late_exact_refill=lambda: session, play_enabled=False,
    )
    runtime.run_check_best_move_request(request)
    assert seen["selected_action"] == "move"
    assert seen["decision_gate"] == gate
    assert _key(seen["evaluation"]) == expected


def test_handover_denial_cannot_override_material_priority_gap(monkeypatch):
    strong, weak, _ = _evaluations()
    replies = {_key(strong): (100.0, False), _key(weak): (0.0, False)}
    # A gap above the largest cap (VERSUS_HANDOVER_LARGE_REPLY_MAX_SACRIFICE).
    gap = ms.VERSUS_HANDOVER_LARGE_REPLY_MAX_SACRIFICE + 1.0
    ordered = _order(monkeypatch, [(7.0 + gap, strong), (7.0, weak)], 2, replies)
    assert _key(ordered[0][1]) == _key(strong)


def test_handover_avoids_large_reply_for_small_priority_cost(monkeypatch):
    strong, weak, _ = _evaluations()
    replies = {_key(strong): (41.0, False), _key(weak): (5.0, False)}
    ordered = _order(monkeypatch, [(12.6, strong), (9.6, weak)], 2, replies)
    assert _key(ordered[0][1]) == _key(weak)


def test_handover_can_trade_more_for_denial_when_both_boards_are_known(monkeypatch):
    strong, weak, _ = _evaluations()
    replies = {_key(strong): (25.0, False), _key(weak): (5.0, False)}
    # Reply gap 20 -> 0.5 * 20 = 10: capped at 8 without the exact refill,
    # 10 with both boards known (cap 12); a priority gap of 9 lies between.
    uncertain = _order(monkeypatch, [(18, strong), (9, weak)], 2, replies)
    exact = _order(monkeypatch, [
        (18, replace(strong, exact_refill=True)),
        (9, replace(weak, exact_refill=True)),
    ], 2, replies)
    assert _key(uncertain[0][1]) == _key(strong)
    assert _key(exact[0][1]) == _key(weak)


def test_defensive_threat_uses_the_priced_reply_value(monkeypatch):
    blue, _strong, _weak = _evaluations()
    replies = ms._versus_handover_opponent_replies(blue, "None", False, None, False, {}, {}, {})
    reply_value = ms._best_opponent_reply_value(replies)
    extras = max(
        [max(result.extra_moves, result.direct_extra_moves) for _item, result in replies],
        default=0.0,
    )
    threat = ms._versus_handover_opponent_threat(blue, "None", False, None, False, {}, {}, {})
    assert threat == ms.VERSUS_DEFENSIVE_OPP_EXTRA_WEIGHT * extras + reply_value


def test_defensive_threat_and_penalty_price_the_same_known_opponent_meter():
    # Both handover paths must read the opponent's meter from turn_state: the
    # defensive reorder used to call _best_opponent_reply_value(replies) bare.
    blue, _strong, _weak = _evaluations()
    turn = ms.TurnState(
        1, "memory", 3, opponent_booster=ms.BoosterState(6, 7, "memory"),
        opponent_charge_colors=(2,), opponent_next_turn_moves=2,
    )
    replies = ms._versus_handover_opponent_replies(blue, "None", False, None, False, {}, {}, {})
    extras = max(
        [max(result.extra_moves, result.direct_extra_moves) for _item, result in replies],
        default=0.0,
    )
    penalty = ms._versus_handover_opponent_reply_value(
        blue, "None", False, None, False, {}, {}, {}, turn
    )
    threat = ms._versus_handover_opponent_threat(
        blue, "None", False, None, False, {}, {}, {}, turn
    )
    assert penalty != ms._best_opponent_reply_value(replies)
    assert threat == ms.VERSUS_DEFENSIVE_OPP_EXTRA_WEIGHT * extras + penalty
