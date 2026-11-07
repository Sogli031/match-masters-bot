"""Guaranteed extras precede charge moves on the reported supersize board."""
import pytest
import move_strategy as ms
import runtime

BOARD = [[4, 4, 5, 4, 5, 5, 4, 6], [4, 1, 2, 1, 4, 5, 4, 1], [5, 1, 6, 3, 5, 2, 1, 2], [1, 2, 2, 4, 3, 2, 3, 1], [6, 6, 4, 6, 2, 4, 5, 2], [2, 1, 1, 3, 6, 1, 3, 6], [5, 3, 3, 6, 4, 3, 3, 2], [3, 6, 3, 3, 5, 2, 1, 2]]
SPECIALS = [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 3, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 3, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]]


@pytest.mark.parametrize("solo_challenge,time_left", [(True, 1400), (False, 30), (False, 7)])
def test_guaranteed_extra_precedes_charge_in_solo_rush(solo_challenge, time_left):
    candidates = ms.rank_moves(BOARD, SPECIALS, include_future_value=False)
    assert any(ms.has_guaranteed_true_extra(item) for item in candidates)
    assert any(item.blue_cells > 0 and not ms.has_guaranteed_true_extra(item)
               for item in candidates)
    ranked = ms.prioritize_ranked_moves(
        candidates, booster_state=ms.BoosterState(6, 7, source="memory"),
        turn_state=ms.TurnState(remaining_moves=5, time_left_seconds=time_left,
                                seconds_per_move=6.5),
        strategy_context=ms.StrategyContext("solo_6", booster_rush=True,
                                           solo_challenge=solo_challenge))
    assert ranked
    assert ms.has_guaranteed_true_extra(ranked[0])


def test_runtime_keeps_extra_ahead_of_charge(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "create_debug_run_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "find_previous_debug_run", lambda path: None)
    monkeypatch.setattr(runtime, "write_move_debug_report", lambda *a, **kw: None)
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kw: seen.update(kw))
    monkeypatch.setattr(runtime, "resolve_ufo_state", lambda *a: None)
    monkeypatch.setattr(runtime, "resolve_mixy_meow_state", lambda *a: None)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="supersize",
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None,
        pre_scanned_board=BOARD, pre_scanned_special_board=SPECIALS,
        selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE),
        cursor_return_position=(0, 0), allow_perk_activation=False,
        debug_enabled=True, debug_images_enabled=False, lookahead_candidates=0,
        include_future_value=False, booster_charge=6, booster_maximum=7,
        remaining_moves=5, strategy_mode="solo_6", showdown_booster_rush=True,
        solo_challenge=True, turn_time_left=1400, seconds_per_move=6.5,
        play_enabled=False)
    runtime.run_check_best_move_request(request)
    assert seen["selected_action"] == "move"
    assert seen["decision_gate"] != "showdown_booster_rush_gate"
    assert ms.has_guaranteed_true_extra(seen["evaluation"])
