"""Measure the native live bridge on actual recordings, with no input drivers."""
import json
from pathlib import Path
import statistics
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import move_strategy as ms
from solo_challenge import SoloGoalState
from . import live
from .catalog import ROOT, records
from .experiment import DATA, rules_version
from .policy import identity, observable, support_reason, POLICY_VERSION
from .simulation import legal_actions


def main():
    values=[];fallbacks=[]
    with tempfile.TemporaryDirectory() as folder:
        directory=Path(folder)
        for path,move in records(ROOT/"Debug"/"runs","2026-10-31"):
            if support_reason(observable(move)) is not None:continue
            evaluations,_=legal_actions(move)
            if not evaluations:continue
            raw=move["strategy_context"]
            context=ms.StrategyContext(mode=raw["mode"],solo_challenge=bool(raw.get("solo_challenge")),
                                      solo_goal=SoloGoalState.from_payload(raw.get("solo_goal")))
            request=SimpleNamespace(action=move["action"],perk_slot_status=move.get("perk_slot_status"),
                booster_action_mode=move["booster_action_mode"],special_piece_mode=move["special_piece_mode"],
                remaining_moves=move["turn_state"]["remaining_moves"])
            config=dict(mode="shadow",budget_ms=50,profile=dict(variant="direct",identity=identity(move),
                        profile_version=POLICY_VERSION,rules=rules_version()))
            with patch.object(live,"settings",return_value=config),patch.object(live,"DIRECTORY",directory),patch.object(live,"AUDIT",directory/"audit.jsonl"):
                _,_,token=live.runtime_select(request=request,mode=move["mode"],context=context,
                    board=move["board"],special_board=move["special_board"],evaluations=evaluations,
                    baseline=evaluations[0],selected_action=move["selected_action"],booster_detection=move["booster_detection"],
                    selected_perks=move["selected_perks"],ufo_state=ms.UfoState(ability_type=(move.get("ufo")or{}).get("ability_type")),
                    mixy_state=None,flags=identity(move)["flags"])
                packet=json.loads((directory/"decisions"/(token+".json")).read_text(encoding="utf-8"))["decision"]
                values.append(packet["selector_ms"])
                if packet.get("fallback"):fallbacks.append(packet["reason"])
            if len(values)>=50:break
    result=dict(n=len(values),median_ms=statistics.median(values),p95_ms=sorted(values)[int(len(values)*.95)-1],
                max_ms=max(values),budget_ms=50,fallbacks=fallbacks,
                method="50 real snapshots; full native bridge in shadow; temporary audit; no game, no input drivers")
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/"timing.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
