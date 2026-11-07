"""Froggy lotus misses recorded 2026-11-06 (Debug/refill_misses).

* Match & Hatch: the lotus blob keeps its shape's special (a bomb); the random
  hatch is only for the player's own combos, so no draw is spent on it.
* Blow 'em up: a lotus blob that makes a Lightning fires it in the same move
  at random targets; the monitor reports that as not checkable, not a miss.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MISSES = ROOT / "Debug" / "refill_misses"


def _pair(name):
    folder = MISSES / name
    if not (folder / "000.json").exists():
        pytest.skip(f"recording {name} is not on this machine")
    load = lambda f: json.loads((folder / f).read_text(encoding="utf-8"))
    return load("000.json"), load("001.json")


@pytest.mark.parametrize("name", [
    "20261106_132747_403994_match-and-hatch",
    "20261106_132817_468859_match-and-hatch",
    "20261106_132952_926391_match-and-hatch",
    "20261106_133156_433956_match-and-hatch",
])
def test_match_and_hatch_lotus_blob_is_not_hatched(name):
    from refill_monitor import check_transition

    before, after = _pair(name)
    assert check_transition(before, after)["verdict"] == "ok"


@pytest.mark.parametrize("name", [
    "20261106_134348_442641_blow-em-up",
    "20261106_134618_587982_blow-em-up",
])
def test_blow_em_up_same_move_lightning_is_not_a_miss(name):
    from refill_monitor import check_transition

    before, after = _pair(name)
    assert check_transition(before, after)["verdict"] == "unsupported"
