"""Prekidac "Snimaj svaki potez": snima svaku mirnu tablu, iskljucen ne snima nista."""
import threading
from types import SimpleNamespace

import memory_gui as gui
import research_recorder


def _snapshot(signature="board-1", game_state=-5, chain_reaction=0):
    return {"signature": signature, "state": {"game_state": game_state, "chain_reaction": chain_reaction}}


def _window(on=True, snapshot=None):
    calls = []
    done = threading.Event()

    def record(script, snapshot, resting_trigger=False):
        calls.append(snapshot["signature"])
        done.set()

    window = SimpleNamespace(
        _refill_on=True, _research_on=on, _research_busy=False, _research_signature=None,
        _snapshot=snapshot, _reader_script=object(), _record_research=record,
    )
    return window, calls, done


def _watch(window, done):
    gui.MemoryWindow._watch_research_board(window)
    if window._research_signature is not None:
        assert done.wait(2)
        done.clear()


def test_off_still_reads_boards_for_the_refill_check():
    window, calls, done = _window(on=False, snapshot=_snapshot())
    _watch(window, done)
    assert calls == ["board-1"]


def test_master_off_with_toggle_off_reads_nothing():
    window, calls, done = _window(on=False, snapshot=_snapshot())
    window._refill_on = False
    gui.MemoryWindow._watch_research_board(window)
    assert calls == [] and window._research_signature is None


def test_master_off_with_toggle_on_still_records_but_sends_nothing_to_the_check():
    window, calls, done = _window(on=True, snapshot=_snapshot())
    window._refill_on = False
    _watch(window, done)
    assert calls == ["board-1"]
    sent = []
    window._refill_monitor = SimpleNamespace(send=lambda *args: sent.append(args))
    gui.MemoryWindow._on_board_captured(window, {}, False)
    assert sent == []


def test_every_new_board_is_recorded_once_without_auto():
    window, calls, done = _window(snapshot=_snapshot("board-1"))
    _watch(window, done)
    window._research_busy = False
    gui.MemoryWindow._watch_research_board(window)
    assert calls == ["board-1"]
    window._research_busy = False
    window._snapshot = _snapshot("board-2")
    _watch(window, done)
    assert calls == ["board-1", "board-2"]


def test_moving_board_waits_for_rest():
    for moving in (_snapshot(game_state=-6), _snapshot(chain_reaction=2)):
        window, calls, done = _window(snapshot=moving)
        gui.MemoryWindow._watch_research_board(window)
        assert calls == [] and window._research_signature is None


def test_switching_on_starts_a_new_folder():
    window = SimpleNamespace(_research_on=False, _research_signature="old",
                             _research=SimpleNamespace(reset=lambda: resets.append(1)))
    resets = []
    gui.MemoryWindow._on_research_toggled(window, True)
    assert window._research_on and window._research_signature is None and resets == [1]
    gui.MemoryWindow._on_research_toggled(window, False)
    assert not window._research_on and resets == [1]


class _Exports:
    def dump_board(self):
        return {"state": {"moves": 5, "chain_reaction": 0}}


def _recorder(monkeypatch, tmp_path):
    import board_source

    monkeypatch.setattr(research_recorder, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(research_recorder, "_grid", lambda grid: grid)
    monkeypatch.setattr(research_recorder, "_profile_players", lambda snap: [])
    monkeypatch.setattr(board_source, "adapt_memory_snapshot_payload", lambda raw: ([[1]], [[0]], None))
    recorder = research_recorder.ResearchRecorder()
    profile = {"state": {"moves": 5}, "rng": {"<counter>k__BackingField": 7}, "rules": {"id": "test"}}
    recorder._reader = SimpleNamespace(settled_profile=lambda script, timeout, gap: profile)
    return recorder, SimpleNamespace(exports_sync=_Exports())


def test_switching_off_during_the_wait_writes_no_file(monkeypatch, tmp_path):
    recorder, script = _recorder(monkeypatch, tmp_path)
    assert recorder.record(script, enabled=lambda: False) is None
    assert list(tmp_path.rglob("*.json")) == []


def test_off_writes_no_file_but_the_refill_check_gets_the_board(monkeypatch, tmp_path):
    recorder, script = _recorder(monkeypatch, tmp_path)
    captured = []
    recorder.on_capture = lambda entry, missed: captured.append((entry["board"], missed))
    recorder.record(script, enabled=lambda: False)
    assert captured == [([[1]], False)]
    assert list(tmp_path.rglob("*.json")) == []


def test_fast_refill_monitor_uses_one_profile_and_requires_rest(monkeypatch, tmp_path):
    recorder, script = _recorder(monkeypatch, tmp_path)
    profile = {"state": {"moves": 5, "currentGameState": -5},
               "rng": {"<counter>k__BackingField": 7}, "rules": {"id": "test"}}
    reads, captured = [], []
    recorder._reader = SimpleNamespace(read_profile=lambda script: reads.append(script) or profile)
    keys = {"signature": "board", "state_signature": "ready", "game_logic": "logic"}
    snapshot = {"board": [[1]], "special_board": [[0]], "stable": True, **keys}
    state = {"moves": 5, "game_state": -5}
    script.exports_sync.dump_board = lambda: {"state": state, **keys}
    recorder.on_capture = lambda entry, missed: captured.append(entry)
    recorder.record(script, snapshot, enabled=lambda: False, resting_trigger=True, single_profile=True)
    assert reads == [script]
    assert len(captured) == 1
    assert recorder.matching_profile(script, snapshot, None) is profile
    assert recorder.matching_profile(script, snapshot, (1, "move")) is None
    assert recorder.matching_profile(script, dict(snapshot), None) is None
    state["game_state"] = -4
    profile["rng"]["<counter>k__BackingField"] = 8
    recorder.record(script, snapshot, enabled=lambda: False, resting_trigger=True, single_profile=True)
    assert len(captured) == 1


def test_board_changed_during_the_wait_is_reported_as_missed(monkeypatch, tmp_path):
    recorder, script = _recorder(monkeypatch, tmp_path)
    captured = []
    recorder.on_capture = lambda entry, missed: captured.append(missed)
    recorder.record(script, {"board": [[9]]}, resting_trigger=True)
    assert captured == [True]


def test_missed_board_is_marked_in_the_saved_file(monkeypatch, tmp_path):
    import json

    recorder, script = _recorder(monkeypatch, tmp_path)
    path = recorder.record(script, {"board": [[9]]}, resting_trigger=True)
    assert json.loads(open(path, encoding="utf-8").read())["missed_board_before"] is True


def test_same_board_read_twice_is_one_file(monkeypatch, tmp_path):
    recorder, script = _recorder(monkeypatch, tmp_path)
    assert recorder.record(script) is not None
    assert recorder.record(script) is None
    assert len(list(tmp_path.rglob("*.json"))) == 1
