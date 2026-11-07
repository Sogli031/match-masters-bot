"""Solo Challenge Cleo: near-equal extra chances tie, then charge, then points.

Recorded boards (Debug/runs, 2026-11-06/07) with a Cleo swap at 0.8316 that
charges 7 next to one at 0.84 that charges (almost) nothing. The 1% edge used
to decide alone. Played at 0.8316 the bot charged 7 on 21:48:05 and 05:47:07;
on 10:02:06 it took the 0.84 swap and charged 0. On 21:48:47 both fill the
meter, so points decide (161 over 87), which is what the bot played then.
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms
from tools.rebuild_evaluation import build_states

FRAMES = json.loads((Path(__file__).parent / "fixtures/cleo_charge_tier.json").read_text())


def _ranked(run):
    frame = FRAMES[run]
    states = build_states(frame)
    with ms.all_specials_lightning_active(bool(frame.get("all_specials_lightning"))):
        ranked = ms.rank_moves(
            frame["board"], frame["special_board"], mode=states["mode"],
            score_rally_values=states["score_rally_values"],
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            strategy_context=states["strategy_context"], include_future_value=True)
        return ms.prioritize_ranked_moves(
            ranked, allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            **states), states


def _cells(evaluation):
    return {tuple(evaluation.candidate.start), tuple(evaluation.candidate.target)}


def _played(run):
    move = FRAMES[run]["best_move"]
    return {tuple(move["start"]), tuple(move["target"])}


def _charge(evaluation, states):
    return ms._useful_total_charge_cells(
        evaluation, states["booster_state"], states["mode"], states["score_rally_values"],
        states["strategy_context"], states["turn_state"])


@pytest.mark.parametrize("run", [
    "2026-11-06_21-48-05_633", "2026-11-07_05-47-07_065", "2026-11-06_21-48-47_358"])
def test_cleo_swap_that_fills_the_meter_is_played(run):
    ranked, states = _ranked(run)
    assert ranked[0].decision_gate == ms.CLEO_DECISION_GATE
    assert _cells(ranked[0]) == _played(run)
    assert _charge(ranked[0], states) >= 6.0


def test_one_percent_chance_edge_does_not_beat_a_full_meter():
    ranked, states = _ranked("2026-11-07_10-02-06_162")
    top = ranked[0]
    assert top.decision_gate == ms.CLEO_DECISION_GATE
    assert _charge(top, states) >= 6.0
    # The 0.84 swap the bot played that day charged nothing.
    assert _cells(top) != _played("2026-11-07_10-02-06_162")
