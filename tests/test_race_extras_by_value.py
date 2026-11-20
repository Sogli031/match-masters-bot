"""Showdown / Rumble / Party: the most valuable sure extra goes first (player, 2026-11-19)."""
import move_strategy as ms
from test_multiplier_madness import _extra


def test_race_plays_the_richest_extra_first(monkeypatch):
    monkeypatch.setattr(ms, '_with_extra_move_chain_bonus', lambda e, *a, **k: e)
    monkeypatch.setattr(ms, '_with_extra_preservation_metadata', lambda e, *a, **k: e)
    cheap = _extra(ms.ORANGE, 2, 30.0, [(3, c) for c in range(4)])
    rich = _extra(ms.RED, 1, 150.0, [(0, c) for c in range(4)])

    def first(context):
        return ms._rank_extra_priority_moves(
            [cheap, rich], 'None', False, None, False, strategy_context=context)[0]

    assert first(ms.StrategyContext(ms.STRATEGY_SOLO_6)) is rich
    # Solo Challenge and Versus keep the old keys: two extras beat one.
    assert first(ms.StrategyContext(ms.STRATEGY_SOLO_6, solo_challenge=True)) is cheap
    assert first(ms.StrategyContext(ms.STRATEGY_VERSUS_2)) is cheap
