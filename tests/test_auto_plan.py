import copy
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from auto_plan import (AutoPlan, PlanningCancelled, planning_cancellation,
                       snapshot_plan_key)
import move_strategy as ms


def snapshot():
    return {'board': [[1, 2], [3, 4]], 'special_board': [[0, 0], [0, 0]],
            'board_object': 'match1', 'stable': False, 'signature': 'a',
            'state': {'game_state': -6, 'chain_reaction': True, 'moves': 3,
                      'remaining_time': 30, 'players': [{'energy': 2, 'is_my_turn': True}]}}


def test_animation_and_timestamps_do_not_invalidate_plan():
    before = snapshot()
    after = copy.deepcopy(before)
    after.update(stable=True, captured_at='later', signature='other-metadata')
    after['state'].update(game_state=-5, chain_reaction=False, remaining_time=29)
    assert snapshot_plan_key(before) == snapshot_plan_key(after)


@pytest.mark.parametrize('change', ['board', 'special', 'turn', 'energy', 'match', 'rules', 'policy'])
def test_strategic_changes_cancel_plan(change):
    before = snapshot()
    after = copy.deepcopy(before)
    if change == 'board': after['board'][0][0] = 4
    if change == 'special': after['special_board'][0][0] = 3
    if change == 'turn': after['state']['players'][0]['is_my_turn'] = False
    if change == 'energy': after['state']['players'][0]['energy'] = 7
    if change == 'match': after['board_object'] = 'match2'
    if change == 'rules': after['state']['rules'] = {'is_square_match': True}
    key = snapshot_plan_key(before)
    plan = AutoPlan(key)
    plan.update(snapshot_plan_key(after, ('changed',) if change == 'policy' else ()), True)
    assert plan.is_cancelled()
    assert not plan.wait_until_ready()
    assert not plan.claim_execution()


def test_worker_waits_for_settle_then_claims_once():
    plan = AutoPlan('a')
    started = threading.Event()
    done = threading.Event()
    outcomes = []
    def worker():
        started.set()
        outcomes.append(plan.wait_until_ready())
        done.set()
    thread = threading.Thread(target=worker)
    thread.start()
    assert started.wait(1)
    plan.update('a', False)
    assert not done.wait(.01)
    plan.update('a', True)
    assert done.wait(1)
    thread.join(1)
    assert outcomes == [True]
    assert plan.claim_execution()
    assert not plan.claim_execution()


def test_cancellation_cannot_be_revived_by_old_board_returning():
    plan = AutoPlan('a')
    plan.update('b', False)
    plan.update('a', True)
    assert not plan.wait_until_ready()


def test_cancellation_interrupts_search_and_restores_context():
    plan = AutoPlan('a')
    with planning_cancellation(plan.is_cancelled):
        ms.generate_candidates([[1, 2], [3, 4]], [[0, 0], [0, 0]])
        plan.cancel()
        with pytest.raises(PlanningCancelled):
            ms._find_matches_cached([[1, 2], [3, 4]], False, {})
    # Cancellation belongs to this worker/decision, not the next calculation.
    ms._find_matches_cached([[1, 2], [3, 4]], False, {})


def test_gui_starts_planning_during_move_processing(monkeypatch):
    import memory_gui as gui
    s = snapshot()
    calls = []
    obj = SimpleNamespace(
        _snapshot=s, _move_running=False, _reader_session=object(), _match_active=True,
        _last_played_signature='previous', AutoButton=SimpleNamespace(isChecked=lambda: True),
        _auto_action=lambda: 'best_move',
        TurnLabel=SimpleNamespace(setText=lambda text: None), _update_auto_plan=lambda: None,
        _turn_label_text=lambda state: '', snapshot_age_seconds=lambda: 0,
        _opponent_is_playing=lambda state: False, _engine_move_phase_open=lambda snap: False,
        _effective_mode=lambda state: ms.GameMode.NONE,
        PerksCheck=SimpleNamespace(isChecked=lambda: False),
        _play=lambda action, **kwargs: calls.append((action, kwargs)),
        _move_retry_wait=lambda: 0.0,
        _prepares_ahead=lambda state: True,
    )
    gui.MemoryWindow._auto_tick(obj)
    assert calls == [('best_move', {'prepare_ahead': True})]


def _move_done_gui(match_active, statuses):
    return SimpleNamespace(
        _auto_plan=AutoPlan('a'), _move_running=True, _reader_session=object(),
        _match_active=match_active,
        _set_actions_enabled=lambda enabled: None,
        statusBar=lambda: SimpleNamespace(showMessage=lambda text: None),
        _auto_tick=lambda: None, _last_played_signature='previous',
        _requested_action=None, _set_calc_status=statuses.append,
        AutoButton=SimpleNamespace(isChecked=lambda: False),
        _auto_action=lambda: None,
    )


def test_cancelled_result_does_not_mark_board_played(monkeypatch):
    import memory_gui as gui
    import runtime
    queued = []
    monkeypatch.setattr(gui.QtCore.QTimer, 'singleShot', lambda delay, fn: queued.append(fn))
    obj = _move_done_gui(True, [])
    gui.MemoryWindow._on_move_done(obj, runtime.CheckBestMoveResult(
        '', '', turn_consumed=False, planning_cancelled=True), 'a')
    assert obj._last_played_signature == 'previous'
    assert not obj._move_running
    assert queued == [obj._auto_tick]


def test_cancelled_result_after_the_match_ended_recomputes_nothing(monkeypatch):
    """2026-09-15 09:45: "racunam ponovo" after the match was over read as a
    stuck reader. The plan is dropped and no tick is queued."""
    import memory_gui as gui
    import runtime
    queued, statuses = [], []
    monkeypatch.setattr(gui.QtCore.QTimer, 'singleShot', lambda delay, fn: queued.append(fn))
    obj = _move_done_gui(False, statuses)
    gui.MemoryWindow._on_move_done(obj, runtime.CheckBestMoveResult(
        '', '', turn_consumed=False, planning_cancelled=True), 'a')
    assert obj._last_played_signature == 'previous'
    assert not obj._move_running
    assert queued == []
    assert statuses == ['partija gotova - cekam sledecu']


@pytest.mark.parametrize('ready', [False, True])
def test_runtime_defers_debug_and_input_until_validated(monkeypatch, tmp_path, ready):
    import runtime
    calls = []
    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    monkeypatch.setattr(runtime, 'apply_board_profile', lambda profile: None)
    monkeypatch.setattr(runtime, 'create_debug_run_dir', lambda: calls.append('debug') or tmp_path)
    monkeypatch.setattr(runtime, 'find_previous_debug_run', lambda path: None)
    monkeypatch.setattr(runtime, 'write_move_debug_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.move_telemetry, 'record', lambda **kwargs: calls.append('telemetry'))
    monkeypatch.setattr(runtime, 'play_best_move_with_cursor_restore',
                        lambda *args, **kwargs: calls.append('swipe'))
    monkeypatch.setattr(runtime, 'resolve_ufo_state', lambda *args: None)
    monkeypatch.setattr(runtime, 'resolve_mixy_meow_state', lambda *args: None)
    def wait():
        assert calls == []
        calls.append('wait')
        return ready
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode='auto', selected_profile='regular',
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None, selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE),
        cursor_return_position=(0, 0), pre_scanned_board=board,
        pre_scanned_special_board=[[0] * 7 for _ in range(7)],
        jelly_zone_cells=(), points_only=True, force_no_booster=True,
        allow_perk_activation=False, debug_enabled=True, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False,
        wait_for_board=wait, claim_execution=lambda: True,
    )
    outcome = runtime.run_check_best_move_request(request)
    if ready:
        assert calls == ['wait', 'debug', 'telemetry', 'swipe']
        assert not outcome.planning_cancelled
    else:
        assert calls == ['wait']
        assert outcome.planning_cancelled


def test_held_plan_rereads_the_window_geometry_right_before_its_swipe(monkeypatch, tmp_path):
    """BlueStacks left or re-entered fullscreen while the plan waited for the click."""
    import runtime
    calls = []
    board = [[(row * 2 + col) % 5 + 1 for col in range(7)] for row in range(7)]
    board[0][:3] = [1, 2, 1]
    board[1][1] = 1
    monkeypatch.setattr(runtime, 'apply_board_profile', lambda profile: calls.append('geometry'))
    monkeypatch.setattr(runtime, 'create_debug_run_dir', lambda: tmp_path)
    monkeypatch.setattr(runtime, 'find_previous_debug_run', lambda path: None)
    monkeypatch.setattr(runtime, 'write_move_debug_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(runtime.move_telemetry, 'record', lambda **kwargs: None)
    monkeypatch.setattr(runtime, 'play_best_move_with_cursor_restore',
                        lambda *args, **kwargs: calls.append('swipe'))
    monkeypatch.setattr(runtime, 'resolve_ufo_state', lambda *args: None)
    monkeypatch.setattr(runtime, 'resolve_mixy_meow_state', lambda *args: None)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode='auto', selected_profile='regular',
        allow_square_matches=False, specials_explode_immediately=False,
        score_rally_values=None, selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE),
        cursor_return_position=(0, 0), pre_scanned_board=board,
        pre_scanned_special_board=[[0] * 7 for _ in range(7)],
        jelly_zone_cells=(), points_only=True, force_no_booster=True,
        allow_perk_activation=False, debug_enabled=False, debug_images_enabled=False,
        lookahead_candidates=0, include_future_value=False,
        wait_for_board=lambda: calls.append('wait') or True, claim_execution=lambda: True,
    )
    runtime.run_check_best_move_request(request)
    assert calls == ['geometry', 'wait', 'geometry', 'swipe']


@pytest.mark.parametrize('invalid', ['detached', 'ended', 'opponent', 'stale', 'animating', 'engine_read'])
def test_gui_never_releases_plan_until_playable(invalid):
    import memory_gui as gui
    s = snapshot()
    s['stable'] = invalid != 'animating'
    plan = AutoPlan('key')
    obj = SimpleNamespace(
        _auto_plan=plan, _snapshot=s,
        _reader_session=None if invalid == 'detached' else object(),
        _match_active=invalid != 'ended', _last_played_signature='previous',
        snapshot_age_seconds=lambda: 100 if invalid == 'stale' else 0,
        _engine_move_phase_open=lambda snap: invalid not in ('opponent', 'animating'),
        _turn_countdown_is_fresh=lambda state: True, _auto_plan_key=lambda snap: 'key',
        _request_dump=lambda: None,
        _needs_engine_read=lambda snap: invalid == 'engine_read',
    )
    gui.MemoryWindow._update_auto_plan(obj)
    assert not plan.claim_execution()


def _engine_read_gui():
    import memory_gui as gui
    obj = SimpleNamespace(
        ABILITY_MIXY_MEOW=gui.MemoryWindow.ABILITY_MIXY_MEOW,
        ABILITY_UFO_SE=gui.MemoryWindow.ABILITY_UFO_SE,
        _current_player=gui.MemoryWindow._current_player,
    )
    return lambda snap: gui.MemoryWindow._needs_engine_read(obj, snap)


def _players_snapshot(reason, ability=None, jelly=None):
    return {
        'reason': reason,
        'jelly': jelly,
        'state': {
            'current_player_index': 0,
            'players': [{'index': 0, 'is_my_turn': True, 'special_ability_type': ability}],
        },
    }


@pytest.mark.parametrize('ability, jelly, poll_needs', [
    (None, None, False),                       # plain match: polls are enough
    (63, None, False),                         # Froggy: nothing behind a getter
    (None, {'keys': {'all_infected': 'k'}}, True),   # jelly live: zone only on a dump
    (59, None, True),                          # Mixy: UsesLeft only on a dump
    (49, None, True),                          # UFO: eye count only on a dump
])
def test_engine_only_values_are_read_before_a_move(ability, jelly, poll_needs):
    needs = _engine_read_gui()
    assert needs(_players_snapshot('stable_poll', ability, jelly)) is poll_needs
    # A manual dump has run the getters; never wait on a second one.
    assert needs(_players_snapshot('manual_rpc', ability, jelly)) is False


def test_unarmed_plan_holds_until_armed_then_claims_once():
    computed = []
    plan = AutoPlan('a', armed=False, on_computed=computed.append)
    outcomes = []
    done = threading.Event()
    def worker():
        outcomes.append(plan.wait_until_ready())
        done.set()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    # Board ready, but nobody asked to play: the worker keeps holding the move.
    plan.update('a', True)
    assert not done.wait(.05)
    assert computed == [plan] and plan.computed
    assert not plan.claim_execution()
    plan.arm()
    assert done.wait(1)
    assert outcomes == [True]
    assert plan.claim_execution()
    assert not plan.claim_execution()


def test_unarmed_plan_is_dropped_by_a_changed_board():
    plan = AutoPlan('a', armed=False)
    done = threading.Event()
    outcomes = []
    def worker():
        outcomes.append(plan.wait_until_ready())
        done.set()
    threading.Thread(target=worker, daemon=True).start()
    plan.update('b', True)
    assert done.wait(1)
    assert outcomes == [False]
    plan.arm()
    assert not plan.claim_execution()


def test_disarm_keeps_the_computation_but_stops_execution():
    plan = AutoPlan('a')
    plan.update('a', True)
    plan.disarm()
    assert not plan.is_cancelled()
    assert not plan.claim_execution()
    plan.arm()
    assert plan.claim_execution()


def test_switching_auto_off_disarms_the_plan_instead_of_dropping_it():
    """With Auto off the computation is kept for the buttons; it just may
    not play on its own."""
    import memory_gui as gui
    plan = AutoPlan('key')
    plan.update('key', True)
    logged = []
    obj = SimpleNamespace(
        _auto_plan=plan, _reader_session=object(),
        AutoButton=SimpleNamespace(setText=lambda text: None),
        _log=logged.append, _wake_agent=lambda: None,
        _set_actions_enabled=lambda enabled: None,
    )
    # Both auto toggles share this tail since the move burner arrived.
    obj._auto_switched = lambda checked: gui.MemoryWindow._auto_switched(obj, checked)
    gui.MemoryWindow._auto_toggled(obj, False)
    assert not plan.is_cancelled()
    assert not plan.claim_execution()
    plan.arm()
    assert plan.claim_execution()


def _lights_up_snapshot(column):
    return {'columns': 7, 'state': {'rules': {'board_model_name': 37}},
            'board_fields': {'CurrentActiveColumn': column, 'RandomColumnChange': True}}


def _lights_up_gui(stale):
    import memory_gui as gui
    obj = SimpleNamespace(
        _lights_up_stale_column=stale, _lights_up_play_column=None,
        _lights_up_reported=None, _lights_up_multiplier_reported=None,
        _log=lambda text: None,
    )
    obj._lights_up_column = lambda snap: gui.MemoryWindow._lights_up_column(obj, snap)
    obj._lights_up_request_state = (
        lambda snap, me: gui.MemoryWindow._lights_up_request_state(obj, snap, me))
    return gui, obj


def test_lights_up_column_still_showing_after_our_swap_is_not_priced():
    """The column moves only after the cascades end (player, 2026-09-18)."""
    gui, obj = _lights_up_gui(stale=2)
    me = {'score_multiplier': 6}
    state = gui.MemoryWindow._lights_up_scored_state(obj, _lights_up_snapshot(2), me)
    assert state == {'column': None, 'multiplier': 6}
    # Played on the column actually showing, so a third swap is judged too.
    assert obj._lights_up_play_column == 2
    assert obj._lights_up_stale_column == 2


def test_lights_up_moved_column_is_priced_again():
    gui, obj = _lights_up_gui(stale=2)
    state = gui.MemoryWindow._lights_up_scored_state(
        obj, _lights_up_snapshot(5), {'score_multiplier': 6})
    assert state == {'column': 5, 'multiplier': 6}
    assert obj._lights_up_stale_column is None


def test_lights_up_first_swap_of_turn_uses_the_lit_column():
    gui, obj = _lights_up_gui(stale=None)
    state = gui.MemoryWindow._lights_up_scored_state(
        obj, _lights_up_snapshot(3), {'score_multiplier': 1})
    assert state == {'column': 3, 'multiplier': 1}
