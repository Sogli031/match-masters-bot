"""Ciljana provera SOLO_DISCO_NEVER_BLUE na dve snimljene table gde je kugla
otisla na plavu (2026-09-01 04:42:26 auto, 08:11:36 Extra move dugme), plus
sinteticka tabla sa svim plavim susedima i versus kontrola. Ispisuje FAILURES.

    python tools/check_disco_never_blue.py
"""
import json
from pathlib import Path
import os
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

RUNS = os.path.join(ROOT, "Debug", "runs")
COL = {1: "BLUE", 2: "green", 3: "yellow", 4: "purple", 5: "red", 6: "orange"}
CTX_SOLO = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)
CTX_VERSUS = ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)


def load_run(run):
    d = os.path.join(RUNS, run)
    od = json.load(open(os.path.join(d, "observed_delta.json"), encoding="utf-8"))
    m = json.load(open(os.path.join(d, "move.json"), encoding="utf-8"))
    return (
        od["board_before"],
        od["special_board_before"],
        m,
    )


def describe(ev):
    if ev is None:
        return "None"
    col = ms._disco_target_color(ev)
    return (
        f"{ev.candidate.start}->{ev.candidate.target} score={ev.score:.1f} "
        f"disco={ev.disco_moves} target={COL.get(col, col)} extra={ev.extra_moves} "
        f"blue={ev.blue_cells}"
    )


def run_case(board, special, m, ctx, flag):
    ms.SOLO_DISCO_NEVER_BLUE = flag
    booster = m.get("booster_state") or {}
    bs = ms.BoosterState(current=booster.get("current"), maximum=booster.get("maximum"), source="memory")
    ts = ms.TurnState(remaining_moves=(m.get("turn_state") or {}).get("remaining_moves"), source="memory")
    ranked = ms.rank_moves(
        board, special, mode=m.get("mode", "None"),
        allow_square_matches=m.get("allow_square_matches", False),
        explode_created_specials_immediately=m.get("specials_explode_immediately", False),
        score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()},
        lookahead_candidates=10, lookahead_depth=2, lookahead_beam_width=3,
        include_future_value=True, strategy_context=ctx,
    )
    pri = ms.prioritize_ranked_moves(
        ranked, mode=m.get("mode", "None"),
        allow_square_matches=m.get("allow_square_matches", False),
        explode_created_specials_immediately=m.get("specials_explode_immediately", False),
        score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()},
        booster_state=bs, turn_state=ts, strategy_context=ctx,
    )
    return ranked, pri


def main():
    failures = 0
    # 1. auto play board where the ball went BLUE (score_gate, meter 0/7)
    board, special, m = load_run("2026-09-01_04-42-26_433")
    for flag in (False, True):
        ranked, pri = run_case(board, special, m, CTX_SOLO, flag)
        discos = [e for e in ranked if e.disco_moves > 0]
        print(f"[04-42-26] flag={flag} top: {describe(pri[0] if pri else None)}")
        print("   disco swaps on board:", [describe(e) for e in discos])
        if flag and pri and ms._is_blue_target_disco(pri[0]):
            print("   FAIL: blue disco still on top"); failures += 1
        if flag and any(ms._is_blue_target_disco(e) for e in pri):
            print("   FAIL: blue disco still in prioritized list"); failures += 1
    # control: versus context keeps blue discos
    ranked, pri = run_case(board, special, m, CTX_VERSUS, True)
    print(f"[04-42-26] versus control top: {describe(pri[0] if pri else None)}; blue discos kept in list:",
          any(ms._is_blue_target_disco(e) for e in pri))

    # 2. Extra move button board where both extra candidates were blue discos
    board, special, m = load_run("2026-09-01_08-11-36_567")
    for ctx, label in ((None, "no ctx"), (CTX_SOLO, "solo ctx"), (CTX_VERSUS, "versus ctx")):
        ms.SOLO_DISCO_NEVER_BLUE = True
        ranked = ms.rank_extra_move_moves(
            board, special, mode=m.get("mode", "None"),
            allow_square_matches=m.get("allow_square_matches", False),
            explode_created_specials_immediately=m.get("specials_explode_immediately", False),
            score_rally_values={int(k): v for k, v in (m.get("score_rally_values") or {}).items()},
            lookahead_candidates=10, lookahead_depth=2, lookahead_beam_width=3,
            include_future_value=False, strategy_context=ctx,
        )
        print(f"[08-11-36] extra button {label}: {[describe(e) for e in ranked[:3]]}")
        if ctx is CTX_SOLO and any(ms._is_blue_target_disco(e) for e in ranked):
            print("   FAIL: blue disco offered by extra button in solo"); failures += 1
    # same board through the auto path
    ms.SOLO_DISCO_NEVER_BLUE = True
    ranked, pri = run_case(board, special, m, CTX_SOLO, True)
    print(f"[08-11-36] auto solo top: {describe(pri[0] if pri else None)}")
    if pri and ms._is_blue_target_disco(pri[0]):
        print("   FAIL"); failures += 1

    # 3. synthetic: every neighbour of the ball painted blue -> ball parked
    board, special, m = load_run("2026-09-01_04-42-26_433")
    board = [row[:] for row in board]
    size = len(board)
    ball = next((r, c) for r in range(size) for c in range(size) if special[r][c] == ms.SPECIAL_DISCO_BALL)
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        r, c = ball[0] + dr, ball[1] + dc
        if 0 <= r < size and 0 <= c < size and special[r][c] == 0:
            board[r][c] = ms.BLUE
    ranked, pri = run_case(board, special, m, CTX_SOLO, True)
    discos = [e for e in ranked if e.disco_moves > 0]
    print(f"[all-blue neighbours] ball at {ball}; disco swaps: {[describe(e) for e in discos]}")
    print(f"   top: {describe(pri[0] if pri else None)}")
    if pri and pri[0].disco_moves > 0 and ms._is_blue_target_disco(pri[0]):
        print("   FAIL: blue disco played although other moves exist"); failures += 1
    # only-blue-disco board: keep_if_empty fallback
    only_blue = [e for e in ranked if ms._is_blue_target_disco(e)]
    kept = ms._without_blue_target_discos(only_blue, CTX_SOLO)
    print(f"   keep_if_empty fallback returns {len(kept)} of {len(only_blue)} blue discos;",
          "strict:", len(ms._without_blue_target_discos(only_blue, CTX_SOLO, keep_if_empty=False)))
    if len(kept) != len(only_blue):
        failures += 1
    print("FAILURES:", failures)


if __name__ == "__main__":
    main()
