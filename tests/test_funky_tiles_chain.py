"""Funky Tiles master league (recorded 2026-11-07 18:07-18:12).

Three rules read from FunkyTilesBoard and the recording:
* a funky marker fires its plus-2 blast whenever the move destroys its cell
  (BeforeCombosDestroy reads cellsUsedThisMove), not only under a match;
* a fired marker is moved at the next move start (onMoveStart 0x598ff2c,
  GetSlotPrioritize: interior cells, x-major, shuffled, one draw each);
* a two-stage zapper loses one hit point per destroy pass, so two blasts of
  the same pass leave it at one instead of setting it off;
* a zapper the refill spawns takes one more draw of its own.
On the recording: 12 -> 24 of 25 checkable moves exact (the 25th is a perk).
008 and 031 need the first two rules, 027 the third, 004 the fourth, and 002
needs them all.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

PAIRS = json.loads((ROOT / "tests/fixtures/funky_tiles_chain.json").read_text(encoding="utf-8"))


def _verdict(monkeypatch, name):
    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    pair = PAIRS[name]
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(pair["before"]["profile"]).value})
    return (check_transition(pair["before"], pair["after"]) or {}).get("verdict")


@pytest.mark.parametrize("name", ["002", "004", "008", "027", "031"])
def test_recorded_funky_moves_are_exact(monkeypatch, name):
    assert _verdict(monkeypatch, name) == "ok"


@pytest.mark.parametrize("name, switch", [("008", "FUNKY_FIRES_ON_ANY_CLEAR"),
                                          ("027", "ZAPPER_ONE_HIT_PER_PASS")])
def test_each_rule_is_needed(monkeypatch, name, switch):
    monkeypatch.setattr(ms, switch, False)
    assert _verdict(monkeypatch, name) != "ok"


def _strict(monkeypatch, name):
    """Board, specials and the RNG counter all equal (analyze_research)."""
    from tools.analyze_research import capture_from, observed, try_transition

    pair = PAIRS[name]
    _verdict(monkeypatch, name)  # certifies the mode prefix
    matches, _, _ = try_transition(capture_from(pair["before"]), observed(pair["after"]))
    return bool(matches)


def test_spawned_zapper_takes_a_draw(monkeypatch):
    import engine_refill

    assert _strict(monkeypatch, "004")
    monkeypatch.setattr(engine_refill, "ZANY_ZAPPER", -1)
    assert not _strict(monkeypatch, "004")


def test_followed_board_stops_after_a_funky_fire():
    from types import SimpleNamespace
    from engine_refill import ExactRefillSession

    session = ExactRefillSession.__new__(ExactRefillSession)
    session.__dict__.update(line_broken=False, follow_moves=True, ply=0, max_plies=4, hot=None,
                            states={}, followed=0, fallbacks=0, successful=0, failure=None,
                            current=SimpleNamespace(random_specials=(), profile={"rules": {}}, billie=None))
    result = SimpleNamespace(intent_events=[{"type": "funky_tile_activation", "cell": [1, 1]}],
                             board=[[1]], special_board=[[0]], cleared_color_counts={})
    session.finish(result)
    assert result.exact_refill_supported and session.followed == 0
