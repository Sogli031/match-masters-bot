"""Points-first lotus still sees the booster activation a full meter buys.

Crazy Columns 2026-11-12 00:16:40 (Debug/runs): meter 0/7, 5 moves left. The
orange collect (more points now) beat the blue one that fills the meter; the
meter got 3 and the last five moves were plain threes.
"""
import json
from dataclasses import replace
from pathlib import Path

import move_strategy as ms

FIXTURE = Path(__file__).parent / "fixtures" / "froggy_lotus_fill_crazy_columns.json"


def _first(booster=None, **turn):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    context = ms.StrategyContext(**{k: v for k, v in data["strategy_context"].items()
                                    if k in ms.StrategyContext.__dataclass_fields__})
    booster_state = booster or ms.BoosterState(**data["booster_state"])
    turn_data = {k: v for k, v in data["turn_state"].items() if k in ms.TurnState.__dataclass_fields__}
    turn_state = replace(ms.TurnState(**turn_data), **turn)
    ranked = ms.rank_moves(data["board"], data["special_board"], mode=data["mode"],
                           allow_square_matches=data["allow_square_matches"], lookahead_depth=1,
                           strategy_context=context)
    lotus = ms.rank_froggy_lotus_moves(ranked, data["board"], data["special_board"], mode=data["mode"],
                                       booster_state=booster_state, turn_state=turn_state,
                                       strategy_context=context)
    return lotus[0].candidate.start, lotus[0].candidate.target


ORANGE = ((4, 1), (4, 2))
BLUE = ((1, 0), (1, 1))


def test_blue_collect_that_fills_the_meter_wins_with_moves_left():
    assert _first() == BLUE


def test_points_decide_when_the_booster_cannot_be_used_before_the_end():
    assert _first(time_left_seconds=10.0) == ORANGE
    assert _first(remaining_moves=0) == ORANGE


def test_points_decide_when_the_collect_does_not_fill_the_meter():
    assert _first(ms.BoosterState(current=0, maximum=20, source="memory")) == ORANGE
    # A full meter takes no charge at all.
    assert _first(ms.BoosterState(current=7, maximum=7, source="memory")) == ORANGE
