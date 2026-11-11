"""RNG-backed target selection for High Voltage and Magic Wand."""

import json
from pathlib import Path

import pytest

import move_strategy as ms
import runtime
from engine_refill import EngineRefill, ExactRefillSession


@pytest.fixture
def blast():
    path = Path(__file__).parent / "fixtures" / "high_voltage_refill.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _session(blast):
    before = blast["before"]
    model = EngineRefill.from_profile(before["profile"])
    return ExactRefillSession(model, before["board"], special_board=before["special_board"])


def test_high_voltage_replays_recorded_board_specials_and_rng(blast):
    board, special = blast["before"]["board"], blast["before"]["special_board"]
    session = _session(blast)
    mode = ms.GameMode.NONE
    with ms.exact_refill_active(session):
        result = ms._color_blast_target_simulation(
            board, special,
            lambda: ms._simulate_high_voltage_color(board, special, blast["color"], mode=mode),
        )
    expected = blast["after"]
    assert result.exact_refill_supported
    assert ms.grid_to_lists(result.board) == expected["board"]
    assert ms.grid_to_lists(result.special_board) == expected["special_board"]
    rng = session.current.rng.to_capture()
    assert rng == {key: expected["rng"][key] for key in rng}
    assert result.extra_moves == result.blue_cells == 0
    assert len(session.states) == 1


def test_magic_wand_candidates_restart_from_the_same_rng(blast):
    board, special = blast["before"]["board"], blast["before"]["special_board"]
    mode = ms.GameMode.NONE
    session = _session(blast)
    without_refill = ms.evaluate_magic_wand_target(board, special, ms.BLUE, mode=mode)
    assert not without_refill.exact_refill
    with ms.exact_refill_active(session):
        first = ms.evaluate_magic_wand_target(board, special, ms.BLUE, mode=mode)
        counter = session.current.rng.counter
        second = ms.evaluate_magic_wand_target(board, special, ms.RED, mode=mode)
        repeat = ms.evaluate_magic_wand_target(board, special, ms.BLUE, mode=mode)
    assert first.exact_refill and second.exact_refill
    assert session.successful == 3
    assert session.current.rng.counter == counter
    assert first == repeat
    assert len(session.states) == 1


def test_magic_wand_replays_recorded_board_specials_and_rng():
    path = Path(__file__).parent / "fixtures" / "magic_wand_refill.json"
    blast = json.loads(path.read_text(encoding="utf-8"))
    board, special = blast["before"]["board"], blast["before"]["special_board"]
    session = _session(blast)
    with ms.exact_refill_active(session), ms.mushroom_multipliers_active(True):
        result = ms._color_blast_target_simulation(
            board, special, lambda: ms._simulate_magic_wand_color(
                board, special, blast["color"], mode=ms.GameMode.MULTIPLIER_MUSHROOMS,
            ),
        )
    expected = blast["after"]
    assert result.exact_refill_supported
    assert ms.grid_to_lists(result.board) == expected["board"]
    assert ms.grid_to_lists(result.special_board) == expected["special_board"]
    rng = session.current.rng.to_capture()
    assert rng == {key: expected["profile"]["rng"][key] for key in rng}


@pytest.mark.parametrize("booster", ["high_voltage", "magic_wand"])
@pytest.mark.parametrize("late", [False, True])
def test_runtime_uses_the_refill_to_choose_a_booster_target(monkeypatch, tmp_path, blast, booster, late):
    before = blast["before"]
    session = _session(blast)
    report = {}
    monkeypatch.setattr(runtime, "apply_board_profile", lambda profile: None)
    monkeypatch.setattr(runtime, "create_debug_run_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "find_previous_debug_run", lambda path: None)
    monkeypatch.setattr(runtime, "write_move_debug_report", lambda *args, **kwargs: report.update(kwargs))
    monkeypatch.setattr(runtime.move_telemetry, "record", lambda **kwargs: None)
    request = runtime.CheckBestMoveRequest(
        mode=ms.GameMode.NONE, special_piece_mode="auto", selected_profile="regular",
        allow_square_matches=False, specials_explode_immediately=False, score_rally_values=None,
        selected_perks=(runtime.PERK_NONE, runtime.PERK_NONE), cursor_return_position=(0, 0),
        pre_scanned_board=before["board"], pre_scanned_special_board=before["special_board"],
        booster_action_mode=booster, booster_charge=7, booster_maximum=7, remaining_moves=2,
        screen_state_read={"resolved": {"booster_ready": True, "sources": {"booster_ready": "memory"}}},
        activate_booster_immediately=True, booster_clock_deadline=True,
        late_exact_refill=(lambda: session) if late else None,
        debug_enabled=True, debug_images_enabled=False,
        include_future_value=False, lookahead_candidates=0, allow_perk_activation=False,
        play_enabled=False,
    )
    with ms.exact_refill_active(None if late else session):
        runtime.run_check_best_move_request(request)
    assert report["selected_action"] == "activate_booster"
    assert report[f"{booster}_target"].exact_refill
