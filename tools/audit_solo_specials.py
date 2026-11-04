"""Sta je bot stvarno odigrao metlom (Sweep SE) i diskom (Brocco) u pravom
Solo Challenge-u, iz Debug/runs (move.json + intent.txt + candidates.json):
aktivacije po boji i gate-u, plave mete, stanje metra.

    python tools/audit_solo_specials.py [OD_DATUMA]   (podrazumevano 2026-08-29)
"""
import json, os, re, sys, collections
from pathlib import Path
ROOT = str(Path(__file__).resolve().parent.parent / "Debug" / "runs")
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-08-29"
COL = {1:"BLUE",2:"green",3:"yellow",4:"purple",5:"red",6:"orange"}
solo_runs = 0
rm_hist = collections.Counter()
brooms = []
discos = []
for name in sorted(os.listdir(ROOT)):
    if name < SINCE:
        continue
    d = os.path.join(ROOT, name)
    mp = os.path.join(d, "move.json")
    ip = os.path.join(d, "intent.txt")
    if not os.path.exists(mp) or not os.path.exists(ip):
        continue
    try:
        m = json.load(open(mp, encoding="utf-8"))
    except Exception:
        continue
    ctx = m.get("strategy_context") or {}
    if not ctx.get("solo_challenge"):
        continue
    if m.get("selected_action") != "move":
        continue
    solo_runs += 1
    ts = m.get("turn_state") or {}
    bs = m.get("booster_state") or {}
    rm = ts.get("remaining_moves")
    rm_hist[rm] += 1
    intent = open(ip, encoding="utf-8", errors="replace").read()
    gate = m.get("decision_gate")
    base = dict(run=name, gate=gate, cur=bs.get("current"), max=bs.get("maximum"), rm=rm)
    mb = re.search(r"Broom sweeps (\w+)", intent)
    if mb:
        blue = re.search(r"Expected total: .*?, (\d+) blue cells", intent)
        brooms.append(dict(base, colour=mb.group(1), blue=int(blue.group(1)) if blue else None))
    if "Disco Ball clears" in intent:
        colour = None
        try:
            c = json.load(open(os.path.join(d, "candidates.json"), encoding="utf-8"))
            for ev in (c[0].get("intent_events") or []):
                if ev.get("type") == "special_effect" and ev.get("special") == "disco_ball":
                    colour = COL.get(ev.get("color"), ev.get("color")); break
            blue = c[0].get("blue_cells")
        except Exception:
            blue = None
        discos.append(dict(base, colour=colour, blue=blue))
print("solo challenge move runs since", SINCE, ":", solo_runs)
print("remaining_moves histogram:", sorted(rm_hist.items(), key=lambda kv: (kv[0] is None, kv[0])))
print()
print("BROOM plays:", len(brooms))
print(" by colour:", collections.Counter(b["colour"] for b in brooms))
print(" by gate:", collections.Counter(b["gate"] for b in brooms))
print(" blue-target by rm:", collections.Counter(b["rm"] for b in brooms if b["colour"]=="blue"))
print(" blue-target with meter full (cur>=max):", sum(1 for b in brooms if b["colour"]=="blue" and b["cur"] is not None and b["max"] and b["cur"]>=b["max"]))
print(" blue-target with meter not full & rm>1:", [ (b["run"],b["gate"],b["cur"],b["max"],b["rm"],b["blue"]) for b in brooms if b["colour"]=="blue" and b["cur"] is not None and b["max"] and b["cur"]<b["max"] and (b["rm"] or 0)>1][:15])
print(" non-blue brooms expected blue cells hist:", collections.Counter(b["blue"] for b in brooms if b["colour"]!="blue"))
print()
print("DISCO plays:", len(discos))
print(" by colour:", collections.Counter(d["colour"] for d in discos))
print(" by gate:", collections.Counter(d["gate"] for d in discos))
print(" BLUE-target discos:", [ (d["run"],d["gate"],d["cur"],d["max"],d["rm"]) for d in discos if d["colour"]=="BLUE"])
print(" disco expected blue cells hist:", collections.Counter(d["blue"] for d in discos))
