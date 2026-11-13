"""Dopuna radi u svakom modu: Candy World i priblizna dopuna (APPROXIMATE_REFILL).

Live log 2026-11-07/08: "Dopuna: NE RADI - mod nije podrzan: Unported simulator
special/color in refill board" in Candy World (bombona = SPECIAL_RED_BLUE_TILE),
Color Crush and Jungle Rumble; the ordinary ranking then ran without any drop.
"""
from types import SimpleNamespace as NS

import pytest

import engine_refill
import move_strategy as ms
from engine_refill import ExactRefillSession, SquareRefill, UnsupportedRefill, fill_simulator_board
from tests.test_engine_refill import entries, profile


def candy_profile():
    p = profile()
    p["rules"].update(id="candy-world", boardModelName=engine_refill.CANDY_WORLD_BOARD)
    return p


def sim_board():
    # Rows shifted by two: nothing matches.
    return [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]


def test_candy_is_a_blue_red_board_special_and_the_replenish_roll_is_counted():
    m = SquareRefill.from_profile(candy_profile(), seed=1234)
    board, specials = sim_board(), [[0] * 7 for _ in range(7)]
    # Two candies stand (the maximum), so no conversion can happen.
    board[0][0], specials[0][0] = ms.BLUE, ms.SPECIAL_RED_BLUE_TILE
    board[0][1], specials[0][1] = ms.RED, ms.SPECIAL_RED_BLUE_TILE
    board[3][0] = ms.EMPTY
    out, after, trace = fill_simulator_board(m, board, specials)
    assert after[0][:2] == [ms.SPECIAL_RED_BLUE_TILE] * 2 and out[3][0] != ms.EMPTY
    # Base refill, then the one Chance(60) of CandyWorldBoard.RefillSlots.
    assert m.rng.counter == trace[-1]["rng_after"] + 1


@pytest.mark.parametrize("hole_column, can_convert", [(1, True), (0, False)])
def test_candy_conversion_turns_a_new_blue_or_red_slot_into_a_candy(hole_column, can_convert):
    """One candy short: a won Chance(60) converts a newly filled blue/red slot
    (CandyWorldBoard.ConvertSlots, colour2 the other of the pair) -- but never
    one in a column that already holds a candy (b__13_1 compares only x)."""
    converted = plain = 0
    for seed in range(40):
        board, specials = sim_board(), [[0] * 7 for _ in range(7)]
        board[0][0], specials[0][0] = ms.BLUE, ms.SPECIAL_RED_BLUE_TILE
        board[3][hole_column] = ms.EMPTY
        m = SquareRefill.from_profile(candy_profile(), seed=seed)
        out, after, trace = fill_simulator_board(m, board, specials)
        (item,) = trace
        y, x = item["y"], item["x"]
        assert out[3][hole_column] != ms.EMPTY
        # Base refill, the Chance(60), and no shuffle draw for one candidate.
        assert m.rng.counter == item["rng_after"] + 1
        if after[y][x] == ms.SPECIAL_RED_BLUE_TILE:
            assert out[y][x] in (ms.BLUE, ms.RED)
            converted += 1
        else:
            plain += 1
    assert plain
    assert bool(converted) == can_convert


@pytest.mark.parametrize("patch, message", [
    (lambda p: p["spawning"].update({"<ForceNextCombo>k__BackingField": True}), "Forced-combo"),
    (lambda p: p["rules"]["refillLogicOverride"].update({"disableFirstRoundLogic": True}), "Adaptive thresholds"),
    (lambda p: p["config"]["spawnEngine"].update({"liveEventPieceChancesBySpawned": [1]}), "Live event"),
    (lambda p: p["config"]["spawnEngine"].update({"newColorPickLogic": False}), "Legacy"),
    (lambda p: p["spawning"].update({"specialTilesData": entries({1: 2})}), "Special tile"),
])
def test_every_unported_branch_has_an_approximate_model(patch, message):
    p = profile()
    patch(p)
    with pytest.raises(UnsupportedRefill, match=message):
        SquareRefill.from_profile(p, seed=1)
    m = SquareRefill.from_profile(p, seed=1, approximate=True)
    assert any(message in note for note in m.approximate)
    board = sim_board()
    board[2][2] = ms.EMPTY
    out, _, trace = fill_simulator_board(m, board, [[0] * 7 for _ in range(7)])
    assert len(trace) == 1 and out[2][2] != ms.EMPTY


def test_unknown_piece_counts_as_its_colour_in_the_approximate_fill():
    board, specials = sim_board(), [[0] * 7 for _ in range(7)]
    specials[4][4] = 98            # nothing the refill knows
    board[0][3] = ms.EMPTY
    with pytest.raises(UnsupportedRefill, match="Unported simulator special"):
        fill_simulator_board(SquareRefill.from_profile(profile(), seed=7), board, specials)
    exact_plain = SquareRefill.from_profile(profile(), seed=7)
    plain_specials = [row[:] for row in specials]
    plain_specials[4][4] = 0
    want, _, _ = fill_simulator_board(exact_plain, board, plain_specials)
    approx = SquareRefill.from_profile(profile(), seed=7, approximate=True)
    out, after, _ = fill_simulator_board(approx, board, specials)
    assert out == want and after[4][4] == 98     # the piece itself stays on the board
    assert approx.is_approximate


def test_session_redoes_an_unported_fill_approximately_from_the_same_rng():
    board, specials = sim_board(), [[0] * 7 for _ in range(7)]
    specials[4][4] = 98
    session = ExactRefillSession(SquareRefill.from_profile(profile(), seed=7), board, special_board=specials)
    assert session.begin(board, specials)
    holed = [row[:] for row in board]
    holed[0][3] = ms.EMPTY
    out, _ = session.refill(holed, specials)
    assert out[0][3] != ms.EMPTY and session.failure is None and not session.line_broken
    result = NS(intent_events=(), extra_moves=0, board=out, special_board=specials)
    session.finish(result)
    assert result.exact_refill_supported is False and result.refill_approximate is True
    assert session.approximated == 1 and session.successful == 0
    assert "Unported simulator special" in session.approximation
    # A guessed board is not followed as if it were the game's.
    assert not session.knows(out, specials)


def test_exact_session_marks_nothing_approximate():
    board = sim_board()
    session = ExactRefillSession(SquareRefill.from_profile(profile(), seed=7), board)
    session.begin(board)
    holed = [row[:] for row in board]
    holed[0][3] = ms.EMPTY
    session.refill(holed, [[0] * 7 for _ in range(7)])
    result = NS(intent_events=(), extra_moves=0, board=holed, special_board=None)
    session.finish(result)
    assert result.exact_refill_supported is True and result.refill_approximate is False
    assert session.successful == 1 and session.approximated == 0 and session.approximation is None


def test_live_session_falls_back_to_the_approximate_model(monkeypatch):
    """square_solo_live.exact_refill_session: an unported mode gets a session, not (None, reason)."""
    import square_solo_live

    p = profile()
    p["rules"]["refillLogicOverride"]["disableFirstRoundLogic"] = True
    monkeypatch.setattr(square_solo_live, "_resting_profile", lambda reader, script, snapshot: (p, None))
    monkeypatch.setattr(square_solo_live, "_profile_players", lambda snapshot: p["players"])
    monkeypatch.setattr(engine_refill.EngineRNG, "from_capture",
                        staticmethod(lambda profile: engine_refill.EngineRNG.from_seed(1)))
    snapshot = {"state": {"players": [], "moves": 5}, "special_board": [[0] * 7 for _ in range(7)],
                "slots": []}
    session, reason = square_solo_live.exact_refill_session(None, object(), snapshot, sim_board())
    assert session is not None and reason is None
    assert "Adaptive thresholds" in session.approximation


def test_gui_reports_the_approximate_drop_as_working():
    import memory_gui

    sent = []
    window = NS(_reader_signals=NS(refill=NS(emit=sent.append)))
    session = NS(failure=None, simulations=3, successful=0, approximated=3,
                 approximation="Candy World: candy conversion is not ported")
    memory_gui.MemoryWindow._report_exact_refill(window, session, None)
    usage = sent[-1]["usage"]
    assert usage["active"] and usage["approximate"].startswith("Candy World")
    from refill_monitor import RefillTally
    tally = RefillTally()
    tally.add(sent[-1])
    assert "RADI PRIBLIZNO" in tally.usage_text() and "nije podrzan" not in tally.usage_text()
