"""Tok versus meceva po turama (poeni po turi, aktivacije, pun metar
nepotrosen, sat) iz sazetog snapshot toka; izgubljeni mecevi detaljno.

    python tools/versus_timeline.py SAZETAK.jsonl
"""
import collections
import json
import statistics
import sys
from datetime import datetime

SRC = sys.argv[1]
LOCAL = 0
GAP_SECONDS = 240
NAMES = {19: "UFOBeam", 25: "HighVoltage", 26: "AllAboard", 27: "DoctorColor", 28: "CrazyClovers", 31: "JeevesBot", 32: "QueenCobra", 33: "ElMagneto", 34: "MrAppleberry", 35: "WoollyWorkout", 37: "ColonelMcQuack", 38: "Cupid", 41: "BillieBoom", 44: "Brocco", 46: "AllAboardSE", 48: "ElMagnetoSE", 49: "UFOBeamSE", 52: "FoxyRoxySE", 54: "CheckmateCharles", 59: "MixyMeow", 60: "JellySE", 61: "SweepItSE", 63: "FroggyFu", 8: "LaserBeam", 14: "CreateSpecials", 15: "Painter"}


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


recs = [json.loads(l) for l in open(SRC, encoding="utf-8")]
recs = [r for r in recs if r.get("t")]
recs.sort(key=lambda r: r["t"])
matches, cur, prev = [], None, None
for r in recs:
    me = next((p for p in r["players"] if p.get("player_type") == LOCAL), None)
    opp = next((p for p in r["players"] if p.get("player_type") != LOCAL), None)
    if me is None or opp is None:
        continue
    r["me"], r["op"] = me, opp
    new = cur is None
    if not new:
        if ts(r["t"]) - ts(prev["t"]) > GAP_SECONDS or r["rules_id"] != prev["rules_id"]:
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

summary = []
for m in matches:
    if len(m) < 6:
        continue
    gs_seen = [r.get("gs") for r in m if r.get("gs") in (2, 3, 4, 5, 6, 7)]
    if not gs_seen:
        continue
    winner = 0 if gs_seen[-1] in (2, 4, 6) else 1
    result = "W" if winner == m[0]["me"]["index"] else "L"
    # turns: consecutive frames with the same (round, turn, cpi)
    turns = []
    for r in m:
        key = (r.get("round"), r.get("turn"), r.get("cpi"))
        if not turns or turns[-1]["key"] != key:
            turns.append({"key": key, "frames": []})
        turns[-1]["frames"].append(r)
    rows = []
    for t in turns:
        f0, f1 = t["frames"][0], t["frames"][-1]
        who = "me" if t["key"][2] == f0["me"]["index"] else "op"
        my_gain = (f1["me"]["score"] or 0) - (f0["me"]["score"] or 0)
        op_gain = (f1["op"]["score"] or 0) - (f0["op"]["score"] or 0)
        e0, e1 = f0["me"]["energy"], f1["me"]["energy"]
        mx = f0["me"]["energy_to_ability"] or 7
        act = any((a["me"]["energy"] or 0) >= mx and (b["me"]["energy"] or 0) < (a["me"]["energy"] or 0) for a, b in zip(t["frames"], t["frames"][1:]))
        op_mx = f0["op"]["energy_to_ability"] or 7
        op_act = any((a["op"]["energy"] or 0) >= op_mx and (b["op"]["energy"] or 0) < (a["op"]["energy"] or 0) for a, b in zip(t["frames"], t["frames"][1:]))
        full_unspent = who == "me" and (e1 or 0) >= mx and not act
        moves_seen = sorted({r.get("moves") for r in t["frames"] if r.get("moves") is not None}, reverse=True)
        times = [r.get("time") for r in t["frames"] if r.get("time") is not None]
        rows.append(dict(round=t["key"][0], turn=t["key"][1], who=who, my_gain=my_gain, op_gain=op_gain, e0=e0, e1=e1, act=act, op_act=op_act,
                         full_unspent=full_unspent, moves=moves_seen[:6], t0=times[0] if times else None, t1=times[-1] if times else None, frames=len(t["frames"])))
    summary.append(dict(start=m[0]["t"][:19], title=m[0].get("title"), tpt=m[0].get("tpt"), rounds=m[0].get("rounds_total"), result=result,
                        my_ab=NAMES.get(m[0]["me"]["special_ability_type"], m[0]["me"]["special_ability_type"]),
                        op_ab=NAMES.get(m[0]["op"]["special_ability_type"], m[0]["op"]["special_ability_type"]),
                        my=max((r["me"]["score"] or 0) for r in m), op=max((r["op"]["score"] or 0) for r in m), turns=rows))

# aggregate per result
for res in ("W", "L"):
    ms = [s for s in summary if s["result"] == res]
    my_turns = [t for s in ms for t in s["turns"] if t["who"] == "me"]
    op_turns = [t for s in ms for t in s["turns"] if t["who"] == "op"]
    print(f"\n=== {res}: matches={len(ms)} my turns={len(my_turns)} opp turns={len(op_turns)}")
    print(f"  my points/turn avg={statistics.mean(t['my_gain'] for t in my_turns):.0f} median={statistics.median(t['my_gain'] for t in my_turns):.0f}; "
          f"opp points/turn avg={statistics.mean(t['op_gain'] for t in op_turns):.0f} median={statistics.median(t['op_gain'] for t in op_turns):.0f}")
    print(f"  my activation turns: {sum(1 for t in my_turns if t['act'])} (avg gain {statistics.mean([t['my_gain'] for t in my_turns if t['act']] or [0]):.0f}); "
          f"opp activation turns: {sum(1 for t in op_turns if t['op_act'])} (avg gain {statistics.mean([t['op_gain'] for t in op_turns if t['op_act']] or [0]):.0f})")
    print(f"  my turns ended with FULL meter unspent: {sum(1 for t in my_turns if t['full_unspent'])} of {len(my_turns)}")
    print(f"  my turns where time hit 0 (t1==0): {sum(1 for t in my_turns if t['t1'] == 0)}; turns starting with <6s: {sum(1 for t in my_turns if t['t0'] is not None and t['t0'] < 6)}")
    print(f"  my no-activation turn gain avg={statistics.mean([t['my_gain'] for t in my_turns if not t['act']] or [0]):.0f}; opp no-activation avg={statistics.mean([t['op_gain'] for t in op_turns if not t['op_act']] or [0]):.0f}")

print("\n=== LOST matches, turn by turn")
for s in summary:
    if s["result"] != "L":
        continue
    print(f"\n{s['start']} {s['title']} tpt={s['tpt']} rounds={s['rounds']} {s['my']}:{s['op']} me={s['my_ab']} opp={s['op_ab']}")
    for t in s["turns"]:
        gain = t["my_gain"] if t["who"] == "me" else t["op_gain"]
        flag = ("ACT " if (t["act"] if t["who"] == "me" else t["op_act"]) else "    ") + ("FULL-UNSPENT" if t["full_unspent"] else "")
        print(f"   r{t['round']} t{t['turn']} {t['who']:2s} +{gain:5d}  e:{t['e0']}->{t['e1']}  moves:{t['moves']}  time:{t['t0']}->{t['t1']} {flag}")
json.dump(summary, open(SRC + ".timeline.json", "w"), indent=0)
