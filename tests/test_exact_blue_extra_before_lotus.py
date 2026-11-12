"""A blue extra picked before the lotus, checked with the exact drop.

Crazy Columns 2026-11-12 01:13:22 / 01:14:00: blue_extra_before_lotus_gate
picks went without the exact refill.
"""
from types import SimpleNamespace

import move_strategy as ms

BOARD = [[1, 2], [3, 4]]
SPECIAL = [[0, 0], [0, 20]]


def _setup(monkeypatch, extra, lotus_left, exact_lotus=None):
    session = SimpleNamespace(knows=lambda board: True, use_special_keys=False)
    monkeypatch.setattr(ms, "_EXACT_REFILL", session)
    special_after = [[0, 0], [0, 20]] if lotus_left else [[0, 0], [0, 0]]
    result = SimpleNamespace(exact_refill_supported=True, intent_events=[], extra_moves=extra,
                             special_board=special_after)
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", lambda *a, **k: result)
    monkeypatch.setattr(ms, "exact_froggy_lotus_choice", lambda *a, **k: exact_lotus)
    return SimpleNamespace(candidate="extra"), [SimpleNamespace(candidate="lotus")]


def test_a_confirmed_extra_that_leaves_the_lotus_stays(monkeypatch):
    extra, lotus = _setup(monkeypatch, extra=1, lotus_left=True)
    pick = ms.exact_blue_extra_before_lotus_check(extra, lotus, BOARD, SPECIAL)
    assert pick[0] is extra and "potvrdjen" in pick[1]


def test_no_real_extra_collects_the_lotus_now(monkeypatch):
    extra, lotus = _setup(monkeypatch, extra=0, lotus_left=True)
    pick = ms.exact_blue_extra_before_lotus_check(extra, lotus, BOARD, SPECIAL)
    assert pick[0] is lotus[0] and "nije siguran" in pick[1]


def test_an_extra_that_breaks_the_lotus_prefers_the_exact_collect(monkeypatch):
    better = SimpleNamespace(candidate="exact lotus")
    extra, lotus = _setup(monkeypatch, extra=1, lotus_left=False,
                          exact_lotus=(better, "lotus sa tacnom dopunom"))
    assert ms.exact_blue_extra_before_lotus_check(extra, lotus, BOARD, SPECIAL)[0] is better


def test_without_a_session_the_plain_pick_stays(monkeypatch):
    monkeypatch.setattr(ms, "_EXACT_REFILL", None)
    assert ms.exact_blue_extra_before_lotus_check(object(), [object()], BOARD, SPECIAL) is None
