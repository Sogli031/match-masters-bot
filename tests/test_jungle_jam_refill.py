import json
from pathlib import Path

import pytest

from tools.analyze_research import capture_from, observed, try_transition


RECORDING = Path(__file__).resolve().parents[1] / "Debug/research/20261107_224136_jungle-rumble"


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Jungle Jam recording not present")
@pytest.mark.parametrize("index", [7, 9, 15])
def test_jungle_jam_leaf_refill_matches_recording(index):
    before, after = (
        json.loads((RECORDING / f"{i:03d}.json").read_text(encoding="utf-8"))
        for i in (index, index + 1)
    )
    matches, closest, _ = try_transition(capture_from(before), observed(after))
    assert matches, closest
