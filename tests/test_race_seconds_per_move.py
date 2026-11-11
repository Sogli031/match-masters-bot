"""Race clock cost per move, re-measured 2026-11-10 (see TIME_BOUND_SECONDS_PER_MOVE).

Debug/runs 2026-11-04..11-10, solo_6 races outside the Solo Challenge: a plain
move drops time_left_seconds by 2.6 s (median) / 2.96 s (mean) to the next
decision, an activation by 6.5 / 6.7 s. The old 6.5 s per move treated every
move as an activation and called turns time-bound that the clock never ended.
"""

import memory_gui
import move_strategy as ms


def test_race_clock_cost_matches_the_plain_move_measurement():
    assert memory_gui.TIME_BOUND_SECONDS_PER_MOVE == 3.0
    assert ms.TIME_BOUND_SECONDS_PER_MOVE_DEFAULT == memory_gui.TIME_BOUND_SECONDS_PER_MOVE
    assert ms.TIME_BOUND_ACTIVATION_SECONDS > 2 * ms.TIME_BOUND_SECONDS_PER_MOVE_DEFAULT


def test_twelve_seconds_allow_four_race_moves():
    turn = ms.TurnState(4, "memory", time_left_seconds=12.0)
    race = ms.StrategyContext("solo_6")
    assert ms._clock_allowed_moves(turn) == 4
    assert not ms._time_bound_turn(turn, race)
    assert ms._time_bound_turn(ms.TurnState(8, "memory", time_left_seconds=12.0), race)


def test_versus_keeps_its_own_clock_cost():
    gui = memory_gui.MemoryWindow
    race = {"is_timer": True, "pvp_mode": memory_gui.PVP_MODE_SOLO}
    versus = {"is_timer": True, "pvp_mode": memory_gui.PVP_MODE_PVP}
    assert gui._seconds_per_move(race, []) == memory_gui.TIME_BOUND_SECONDS_PER_MOVE
    assert gui._seconds_per_move(versus, [{}, {}]) == memory_gui.VERSUS_SECONDS_PER_MOVE == 6.5
    assert gui._seconds_per_move({"is_timer": False}, []) is None
