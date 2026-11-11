"""Timed solo race: a ready booster fires before extras once the clock is short.

Player rule (2026-10-08). 31 of 263 Showdown/Party/Rumble matches (9/25-10/8)
ended with a full meter: extras kept going first until the clock fell under the
8 s low-clock rule, which then held the booster for good.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import memory_gui  # noqa: E402
import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402


def _board_with_direct_extra():
    # No matches anywhere; row 3 reads R R _ R with a red above the gap, so
    # dropping it in makes a direct match-4 extra.
    palette = [ms.GREEN, ms.YELLOW, ms.PURPLE, ms.ORANGE]
    board = [[palette[(row + col) % 4] for col in range(7)] for row in range(7)]
    board[3][0] = board[3][1] = board[3][3] = ms.RED
    board[2][2] = ms.RED
    return board


def _decide(monkeypatch, tmp_path, deadline, *, strategy=ms.STRATEGY_UNKNOWN, moves=4, seconds=12.0):
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
        turn_time_left=seconds, seconds_per_move=6.5, strategy_mode=strategy,
        screen_state_read={'resolved': {'booster_ready': True,
                                        'sources': {'booster_ready': 'memory'}}},
        booster_clock_deadline=deadline, play_enabled=False,
    )
    runtime.run_check_best_move_request(request)
    return seen['selected_action'], seen['decision_gate']


def test_deadline_fires_the_booster_over_a_direct_extra(monkeypatch, tmp_path):
    assert _decide(monkeypatch, tmp_path, True) == ('activate_booster', 'booster_clock_deadline_gate')


def test_without_the_deadline_the_extra_still_goes_first(monkeypatch, tmp_path):
    action, gate = _decide(monkeypatch, tmp_path, False)
    assert action == 'move'
    assert gate != 'booster_clock_deadline_gate'


def test_versus_deadline_keeps_the_direct_extra_first(monkeypatch, tmp_path):
    assert _decide(
        monkeypatch, tmp_path, True, strategy="versus_2", moves=1, seconds=13.467,
    ) == ("move", "true_extra_gate")


def test_deadline_leaves_room_for_one_extra_above_the_low_clock_line():
    assert memory_gui.BOOSTER_CLOCK_DEADLINE_SECONDS > memory_gui.LOW_TURN_TIME_SECONDS + 5.0
