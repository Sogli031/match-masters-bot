"""Vinnie SE two-colour hearts on the board no longer switch the exact refill off.

2026-11-07 07:00-07:10 (log): "UnsupportedRefill: Unported simulator
special/color in refill board" on every board holding a Vinnie SE heart, so the
drop was neither used nor checked (55 moves uncheckable). The engine keeps the
heart as a CupidHeart (SlotValue 23) with the pair's other colour in color2.
"""
import json
from pathlib import Path

import pytest

import engine_refill
import move_strategy as ms

RECORDING = Path(__file__).resolve().parents[1] / "Debug" / "research" / "20261107_053132_column-mania"


class _Model:
    profile = None
    random_specials = ()
    billie = None

    def __init__(self):
        self.raw = None

    def ball_colors_at(self, cells):
        return {}

    def fill(self, raw, chain_combos):
        self.raw = raw
        return raw, []


def _fill(monkeypatch, board, special):
    sim_to_engine = {color: color + 10 for color in range(1, 7)}
    monkeypatch.setattr(engine_refill, "color_maps",
                        lambda profile: (sim_to_engine, {v: k for k, v in sim_to_engine.items()}))
    model = _Model()
    engine_refill.fill_simulator_board(model, board, special)
    return model.raw


def test_heart_goes_to_the_engine_as_a_cupid_heart_with_its_second_colour(monkeypatch):
    heart = ms.make_vinnie_se_heart_special(ms.RED, ms.YELLOW)
    raw = _fill(monkeypatch, [[ms.YELLOW, ms.BLUE]], [[heart, 0]])
    assert raw[0][0] == {"color": ms.YELLOW + 10, "value": 23, "canBeMatched": True,
                         "color2": ms.RED + 10}
    assert raw[0][1]["value"] == 0


def test_heart_whose_board_colour_is_outside_its_pair_is_refused(monkeypatch):
    heart = ms.make_vinnie_se_heart_special(ms.RED, ms.YELLOW)
    with pytest.raises(engine_refill.UnsupportedRefill):
        _fill(monkeypatch, [[ms.GREEN]], [[heart]])


@pytest.mark.skipif(not RECORDING.is_dir(), reason="Vinnie SE recording not present")
def test_recorded_moves_with_hearts_on_the_board_check_out():
    from refill_monitor import check_transition

    records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDING.glob("*.json"))]
    verdicts = []
    for before, after in zip(records, records[1:]):
        if not any(ms.is_vinnie_se_heart_special(v) for row in before["special_board"] for v in row):
            continue
        result = check_transition(before, after)
        if result is not None and result["verdict"] != "booster":
            verdicts.append(result["verdict"])
    # 18 of 19 exact; the last move fires a random-target special.
    assert verdicts.count("ok") >= 18
    assert "miss" not in verdicts
