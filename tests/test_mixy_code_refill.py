"""Mixy Meow: a swap matching a code colour repaints 7 random pieces (not ported).

Funky Tiles + Mixy, 2026-11-07 20:42 (Debug/research/20261107_204218): 16 of
17 refill "misses" were exactly the moves where UsesLeft dropped.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import refill_monitor
import square_solo_live
from engine_refill import ExactRefillSession

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_204218_funky-tiles-master-league"


def _record(uses, colors=(6, 3)):
    me = {"player_type": 0, "index": 0, "special_ability_type": 59,
          "special_ability_engine": {"uses_left": uses},
          "special_ability_fields": {"<Phase>k__BackingField": 1, "activeColors": list(colors)}}
    return {"snapshot_state": {"players": [me]}}


def test_a_spent_code_use_is_uncheckable_not_a_miss():
    assert refill_monitor._mixy_code_spent(_record(2), _record(1))
    assert not refill_monitor._mixy_code_spent(_record(1), _record(1))
    assert not refill_monitor._mixy_code_spent({"snapshot_state": {"players": []}}, _record(1))


def test_session_breaks_the_line_on_a_code_colour_match():
    model = NS(clone=lambda: model, reset_action=lambda: None, random_specials=False, profile={})
    session = ExactRefillSession(model, [[1]])
    session.mixy_code = frozenset({4})
    for color, broken in ((2, False), (4, True)):
        session.begin([[1]])
        result = NS(board=[[color]], special_board=None, extra_moves=0, intent_events=(),
                    cleared_color_counts={}, matches=[NS(color=color)])
        session.finish(result)
        assert result.exact_refill_supported is (not broken)


def test_live_code_is_read_only_while_it_can_trigger(monkeypatch):
    import engine_refill
    monkeypatch.setattr(engine_refill, "color_maps", lambda profile: ({}, {6: 1, 3: 2}))
    state = lambda uses, phase=1: {"players": [{
        "player_type": 0, "special_ability_type": 59, "special_ability_engine": {"uses_left": uses},
        "special_ability_fields": {"<Phase>k__BackingField": phase, "activeColors": [6, 3]}}]}
    assert square_solo_live._mixy_sim_code(state(2), {}) == {1, 2}
    assert square_solo_live._mixy_sim_code(state(0), {}) == frozenset()
    assert square_solo_live._mixy_sim_code(state(2, phase=0), {}) == frozenset()


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Mixy recording not present")
def test_recording_has_no_mixy_misses_left():
    from refill_monitor import check_transition
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))[:7]
    records = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    verdicts = [check_transition(a, b) for a, b in zip(records, records[1:])]
    assert all(v is None or v["verdict"] != "miss" for v in verdicts)
    assert sum(1 for v in verdicts if v and "Mixy" in v["detail"]) >= 3
