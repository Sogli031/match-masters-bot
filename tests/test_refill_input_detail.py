"""The bot's own played move travels with every board into refill-miss records."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms
import runtime
from tools.trace_refill_miss import played_detail


def _evaluation(start, target, direction):
    board = [[1, 2, 3], [2, 3, 1], [3, 1, 2]]
    candidate = ms.MoveCandidate(start, target, direction, board, [[0] * 3 for _ in range(3)])
    return SimpleNamespace(candidate=candidate)


def test_move_detail_is_the_oriented_swipe(monkeypatch):
    # The orientation itself is move_strategy's business (oriented_swipe tests).
    monkeypatch.setattr(runtime, "oriented_swap_candidate", lambda evaluation: evaluation.candidate)
    evaluation = _evaluation((1, 0), (1, 1), ms.Direction.RIGHT)
    detail = runtime.refill_input_detail("move", evaluation)
    assert detail["action"] == "move"
    assert detail["start"] == [1, 0] and detail["target"] == [1, 1]
    assert detail["direction"] == "right"


def test_perk_detail_is_json_safe():
    perk = SimpleNamespace(perk_key=runtime.PERK_HAMMER, target=(2, 1), follow_up=None)
    detail = runtime.refill_input_detail("activate_perk", None, perk)
    assert detail == {"action": "activate_perk", "perk": runtime.PERK_HAMMER, "perk_target": [2, 1]}


def test_bad_input_never_raises():
    detail = runtime.refill_input_detail("move", object())
    assert detail["action"] == "move" and "error" in detail


def test_gui_keeps_the_detail_with_the_counter():
    import memory_gui as gui
    window = SimpleNamespace(_refill_input=(4, "move"))
    gui.MemoryWindow._note_refill_input(window, "activate_perk", {"perk": "hammer"})
    assert window._refill_input == (5, "activate_perk", {"perk": "hammer"})
    gui.MemoryWindow._note_refill_input(window, "move")
    assert window._refill_input == (6, "move", None)


def test_trace_tool_reads_only_a_recorded_detail():
    assert played_detail({"refill_input": [3, "move", {"action": "move"}]}) == {"action": "move"}
    assert played_detail({"refill_input": [3, "move"]}) is None
    assert played_detail({}) is None


def test_fast_refill_checks_every_move_while_the_clock_allows():
    assert runtime.fast_exact_refill_count(30, None) == 30
    assert runtime.fast_exact_refill_count(30, 60.0) == 30
    assert runtime.fast_exact_refill_count(30, 4.0) == runtime.FAST_EXACT_REFILL_TOP
    assert runtime.fast_exact_refill_count(3, 4.0) == 3


def test_every_mode_ranks_with_the_full_exact_refill():
    import memory_gui as gui
    window = SimpleNamespace(_refill_on=True, _relaxed_turn_clock=lambda rules: False)
    window._is_solo_challenge = lambda state: gui.MemoryWindow._is_solo_challenge(window, state)
    window._strategy_mode = gui.MemoryWindow._strategy_mode
    window._full_exact_refill = lambda state: gui.MemoryWindow._full_exact_refill(window, state)
    for players, pvp in (([{}], 1), ([{}, {}], 2), ([{}] * 4, 2), ([{}, {}], 0)):   # Showdown, Rumble, Party, Versus
        state = {"is_singleplayer_board": len(players) == 1, "players": players, "rules": {"pvp_mode": pvp}}
        assert gui.FULL_EXACT_REFILL_EVERYWHERE
        assert not gui.MemoryWindow._fast_refill(window, state)
        assert not gui.MemoryWindow._prepares_ahead(window, state)


def test_trace_tool_ignores_a_stale_detail_on_a_hand_move():
    detail = {"action": "move"}
    assert played_detail({"refill_input": [5, "move", detail]}, {"refill_input": [4, "move", None]}) == detail
    # A move by hand: the counter did not move, the detail is the bot's previous one.
    assert played_detail({"refill_input": [5, "move", detail]}, {"refill_input": [5, "move", detail]}) is None
