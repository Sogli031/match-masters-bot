"""Instance discovery: a flaky identity check must not write the device off."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import matchmasters_board_reader as reader  # noqa: E402

ONLINE = "List of devices attached\n127.0.0.1:5555\tdevice\n"


def _fake_adb(monkeypatch, shell):
    monkeypatch.setattr(
        reader, "_run",
        lambda cmd, timeout=0: types.SimpleNamespace(stdout=ONLINE, stderr="", returncode=0),
    )
    monkeypatch.setattr(reader, "adb_shell", shell)
    monkeypatch.setattr(reader, "_ensure_adb_server", lambda adb: None)
    monkeypatch.setattr(reader, "_adb_connect", lambda adb, serial: None)
    monkeypatch.setattr(reader, "bluestacks_conf_serials", lambda: [])
    monkeypatch.setattr(reader, "DISCOVERY_REPROBE_SECONDS", 0.0)
    monkeypatch.setattr(reader.time, "sleep", lambda seconds: None)


def test_failed_identity_check_is_retried(monkeypatch):
    # 2026-09-15 04:28:39-04:29:26: 127.0.0.1:5555 online the whole time, one
    # identity check failed, and the old code never probed it again.
    calls = {"pm": 0}

    def shell(adb, serial, command, timeout=0):
        if "release" in command:
            return "9"
        if "abi" in command:
            return "x86_64"
        calls["pm"] += 1
        if calls["pm"] == 1:
            raise reader.ReaderError("timeout")
        return "package:" + reader.DEFAULT_PACKAGE

    _fake_adb(monkeypatch, shell)
    assert reader.discover_serial("adb", timeout=5.0) == "127.0.0.1:5555"
    assert calls["pm"] == 2


def test_discovery_error_says_why_the_check_failed(monkeypatch):
    def shell(adb, serial, command, timeout=0):
        raise reader.ReaderError("device offline")

    _fake_adb(monkeypatch, shell)
    try:
        reader.discover_serial("adb", timeout=0.2)
    except reader.ReaderError as exc:
        assert "device offline" in str(exc)
    else:
        raise AssertionError("discovery should have failed")
