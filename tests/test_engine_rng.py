import hashlib
import struct

import pytest

from engine_rng import EngineRNG


def test_seed_recurrence_and_first_generation_reference_vector():
    # Independently evaluated uint32 ARM operations in JavaScript; deliberately
    # unlike the standard MT19937 seed recurrence and twist.
    rng = EngineRNG.from_seed(1)
    assert rng.matrix[:5] == [1, 0, 1812433253, 3713160355, 626640099]
    assert [rng.next() for _ in range(6)] == [977509196, 421939118, 336263288,
                                           1747538373, 1666694184, 1084859971]
    assert rng.matrix[-3:] == [2038624979, 884875020, 173264881]


@pytest.mark.parametrize("word,expected", [(0, 0), (1, 4194449), (2, 2),
    (0x80000000, 135275013), (0xFFFFFFFF, 1876958200),
    (2859156178, 448691478), (1013477264, 1799986896)])
def test_temper_and_positive_modulo_known_words(word, expected):
    matrix = [0] * 624
    matrix[1] = word
    assert EngineRNG(matrix, 1, 0).next() == expected


def test_index_cycle_is_623_not_matrix_length_624():
    rng = EngineRNG([0] * 624, 622, 0, 622)
    rng.matrix[622] = 1
    rng.matrix[623] = 0xFFFFFFFF
    assert rng.next() == 4194449
    assert rng.index == 0 and rng.counter == 623
    # index zero triggers a new generation, instead of outputting matrix[623].
    old = rng.matrix[:]
    rng.next()
    assert rng.matrix != old and rng.index == 1 and rng.counter == 624


def test_capture_restore_and_clone_do_not_alias_matrix():
    original = EngineRNG.from_seed(-1, 623)
    raw = original.to_capture()
    restored = EngineRNG.from_capture(raw)
    clone = original.clone()
    expected = [original.next() for _ in range(630)]
    assert [restored.next() for _ in range(630)] == expected
    assert [clone.next() for _ in range(630)] == expected
    raw["_matrix"][0] = 0
    assert original.matrix is not clone.matrix and raw["_matrix"] is not restored.matrix


def test_equal_ranges_and_zero_max_do_not_consume_rng():
    rng = EngineRNG.from_seed(123)
    before = rng.to_capture()
    assert rng.range(4, 4) == 4
    assert rng.next(0) == 0
    assert rng.normal_range(-3, -3) == -3
    assert rng.to_capture() == before
    with pytest.raises(ValueError):
        rng.range(8, 2)
    assert rng.to_capture() == before


def test_chance_uses_inclusive_threshold_and_always_consumes():
    # A zero matrix at a nonzero index produces zero, distinguishing <= from <.
    rng = EngineRNG([0] * 624, 1, 0)
    assert rng.chance(0) is True
    assert rng.chance(-1) is False
    assert rng.chance(100) is True
    assert rng.counter == 3


def test_range_and_normal_range_preserve_engine_draw_counts():
    rng = EngineRNG.from_seed(7)
    reference = rng.clone()
    expected = reference.next() % 100
    assert rng.range(0, 100) == expected
    assert rng.counter == 1
    expected = int((reference.range(-100, -1) + reference.range(-100, -1)) / 2)
    assert rng.normal_range(-100, -1) == expected
    assert rng.counter == 3


def test_random_key_order_is_stable_and_draws_once_per_item():
    rng = EngineRNG([0] * 624, 1, 0)
    assert rng.random_key_order(["b", "a", "c"], selector="value") == ["b", "a", "c"]
    assert rng.counter == 3
    assert rng.random_key_order([1], selector="next") == [1]
    assert rng.counter == 3
    with pytest.raises(ValueError):
        rng.random_key_order([1, 2], selector="unresolved")


def test_bad_capture_cannot_silently_be_used_as_python_rng():
    with pytest.raises(ValueError):
        EngineRNG([0] * 623, 0, 0)
    with pytest.raises(ValueError):
        EngineRNG([0] * 624, 624, 0)


def test_shuffle_uses_next_random_keys_returns_copy_and_preserves_ties():
    rng = EngineRNG([0] * 624, 1, 0)
    original = ["c", "a", "b"]
    shuffled = rng.shuffled(original)
    assert shuffled == original and shuffled is not original
    assert rng.counter == 3
    singleton = [1]
    assert rng.shuffled(singleton) is singleton
    assert rng.counter == 3


def test_rng_reconstructs_full_recorded_square_match_matrix():
    # SHA-256 of packed 624 UInt32 words captured in the live game's RNG,
    # profile 20261031_223909_674630. No live game or local capture file needed.
    rng = EngineRNG.from_seed(453592007, 387)
    digest = hashlib.sha256(struct.pack("<624I", *rng.matrix)).hexdigest()
    assert digest == "3745dd660c1d020136b105d6ccecef6b898fe766f2dfc54e750e3bf5d825b725"
    assert rng.index == 387 and rng.counter == 387
    assert [rng.next() for _ in range(6)] == [295354990, 2114269082, 624800351,
                                           1357727170, 329786734, 532426810]
