"""Timed solo races price 'unreachable' charge at the measured fire chance.

Over 264 Showdown/Party/Rumble races (2026-09-25..10-08) the booster was still
filled and fired later in the round from 3 moves left and an empty meter 64% of
the time: extras and perks charge without spending the counter. The hard
dead-charge cut-off zeroed that blue (2026-10-08 09:39:48: 3 blue lost to a
plain 21-point move with 3 moves left). Solo Challenge keeps the cut-off.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402

RACE = ms.StrategyContext(ms.STRATEGY_SOLO_6)
CHALLENGE = ms.StrategyContext(ms.STRATEGY_SOLO_6, solo_challenge=True)
EMPTY = ms.BoosterState(current=0, maximum=7, source="memory")


def _blue(cells, moves, context):
    turn = ms.TurnState(remaining_moves=moves, source="memory")
    priority, fill, waste, _phase = ms._base_blue_priority_components_for_cells(
        cells, EMPTY, turn, context
    )
    return priority, fill, waste


def test_race_keeps_three_blue_with_three_moves_left():
    priority, fill, waste = _blue(3.0, 3, RACE)
    expected = ms.BLUE_PRIORITY_WEIGHT * 3.0 * ms.SOLO_RACE_FIRE_CHANCE_TWO_MOVES_FAR
    assert abs(priority - expected) < 1e-9
    assert fill == 0.0 and waste == 0.0


def test_challenge_still_calls_the_same_charge_dead():
    assert _blue(3.0, 3, CHALLENGE)[0] == 0.0


def test_reachable_charge_is_unchanged_in_a_race():
    # Six moves left: never dead, full weight as before.
    assert _blue(3.0, 6, RACE)[0] == ms.BLUE_PRIORITY_WEIGHT * 3.0


def test_fire_chance_table():
    assert ms._solo_race_fire_chance(0, 4.0) == 0.0
    assert ms._solo_race_fire_chance(1, 6.0) == ms.SOLO_RACE_FIRE_CHANCE_LAST_MOVE
    assert ms._solo_race_fire_chance(2, 2.0) == ms.SOLO_RACE_FIRE_CHANCE_TWO_MOVES_NEAR
    assert ms._solo_race_fire_chance(2, 5.0) == ms.SOLO_RACE_FIRE_CHANCE_TWO_MOVES_FAR
    assert ms._solo_race_fire_chance(4, 7.0) == ms.SOLO_RACE_FIRE_CHANCE_MORE
