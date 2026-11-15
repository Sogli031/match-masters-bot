"""Checkmate Charles: the exact plan prices the booster meter.

The solo plans were switched off 2026-11-10 because they played for points
with the meter at 0 and threw charge away. With Charles the meter keeps its
real charge and a full one is worth an activation (CHARLES_FIRE_VALUE).
"""
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategy_lab import planner
import square_solo_live as sl


def _state(current, fired=0, score=100, price=44):
    return {"score": score, "turn_state": {"remaining_moves": 3},
            "booster_state": {"current": current, "maximum": 7},
            "booster_fire_value": price, "booster_fired": fired}


def test_line_value_counts_charge_pro_rata_and_banked_meters():
    assert planner.Line(_state(0)).value == 100
    assert abs(planner.Line(_state(7 // 2 + 0.5)).value - (100 + 44 * 0.5)) < 1e-9
    assert planner.Line(_state(0, fired=2)).value == 100 + 88


def test_without_a_price_the_value_is_the_score():
    state = _state(5, price=None)
    assert planner.Line(state).value == 100


def test_full_meter_is_banked_and_starts_again():
    banked = planner._bank_full_meter(_state(7))
    assert banked["booster_state"]["current"] == 0 and banked["booster_fired"] == 1
    assert planner._bank_full_meter(_state(6))["booster_fired"] == 0


def test_charles_eligible_only_solo_with_charles():
    charles = {"rules": {"pvp_mode": 1}, "players": [{"player_type": 0, "special_ability_type": 54}]}
    assert sl.charles_eligible(charles)
    assert not sl.charles_eligible(dict(charles, rules={"pvp_mode": 2}))
    assert not sl.charles_eligible({"rules": {"pvp_mode": 1},
                                    "players": [{"player_type": 0, "special_ability_type": 35}]})


def test_full_meter_with_booster_auto_offers_only_the_booster():
    state = {"booster_auto": True, "booster_state": {"current": 7, "maximum": 7},
             "board": [[1] * 7 for _ in range(7)], "special_board": [[0] * 7 for _ in range(7)]}
    assert planner.actions(state) == [{"kind": "booster"}]


def test_full_meter_with_booster_hold_also_offers_swipes():
    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    state = {"mode": "none", "booster_auto": True, "booster_hold": True,
             "booster_state": {"current": 7, "maximum": 7},
             "board": board, "special_board": [[0] * 7 for _ in range(7)]}
    offered = planner.actions(state)
    assert offered[0] == {"kind": "booster"} and len(offered) > 1
    assert planner.actions(dict(state, booster_hold=False)) == [{"kind": "booster"}]
    assert {"kind": "booster"} not in planner.actions(dict(state, booster_state={"current": 6, "maximum": 7}))


def test_charles_hold_plan_has_its_own_budget():
    assert sl.CHARLES_HOLD_SECONDS > 0


def test_carried_plan_key_needs_board_rng_and_moves():
    class Model:
        class rng:
            counter = 5
    state = {"board": [[1, 2], [3, 4]], "special_board": [[0, 0], [0, 0]], "engine_refill": Model,
             "turn_state": {"remaining_moves": 3}}
    other = dict(state, turn_state={"remaining_moves": 2})
    assert sl._plan_key(state) == sl._plan_key(dict(state))
    assert sl._plan_key(state) != sl._plan_key(other)
    assert sl._plan_key(state) == sl._plan_key(dict(state, perks={3: 0}))
    assert sl._plan_key(state) != sl._plan_key(dict(state, perks={3: 1}))
    assert sl._plan_key(state) != sl._plan_key(dict(state, booster_state={"current": 7, "maximum": 7}))


def test_charles_plan_budgets():
    assert sl.CHARLES_FIRST_SECONDS > sl.CHARLES_NEXT_SECONDS > 0


def test_planned_swipe_keeps_its_direction():
    """2026-11-15 00:29:53: the plan's (4,1)->(5,1) was swiped (5,1)->(4,1)."""
    import types
    import move_strategy as ms
    import runtime

    board = [[1] * 7 for _ in range(7)]
    cand = ms.MoveCandidate((5, 1), (4, 1), ms.Direction("up"), board, [[0] * 7 for _ in range(7)])
    evaluation = types.SimpleNamespace(candidate=cand)
    ordered = runtime.promote_engine_plan_move([evaluation], ((4, 1), (5, 1)))
    assert ordered[0] is evaluation
    played = ms.oriented_swap_candidate(evaluation)
    assert tuple(played.start) == (4, 1) and tuple(played.target) == (5, 1)


@pytest.mark.parametrize("kind", ["teleport", "energy_boost", None])
def test_live_runtime_plays_only_the_planned_action(monkeypatch, kind):
    import move_strategy as ms
    import runtime

    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    calls = []
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *args: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *args: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kwargs: None)
    monkeypatch.setattr(runtime, "play_best_move_with_cursor_restore",
                        lambda start, direction, score, **kwargs: calls.append((start, direction)))

    def execute(action, slots, **kwargs):
        assert kwargs["planned"]
        assert slots[action.slot_number - 1] == kind
        calls.append(action.target if kind == "teleport" else runtime.oriented_swipe(action.follow_up))
        return True

    monkeypatch.setattr(runtime, "execute_verified_perk_action", execute)
    pair = ((0, 1), (6, 6)) if kind == "teleport" else ((1, 1), (0, 1))
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None, selected_perks=(runtime.PERK_TELEPORT, runtime.PERK_ENERGY_BOOST),
        pre_scanned_board=board, pre_scanned_special_board=[[0] * 7 for _ in range(7)],
        engine_plan_move=pair, engine_plan_perk=kind, engine_plan_owns_goal=True,
        cursor_return_position=(0, 0), force_no_booster=True, allow_perk_activation=True,
        debug_enabled=False, lookahead_candidates=0, include_future_value=False,
    )
    result = runtime.run_check_best_move_request(request)
    if kind == "teleport":
        assert calls == [[[0, 1], [6, 6]]]
        assert not result.turn_consumed
    else:
        assert calls == [((1, 1), ms.Direction.UP)]
    if kind:
        assert result.clear_used_perk_key == kind
        assert runtime.engine_plan_perk_action(
            replace(request, selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE)), []
        ) is None
