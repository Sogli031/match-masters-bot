"""A held Teleport / Energy Boost / Remove Cross is a move in hand in the beam.

None of them costs a move, so unpriced the perk line kept its move and beat
the same swipe by CHARLES_MOVE_VALUE: the beam threw the perks at once.
Column Mania 2026-11-20 08:32 (research 20261120_083206, Checkmate Charles):
Teleport on the first board, then Energy Boost at a 6 of 7 meter for 1893
(5 moves left) against 1884 from a plain swap that keeps its move (a four)
and 1905 from one that spends it.
"""
import json
from pathlib import Path

from strategy_lab import planner, simulation as sim

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "perk_rank" / "column_mania_eb_6of7.json"


def _line(moves, perks, score=0):
    return planner.Line({"score": score, "turn_state": {"remaining_moves": moves},
                         "rank_move_value": 100, "perks": perks})


def test_held_perk_counts_as_a_move_in_hand():
    swap = _line(4, {sim.PERK_ENERGY_BOOST: 1, sim.PERK_TELEPORT: 1})
    perk = _line(5, {sim.PERK_ENERGY_BOOST: 0, sim.PERK_TELEPORT: 1})
    assert planner._rank(swap) == planner._rank(perk) == 600
    assert planner._rank(_line(2, {sim.PERK_REMOVE_CROSS: 1}), steps_left=2) == 200


def test_energy_boost_is_not_thrown_for_a_few_points(monkeypatch):
    from simulator_capture import capture_mode, lab_move
    from tools.analyze_research import capture_from, local_player

    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    capture = capture_from(record)
    monkeypatch.setattr(sim, "PREFIX_MODES", set(sim.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture)
    me = local_player(record)
    lab.update(booster_state={"current": me["energy"], "maximum": me["energy_to_ability"]},
               booster_auto=True, booster_hold=True, rank_move_value=100, perks={sim.PERK_ENERGY_BOOST: 1})
    children = []
    for action in planner.actions(lab):
        result = sim.step(lab, action)
        if result["supported"]:
            children.append((action.get("kind", "swap"), planner.Line(result["state"])))
    best = {(kind, line.moves_left): 0 for kind, line in children}
    for kind, line in children:
        best[kind, line.moves_left] = max(best[kind, line.moves_left], line.score)
    # The perk bought 9 points over the swap that keeps its move.
    assert (best["swap", 5], best["swap", 4], best["energy_boost", 5]) == (1884, 1905, 1893)
    top = max(children, key=lambda c: planner._rank(c[1], 59))
    assert top[0] == "swap"
