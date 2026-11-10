"""Kalibracija VERSUS_HANDOVER_THREAT_*: koliko predvidjeni protivnicki odgovor
(opp_reply u candidates.json) zaista predvidja protivnicke poene u potezu posle
nase predaje table.

Za svaku versus predaju (remaining_moves == 1, odigran potez, kandidati nose
opp_reply) uzima sledeci nas run u istoj rundi (nas novi potez) i racuna
protivnikove poene = opponent_score(sledeci) - opponent_score(predaja).
Jedinice: k = stvarni nasi poeni / predvidjeni instant_score (iz uzastopnih
nasih poteza), pa je tezina w = nagib(poeni ~ opp_reply) / k.

    python tools/measure_handover_threat.py [OD_DATUMA] [IZLAZ.json]
"""
import json
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "Debug" / "runs"
SINCE = sys.argv[1] if len(sys.argv) > 1 else "2026-09-01"
OUT = sys.argv[2] if len(sys.argv) > 2 else None
REPLY = re.compile(r"opp_reply=([-0-9.]+) \(-([-0-9.]+)\)")
MAX_GAP_S = 150


def load(name):
    try:
        m = json.loads((RUNS / name / "move.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    if (m.get("strategy_context") or {}).get("mode") != "versus_2":
        return None
    return m


def ts(m):
    return datetime.fromisoformat(m["created_at"]).timestamp()


def score(m, key):
    v = (m.get("score_state") or {}).get(key)
    return v if isinstance(v, (int, float)) else None


def rnd(m):
    r = m.get("round_state") or {}
    return r.get("current"), r.get("total")


def same_cell(a, b):
    return list(a.get("start") or ()) == list(b.get("start") or ()) and \
        list(a.get("target") or ()) == list(b.get("target") or ())


def fit(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    syy = sum((y - my) ** 2 for y in ys)
    r = b * (sxx / syy) ** 0.5 if syy else 0.0
    return b, my - b * mx, r


names = sorted(n for n in os.listdir(RUNS) if n >= SINCE)
runs = []
for n in names:
    m = load(n)
    if m is not None and m.get("created_at"):
        runs.append((n, m))
print("versus runs:", len(runs))

cases, own = [], []
for (n, h), (n2, nx) in zip(runs, runs[1:]):
    # A versus round is our turn, then theirs; scores carry across rounds, so
    # our next turn is the first run of the next round.
    (cur, total), (cur2, total2) = rnd(h), rnd(nx)
    if ts(nx) - ts(h) > MAX_GAP_S or total != total2 or cur is None or cur2 is None:
        continue
    if cur2 not in (cur, cur + 1):
        continue
    if cur2 == cur + 1 and (h.get("turn_state") or {}).get("remaining_moves") != 1:
        continue
    hs, ns = h.get("turn_state") or {}, nx.get("turn_state") or {}
    best = h.get("best_move") or {}
    # Own-move scale: consecutive moves inside our own turn.
    if (cur2 == cur and h.get("selected_action") == "move" and best
            and ns.get("remaining_moves") is not None
            and hs.get("remaining_moves") is not None
            and ns["remaining_moves"] <= hs["remaining_moves"]
            and score(h, "opponent_score") == score(nx, "opponent_score")
            and score(h, "our_score") is not None and score(nx, "our_score") is not None):
        own.append((float(best.get("instant_score") or 0), score(nx, "our_score") - score(h, "our_score")))
    if hs.get("remaining_moves") != 1 or h.get("selected_action") != "move" or not best:
        continue
    # Our next turn must have started: the round moved on.
    if cur2 != cur + 1:
        continue
    o0, o1 = score(h, "opponent_score"), score(nx, "opponent_score")
    if o0 is None or o1 is None or o1 < o0:
        continue
    try:
        cands = json.loads((RUNS / n / "candidates.json").read_text(encoding="utf-8"))
    except Exception:
        continue
    replies, chosen = [], None
    for c in cands if isinstance(cands, list) else []:
        mt = REPLY.search(c.get("explanation") or "")
        if not mt:
            continue
        replies.append(float(mt.group(1)))
        if same_cell(c, best):
            chosen = float(mt.group(1))
    if chosen is None or len(replies) < 2:
        continue
    cases.append(dict(run=n, mode=h.get("mode"), reply=chosen, reply_min=min(replies),
                      reply_max=max(replies), opp=o1 - o0,
                      final_round=bool(hs.get("is_final_round")),
                      instant=float(best.get("instant_score") or 0)))

print("handover cases:", len(cases))
own = [(p, a) for p, a in own if p > 0 and a >= 0]
k = sum(a for _p, a in own) / sum(p for p, _a in own) if own else float("nan")
print(f"own moves: {len(own)}  k = actual/predicted points = {k:.2f}"
      f"  (median ratio {statistics.median(a / p for p, a in own):.2f})" if own else "own moves: 0")
if len(cases) < 10:
    sys.exit("premalo slucajeva")

xs = [c["reply"] for c in cases]
ys = [c["opp"] for c in cases]
b, a, r = fit(xs, ys)
print(f"\nopp_points = {a:.1f} + {b:.2f} * opp_reply   (r={r:.2f}, n={len(cases)})")
print(f"=> tezina w = b / k = {b / k:.2f}  (sada VERSUS_HANDOVER_THREAT_WEIGHT = 0.5)")

# Within-board gap: how much lower the reply could have been, and binned effect.
gaps = [c["reply"] - c["reply_min"] for c in cases]
print(f"\nchosen - min reply: median {statistics.median(gaps):.1f}, "
      f">=10: {sum(g >= 10 for g in gaps)}, >=30: {sum(g >= 30 for g in gaps)}")
print("\nbin opp_reply  n   mean opp pts  median")
edges = [0, 20, 40, 60, 80, 120, 10 ** 9]
for lo, hi in zip(edges, edges[1:]):
    sel = [c["opp"] for c in cases if lo <= c["reply"] < hi]
    if sel:
        print(f"{lo:>4}-{hi if hi < 10**9 else 'inf':<5} {len(sel):>4} {statistics.fmean(sel):>10.1f} "
              f"{statistics.median(sel):>8.1f}")

# Residual against board richness: same board, does the chosen reply relative
# to the board's own range still predict? (controls for rich vs poor boards)
rel = [(c["reply"] - c["reply_min"], c["opp"]) for c in cases if c["reply_max"] > c["reply_min"]]
mid = [c["reply_min"] for c in cases if c["reply_max"] > c["reply_min"]]
if len(rel) >= 10:
    # opp ~ a + b1*reply_min + b2*(reply - reply_min), solved by two-variable OLS.
    x1 = mid
    x2 = [g for g, _ in rel]
    y = [o for _, o in rel]
    m1, m2, my = statistics.fmean(x1), statistics.fmean(x2), statistics.fmean(y)
    s11 = sum((v - m1) ** 2 for v in x1)
    s22 = sum((v - m2) ** 2 for v in x2)
    s12 = sum((u - m1) * (v - m2) for u, v in zip(x1, x2))
    s1y = sum((u - m1) * (w - my) for u, w in zip(x1, y))
    s2y = sum((v - m2) * (w - my) for v, w in zip(x2, y))
    det = s11 * s22 - s12 ** 2
    if det:
        b1 = (s22 * s1y - s12 * s2y) / det
        b2 = (s11 * s2y - s12 * s1y) / det
        print(f"\nkontrola table (n={len(y)}): opp ~ {b1:.2f}*min_reply + {b2:.2f}*(izabrani - min)"
              f"  => w_unutar_table = {b2 / k:.2f}")

by_mode = {}
for c in cases:
    by_mode.setdefault(c["mode"], []).append(c)
print("\nmod                       n   b     r")
for mode, cs in sorted(by_mode.items(), key=lambda kv: -len(kv[1])):
    if len(cs) >= 15:
        bm, _am, rm = fit([c["reply"] for c in cs], [c["opp"] for c in cs])
        print(f"{str(mode)[:24]:<24} {len(cs):>4} {bm:>5.2f} {rm:>5.2f}")

if OUT:
    Path(OUT).write_text(json.dumps(dict(k=k, cases=cases), indent=1), encoding="utf-8")
