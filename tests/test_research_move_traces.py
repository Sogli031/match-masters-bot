"""research_recorder._move_traces: each record carries the moves played since the last one."""
from types import SimpleNamespace

import move_strategy as ms
import research_recorder


def _script(traces):
    exports = SimpleNamespace(swap_trace_history=lambda: {"traces": traces, "error": None})
    return SimpleNamespace(exports_sync=exports)


def _profile(counter):
    return {"rng": {"<counter>k__BackingField": counter}}


def test_record_keeps_only_the_traces_between_the_two_boards():
    recorder = research_recorder.ResearchRecorder()
    traces = [{"before_rng_counter": 90}, {"before_rng_counter": 100}, {"before_rng_counter": 150},
              {"before_rng_counter": 210}]
    # The first record has no previous board to bound the traces.
    assert recorder._move_traces(_script(traces), _profile(100)) == []
    assert recorder._move_traces(_script(traces), _profile(200)) == traces[1:3]


def test_an_agent_without_the_export_records_no_traces():
    recorder = research_recorder.ResearchRecorder()
    recorder._move_traces(_script([]), _profile(10))
    broken = SimpleNamespace(exports_sync=SimpleNamespace())
    assert recorder._move_traces(broken, _profile(20)) == []


def test_auto_explode_cascade_t_takes_the_row_then_column_listing():
    # Multiplier Mushrooms refill_misses 2026-11-16 191253: row 6 cols 0-2 +
    # column 1 rows 4-6, draw % 5 == 2 -> the game put the bomb on (6, 2).
    cells = frozenset({(6, 0), (6, 1), (6, 2), (5, 1), (4, 1)})
    match = ms.MatchGroup(color=3, cells=cells, kind="t_or_cross")
    previous = (ms._CASCADE_AUTO_EXPLODE, ms._ENGINE_PEEK_DRAWS)
    ms._CASCADE_AUTO_EXPLODE = True
    ms._ENGINE_PEEK_DRAWS = lambda count: [2] * count
    try:
        assert ms._created_special_cell(match, cascade_combos=[match]) == (6, 2)
    finally:
        ms._CASCADE_AUTO_EXPLODE, ms._ENGINE_PEEK_DRAWS = previous
