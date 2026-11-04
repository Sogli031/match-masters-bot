"""Strict audit criteria and recorded pre-Cleo exact replay regressions."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import move_strategy as ms
from engine_rng import EngineRNG
from tools.verify_cleo import differences, cleo_actions, measure

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "Debug/research"


def _observed_and_predicted():
    rng = EngineRNG.from_seed(7)
    record = {"board": [[1]], "special_board": [[0]],
              "profile": {"rng": rng.to_capture(), "state": {"moves": 2}}}
    state = {"board": [[1]], "special_board": [[0]],
             "engine_refill": SimpleNamespace(rng=rng), "turn_state": {"remaining_moves": 2}}
    return record, state


@pytest.mark.parametrize("field", ["board", "special_board", "_matrix", "_index", "_seed",
                                  "<counter>k__BackingField", "moves"])
def test_full_hit_requires_every_board_rng_and_move_field(field):
    record, state = _observed_and_predicted()
    assert not differences(record, state)
    if field in ("board", "special_board"):
        record[field][0][0] += 1
    elif field == "_matrix":
        # Equal counters/index/seed do not certify equal RNG state.
        record["profile"]["rng"][field][623] ^= 1
    elif field == "moves":
        record["profile"]["state"]["moves"] += 1
    else:
        record["profile"]["rng"][field] += 1
    assert differences(record, state)


def test_missing_rng_words_or_move_counter_cannot_be_a_hit():
    record, state = _observed_and_predicted()
    del record["profile"]["rng"]["_matrix"]
    del record["profile"]["state"]["moves"]
    assert set(differences(record, state)) == {"rng._matrix", "moves"}


def test_audit_enumerates_both_swipe_directions_without_scenario_inference():
    record = {"special_board": [[0, 0], [ms.SPECIAL_CLEO_BUG, 0]]}
    actions = list(cleo_actions(record))
    assert len(actions) == 4
    assert {tuple(a["start"]) for a in actions} == {(0, 0), (1, 0), (1, 1)}


def test_old_recording_never_infers_config_or_colour_from_the_answer():
    before = {"profile": {}, "special_board": [[ms.SPECIAL_CLEO_BUG]]}
    # A complete missing-input failure must precede reading any answer field.
    result = measure(before, {})
    assert result["verdict"] == "unsupported" and not result["matches"]
    assert "missing capture fields" in next(iter(result["reasons"]))


@pytest.mark.parametrize("folder,first,last,action,billie", [
    ("20261101_024539_square-match", "001", "002",
     {"start": [3, 4], "target": [3, 5], "direction": "right"}, False),
    ("20261102_235024_column-mania", "027", "028",
     {"start": [1, 0], "target": [1, 1], "direction": "right"}, True),
    ("20261104_031513_multiplier-mushrooms", "005", "006",
     {"start": [3, 3], "target": [4, 3], "direction": "down"}, True),
])
def test_recorded_square_billie_and_mushrooms_remain_fully_exact(monkeypatch, folder, first, last, action, billie):
    from tools.analyze_research import load
    from simulator_capture import lab_move
    from strategy_lab import simulation

    directory = RESEARCH / folder
    if not all((directory / f"{name}.json").is_file() for name in (first, last)):
        pytest.skip("recorded transition unavailable")
    before, capture = load(directory / f"{first}.json")
    after, _ = load(directory / f"{last}.json")
    lab = lab_move(capture)
    if billie:
        from engine_billie import BilliePassive
        lab["engine_refill"].billie = BilliePassive.from_record(before)
    monkeypatch.setattr(simulation, "PREFIX_MODES", simulation.PREFIX_MODES | {lab["mode"]})
    original_rng = lab["engine_refill"].rng.to_capture()
    result = simulation.step(lab, action)
    assert result["supported"], result.get("reason")
    assert not differences(after, result["state"])
    assert lab["engine_refill"].rng.to_capture() == original_rng


def test_recorded_ufo_eye_keeps_board_specials_complete_rng_and_moves():
    from tools.analyze_research import load
    from simulator_capture import lab_move
    from strategy_lab import simulation

    directory = RESEARCH / "20261102_225912_hot-color"
    if not all((directory / f"{name}.json").is_file() for name in ("005", "006")):
        pytest.skip("recorded UFO transition unavailable")
    before, capture = load(directory / "005.json")
    after, _ = load(directory / "006.json")
    lab = lab_move(capture)
    model = lab["engine_refill"].clone()
    start, target = (0, 2), (0, 3)
    board, special = ms.swap_cells(before["board"], before["special_board"], start, target)
    candidate = ms.MoveCandidate(start, target, ms.Direction.RIGHT, board, special)
    # Existing UFO port is checked directly: step deliberately rejects its
    # predicted-colour boundary, independently of Cleo support.
    with simulation.rules(lab), simulation.engine_refill(model), ms.ufo_abduction_active(1):
        result = simulation.simulate(lab, candidate)
    assert result is not None
    state = {"board": result.board, "special_board": result.special_board,
             "engine_refill": model,
             "turn_state": {"remaining_moves": lab["turn_state"]["remaining_moves"] - 1 + bool(result.extra_moves)}}
    assert not differences(after, state)


def test_archived_cleo_without_raw_fields_is_uncheckable():
    directory = RESEARCH / "20261104_032503_match-and-hatch"
    if not all((directory / f"{name}.json").is_file() for name in ("025", "026")):
        pytest.skip("recorded Cleo transition unavailable")
    before = json.loads((directory / "025.json").read_text(encoding="utf-8"))
    after = json.loads((directory / "026.json").read_text(encoding="utf-8"))
    assert any(ms.SPECIAL_CLEO_BUG in row for row in before["special_board"])
    assert not any(ms.SPECIAL_CLEO_BUG in row for row in after["special_board"])
    report = measure(before, after)
    assert report["verdict"] == "unsupported" and not report["matches"]
    assert "missing capture fields" in next(iter(report["reasons"]))
