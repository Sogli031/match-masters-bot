"""The first live Showdown matches on the mushroom boards, 2026-11-19.

crosshair_mushrooms (research 20261119_120537, Multiplier Mushrooms, Froggy Fu):
a Crosshair (sim 46, engine 8) in the Froggy entrance, and a Crosshair
picking a mushroom target (009->010). mighty_mushrooms_foxy (research
20261119_120931, Mighty Mushrooms, Foxy Roxy SE): the paint takes mushrooms,
the sprays replay, and the planner no longer refuses board 30.
"""
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# (folder, before, after, action): None = booster, (r, c, direction) = spray,
# ((r, c), (r, c)) = swap.
PAIRS = [("crosshair_mushrooms", "007", "008", None),
         ("crosshair_mushrooms", "009", "010", ((1, 3), (1, 4))),
         ("mighty_mushrooms_foxy", "001", "002", None),
         ("mighty_mushrooms_foxy", "002", "003", (0, 5, "left")),     # a ray of five: Lightning
         ("mighty_mushrooms_foxy", "003", "004", (4, 2, "up")),       # a ray of four
         ("mighty_mushrooms_foxy", "004", "005", None)]


def _record(folder, name):
    return json.loads((FIXTURES / folder / f"{name}.json").read_text(encoding="utf-8"))


def _lab(folder, name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(folder, name)), thresholds=None)
    lab["perks"] = {}
    return lab


def _action(lab, spec):
    from strategy_lab import planner
    if spec is None:
        return {"kind": "booster"}
    if len(spec) == 3:
        r, c, direction = spec
        return next(a for a in planner.actions(lab) if tuple(a["start"]) == tuple(a["target"]) == (r, c)
                    and a.get("direction") == direction)
    return next(a for a in planner.actions(lab) if a.get("kind", "swap") == "swap"
                and (tuple(a["start"]), tuple(a["target"])) == spec)


@pytest.mark.parametrize("folder, before, after, spec", PAIRS)
def test_move_replays_exactly(folder, before, after, spec):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(folder, before)
    assert sim.plan_refusal(lab) is None
    result = sim.step(lab, _action(lab, spec))
    assert result["supported"], result.get("reason")
    state, want = result["state"], observed(_record(folder, after))
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]


def test_froggy_entrance_maps_the_crosshair():
    from engine_froggy_placement import entrance_slots
    record = _record("crosshair_mushrooms", "007")
    sim_to_engine = {c: c for c in range(1, 7)}
    slots = entrance_slots(record["board"], record["special_board"], sim_to_engine, {})
    assert {s["value"] for s in slots if (s["y"], s["x"]) in ((1, 4), (6, 1))} == {8}
