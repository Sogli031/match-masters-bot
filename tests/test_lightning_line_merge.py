"""Lightning + line swipe: the Lightning draws its targets from 48 pieces.

Recorded Square Match 2026-11-14 21:26:10 (refill_misses 20261114_212610):
a vertical dragged from (6,4) onto a Lightning at (6,3). GetMergeSwapOutcome
gives a mixed pair no merge type, so both pieces fire their own effect from
the end cell, but the swipe's start slot is already empty then. With the full
49-piece pool the simulator drew one RNG value too many (1479 vs 1478) and got
17 cells wrong; without the start cell every refill matched.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "lightning_line_merge" / "212610.json"


def test_lightning_plus_vertical_swipe_is_exact():
    from refill_monitor import check_transition

    pair = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
