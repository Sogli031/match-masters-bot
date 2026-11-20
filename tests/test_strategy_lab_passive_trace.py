"""Coverage for the rewritten ``strategy_lab.passive_trace`` (API of 2026-11-20).

The tracer no longer has ``record()``: it reads a code-proof file, builds the
hook configuration, measures ``libil2cpp.so`` from the game process and attaches
only with ``--allow-live``. These tests exercise all of that without a device:
the live path (frida + adb) is replaced by fakes, so nothing attaches.
"""
from __future__ import annotations

import json

import pytest

from strategy_lab import passive_trace


def _proof(tmp_path, monkeypatch, hooks):
    path = tmp_path / "code_proof.json"
    path.write_text(json.dumps(hooks), encoding="utf-8")
    monkeypatch.setattr(passive_trace, "PROOF_PATH", path)
    return path


def test_configuration_keeps_the_rng_layout_and_adds_hook_defaults(tmp_path, monkeypatch):
    _proof(tmp_path, monkeypatch,
           [{"name": "Next", "rva": "0x1"}, {"name": "Generate", "rva": "0x2", "rng": False}])
    config = passive_trace.configuration(True, 50)
    assert config["rng"] == passive_trace.LAYOUT
    assert config["max_events"] == 50 and config["module_size"] is None
    # A proof entry without a label gets the class::method one; an explicit rng stays.
    assert [hook["label"] for hook in config["hooks"]] == ["RandomWrapper.Next", "RandomWrapper.Generate"]
    assert [hook["rng"] for hook in config["hooks"]] == [True, False]
    # --no-rng clears every hook's flag but keeps the layout: the offsets are still read.
    assert all(hook["rng"] is False for hook in passive_trace.configuration(False, 50)["hooks"])


def test_missing_or_unusable_code_proof_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(passive_trace, "PROOF_PATH", tmp_path / "missing.json")
    with pytest.raises(SystemExit, match="missing code proof"):
        passive_trace.load_code_proof()
    _proof(tmp_path, monkeypatch, [{"name": "EndGame", "rva": "0x1"}])
    with pytest.raises(SystemExit, match="unknown hook"):
        passive_trace.load_code_proof()
    _proof(tmp_path, monkeypatch, [])
    with pytest.raises(SystemExit, match="non-empty list"):
        passive_trace.load_code_proof()


def test_module_size_reads_the_libil2cpp_mapping(monkeypatch):
    maps = ("12c00000-12c01000 r-xp 00000000 00:00 0 \n"
            "73a00000-74100000 r-xp 00000000 00:00 0 /data/app/base.apk!/lib/arm64-v8a/libil2cpp.so\n")
    monkeypatch.setattr(passive_trace.reader, "find_adb", lambda: "adb")
    monkeypatch.setattr(passive_trace.reader, "adb_shell", lambda adb, serial, command: maps)
    assert passive_trace.module_size("serial", 123) == 0x74100000 - 0x73a00000
    monkeypatch.setattr(passive_trace.reader, "adb_shell",
                        lambda adb, serial, command: "12c00000-12c01000 r-xp 00000000 00:00 0 \n")
    with pytest.raises(SystemExit, match="not mapped"):
        passive_trace.module_size("serial", 123)


def test_main_refuses_to_attach_without_allow_live_or_a_valid_duration(tmp_path):
    # Both guards run before frida is imported, so no device is touched.
    with pytest.raises(SystemExit, match="allow-live"):
        passive_trace.main(["--directory", str(tmp_path)])
    for seconds in ("0", "61", "-1"):
        with pytest.raises(SystemExit, match="seconds"):
            passive_trace.main(["--allow-live", "--seconds", seconds, "--directory", str(tmp_path)])
