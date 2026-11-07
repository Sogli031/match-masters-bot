"""Ciljana provera jurenja plavih u Solo Challenge-u na snimljenim tablama od
2026-09-18: UFO extra tier (21:12:12, crvena extra sa 5 plavih iza refill-a
ispred direktne plave cetvorke) i obicni potezi na 0/7 gde je 0 plavih dobilo
na poenima (20:26:47, 20:28:50). Ispisuje FAILURES.

    python tools/check_solo_blue_chase.py
"""
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

RUNS = os.path.join(ROOT, "Debug", "runs")
CTX_SOLO = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)

# run -> (start, target) the blue-chasing policy should play
CASES = {
    "2026-09-18_21-12-12_764": ((3, 2), (4, 2)),
    "2026-09-18_20-26-47_548": ((4, 2), (4, 3)),
    "2026-09-18_20-28-50_655": ((2, 1), (2, 2)),
    # meter 4/7: direktna plava trojka puni metar, spoj specijala staje na 6/7
    "2026-09-18_21-31-26_243": ((2, 3), (3, 3)),
}


def describe(ev):
    return (
        f"{ev.candidate.start}->{ev.candidate.target} score={ev.score:.1f} "
        f"blue={ev.blue_cells} direct_blue={ev.direct_blue_cells} extra={ev.extra_moves}"
    )


def top_move(run):
    m = json.load(open(os.path.join(RUNS, run, "move.json"), encoding="utf-8"))
    booster = m.get("booster_state") or {}
    turn = m.get("turn_state") or {}
    bs = ms.BoosterState(current=booster.get("current"), maximum=booster.get("maximum"), source="memory")
    ts = ms.TurnState(remaining_moves=turn.get("remaining_moves"), source="memory")
    rally = {int(k): v for k, v in (m.get("score_rally_values") or {}).items()}
    common = dict(
        mode=m.get("mode", "None"),
        allow_square_matches=m.get("allow_square_matches", False),
        explode_created_specials_immediately=m.get("specials_explode_immediately", False),
        score_rally_values=rally,
        strategy_context=CTX_SOLO,
    )
    ufo = m.get("ufo") or {}
    eyes = int(ufo.get("eyes") or 0) if ufo.get("applied") else 0
    scope = (
        ms.ufo_abduction_active(eyes, allow_blues=bool(ufo.get("allow_blues")))
        if eyes
        else nullcontext()
    )
    with scope:
        ranked = ms.rank_moves(
            m["board"], m["special_board"],
            lookahead_candidates=10, lookahead_depth=2, lookahead_beam_width=3,
            include_future_value=True, **common,
        )
        pri = ms.prioritize_ranked_moves(ranked, booster_state=bs, turn_state=ts, **common)
    played = (m.get("best_move") or {})
    return pri[0] if pri else None, played


def main():
    failures = 0
    for run, (start, target) in CASES.items():
        top, played = top_move(run)
        print(f"[{run}] played {played.get('start')}->{played.get('target')}")
        print(f"   now: {describe(top) if top else None}")
        if top is None or (tuple(top.candidate.start), tuple(top.candidate.target)) != (start, target):
            print(f"   FAIL: expected {start}->{target}")
            failures += 1
    print("FAILURES:", failures)


if __name__ == "__main__":
    main()
