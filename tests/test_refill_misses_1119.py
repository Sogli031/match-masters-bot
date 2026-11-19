"""Two live refill misses of 2026-11-19, both replayed exactly now.

* merge (Multiplier Madness 18:21:34): a Lightning dragged onto a bomb. The
  chained specials fire in the order the two areas were added -- the crosshair
  the Lightning hit before the Lightning the bomb hit -- not x-major.
* froggy (Gem Grab 18:02:55): the entrance attempts are scored with a crystal
  at its number, not its colour; the colour value picked the wrong attempt.
"""
import json
from pathlib import Path

import pytest

FRAMES = Path(__file__).resolve().parent / "fixtures" / "refill_misses_1119"


def _record(name):
    return json.loads((FRAMES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["merge", "froggy"])
def test_live_miss_now_replays(name):
    from refill_monitor import check_transition
    verdict = check_transition(_record(f"{name}_000"), _record(f"{name}_001"))
    assert verdict["verdict"] == "ok", verdict


def test_merge_order_is_what_fixes_it(monkeypatch):
    import move_strategy as ms
    from refill_monitor import check_transition
    monkeypatch.setattr(ms, "MERGE_EFFECT_ORDER", False)
    assert check_transition(_record("merge_000"), _record("merge_001"))["verdict"] != "ok"
