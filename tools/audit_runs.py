"""Siroki audit snimljenih runova (Debug/runs): predvidjeno vs izmereno.

Po kontekstu (solo_race / solo_challenge / versus_2), vrsti poteza i busteru:
  A. punjenje metra: predicted_booster_charge_gained vs observed
  B. extra potezi: obecan pa izgubljen / neobecan pa zadrzan, po gate-u
  C. odigran potez a tabla nepromenjena (progutan swipe)
  D. metar pun a odigran potez; aktivacije sa nepunim metrom
  E. Solo Challenge: boje koje biraju lotus / jelly / mixy / High Voltage
  F. potez odigran a 0 poena
  G. ishodi Extra move dugmeta

    python tools/audit_runs.py [OD_DATUMA]      (podrazumevano 2026-08-25)

Ispis je dugacak -- preusmeri u fajl. ID bustera se cita iz ufo.ability_type
ili iz "specialAbilityType=NN" u mixy_meow/ufo.reason.
"""
import collections
import json
import os
from pathlib import Path
import re
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
RUNS = os.path.join(ROOT, "Debug", "runs")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-08-25"

names_by_id = {}
src = open(os.path.join(ROOT, "memory_gui.py"), encoding="utf-8").read()
_block = ""
for _m in re.finditer(r"SPECIAL_ABILITY_NAMES = \{", src):
    _cand = src[_m.start():src.find("}", _m.start())]
    if '"BroccoBoogie"' in _cand:
        _block = _cand
        break
for k, v in re.findall(r"(\d+): \"([A-Za-z0-9]+)\"", _block):
    names_by_id[int(k)] = v


def booster_name(i):
    return f"{names_by_id.get(i, '?')}({i})"


def ctx_label(sc):
    mode = sc.get("mode")
    if mode == "solo_6":
        return "solo_challenge" if sc.get("solo_challenge") else "solo_race"
    return mode or "unknown"


def move_kind(best):
    evs = (best or {}).get("intent_events") or []
    kinds = set()
    for e in evs:
        t = e.get("type")
        if t == "sweep_se_activation":
            kinds.add("sweep")
        elif t == "special_effect" and e.get("special") == "disco_ball":
            kinds.add("disco")
        elif t in ("froggy_lotus_collect", "froggy_lotus_activation"):
            kinds.add("lotus")
        elif t and "jelly" in t:
            kinds.add("jelly")
        elif t and "mixy" in t:
            kinds.add("mixy")
        elif t and "cleo" in t:
            kinds.add("cleo")
        elif t == "special_activation":
            kinds.add("special:" + str(e.get("special")))
        elif t == "uncertain_refill_boundary":
            kinds.add("uncertain")
    if (best or {}).get("froggy_lotus_collected"):
        kinds.add("lotus")
    if (best or {}).get("jelly_converted_tiles"):
        kinds.add("jelly")
    if (best or {}).get("mixy_converted_tiles"):
        kinds.add("mixy")
    if not kinds:
        return "plain"
    return "+".join(sorted(kinds))


def ability_of(mv):
    a = (mv.get("ufo") or {}).get("ability_type")
    if a is not None:
        return a
    for key in ("mixy_meow", "ufo"):
        reason = str((mv.get(key) or {}).get("reason") or "")
        mm = re.search(r"specialAbilityType=(\d+)", reason)
        if mm:
            return int(mm.group(1))
    return None


rows = []
event_types = collections.Counter()
for name in sorted(os.listdir(RUNS)):
    if name < SINCE:
        continue
    d = os.path.join(RUNS, name)
    mp = os.path.join(d, "move.json")
    if not os.path.exists(mp):
        continue
    try:
        mv = json.load(open(mp, encoding="utf-8"))
    except Exception:
        continue
    od = None
    op = os.path.join(d, "observed_delta.json")
    if os.path.exists(op):
        try:
            od = json.load(open(op, encoding="utf-8"))
        except Exception:
            od = None
    best = mv.get("best_move") or {}
    for e in best.get("intent_events") or []:
        event_types[e.get("type")] += 1
    sc = mv.get("strategy_context") or {}
    rows.append(dict(
        run=name, ability=ability_of(mv),
        ctx=ctx_label(sc), gmode=mv.get("mode"), action=mv.get("action"),
        selected=mv.get("selected_action"), gate=mv.get("decision_gate"),
        kind=move_kind(best), best=best,
        booster=mv.get("booster_state") or {}, turn=mv.get("turn_state") or {},
        pc=(od or {}).get("prediction_check") or {}, sd=(od or {}).get("state_delta") or {},
        score=(od or {}).get("score_delta") or {}, bd=(od or {}).get("board_delta") or {},
        hv=mv.get("high_voltage_target"), will_activate=mv.get("will_activate_booster"),
        bdet=mv.get("booster_detection") or {},
    ))
print("runs:", len(rows), "since", SINCE)
print("intent event types:", event_types.most_common())

# ---- A. charge prediction ----
print("\n=== A. charge: predicted vs observed gained (moves only, no spend in between)")
by = collections.defaultdict(lambda: [0, 0, 0.0, []])  # n, mism, abs err, examples
for r in rows:
    if r["selected"] != "move":
        continue
    pc = r["pc"]
    p, o = pc.get("predicted_booster_charge_gained"), pc.get("observed_booster_charge_gained")
    if p is None or o is None or pc.get("charge_spent_between"):
        continue
    key = (r["ctx"], r["kind"])
    b = by[key]
    b[0] += 1
    err = float(o) - float(p)
    if abs(err) >= 1:
        b[1] += 1
        b[2] += abs(err)
        if len(b[3]) < 3:
            b[3].append((r["run"], p, o, r["gate"]))
for key, (n, mism, ae, ex) in sorted(by.items(), key=lambda kv: -kv[1][1]):
    if n >= 5:
        print(f"  {key[0]:15s} {key[1]:28s} n={n:5d} mismatch>=1: {mism:4d} ({100*mism/n:4.0f}%) mean|err| among mismatches={ae/max(mism,1):.1f}  e.g. {ex[:2]}")

# per booster ability
print("\n--- charge mismatch by booster ability")
byb = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
for r in rows:
    pc = r["pc"]
    p, o = pc.get("predicted_booster_charge_gained"), pc.get("observed_booster_charge_gained")
    if r["selected"] != "move" or p is None or o is None or pc.get("charge_spent_between"):
        continue
    b = byb[r["ability"]]
    b[0] += 1
    b[1] += abs(float(o) - float(p)) >= 1
    b[2] += float(o) - float(p)
    b[3] += (float(o) - float(p)) if abs(float(o) - float(p)) >= 1 else 0
for a, (n, mism, signed, signed_m) in sorted(byb.items(), key=lambda kv: -kv[1][0]):
    print(f"  {booster_name(a):22s} n={n:5d} mismatch={mism:4d} ({100*mism/n:4.0f}%) signed err sum={signed:+.0f} (obs-pred)")

# ---- B. extra prediction ----
print("\n=== B. extra moves: predicted >=1 but turn NOT kept / predicted 0 but kept")
byx = collections.defaultdict(lambda: [0, 0, 0, 0, []])
for r in rows:
    if r["selected"] != "move":
        continue
    pc, sd = r["pc"], r["sd"]
    if not sd.get("turn_measured"):
        continue
    kept = pc.get("observed_kept_the_turn")
    if kept is None:
        continue
    p = float(pc.get("predicted_extra_moves") or 0)
    key = (r["ctx"], r["kind"], r["gate"])
    b = byx[key]
    b[0] += 1
    if p >= 1 and not kept:
        b[1] += 1
        if len(b[4]) < 3:
            b[4].append(r["run"])
    if p < 1 and kept:
        b[2] += 1
    if p >= 1 and kept:
        b[3] += 1
tot = collections.defaultdict(lambda: [0, 0, 0])
for key, (n, broken, missed, ok, ex) in sorted(byx.items(), key=lambda kv: -kv[1][1]):
    t = tot[(key[0], key[2])]
    t[0] += n; t[1] += broken; t[2] += missed
    if broken >= 2 or (n >= 20 and missed >= 5):
        print(f"  {key[0]:15s} {key[1]:28s} {str(key[2]):32s} n={n:4d} promised-but-lost={broken:3d} unpromised-kept={missed:3d} ok={ok:3d} e.g. {ex[:2]}")
print("--- totals by ctx/gate")
for (c, g), (n, broken, missed) in sorted(tot.items(), key=lambda kv: -kv[1][1]):
    if n >= 10:
        print(f"  {c:15s} {str(g):32s} n={n:5d} promised-but-lost={broken:4d} ({100*broken/n:3.0f}%) unpromised-kept={missed:4d}")

# ---- C. board unchanged after a played move ----
print("\n=== C. played move but board did not change (swipe swallowed?)")
byc = collections.defaultdict(lambda: [0, 0, []])
for r in rows:
    if r["selected"] != "move" or not r["bd"]:
        continue
    key = (r["ctx"], r["kind"])
    b = byc[key]
    b[0] += 1
    if r["bd"].get("changed_count") == 0:
        b[1] += 1
        if len(b[2]) < 3:
            b[2].append(r["run"])
for key, (n, z, ex) in sorted(byc.items(), key=lambda kv: -kv[1][1]):
    if z:
        print(f"  {key[0]:15s} {key[1]:28s} n={n:5d} unchanged={z:4d} ({100*z/n:3.0f}%) e.g. {ex}")

# ---- D. booster activation timing ----
print("\n=== D. booster ready but a move was played instead (by ctx / gate)")
byd = collections.Counter(); byd_n = collections.Counter()
for r in rows:
    before = (r["sd"].get("before") or {})
    ready = before.get("booster_ready")
    if ready is None:
        b = r["booster"]
        ready = b.get("current") is not None and b.get("maximum") and b["current"] >= b["maximum"]
    if not ready:
        continue
    byd_n[r["ctx"]] += 1
    if r["selected"] == "move":
        byd[(r["ctx"], r["action"], r["gate"])] += 1
for c in byd_n:
    print(f"  {c}: runs with meter full: {byd_n[c]}")
for (c, a, g), n in byd.most_common(25):
    print(f"    {c:15s} action={a:15s} gate={str(g):40s} {n}")
print("--- activations with meter NOT full")
cnt = collections.Counter()
for r in rows:
    if r["selected"] == "activate_booster":
        b = r["booster"]
        full = b.get("current") is not None and b.get("maximum") and b["current"] >= b["maximum"]
        cnt[(r["ctx"], booster_name(r["ability"]), "full" if full else f"{b.get('current')}/{b.get('maximum')}", r["gate"])] += 1
for k, n in cnt.most_common(30):
    if k[2] != "full":
        print(f"    {k} {n}")

# ---- E. solo challenge blue-first leaks for the other boosters ----
print("\n=== E. solo challenge: colour choices of the colour-picking boosters")
for r in rows:
    pass
col = {1: "BLUE", 2: "green", 3: "yellow", 4: "purple", 5: "red", 6: "orange"}
hv = collections.Counter(); lot = collections.Counter(); jel = collections.Counter(); mix = collections.Counter()
for r in rows:
    if r["ctx"] != "solo_challenge":
        continue
    b = r["best"]
    if r["hv"] and r["selected"] != "none":
        hv[(col.get(r["hv"].get("color"), r["hv"].get("color")), r["selected"])] += 1
    if b.get("froggy_lotus_collected"):
        lot[col.get(b.get("froggy_lotus_color"), b.get("froggy_lotus_color"))] += 1
    if b.get("jelly_converted_tiles"):
        jel[col.get(b.get("jelly_converted_color"), b.get("jelly_converted_color"))] += 1
    if b.get("mixy_converted_tiles"):
        mix[col.get(b.get("mixy_code_color"), b.get("mixy_code_color"))] += 1
print("  high voltage targets:", hv.most_common())
print("  lotus collect colours:", lot.most_common())
print("  jelly conversion colours:", jel.most_common())
print("  mixy code colours:", mix.most_common())

# ---- F. score: points gained 0 after a played move ----
print("\n=== F. played move, score readable, 0 points gained")
byf = collections.defaultdict(lambda: [0, 0, []])
for r in rows:
    s = r["score"]
    if r["selected"] != "move" or not s.get("confirmed"):
        continue
    g = s.get("our_points_gained")
    if g is None:
        continue
    b = byf[(r["ctx"], r["gmode"])]
    b[0] += 1
    if g <= 0:
        b[1] += 1
        if len(b[2]) < 2:
            b[2].append(r["run"])
for key, (n, z, ex) in sorted(byf.items(), key=lambda kv: -kv[1][1]):
    if z >= 3:
        print(f"  {key[0]:15s} {str(key[1]):30s} n={n:5d} zero={z:4d} ({100*z/n:3.0f}%) e.g. {ex}")

# ---- G. extra-move button outcomes ----
print("\n=== G. Extra move button presses")
g = collections.Counter((r["ctx"], r["selected"], r["gate"]) for r in rows if r["action"] == "extra_move")
for k, n in g.most_common(15):
    print("  ", k, n)
