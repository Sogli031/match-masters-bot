"""The jelly zone out of memory: three answers, and the cache between them.

The recorded match of 2026-09-12 (Debug/memory_board/board_snapshots.jsonl)
is the shape these tests follow: the played board's ``extraData`` sits empty
the whole match, the zone arrives only on manual dumps as the engine's decoded
``all_infected`` list, the plain poll leaves it null, and between a converted
zone and the next booster throw the engine reports an empty list.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import board_source  # noqa: E402

KEYS = {
    "all_infected": "JellySEallInfected0",
    "source_cell": "JellySEsourceCellToInfected0",
    "target_color": "JellySETargetColor0",
    "phase": "JellySEPhase0",
    "uses_left": "JellySEUsesLeftKeyPlayer0",
}


def snapshot(all_infected=None, extra=None, jelly=True):
    snap = {"columns": 7, "rows": 7, "board_extra_data": {} if extra is None else extra}
    if jelly:
        snap["jelly"] = {"keys": KEYS, "all_infected": all_infected}
    return snap


# ---------------------------------------------------------- jelly_zone_state


def test_engine_points_become_row_col_cells_and_are_verified():
    state = board_source.jelly_zone_state(snapshot([[4, 4], [4, 3], [3, 4]]))
    assert state is not None
    assert state["verified"] is True
    # Engine points are (x, y); cells are (row, col) = (y, x).
    assert state["cells"] == ((3, 4), (4, 3), (4, 4))


def test_engine_empty_list_is_a_positive_no_jelly_reading():
    state = board_source.jelly_zone_state(snapshot([]))
    assert state is not None
    assert state["cells"] == ()
    assert state["verified"] is True


def test_shallow_poll_is_unknown():
    assert board_source.jelly_zone_state(snapshot(None)) is None
    assert board_source.jelly_zone_state(snapshot(None, jelly=False)) is None


def test_agent_without_extra_data_is_unknown():
    snap = snapshot(None)
    snap["board_extra_data"] = None
    assert board_source.jelly_zone_state(snap) is None


def test_named_key_with_points_parses_unverified():
    extra = {KEYS["all_infected"]: "[{1,2},{2,2},{3,2}]"}
    state = board_source.jelly_zone_state(snapshot(None, extra))
    assert state is not None
    assert state["verified"] is False
    assert state["cells"] == ((2, 1), (2, 2), (2, 3))


def test_named_key_with_nothing_behind_it_is_no_jelly():
    for payload in ("", "[]"):
        extra = {KEYS["all_infected"]: payload}
        state = board_source.jelly_zone_state(snapshot(None, extra))
        assert state is not None, payload
        assert state["cells"] == ()


def test_extra_data_without_jelly_key_is_unknown():
    extra = {"SomeOtherModeKey": "3"}
    assert board_source.jelly_zone_state(snapshot(None, extra)) is None


# ---------------------------------------------------------- JellyZoneTracker


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_tracker_serves_last_zone_while_memory_is_silent():
    tracker = board_source.JellyZoneTracker(clock=Clock())
    cells, source = tracker.update(snapshot([[1, 1], [1, 2]]))
    assert (cells, source) == (((1, 1), (2, 1)), "memory")
    cells, source = tracker.update(snapshot(None))
    assert (cells, source) == (((1, 1), (2, 1)), "cache")


def test_tracker_clears_on_engine_empty_list():
    """The bug of 2026-09-12: a consumed zone kept being played."""
    tracker = board_source.JellyZoneTracker(clock=Clock())
    tracker.update(snapshot([[1, 1], [1, 2]]))
    cells, source = tracker.update(snapshot([]))
    assert (cells, source) == ((), "cleared")
    assert tracker.cached is None
    # The silent polls after it no longer resurrect the old zone.
    assert tracker.update(snapshot(None)) == (None, "unknown")
    # And a plain "no jelly" with nothing cached is just that.
    assert tracker.update(snapshot([])) == ((), "none")


def test_tracker_new_zone_replaces_old_one():
    tracker = board_source.JellyZoneTracker(clock=Clock())
    tracker.update(snapshot([[1, 1], [1, 2]]))
    cells, source = tracker.update(snapshot([[5, 5]]))
    assert (cells, source) == (((5, 5),), "memory")
    assert tracker.update(snapshot(None)) == (((5, 5),), "cache")


def test_tracker_unknown_with_nothing_cached():
    tracker = board_source.JellyZoneTracker(clock=Clock())
    assert tracker.update(snapshot(None)) == (None, "unknown")


def test_tracker_reset_forgets_the_zone():
    tracker = board_source.JellyZoneTracker(clock=Clock())
    tracker.update(snapshot([[1, 1], [1, 2]]))
    tracker.reset()
    assert tracker.update(snapshot(None)) == (None, "unknown")


def test_tracker_cache_expires_without_a_confirming_read():
    clock = Clock()
    tracker = board_source.JellyZoneTracker(clock=clock)
    tracker.update(snapshot([[1, 1], [1, 2]]))
    clock.now += board_source.JELLY_ZONE_CACHE_MAX_AGE_S - 1
    assert tracker.update(snapshot(None))[1] == "cache"
    clock.now += 2
    assert tracker.update(snapshot(None)) == (None, "unknown")
    assert tracker.cached is None


def test_tracker_confirming_read_refreshes_age():
    clock = Clock()
    tracker = board_source.JellyZoneTracker(clock=clock)
    tracker.update(snapshot([[1, 1], [1, 2]]))
    clock.now += board_source.JELLY_ZONE_CACHE_MAX_AGE_S - 1
    tracker.update(snapshot([[1, 1], [1, 2]]))
    clock.now += board_source.JELLY_ZONE_CACHE_MAX_AGE_S - 1
    assert tracker.update(snapshot(None))[1] == "cache"
