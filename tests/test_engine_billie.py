"""Billie passive: raw evidence, exact replay and candidate-level fallback."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import move_strategy as ms
from engine_billie import BilliePassive
from engine_refill import UnsupportedRefill, fill_simulator_board

ROOT = Path(__file__).resolve().parents[1]
RECORDING = ROOT / "Debug/research/20261102_230448_column-mania"
LATEST = ROOT / "Debug/research/20261102_235024_column-mania"
NOVEMBER_3 = ROOT / "Debug/research/20261103_000405_column-mania"


@pytest.mark.skipif(not NOVEMBER_3.is_dir(), reason="November 3 Billie recording not present")
def test_special_merge_candidates_fix_all_three_recorded_target_misses():
    from tools.verify_billie import analyze
    report = analyze(NOVEMBER_3)
    assert report["counts"] == {"hit": 18, "miss": 5, "booster": 11}
    for pair in ("006->007", "010->011", "024->025"):
        item = next(x for x in report["transitions"] if x["pair"] == pair)
        assert item["verdict"] == "hit" and item["best"]["rng"]["state_equal"]


@pytest.mark.skipif(not LATEST.is_dir(), reason="Billie latest recording not present")
def test_previous_wrong_bomb_position_now_matches_the_game():
    from tools.analyze_research import load
    from tools.verify_billie import measure
    before, capture = load(LATEST / "027.json")
    after, _ = load(LATEST / "028.json")
    report = measure(before, capture, after, BilliePassive.from_record(before))
    assert report["matches"] and report["best"]["distance"] == 0


@pytest.mark.skipif(not LATEST.is_dir(), reason="Billie latest recording not present")
def test_energy_boost_skips_billie_passive_and_matches_complete_rng(monkeypatch):
    from tools.analyze_research import load
    from simulator_capture import lab_move
    from strategy_lab import simulation
    before, capture = load(LATEST / "031.json")
    after, _ = load(LATEST / "032.json")
    lab = lab_move(capture)
    lab["perks"] = {22: 1}
    monkeypatch.setattr(simulation, "PREFIX_MODES", simulation.PREFIX_MODES | {lab["mode"]})
    out = simulation.step(lab, {"kind": "energy_boost", "start": [4, 2], "target": [4, 3], "direction": "right"})
    assert out["supported"], out.get("reason")
    assert [[int(v) for v in row] for row in out["state"]["board"]] == after["board"]
    assert [[int(v) for v in row] for row in out["state"]["special_board"]] == after["special_board"]
    assert out["state"]["engine_refill"].rng.to_capture() == after["profile"]["rng"]
    assert not any(e["type"] == "billie_passive" for e in out["events"])
    assert not out["state"]["engine_refill"].billie.suppress_once


def test_live_free_perk_suppresses_only_one_passive_without_rng_draws():
    from engine_billie import finish_passive
    from engine_rng import EngineRNG
    model = SimpleNamespace(billie=BilliePassive(6, suppress_once=True), rng=EngineRNG.from_seed(123))
    assert finish_passive(model, object()) is None
    assert model.rng.counter == 0 and not model.billie.suppress_once


def test_drone_falls_into_a_hole_with_its_special_and_origin():
    board = [[1, 2, 3, 4], [2, -1, 4, 1], [3, 0, 1, 2], [4, 2, 3, 1]]
    special = [[0] * 4 for _ in range(4)]
    special[1][1] = ms.SPECIAL_BILLIE_DRONE
    origins = [[(r, c) for c in range(4)] for r in range(4)]
    dropped, specials = ms.drop_boards(board, special)
    with_origins, with_specials, source = ms._drop_boards_with_origins(board, special, origins)
    assert dropped[2][1] == ms.BLOCKED and specials[2][1] == ms.SPECIAL_BILLIE_DRONE
    assert dropped[1][1] == 2 and dropped[0][1] == ms.EMPTY
    assert np.array_equal(dropped, with_origins) and np.array_equal(specials, with_specials)
    assert source[2][1] == (1, 1) and source[0][1] is None


def test_refill_counts_the_hidden_drone_colour_without_matching_or_replacing_it():
    seen = []
    profile = {"players": [{"player_type": 0, "model": {"index": 0, "slotType": 4}}]}
    model = SimpleNamespace(profile=profile, billie=BilliePassive(6), fill=lambda raw, chain: (seen.append(raw), []))
    board, special = [[-1, 1]], [[14, 0]]
    before = copy.deepcopy((board, special))
    result, specials, trace = fill_simulator_board(model, board, special)
    assert seen[0][0][0] == {"color": 6, "value": 25, "canBeMatched": False, "color2": 1, "movable": True}
    assert (board, special) == before and result == board and specials == special
    model.billie = None
    with pytest.raises(UnsupportedRefill, match="raw drone colour"):
        fill_simulator_board(model, board, special)


def test_new_recordings_keep_raw_drone_fields(monkeypatch, tmp_path):
    import research_recorder
    import board_source

    drone = {"x": 3, "y": 6, "color": 6, "value": 25, "flags": 1,
             "canBeMatched": False, "movable": True}
    raw = {"state": {"moves": 5}, "slots": [drone, {"color": 2, "value": 0}]}
    profile = {"state": {"moves": 5}, "rng": {"<counter>k__BackingField": 7}, "rules": {"id": "test"}}
    recorder = research_recorder.ResearchRecorder()
    recorder._reader = SimpleNamespace(settled_profile=lambda *a, **kw: profile)
    monkeypatch.setattr(research_recorder, "RESEARCH_DIR", tmp_path)
    monkeypatch.setattr(board_source, "adapt_memory_snapshot_payload", lambda raw: ([[-1]], [[14]], ()))
    path = recorder.record(SimpleNamespace(exports_sync=SimpleNamespace(dump_board=lambda: raw)))
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    assert saved["billie_slots"] == [drone]


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Billie recording not present")
def test_recorded_passive_hits_require_board_specials_and_full_rng_state():
    from tools.verify_billie import analyze
    from strategy_lab import simulation

    previous = set(simulation.PREFIX_MODES)
    report = analyze(RECORDING)
    assert simulation.PREFIX_MODES == previous
    hits = {item["pair"] for item in report["transitions"] if item["verdict"] == "hit"}
    assert hits == {"010->011", "011->012", "013->014", "016->017", "018->019", "020->021", "023->024",
                    "025->026", "026->027", "030->031", "031->032", "032->033"}
    assert report["counts"] == {"hit": 12, "miss": 5, "booster": 10}
    for item in report["transitions"]:
        if item["verdict"] == "hit":
            assert item["best"]["rng"]["state_equal"]


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Billie recording not present")
def test_missing_raw_colour_and_unsupported_variant_are_refused():
    record = json.loads((RECORDING / "010.json").read_text(encoding="utf-8"))
    with pytest.raises(UnsupportedRefill, match="colour missing"):
        BilliePassive.from_record(record)
    config = BilliePassive.from_record(record, drone_color=6)
    assert config == BilliePassive(6)
    record["snapshot_state"]["players"][0]["special_ability_params"]["chanceToPickEnergyColors"] = "20"
    with pytest.raises(UnsupportedRefill, match="default passive"):
        BilliePassive.from_record(record, drone_color=6)


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Billie recording not present")
def test_live_session_uses_raw_drone_colour_and_predicts_recorded_swap():
    from square_solo_live import exact_refill_session

    record = json.loads((RECORDING / "010.json").read_text(encoding="utf-8"))
    after = json.loads((RECORDING / "011.json").read_text(encoding="utf-8"))
    snapshot = {"stable": True, "board": record["board"], "special_board": record["special_board"],
                "state": record["snapshot_state"],
                "slots": [{"x": 3, "y": 6, "value": 25, "color": 6,
                           "canBeMatched": False, "movable": True}]}
    reader = SimpleNamespace(read_profile=lambda script: record["profile"])
    session, reason = exact_refill_session(reader, object(), snapshot, record["board"])
    assert session is not None, reason
    assert session.use_special_keys
    # Resting random specials are allowed: only firing one breaks the line.
    candidate = next(c for c in ms.generate_candidates(record["board"], record["special_board"])
                     if c.start == (3, 5) and c.target == (4, 5))
    with ms.exact_refill_active(session):
        result = ms._simulate_created_candidate_cached(record["board"], candidate, True,
                    ms.GameMode.VERTICAL_RUSH.value, False, False, {}, {})
    assert result.exact_refill_supported and not session.line_broken
    assert [[int(v) for v in row] for row in result.board] == after["board"]
    assert [[int(v) for v in row] for row in result.special_board] == after["special_board"]
    assert session.current.rng.to_capture() == after["profile"]["rng"]
    assert session.knows(result.board, result.special_board)
    different_specials = copy.deepcopy(result.special_board)
    different_specials[0][0] = 3
    assert not session.knows(result.board, different_specials)


@pytest.mark.parametrize("mode,effect", [
    ("None", "lightning"), ("Column Mania", "crosshair"),
    ("Hot Color", "all_aboard_bandit"), ("Color Crush", "lightning"),
])
def test_unknown_effect_falls_back_only_for_that_candidate_in_every_mode(monkeypatch, mode, effect):
    from engine_refill import ExactRefillSession

    class Model:
        def clone(self):
            return self

        def reset_action(self):
            pass

    calls = []
    def simulate(*args, **kwargs):
        calls.append(ms._ENGINE_REFILL is not None)
        return SimpleNamespace(board=[[2]], special_board=[[0]], cleared_color_counts={},
                               intent_events=[{"type": "special_activation", "special": effect}])

    monkeypatch.setattr(ms, "_simulate_created_candidate", simulate)
    session = ExactRefillSession(Model(), [[1]])
    with ms.exact_refill_active(session):
        result = ms._simulate_created_candidate_cached([[1]], object(), False, mode, False, False, {}, {})
    assert calls == [True, False]
    assert not result.exact_refill_supported and not session.knows([[2]])
    # No match-wide disable: the next candidate still starts with exact RNG.
    assert session.begin([[1]]) and not session.line_broken
    assert ms._EXACT_REFILL is None and ms._ENGINE_REFILL is None


def test_exact_priority_never_promotes_an_unsupported_candidate(monkeypatch):
    def simulate(board, candidate, *args):
        return SimpleNamespace(extra_moves=1, exact_refill_supported=candidate.start == "known")

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate)
    choices = [SimpleNamespace(candidate=SimpleNamespace(start=name, target=name + "-target"))
               for name in ("random", "known")]
    session = SimpleNamespace(knows=lambda board: True, blue_missing=99)
    with ms.exact_refill_active(session):
        chosen = ms.exact_refill_choice(choices, "root", None)
    assert chosen[0] is choices[1] and chosen[1] == "extra"


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Billie recording not present")
def test_monitor_checks_new_raw_drone_records_in_its_worker(monkeypatch, tmp_path):
    import refill_monitor
    from strategy_lab import simulation

    monkeypatch.setattr(refill_monitor, "MISS_DIR", tmp_path)
    monkeypatch.setattr(simulation, "PREFIX_MODES", set(simulation.PREFIX_MODES))
    checker = refill_monitor.TransitionChecker()
    records = [json.loads((RECORDING / name).read_text(encoding="utf-8")) for name in ("010.json", "011.json")]
    for record in records:
        record["billie_slots"] = [{"x": 3, "y": 6, "value": 25, "color": 6,
                                  "canBeMatched": False, "movable": True}]
    assert checker.handle(records[0])["data"]["level"] == "delimicno"
    answer = checker.handle(records[1])
    assert answer["move"]["verdict"] == "ok"
    assert list(tmp_path.iterdir()) == []
