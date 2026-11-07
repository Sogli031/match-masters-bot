"""Rekonstruise solo meceve (Solo Challenge / Showdown / Party / Master League)
iz sazetog toka (scan_solo_snapshots.py): skor, dostignuti solo targeti,
aktivacije, extra potezi, pun metar na kraju, po familiji i modu.

    python tools/solo_matches.py SAZETAK.jsonl
"""
import collections
import json
import statistics
import sys
from datetime import datetime

SRC = sys.argv[1]
GAP_SECONDS = 180


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def family(r):
    ef = r["ef"]
    if r["pvp"] == 1 and r.get("solo_targets"):
        return "solo_challenge_energy" if ef.get("soloUnusedMovesEnergyWorth") else "solo_challenge"
    if r["pvp"] == 2:
        rt = ef.get("rumbleType")
        return {1: "master_league", 2: "showdown", 3: "party"}.get(rt, f"rumble{rt}")
    return f"pvp{r['pvp']}"


recs = [json.loads(l) for l in open(SRC, encoding="utf-8")]
recs = [r for r in recs if r.get("t")]
recs.sort(key=lambda r: r["t"])
matches, cur, prev = [], None, None
for r in recs:
    me = r["me"]
    new = cur is None
    if not new:
        if ts(r["t"]) - ts(prev["t"]) > GAP_SECONDS or r["rules_id"] != prev["rules_id"]:
            new = True
        elif (me["score"] or 0) < (prev["me"]["score"] or 0) - 5 and (me["score"] or 0) <= 5:
            new = True
        elif (r["moves"] or 0) > (prev["moves"] or 0) + 3 and (me["score"] or 0) <= (prev["me"]["score"] or 0) and r["turn"] == prev["turn"]:
            new = True
    if new:
        cur = []
        matches.append(cur)
    cur.append(r)
    prev = r

rows = []
for m in matches:
    if len(m) < 5:
        continue
    f = family(m[0])
    scores = [(r["me"]["score"] or 0) for r in m]
    final = max(scores)
    if final <= 0:
        continue
    targets = m[0].get("solo_targets") or []
    reached = sum(1 for t in targets if final >= t)
    mpt = m[0]["mpt"] or 0
    tpg = m[0]["tpg"] or 1
    # activations
    acts = 0
    prev_e = None
    for r in m:
        e = r["me"]["energy"]
        mx = r["me"]["energy_to_ability"] or 7
        if prev_e is not None and prev_e >= mx and (e or 0) < prev_e:
            acts += 1
        prev_e = e
    # moves actually played: count frames where moves decreased
    played = 0
    prev_mv = None
    extras = 0
    for r in m:
        mv = r.get("moves")
        if prev_mv is not None and mv is not None:
            if mv < prev_mv:
                played += prev_mv - mv
            elif mv > prev_mv and r["turn"] == prevturn:
                extras += mv - prev_mv
        prev_mv = mv
        prevturn = r["turn"]
    last = m[-1]
    end_energy = last["me"]["energy"]
    end_full = (end_energy or 0) >= (last["me"]["energy_to_ability"] or 7)
    # clock usage per turn (rumble modes): remaining_time at first and last frame with moves>0
    times = [r.get("time") for r in m if r.get("time") is not None]
    t_min = min(times) if times else None
    # frames at score plateau near end: moves left at the end
    moves_left_end = last.get("moves")
    rows.append(dict(start=m[0]["t"][:19], fam=f, title=m[0]["title"], tpt=m[0]["tpt"], mpt=mpt, tpg=tpg,
                     targets=targets, final=final, reached=reached, ntargets=len(targets), acts=acts, played=played,
                     extras=extras, end_energy=end_energy, end_full=end_full, t_min=t_min, moves_left=moves_left_end,
                     frames=len(m), ability=m[0]["me"].get("special_ability_type"), gs=last.get("gs")))

print("matches:", len(rows))
by = collections.defaultdict(list)
for r in rows:
    by[r["fam"]].append(r)


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


for fam, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    print(f"\n=== {fam}: matches={len(rs)} final score avg={mean([r['final'] for r in rs])} activations avg={mean([r['acts'] for r in rs])} "
          f"end full meter={sum(1 for r in rs if r['end_full'])} end energy avg={mean([r['end_energy'] for r in rs])} "
          f"extras avg={mean([r['extras'] for r in rs])} moves played avg={mean([r['played'] for r in rs])} (mpt avg {mean([r['mpt'] for r in rs])})")
    if fam.startswith("solo_challenge"):
        c = collections.Counter((r["ntargets"], r["reached"]) for r in rs)
        print("   targets reached (ntargets, reached):", sorted(c.items()))
        bym = collections.defaultdict(list)
        for r in rs:
            bym[r["title"]].append(r)
        for title, ms in sorted(bym.items(), key=lambda kv: -len(kv[1])):
            miss = [r for r in ms if r["reached"] < r["ntargets"]]
            print(f"   {str(title):22s} n={len(ms):2d} top target reached {len(ms)-len(miss)}/{len(ms)}; misses: " +
                  ", ".join(f"{r['final']}/{r['targets'][-1]}(moves_left={r['moves_left']},acts={r['acts']})" for r in miss[:6]))
    else:
        bym = collections.defaultdict(list)
        for r in rs:
            bym[r["title"]].append(r)
        for title, ms in sorted(bym.items(), key=lambda kv: -len(kv[1])):
            print(f"   {str(title):22s} n={len(ms):2d} score avg={mean([r['final'] for r in ms]):8} acts={mean([r['acts'] for r in ms])} extras={mean([r['extras'] for r in ms])} end_full={sum(1 for r in ms if r['end_full'])} min clock left={mean([r['t_min'] for r in ms])}")
json.dump(rows, open(SRC + ".matches.json", "w"), indent=0)
