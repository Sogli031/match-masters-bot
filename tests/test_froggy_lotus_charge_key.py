"""Solo Challenge lotus: most useful charge first, then the certain part, then points.

Four recorded Froggy Fu boards (Debug/runs, 2026-11-06/07). In every one the bot
of that day played the move asserted here and the meter got what is noted:
* 14:54:51 (11-06) and 06:35:41: two collects of the same colour, one predicted
  to fill the meter (7) and one not (6 / 5). A 0.5 discount on capped random
  charge ranked the full one lower; the full one charged 7 for real both times.
* 13:41:11 (11-06) and 04:35:55: equal predicted charge (3); one collect gathers
  its blue itself, the other only through random cascades. Certain wins over
  points (the played certain collect charged 5 and 7).
"""
import json
from pathlib import Path

import pytest

import move_strategy as ms
from tools.rebuild_evaluation import build_states

FRAMES = json.loads((Path(__file__).parent / "fixtures/froggy_lotus_charge_key.json").read_text())


def _top_lotus(run):
    frame = FRAMES[run]
    states = build_states(frame)
    with ms.froggy_gather_region_active(7, True), ms.all_specials_lightning_active(
            bool(frame.get("all_specials_lightning"))):
        ranked = ms.rank_moves(
            frame["board"], frame["special_board"], mode=states["mode"],
            score_rally_values=states["score_rally_values"],
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            strategy_context=states["strategy_context"], include_future_value=True)
        lotus = ms.rank_froggy_lotus_moves(
            ranked, frame["board"], frame["special_board"], mode=states["mode"],
            score_rally_values=states["score_rally_values"],
            booster_state=states["booster_state"], turn_state=states["turn_state"],
            strategy_context=states["strategy_context"],
            specials_auto_explode=frame["specials_explode_immediately"])
    return lotus[0], states


def _cells(evaluation):
    return {tuple(evaluation.candidate.start), tuple(evaluation.candidate.target)}


def _charge(evaluation, states):
    return ms._useful_total_charge_cells(
        evaluation, states["booster_state"], states["mode"], states["score_rally_values"],
        states["strategy_context"], states["turn_state"])


@pytest.mark.parametrize("run", ["2026-11-06_14-54-51_979", "2026-11-07_06-35-41_348"])
def test_collect_that_fills_the_meter_beats_a_smaller_one(run):
    top, states = _top_lotus(run)
    played = FRAMES[run]["best_move"]
    assert _cells(top) == {tuple(played["start"]), tuple(played["target"])}
    assert _charge(top, states) == pytest.approx(7.0)


@pytest.mark.parametrize("run", ["2026-11-06_13-41-11_338", "2026-11-07_04-35-55_799"])
def test_equal_charge_goes_to_the_certain_blue(run):
    top, states = _top_lotus(run)
    played = FRAMES[run]["best_move"]
    assert _cells(top) == {tuple(played["start"]), tuple(played["target"])}
    assert ms._lotus_certain_charge(top, _charge(top, states)) == pytest.approx(3.0)


def test_certain_part_never_exceeds_the_useful_charge():
    top, states = _top_lotus("2026-11-07_04-35-55_799")
    assert ms._lotus_certain_charge(top, 0.0) == 0.0
    assert ms._lotus_certain_charge(top, 1.0) == 1.0
