import threading
import time
from types import SimpleNamespace

import memory_gui as gui


def test_back_to_back_dumps_wait_the_gap(monkeypatch):
    sent = []
    monkeypatch.setattr(gui.reader, "_export_call", lambda *a, **k: sent.append(time.monotonic()))
    obj = SimpleNamespace(_reader=SimpleNamespace(snapshot_event=threading.Event()), _reader_script=SimpleNamespace(exports_sync=None),
                          _dump_lock=threading.Lock(), _dump_inflight=False, _reader_signals=None)
    for _ in range(2):
        assert gui.MemoryWindow._request_dump(obj)
        deadline = time.monotonic() + 2
        while obj._dump_inflight and time.monotonic() < deadline:
            time.sleep(0.01)
    assert len(sent) == 2 and sent[1] - sent[0] >= gui.DUMP_MIN_GAP_SECONDS - 0.02
