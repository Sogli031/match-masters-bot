"""Timed race, full meter, turn ended by the clock: booster before extras.

Point 4 of the 2026-11-10 analysis: in races 913 moves were played on a full
meter (752 of them extras) and 22% of the collected blue burned there, while
TIME_BOUND_TURNS already says an extra is worth nothing in a turn the clock
ends. a) the booster goes first there; b) a move that only fills the meter
gets no fill bonus once the clock leaves no move to fire it with.
"""

from dataclasses import replace
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402
from tests.test_booster_clock_deadline import _board_with_direct_extra  # noqa: E402


def _decide(monkeypatch, tmp_path, *, moves, seconds, strategy="solo_6", solo_challenge=False,
            immediate=False):
    seen = {}
    monkeypatch.setattr(runtime, 'apply_board_profile', lambda profile: None)
    monkeypatch.setattr(runtime, 'create_debug_run_dir', lambda: tmp_path)
    monkeypatch.setattr(runtime, 'find_previous_debug_run', lambda path: None)
    monkeypatch.setattr(runtime, 'write_move_debug_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.move_telemetry, 'record', lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(runtime, 'resolve_ufo_state', lambda *args: None)
    monkeypatch.setattr(runtime, 'resolve_mixy_meow_state', lambda *args: None)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode='auto', selected_profile='regular',
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None, selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE),
        cursor_return_position=(0, 0), pre_scanned_board=_board_with_direct_extra(),
        pre_scanned_special_board=[[0] * 7 for _ in range(7)],
        jelly_zone_cells=(), allow_perk_activation=False,
        debug_enabled=True, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False,
        booster_charge=7, booster_maximum=7, remaining_moves=moves,
        turn_time_left=seconds, seconds_per_move=ms.TIME_BOUND_SECONDS_PER_MOVE_DEFAULT,
        screen_state_read={'resolved': {'booster_ready': True,
                                        'sources': {'booster_ready': 'memory'}}},
        strategy_mode=strategy, solo_challenge=solo_challenge,
        activate_booster_immediately=immediate, play_enabled=False,
    )
    runtime.run_check_best_move_request(request)
    return seen['selected_action'], seen['decision_gate']


def test_time_bound_race_fires_the_full_meter_before_a_plain_extra(monkeypatch, tmp_path):
    # 12 s at 3 s a move allow 4 moves, the counter holds 6: the clock ends it.
    assert _decide(monkeypatch, tmp_path, moves=6, seconds=12.0) == (
        'activate_booster', runtime.TIME_BOUND_BOOSTER_GATE)


@pytest.mark.parametrize("kwargs", [
    dict(moves=6, seconds=60.0),                                   # counter ends the turn
    dict(moves=6, seconds=12.0, strategy="versus_2"),              # versus untouched
    dict(moves=6, seconds=12.0, solo_challenge=True),              # Solo Challenge untouched
])
def test_extra_still_goes_first_outside_a_time_bound_race(monkeypatch, tmp_path, kwargs):
    action, gate = _decide(monkeypatch, tmp_path, **kwargs)
    assert action == 'move'
    assert gate != runtime.TIME_BOUND_BOOSTER_GATE


def test_toggle_keeps_its_own_gate_name(monkeypatch, tmp_path):
    assert _decide(monkeypatch, tmp_path, moves=6, seconds=12.0, immediate=True) == (
        'activate_booster', 'booster_immediate_toggle_gate')


def test_climb_dealt_colour_extra_still_precedes_the_time_bound_booster():
    match = ms.MatchGroup(frozenset((1, col) for col in range(4)), ms.YELLOW, "four")
    from types import SimpleNamespace
    extra = SimpleNamespace(direct_extra_moves=1.0, extra_moves=1.0, disco_moves=0,
                            cascade_matches=[[match]], decision_gate="score_gate")
    action, chosen, gate = runtime.select_booster_action_with_gate(
        [extra], True, True, multiplier_extra_colors=(ms.YELLOW, ms.PURPLE))
    assert (action, gate) == ("move", "multiplier_color_extra_before_booster_gate")


def test_time_bound_helper_scope():
    turn = ms.TurnState(6, "memory", time_left_seconds=12.0,
                        seconds_per_move=ms.TIME_BOUND_SECONDS_PER_MOVE_DEFAULT)
    assert runtime.time_bound_booster_first(turn, ms.StrategyContext("solo_6"))
    assert not runtime.time_bound_booster_first(turn, ms.StrategyContext("solo_6", solo_challenge=True))
    assert not runtime.time_bound_booster_first(turn, ms.StrategyContext("versus_2"))
    assert not runtime.time_bound_booster_first(replace(turn, time_left_seconds=60.0),
                                                ms.StrategyContext("solo_6"))


# b) -------------------------------------------------------------------------

def _race_pick(seconds, **turn):
    from tests.test_solo_challenge_goals import _last_move_pair
    points, blue = _last_move_pair()
    turn_state = ms.TurnState(3, "memory", time_left_seconds=seconds,
                              seconds_per_move=ms.TIME_BOUND_SECONDS_PER_MOVE_DEFAULT, **turn)
    return ms.prioritize_ranked_moves(
        [blue, points], booster_state=ms.BoosterState(6, 7, "memory"),
        turn_state=turn_state, strategy_context=ms.StrategyContext("solo_6"),
    )[0]


def test_fill_with_no_clock_left_to_fire_earns_nothing():
    # 10 s - 3 s for this move = 7 s: under the 8 s low-clock hold.
    late = _race_pick(10.0)
    assert late.instant_score == 8
    assert late.booster_fill_bonus == 0
    # With time to fire the fill still wins over the plain points.
    assert _race_pick(30.0).blue_cells == 3


def test_fill_keeps_its_value_when_a_later_round_follows():
    assert _race_pick(10.0, current_round=1, total_rounds=3).blue_cells == 3


def test_dead_fill_line_tracks_the_gui_low_clock_hold():
    import memory_gui
    assert ms.TIME_BOUND_LOW_CLOCK_HOLD_SECONDS == memory_gui.LOW_TURN_TIME_SECONDS
