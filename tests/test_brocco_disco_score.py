"""A disco ball swiped onto a piece scores its own colour (Vertical Rush,
Brocco Boogie, research 20261119_134322 005->006: +336, the ball's colour 3)."""
import json
from pathlib import Path

FRAMES = Path(__file__).resolve().parent / "fixtures" / "brocco_disco"


def _lab(name):
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from
    capture = capture_from(json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8")))
    lab = lab_move(capture, thresholds=None)
    lab["perks"] = {}
    return lab, capture_mode(capture["profile"]).value


def test_disco_ball_pays_its_colour_and_keeps_the_other_ball(monkeypatch):
    from strategy_lab import simulation as sim
    state, mode = _lab("two_balls_000")
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {mode})
    balls = list(state["engine_refill"].balls)
    # Another ball's swipe first, as the planner tries every action: it must
    # not drop the other ball from the state (ball_colors_at re-lays them).
    sim.step(state, {"start": [1, 3], "target": [0, 3], "direction": "up"})
    assert state["engine_refill"].balls == balls
    result = sim.step(state, {"start": [4, 2], "target": [3, 2], "direction": "up"})
    after, _ = _lab("two_balls_001")
    assert result["state"]["score"] == after["score"]
