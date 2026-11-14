"""Checkmate Charles knights replayed against the game's recorded areas."""
import json
from pathlib import Path

import pytest

import engine_knights as ek
from engine_refill import ENGINE_SPECIAL_TO_SIM, SIM_TO_ENGINE
from engine_rng import EngineRNG

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/charles_knight_areas.json").read_text(encoding="utf-8"))
ENGINE_TO_SIM = {engine: sim for sim, engine in SIM_TO_ENGINE.items()}


def _simulator_boards(grid):
    board = [[ENGINE_TO_SIM[cell[0]] for cell in row] for row in grid]
    special = [[ek.SIM_KNIGHT if cell[2] == 33 else ENGINE_SPECIAL_TO_SIM.get(cell[2], 99) if cell[2] else 0
                for cell in row] for row in grid]
    return board, special


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["record"])
def test_knight_area_matches_the_recorded_engine(case):
    board, special = _simulator_boards(case["grid"])
    rng = EngineRNG.from_capture(case["rng"])
    state = ek.knight_state({"players": [{"player_type": 0}]}, case["extra"])
    visited = [(y, x) for x, y in case["positions_to_destroy"]]
    area = ek.knight_area(board, special, rng, state, visited, explodes=lambda cell: board[cell[0]][cell[1]] > 0)
    assert [[x, y] for y, x in area] == case["cells"]
    assert rng.counter == case["rng_after"]
    assert state.moved_this_action
    assert state.uses == case["extra"]["CheckmateCharlesPieceUsesThisTurnPlayer0"] + 1


def test_second_knight_activation_in_one_action_adds_nothing():
    case = FIXTURE["cases"][0]
    board, special = _simulator_boards(case["grid"])
    rng = EngineRNG.from_capture(case["rng"])
    state = ek.knight_state({"players": [{"player_type": 0}]}, case["extra"])
    ek.knight_area(board, special, rng, state, [], explodes=lambda cell: True)
    counter = rng.counter
    assert ek.knight_area(board, special, rng, state, [], explodes=lambda cell: True) == []
    assert rng.counter == counter


def test_recorded_config_overrides_the_defaults():
    profile = {"players": [{"player_type": 0}],
               "ability_detail": {"class": ek.ABILITY_CLASS,
                                  "fields": {"knightMovesOnPieceActivation": [2]}}}
    state = ek.knight_state(profile, {"piecesActivatedTimesThisUseKey0": 0,
                                      "CheckmateCharlesPieceUsesThisTurnPlayer0": 0})
    assert state.moves == (2,)
    assert state.favor_blue == (100, 50)
    assert ek.knight_state(profile, {}) is None


def test_simulated_move_uses_the_engine_knight_area():
    """Move 81 of research 20261114_172725: (3,3) down onto a knight line."""
    import move_strategy as ms
    from engine_refill import EngineRefill

    case = next(c for c in FIXTURE["cases"] if c["record"] == "007")
    board, special = _simulator_boards(case["grid"])    # the swap is already applied
    state = ek.knight_state({"players": [{"player_type": 0}]}, case["extra"])
    model = EngineRefill({"rules": {}}, EngineRNG.from_capture(case["rng"]), knights=state)
    candidate = ms.MoveCandidate((3, 3), (4, 3), ms.Direction.DOWN, board, special)
    with ms.engine_refill_active(lambda b, s, chain_combos=0: (b, s), fireworks=model.fireworks_targets):
        result = ms.simulate_candidate(candidate)
    knights = [e for e in result.intent_events
               if e.get("type") == "special_activation" and e.get("special") == "knight"]
    recorded = {(y, x) for x, y in case["cells"]}
    assert knights and all(e.get("exact_targets") for e in knights)
    assert set(map(tuple, knights[0]["effect_cells"])) == recorded
    # The other knights fire too, but only their own (already taken) cell.
    assert all(set(map(tuple, e["effect_cells"])) <= recorded for e in knights[1:])
    assert model.pending_effect_draws == case["rng_after"] - case["rng"]["<counter>k__BackingField"]
    # The measured knight top-up is for the old three-jump model only.
    assert not any(e.get("type") == ms.MEASURED_CHARGE_EVENT and e.get("source") == "knight"
                   for e in result.intent_events)


RECORDED = ROOT / "tests/fixtures/charles_knights_super_sized"
# Research 20261114_172725 (Super Sized): 006->007 and 007->008 the first and
# second knight activation after a booster, 016->017 a plain move, 018->019 a
# knight set off in a cascade, 019->020 the second activation.
RECORDED_MOVES = [("006", "007"), ("007", "008"), ("016", "017"), ("018", "019"), ("019", "020")]


def _record(name, strip_detail=False):
    record = json.loads((RECORDED / f"{name}.json").read_text(encoding="utf-8"))
    if strip_detail:
        record["profile"].pop("ability_detail", None)
    return record


@pytest.mark.parametrize("strip_detail", [False, True], ids=["recorded_config", "default_config"])
@pytest.mark.parametrize("pair", RECORDED_MOVES, ids=lambda pair: "->".join(pair))
def test_recorded_knight_moves_are_exact(pair, strip_detail):
    """Board, specials (the knights that come back) and the whole RNG state."""
    from refill_monitor import check_transition

    before, after = (_record(name, strip_detail) for name in pair)
    result = check_transition(before, after)
    assert result is not None and result["verdict"] == "ok", result


def test_knights_come_back_on_plain_pieces_outside_blue():
    from engine_refill import EngineRefill
    from tools.analyze_research import capture_from

    record = _record("006")
    model = EngineRefill.from_profile(capture_from(record)["profile"], approximate=True)
    board = [list(row) for row in record["board"]]
    special = [[0 if v == ek.SIM_KNIGHT else v for v in row] for row in record["special_board"]]
    out = model.knight_end_move(board, special)
    new = [(r, c) for r, row in enumerate(out) for c, v in enumerate(row) if v == ek.SIM_KNIGHT]
    assert len(new) == ek._pick(model.knights.pieces, model.knights.activations)
    assert all(special[r][c] == 0 and board[r][c] != ek.SIM_BLUE for r, c in new)
