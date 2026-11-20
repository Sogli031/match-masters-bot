"""El Magneto / SE: MakeColorSwaps geometry and Use's draws against the recordings."""
from pathlib import Path

import pytest

import engine_magneto as em
from engine_refill import color_maps
from simulator_capture import lab_move
from tools.analyze_research import grid, load
from tools.magneto_check import _activation, captured_path

FIXTURES = Path(__file__).parent / "fixtures"


def _pairs():
    for folder in sorted(FIXTURES.glob("el_magneto*/*")):
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        for a, b in zip(files, files[1:]):
            rec_a, cap_a = load(a)
            rec_b, _ = load(b)
            if not _activation(a, b, rec_a, rec_b):
                yield pytest.param(cap_a, rec_b, id=f"{folder.parent.name}-{a.stem}")


def _final_positions(swaps):
    where = {}
    for x, y in swaps:
        u, v = where.pop(x, x), where.pop(y, y)
        where[y], where[x] = u, v
    return {(origin, pos) for pos, origin in where.items() if origin != pos}


@pytest.mark.parametrize("cap_a, rec_b", list(_pairs()))
def test_last_magnet_swaps_match_recorded_source_to_target_pairs(cap_a, rec_b):
    lab = lab_move(cap_a)
    path = captured_path(rec_b)
    sim_to_engine, _ = color_maps(cap_a["profile"])
    board = [list(map(int, r)) for r in grid(lab["board"])]
    special = [list(map(int, r)) for r in grid(lab["special_board"])]
    magnitied = set()
    for magnet, color in path:
        swaps = em.make_color_swaps(board, special, magnet, color, magnitied, sim_to_engine)
    data = rec_b["profile"]["ability_detail"]["fields"]["<currentConvertData>k__BackingField"]
    recorded = {((s["x"], s["y"]), (t["x"], t["y"]))
                for s, t in data["<sourceToTargetPairs>k__BackingField"] if s != t}
    assert _final_positions(swaps) == recorded


@pytest.mark.parametrize("cap_a, rec_b", list(_pairs()))
def test_draws_give_the_recorded_magnets_and_a_candidate_with_its_colours(cap_a, rec_b):
    lab = lab_move(cap_a)
    model = lab["engine_refill"].clone()
    model.profile = dict(model.profile, ability_detail=rec_b["profile"]["ability_detail"])
    magnets, combos, _ = em.candidates(grid(lab["board"]), grid(lab["special_board"]), model)
    path = captured_path(rec_b)
    assert magnets == [m for m, _ in path]
    assert [c for _, c in path] in combos
