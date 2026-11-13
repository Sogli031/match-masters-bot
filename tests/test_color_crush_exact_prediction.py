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


CASCADE_ROW = Path(__file__).resolve().parent / "fixtures" / "color_crush_cascade_row.json"


def test_refill_check_measures_a_cascade_special_the_planner_still_refuses():
    """Color Crush 2026-11-13 15:26:29 (research 20261113_152616 001->002).

    A row special made and fired in the second cascade: the refill check now
    replays it (exact: board, specials, RNG 737), while the planner keeps the
    cascade-timing boundary until more such moves are measured.
    """
    import json

    from refill_monitor import check_transition
    from tools.analyze_research import capture_from

    pair = json.loads(CASCADE_ROW.read_text(encoding="utf-8"))
    assert check_transition(pair["before"], pair["after"])["verdict"] == "ok"
    move = pair["after"]["refill_input"][2]
    result = step(lab_move(capture_from(pair["before"])),
                  dict(start=move["start"], target=move["target"], direction=move["direction"]))
    assert not result["supported"]
    assert result["reason"] == "Color Crush cascade special timing is not ported"


CLEO = Path(__file__).resolve().parent / "fixtures" / "cleo_color_crush.json"


def test_refill_check_measures_cleo_on_color_crush_the_planner_still_refuses():
    """Color Crush 2026-11-13 15:29:06 (research 20261113_152834 004->005).

    A piece dragged onto the booster's Cleo, a second Cleo and resting row
    specials on the board: the Score Market branch replays it exactly. Only
    the refill check takes it so far; the planner keeps the boundary.
    """
    import json

    from refill_monitor import check_transition
    from tools.analyze_research import capture_from

    pair = json.loads(CLEO.read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"])
    assert result["verdict"] == "ok", result
    move = pair["after"]["refill_input"][2]
    planned = step(lab_move(capture_from(pair["before"])),
                   dict(start=move["start"], target=move["target"], direction=move["direction"]))
    assert not planned["supported"]
    assert "Cleo" in planned["reason"]


CLEO_LIGHTNING = Path(__file__).resolve().parent / "fixtures" / "cleo_lightning_partner.json"


def test_cleo_clones_a_lightning_partner_with_the_engine_targets():
    """Color Crush 2026-11-13 (research 20261113_153230 021->022).

    A Lightning swiped onto the Cleo: the partner fires from the end cell,
    then all seven clones fire, each through GetFireworks. Exact once the
    clone cascade runs with the engine's fireworks (it drew random targets).
    """
    import json

    from refill_monitor import check_transition

    pair = json.loads(CLEO_LIGHTNING.read_text(encoding="utf-8"))
    assert check_transition(pair["before"], pair["after"])["verdict"] == "ok"
