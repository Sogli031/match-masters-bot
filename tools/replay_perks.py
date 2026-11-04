"""Replay snimljenih tabli (Debug/runs) na kojima je bio opremljen zadati perk:
da li ga nova procena (PERK_RANDOM_EXPECTED_CHARGE) aktivira, kada i sa kojim
ocekivanim dobitkom punjenja, u poredjenju sa starom (donji kvartil sopstvenog
punjenja perka).

    python tools/replay_perks.py [perk1,perk2,...] [LIMIT]
    npr. python tools/replay_perks.py star_maker,mini_wand,checkerboard 160
"""
import collections
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

RUNS = os.path.join(ROOT, "Debug", "runs")
PERKS = set(sys.argv[1].split(",")) if len(sys.argv) > 1 else {"star_maker", "mini_wand", "checkerboard", "mini_mastermind"}
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 80

cases = []
for n in sorted(os.listdir(RUNS), reverse=True):
    if n < "2026-08-20":
        break
    try:
        m = json.load(open(os.path.join(RUNS, n, "move.json"), encoding="utf-8"))
    except Exception:
        continue
    if m.get("selected_action") not in ("move", "activate_perk") or not m.get("board"):
        continue
    perks = [p for p in (m.get("selected_perks") or []) if p in PERKS]
    if not perks:
        continue
    # only frames where the perk was still available (candidates mention it or no perk used yet this match)
    cases.append((n, m, perks))
    if len(cases) >= LIMIT:
        break
print("boards:", len(cases))

stats = collections.defaultdict(collections.Counter)
gains = collections.defaultdict(list)
examples = collections.defaultdict(list)
for n, m, perks in cases:
    ctx = ms.StrategyContext(mode=(m.get("strategy_context") or {}).get("mode") or "unknown",
                             solo_challenge=bool((m.get("strategy_context") or {}).get("solo_challenge")))
    bs = m.get("booster_state") or {}
    booster = ms.BoosterState(current=bs.get("current"), maximum=bs.get("maximum"), source="memory")
    ts = m.get("turn_state") or {}
    rs = m.get("round_state") or {}
    turn = ms.TurnState(remaining_moves=ts.get("remaining_moves"), source="memory",
                        current_round=rs.get("current"), total_rounds=rs.get("total"))
    kw = dict(mode=m.get("mode", "None"), allow_square_matches=m.get("allow_square_matches", False),
              explode_created_specials_immediately=m.get("specials_explode_immediately", False),
              score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()})
    ranked = ms.rank_moves(m["board"], m["special_board"], lookahead_candidates=10, lookahead_depth=2,
                           lookahead_beam_width=3, include_future_value=True, strategy_context=ctx, **kw)
    if not ranked:
        continue
    pri = ms.prioritize_ranked_moves(ranked, booster_state=booster, turn_state=turn, strategy_context=ctx, **kw)
    baseline = pri[0] if pri else ranked[0]
    plan = ms.evaluate_blue_plan(m["board"], m["special_board"], booster, **kw)
    dc = ms.PerkDecisionContext(booster=booster, turn=turn, blue_plan=plan, objective=ms.PerkObjective.MAX_BLUE)
    for flag in (False, True):
        ms.PERK_RANDOM_EXPECTED_CHARGE = flag
        actions = ms.rank_perk_actions(m["board"], m["special_board"], perks, normal_baseline=baseline,
                                       decision_context=dc, strategy_context=ctx, **kw)
        for perk in perks:
            best = next((a for a in actions if a.perk_key == perk), None)
            key = (perk, "new" if flag else "old")
            if best is None:
                stats[key]["no_candidate"] += 1
                continue
            ok, margin, gate = ms.perk_activation_decision(best, baseline, dc, ctx)
            stats[key]["activate" if ok else "hold"] += 1
            if ok:
                gains[key].append(margin)
                if flag and len(examples[perk]) < 5:
                    examples[perk].append((n, f"rem={booster.remaining}", f"moves={turn.remaining_moves}",
                                           f"exp={best.expected_value:.1f}", f"base_blue={baseline.blue_cells:.1f}",
                                           f"gain={margin:.1f}", gate, best.reason[:50]))
for key in sorted(stats):
    g = gains.get(key) or []
    print(f"{key[0]:16s} {key[1]:4s} {dict(stats[key])}  gain avg={statistics.mean(g) if g else 0:.2f}")
for perk, ex in examples.items():
    print(perk)
    for e in ex:
        print("   ", e)
