"""Safety boundaries of the narrow ordinary Cleo merge adapter."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

import engine_cleo
import engine_cleo_simulation as cleo
from engine_refill import EngineRefill, UnsupportedRefill, color_maps
from engine_rng import EngineRNG
import move_strategy as ms


def test_missing_capture_is_explicit_and_does_not_draw_rng():
    model = SimpleNamespace(profile={}, rng=EngineRNG.from_seed(7), spawned_colors={4: 3})
    before = deepcopy(model.__dict__)
    with pytest.raises(UnsupportedRefill, match="raw slots|loaded figure"):
        cleo.simulate_swipe(model, None)
    assert model.__dict__ == before


@pytest.mark.parametrize("mode,square,rules", [
    ("None", True, {"boardModelName": 1}),
    ("Color Crush", False, {"boardModelName": 1}),
    ("None", False, {"boardModelName": 29}),
    ("None", False, {"boardModelName": 1, "specialsAutoExplode": True}),
])
def test_board_layers_reject_before_main_rng_changes(monkeypatch, mode, square, rules):
    monkeypatch.setattr(engine_cleo.CleoPieceModel, "from_profile", lambda profile: object())
    model = SimpleNamespace(profile={"rules": rules}, rng=EngineRNG.from_seed(19), billie=None)
    before = model.rng.to_capture()
    with pytest.raises(UnsupportedRefill, match="board rule"):
        cleo.simulate_swipe(model, None, mode=mode, allow_square_matches=square)
    assert model.rng.to_capture() == before


def test_probe_with_surviving_placeholder_rejects_before_refill():
    # The green target (1,1) is not in the yellow triple being tested.
    # Treating it as a permanent normal green would change native refill counts.
    board = [[3, 3, 3], [1, 2, 4], [4, 1, 2]]
    special = [[0] * 3 for _ in range(3)]
    with pytest.raises(UnsupportedRefill, match="placeholder survives"):
        cleo._resolve(None, board, special, {(0, 0)}, (1, 1))


def test_conversion_four_rejects_instead_of_inventing_special_origin():
    board = [[2, 2, 2, 2], [3, 4, 5, 6], [4, 5, 6, 1], [5, 6, 1, 3]]
    special = [[0] * 4 for _ in range(4)]
    with pytest.raises(UnsupportedRefill, match="initial high-rank"):
        cleo._resolve(None, board, special, {(0, 0)}, (0, 1))


def test_possible_extra_scan_accepts_ordinary_four_setup_only():
    special = [[0] * 4 for _ in range(4)]
    board = [[1, 1, 2, 1], [2, 3, 1, 4], [3, 4, 5, 6], [4, 5, 6, 2]]
    assert cleo._ordinary_extra(board, special)
    special[3][3] = ms.SPECIAL_BOMB
    with pytest.raises(UnsupportedRefill, match="surviving specials"):
        cleo._ordinary_extra(board, special)


def test_failed_native_probe_discards_two_chance_draws_and_spawn_state():
    fields = {
        "cloneToWholeColor": True, "cloneToWholeColorMinimumTargetPieces": 4,
        "chanceToPickColorOnlyByPieceCount": 0,
        "maxAllowedDifferenceFromDeltaForExtraMoveMatch": 2,
        "chanceToPreventExtraMoveOnColorBasedClone": [0],
        "clonedNormalPiecesAmountByPieceUse": [8],
        "clonedBluePiecesAmountByPieceUse": [7],
        "maxAllowedClonedPieces": 20, "overrideCloneAmount": -1,
        "config": {"slotType": 32}, "LogicOrigin": 0,
    }
    slots = []
    colors = (3, 5, 6, 7)
    for r in range(4):
        for c in range(4):
            slots.append({"row": r, "col": c, "value": 0,
                          "color": colors[(r + c) % 4], "color2": 1,
                          "canBeMatched": True, "movable": True, "hitPoints": 1,
                          "status": 0, "skipDestroyTillMoveEnds": False})
    slots[0].update(value=32, color=4, canBeMatched=False)
    profile = {"cleo_piece_logic": fields, "raw_slots": slots,
               "board_extra_data": {"entries": []},
               "rules": {"boardModelName": 1},
               "state": {"currentPlayerIndex": 0},
               "players": [{"player_type": 0, "model": {"index": 0, "slotType": 4}}]}
    _, to_sim = color_maps(profile)
    board = [[to_sim[slots[r * 4 + c]["color"]] for c in range(4)] for r in range(4)]
    special = [[0] * 4 for _ in range(4)]
    board[0][0], special[0][0] = 99, ms.SPECIAL_CLEO_BUG
    swapped, swapped_special = ms.swap_cells(board, special, (0, 0), (0, 1))
    candidate = ms.MoveCandidate((0, 0), (0, 1), ms.Direction.RIGHT, swapped, swapped_special)
    model = EngineRefill(profile, EngineRNG.from_seed(123), spawned_colors={4: 2})
    original_rng = model.rng.to_capture()
    original_profile = deepcopy(model.profile)
    with pytest.raises(UnsupportedRefill, match="placeholder survives|initial high-rank"):
        cleo.simulate_swipe(model, candidate)
    assert model.rng.to_capture() == original_rng
    assert model.spawned_colors == {4: 2}
    assert model.profile == original_profile
