"""Solo Challenge Froggy: a reliable extra that out-charges every lotus goes first.

Exact refill audit of 313 recorded Froggy solo moves (2026-11-07): five lotus
collects banked 0-1 while a same-move extra banked 4-7 and left the lotus
standing. Both keep the turn, so the extra goes first and the lotus fires next
move. On the 109 recorded boards with a lotus this changes exactly those five
(charge 381 -> 402) and no other.
* arcade-man 031: lotus 1, extra 7.
* mighty-mushrooms 051: lotus 0, extra 4.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from tools.analyze_research import local_player
from tools.rebuild_evaluation import build_states

CASES = json.loads((ROOT / "tests/fixtures/froggy_solo_extra_before_lotus.json").read_text(encoding="utf-8"))


def _decide(name):
    from engine_refill import EngineRefill, ExactRefillSession

    record, frame = CASES[name]["record"], CASES[name]["frame"]
    states = build_states(frame)
    session = ExactRefillSession(EngineRefill.from_profile(record["profile"]), record["board"],
                                 special_board=record["special_board"], follow_moves=True)
    gather = ms.froggy_gather_config_from_params(local_player(record).get("special_ability_params"))
    common = dict(mode=states["mode"], score_rally_values=states["score_rally_values"])
    with ms.exact_refill_active(session), ms.froggy_gather_region_active(*gather):
        ranked = ms.rank_moves(frame["board"], frame["special_board"],
                               allow_square_matches=frame["allow_square_matches"],
                               explode_created_specials_immediately=frame["specials_explode_immediately"],
                               strategy_context=states["strategy_context"], include_future_value=True, **common)
        lotus = ms.rank_froggy_lotus_moves(
            ranked, frame["board"], frame["special_board"], booster_state=states["booster_state"],
            turn_state=states["turn_state"], strategy_context=states["strategy_context"],
            specials_auto_explode=frame["specials_explode_immediately"], **common)
        extra = ms.blue_extra_move_before_lotus(
            ranked, lotus, frame["special_board"], allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            booster_state=states["booster_state"], turn_state=states["turn_state"],
            strategy_context=states["strategy_context"], **common)
    charge = lambda e: ms._useful_total_charge_cells(
        e, states["booster_state"], states["mode"], states["score_rally_values"],
        states["strategy_context"], states["turn_state"])
    return extra, lotus, charge


@pytest.mark.parametrize("name, extra_charge", [
    ("20261106_150156_arcade-man/031", 7.0),
    ("20261104_144248_mighty-mushrooms/051", 4.0),
])
def test_extra_that_out_charges_the_lotus_goes_first(name, extra_charge):
    extra, lotus, charge = _decide(name)
    assert extra is not None
    assert charge(extra) == pytest.approx(extra_charge)
    assert charge(extra) > max(charge(e) for e in lotus)


def test_switch_off_restores_the_lotus_first(monkeypatch):
    monkeypatch.setattr(ms, "SOLO_EXTRA_BEFORE_LOTUS", False)
    extra, _lotus, _charge = _decide("20261106_150156_arcade-man/031")
    assert extra is None
