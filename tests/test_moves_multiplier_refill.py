"""Exact refill with specialsAutoExplode, from recorded moves-multiplier games."""
import json
from pathlib import Path

import pytest

from engine_refill import EngineRefill, ExactRefillSession
import move_strategy as ms
import refill_monitor
from simulator_capture import capture_mode
from strategy_lab import simulation

ROOT = Path(__file__).resolve().parents[1] / "Debug" / "research"
# (game, transition): plain swipes, and swipes with a Cleo on the board or crossed.
EXACT = [
    ("20261104_041047_moves-multiplier", 0),   # four, then the column: 21 + 49 draws
    ("20261104_041047_moves-multiplier", 1),   # plain three, nothing explodes
    ("20261104_041047_moves-multiplier", 3),   # Cleo on the board
    ("20261104_041047_moves-multiplier", 7),   # a line crosses a Cleo: 3 + 6 holes
    ("20261104_043737_moves-multiplier", 1),   # a longer chain of explosions
    ("20261104_044447_moves-multiplier", 1),
]


@pytest.mark.parametrize("game,index", EXACT)
def test_recorded_swipe_is_exact(game, index, monkeypatch):
    files = sorted((ROOT / game).glob("[0-9][0-9][0-9].json"))
    if len(files) <= index + 1:
        pytest.skip("recording not available")
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(before["profile"]).value})
    verdict = refill_monitor.check_transition(before, after)
    assert verdict["verdict"] == "ok", verdict


@pytest.mark.parametrize("index", [4, 7, 12, 13, 18])
def test_disco_swipe_whose_cascade_makes_a_special_is_exact(index, monkeypatch):
    # Debug/research/20261104_050645: Brocco balls. 18 has no such cascade; the
    # others were wrong while this path still fired the special at once.
    files = sorted((ROOT / "20261104_050645_moves-multiplier").glob("[0-9][0-9][0-9].json"))
    if len(files) <= index + 1:
        pytest.skip("recording not available")
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(before["profile"]).value})
    verdict = refill_monitor.check_transition(before, after)
    assert verdict["verdict"] == "ok", verdict


@pytest.mark.parametrize("index", [4, 5, 7, 12, 13, 17])
def test_recorded_lotus_swipe_is_exact(index, monkeypatch):
    # Debug/research/20261104_052333: Froggy Fu. In all but 7 and 12 the pull also
    # forms other matches, which go with the cluster, in the first layer.
    files = sorted((ROOT / "20261104_052333_moves-multiplier").glob("[0-9][0-9][0-9].json"))
    if len(files) <= index + 1:
        pytest.skip("recording not available")
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(before["profile"]).value})
    verdict = refill_monitor.check_transition(before, after)
    assert verdict["verdict"] == "ok", verdict


@pytest.mark.parametrize("index", [3, 6, 7, 15, 16, 18, 19])
def test_recorded_lotus_swipe_of_the_second_froggy_game_is_exact(index, monkeypatch):
    # Debug/research/20261104_054022: Froggy Fu. In 6 the swipe also makes a three
    # that touches no lotus, so it gets its own pull as assignedSecondary.
    files = sorted((ROOT / "20261104_054022_moves-multiplier").glob("[0-9][0-9][0-9].json"))
    if len(files) <= index + 1:
        pytest.skip("recording not available")
    before, after = (json.loads(files[i].read_text(encoding="utf-8")) for i in (index, index + 1))
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {capture_mode(before["profile"]).value})
    verdict = refill_monitor.check_transition(before, after)
    assert verdict["verdict"] == "ok", verdict


def _rank_lotus_moves(record, session):
    board = [[int(v) for v in row] for row in record["board"]]
    special = [[int(v) for v in row] for row in record["special_board"]]
    mode = capture_mode(record["profile"]).value
    me = next(p for p in record["snapshot_state"]["players"] if p.get("player_type") == 0)
    gather = ms.froggy_gather_config_from_params(me.get("special_ability_params"))
    with ms.exact_refill_active(session), ms.froggy_gather_region_active(*gather):
        ranked = ms.rank_moves(board, special, mode=mode, explode_created_specials_immediately=True)
        return ms.rank_froggy_lotus_moves(ranked, board, special, mode=mode)


def test_lotus_moves_use_visible_pieces_without_refill_and_the_drop_with_it():
    # Debug/research/20261104_054022, snapshot 6: the swipe that also makes a three.
    path = ROOT / "20261104_054022_moves-multiplier" / "006.json"
    if not path.exists():
        pytest.skip("recording not available")
    record = json.loads(path.read_text(encoding="utf-8"))
    swipe = {(3, 5), (3, 6)}
    pick = lambda moves: next(m for m in moves if {m.candidate.start, m.candidate.target} == swipe)
    boundary = lambda move: any(e.get("type") == "uncertain_refill_boundary" for e in move.intent_events)
    gathered = lambda move: [(tuple(e["lotus"]), e["color"], e["collected"]) for e in move.intent_events
                             if e.get("type") == ms.FROGGY_LOTUS_GATHER_EVENT]

    visible = pick(_rank_lotus_moves(record, None))
    session = ExactRefillSession(EngineRefill.from_profile(record["profile"]), record["board"],
                                 special_board=record["special_board"])
    with_drop = pick(_rank_lotus_moves(record, session))

    assert gathered(visible) == gathered(with_drop) == [((4, 4), 6, 9)]
    # The second match of the swipe goes in the first layer either way.
    assert {3, 6} <= {m.color for m in visible.cascade_matches[0]}
    assert {3, 6} <= {m.color for m in with_drop.cascade_matches[0]}
    assert boundary(visible) and not boundary(with_drop)
    assert session.successful
    assert with_drop.cleared_cells > visible.cleared_cells


def test_blow_em_up_mode_alone_turns_the_rule_on():
    special = [[ms.SPECIAL_BOMB, 0], [0, 0]]
    assert ms._classic_specials(special, False, ms.GameMode.BLOW_EM_UP.value) == {(0, 0)}
    assert ms._classic_specials(special, True, "None") == {(0, 0)}
    assert ms._classic_specials(special, False, "None") is None


def test_every_cascade_loop_uses_the_deferred_explosion():
    import inspect
    assert "explode_created_specials_immediately" not in inspect.signature(
        ms._clear_matches_with_details).parameters
    for function in (ms.simulate_candidate, ms._simulate_disco_candidate, ms._simulate_special_swap_candidate):
        source = inspect.getsource(function)
        assert "_with_auto_explosions" in source and "_tag_auto_explosions" in source


def _four_in_column():
    # Swiping (3, 0) right makes a vertical four of 2s in column 0.
    board = [[(r + 2 * c) % 4 + 3 for c in range(5)] for r in range(5)]
    for r in (1, 2, 4):
        board[r][0] = 2
    board[3][1] = 2
    board[3][0] = 1
    special = [[0] * 5 for _ in range(5)]
    swapped_board, swapped_special = ms.swap_cells(board, special, (3, 1), (3, 0))
    return ms.MoveCandidate((3, 1), (3, 0), ms.Direction.LEFT, swapped_board, swapped_special)


def _resolve(candidate, explode):
    refills = []

    def refill(board, special, chain):
        refills.append((sum(int(v) == ms.EMPTY for row in board for v in row), chain))
        # Alternating colours the rest of the board lacks: the refill matches nothing.
        filled = [[(1 if y % 2 else 2) if int(v) == ms.EMPTY else int(v) for v in row]
                  for y, row in enumerate(board)]
        return filled, [list(map(int, row)) for row in special]

    with ms.engine_refill_active(refill):
        result = ms.simulate_candidate(candidate, explode_created_specials_immediately=explode)
    return result, refills


def test_created_special_fires_after_the_refill_not_before():
    candidate = _four_in_column()
    result, refills = _resolve(candidate, True)
    assert refills[0] == (3, 0)              # the four leaves its special behind
    assert refills[1][0] == 5                # then the whole column, a layer later
    assert not any(v for row in result.special_board for v in row)


def test_auto_explosion_draws_no_chain_combo():
    _, refills = _resolve(_four_in_column(), True)
    assert refills[1][1] == 0


def test_without_the_rule_the_special_stays():
    result, refills = _resolve(_four_in_column(), False)
    assert len(refills) == 1
    assert any(v for row in result.special_board for v in row)


def test_a_blast_leaves_a_cleo_standing():
    board = [[1, 2, 3], [99, 4, 5], [6, 2, 3]]
    special = [[0, 0, 0], [ms.SPECIAL_CLEO_BUG, 0, 0], [ms.SPECIAL_VERTICAL, 0, 0]]
    cleared, _ = ms._resolve_special_chain(board, special, {(2, 0)})
    assert (0, 0) in cleared
    assert (1, 0) not in cleared
