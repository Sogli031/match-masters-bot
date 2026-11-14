"""Checkmate Charles activation (CheckmateCharles.Use), 31 of 31 recorded exact.

* the first activation of a match: the blast (a row or column, never the
  last one, plus a diagonal) and its cascade;
* with knights on the board: removePreviousPieces turns them back into plain
  pieces first (CreateBoosterPieceBackToNormalConversion, 5 draws each),
  traced Square Match 20261114_232927 005->006;
* with one move left: the knights still come back, the booster spends no move.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "charles_activation"


@pytest.mark.parametrize("name", ["first", "with_knights", "last_move"])
def test_recorded_charles_activation_is_exact(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result


def test_explosion_never_draws_the_last_row_or_column():
    from engine_rng import EngineRNG
    from strategy_lab.simulation import charles_explosion_cells

    board = [[1] * 7 for _ in range(7)]
    for seed in range(200):
        cells = charles_explosion_cells(board, EngineRNG.from_seed(seed))
        line = cells[:7]
        assert not all(r == 6 for r, _ in line) and not all(c == 6 for _, c in line)
