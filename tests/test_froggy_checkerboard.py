"""Froggy Fu + Checkerboard: the perk waits for the last activation.

The player's rule (2026-09-19): do not spend Checkerboard whenever. At 20 s left
the rule arms, and the next booster activation after that -- whenever it comes --
throws it as soon as the lotuses stand: half the board turns one colour and the
lotus collects all of it.
"""
from types import SimpleNamespace

import move_strategy as ms
import runtime

# 2026-09-19 00:07:36, Multiplier Madness, two fresh lotuses, 26.2 s left.
BOARD = [
    [3, 1, 1, 4, 3, 3, 6],
    [4, -1, 1, 6, 4, 2, 1],
    [2, 4, 2, 3, 1, 2, 1],
    [5, 1, 5, 4, 1, 1, 3],
    [2, 1, 5, 5, 6, -1, 3],
    [2, 5, 6, 4, 5, 1, 6],
    [6, 6, 4, 4, 6, 5, 3],
]


def _specials(*lotuses):
    grid = [[0] * 7 for _ in range(7)]
    for row, col in lotuses:
        grid[row][col] = ms.SPECIAL_FROGGY_LOTUS
    return grid


def _turn(seconds):
    return SimpleNamespace(time_left_seconds=seconds, remaining_moves=6)


SOLO_RACE = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6)
PERKS = (runtime.PERK_CHECKERBOARD, runtime.PERK_NONE)


def test_policy_applies_only_to_froggy_in_the_timed_solo_race():
    applies = runtime.froggy_checkerboard_policy_applies
    assert applies(PERKS, True, _turn(60.0), SOLO_RACE)
    assert not applies(PERKS, False, _turn(60.0), SOLO_RACE)
    assert not applies((runtime.PERK_HAMMER, runtime.PERK_NONE), True, _turn(60.0), SOLO_RACE)
    # No match clock to wait for: moves-limited Solo Challenge, versus turn clock.
    challenge = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)
    assert not applies(PERKS, True, _turn(60.0), challenge)
    assert not applies(PERKS, True, _turn(15.0), ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2))
    assert not applies(PERKS, True, _turn(None), SOLO_RACE)


def _observe(tracker, lotuses, seconds):
    return tracker.observe(_specials(*lotuses), _turn(seconds))


def test_next_activation_after_the_clock_arms_throws_the_perk():
    tracker = runtime.FroggyCheckerboardTracker()
    one, two = ((1, 1),), ((1, 1), (4, 5))
    # 00:07:31 activation at 32 s, collects at 26 s and 19 s: all before or
    # across the 20 s mark, and the lotus left standing at 19 s is an old one.
    assert not _observe(tracker, (), 32.5)
    assert not _observe(tracker, two, 26.2)
    assert not _observe(tracker, one, 18.9)
    assert not _observe(tracker, (), 16.0)
    # The next activation, whenever it comes: due from the first board that
    # shows its lotuses until they are gone.
    assert _observe(tracker, two, 11.0)
    assert _observe(tracker, two, 10.5)
    assert _observe(tracker, one, 9.0)
    assert not _observe(tracker, (), 8.5)


def test_activation_with_an_old_lotus_still_standing_counts():
    tracker = runtime.FroggyCheckerboardTracker()
    assert not _observe(tracker, ((1, 1),), 19.0)
    assert _observe(tracker, ((1, 1), (4, 5), (6, 0)), 14.0)


def test_an_activation_before_the_clock_arms_does_not_count():
    tracker = runtime.FroggyCheckerboardTracker()
    assert not _observe(tracker, (), 40.0)
    assert not _observe(tracker, ((1, 1), (4, 5)), 35.0)
    assert not _observe(tracker, ((1, 1), (4, 5)), 19.5)


def test_first_sight_of_a_board_and_a_new_match_never_fire():
    tracker = runtime.FroggyCheckerboardTracker()
    # Nothing to compare the very first board with.
    assert not _observe(tracker, ((1, 1), (4, 5)), 15.0)
    assert not _observe(tracker, (), 3.0)
    # The clock jumped back up: a new match, the old lotus count is forgotten.
    assert not _observe(tracker, ((1, 1), (4, 5)), 104.0)
    assert tracker.last_lotuses == 2 and not tracker.pending
    assert not _observe(tracker, (), None)
    assert tracker.last_lotuses is None

def test_forced_action_targets_the_checkerboard_slot():
    perks = (runtime.PERK_NONE, runtime.PERK_CHECKERBOARD)
    action = runtime._froggy_checkerboard_action(
        BOARD,
        _specials((1, 1), (4, 5)),
        perks,
        None,
        ms.BoosterState.unknown(),
        ms.TurnState.unknown(),
        SOLO_RACE,
        mode="Multiplier Madness",
    )
    assert action is not None
    assert action.perk_key == runtime.PERK_CHECKERBOARD
    assert runtime.resolve_perk_action_slot(action, perks) == 2
    assert (
        runtime._froggy_checkerboard_action(
            BOARD, _specials((1, 1)), (runtime.PERK_HAMMER, runtime.PERK_NONE), None,
            ms.BoosterState.unknown(), ms.TurnState.unknown(), SOLO_RACE,
        )
        is None
    )


# 2026-09-19 00:55:12, Multiplier Mushrooms: the player threw Checkerboard with
# two fresh lotuses standing -- 20 yellow, 20 orange. The bot then played two
# "blue extra before lotus" moves, the pattern collapsed and the lotus collected
# 8 green nine seconds later.
CHECKERBOARD_BOARD = [
    [2, 5, 4, 6, 3, 6, 3],
    [3, 4, 1, 3, 6, -1, 6],
    [6, 1, 3, 6, 3, 6, 3],
    [3, 1, 6, 3, 6, 3, 6],
    [3, 6, 3, 6, 3, 6, 3],
    [6, 3, 6, -1, 6, 3, 6],
    [3, 6, 3, 6, 3, 6, 3],
]


def _rank_checkerboard_board():
    specials = _specials((1, 5), (5, 3))
    rally = {ms.ORANGE: 1.0, ms.YELLOW: 1.0}
    with ms.froggy_gather_region_active(7, True):
        ranked = ms.rank_moves(
            CHECKERBOARD_BOARD, specials, score_rally_values=rally,
            strategy_context=SOLO_RACE,
        )
        lotus = ms.rank_froggy_lotus_moves(
            ranked, CHECKERBOARD_BOARD, specials, score_rally_values=rally,
            strategy_context=SOLO_RACE,
        )
        extra = ms.blue_extra_move_before_lotus(
            ranked, lotus, specials, score_rally_values=rally,
            booster_state=ms.BoosterState(current=0, maximum=7),
            strategy_context=SOLO_RACE,
        )
    return lotus, extra


def test_loaded_board_fires_the_richest_lotus_first_and_no_extra_before_it():
    lotus, extra = _rank_checkerboard_board()
    assert extra is None
    assert lotus[0].froggy_lotus_color == ms.YELLOW
    assert lotus[0].froggy_lotus_collected == 20
    # Two lotuses fired by one colour share the 20 tiles; nothing reads x40.
    assert max(move.froggy_lotus_collected for move in lotus) == 20
