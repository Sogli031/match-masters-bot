"""The live Floor Is Lava mark set is recorded with every run.

Until 2026-09-20 move.json held only the PREDICTED marks, so whether a swap
that matches nothing (disco, special+special) marks a column could not be
answered from Debug/runs. move.json now carries `floor_lava_state` and the
observed delta a `floor_lava_check` against the engine's next reading.
"""
import json
from pathlib import Path

import pytest

import runtime
from move_strategy import GameMode


@pytest.mark.parametrize("index", [5, 7, 10])
def test_jelly_erupts_only_columns_from_original_swap_match(index):
    from refill_monitor import check_transition
    from tools.analyze_research import load

    folder = Path(__file__).resolve().parents[1] / "Debug/research/20261110_042023_the-floor-is-lava"
    if not folder.is_dir():
        pytest.skip("Floor Is Lava Jelly SE recording not present")
    before, after = (load(folder / f"{i:03}.json")[0] for i in (index, index + 1))
    assert check_transition(before, after)["verdict"] == "ok"


@pytest.mark.parametrize("index", [1, 2, 7, 16, 19])
def test_research_replay_uses_recorded_lava_columns(index):
    from tools.analyze_research import load, observed, try_transition

    folder = Path(__file__).resolve().parents[1] / "Debug/research/20261110_011211_the-floor-is-lava"
    if not folder.is_dir():
        pytest.skip("Floor Is Lava research recording not present")
    _, before = load(folder / f"{index:03}.json")
    after, _ = load(folder / f"{index + 1:03}.json")
    matches, closest, _ = try_transition(before, observed(after))
    assert matches, closest


def test_debug_state_prefers_memory_and_is_one_based(monkeypatch):
    monkeypatch.setattr(runtime.recognition, "curr_mode", GameMode.FLOOR_IS_LAVA)
    assert runtime.floor_lava_debug_state((0, 3)) == {
        "columns": [1, 4],
        "source": "memory",
    }
    assert runtime.floor_lava_debug_state(()) == {"columns": [], "source": "memory"}
    runtime.reset_floor_lava_state()
    assert runtime.floor_lava_debug_state(None) == {"columns": [], "source": "tally"}


def test_debug_state_is_none_outside_the_mode(monkeypatch):
    monkeypatch.setattr(runtime.recognition, "curr_mode", GameMode.NONE)
    assert runtime.floor_lava_debug_state((0, 3)) is None


def _previous_run(tmp_path, state, selected_action="move"):
    (tmp_path / "move.json").write_text(
        json.dumps({"floor_lava_state": state, "selected_action": selected_action}),
        encoding="utf-8",
    )
    return tmp_path


def test_check_compares_prediction_with_the_engine(tmp_path):
    run = _previous_run(tmp_path, {"columns": [3, 8], "source": "memory"})
    best_move = {
        "has_direct_match_layer": False,
        "floor_lava_checked_columns_after": [3, 8],
        "floor_lava_destroyed_columns": [],
    }
    check = runtime._floor_lava_prediction_check(
        run, best_move, {"columns": [3, 5, 8], "source": "memory"}
    )
    assert check["matches_prediction"] is False
    assert check["unpredicted_marks"] == [5]
    assert check["missing_marks"] == []
    assert check["has_direct_match_layer"] is False
    same = runtime._floor_lava_prediction_check(
        run, best_move, {"columns": [8, 3], "source": "memory"}
    )
    assert same["matches_prediction"] is True


def test_tally_after_state_is_not_evidence(tmp_path):
    run = _previous_run(tmp_path, {"columns": [3], "source": "tally"})
    check = runtime._floor_lava_prediction_check(
        run,
        {"floor_lava_checked_columns_after": [3]},
        {"columns": [3], "source": "tally"},
    )
    assert check["matches_prediction"] is None


def test_no_check_without_a_recorded_state(tmp_path):
    run = _previous_run(tmp_path, None)
    assert runtime._floor_lava_prediction_check(run, {}, {"columns": []}) is None
    assert runtime._floor_lava_prediction_check(run, {}, None) is None
