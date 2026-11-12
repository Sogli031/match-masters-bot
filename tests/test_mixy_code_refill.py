"""Mixy Meow in the exact refill (engine_mixy).

Funky Tiles + Mixy, 2026-11-07 20:42 (Debug/research/20261107_204218): the
refill "missed" exactly on the swipes that matched a code colour. Use #2 is
ported (the repaint of the code's other colours, before the swap resolves).
Use #1 re-deals the code (RandomizeActiveColors, engine_mixy.redeal), ported
2026-11-12 from the Multiplier Madness recording: board, whole RNG and the new
code's colours.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

import engine_mixy
import move_strategy as ms
import refill_monitor
from engine_refill import ExactRefillSession, color_maps
from engine_rng import EngineRNG

RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_204218_funky-tiles-master-league"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def test_only_use_one_redeals():
    assert refill_monitor._mixy_code_spent(_record(2), _record(1))
    assert not refill_monitor._mixy_code_spent(_record(1), _record(0))
    assert not refill_monitor._mixy_code_spent(_record(1), _record(1))


def _pair(folder):
    return [json.loads((folder / f"{index:03}.json").read_text(encoding="utf-8")) for index in range(2)]


@pytest.mark.parametrize("capture", ["012932_497455", "013016_057464"])
def test_bullseye_redeal_is_exact(capture):
    """Bullseye Bash (colour score override): the max-score colour branch."""
    folder = (RECORDING.parent.parent / "refill_unsupported" / "mixy_redeal"
              / f"20261110_{capture}_bullseye-bash")
    if not folder.is_dir():
        pytest.skip("Bullseye Mixy re-deal recording not present")
    result = refill_monitor.check_transition(*_pair(folder))
    assert result["verdict"] == "ok" and "novi kod tacni" in result["detail"]


def test_multiplier_madness_redeal_checks_board_rng_and_code():
    before, after = _pair(FIXTURES / "mixy_redeal_multiplier_madness")
    result = refill_monitor.check_transition(before, after)
    assert result["verdict"] == "ok" and "novi kod tacni" in result["detail"]
    # The colours change no draw count: a wrong code must still fail.
    me = next(p for p in after["snapshot_state"]["players"] if p.get("player_type") == 0)
    me["special_ability_fields"]["activeColors"] = [7, 4, 5]
    assert refill_monitor.check_transition(before, after)["verdict"] == "miss"
    me["special_ability_fields"]["activeColors"] = [7, 4, 3]
    after["profile"]["rng"]["_matrix"][0] ^= 1
    assert refill_monitor.check_transition(before, after)["verdict"] == "miss"


def test_redeal_matches_the_engine_trace():
    """RandomizeActiveColors as traced in the game (20261112_020924): ten
    draws, code [3, 6, 5] -> [7, 5, 4] on that board."""
    data = json.loads((FIXTURES / "mixy_redeal_trace_multiplier_madness.json").read_text(encoding="utf-8"))
    profile, trace = data["profile"], data["mixy_redeal_trace"][0]
    before, after = trace["before_redeal"], trace["after_redeal"]
    _, to_sim = color_maps(profile)
    fields = dict(data["player"]["special_ability_fields"], activeColors=before["active_colors"])
    player = dict(data["player"], special_ability_fields=dict(fields, TargetColor=1),
                  special_ability_engine={"uses_left": 2})
    mixy = engine_mixy.MixyPassive.from_player(player, to_sim, profile)
    assert mixy.config is not None
    model = NS(profile=profile, rng=EngineRNG.from_seed(profile["rng"]["_seed"], before["rng_counter"]),
               mixy=engine_mixy.MixyPassive(mixy.code, 1, mixy.config, 1, redeal_pending=True),
               mixy_redealt=False)
    board = [[to_sim[cell[0]] for cell in row] for row in before["grid"]]
    engine_mixy.finish_swipe(model, board)
    assert model.rng.counter == after["rng_counter"]
    assert model.mixy.code == frozenset(to_sim[c] for c in after["active_colors"])
    assert model.mixy.uses_left == 1 and not model.mixy.redeal_pending


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
@pytest.mark.parametrize("index, ported", [(5, True), (19, True), (24, True)])
def test_recording_code_matches(index, ported):
    from tools.analyze_research import capture_from, observed, try_transition
    files = sorted(RECORDING.glob("[0-9][0-9][0-9].json"))
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    matches, _closest, reasons = try_transition(capture_from(before), observed(after))
    if ported:
        assert matches
    else:
        assert not matches and any("re-deal" in str(r) for r in reasons)
