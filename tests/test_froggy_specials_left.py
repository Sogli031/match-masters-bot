"""Ability.GetSpecialsLeftScore as Froggy Fu's entrance evaluation reads it."""
import pytest

from engine_froggy_placement import UnsupportedPlacement, specials_left_score


def test_counts_classic_specials_times_value_and_factor():
    special = [[0, 1, 0], [3, 0, 4], [0, 0, 46]]     # row, bomb, lightning, crosshair
    assert specials_left_score(special, 5, 1.0) == 20
    assert specials_left_score(special, 5, 1.5) == 30


def test_unknown_special_is_refused():
    with pytest.raises(UnsupportedPlacement):
        specials_left_score([[0, 17]], 5, 1.0)       # mushroom: IsSpecial not read yet
