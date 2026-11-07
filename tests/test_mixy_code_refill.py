"""Mixy Meow in the exact refill (engine_mixy).

Funky Tiles + Mixy, 2026-11-07 20:42 (Debug/research/20261107_204218): the
refill "missed" exactly on the swipes that matched a code colour. Use #2 is now
ported (the repaint of the code's other colours, before the swap resolves) and
replays exactly; use #1 re-deals the code, which is not, and stays uncheckable.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import engine_mixy
import move_strategy as ms
import refill_monitor
from engine_refill import ExactRefillSession

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_204218_funky-tiles-master-league"


def _player(uses, colors=(6, 3), target=1, ability=59):
    return {"player_type": 0, "index": 0, "special_ability_type": ability,
            "special_ability_engine": {"uses_left": uses},
            "special_ability_fields": {"TargetColor": target, "activeColors": list(colors)}}


def _record(uses):
    return {"snapshot_state": {"players": [_player(uses)]}}


def test_live_code_only_while_it_can_trigger():
    to_sim = {6: 1, 3: 2}
    assert engine_mixy.MixyPassive.from_player(_player(2), to_sim) == engine_mixy.MixyPassive(frozenset({1, 2}), 2)
    assert engine_mixy.MixyPassive.from_player(_player(0), to_sim) is None
    assert engine_mixy.MixyPassive.from_player(_player(2, target=6), to_sim) is None
    assert engine_mixy.MixyPassive.from_player(_player(2, ability=63), to_sim) is None


def test_code_match_repaints_the_other_code_colours():
    board = [[1, 1, 3, 2],
             [4, 5, 1, 2],
             [2, 4, 5, 6],
             [5, 6, 4, 2]]
    special = [[0] * 4 for _ in range(4)]
    candidate = ms.MoveCandidate((0, 2), (1, 2), ms.Direction.DOWN, [row[:] for row in board], special)
    swapped = [row[:] for row in board]
    swapped[0][2], swapped[1][2] = swapped[1][2], swapped[0][2]     # row 0: 1 1 1 2
    candidate = ms.MoveCandidate((0, 2), (1, 2), ms.Direction.DOWN, swapped, special)
    for uses, redealt in ((1, False), (2, True)):
        model = NS(mixy=engine_mixy.MixyPassive(frozenset({1, 2}), uses), mixy_redealt=False)
        out = engine_mixy.convert_swap(model, candidate, False)
        assert all(v != 2 for row in out.board for v in row)          # every 2 became 1
        assert model.mixy.uses_left == uses - 1 and model.mixy_redealt is redealt
    # A swipe that matches no code colour changes nothing.
    model = NS(mixy=engine_mixy.MixyPassive(frozenset({5}), 1), mixy_redealt=False)
    assert engine_mixy.convert_swap(model, candidate, False) is candidate


def test_only_the_redealing_use_is_uncheckable():
    assert refill_monitor._mixy_code_spent(_record(2), _record(1))
    assert not refill_monitor._mixy_code_spent(_record(1), _record(0))
    assert not refill_monitor._mixy_code_spent(_record(1), _record(1))


def test_session_breaks_the_line_only_on_a_redeal():
    for redealt in (False, True):
        model = NS(clone=lambda: model, reset_action=lambda: None, random_specials=False, profile={},
                   mixy=None, mixy_redealt=redealt)
        session = ExactRefillSession(model, [[1]])
        session.begin([[1]])
        result = NS(board=[[2]], special_board=None, extra_moves=0, intent_events=(),
                    cleared_color_counts={}, matches=[])
        session.finish(result)
        assert result.exact_refill_supported is (not redealt)


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Mixy recording not present")
@pytest.mark.parametrize("index, ported", [(5, True), (19, True), (24, True), (0, False), (4, False)])
def test_recording_code_matches(index, ported):
    from tools.analyze_research import capture_from, observed, try_transition
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    matches, _closest, reasons = try_transition(capture_from(before), observed(after))
    if ported:
        assert matches
    else:
        assert not matches and any("re-deal" in str(r) for r in reasons)
