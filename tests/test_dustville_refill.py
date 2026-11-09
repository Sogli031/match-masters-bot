"""Dustville Duel in the exact refill: wanted figures, their shots, the replenish."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine_refill
import move_strategy as ms
from engine_refill import EngineRefill
from tests.test_engine_refill import entries, profile

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_083610_dustville-duel-master-league"
EXTRA = {"scoreBonusPerHit": 1, "wantedTilesCount": 3, "wantedShoots": 4, "replenishChance": 1,
         "minBluesToPick": 2, "replenishRate": 3}


def dustville(seed=1234):
    p = profile()
    p["rules"].update(boardModelName=engine_refill.DUSTVILLE_BOARD, _extraData=entries(EXTRA))
    return EngineRefill.from_profile(p, seed=seed)


def sim_board():
    colors = (ms.BLUE, ms.RED, ms.ORANGE, ms.GREEN, ms.PURPLE, ms.YELLOW)
    return [[colors[(x + 2 * y) % 6] for x in range(7)] for y in range(7)]


def test_config_reads_extra_data_over_code_defaults():
    config = dustville().dustville_config()
    assert config["wantedShoots"] == 4 and config["minBluesToPick"] == 2 and config["wantedTilesCount"] == 3
    assert config["chanceToPickBlue"] == 0      # not in extraData: getter default
    assert EngineRefill.from_profile(profile(), seed=1).dustville_config() is None


def test_shots_pick_min_blues_first_then_red_and_skip_destroyed_cells():
    m = dustville()
    board, special = sim_board(), [[0] * 7 for _ in range(7)]
    prevent = {(0, 0), (1, 5)}      # a blue and a red already being destroyed
    shots = m.wanted_shots(board, special, prevent)
    assert len(shots) == len(set(shots)) == 4
    assert not set(shots) & prevent
    assert [board[r][c] for r, c in shots[:2]] == [ms.BLUE, ms.BLUE]
    assert all(board[r][c] in (ms.BLUE, ms.RED) for r, c in shots)


def test_shots_draw_shuffles_colour_list_chances_and_picks():
    m = dustville()
    board, special = sim_board(), [[0] * 7 for _ in range(7)]
    blues = sum(v == ms.BLUE for row in board for v in row)
    reds = sum(v == ms.RED for row in board for v in row)
    before = m.rng.counter
    m.wanted_shots(board, special, set())
    # two shuffles, the unused colour-list shuffle, two Chance rolls, four picks
    assert m.rng.counter - before == blues + reds + 4 + 2 + 4


def test_turn_start_tops_figures_up_on_plain_orange():
    m = dustville()
    board, special = sim_board(), [[0] * 7 for _ in range(7)]
    orange = [(r, c) for r in range(7) for c in range(7) if board[r][c] == ms.ORANGE]
    special[orange[0][0]][orange[0][1]] = ms.SPECIAL_MODE_TARGET
    before = m.rng.counter
    after = m.wanted_turn_start(board, special)
    wanted = [(r, c) for r in range(7) for c in range(7) if after[r][c] == ms.SPECIAL_MODE_TARGET]
    assert len(wanted) == 3 and all(board[r][c] == ms.ORANGE for r, c in wanted)
    assert m.rng.counter - before == 1 + len(orange) - 1     # Chance, then shuffle of the candidates
    assert m.wanted_turn_start(board, after) == after         # full: no draw
    assert m.rng.counter - before == len(orange)


def test_disco_on_orange_fires_no_shots_for_its_own_partner():
    board = [[ms.GREEN if (r + c) % 2 else ms.YELLOW for c in range(7)] for r in range(7)]
    special = [[0] * 7 for _ in range(7)]
    board[3][3], special[3][3] = 99, ms.SPECIAL_DISCO_BALL
    board[3][4], special[3][4] = ms.ORANGE, ms.SPECIAL_MODE_TARGET
    calls = []
    with ms.engine_refill_active(lambda b, s, c=0: (b, s), wanted_shots=lambda *a: calls.append(a) or []):
        ms._simulate_disco_candidate(ms.MoveCandidate((3, 3), (3, 4), ms.Direction.RIGHT, board, special),
                                     mode=ms.GameMode.DUSTVILLE_DUEL)
    assert calls == []


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Dustville recording not present")
@pytest.mark.parametrize("index", [3, 10, 18, 26, 30])
def test_recorded_dustville_move_matches_the_game(index):
    """003: matched figure; 010/018: disco on orange; 026/030: three volleys."""
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation
    before, after = (json.loads((RECORDING / f"{i:03d}.json").read_text(encoding="utf-8"))
                     for i in (index, index + 1))
    modes = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(modes) | {capture_mode(before["profile"]).value}
    try:
        assert check_transition(before, after)["verdict"] == "ok"
    finally:
        simulation.PREFIX_MODES = modes


LIVE_MISS = Path(__file__).resolve().parents[1] / "Debug/refill_misses/20261107_090851_137327_dustville-duel-master-league"


@pytest.mark.skipif(not LIVE_MISS.is_dir(), reason="Dustville live miss not present")
def test_figure_matched_in_a_cascade_is_uncheckable_not_a_miss():
    """Live 09:08:51: the volley fired in cascade 2 and the RNG ended 43 short."""
    from refill_monitor import check_transition
    before, after = (json.loads((LIVE_MISS / n).read_text(encoding="utf-8")) for n in ("000.json", "001.json"))
    assert check_transition(before, after)["verdict"] == "unsupported"


def test_cascade_volley_breaks_the_exact_line():
    from strategy_lab.simulation import _dustville_cascade_unported
    assert _dustville_cascade_unported({"type": "dustville_wanted_shots", "cascade": 2})
    assert not _dustville_cascade_unported({"type": "dustville_wanted_shots", "cascade": 1})


def test_exact_wanted_shots_are_not_counted_twice_as_charge():
    # The two blue shot cells are already in blue_cells after exact simulation.
    evaluation = SimpleNamespace(
        blue_cells=2.0, mode_targets=1.0, cleo_scenario_count=0,
        intent_events=[{"type": "dustville_wanted_shots", "cascade": 1,
                        "cells": [(0, 0), (0, 1)]}],
        candidate=SimpleNamespace(board=sim_board()),
    )
    assert ms._booster_charge_cells_for_mode(evaluation, ms.GameMode.DUSTVILLE_DUEL) == 2.0


KEPT_TURN_MISSES = [Path(__file__).resolve().parents[1] / "Debug/refill_misses" / name for name in (
    "20261107_225834_285082_dustville-duel",      # moves 1->1 (a four's extra move)
    "20261107_230829_161503_dustville-duel",      # moves 2->2
    "20261107_231130_615342_dustville-duel")]     # moves 2->1


@pytest.mark.parametrize("folder", KEPT_TURN_MISSES, ids=lambda p: p.name[:15])
def test_wanted_figures_are_topped_up_only_when_the_turn_passes(folder):
    """The game kept 2 figures; topping up after every move added 2-4 and 6-8 draws."""
    if not folder.is_dir():
        pytest.skip("Dustville live miss not present")
    from refill_monitor import check_transition
    before, after = (json.loads((folder / n).read_text(encoding="utf-8")) for n in ("000.json", "001.json"))
    assert check_transition(before, after)["verdict"] == "ok"
