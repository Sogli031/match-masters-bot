"""Native entrance RNG; no claim of a complete activation/placement port."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from engine_froggy import entrance_attempts, preview_entrance, roll_preferred_color
from engine_rng import EngineRNG
from tools.validate_froggy_entrance import RECORDINGS, check_entrance


def test_preferred_color_filters_and_sorts_before_drawing():
    rng = EngineRNG.from_seed(42)
    expected = rng.clone()
    pick = expected.next(3)
    assert roll_preferred_color(rng, {7: 1, 2: 2, 6: 0, 8: 100}, [7, 6, 2]) == (
        2 if pick < 2 else 7)
    assert rng.to_capture() == expected.to_capture()
    state = rng.to_capture()
    assert roll_preferred_color(rng, {8: 100, 6: 0}, [7, 6, 2]) == 1
    assert rng.to_capture() == state


def _slot(x, y, value=0, **flags):
    return dict(x=x, y=y, value=value, score=1,
                **({"canBeMatched": True, "movable": True} | flags))


def test_attempts_use_column_order_without_replacement_and_restore_the_pool():
    slots = [_slot(1, 0), _slot(0, 1), _slot(0, 0), _slot(1, 1, movable=False),
             _slot(2, 0, canBeMatched=False), _slot(2, 1, 40)]
    original = deepcopy(slots)
    rng = EngineRNG.from_seed(9)
    expected = rng.clone()
    wanted = []
    for _ in range(2):
        pool = [(0, 0), (0, 1)]  # (1,0) is a blocked cell.
        chosen = []
        while pool:
            chosen.append(pool.pop(expected.next(100 * len(pool)) // 100))
        wanted.append(chosen)
    assert entrance_attempts(rng, slots, mushroom_target=0, destroy_count=9,
                             high_score_ratio=20, simulated_runs=2,
                             blocked_cells={(1, 0)}) == wanted
    assert rng.to_capture() == expected.to_capture()
    assert slots == original


def test_high_score_weight_cap_ratio_clamp_and_at_least_one_attempt():
    slots = [_slot(0, 0), dict(_slot(1, 0), score=9), dict(_slot(2, 0), score=0)]
    rng = EngineRNG.from_seed(19)
    expected = rng.clone()
    pick = expected.next(600)  # weights 100, 500 (score capped at 5), 0.
    chosen = (0, 0) if pick < 100 else (0, 1)
    assert entrance_attempts(rng, slots, mushroom_target=0, destroy_count=1,
                             high_score_ratio=200, simulated_runs=0) == [[chosen]]
    assert rng.to_capture() == expected.to_capture()


def test_mushrooms_are_shuffled_per_attempt_and_reduce_normal_target_count():
    rng = EngineRNG.from_seed(31)
    expected = rng.clone()
    slots = [_slot(0, 0, 19), _slot(1, 0, 19), _slot(2, 0)]
    wanted = []
    for _ in range(2):
        mushroom = expected.shuffled([(0, 0), (0, 1)])[0]
        expected.next(100)
        wanted.append([mushroom, (0, 2)])
    assert entrance_attempts(rng, slots, mushroom_target=1, destroy_count=2,
                             high_score_ratio=20, simulated_runs=2) == wanted
    assert rng.to_capture() == expected.to_capture()


def test_mushroom_pool_needs_a_movable_matchable_piece_on_an_open_cell():
    slots = [_slot(0, 0, 19, movable=False), _slot(1, 0, 19, canBeMatched=False),
             _slot(2, 0, 19), _slot(3, 0)]
    assert entrance_attempts(EngineRNG.from_seed(1), slots, mushroom_target=1, destroy_count=1,
                             high_score_ratio=0, simulated_runs=1,
                             blocked_cells={(0, 2)}) == [[(0, 3)]]


def test_chance_below_one_draws_nothing():
    fields = {"chanceToPlaceNextToEnergyMatchByActivation": [0], "highScorePieceRatioByActivation": [0],
              "entranceMushroomCountRangeByActivation": [], "entranceDestroyCountRangeByActivation": [],
              "simulatedRuns": 1}
    rng = EngineRNG.from_seed(5)
    profile = {"froggy_booster_fields": fields, "rng": rng.to_capture()}
    preview = preview_entrance(profile, [], activation=1, preferred_color_fix=False)
    assert preview.prefer_energy_adjacent is False
    assert preview.rng_after.counter == rng.counter


@pytest.mark.parametrize("game,activation,index", [
    (game, activation, index) for game, indices in RECORDINGS.items()
    for activation, index in enumerate(indices, 1)
])
def test_recorded_entrance_settings_and_candidate_refill(game, activation, index):
    root = Path(__file__).resolve().parents[1] / "Debug" / "research" / game
    paths = [root / f"{i:03}.json" for i in (index, index + 1)]
    if not all(p.exists() for p in paths):
        pytest.skip("recording not available")
    before, after = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    original = deepcopy(before)
    result = check_entrance(before, after, activation)
    assert result["settings_match"], result
    assert result["generated_attempts"] == 10
    # 054022/002 has a cascade, outside the one-refill validator's coverage.
    if not (game.endswith("054022_moves-multiplier") and index == 2):
        assert result["matching_attempts"], result
    assert before == original
    # Disabling engine fix 7 skips exactly the preferred-colour draw. The
    # attempt targets may consequently differ; no draw is silently consumed.
    no_fix = preview_entrance(before["profile"], before["raw_slots"],
                              activation=activation, preferred_color_fix=False)
    with_fix = preview_entrance(before["profile"], before["raw_slots"],
                                activation=activation, preferred_color_fix=True)
    assert no_fix.preferred_color == 1
    assert with_fix.rng_after.counter == no_fix.rng_after.counter + 1
