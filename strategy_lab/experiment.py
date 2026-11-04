"""Frozen inputs, exactly-once SQLite commits, pause/resume and paired reports."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import statistics
import time
from contextlib import contextmanager

from . import VERSION
from .catalog import ROOT, read_json, records
from .policy import (VARIANTS, POLICY_VERSION, action_key, canonical, choose_action,
                     digest, identity, observable, recorded_action)
from .simulation import step, legal_actions

DATA = ROOT / "Debug" / "strategy_lab"


def rules_version():
    paths = [ROOT / "move_strategy.py", Path(__file__), Path(__file__).with_name("policy.py"),
             Path(__file__).with_name("simulation.py")]
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def set_meta(db, key, value):
    db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, canonical(value)))


def get_meta(db, key):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def create_job(path, *, runs=ROOT / "Debug" / "runs", day=None, modes=(), formats=(), setups=(),
               goal=None, detail="quick", seed=1729, limit=120, group_keys=()):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Posao postoji. Koristite resume; ne prepisujem rezultate.")
    db = connect(path)
    db.executescript("""
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE inputs(id TEXT PRIMARY KEY, source TEXT, payload TEXT NOT NULL, split TEXT, identity_key TEXT);
        CREATE TABLE trials(input_id TEXT PRIMARY KEY REFERENCES inputs(id), payload TEXT NOT NULL, seconds REAL NOT NULL);
    """)
    config = dict(version=VERSION, profile_version=POLICY_VERSION, rules=rules_version(), seed=seed,
                  day=day, modes=list(modes), formats=list(formats), setups=list(setups), goal=goal,
                  detail=detail, limit=limit, group_keys=list(group_keys), runs=str(Path(runs).resolve()),
                  scope="B: deterministic prefix from actual equipped state; no full matches or equipment ranking",
                  baseline_source="historical recorded native action; current rule adapter evaluates both branches",
                  refill="not sampled: stop at unknown refill", profiles=list(VARIANTS))
    set_meta(db, "config", config)
    set_meta(db, "status", "preparing")
    db.commit()
    seen, counts = set(), {}
    try:
        for source, move in records(runs, day):
            ident = identity(move)
            ikey = digest(ident)
            if modes and ident["mode"] not in modes: continue
            if formats and ident["format"] not in formats: continue
            if setups and digest(ident["setup"]) not in setups: continue
            if goal is not None and canonical(ident["goal"]) != canonical(goal): continue
            if group_keys and ikey not in group_keys: continue
            # Limit per ruleset: selecting several modes must not let the first exhaust the budget.
            if counts.get(ident["mode"], 0) >= limit: continue
            try:
                pool = [recorded_action(a) for a in read_json(source.with_name("candidates.json"))]
                pool = [a for a in pool if a]
                baseline = recorded_action(move.get("best_move"))
                if not pool or baseline is None: continue
                board_key = digest({"board": move["board"], "special": move["special_board"], "identity": ident})
                if board_key in seen: continue
                seen.add(board_key)
                split = "validation" if int(digest([seed, board_key])[:8], 16) % 4 == 0 else "selection"
                payload = dict(move=move, actions=pool, baseline=baseline,
                               input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                               candidates_sha256=hashlib.sha256(source.with_name("candidates.json").read_bytes()).hexdigest())
                db.execute("INSERT INTO inputs VALUES (?,?,?,?,?)",
                           (board_key, str(source.resolve()), canonical(payload), split, ikey))
                counts[ident["mode"]] = counts.get(ident["mode"], 0) + 1
            except (ValueError, OSError, TypeError, KeyError):
                continue
        set_meta(db, "status", "paused" if seen else "empty")
        db.commit()
    finally:
        db.close()
    return status(path)


@contextmanager
def worker_lock(path):
    """OS lock is automatically released after process termination/reboot."""
    stream = open(str(path) + ".worker.lock", "a+b")
    try:
        stream.seek(0); stream.write(b"0"); stream.flush(); stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        stream.close()
        raise RuntimeError("Ovaj eksperiment već obrađuje drugi proces.") from exc
    try:
        yield
    finally:
        stream.close()


def pause(path):
    with connect(path) as db:
        set_meta(db, "status", "paused")


def run(path, *, max_trials=None):
    path = Path(path)
    with worker_lock(path), connect(path) as db:
        config = get_meta(db, "config")
        if get_meta(db,"status") in ("preparing","empty"):
            raise ValueError("Ulazni skup nije završen ili nema odgovarajućih snimaka. Napravite novi posao.")
        if config["rules"] != rules_version():
            raise ValueError("Kod pravila/profila se promenio. Kreirajte novi eksperiment; stari rezultati su sačuvani.")
        set_meta(db, "status", "running"); db.commit()
        completed = 0
        for row in db.execute("SELECT * FROM inputs WHERE id NOT IN (SELECT input_id FROM trials) ORDER BY split DESC,id").fetchall():
            if get_meta(db, "status") != "running": break
            started = time.perf_counter()
            frozen = json.loads(row["payload"])
            move, actions, baseline = frozen["move"], frozen["actions"], frozen["baseline"]
            state = observable(move)
            from .policy import support_reason
            if support_reason(state) is None:
                _,actions=legal_actions(move)
            results = {}
            for variant in VARIANTS:
                choice = choose_action(state, actions, variant, baseline)
                transition = step(move, choice.action) if choice.action and not choice.fallback else {
                    "supported": False, "reason": choice.reason}
                # A fallback baseline may still be measured, but is never evidence for a new policy.
                transition.pop("state", None)
                results[variant] = dict(action=choice.action, reason=choice.reason, fallback=choice.fallback,
                                        transition=transition, differs=action_key(choice.action or {}) != action_key(baseline))
            db.execute("INSERT INTO trials VALUES (?,?,?)", (row["id"], canonical(results), time.perf_counter()-started))
            db.commit()  # atomic: all policies for one board, no duplicated partial trials
            completed += 1
            if max_trials is not None and completed >= max_trials:
                set_meta(db, "status", "paused"); db.commit(); break
        left = db.execute("SELECT count(*) FROM inputs WHERE id NOT IN (SELECT input_id FROM trials)").fetchone()[0]
        if not left:
            set_meta(db, "status", "completed"); db.commit()
    write_report(path)
    return status(path)


def status(path):
    with connect(path) as db:
        total = db.execute("SELECT count(*) FROM inputs").fetchone()[0]
        done, seconds = db.execute("SELECT count(*),coalesce(sum(seconds),0) FROM trials").fetchone()
        groups = db.execute("SELECT count(DISTINCT identity_key) FROM inputs").fetchone()[0]
        completed_groups = db.execute("""SELECT count(*) FROM (SELECT identity_key FROM inputs
            GROUP BY identity_key HAVING sum(id NOT IN (SELECT input_id FROM trials))=0)""").fetchone()[0]
        simulations=sum(bool(v["transition"].get("supported")) for row in db.execute("SELECT payload FROM trials")
                        for v in json.loads(row[0]).values())
        return dict(status=get_meta(db,"status"), completed=done, total=total,
                    completed_combinations=completed_groups, combinations=groups,
                    policy_evaluations=done*len(VARIANTS), simulations=simulations,
                    seconds=round(seconds,3), eta_seconds=round(seconds/done*(total-done),1) if done>=5 else None)


def interval(values, seed):
    if not values: return None
    mean = statistics.mean(values)
    if len(values)<2: return dict(n=len(values), mean=mean, ci95=None)
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(600))
    return dict(n=len(values), mean=mean, ci95=[samples[15],samples[584]],
                method="paired bootstrap over unique boards; does not cover model error or within-match correlation")


def report(path):
    with connect(path) as db:
        config = get_meta(db, "config")
        rows = db.execute("SELECT i.*,t.payload AS result,t.seconds FROM inputs i JOIN trials t ON t.input_id=i.id").fetchall()
    groups, examples, excluded = {}, [], {}
    for row in rows:
        inp, out = json.loads(row["payload"]), json.loads(row["result"])
        ident = identity(inp["move"])
        group = groups.setdefault(row["identity_key"], dict(identity=ident, selection={}, validation={}))
        complete_case=all(not result["fallback"] and result["transition"].get("supported")
                          for result in out.values())
        for variant in VARIANTS[1:]:
            result, baseline = out[variant], out["existing"]
            if result["fallback"] or not result["transition"].get("supported") or not baseline["transition"].get("supported"):
                reason = result["reason"] if result["fallback"] else result["transition"].get("reason", baseline["transition"].get("reason"))
                excluded[reason] = excluded.get(reason,0)+1
                continue
            if not complete_case:
                excluded["paired_comparison_requires_all_variants_supported"] = excluded.get("paired_comparison_requires_all_variants_supported",0)+1
                continue
            delta = result["transition"]["value"]-baseline["transition"]["value"]
            group[row["split"]].setdefault(variant,[]).append(delta)
            if result["differs"]:
                examples.append(dict(source=row["source"], identity=ident, split=row["split"],
                                     profile=variant, board=inp["move"]["board"], special_board=inp["move"]["special_board"],
                                     baseline=baseline["action"], recommendation=result["action"],
                                     reason=result["reason"], prefix_delta_tiles=delta))
    for group in groups.values():
        for split in ("selection","validation"):
            group[split] = {k:interval(v,config["seed"]) for k,v in group[split].items()}
        available = group["selection"]
        group["selected_profile"] = max(available,key=lambda k:available[k]["mean"]) if available else None
        winner = group["selected_profile"]
        group["held_out_result"] = group["validation"].get(winner)
        group["verified_for_full_game"] = False
        group["interpretation"] = "Ograničena mera: uklonjene pločice pre nepoznate dopune; nije pobeda, završetak izazova ili ukupni skor."
    examples=sorted(examples,key=lambda e:-abs(e["prefix_delta_tiles"]))[:12]
    return dict(config=config, progress=status(path), groups=groups, differences=examples, exclusions=excluded,
                metric="deterministic_prefix_cleared_tiles", uncertainty="CI is conditional on this model and selected recorded boards; not full-game performance",
                examples_note="Largest absolute decision differences, illustrative only; profile selection uses all eligible selection boards",
                equipment_ranking="excluded: no faithful initial-equipment initializer",
                full_matches=0, refill_samples=0, independent_initial_boards=0)


def write_report(path):
    result = report(path)
    path = Path(path)
    path.with_suffix(".report.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines = ["# Strategy Lab — izveštaj", "", "Obim B: odluke iz sredine partije sa stvarno zabeleženom opremom.",
             "Mera je broj uklonjenih pločica do nepoznate dopune. To nisu poeni igre niti rezultat cele partije.",
             "Rangiranje alternativne opreme nije podržano; nema vernog inicijalizatora.", "", canonical(result["progress"]), ""]
    for group in result["groups"].values():
        lines += ["## " + canonical(group["identity"]), "", "Izbor: " + str(group["selected_profile"]),
                  "Završna provera na odvojenim tablama: " + canonical(group["held_out_result"]), ""]
    for example in result["differences"][:3]:
        lines += ["Različita odluka: " + example["source"],
                  "Koordinate (red, kolona), od nule: " + canonical(example["baseline"]) + " → " + canonical(example["recommendation"]), ""]
    path.with_suffix(".report.md").write_text("\n".join(lines),encoding="utf-8")
    return result
