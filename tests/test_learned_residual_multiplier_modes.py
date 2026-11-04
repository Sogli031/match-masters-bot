"""The value model stays out of the multiplier-building modes (2026-10-08).

It learns from what a move pays right away, so it cannot see the multiplier a
mushroom (or a dealt-colour combo, a column ramp ...) builds for later moves.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402


def _residual(monkeypatch, mode):
    monkeypatch.setattr(ms, "_LEARNED_RANK_DEPTH", 1)
    monkeypatch.setattr(ms.learned_value, "model", lambda: SimpleNamespace(enabled=True))
    monkeypatch.setattr(ms.learned_value, "residual_adjustment", lambda *a, **k: -50.0)
    return ms._learned_residual(SimpleNamespace(), "solo_race", None, None, None, "mid", mode)


def test_multiplier_modes_get_no_model_correction(monkeypatch):
    for mode in ms.LEARNED_RESIDUAL_EXCLUDED_MODES:
        assert _residual(monkeypatch, mode) == 0.0, mode
    # The name the GUI sends works too.
    assert _residual(monkeypatch, "Multiplier Mushrooms Studio") == 0.0


def test_other_modes_keep_the_model(monkeypatch):
    assert _residual(monkeypatch, ms.GameMode.NONE) == -50.0
    assert _residual(monkeypatch, ms.GameMode.CRAZY_COLUMNS) == -50.0
