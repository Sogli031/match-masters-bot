"""Replay snimljenih versus handover tabli (remaining_moves == 1): penal
protivnickog odgovora (VERSUS_HANDOVER_THREAT_*) iskljucen vs ukljucen --
koliko cesto se izbor menja, sta dajemo, sta protivnik gubi, dodatno vreme.

    python tools/replay_versus_handover.py [LIMIT]
"""
import json
from pathlib import Path
import os
import statistics
import sys
import time

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

RUNS = os.path.join(ROOT, "Debug", "runs")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60
cases = []
for n in sorted(os.listdir(RUNS), reverse=True):
    if n < "2026-08-25":
        break
    p = os.path.join(RUNS, n, "move.json")
    try:
        m = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if (m.get("strategy_context") or {}).get("mode") != "versus_2" or m.get("selected_action") != "move":
        continue
    ts = m.get("turn_state") or {}
    if ts.get("remaining_moves") != 1 or not m.get("board"):
        continue
    if (m.get("round_state") or {}).get("current") == (m.get("round_state") or {}).get("total"):
        pass
    cases.append((n, m))
    if len(cases) >= LIMIT:
        break
print("handover boards:", len(cases))

ctx = ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)
changed = 0
give_up = []
opp_loss = []
extra_ms = []
examples = []
for n, m in cases:
    bs = m.get("booster_state") or {}
    booster = ms.BoosterState(current=bs.get("current"), maximum=bs.get("maximum"), source="memory")
    rs = m.get("round_state") or {}
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=None,
                        is_final_round=False)
    kw = dict(mode=m.get("mode", "None"), allow_square_matches=m.get("allow_square_matches", False),
              explode_created_specials_immediately=m.get("specials_explode_immediately", False),
              score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()})
    ranked = ms.rank_moves(m["board"], m["special_board"], lookahead_candidates=12, lookahead_depth=1,
                           lookahead_beam_width=4, include_future_value=True, strategy_context=ctx, **kw)
    if not ranked:
        continue
    ms.VERSUS_HANDOVER_THREAT_ENABLED = False
    t0 = time.perf_counter()
    off = ms.prioritize_ranked_moves(ranked, booster_state=booster, turn_state=turn, strategy_context=ctx, **kw)
    t1 = time.perf_counter()
    ms.VERSUS_HANDOVER_THREAT_ENABLED = True
    on = ms.prioritize_ranked_moves(ranked, booster_state=booster, turn_state=turn, strategy_context=ctx, **kw)
    t2 = time.perf_counter()
    extra_ms.append((t2 - t1 - (t1 - t0)) * 1000)
    if not off or not on:
        continue
    a, b = off[0], on[0]
    caches = ({}, {}, {})
    ra = ms._versus_handover_opponent_reply_value(a, kw["mode"], kw["allow_square_matches"], kw["score_rally_values"], kw["explode_created_specials_immediately"], *caches)
    rb = ms._versus_handover_opponent_reply_value(b, kw["mode"], kw["allow_square_matches"], kw["score_rally_values"], kw["explode_created_specials_immediately"], *caches)
    if (a.candidate.start, a.candidate.target) != (b.candidate.start, b.candidate.target):
        changed += 1
        give_up.append(a.score - b.score)
        opp_loss.append(ra - rb)
        if len(examples) < 8:
            examples.append((n, round(a.score, 1), round(ra, 1), round(b.score, 1), round(rb, 1)))
print(f"pick changed on {changed}/{len(cases)} boards")
if give_up:
    print(f"  our score given up avg={statistics.mean(give_up):.1f} (max {max(give_up):.1f}); opponent best reply reduced avg={statistics.mean(opp_loss):.1f} (min {min(opp_loss):.1f})")
print(f"  extra compute per handover move avg={statistics.mean(extra_ms):.0f} ms, max={max(extra_ms):.0f} ms")
for e in examples:
    print("   ", e)
