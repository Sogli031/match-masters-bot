"""Regression boards from the Froggy Fu match on 2026-10-16 at 02:04."""
from dataclasses import replace
import json
from pathlib import Path

import pytest
import move_strategy as ms
from tools.rebuild_evaluation import build_states


FRAMES = json.loads((Path(__file__).parent / "fixtures/dustville_wanted.json").read_text())


def rank_frame(index):
    frame = FRAMES[index]
    states = build_states(frame)
    with ms.froggy_gather_region_active(7, True):
        candidates = ms.rank_moves(frame["board"], frame["special_board"],
            mode=states["mode"], score_rally_values=states["score_rally_values"],
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            strategy_context=states["strategy_context"])
        ranked = ms.prioritize_ranked_moves(candidates,
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"], **states)
    return ranked, states


@pytest.mark.parametrize("index", range(5))
def test_recorded_board_collects_two_wanted_tiles(index):
    ranked, states = rank_frame(index)
    assert ranked[0].mode_targets == 2
    assert ms._dustville_wanted_charge(ranked[0], states["mode"]) == 4


def test_known_extra_still_precedes_wanted_collection():
    ranked, _ = rank_frame(5)
    assert ms.has_reliable_same_move_extra(ranked[0])


def test_charge_floor_excludes_already_cleared_and_missing_blues():
    ranked, states = rank_frame(0)
    item = ranked[0]
    count = sum(c == ms.BLUE for row in item.candidate.board for c in row)
    item = replace(item, blue_cells=count - 1)
    assert ms._dustville_wanted_charge(item, states["mode"]) == 1
    assert ms._dustville_wanted_charge(replace(item, blue_cells=count), states["mode"]) == 0
    assert ms._dustville_wanted_charge(item, ms.GameMode.NONE) == 0
    uncertain = replace(item, intent_events=[dict(type="uncertain_refill_boundary", after_cascade=0)])
    assert ms._dustville_wanted_charge(uncertain, states["mode"]) == 0


def test_old_residual_cannot_penalize_wanted_shots(monkeypatch):
    ranked, states = rank_frame(0)
    monkeypatch.setattr(ms, "_LEARNED_RANK_DEPTH", 1)
    monkeypatch.setattr(ms.learned_value.model(), "enabled", True)
    def invalid_model(*args, **kwargs):
        raise AssertionError("old residual lacks Dustville shot outcomes")
    monkeypatch.setattr(ms.learned_value, "residual_adjustment", invalid_model)
    assert ms._learned_residual(ranked[0], "solo_6", states["booster_state"],
        states["turn_state"], states["strategy_context"], "early", states["mode"]) == 0
