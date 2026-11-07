import copy
import json

import pytest

from simulator_capture import (decode_dictionary, load_capture, prepare_input, resolve_refill_overrides,
                               resolve_square_overrides, versus_adaptive_thresholds)
from tools import capture_match


def profile():
    return {
        "rules": {"id": "square-match", "pvpMode": 1, "colorsCount": 6, "boardSize": 7,
                  "disableMatchPrevention": False,
                  "refillLogicOverride": {"disableFirstRoundLogic": False, "preventMatchChance": 0,
                                          "preventComboChance": 0, "preventSpecialComboChance": 0,
                                          "preventSquareMatchChance": 0},
                  "_colorScoreOverride": {"entries": [{"key": 3, "value": 2}, {"key": 5, "value": 5}]},
                  "maxBoosterUsesPerTurn": 0},
        "state": {"<Turns>k__BackingField": 1, "<TurnsTotal>k__BackingField": 1},
        "spawning": {"<SquareMatchesAvailable>k__BackingField": True, "initialSpawnParams": {},
                     "gameColors": [2, 3, 4, 5, 6, 7], "baseColorWeights": {"entries": []},
                     "colorWeights": {"entries": []}},
        "players": [{"model": {"index": 0, "slotType": 4}, "player_type": 0}],
        "board": {"rows": 7, "columns": 7, "slots": [
            {"x": x, "y": y, "color": 2 + (x + y) % 6, "value": 0}
            for x in range(7) for y in range(7)]},
        "issues": [],
    }


def test_zero_overrides_do_not_disable_last_round_prevention():
    p = profile()
    before = copy.deepcopy(p)
    result = resolve_square_overrides(p)
    assert result["resolved"] is True
    assert result["prevention_thresholds"] == {"match": 100, "combo": 100, "special_combo": 100, "square": 100}
    assert result["max_booster_uses_per_turn"] == 0
    assert p == before


def test_disabling_fixed_branch_does_not_invent_adaptive_formula():
    p = profile()
    p["rules"]["refillLogicOverride"]["disableFirstRoundLogic"] = True
    result = resolve_square_overrides(p)
    assert result["resolved"] is False and result["prevention_thresholds"] is None


def test_positive_overrides_resolve_without_adaptive_formula():
    p = profile()
    p["rules"]["refillLogicOverride"].update(disableFirstRoundLogic=True,
        preventMatchChance=1, preventComboChance=90)
    result = resolve_refill_overrides(p)
    assert result["resolved"]
    assert result["prevention_thresholds"] == {"match": 1, "combo": 90, "special_combo": 0, "square": -1}
    assert "explicit" in result["branch"]


def test_versus_adaptive_thresholds_use_score_moves_and_spawn_bonus():
    p = profile()
    p["rules"].update(pvpMode=0, movesPerTurn=2)
    p["rules"]["refillLogicOverride"].update(disableFirstRoundLogic=True,
        preventSquareMatchChance=80)
    p["state"].update({"<Turns>k__BackingField": 5, "<TurnsTotal>k__BackingField": 6,
                       "currentPlayerIndex": 0, "moves": 2})
    p["config"] = {"spawnEngine": {"rubberBanding": True, "maxDifferenceForPrevent": 40,
        "preventMatchBaselineChance": 50, "preventComboBaselineChance": 50,
        "preventComboMinimumChance": 25, "preventMatchMinimumChance": 0,
        "moveScoreEstimate": 15}}
    p["players"][0]["model"].update(score=0, spawnBonus=3)
    p["players"].append({"player_type": 1, "model": {"index": 1, "score": 0, "spawnBonus": 0}})
    assert versus_adaptive_thresholds(p) == {"match": 85, "combo": 91,
                                             "special_combo": 0, "square": 80}
    resolved = resolve_refill_overrides(p)
    assert resolved["resolved"] and "Versus adaptive" in resolved["branch"]
    p["players"][0]["model"].pop("spawnBonus")
    assert not resolve_refill_overrides(p)["resolved"]


def test_other_modes_are_not_certified_by_square_resolver():
    p = profile()
    p["rules"]["id"] = "mutation-lab-solo-mode"
    assert resolve_square_overrides(p)["resolved"] is False


def test_generic_resolver_covers_other_modes_and_offers_hypotheses():
    p = profile()
    p["rules"]["id"] = "classic"
    p["rules"]["pvpMode"] = 0
    assert resolve_refill_overrides(p)["resolved"] is True
    p["state"]["<TurnsTotal>k__BackingField"] = 5
    result = resolve_refill_overrides(p)
    assert result["resolved"] is False
    hypotheses = result["threshold_hypotheses"]
    assert hypotheses["bez sprecavanja (-1)"] == {"match": -1, "combo": -1, "special_combo": -1, "square": -1}
    assert hypotheses["refillLogicOverride"]["match"] == 0


def test_color_points_are_imported_in_simulator_color_space():
    result = prepare_input(profile())
    assert result["score_rally_values"] == {"2": 2, "3": 5}
    assert result["local_player_index"] == 0
    assert result["full_simulation_ready"] is False


def test_duplicate_or_unread_dictionary_is_rejected():
    with pytest.raises(ValueError):
        decode_dictionary({"entries": [{"key": 3, "value": 2}, {"key": 3, "value": 4}]})
    with pytest.raises(ValueError):
        decode_dictionary({"unresolved": "type"})


def test_package_roundtrip_checksums_and_incomplete_status(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_match, "ROOT", tmp_path)
    p = profile()
    p["issues"] = [{"path": "test", "reason": "not read"}]
    folder = tmp_path / "capture"
    manifest, archive = capture_match.save_package(p, {"version": "test"}, folder)
    assert archive.is_file() and not manifest["capture_complete"]
    loaded = load_capture(folder)
    assert loaded["profile"]["issues"] == p["issues"]
    assert loaded["simulator_input"]["rules_id"] == "square-match"
    (folder / "profile.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_capture(folder)


def test_manifest_cannot_remove_required_integrity_checks(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"schema_version": 1, "files": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="obavezne"):
        load_capture(tmp_path)
