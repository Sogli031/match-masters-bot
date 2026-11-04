from pathlib import Path

import pytest

from simulator_capture import lab_move
from strategy_lab.simulation import step
from tools.analyze_research import grid, load, observed

SESSION = Path(__file__).resolve().parents[1] / "Debug/research/20261101_021257_color-crush"


@pytest.mark.skipif(not SESSION.is_dir(), reason="recorded Color Crush session not present")
@pytest.mark.parametrize("index,start,target", [
    (0, (3, 1), (3, 2)), (1, (5, 3), (5, 4)),
    (3, (5, 4), (6, 4)), (4, (6, 2), (6, 3)),
    (5, (3, 2), (3, 3)), (8, (1, 2), (1, 3)),
    (9, (6, 5), (6, 6)), (10, (6, 2), (6, 3)),
    (11, (2, 0), (2, 1)), (13, (2, 3), (2, 4)),
    (14, (5, 5), (5, 6)), (16, (4, 2), (4, 3)),
    (17, (5, 2), (5, 3)), (18, (4, 5), (5, 5)),
])
def test_recorded_color_crush_prediction(index, start, target):
    _, capture = load(SESSION / f"{index:03}.json")
    after, _ = load(SESSION / f"{index + 1:03}.json")
    action = dict(start=start, target=target,
                  direction="down" if target[0] > start[0] else "right")
    result = step(lab_move(capture), action)
    assert result["supported"], result
    predicted, want = result["state"], observed(after)
    assert grid(predicted["board"]) == want["board"]
    assert grid(predicted["special_board"]) == want["special_board"]
    assert predicted["engine_refill"].rng.counter == want["rng"]
    assert predicted["turn_state"]["remaining_moves"] == want["moves"]
    local = next(p["model"] for p in after["profile"]["players"] if p["player_type"] == 0)
    assert predicted["score"] == local["score"]


@pytest.mark.skipif(not SESSION.is_dir(), reason="recorded Color Crush session not present")
def test_unported_cascade_special_falls_back():
    _, capture = load(SESSION / "006.json")
    result = step(lab_move(capture), dict(start=[0, 1], target=[1, 1], direction="down"))
    assert not result["supported"]
    assert result["reason"] == "Color Crush cascade special timing is not ported"


def test_live_mode_eligibility_is_solo_only():
    from square_solo_live import eligible
    assert eligible({"id": "color-crush", "pvp_mode": 1})
    assert eligible({"id": "square-match", "pvp_mode": 1})
    assert not eligible({"id": "color-crush", "pvp_mode": 0})
    assert not eligible({"id": "rainbow", "pvp_mode": 1})


def test_color_crush_live_miss_disables_planner(monkeypatch):
    from square_solo_live import Expectation, LiveSquareSolo
    live = LiveSquareSolo()
    live.expectation = Expectation(None, {}, [[1]], [[0]], 7,
                                  capture={"profile": {"rules": {"id": "color-crush"}}})
    monkeypatch.setattr(live, "_save_miss", lambda *args: "")
    live.check_expectation({"board": [[2]], "special_board": [[0]]},
                           {"rng": {"<counter>k__BackingField": 7}})
    assert live.disabled_reason
    assert live.stats["miss"] == 1
    live.reset()
    assert live.disabled_reason is None
