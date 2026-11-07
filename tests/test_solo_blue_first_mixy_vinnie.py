"""Solo Challenge blue-first for Mixy Meow code moves and Vinnie SE hearts (2026-11-07)."""
from types import SimpleNamespace as NS

import move_strategy as ms


def _heart(score, charge, hearts=1):
    events = [{"type": "special_activation", "special": "vinnie_se_heart"}] * hearts
    return NS(score=score, intent_events=events, charge=charge)


def _plain(score, charge):
    return NS(score=score, intent_events=[], charge=charge)


def test_vinnie_hearts_swap_places_for_charge_only_in_solo_challenge(monkeypatch):
    monkeypatch.setattr(ms, "_useful_total_charge_cells", lambda item, *a: item.charge)
    moves = [_heart(90, 1), _plain(80, 9), _heart(70, 4)]
    monkeypatch.setattr(ms, "_special_booster_blue_first", lambda *a: True)
    out = ms._solo_vinnie_heart_blue_first_order(moves, "None", None, None, None, None)
    assert [m.score for m in out] == [70, 80, 90]          # hearts swapped, plain move stays
    monkeypatch.setattr(ms, "_special_booster_blue_first", lambda *a: False)
    assert ms._solo_vinnie_heart_blue_first_order(moves, "None", None, None, None, None) is moves


def test_mixy_and_vinnie_are_in_the_ranking_wrapper():
    import inspect
    assert "_solo_vinnie_heart_blue_first_order(" in inspect.getsource(ms.prioritize_ranked_moves)
    source = inspect.getsource(ms.rank_mixy_code_moves)
    assert "_special_booster_blue_first(strategy_context, turn_state)" in source
    assert "_useful_total_charge_cells(" in source
