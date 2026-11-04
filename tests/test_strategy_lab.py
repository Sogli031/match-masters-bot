"""Independent Strategy Lab regressions; no game or input driver is required."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import move_strategy as ms
from strategy_lab import experiment as ex
from strategy_lab import live
from strategy_lab.catalog import catalog
from strategy_lab.policy import (action_key, choose_action, identity, native_action,
                                 observable, recorded_action, POLICY_VERSION)
from strategy_lab.simulation import step


def fixture_move(mode="None"):
    board=[[1+(r*2+c)%6 for c in range(7)] for r in range(7)]
    board[0][0]=board[0][1]=ms.GREEN; board[1][2]=ms.GREEN
    board[0][2]=ms.PURPLE
    return dict(board=board,special_board=[[0]*7 for _ in range(7)],mode=mode,
        strategy_context={"mode":"versus_2"},active_booster=25,booster_action_mode="high_voltage",
        special_piece_mode="auto",selected_perks=["none","none"],perk_slot_status=[],
        selected_action="move",action="highest_points",booster_detection={"active":False},
        booster_state={"current":0,"maximum":7},turn_state={"remaining_moves":2},
        ufo={"ability_type":25,"eyes":0},mixy_meow={},allow_square_matches=False)


def fixture_actions(move):
    evaluations=ms.rank_moves(move["board"],move["special_board"],mode=move["mode"])
    actions=[native_action(e) for e in evaluations]
    return evaluations,actions


def config(move,variant="direct",mode="shadow"):
    return dict(mode=mode,budget_ms=1000,profile=dict(variant=variant,identity=identity(move),
                rules=ex.rules_version(),profile_version=POLICY_VERSION))


def write_runs(tmp_path,n=4):
    runs=tmp_path/"runs"
    for i in range(n):
        move=fixture_move();move["board"][6][6]=1+i
        _,actions=fixture_actions(move)
        move["best_move"]=actions[-1]
        folder=runs/f"2026-10-31_00-00-{i:02d}_000";folder.mkdir(parents=True)
        (folder/"move.json").write_text(json.dumps(move))
        (folder/"candidates.json").write_text(json.dumps(actions))
    return runs


@pytest.mark.parametrize("variant",["direct","extra","charge"])
def test_offline_shadow_exact_action_and_target(variant):
    move=fixture_move();_,actions=fixture_actions(move);baseline=actions[-1]
    offline=choose_action(observable(move),actions,variant,baseline,identity(move))
    executed,shadow=live.select(move,actions,baseline,config(move,variant))
    assert not offline.fallback
    assert action_key(offline.action)==action_key(shadow["recommendation"])
    assert offline.action["target"]==shadow["recommendation"]["target"]
    assert executed==baseline and not shadow["applied"]


def test_native_bridge_executes_identical_native_object(tmp_path,monkeypatch):
    move=fixture_move();evaluations,actions=fixture_actions(move)
    baseline=evaluations[-1]
    # Native request and frozen record carry the same observable flags.
    cfg=config(move,mode="active")
    monkeypatch.setattr(live,"settings",lambda:cfg)
    monkeypatch.setattr(live,"DIRECTORY",tmp_path)
    monkeypatch.setattr(live,"AUDIT",tmp_path/"audit.jsonl")
    request=SimpleNamespace(action="highest_points",perk_slot_status=[],booster_action_mode="high_voltage",
                            special_piece_mode="auto",remaining_moves=2)
    selected,label,token=live.runtime_select(request=request,mode=ms.GameMode.NONE,
        context=ms.StrategyContext(mode="versus_2"),board=move["board"],special_board=move["special_board"],
        evaluations=evaluations,baseline=baseline,selected_action="move",booster_detection={"active":False},
        selected_perks=("none","none"),ufo_state=ms.UfoState(ability_type=25),mixy_state=None,
        flags={"allow_square_matches":False})
    assert token and "active" in label
    expected=choose_action(observable(move),actions,"direct",native_action(baseline),identity(move))
    assert action_key(native_action(selected))==action_key(expected.action)
    assert isinstance(selected,ms.MoveEvaluation)
    packet=json.loads(next((tmp_path/"decisions").glob("*.json")).read_text())
    replay=choose_action(observable(packet["move"]),packet["actions"],"direct",packet["baseline"],cfg["profile"]["identity"])
    assert replay.action==packet["decision"]["recommendation"]


def test_wrong_setup_incomplete_mode_and_revert():
    move=fixture_move();_,actions=fixture_actions(move);baseline=actions[-1];cfg=config(move,mode="active")
    other=deepcopy(move);other["ufo"]["ability_type"]=49
    chosen,record=live.select(other,actions,baseline,cfg)
    assert chosen==baseline and record["reason"]=="profile_identity_mismatch"
    incomplete=fixture_move("Zany Zappers")
    _,record=live.select(incomplete,actions,baseline,config(incomplete,mode="active"))
    assert record["fallback"] and "incomplete_mode" in record["reason"]
    chosen,record=live.select(move,actions,baseline,{"mode":"existing"})
    assert chosen==baseline and record["reason"]=="existing_strategy"


def test_perks_booster_and_manual_are_explicit_fallbacks():
    for updates,reason in (({"selected_perks":["hammer","none"]},"available_perk"),
                           ({"booster_detection":{"active":True}},"booster_ready"),
                           ({"action":"extra_move"},"manual_action")):
        move=fixture_move();move.update(updates);_,actions=fixture_actions(move)
        choice=choose_action(observable(move),actions,"direct",actions[0],identity(move))
        assert choice.fallback and reason in choice.reason


def test_budget_and_rules_fallback():
    move=fixture_move();_,actions=fixture_actions(move);cfg=config(move,mode="active");cfg["budget_ms"]=-1
    selected,out=live.select(move,actions,actions[-1],cfg)
    assert selected==actions[-1] and out["reason"]=="budget_exceeded"
    cfg["profile"]["rules"]={}
    assert live.select(move,actions,actions[-1],cfg)[1]["reason"]=="profile_version_or_rules_mismatch"


def test_two_rulesets_use_same_transition_and_preserve_input():
    plain=fixture_move();crush=fixture_move(ms.GameMode.COLOR_CRUSH.value)
    action={"start":[1,2],"target":[0,2],"direction":"up"}
    original=deepcopy(plain)
    a,b=step(plain,action),step(crush,action)
    assert a["supported"] and b["supported"]
    assert b["value"]>a["value"]
    assert a["state"]["turn_state"]["remaining_moves"]==1
    assert a["terminal_reason"].startswith("unknown_refill")
    assert plain==original


def test_resume_is_exactly_once_and_inputs_are_frozen(tmp_path):
    runs=write_runs(tmp_path);job=tmp_path/"job.sqlite"
    ex.create_job(job,runs=runs,limit=4)
    first=ex.run(job,max_trials=1)
    assert first["completed"]==1 and first["status"]=="paused"
    # External source changes cannot alter an already-created experiment.
    for p in runs.glob("*/move.json"):p.write_text("{}")
    result=ex.run(job)
    assert result["completed"]==result["total"]==4
    assert result["status"]=="completed"
    assert ex.run(job)["completed"]==4
    with ex.connect(job) as db:
        assert db.execute("SELECT count(DISTINCT input_id) FROM trials").fetchone()[0]==4
    report=ex.report(job)
    assert report["full_matches"]==0 and report["refill_samples"]==0
    assert all(g["verified_for_full_game"] is False for g in report["groups"].values())


def test_worker_lock_and_pause(tmp_path):
    runs=write_runs(tmp_path);job=tmp_path/"job.sqlite";ex.create_job(job,runs=runs)
    with ex.worker_lock(job):
        with pytest.raises(RuntimeError):ex.run(job)
    ex.pause(job);assert ex.status(job)["status"]=="paused"
    ex.run(job,max_trials=1)
    # Simulate restart while saved status still says running.
    with ex.connect(job) as db:ex.set_meta(db,"status","running")
    assert ex.run(job)["completed"]==4


def test_catalog_is_installation_derived_and_no_fake_equipment_ranking():
    inventory=catalog()
    assert {m["label"] for m in inventory["modes"]}=={m.value for m in ms.GameMode}
    assert not inventory["equipment_ranking"]["supported"]
    assert all(row["gap"] for row in inventory["modes"]+inventory["boosters"]+inventory["perks"])


def test_hidden_future_cannot_change_policy():
    move=fixture_move();_,actions=fixture_actions(move)
    state=observable(move)
    move.update(observed_delta={"score":999999},seed=999,future_board=[[7]*7]*7)
    assert observable(move)==state


def test_atomic_settings_and_missing_profile(tmp_path):
    path=tmp_path/"live.json"
    live.configure("existing",path=path)
    assert json.loads(path.read_text())["mode"]=="existing"
    with pytest.raises(ValueError):live.configure("active",path=path)


def test_goal_identity_does_not_include_progress():
    move=fixture_move();move["strategy_context"].update(solo_challenge=True,
        solo_goal=dict(targets=[800,1600],score=0,multiplier=1,overflow=True))
    before=identity(move)
    move["strategy_context"]["solo_goal"].update(score=753,multiplier=2)
    assert identity(move)==before


def test_full_swap_pool_includes_special_combination():
    from strategy_lab.simulation import legal_actions
    move=fixture_move()
    move["special_board"][3][3]=ms.SPECIAL_HORIZONTAL
    move["special_board"][3][4]=ms.SPECIAL_VERTICAL
    _,actions=legal_actions(move)
    assert any({tuple(a["start"]),tuple(a["target"])}=={(3,3),(3,4)} for a in actions)
    choice=choose_action(observable(move),actions,"direct",actions[-1],identity(move))
    assert not choice.fallback
    combo=next(a for a in actions if {tuple(a["start"]),tuple(a["target"])}=={(3,3),(3,4)})
    assert step(move,combo)["value"]>0


def test_negative_utility_does_not_remove_legal_actions(monkeypatch):
    from strategy_lab.simulation import legal_actions
    move=fixture_move();original=ms.evaluate_simulation
    def negative(*args,**kwargs):return replace(original(*args,**kwargs),score=-10000)
    monkeypatch.setattr(ms,"evaluate_simulation",negative)
    _,actions=legal_actions(move)
    assert actions and all(a["score"]<0 for a in actions)
    assert not choose_action(observable(move),actions,"direct",actions[0],identity(move)).fallback


@pytest.mark.parametrize("name",["2026-10-31_11-22-20_922","2026-10-31_13-04-40_351"])
def test_real_snapshot_offline_shadow_parity(name):
    from strategy_lab.simulation import legal_actions
    path=Path(__file__).resolve().parents[1]/"Debug"/"runs"/name/"move.json"
    move=json.loads(path.read_text(encoding="utf-8"));_,actions=legal_actions(move)
    baseline=recorded_action(move["best_move"])
    offline=choose_action(observable(move),actions,"direct",baseline,identity(move))
    executed,shadow=live.select(move,actions,baseline,config(move))
    assert not offline.fallback
    assert offline.action==shadow["recommendation"]
    assert offline.action["target"]==shadow["recommendation"]["target"]
    assert executed==baseline
