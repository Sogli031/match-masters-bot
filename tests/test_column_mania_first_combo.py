"""Column Mania raises the columns of the swipe's first combo only.

Research 20261120_083206 002->003 (cols 4, 5 raised, not 0-2 or 6) and
036->037 (the first combo's columns are capped at 10: nothing raised, col 6
stays 5). The refill check now reports a wrong multiplier ("resources").
"""
import json
from pathlib import Path

import pytest

import refill_monitor
from tools.analyze_research import resource_verdict

FIXTURES = Path(__file__).resolve().parent / "fixtures/column_mania_first_combo"


@pytest.mark.parametrize("before, after", [("002", "003"), ("036", "037")])
def test_first_combo_multipliers_are_exact(before, after):
    rec_a = json.loads((FIXTURES / f"{before}.json").read_text(encoding="utf-8"))
    rec_b = json.loads((FIXTURES / f"{after}.json").read_text(encoding="utf-8"))
    answer = refill_monitor.check_transition(rec_a, rec_b)
    assert answer["verdict"] == "ok", answer


def test_resource_verdict():
    assert resource_verdict("x", []) == ("ok", "x")
    assert resource_verdict("x", ["skor 5 (sim 4)"]) == ("ok", "x, ali skor 5 (sim 4)")
    assert resource_verdict("x", ["potezi 5 (sim 3)"])[0] == "resources"
