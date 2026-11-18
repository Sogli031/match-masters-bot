"""A research record that saves nothing says why, and an unsettled board is
read again instead of releasing the swipe (Crazy Columns research
20261118_215913: boards after a Foxy Roxy SE booster went missing silently)."""
import threading
from types import SimpleNamespace

import research_recorder


def _recorder(profile, moves_in_dump):
    recorder = research_recorder.ResearchRecorder()
    recorder._reader = SimpleNamespace(settled_profile=lambda script, timeout, gap: profile)
    dump = {"state": {"moves": moves_in_dump}}
    script = SimpleNamespace(exports_sync=SimpleNamespace(dump_board=lambda: dump, arm_booster_detail=lambda on: None,
                                                          arm_mixy_trace=lambda: None))
    return recorder, script


def test_skip_reasons():
    recorder, script = _recorder(None, 5)
    assert recorder.record(script) is None
    assert recorder.last_skip == research_recorder.SKIP_NOT_AT_REST
    recorder, script = _recorder({"state": {"moves": 5}}, 4)
    assert recorder.record(script) is None
    assert recorder.last_skip == research_recorder.SKIP_BOARD_MOVING
    inputs = iter([(1, "move", None), (2, "move", None)])
    recorder, script = _recorder({"state": {"moves": 5}}, 5)
    assert recorder.record(script, input_marker=lambda: next(inputs)) is None
    assert recorder.last_skip == research_recorder.SKIP_NEW_INPUT
    assert research_recorder.SKIP_NEW_INPUT not in research_recorder.RETRY_SKIPS


def _watch(skip, retried=None):
    import memory_gui

    done = threading.Event()
    statuses = []
    research = SimpleNamespace(last_skip=skip)
    window = SimpleNamespace(
        _refill_on=True, _research_on=True, _research_busy=False, _reader_script=object(),
        _snapshot={"signature": "s", "state": {"game_state": -5}}, _research_signature=None,
        _research_done_signature=None, _research=research, _research_retried=retried,
        _reader_signals=SimpleNamespace(status=SimpleNamespace(emit=statuses.append)),
        _record_research=lambda script, snapshot: None)
    original = threading.Thread

    class Inline:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()
            done.set()

    memory_gui.threading.Thread = Inline
    try:
        memory_gui.MemoryWindow._watch_research_board(window)
    finally:
        memory_gui.threading.Thread = original
    assert done.is_set()
    return window, statuses


def test_unsettled_board_is_read_again():
    window, statuses = _watch(research_recorder.SKIP_NOT_AT_REST)
    assert window._research_signature is None and window._research_done_signature is None
    assert statuses and research_recorder.SKIP_NOT_AT_REST in statuses[0]


def test_saved_board_releases_the_swipe():
    window, statuses = _watch(None)
    assert window._research_done_signature == "s" and not statuses


def test_a_board_is_read_again_only_once():
    window, _ = _watch(research_recorder.SKIP_BOARD_MOVING, retried="s")
    assert window._research_done_signature == "s"
