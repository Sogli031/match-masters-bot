"""ARM64 selector invariants, independent of target recording outcomes."""
from types import SimpleNamespace

import pytest

from engine_cleo import CleoPieceModel, select_clone
from engine_refill import UnsupportedRefill
from engine_rng import EngineRNG


def fixture_model(*, cap=40, prevent=100):
    fields = dict(cloneToWholeColor=True, cloneToWholeColorMinimumTargetPieces=1,
                  chanceToPickColorOnlyByPieceCount=0,
                  maxAllowedDifferenceFromDeltaForExtraMoveMatch=3,
                  chanceToPreventExtraMoveOnColorBasedClone=[prevent],
                  clonedNormalPiecesAmountByPieceUse=[8],
                  clonedBluePiecesAmountByPieceUse=[7],
                  maxAllowedClonedPieces=cap, overrideCloneAmount=-1)
    slots = [dict(row=r, col=c, color=3, value=0, canBeMatched=True)
             for r in range(4) for c in range(4)]
    slots[0].update(value=32, color=6, canBeMatched=False)
    slots[1].update(color=2)
    model = CleoPieceModel(fields, tuple(slots), 1, 4, 2)
    candidate = SimpleNamespace(start=(0, 0), target=(0, 1), board=[[1] * 4 for _ in range(4)])
    return model, candidate


def test_probes_start_after_two_chance_draws_and_do_not_consume_main_rng():
    model, candidate = fixture_model()
    rng = EngineRNG.from_seed(72)
    baseline = rng.clone()
    baseline.chance(0)
    baseline.chance(100)
    observed = []

    def probe(positions):
        observed.append((positions, rng.to_capture()))
        clone = rng.clone()
        for _ in range(200):
            clone.next()
        return False, False

    selection = select_clone(model, candidate, rng, probe)
    assert observed
    assert all(state == baseline.to_capture() for _, state in observed)
    assert rng.to_capture() == baseline.to_capture()
    assert selection.color == 3


def test_chance_zero_really_can_take_count_branch():
    # Chance 0x5af5c4c uses <=, not <. Find a seed without relying on a recording.
    seed = next(i for i in range(10000) if EngineRNG.from_seed(i).next() % 100 == 0)
    model, candidate = fixture_model()
    rng = EngineRNG.from_seed(seed)
    selection = select_clone(model, candidate, rng, lambda positions: (False, False))
    assert selection.pick_by_count is True
    assert rng.counter == 2


def test_raw_flags_specials_and_both_swap_positions_are_excluded():
    model, candidate = fixture_model()
    slots = [dict(slot) for slot in model.slots]
    slots[4]["value"] = 19  # board special
    slots[5]["value"] = 6   # classic special; ordinary partner cannot clone onto it
    slots[6]["canBeMatched"] = False
    model = CleoPieceModel(model.fields, tuple(slots), 1, 4, 2)
    selection = select_clone(model, candidate, EngineRNG.from_seed(72), lambda positions: (False, False))
    assert not set(selection.positions) & {(0, 0), (0, 1), (1, 0), (1, 1), (1, 2)}
    assert selection.positions == tuple((r, c) for c in range(4) for r in range(4)
                                        if (r, c) not in {(0, 0), (0, 1), (1, 0), (1, 1), (1, 2)})


def test_hidden_cleo_endpoint_colour_does_not_create_a_probe_group():
    model, candidate = fixture_model()
    probes = []

    def probe(positions):
        probes.append(positions)
        return False, False

    select_clone(model, candidate, EngineRNG.from_seed(72), probe)
    # The only colour 6 is under Cleo, but native merge preparation has
    # replaced both endpoint colours with Empty/None before colour grouping.
    assert len(probes) == 1
    assert len(probes[0]) == 14


def test_cap_uses_stable_random_keys_over_all_selected_positions():
    model, candidate = fixture_model(cap=3)
    rng = EngineRNG.from_seed(72)
    expected_rng = rng.clone()
    expected_rng.chance(0)
    expected_rng.chance(100)
    cells = [(r, c) for c in range(4) for r in range(4) if (r, c) not in ((0, 0), (0, 1))]
    expected = expected_rng.random_key_order(cells, selector="next")[:3]
    selection = select_clone(model, candidate, rng, lambda positions: (False, False))
    assert selection.positions == tuple(expected)
    assert rng.to_capture() == expected_rng.to_capture()


def test_missing_capture_state_refuses_exact_port():
    with pytest.raises(UnsupportedRefill, match="raw slots"):
        CleoPieceModel.from_profile({})


def test_special_partner_refuses_before_consuming_rng():
    model, candidate = fixture_model()
    slots = [dict(slot) for slot in model.slots]
    slots[1]["value"] = 6
    model = CleoPieceModel(model.fields, tuple(slots), 1, 4, 2)
    rng = EngineRNG.from_seed(72)
    before = rng.to_capture()
    with pytest.raises(UnsupportedRefill, match="partner"):
        select_clone(model, candidate, rng, lambda positions: (False, False))
    assert rng.to_capture() == before


def profile_fixture(origin=0, extra=None):
    model, _ = fixture_model()
    fields = dict(model.fields, config={"slotType": 32}, LogicOrigin=origin)
    fields["<PieceType>k__BackingField"] = 32
    return dict(cleo_piece_logic=fields,
                raw_slots=list(model.slots), state={"currentPlayerIndex": 0},
                players=[{"model": {"index": 0, "slotType": 4, "specialAbilityType": 44}}],
                board_extra_data={"entries": []} if extra is None else extra)


@pytest.mark.parametrize("origin,name", [(0, "Default"), (1, "Booster"), (2, "Board")])
def test_uses_counter_uses_typed_enum_template(origin, name):
    key = "CleoCadabraPiece_PieceUsesThisTurnOrigin_" + name
    profile = profile_fixture(origin, {"entries": [{"key": key, "value": "2"}]})
    assert CleoPieceModel.from_profile(profile).uses == 3


def test_missing_counter_key_in_complete_dictionary_is_native_zero():
    assert CleoPieceModel.from_profile(profile_fixture()).uses == 1


@pytest.mark.parametrize("raw", [None, {}, {"unresolved": "budget"},
                                  {"entries": [{"key": "CleoCadabraPiece_PieceUsesThisTurnOrigin_Default",
                                                "value": {"unresolved": "read"}}]}])
def test_incomplete_dictionary_is_not_a_first_use(raw):
    profile = profile_fixture()
    profile["board_extra_data"] = raw
    with pytest.raises(UnsupportedRefill, match="counter"):
        CleoPieceModel.from_profile(profile)


@pytest.mark.parametrize("changed", [{"config": {"slotType": 31}}, {"config": None},
                                     {"<PieceType>k__BackingField": 31},
                                     {"LogicOrigin": None}, {"LogicOrigin": 3}])
def test_unknown_figure_type_or_origin_cannot_select_a_usage_key(changed):
    profile = profile_fixture()
    profile["cleo_piece_logic"].update(changed)
    with pytest.raises(UnsupportedRefill, match="LogicOrigin"):
        CleoPieceModel.from_profile(profile)


def test_direct_slot_type_cannot_replace_missing_native_nested_config():
    profile = profile_fixture()
    fields = profile["cleo_piece_logic"]
    fields.pop("config")
    fields["slotType"] = 32
    with pytest.raises(UnsupportedRefill, match="slotType"):
        CleoPieceModel.from_profile(profile)
