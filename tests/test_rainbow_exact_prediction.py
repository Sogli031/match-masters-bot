from pathlib import Path

import numpy as np
import pytest

import move_strategy as ms
from simulator_capture import lab_move
from strategy_lab.simulation import step
from tools.analyze_research import grid, load, observed

SESSION = Path(__file__).resolve().parents[1] / "Debug/research/20261101_020003_rainbow"
recorded = pytest.mark.skipif(not SESSION.is_dir(), reason="recorded Rainbow session not present")


@recorded
@pytest.mark.parametrize("index,start,target", [
    (0, (3, 3), (3, 4)), (1, (5, 6), (6, 6)),
    (3, (0, 2), (1, 2)), (6, (3, 4), (4, 4)),
    (7, (5, 4), (6, 4)), (9, (5, 5), (5, 6)),
    (15, (2, 2), (2, 3)), (16, (2, 3), (3, 3)),
    (19, (4, 5), (4, 6)), (20, (5, 3), (5, 4)),
    (21, (3, 1), (3, 2)),
])
def test_recorded_rainbow_prediction(index, start, target):
    _, capture = load(SESSION / f"{index:03}.json")
    after, _ = load(SESSION / f"{index + 1:03}.json")
    result = step(lab_move(capture), dict(start=start, target=target,
                  direction="down" if target[0] > start[0] else "right"))
    assert result["supported"], result
    predicted, want = result["state"], observed(after)
    assert grid(predicted["board"]) == want["board"]
    assert grid(predicted["special_board"]) == want["special_board"]
    assert predicted["engine_refill"].rng.counter == want["rng"]
    assert predicted["turn_state"]["remaining_moves"] == want["moves"]
    local = next(p["model"] for p in after["profile"]["players"] if p["player_type"] == 0)
    assert predicted["score"] == local["score"]
    # 000->001 has unexplained energy gain (0->4 on an orange four),
    # possibly a perk. Board, score and RNG are identical for either action;
    # this capture alone cannot identify it. Live planning does not use energy.
    if index != 0:
        assert predicted["booster_state"]["current"] == local["energy"]


@recorded
@pytest.mark.parametrize("index,start,target,reason", [
    (5, (2, 4), (3, 4), "lotus gather"),
    (13, (3, 3), (4, 3), "lotus gather"),
])
def test_unported_rainbow_branches_fall_back(index, start, target, reason):
    _, capture = load(SESSION / f"{index:03}.json")
    result = step(lab_move(capture), dict(start=start, target=target,
                  direction="down" if target[0] > start[0] else "right"))
    assert not result["supported"]
    assert reason in result["reason"]


@recorded
def test_lotus_without_config_is_not_silently_ignored():
    _, capture = load(SESSION / "003.json")
    capture["simulator_input"].pop("froggy_params")
    result = step(lab_move(capture), dict(start=[0, 2], target=[1, 2], direction="down"))
    assert not result["supported"]
    assert "configuration" in result["reason"]


@recorded
def test_live_planner_leaves_lotus_choice_to_froggy_strategy(monkeypatch):
    from square_solo_live import LiveSquareSolo
    from strategy_lab import planner
    record, capture = load(SESSION / "003.json")
    live = LiveSquareSolo()
    monkeypatch.setattr(live, "settled_profile", lambda script: capture["profile"])
    def unexpected_search(*args, **kwargs):
        pytest.fail("exact search must not override unmodeled lotus choices")
    monkeypatch.setattr(planner, "plan_anytime", unexpected_search)
    snapshot = {"board": record["board"], "special_board": record["special_board"],
                "state": {"moves": capture["profile"]["state"]["moves"],
                          "players": record["snapshot_state"]["players"]}}
    outcome = live.plan(None, snapshot)
    assert outcome["move"] is None and "Froggy" in outcome["note"]


def test_gravity_passes_through_stationary_lotus_and_preserves_origins():
    board = np.array([[1, 2, 3, 4], [-1, 3, 4, 5], [0, 4, 5, 6], [2, 5, 6, 1]])
    special = np.zeros_like(board)
    special[1, 0] = ms.SPECIAL_FROGGY_LOTUS
    origins = [[(y, x) for x in range(4)] for y in range(4)]
    out, spec, provenance = ms._drop_boards_with_origins(board, special, origins)
    assert out[:, 0].tolist() == [0, -1, 1, 2]
    assert spec[1, 0] == ms.SPECIAL_FROGGY_LOTUS
    assert provenance[2, 0] == (0, 0)
    ordinary, ordinary_special = ms.drop_boards(board, special)
    np.testing.assert_array_equal(ordinary, out)
    np.testing.assert_array_equal(ordinary_special, spec)


def test_rainbow_live_eligibility_and_miss_guard(monkeypatch):
    from square_solo_live import eligible, Expectation, LiveSquareSolo
    assert eligible({"id": "rainbow", "pvp_mode": 2})
    assert not eligible({"id": "rainbow", "pvp_mode": 0})
    live = LiveSquareSolo()
    live.expectation = Expectation(None, {}, [[1]], [[0]], 7,
                                  capture={"profile": {"rules": {"id": "rainbow"}}})
    monkeypatch.setattr(live, "_save_miss", lambda *args: "")
    live.check_expectation({"board": [[2]], "special_board": [[0]]},
                           {"rng": {"<counter>k__BackingField": 7}})
    assert live.disabled_reason and live.stats["miss"] == 1
