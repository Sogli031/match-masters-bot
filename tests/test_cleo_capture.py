"""Research records preserve memory evidence without reconstructing colours."""
import json
from types import SimpleNamespace

import research_recorder


def test_research_preserves_cleo_raw_state_for_replay(monkeypatch, tmp_path):
    import board_source

    raw = {
        "state": {"moves": 3, "chain_reaction": 0},
        "slots": [{"row": 2, "col": 4, "value": 32, "color": 6,
                   "canBeMatched": False, "movable": True, "origin": 0},
                  {"row": 0, "col": 0, "value": 4, "color": 3}],
        "board_extra_data": {"CleoCadabraPiece_PieceUsesThisTurnOrigin_Default": "2"},
    }
    profile = {
        "state": {"moves": 3}, "rng": {"<counter>k__BackingField": 71},
        "rules": {"id": "test"},
        "board_extra_data": {"entries": [{"key": "CleoCadabraPiece_PieceUsesThisTurnOrigin_Default", "value": 2}]},
        "cleo_piece_logic": {"overrideCloneAmount": -1, "overrideChanceToCreateExtraMove": -1},
        "cleo_booster_fields": {"<freePieceSwaps>k__BackingField": False},
    }
    monkeypatch.setattr(research_recorder, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(board_source, "adapt_memory_snapshot_payload", lambda value: ([[1]], [[0]], None))
    monkeypatch.setattr(research_recorder, "_grid", lambda value: value)
    monkeypatch.setattr(research_recorder, "_profile_players", lambda value: [])
    recorder = research_recorder.ResearchRecorder()
    recorder._reader = SimpleNamespace(settled_profile=lambda *a, **k: profile)
    script = SimpleNamespace(exports_sync=SimpleNamespace(dump_board=lambda: raw))
    captured = []
    recorder.on_capture = lambda entry, missed: captured.append(entry)

    path = recorder.record(script)
    result = json.loads(open(path, encoding="utf-8").read())
    assert result["cleo_slots"] == [raw["slots"][0]]
    assert result["profile"]["cleo_slots"] == result["cleo_slots"]
    assert result["board_extra_data"] == profile["board_extra_data"]
    assert result["profile"]["board_extra_data"] == profile["board_extra_data"]
    assert result["board_extra_data_view"] == raw["board_extra_data"]
    assert result["profile"]["cleo_piece_logic"] == profile["cleo_piece_logic"]
    assert result["profile"]["cleo_booster_fields"] == profile["cleo_booster_fields"]
    assert result["raw_slots"] == raw["slots"]
    assert result["profile"]["raw_slots"] == raw["slots"]
    assert result["profile"]["rng"] == profile["rng"]
    raw["slots"][0]["color"] = 8
    raw["board_extra_data"].clear()
    assert captured[0]["cleo_slots"][0]["color"] == 6
    assert captured[0]["profile"]["board_extra_data"]


def test_missing_raw_cleo_colour_is_not_inferred(monkeypatch, tmp_path):
    import board_source

    monkeypatch.setattr(research_recorder, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(board_source, "adapt_memory_snapshot_payload", lambda value: ([[6]], [[32]], None))
    monkeypatch.setattr(research_recorder, "_grid", lambda value: value)
    monkeypatch.setattr(research_recorder, "_profile_players", lambda value: [])
    profile = {"state": {"moves": 3}, "rng": {"<counter>k__BackingField": 71}, "rules": {"id": "test"}}
    recorder = research_recorder.ResearchRecorder()
    recorder._reader = SimpleNamespace(settled_profile=lambda *a, **k: profile)
    script = SimpleNamespace(exports_sync=SimpleNamespace(
        dump_board=lambda: {"state": {"moves": 3, "chain_reaction": 0}}))
    result = json.loads(open(recorder.record(script), encoding="utf-8").read())
    assert result["cleo_slots"] == []
    assert result["raw_slots"] is None
    assert result["board_extra_data"] is None
    assert "cleo_piece_logic" not in result["profile"]
