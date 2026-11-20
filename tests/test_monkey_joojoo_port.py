"""Monkey JooJoo (booster 40) activation port: what is measured and what holds.

Super Sized Solo research 20261120_111530 (12 activations, one game): 10 of
10 usable activations are exact (board, specials, RNG, points, meter); 006->007
spans two activations and 009->010 is uncharged. Booster 40 is in
square_solo_live.EXACT_PLAN_BOOSTERS.
"""
import json
from pathlib import Path

import pytest

import engine_monkey
from simulator_capture import capture_mode, lab_move
from strategy_lab import simulation
from tools.analyze_research import capture_from

FIXTURES = Path(__file__).parent / "fixtures" / "monkey_joojoo" / "20261120_111530_super-sized"
SKULL = 19


def _load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _skulls(record):
    return sum(int(v) == SKULL for row in record["special_board"] for v in row)


def _activate(before_name, monkeypatch):
    """Play the recorded activation that led to the next record."""
    before, after = _load(before_name), _load(f"{int(before_name) + 1:03d}")
    capture = capture_from(before)
    # Measurement only: the planner still refuses this booster.
    monkeypatch.setattr(simulation, "MONKEY_JOOJOO_PORTED", True)
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(capture["profile"]).value})
    lab = lab_move(capture)
    lab["booster_type"] = 40
    return simulation.step(lab, {"kind": "booster"}), after


def test_solo_config_is_read():
    config = engine_monkey.config_from(_load("002")["profile"])
    assert config["skullsPerActivation"] == [4, 1]
    assert config["autoExplodeAmount"] == 3
    assert config["chanceToPickMatchablePiece"] == 20
    assert config["scoreTarget"] == 35
    assert config["maxTries"] == 5 and config["piecesAmount"] == 5


def test_port_is_enabled_and_planned():
    import square_solo_live
    assert simulation.MONKEY_JOOJOO_PORTED is True
    assert square_solo_live.MONKEY_JOOJOO in square_solo_live.EXACT_PLAN_BOOSTERS


def test_throw_places_the_configured_skulls():
    config = engine_monkey.config_from(_load("002")["profile"])
    # skullsPerActivation[min(ActivatesThisTurn - 1, n - 1)]: 4, then 1 each.
    assert [engine_monkey.skull_pick(config, i) for i in range(1, 5)] == [4, 1, 1, 1]


def test_resting_target_follows_the_recording():
    # The recording's resting boards after throws 1..12: 4, 6, 7, ... 16. Each
    # throw raises that count by the config's skulls; the second by two.
    config = engine_monkey.config_from(_load("002")["profile"])
    recorded = [_skulls(_load(f"{i:03d}")) for i in (3, 7, 9, 10, 12, 14, 16, 18, 20, 22, 24, 26)]
    assert recorded == [4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    count = 0
    for wanted in recorded:
        count = engine_monkey.skull_target(config, count)
        assert count == wanted


def test_candidates_are_plain_allowed_pieces_and_one_draw_each():
    record = _load("002")
    capture = capture_from(record)
    lab = lab_move(capture)
    board, special = lab["board"], lab["special_board"]
    from engine_refill import color_maps

    to_sim = color_maps(lab["engine_refill"].profile)[1]
    allowed = {to_sim[c] for c in engine_monkey.ALLOWED_COLORS if c in to_sim}
    cells = engine_monkey.plain_cells(board, special, lab["engine_refill"].profile)
    assert cells == [(y, x) for x in range(len(board[0])) for y in range(len(board))
                     if int(special[y][x]) == 0 and int(board[y][x]) in allowed]
    assert cells
    before = lab["engine_refill"].rng.counter
    tries = engine_monkey.draw_candidates(board, special, lab["engine_refill"],
                                          engine_monkey.config_from(lab["engine_refill"].profile), 4)
    assert len(tries) == 5 and all(len(t) == 4 for t in tries)
    assert lab["engine_refill"].rng.counter - before == 5 * len(cells)


@pytest.mark.parametrize("name", ["015", "023"])
def test_activation_is_played_and_rests_on_the_target(name, monkeypatch):
    # The resting count is the target rule, not the game's number: the
    # auto-explode's cascade is still one skull off (docs/monkey_joojoo.md).
    result, after = _activate(name, monkeypatch)
    assert result["supported"], result.get("reason")
    special = [list(map(int, row)) for row in result["state"]["special_board"]]
    config = engine_monkey.config_from(after["profile"])
    before = _load(name)
    assert sum(v == SKULL for row in special for v in row) == engine_monkey.skull_target(
        config, _skulls(before))
    assert abs(sum(v == SKULL for row in special for v in row) - _skulls(after)) <= 1


def test_activation_does_not_spend_the_booster_meter_twice(monkeypatch):
    result, after = _activate("002", monkeypatch)
    assert result["supported"], result.get("reason")
    assert (result["state"]["booster_state"]["current"]
            == after["snapshot_state"]["players"][0]["energy"])


def test_get_slot_prioritize_keeps_the_first_pass_order_and_shuffles_the_rest():
    """BoardModel::GetSlotPrioritize 0x5972158: pass 1 in board order, rest shuffled."""
    capture = capture_from(_load("002"))
    lab = lab_move(capture)
    model = lab["engine_refill"]
    cells = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)]
    model.rng.counter = 0
    drawn = engine_monkey.get_slot_prioritize(cells, model, 3, prioritize=lambda cell: cell[0] == 0 and cell[1] == 1)
    # One prioritized cell that is not enough for 3, so it leads in board order.
    assert drawn[0] == (0, 1) and len(drawn) == 3
    model.rng.counter = 0
    all_drawn = engine_monkey.get_slot_prioritize(cells, model, 3)
    assert len(all_drawn) == 3 and set(all_drawn) <= set(cells)
    # The shuffle costs one draw per cell of the list it draws from.
    assert model.rng.counter == len(cells)
    model.rng.counter = 0
    prioritized = [cell for cell in cells if cell[1] in (0, 1, 2)]
    assert set(engine_monkey.get_slot_prioritize(
        cells, model, 3, prioritize=lambda cell: cell[1] in (0, 1, 2))) == set(prioritized)
    assert model.rng.counter == len(prioritized)


EXACT = ("002", "008", "011", "013", "015", "017", "019", "021", "023", "025")


@pytest.mark.parametrize("name", EXACT)
def test_recorded_activation_is_exact(name):
    from tools import monkey_check
    before = FIXTURES / f"{name}.json"
    after = FIXTURES / f"{int(name) + 1:03d}.json"
    rec_a, cap_a = monkey_check.load(before)
    rec_b, _ = monkey_check.load(after)
    assert monkey_check.exact(monkey_check.compare(rec_a, cap_a, rec_b))
