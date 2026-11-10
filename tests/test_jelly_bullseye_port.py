from pathlib import Path

import pytest

import move_strategy as ms
from refill_monitor import check_transition
from tools.analyze_research import grid, load, observed, try_transition


FIXTURES = Path(__file__).parent / "fixtures" / "jelly_bullseye"


def test_active_jelly_is_unverifiable_until_ported(monkeypatch):
    monkeypatch.setattr(ms, "JELLY_EXACT_PORTED", False)
    before, _ = load(FIXTURES / "003.json")
    after, _ = load(FIXTURES / "004.json")
    result = check_transition(before, after)
    assert result["verdict"] == "unsupported"
    assert "Jelly SE" in result["detail"]


@pytest.mark.parametrize("index", [4, 8, 11, 14, 16, 23, 29])
def test_jelly_zone_replays_board_specials_and_rng(index):
    _, capture = load(FIXTURES / f"{index:03}.json")
    after, _ = load(FIXTURES / f"{index + 1:03}.json")
    matches, closest, reasons = try_transition(capture, observed(after))
    assert matches, (closest, reasons)


def test_refill_monitor_uses_port_and_keeps_renewal_unverifiable():
    before, _ = load(FIXTURES / "003.json")
    renewed, _ = load(FIXTURES / "004.json")
    after, _ = load(FIXTURES / "005.json")
    assert check_transition(before, renewed)["verdict"] == "unsupported"
    assert check_transition(renewed, after)["verdict"] == "ok"


def test_live_refill_ranks_jelly_swipe_with_chained_lightning(monkeypatch):
    import square_solo_live as live

    before, capture = load(FIXTURES / "014.json")
    after, _ = load(FIXTURES / "015.json")
    board, specials = before["board"], before["special_board"]
    snapshot = {
        "columns": len(board),
        "state": before["snapshot_state"],
        "slots": before["raw_slots"],
        "special_board": specials,
        "board_extra_data": {
            entry["key"]: str(entry["value"]) for entry in before["board_extra_data"]["entries"]
        },
    }
    monkeypatch.setattr(live, "_resting_profile", lambda *_: (capture["profile"].copy(), None))
    session, reason = live.exact_refill_session(None, None, snapshot, board)
    assert session is not None, reason
    candidate = next(c for c in ms.generate_candidates(board, specials)
                     if (c.start, c.target) == ((2, 4), (3, 4)))
    with ms.exact_refill_active(session), ms.jelly_zone_cells(session.jelly_cells):
        result = ms._simulate_created_candidate_cached(
            board, candidate, False, "None", False, False, None, None,
        )
    assert result.exact_refill_supported, session.failure
    assert grid(result.board) == after["board"]
    assert grid(result.special_board) == after["special_board"]
    rng = session.current.rng.to_capture()
    assert rng == {key: observed(after)["rng_state"][key] for key in rng}
    assert not session.knows(result.board, result.special_board)


def test_live_refill_uses_visible_jelly_zone_before_renewal(monkeypatch):
    import square_solo_live as live

    folder = FIXTURES.parents[2] / "Debug/research/20261110_043451_the-floor-is-lava"
    if not folder.is_dir():
        pytest.skip("Lava Jelly SE renewal recording not present")
    before, capture = load(folder / "004.json")
    after, _ = load(folder / "005.json")
    board, specials = before["board"], before["special_board"]
    snapshot = {
        "columns": len(board), "state": before["snapshot_state"],
        "slots": before["raw_slots"], "special_board": specials,
        "board_extra_data": {entry["key"]: str(entry["value"])
                             for entry in before["board_extra_data"]["entries"]},
    }
    monkeypatch.setattr(live, "_resting_profile", lambda *_: (capture["profile"].copy(), None))
    session, reason = live.exact_refill_session(None, None, snapshot, board)
    assert session is not None, reason
    assert session.jelly_uses_left == 2
    candidate = next(c for c in ms.generate_candidates(board, specials)
                     if (c.start, c.target) == ((4, 2), (4, 3)))
    with (ms.exact_refill_active(session), ms.jelly_zone_cells(session.jelly_cells),
          ms.floor_lava_checked_columns(capture["simulator_input"]["floor_lava_columns"])):
        result = ms._simulate_created_candidate_cached(
            board, candidate, False, ms.GameMode.FLOOR_IS_LAVA.value, False, False, None, None,
        )
    assert result.exact_refill_supported, session.failure
    assert grid(result.board) == after["board"]
    assert grid(result.special_board) == after["special_board"]
    assert session.current.rng.counter == after["profile"]["jelly_renewal_trace"][-1]["before_rng_counter"]
    assert not session.knows(result.board, result.special_board)
