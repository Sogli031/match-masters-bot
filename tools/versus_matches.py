"""Rekonstruise versus meceve iz sazetog snapshot toka (scan_versus_snapshots.py):
pobednik iz engine game_state (2..7), W/L po modu, busteru protivnika i nasem,
aktivacije, metar na kraju, lista izgubljenih i tesnih meceva.

    python tools/versus_matches.py SAZETAK.jsonl [LOCAL_PLAYER_TYPE=0]
"""
import collections
import json
import statistics
import sys
from datetime import datetime, timezone

SRC = sys.argv[1]
LOCAL = int(sys.argv[2]) if len(sys.argv) > 2 else 0
GAP_SECONDS = 240


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


recs = []
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    if not r.get("t"):
        continue
    recs.append(r)
recs.sort(key=lambda r: r["t"])
print("versus snapshots:", len(recs))

# --- segment into matches ---------------------------------------------------
matches = []
cur = None
prev = None
for r in recs:
    me = next((p for p in r["players"] if p.get("player_type") == LOCAL), None)
    opp = next((p for p in r["players"] if p.get("player_type") != LOCAL), None)
    if me is None or opp is None:
        continue
    r["me"], r["op"] = me, opp
    new = cur is None
    if not new:
        if ts(r["t"]) - ts(prev["t"]) > GAP_SECONDS:
            new = True
        elif r["rules_id"] != prev["rules_id"]:
            new = True
        elif (me["score"] or 0) + (opp["score"] or 0) < (prev["me"]["score"] or 0) + (prev["op"]["score"] or 0) - 5 and (me["score"] or 0) <= 5 and (opp["score"] or 0) <= 5:
            new = True
        elif (r["round"] or 0) < (prev["round"] or 0) and (me["score"] or 0) < (prev["me"]["score"] or 0):
            new = True
    if new:
        cur = []
        matches.append(cur)
    cur.append(r)
    prev = r

rows = []
for m in matches:
    last = m[-1]
    first = m[0]
    if len(m) < 6:
        continue
    # final scores: the maximum seen (post-match frames may zero things out)
    my_final = max((r["me"]["score"] or 0) for r in m)
    op_final = max((r["op"]["score"] or 0) for r in m)
    if my_final == 0 and op_final == 0:
        continue
    my_rw = max((r["me"]["rounds_won"] or 0) for r in m)
    op_rw = max((r["op"]["rounds_won"] or 0) for r in m)
    rounds_total = last.get("rounds_total") or first.get("rounds_total")
    max_round = max((r["round"] or 0) for r in m)
    gs_seen = [r.get("gs") for r in m if r.get("gs") in (2, 3, 4, 5, 6, 7)]
    winner_index = None
    if gs_seen:
        winner_index = 0 if gs_seen[-1] in (2, 4, 6) else 1
    complete = bool(gs_seen) or (rounds_total is not None and max_round + 1 >= rounds_total)
    # our activations: energy drops from >= max to a lower value
    acts = 0
    full_turn_ends = 0
    my_turn_frames = [r for r in m if r["me"].get("is_my_turn")]
    prev_e = None
    for r in m:
        e = r["me"]["energy"]
        mx = r["me"]["energy_to_ability"] or 7
        if prev_e is not None and prev_e >= mx and (e or 0) < prev_e:
            acts += 1
        prev_e = e
    op_acts = 0
    prev_e = None
    for r in m:
        e = r["op"]["energy"]
        mx = r["op"]["energy_to_ability"] or 7
        if prev_e is not None and prev_e >= mx and (e or 0) < prev_e:
            op_acts += 1
        prev_e = e
    end_full = (last["me"]["energy"] or 0) >= (last["me"]["energy_to_ability"] or 7)
    end_energy = last["me"]["energy"]
    low_time_my_moves = sum(1 for r in my_turn_frames if (r.get("time") or 99) < 5 and (r.get("moves") or 0) > 0)
    first_mover = "me" if (first["cpi"] == first["me"]["index"]) else "opp"
    rows.append(dict(
        start=first["t"][:19], title=first.get("title"), tpt=first.get("tpt"), mpt=first.get("mpt"),
        rounds=rounds_total, max_round=max_round, complete=complete, frames=len(m),
        my=my_final, op=op_final, diff=my_final - op_final, my_rw=my_rw, op_rw=op_rw,
        my_ab=first["me"].get("special_ability_type"), op_ab=first["op"].get("special_ability_type"),
        acts=acts, op_acts=op_acts, end_full=end_full, end_energy=end_energy,
        low_time_moves=low_time_my_moves, first=first_mover, gs_last=last.get("gs"),
        result=(("W" if winner_index == first["me"]["index"] else "L") if winner_index is not None
                else ("W" if my_final > op_final else ("L" if my_final < op_final else "T"))),
        gs_final=gs_seen[-1] if gs_seen else None,
    ))

print("matches:", len(rows), "complete:", sum(1 for r in rows if r["complete"]))
comp = [r for r in rows if r["complete"]]
wl = collections.Counter(r["result"] for r in comp)
print("W/L/T (complete):", dict(wl))
print("\nby mode:")
bym = collections.defaultdict(collections.Counter)
for r in comp:
    bym[r["title"]][r["result"]] += 1
for k, v in sorted(bym.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  {str(k):28s} {dict(v)}")
print("\nby opponent booster:")
byo = collections.defaultdict(collections.Counter)
for r in comp:
    byo[r["op_ab"]][r["result"]] += 1
for k, v in sorted(byo.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  opp ability {k}: {dict(v)}")
print("\nby our booster:")
byb = collections.defaultdict(collections.Counter)
for r in comp:
    byb[r["my_ab"]][r["result"]] += 1
for k, v in sorted(byb.items(), key=lambda kv: -sum(kv[1].values())):
    print(f"  my ability {k}: {dict(v)}")
print("\nby first mover:")
byf = collections.defaultdict(collections.Counter)
for r in comp:
    byf[r["first"]][r["result"]] += 1
print(" ", {k: dict(v) for k, v in byf.items()})


def avg(rs, key):
    vals = [r[key] for r in rs if r[key] is not None]
    return round(statistics.mean(vals), 2) if vals else None


for res in ("W", "L"):
    rs = [r for r in comp if r["result"] == res]
    if not rs:
        continue
    print(f"\n{res}: n={len(rs)} my score avg={avg(rs,'my')} opp avg={avg(rs,'op')} margin avg={avg(rs,'diff')} "
          f"my activations={avg(rs,'acts')} opp activations={avg(rs,'op_acts')} ended with full meter={sum(1 for r in rs if r['end_full'])} "
          f"end energy avg={avg(rs,'end_energy')} low-time moves avg={avg(rs,'low_time_moves')}")

print("\nLOST matches (complete):")
for r in sorted(comp, key=lambda r: r["start"]):
    if r["result"] == "L":
        print(f"  {r['start']} {str(r['title']):22s} tpt={r['tpt']} rounds={r['rounds']} {r['my']}:{r['op']} ({r['diff']:+d}) "
              f"my_ab={r['my_ab']} op_ab={r['op_ab']} acts={r['acts']}/{r['op_acts']} end_energy={r['end_energy']} first={r['first']} lowtime={r['low_time_moves']} rw={r['my_rw']}-{r['op_rw']}")
print("\nclose WINS (margin<60):")
for r in sorted(comp, key=lambda r: r["start"]):
    if r["result"] == "W" and r["diff"] < 60:
        print(f"  {r['start']} {str(r['title']):22s} {r['my']}:{r['op']} ({r['diff']:+d}) acts={r['acts']}/{r['op_acts']} end_energy={r['end_energy']}")
json.dump(rows, open(SRC + ".matches.json", "w"), indent=1)
