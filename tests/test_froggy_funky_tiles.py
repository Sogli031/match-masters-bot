"""Froggy Fu on Funky Tiles (research 20261118_110443, Solo).

The entrance never targets a funky cell and the funky markers never move onto
a lotus: with both, all 49 moves (34 swaps, 15 activations) replay with the
game's board, RNG, moves and score.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "froggy_funky_tiles"
# 002->003 activation; 005->006 and 038->039 were one RNG draw off while the
# markers could land on a lotus; 003->004 and 039->040 are swaps with a lotus.
PAIRS = [("002", "003", None), ("005", "006", None), ("038", "039", None),
         ("003", "004", ((2, 5), (3, 5))), ("039", "040", ((4, 2), (4, 1))),
         # Research 20261118_115219 019->020: the lotus next to the Blue three a
         # piece swapped into the Lightning's cell would make (live miss 11:59).
         ("lightning_019", "lightning_020", None),
         # Research 20261118_120934 088->089: a bomb+row swap; the chained bomb
         # clears a funky marker and it blasts (special swaps missed it).
         ("combo_088", "combo_089", ((6, 2), (5, 2)))]


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


def _lab(name):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from
    lab = lab_move(capture_from(_record(name)), thresholds=None)
    lab["perks"] = {}
    return lab


@pytest.mark.parametrize("before, after, swap", PAIRS)
def test_move_replays_exactly(before, after, swap):
    from strategy_lab import simulation as sim
    from tools.analyze_research import grid, observed
    lab = _lab(before)
    assert sim.plan_refusal(lab) is None
    if swap is None:
        action = {"kind": "booster"}
    else:
        action = next(a for a in sim.legal_actions(lab)[1]
                      if (tuple(a["start"]), tuple(a["target"])) == swap)
    result = sim.step(lab, action)
    assert result["supported"], result.get("reason")
    state, want, nxt = result["state"], observed(_record(after)), _lab(after)
    assert grid(state["board"]) == want["board"]
    assert grid(state["special_board"]) == want["special_board"]
    assert state["engine_refill"].rng.counter == want["rng"]
    assert state["turn_state"]["remaining_moves"] == nxt["turn_state"]["remaining_moves"]
    assert state["score"] == nxt["score"]


def test_refill_monitor_checks_froggy_activations():
    """Froggy Fu activations were all "booster, ne moze da se proveri"."""
    from refill_monitor import check_transition
    verdict = check_transition(_record("002"), _record("003"))
    assert verdict["verdict"] == "ok", verdict


def test_unread_funky_cells_refuse_the_plan():
    from strategy_lab import simulation as sim
    lab = _lab("002")
    lab["funky_cells"] = None
    assert "Funky" in sim.plan_refusal(lab)


def test_energy_boost_charges_with_what_the_swipe_sets_off():
    """Funky Tiles live 2026-11-18 11:35 (research 20261118_113037 000->001):
    Energy Boost's three sat on a funky cell, the tile went off, energy 0 -> 7.
    The plan charged the match alone (5), dropped its line and searched 4
    minutes again -- after every Energy Boost that set something off."""
    import square_solo_live as sl
    from strategy_lab.simulation import step

    def lab(name, perks):
        state = _lab(name)
        charge = state.get("booster_state") or {}
        return dict(state, perks=perks, booster_auto=True,
                    booster_state={"current": charge.get("current") or 0, "maximum": charge.get("maximum")})

    after = step(lab("eb_000", {22: 1, 3: 1}),
                 {"kind": "energy_boost", "start": [5, 4], "target": [5, 5], "direction": "right"})["state"]
    assert after["booster_state"]["current"] == 7
    assert sl._plan_key(after) == sl._plan_key(lab("eb_001", {3: 1}))


def test_move_waits_for_a_destroyed_funky_marker(monkeypatch):
    """Live 2026-11-18 11:40:37: cell_types still held one funky cell, the
    planner predicted the wrong RNG for its Teleport and dropped its line."""
    import types
    import memory_gui as mg
    from move_strategy import GameMode

    def snapshot(cells, signature="a"):
        grid = [[3 if (r, c) in cells else 1 for c in range(7)] for r in range(7)]
        return {"signature": signature, "cell_types": grid, "state": {}}

    window = types.SimpleNamespace(_effective_mode=lambda state: GameMode.FUNKY_TILES,
                                   _request_dump=lambda: None)
    pending = lambda snap: mg.MemoryWindow._funky_cells_pending(window, snap)
    clock = [100.0]
    monkeypatch.setattr(mg.time, "monotonic", lambda: clock[0])
    assert not pending(snapshot({(1, 3), (5, 5)}))
    assert pending(snapshot({(5, 5)}))
    clock[0] += mg.FUNKY_CELLS_WAIT_SECONDS
    assert not pending(snapshot({(5, 5)}))      # never stalls the bot for good
    assert pending(snapshot({(5, 5)}, signature="b"))
