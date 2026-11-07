import pytest

from engine_spawn_weights import create_weights_list_new, get_colors_priority, pick_color


class Draws:
    def __init__(self, values):
        self.values = iter(values)
        self.used = 0

    def next(self):
        self.used += 1
        return next(self.values)


def test_fair_names_consume_draws_in_source_order_even_without_count_tie():
    rng = Draws([3, 4])  # Blue gets A, Red gets A independently.
    counts = {4: 10, 3: 9, 2: 6, 5: 7, 7: 8, 6: 9}
    before = counts.copy()
    assert get_colors_priority(counts, {}, rng, [4, 3, 2, 5, 7, 6]) == [2, 5, 7, 3, 6, 4]
    assert rng.used == 2
    assert counts == before


def test_tied_red_blue_fair_names_and_stable_tie():
    counts = {4: 8, 2: 8, 3: 8}
    # Both A: retain source order Blue then Red, followed by Green.
    assert get_colors_priority(counts, {}, Draws([1, 0]), [4, 2, 3]) == [4, 2, 3]
    # Blue B, Red A: reverse their order.
    assert get_colors_priority(counts, {}, Draws([0, 0]), [4, 2, 3]) == [2, 4, 3]


def test_spawned_color_penalty_is_twice_count_not_once():
    counts = {3: 2, 5: 5}
    assert get_colors_priority(counts, {3: 2}, Draws([]), [3, 5]) == [5, 3]
    assert counts == {3: 2, 5: 5}


def test_captured_count_vector_has_uncovered_tail_not_normalized_weights():
    counts = {4: 10, 3: 9, 2: 6, 5: 7, 7: 8, 6: 9}
    priority = [2, 5, 7, 3, 6, 4]
    thresholds = create_weights_list_new(priority, counts, dict.fromkeys(counts, 1))
    # target floor(49/6)=8, deficits Red2/Yellow1, pool30,
    # base floor(70/6)=11 and extras20/10: 31,21,11,11,11,11.
    assert thresholds == [31, 52, 63, 74, 85, 96]
    assert pick_color(priority, thresholds, 95) == 4
    assert pick_color(priority, thresholds, 96) == 2
    assert pick_color(priority, thresholds, 99) == 2
    assert pick_color(priority, thresholds, 31) == 5


def test_remainder_goes_to_first_strict_maximum_deficit():
    # Board12 cells, target4, deficits3,3,0; pool5, unit0/remainder5.
    counts = {3: 1, 5: 1, 7: 4}
    assert create_weights_list_new([5, 3, 7], counts, {3: 1, 5: 1, 7: 1},
                                   rows=3, columns=4, max_pool_size=5) == [36, 67, 98]


def test_color_weight_subtracts_up_to_weight_minus_one_from_count():
    counts = {3: 8, 5: 8}
    # target8; weight4 reduces Green effective count to5 -> deficit3,
    # extra30 + base35 => weights65/35.
    assert create_weights_list_new([3, 5], counts, {3: 4, 5: 1}, rows=4, columns=4) == [65, 100]
    assert counts == {3: 8, 5: 8}


def test_missing_color_is_not_assigned_an_invented_default_weight():
    with pytest.raises(KeyError):
        create_weights_list_new([3, 5], {3: 1, 5: 2}, {3: 1})


def test_zero_deficit_pool_uses_floor_base_and_fallback():
    counts = {c: 10 for c in range(2, 8)}
    assert create_weights_list_new(list(counts), counts, dict.fromkeys(counts, 1)) == [16, 32, 48, 64, 80, 96]
