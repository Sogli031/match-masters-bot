"""The refill check replays a played perk instead of calling it uncheckable.

Square Match 2026-11-14 (research 20261114_230352): a Teleport (010->011,
moves 6->7) and an Energy Boost (017->018) read "odigran perk, ne moze da se
proveri" in the GUI while the research report found both exact.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "perk_check"


@pytest.mark.parametrize("name", ["teleport", "energy_boost"])
def test_played_perk_is_checked(name):
    from refill_monitor import check_transition

    pair = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    result = check_transition(pair["before"], pair["after"]) or {}
    assert result.get("verdict") == "ok", result
