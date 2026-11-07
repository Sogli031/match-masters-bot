"""The research record keeps Froggy Fu's loaded fields and this activation's rolls."""
import json
from pathlib import Path
from types import SimpleNamespace

import research_recorder

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def test_research_keeps_froggy_fields(monkeypatch, tmp_path):
    import board_source

    fields = {"lotusCountByActivation": [2, 1], "gatherRadiusByActivation": [2],
              "rolledPreferredColorThisActivation": 5,
              "plannedLotusPositionsThisActivation": [{"x": 1, "y": 2}]}
    profile = {"state": {"moves": 3}, "rng": {"<counter>k__BackingField": 7}, "rules": {"id": "test"},
               "froggy_booster_fields": fields}
    raw = {"state": {"moves": 3, "chain_reaction": 0}, "slots": []}
    monkeypatch.setattr(research_recorder, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(board_source, "adapt_memory_snapshot_payload", lambda value: ([[1]], [[0]], None))
    monkeypatch.setattr(research_recorder, "_grid", lambda value: value)
    monkeypatch.setattr(research_recorder, "_profile_players", lambda value: [])
    recorder = research_recorder.ResearchRecorder()
    recorder._reader = SimpleNamespace(settled_profile=lambda *a, **k: profile)
    script = SimpleNamespace(exports_sync=SimpleNamespace(dump_board=lambda: raw))
    result = json.loads(open(recorder.record(script), encoding="utf-8").read())
    assert result["profile"]["froggy_booster_fields"] == fields


def test_agent_bundle_sizes_match_its_contents():
    # The .js is a Frida bundle: its header gives each asset's byte size, so a
    # hand edit shifts every boundary and the agent can no longer load.
    raw = (TOOLS / "matchmasters_board_dump.js").read_bytes()
    separator = "\n✄\n".encode()
    head, _, body = raw.partition(separator)
    position = 0
    for line in head.decode().split("\n")[1:]:
        position += int(line.split(" ", 1)[0])
        assert position == len(body) or body[position:position + len(separator)] == separator, line
        position += len(separator)


def test_agent_source_and_build_read_the_same_froggy_fields():
    for name in ("matchmasters_board_dump.ts", "matchmasters_board_dump.js"):
        source = (TOOLS / name).read_text(encoding="utf-8")
        assert "froggy_booster_fields:" in source
        assert '"Match3Engine.FroggyFu"' in source
        assert '"_froggyFuAttractionPlanner"' in source
        assert 'type.startsWith("FroggyFuLotusPlacementPlanner")' in source
