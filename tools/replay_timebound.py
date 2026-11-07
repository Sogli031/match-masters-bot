"""Replay snimljenih solo tabli: (a) dead-charge pravilo na poslednjim
potezima, (b) time-bound tura sa emuliranim kratkim satom (20 s),
(c) regresija bez pritiska sata (100 s) -- izbori moraju biti identicni.

    python tools/replay_timebound.py [LIMIT]
"""
import collections
from pathlib import Path
import json
import os
import statistics
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

RUNS = os.path.join(ROOT, "Debug", "runs")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def load(pred, limit):
    out = []
    for n in sorted(os.listdir(RUNS), reverse=True):
        if n < "2026-08-25":
            break
        try:
            m = json.load(open(os.path.join(RUNS, n, "move.json"), encoding="utf-8"))
        except Exception:
            continue
        if m.get("selected_action") != "move" or not m.get("board"):
            continue
        sc = m.get("strategy_context") or {}
        if sc.get("mode") != "solo_6":
            continue
        if pred(m):
            out.append((n, m))
            if len(out) >= limit:
                break
    return out


def rank(m, turn):
    sc = m.get("strategy_context") or {}
    ctx = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=bool(sc.get("solo_challenge")))
    bs = m.get("booster_state") or {}
    booster = ms.BoosterState(current=bs.get("current"), maximum=bs.get("maximum"), source="memory")
    kw = dict(mode=m.get("mode", "None"), allow_square_matches=m.get("allow_square_matches", False),
              explode_created_specials_immediately=m.get("specials_explode_immediately", False),
              score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()})
    ranked = ms.rank_moves(m["board"], m["special_board"], lookahead_candidates=10, lookahead_depth=2,
                           lookahead_beam_width=3, include_future_value=True, strategy_context=ctx, **kw)
    if not ranked:
        return None
    pri = ms.prioritize_ranked_moves(ranked, booster_state=booster, turn_state=turn, strategy_context=ctx, **kw)
    return pri[0] if pri else None


def desc(e):
    return f"blue={e.blue_cells:.1f} inst={e.instant_score:.1f} extra={e.extra_moves:.0f} gate={getattr(e, 'decision_gate', '?')}"


# (a) dead charge: last 2-3 moves, meter far from full
def far(m):
    bs = m.get("booster_state") or {}
    rem = (bs.get("maximum") or 0) - (bs.get("current") or 0)
    rm = (m.get("turn_state") or {}).get("remaining_moves")
    return rm in (2, 3) and rem >= 4


cases = load(far, LIMIT)
changed = 0
blue_old, blue_new, inst_old, inst_new = [], [], [], []
for n, m in cases:
    rm = (m.get("turn_state") or {}).get("remaining_moves")
    turn = ms.TurnState(remaining_moves=rm, source="memory")
    ms.SOLO_DEAD_CHARGE = False
    a = rank(m, turn)
    ms.SOLO_DEAD_CHARGE = True
    b = rank(m, turn)
    if a is None or b is None:
        continue
    blue_old.append(a.blue_cells); blue_new.append(b.blue_cells)
    inst_old.append(a.instant_score); inst_new.append(b.instant_score)
    if (a.candidate.start, a.candidate.target) != (b.candidate.start, b.candidate.target):
        changed += 1
print(f"(a) dead charge: boards={len(cases)} changed={changed}; avg blue old={statistics.mean(blue_old):.2f} new={statistics.mean(blue_new):.2f}; avg instant old={statistics.mean(inst_old):.1f} new={statistics.mean(inst_new):.1f}")

# (b) time-bound: rumble boards with >=5 moves left, emulate 20 s on the clock
def rumble(m):
    sc = m.get("strategy_context") or {}
    rm = (m.get("turn_state") or {}).get("remaining_moves")
    return not sc.get("solo_challenge") and rm is not None and rm >= 5


cases = load(rumble, LIMIT)
changed = 0
ex_old = ex_new = 0
pts_old, pts_new, ch_old, ch_new = [], [], [], []
for n, m in cases:
    rm = (m.get("turn_state") or {}).get("remaining_moves")
    a = rank(m, ms.TurnState(remaining_moves=rm, source="memory"))
    b = rank(m, ms.TurnState(remaining_moves=rm, source="memory", time_left_seconds=20.0, seconds_per_move=6.5))
    if a is None or b is None:
        continue
    ex_old += a.extra_moves > 0
    ex_new += b.extra_moves > 0
    pts_old.append(a.instant_score); pts_new.append(b.instant_score)
    ch_old.append(a.blue_cells); ch_new.append(b.blue_cells)
    if (a.candidate.start, a.candidate.target) != (b.candidate.start, b.candidate.target):
        changed += 1
print(f"(b) time-bound (20 s left, {LIMIT} rumble boards): changed={changed}; picks with extra old={ex_old} new={ex_new}; avg instant old={statistics.mean(pts_old):.1f} new={statistics.mean(pts_new):.1f}; avg blue old={statistics.mean(ch_old):.2f} new={statistics.mean(ch_new):.2f}")

# (c) regression: same boards, plenty of clock -> identical picks
same = 0
for n, m in cases[:30]:
    rm = (m.get("turn_state") or {}).get("remaining_moves")
    a = rank(m, ms.TurnState(remaining_moves=rm, source="memory"))
    b = rank(m, ms.TurnState(remaining_moves=rm, source="memory", time_left_seconds=100.0, seconds_per_move=6.5))
    if a is not None and b is not None and (a.candidate.start, a.candidate.target) == (b.candidate.start, b.candidate.target):
        same += 1
print(f"(c) regression with 100 s left: identical picks {same}/30")
