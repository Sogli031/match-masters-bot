"""Reader review fixes (2026-09-22): a snapshot survives a failed file write,
stale Frida sessions cannot flag the current one, a half-made attach is torn
down, the CLI survives adb hiccups and hands dead keys back, and rotated
snapshot logs are pruned."""

import io
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import matchmasters_board_reader as reader  # noqa: E402


def _snapshot_message():
    return {"type": "send", "payload": {"type": "board_snapshot", "snapshot": {"x": 1}}}


def _plain_enrich(monkeypatch):
    monkeypatch.setattr(reader, "enrich_snapshot", lambda raw: {"signature": "s1", **raw})


# --- E: a failed write must not lose the snapshot ----------------------------

def test_snapshot_kept_when_jsonl_write_fails(monkeypatch, tmp_path):
    _plain_enrich(monkeypatch)
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    # A directory where the log should be: opening it for append fails.
    output = tmp_path / "board_snapshots.jsonl"
    output.mkdir()
    latest = tmp_path / "latest.json"
    receiver = reader.BoardReader(output, latest, quiet=True)

    receiver.on_message(_snapshot_message(), None)

    assert receiver.last_snapshot == {"signature": "s1", "x": 1}
    assert receiver.snapshot_event.is_set()
    # The other file is still written.
    assert json.loads(latest.read_text(encoding="utf-8"))["snapshot"]["x"] == 1
    assert receiver.write_errors[str(output)] is not None
    assert "Upis snapshot-a nije uspeo" in stderr.getvalue()


def test_write_failure_logged_once_and_cleared_on_success(monkeypatch, tmp_path):
    _plain_enrich(monkeypatch)
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    fail = {"on": True}

    def flaky_latest(path, payload):
        if fail["on"]:
            raise OSError("disk full")

    monkeypatch.setattr(reader, "write_latest", flaky_latest)
    receiver = reader.BoardReader(tmp_path / "log.jsonl", tmp_path / "latest.json", quiet=True)
    receiver.on_message(_snapshot_message(), None)
    receiver.on_message(_snapshot_message(), None)
    assert stderr.getvalue().count("disk full") == 1
    assert receiver.last_snapshot is not None
    fail["on"] = False
    receiver.on_message(_snapshot_message(), None)
    assert receiver.write_errors[str(tmp_path / "latest.json")] is None
    # The log itself was written every time.
    lines = (tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


# --- F: session ids, attach cleanup, adb back-off, dead keys ------------------

def test_late_detach_from_old_session_is_ignored(tmp_path):
    receiver = reader.BoardReader(tmp_path / "a.jsonl", tmp_path / "b.json", quiet=True)
    old = receiver.detached_handler(receiver.new_session())
    current = receiver.detached_handler(receiver.new_session())
    old("application-requested", None)
    assert not receiver.detached_event.is_set()
    current("process-terminated")
    assert receiver.detached_event.is_set()
    assert "process-terminated" in receiver.last_error


def test_dead_match_state_keys_are_remembered(tmp_path):
    receiver = reader.BoardReader(tmp_path / "a.jsonl", tmp_path / "b.json", quiet=True)
    for key, dead in (("0x1/0x2", True), ("0x3/0x4", False), ("0x1/0x2", True), ("0x5/0x6", True)):
        receiver.on_message(
            {"type": "send", "payload": {
                "type": "match_state", "active": False, "reason": "partija zavrsena",
                "logic_key": key, "dead": dead,
            }},
            None,
        )
    assert receiver.dead_logic_keys == ["0x1/0x2", "0x5/0x6"]


def test_merge_dead_logics():
    assert reader.merge_dead_logics(None, ["a"]) is None
    assert reader.merge_dead_logics(7, []) is None
    assert reader.merge_dead_logics(7, ["a", "b"]) == (7, ["a", "b"])
    # The GUI's record only counts for the same process, and is merged in.
    assert reader.merge_dead_logics(7, ["b"], (7, ["a", "b"])) == (7, ["a", "b"])
    assert reader.merge_dead_logics(7, ["b"], (8, ["a"])) == (7, ["b"])
    many = [f"k{i}" for i in range(reader.DEAD_LOGICS_MAX + 5)]
    merged = reader.merge_dead_logics(7, many)
    assert len(merged[1]) == reader.DEAD_LOGICS_MAX
    assert merged[1][-1] == many[-1]


def test_load_recorded_dead_logics(tmp_path):
    path = tmp_path / "dead_logics.json"
    assert reader.load_recorded_dead_logics(path) is None
    path.write_text(json.dumps({"pid": 42, "keys": ["x", ""]}), encoding="utf-8")
    assert reader.load_recorded_dead_logics(path) == (42, ["x"])
    path.write_text("not json", encoding="utf-8")
    assert reader.load_recorded_dead_logics(path) is None


def test_pid_poll_backoff_doubles_to_the_cap():
    assert reader.pid_poll_backoff(0) == 0.0
    assert reader.pid_poll_backoff(1) == reader.PID_POLL_BACKOFF_BASE
    assert reader.pid_poll_backoff(2) == 2 * reader.PID_POLL_BACKOFF_BASE
    assert reader.pid_poll_backoff(50) == reader.PID_POLL_BACKOFF_MAX


class _FakeScript:
    def __init__(self, configure_error=None):
        self.unloaded = False
        self.loaded = False
        self.calls = []
        script = self

        class _Exports:
            def configure(self, *args):
                script.calls.append(("configure", args))
                if configure_error is not None:
                    raise configure_error

            def mark_dead(self, keys):
                script.calls.append(("mark_dead", keys))

        self.exports_sync = _Exports()

    def on(self, name, handler):
        pass

    def load(self):
        self.loaded = True

    def unload(self):
        self.unloaded = True


class _FakeSession:
    def __init__(self, script):
        self.script = script
        self.detached = False
        self.handlers = []

    def on(self, name, handler):
        if name == "detached":
            self.handlers.append(handler)

    def create_script(self, source):
        return self.script

    def detach(self):
        self.detached = True
        for handler in self.handlers:
            handler("application-requested", None)


def _fake_frida(monkeypatch, session):
    device = types.SimpleNamespace(attach=lambda pid, realm=None: session)
    manager = types.SimpleNamespace(add_remote_device=lambda address: device)
    monkeypatch.setattr(
        reader, "frida", types.SimpleNamespace(get_device_manager=lambda: manager)
    )
    monkeypatch.setattr(reader, "game_pid", lambda adb, serial, package: 123)
    monkeypatch.setattr(reader, "verify_namespace_cleaned", lambda adb, serial, pid: None)


def test_failed_attach_after_load_unloads_and_detaches(monkeypatch, tmp_path):
    script = _FakeScript(configure_error=RuntimeError("configure blew up"))
    session = _FakeSession(script)
    _fake_frida(monkeypatch, session)
    agent = tmp_path / "agent.js"
    agent.write_text("// agent", encoding="utf-8")
    receiver = reader.BoardReader(tmp_path / "a.jsonl", tmp_path / "b.json", quiet=True)
    receiver.ready_event.set()

    with pytest.raises(RuntimeError, match="configure blew up"):
        reader.attach_reader(
            "adb", "serial", "pkg", agent, receiver, spawn=False, poll_seconds=0.1,
            dead_logics=(123, ["0x1/0x2"]),
        )
    assert script.loaded and script.unloaded
    assert session.detached
    # Our own teardown's detach is not reported as the game going away.
    assert not receiver.detached_event.is_set()
    assert ("mark_dead", ["0x1/0x2"]) in script.calls


def test_successful_attach_keeps_session_and_reports_its_detach(monkeypatch, tmp_path):
    script = _FakeScript()
    session = _FakeSession(script)
    _fake_frida(monkeypatch, session)
    agent = tmp_path / "agent.js"
    agent.write_text("// agent", encoding="utf-8")
    receiver = reader.BoardReader(tmp_path / "a.jsonl", tmp_path / "b.json", quiet=True)
    receiver.ready_event.set()

    result = reader.attach_reader(
        "adb", "serial", "pkg", agent, receiver, spawn=False, poll_seconds=0.1,
    )
    assert result[1] is session and result[2] is script
    assert not script.unloaded and not session.detached
    session.handlers[0]("process-terminated", None)
    assert receiver.detached_event.is_set()


def _cli_harness(monkeypatch, tmp_path, pid_answers, on_attach=None):
    """Run reader.main with the device side faked; returns (exit, sleeps, attaches)."""
    sleeps = []
    attaches = []
    monkeypatch.setattr(reader, "find_adb", lambda: "adb")
    monkeypatch.setattr(reader, "discover_serial", lambda adb, requested=None: "127.0.0.1:5555")
    monkeypatch.setattr(reader, "ensure_frida_server", lambda adb, serial: None)
    monkeypatch.setattr(reader, "_adb_connect", lambda adb, serial: None)
    monkeypatch.setattr(reader, "load_recorded_dead_logics", lambda path=None: None)
    monkeypatch.setattr(reader.time, "sleep", lambda seconds: sleeps.append(seconds))

    def fake_attach(adb, serial, package, agent, receiver, **kwargs):
        attaches.append(kwargs)
        receiver.new_session()
        if on_attach is not None:
            on_attach(len(attaches), receiver)
        return object(), None, None, 123

    monkeypatch.setattr(reader, "attach_reader", fake_attach)
    answers = iter(pid_answers)

    def fake_pid(adb, serial, package):
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(reader, "game_pid", fake_pid)
    code = reader.main([
        "--quiet",
        "--output", str(tmp_path / "log.jsonl"),
        "--latest", str(tmp_path / "latest.json"),
    ])
    return code, sleeps, attaches


def test_cli_loop_survives_adb_errors_with_backoff(monkeypatch, tmp_path):
    code, sleeps, attaches = _cli_harness(
        monkeypatch, tmp_path,
        [
            reader.ReaderError("error: device offline"),
            reader.ReaderError("error: device offline"),
            123,
            KeyboardInterrupt(),
        ],
    )
    assert code == 0
    assert len(attaches) == 1  # no spurious re-attach on an adb error
    assert sleeps[:2] == [reader.pid_poll_backoff(1), reader.pid_poll_backoff(2)]


def test_cli_reattach_hands_back_dead_keys_of_the_same_process(monkeypatch, tmp_path):
    def on_attach(count, receiver):
        if count == 1:
            receiver.on_message(
                {"type": "send", "payload": {
                    "type": "match_state", "active": False, "reason": "partija zavrsena",
                    "logic_key": "0xa/0xb", "dead": True,
                }},
                None,
            )
            receiver.detached_event.set()  # the session dropped, the game did not

    code, sleeps, attaches = _cli_harness(
        monkeypatch, tmp_path, [123, KeyboardInterrupt()], on_attach
    )
    assert code == 0
    assert len(attaches) == 2
    assert attaches[1]["dead_logics"] == (123, ["0xa/0xb"])


# --- G: rotated logs are pruned ------------------------------------------------

def test_prune_keeps_newest_rotated_and_touches_nothing_else(tmp_path):
    live = tmp_path / "board_snapshots.jsonl"
    live.write_text("live\n", encoding="utf-8")
    stamps = ["20260101_000000", "20260301_120000", "20260919_015501",
              "20260919_043455", "20260920_101010"]
    for stamp in stamps:
        (tmp_path / f"board_snapshots.{stamp}.jsonl").write_text("x", encoding="utf-8")
    others = [
        "latest.json",
        "board_snapshots.2026_01.jsonl",
        "board_snapshots.20200101_000000.jsonl.bak",
        "other.20200101_000000.jsonl",
        "board_snapshots.20200101_000000.json",
    ]
    for name in others:
        (tmp_path / name).write_text("keep", encoding="utf-8")

    deleted = reader.prune_rotated_jsonl(live, keep=3)

    assert sorted(path.name for path in deleted) == [
        "board_snapshots.20260101_000000.jsonl",
        "board_snapshots.20260301_120000.jsonl",
    ]
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == sorted(
        ["board_snapshots.jsonl"]
        + [f"board_snapshots.{stamp}.jsonl" for stamp in stamps[2:]]
        + others
    )


def test_rotation_prunes_to_the_module_limit(monkeypatch, tmp_path):
    live = tmp_path / "board_snapshots.jsonl"
    for stamp in ("20200101_000000", "20200102_000000", "20200103_000000", "20200104_000000"):
        (tmp_path / f"board_snapshots.{stamp}.jsonl").write_text("x", encoding="utf-8")
    live.write_text("y" * 64, encoding="utf-8")
    assert reader.JSONL_ROTATED_KEEP == 3

    rotated = reader.rotate_jsonl_if_large(live, limit=10)

    assert rotated is not None and rotated.exists()
    assert not live.exists()
    names = sorted(path.name for path in tmp_path.iterdir())
    assert len(names) == 3
    assert rotated.name in names
    assert "board_snapshots.20200101_000000.jsonl" not in names
    assert "board_snapshots.20200104_000000.jsonl" in names


def test_small_log_is_neither_rotated_nor_pruned(tmp_path):
    live = tmp_path / "board_snapshots.jsonl"
    live.write_text("y", encoding="utf-8")
    for stamp in ("20200101_000000", "20200102_000000", "20200103_000000", "20200104_000000"):
        (tmp_path / f"board_snapshots.{stamp}.jsonl").write_text("x", encoding="utf-8")
    assert reader.rotate_jsonl_if_large(live, limit=1024) is None
    assert len(list(tmp_path.iterdir())) == 5
