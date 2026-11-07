"""Plunder Pirates (board model 8, PirateChestPiece = SlotValue 20) with the exact refill.

Recorded 2026-11-06 (Debug/research/20261106_143840_plunder-pirates): the
refill spawns the chest, a chest on the bottom row is collected, blasts pass
chests by and the Froggy pull walks around them. 27 of the 29 checkable moves (with the uncommitted Froggy rules; 25 without)
are exact; 007 (two lotuses) and 032 (chest collected beside cascade matches)
are still open.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

SESSION = ROOT / "Debug" / "research" / "20261106_143840_plunder-pirates"


def test_bottom_chest_is_collected():
    board = [[1, 2], [ms.CHEST, 3]]
    special = [[0, 0], [ms.SPECIAL_MODE_TARGET, 0]]
    origins = [[(0, 0), (0, 1)], [(1, 0), (1, 1)]]
    assert ms._collect_bottom_chests(board, special, origins) == [(1, 0)]
    assert board[1][0] == ms.EMPTY and special[1][0] == ms.EMPTY and origins[1][0] is None


def test_pull_does_not_walk_over_a_chest():
    assert not ms._froggy_can_be_matched(ms.CHEST)
    assert ms._froggy_can_be_matched(1)


def test_recorded_session_replays(monkeypatch):
    from refill_monitor import check_transition
    from strategy_lab import simulation

    files = sorted(SESSION.glob("[0-9][0-9][0-9].json"))
    if not files:
        pytest.skip("Plunder Pirates recording is not on this machine")
    # As TransitionChecker does: measuring is allowed outside the certified modes.
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {ms.GameMode.CHEST.value})
    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    verdicts = {}
    for index in range(1, len(records)):
        if records[index].get("missed_board_before"):
            continue
        answer = check_transition(records[index - 1], records[index])
        if answer is not None:
            verdicts[index] = answer["verdict"]
    # 010 and 012 are lotus moves that also need the Froggy blob/secondary
    # special-cell rules; they are exact once those are in.
    assert sum(v == "ok" for v in verdicts.values()) >= 25
    assert {8, 33} <= {i for i, v in verdicts.items() if v == "miss"} <= {8, 10, 12, 33}
