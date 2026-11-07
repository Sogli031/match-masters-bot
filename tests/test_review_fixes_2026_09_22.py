"""Fixes from the 2026-09-22 review: reader allowlist, Xtra tile, perk value,
move-error back-off, and board geometry that must not be played on."""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import board_source  # noqa: E402
import matchmasters_board_reader as reader  # noqa: E402
import move_strategy as ms  # noqa: E402
import recognition  # noqa: E402


# --- reader allowlist -------------------------------------------------------

def test_reader_keeps_the_keys_board_source_reads():
    raw = {
        "cell_types": [[0, 3], [0, 0]],
        "cell_multipliers": [1, 2],
        "board_extra_data_diag": {"entries": 0},
        "state": {"rules": {
            "color_combo_energy": {"4": 1},
            "color_energy_override": {"3": 1},
            "title": "x",
        }},
    }
    snapshot = reader._safe_snapshot(raw)
    assert snapshot["cell_types"] == [[0, 3], [0, 0]]
    assert snapshot["cell_multipliers"] == [1, 2]
    assert snapshot["board_extra_data_diag"] == {"entries": 0}
    rules = snapshot["state"]["rules"]
    assert rules["color_combo_energy"] == {"4": 1}
    assert rules["color_energy_override"] == {"3": 1}
    assert board_source.funky_tile_cells(snapshot) == ((0, 1),)


def _charge(rules, monkeypatch):
    monkeypatch.setattr(board_source, "_player_color_swap", {})
    return board_source.charging_colors({"state": {"rules": rules}})


def test_charge_table_names_the_charging_colour(monkeypatch):
    # SlotColor 4 is blue, 3 green; a zero entry charges nothing.
    assert _charge({"color_combo_energy": {"4": 1, "3": 0}}, monkeypatch) == (ms.BLUE,)
    assert _charge({
        "color_combo_energy": {"4": 1},
        "color_energy_override": {"3": 1},
    }, monkeypatch) == (ms.GREEN,)


def test_charge_table_naming_every_colour_keeps_the_blue_default(monkeypatch):
    every = {str(code): 1 for code in (2, 3, 4, 5, 6, 7)}
    assert _charge({"color_combo_energy": every, "colors_count": 6}, monkeypatch) is None


# --- Xtra Move tile -----------------------------------------------------------

def test_xtra_marker_is_not_a_special():
    assert not ms._is_created_special(ms.SPECIAL_XTRA_MOVE_TILE)
    assert not ms._is_activatable_special(ms.SPECIAL_XTRA_MOVE_TILE)
    assert ms._is_activatable_special(ms.SPECIAL_BOMB)


def test_plain_tiles_on_adjacent_xtra_cells_are_no_special_combo():
    board = [[ms.BLUE, ms.GREEN], [ms.YELLOW, ms.RED]]
    specials = [[ms.SPECIAL_XTRA_MOVE_TILE, ms.SPECIAL_XTRA_MOVE_TILE], [0, 0]]
    candidate = ms.MoveCandidate(
        (0, 0), (0, 1), ms._direction_between((0, 0), (0, 1)), board, specials
    )
    assert not ms._candidate_activates_special_swap(candidate)


# --- perk value ---------------------------------------------------------------

def _perk(**fields):
    return ms.PerkAction(
        perk_key="detonator", target=(0, 0), score=40.0, gross_score=40.0,
        threshold=0.0, baseline_score=10.0, immediate_points=40.0, **fields,
    )


def test_deterministic_perk_across_a_random_refill_keeps_its_value():
    context = ms.PerkDecisionContext(objective=ms.PerkObjective.MAX_POINTS)
    valued = ms._with_perk_objective_value(_perk(confidence=0.6), None, context)
    assert valued.horizon_value == pytest.approx(40.0)
    assert valued.net_gain == pytest.approx(40.0)


def test_sampled_perk_is_still_valued_by_its_distribution():
    context = ms.PerkDecisionContext(objective=ms.PerkObjective.MAX_POINTS)
    valued = ms._with_perk_objective_value(
        _perk(confidence=0.65, random_outcome=True), None, context
    )
    # Every sampled outcome scored 0: the flat 40 must not stand in for it.
    assert valued.horizon_value == pytest.approx(0.0)


# --- move-error back-off --------------------------------------------------------

def _failing_gui(logged):
    import memory_gui as gui

    obj = types.SimpleNamespace(
        _move_error_count=0, _move_error_text=None, _move_retry_not_before=0.0,
        _log=logged.append,
    )
    for name in ("_note_move_failure", "_clear_move_failures", "_move_retry_wait"):
        setattr(obj, name, types.MethodType(getattr(gui.MemoryWindow, name), obj))
    return obj


def test_repeated_move_error_backs_off_and_logs_sparingly(monkeypatch):
    import memory_gui as gui

    now = [100.0]
    monkeypatch.setattr(gui.time, "monotonic", lambda: now[0])
    logged = []
    obj = _failing_gui(logged)
    delays = []
    for _ in range(8):
        obj._note_move_failure("error: cv::resize\n")
        delays.append(obj._move_retry_wait())
    assert delays == pytest.approx([0.5, 1.0, 2.0, 4.0, 5.0, 5.0, 5.0, 5.0])
    # 1st, 2nd, 4th and 8th repeat only -- not 8 lines.
    assert len(logged) == 4
    assert "ponovljeno 8x" in logged[-1]
    obj._clear_move_failures()
    assert obj._move_retry_wait() == 0.0
    obj._note_move_failure("other error")
    assert obj._move_retry_wait() == pytest.approx(0.5)


# --- board geometry -------------------------------------------------------------

def _profile_config(monkeypatch, config=None, error=None):
    monkeypatch.setattr(recognition, "has_relative_calibration", lambda *a, **k: False)

    def load(*args, **kwargs):
        if error is not None:
            raise error
        return dict(config)

    monkeypatch.setattr(recognition, "load_board_config", load)


def test_minimized_window_geometry_is_refused_and_keeps_the_last_good(monkeypatch):
    monkeypatch.setattr(recognition, "squareSize", 84)
    _profile_config(monkeypatch, {
        "left": 0, "up": 0, "width": 14, "height": 14,
        "squareSize": 2, "boardSize": 7,
    })
    with pytest.raises(RuntimeError, match="minimizovan"):
        recognition.apply_board_profile("default")
    assert recognition.squareSize == 84


def test_missing_calibration_file_raises_instead_of_exiting(monkeypatch):
    _profile_config(monkeypatch, error=FileNotFoundError("board_config.json"))
    with pytest.raises(RuntimeError, match="kalibracije"):
        recognition.apply_board_profile("default")


# --- GUI: turn clock, stale boards, detach, attach watchdog, slots -----------------

def _bound(obj, *names):
    import memory_gui as gui

    for name in names:
        setattr(obj, name, types.MethodType(getattr(gui.MemoryWindow, name), obj))
    return obj


def test_zero_clock_before_the_first_turn_is_no_clock():
    obj = _bound(types.SimpleNamespace(snapshot_age_seconds=lambda: 0.0), "turn_time_left")
    intro = {"remaining_time": 0, "game_state": -3, "rules": {"is_timer": True}}
    assert obj.turn_time_left(intro) is None
    playing = {"remaining_time": 0, "game_state": -5, "rules": {"is_timer": True}}
    assert obj.turn_time_left(playing) == 0.0
    running = {"remaining_time": 1499.5, "game_state": -5}
    assert obj.turn_time_left(running) == pytest.approx(1499.5)


def test_refresh_does_not_restamp_a_board_that_arrived_earlier():
    old = {"signature": "old"}
    receiver = types.SimpleNamespace(
        last_snapshot=old,
        snapshot_event=types.SimpleNamespace(wait=lambda timeout: True),
    )
    seen = []
    obj = _bound(
        types.SimpleNamespace(
            _reader=receiver, _request_dump=lambda: True, _on_snapshot=seen.append,
        ),
        "_refresh_snapshot_now",
    )
    # A dump is already in flight and the event is still set from before:
    # nothing new arrived, so nothing is re-stamped.
    assert obj._refresh_snapshot_now(timeout=0.05) is False
    assert seen == []


def test_detach_from_a_replaced_session_is_ignored():
    calls = []
    current = object()
    obj = _bound(
        types.SimpleNamespace(
            _reader=current, _match_active=False,
            _stop_auto=lambda: calls.append("stop"),
            _on_reader_stopped=lambda message: calls.append(message),
            _reset_match_state=lambda: calls.append("reset"),
            _clear_match_view=lambda: calls.append("clear"),
        ),
        "_on_reader_detached",
    )
    obj._on_reader_detached(object(), "application-requested")
    assert calls == []
    obj._match_active = True
    obj._on_reader_detached(current, "process-terminated")
    assert calls[:3] == ["reset", "clear", "stop"]
    assert "process-terminated" in calls[3]


def test_old_attach_watchdog_leaves_a_newer_attempt_alone():
    logged = []
    obj = _bound(
        types.SimpleNamespace(
            _reader_session=None, _attach_started_at=1.0, _attach_attempt=3,
            _reader_auto_retry=True, _log=logged.append,
        ),
        "_attach_watchdog",
    )
    obj._attach_watchdog(1)
    assert obj._reader_auto_retry is True
    assert logged == []


def test_guarded_slot_still_raises_for_test_doubles():
    import memory_gui as gui

    @gui.guarded_slot
    def boom(self):
        raise ValueError("x")

    with pytest.raises(ValueError):
        boom(types.SimpleNamespace())


def test_freeze_log_rolls_over(monkeypatch, tmp_path):
    import memory_gui as gui

    path = tmp_path / "freeze_watch.log"
    path.write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(gui, "FREEZE_LOG_PATH", path)
    monkeypatch.setattr(gui, "FREEZE_LOG_MAX_BYTES", 50)
    gui.append_freeze_log(["novo"])
    assert (tmp_path / "freeze_watch.log.1").read_text(encoding="utf-8") == "x" * 100
    assert path.read_text(encoding="utf-8").strip().endswith("novo")


# --- runtime: previous run lookup, perk follow-up rules -------------------------

def test_previous_run_is_never_one_from_an_earlier_session(tmp_path):
    import os
    import time as _time

    import runtime

    old = tmp_path / "2026-09-21_23-00-00_000"
    old.mkdir()
    (old / "move.json").write_text("{}", encoding="utf-8")
    stale = _time.time() - 3600
    os.utime(old, (stale, stale))
    current = tmp_path / "2026-09-22_10-00-00_000"
    current.mkdir()
    assert runtime.find_previous_debug_run(current) is None
    recent = tmp_path / "2026-09-22_09-59-58_000"
    recent.mkdir()
    (recent / "move.json").write_text("{}", encoding="utf-8")
    assert runtime.find_previous_debug_run(current) == recent


def test_safe_debug_write_swallows_a_failing_writer():
    import runtime

    def writer():
        raise TypeError("Object of type int64 is not JSON serializable")

    assert runtime._safe_debug_write(writer) is None


# --- Hammer: only a follow-up worth opening counts (player, 2026-09-22) -----------

def _hammer_follow_up(extra=0.0, blue=0.0):
    board = [[ms.BLUE, ms.GREEN], [ms.YELLOW, ms.RED]]
    specials = [[0, 0], [0, 0]]
    candidate = ms.MoveCandidate((0, 0), (0, 1), ms._direction_between((0, 0), (0, 1)), board, specials)
    return ms.MoveEvaluation(
        candidate, score=3, instant_score=3, special_bonus=0, blue_bonus=blue,
        mode_bonus=0, extra_move_bonus=0, disco_move_bonus=0, extra_moves=extra,
        disco_moves=0, cascade_count=1, board_potential=0, lookahead_bonus=0,
        explanation='', blue_cells=blue, direct_extra_moves=extra,
    )


def _hammer(follow_up):
    return ms.PerkAction(
        perk_key=ms.PERK_HAMMER, target=(0, 0), score=5.0, gross_score=5.0,
        threshold=0.0, baseline_score=0.0, follow_up=follow_up,
    )


def test_hammer_that_only_opens_an_ordinary_move_is_not_used():
    booster = ms.BoosterState(current=1)
    assert not ms._hammer_action_is_useful(
        _hammer(_hammer_follow_up(blue=1.0)), "None", None, booster
    )


def test_hammer_that_opens_an_extra_move_is_used():
    booster = ms.BoosterState(current=1)
    assert ms._hammer_action_is_useful(
        _hammer(_hammer_follow_up(extra=1.0)), "None", None, booster
    )
