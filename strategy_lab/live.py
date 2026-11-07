"""Small live bridge; native execution and verification remain in runtime.py."""
from __future__ import annotations
from dataclasses import asdict
import json
import os
from pathlib import Path
import time
import uuid

from .catalog import ROOT
from .policy import (POLICY_VERSION, action_key, canonical, choose_action, identity,
                     native_action, observable, support_reason)

DIRECTORY = ROOT / "Debug" / "strategy_lab"
SETTINGS = DIRECTORY / "live.json"
AUDIT = DIRECTORY / "live.jsonl"
_cache = (None, {"mode": "existing"})
_pending = None
_last_observation = None


def atomic_json(path, payload):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("w",encoding="utf-8") as stream:
            stream.write(json.dumps(payload,ensure_ascii=False,indent=2)); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists(): tmp.unlink()


def settings():
    global _cache
    try:
        stamp = SETTINGS.stat().st_mtime_ns
        if stamp != _cache[0]:
            value = json.loads(SETTINGS.read_text(encoding="utf-8"))
            _cache = stamp, value
        return _cache[1]
    except (OSError, ValueError):
        return {"mode": "existing"}


def configure(mode, profile=None, path=None):
    if mode not in ("existing", "shadow", "active"):
        raise ValueError("unknown live mode")
    if mode != "existing" and not profile:
        raise ValueError("Izaberite profil sa tačnim setupom iz izveštaja.")
    atomic_json(path or SETTINGS, dict(mode=mode, profile=profile, budget_ms=50))


def audit(payload):
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    with AUDIT.open("a",encoding="utf-8") as stream:
        stream.write(canonical(dict(at=time.time(),**payload))+"\n")


def select(move, actions, baseline, config, *, elapsed_before_ms=0):
    """This pure bridge is exercised offline by parity tests as well."""
    mode = config.get("mode", "existing")
    if mode == "existing":
        return baseline, {"mode": mode, "reason": "existing_strategy", "recommendation": baseline}
    started = time.perf_counter()
    profile = config.get("profile") or {}
    from .experiment import rules_version
    if profile.get("profile_version") != POLICY_VERSION or profile.get("rules") != rules_version():
        return baseline, dict(mode=mode, reason="profile_version_or_rules_mismatch", recommendation=baseline, fallback=True)
    if not isinstance(profile.get("identity"),dict):
        return baseline, dict(mode=mode,reason="missing_profile_identity",fallback=True,recommendation=baseline)
    choice = choose_action(observable(move), actions, profile.get("variant"), baseline, profile.get("identity"))
    elapsed = elapsed_before_ms + (time.perf_counter()-started)*1000
    expired = elapsed > config.get("budget_ms",50)
    applied = mode == "active" and not choice.fallback and not expired
    return (choice.action if applied else baseline), dict(
        mode=mode, profile=profile.get("variant"), identity=identity(move),
        baseline=baseline, recommendation=choice.action, planned=choice.action if applied else baseline,
        reason="budget_exceeded" if expired else choice.reason, fallback=choice.fallback or expired,
        applied=applied, selector_ms=elapsed, verified_for_full_game=False)


def runtime_select(*, request, mode, context, board, special_board, evaluations, baseline,
                   selected_action, booster_detection, selected_perks, ufo_state, mixy_state,
                   flags):
    """Return an existing native evaluation object, never a synthetic swipe."""
    config = settings()
    if config.get("mode") == "existing":
        return baseline, "", None
    started = time.perf_counter()
    move = dict(mode=getattr(mode,"value",mode), strategy_context=asdict(context), board=board,
                special_board=special_board, selected_action=selected_action, action=request.action,
                booster_detection=booster_detection, selected_perks=list(selected_perks),
                perk_slot_status=request.perk_slot_status, booster_action_mode=request.booster_action_mode,
                special_piece_mode=getattr(request,"special_piece_mode","auto"), active_booster="unknown",
                ufo=asdict(ufo_state) if ufo_state is not None else {},
                mixy_meow=asdict(mixy_state) if mixy_state is not None else {},
                turn_state={"remaining_moves":request.remaining_moves}, **flags)
    # The original survives even if it was produced by a native special gate.
    native = list(evaluations or [])
    if support_reason(observable(move)) is None:
        from .simulation import legal_actions
        native,_=legal_actions(move)
    if baseline is not None: native.append(baseline)
    mapping = {action_key(native_action(e)):e for e in native}
    actions = [native_action(e) for e in native]
    original = native_action(baseline) if baseline is not None else None
    chosen, payload = select(move, actions, original, config,
                             elapsed_before_ms=(time.perf_counter()-started)*1000)
    token = uuid.uuid4().hex
    payload.update(event="decision", id=token, board=board, special_board=special_board,
                   selected_action=selected_action, game_outcome="unknown_pending_observation")
    audit(payload)
    atomic_json(DIRECTORY / "decisions" / (token + ".json"),
                dict(move=move, actions=actions, baseline=original, decision=payload))
    reason = payload.get("reason","")
    label = f"[Lab {config['mode']}: {config.get('profile',{}).get('variant','?')}; {reason}] "
    return mapping.get(action_key(chosen or {}),baseline), label, token


def record_execution(token, executed, fresh_provider=None):
    global _pending, _last_observation
    if not token: return
    state = None
    if executed and fresh_provider is not None:
        try: state = fresh_provider()
        except Exception: pass
    # A sent swipe or an early frame is not a confirmed result or a win.
    audit(dict(event="execution", id=token, sent=bool(executed), observation=state,
               outcome="fresh_frame_unconfirmed" if state is not None else "await_next_native_scan"))
    if executed:
        _pending=token;_last_observation=None


def observe_snapshot(snapshot):
    """Join native, settled observations to a sent decision; do not infer wins."""
    global _last_observation
    if not _pending:return
    state=(snapshot or {}).get("state") or {}
    if state.get("chain_reaction"):return
    players=[{k:p.get(k) for k in ("player_type","score","score_multiplier","is_my_turn")}
             for p in state.get("players") or ()]
    observation={"game_state":state.get("game_state"),"round":state.get("current_round"),
                 "moves":state.get("moves"),"players":players,
                 "explicit_outcome":{k:state[k] for k in ("winner","winner_id","game_result","match_result") if k in state}}
    from .native_rules import terminal_observation
    terminal=terminal_observation(state.get('game_state'))
    if terminal is not None:
        observation['explicit_outcome']['terminal_state']=terminal
    signature=canonical(observation)
    if signature==_last_observation:return
    audit(dict(event="native_observation",id=_pending,observation=observation,
               outcome="engine_reported" if observation["explicit_outcome"] else "unknown: scores alone do not prove final outcome"))
    _last_observation=signature


def profile_from_report(report, group_key, variant):
    group = report["groups"][group_key]
    if variant == "existing": raise ValueError("Use existing strategy instead.")
    return dict(variant=variant, identity=group["identity"], profile_version=POLICY_VERSION,
                rules=report["config"]["rules"], evidence=group.get("held_out_result"),
                scope=report["metric"], verified_for_full_game=False)
