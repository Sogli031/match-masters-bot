"""Perks vs the exact refill: held while the known drop fills the booster soon."""
from types import SimpleNamespace as NS

import move_strategy as ms


def _context(fill_moves, moves_left, current=3, maximum=7):
    return ms.PerkDecisionContext(
        booster=ms.BoosterState(current=current, maximum=maximum),
        turn=ms.TurnState(remaining_moves=moves_left),
        blue_plan=ms.BluePlan(exact_best_within_three=5.0, exact_fill_moves=fill_moves))


def _rank(context):
    diagnostics = {}
    actions = ms.rank_perk_actions([[1, 2, 3]] * 3, [[0, 0, 0]] * 3, [ms.PERK_ENERGY_BOOST],
                                   normal_baseline=None, decision_context=context, diagnostics=diagnostics)
    return actions, diagnostics


def test_held_while_the_drop_fills_the_booster_within_three_moves():
    actions, diagnostics = _rank(_context(fill_moves=2, moves_left=6))
    assert actions == [] and "exact_refill_fills_booster_in_2" in diagnostics.get(ms.PERK_ENERGY_BOOST, "")


def test_not_held_when_the_fill_comes_too_late_or_never():
    for context in (_context(fill_moves=2, moves_left=2), _context(fill_moves=None, moves_left=6)):
        _actions, diagnostics = _rank(context)
        assert "exact_refill_fills_booster" not in str(diagnostics)


def test_three_move_plan_needs_the_exact_refill(monkeypatch):
    monkeypatch.setattr(ms, "_EXACT_REFILL", None)
    assert ms._exact_blue_within_three([[1]], [[0]], ms.BoosterState(current=1, maximum=7), mode="None",
                                       allow_square_matches=False, score_rally_values=None,
                                       explode_created_specials_immediately=False) == (None, None)


def test_three_move_plan_counts_only_known_lines(monkeypatch):
    # board name -> moves (blue, next board, exact)
    tree = {"a": [(2, "b", True), (5, "x", False)], "b": [(2, "c", True)], "c": [(3, "d", True)]}
    session = NS(knows=lambda b: True, use_special_keys=False)
    monkeypatch.setattr(ms, "_EXACT_REFILL", session)
    monkeypatch.setattr(ms, "generate_candidates", lambda b, sp: [NS(board=b, i=i) for i in range(len(tree.get(b[0][0], [])))])

    def simulate(board, candidate, **kwargs):
        blue, nxt, exact = tree[board[0][0]][candidate.i]
        return NS(blue_cells=blue, board=[[nxt]], special_board=[[0]], exact_refill_supported=exact)

    monkeypatch.setattr(ms, "_simulate_created_candidate", simulate)
    best, fill = ms._exact_blue_within_three(
        [["a"]], [[0]], ms.BoosterState(current=1, maximum=7), mode="None", allow_square_matches=False,
        score_rally_values=None, explode_created_specials_immediately=False)
    # The 5-blue move is a guess and does not count; 2 + 2 + 3 = 7 >= 6 in three moves.
    assert best == 7 and fill == 3
