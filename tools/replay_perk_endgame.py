"""Replay the Auto perk decision for a Debug/runs board with the current code.

Usage: python tools/replay_perk_endgame.py RUN [RUN ...]

Rebuilds the board, booster, turn and score context recorded in move.json
and runs the same perk pipeline Auto uses (ranking per slot, activation
gate, last-perk reserve), printing the historical and the current decision.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402


def load_run(run: str) -> dict:
    path = Path(run)
    if not path.is_dir():
        path = ROOT / "Debug" / "runs" / run
    return json.loads((path / "move.json").read_text(encoding="utf-8"))


def contexts(move: dict):
    ctx = move["ranking_context"]
    booster = ms.BoosterState(
        current=ctx["booster_state"]["current"],
        maximum=ctx["booster_state"]["maximum"],
        source="memory",
    )
    turn_raw = ctx["turn_state"]
    turn = ms.TurnState(
        remaining_moves=turn_raw.get("remaining_moves"),
        source="memory",
        moves_left_in_match=turn_raw.get("moves_left_in_match"),
        is_final_round=bool(turn_raw.get("is_final_round")),
        current_round=turn_raw.get("current_round"),
        total_rounds=turn_raw.get("total_rounds"),
        time_left_seconds=turn_raw.get("time_left_seconds"),
        seconds_per_move=turn_raw.get("seconds_per_move"),
    )
    sc = ctx["strategy_context"]
    strategy = ms.StrategyContext(
        mode=sc["mode"],
        score_strategy=sc.get("score_strategy") or ms.SCORE_STRATEGY_NORMAL,
        our_score=sc.get("our_score"),
        opponent_score=sc.get("opponent_score"),
        score_deficit=sc.get("score_deficit"),
        expected_safe_points=sc.get("expected_safe_points"),
        score_confidence=sc.get("score_confidence"),
        booster_rush=bool(sc.get("booster_rush")),
    )
    return booster, turn, strategy


def replay(run: str, selected_perks=None) -> dict:
    move = load_run(run)
    board = move["board"]
    specials = move["special_board"]
    mode = move["mode"]
    rally = {int(k): float(v) for k, v in (move.get("score_rally_values") or {}).items()} or None
    booster, turn, strategy = contexts(move)
    perks = tuple(selected_perks or move.get("selected_perks") or ("none", "none"))
    # move.json records the lava marks 1-based (floor_lava_debug_state).
    lava = tuple(
        int(col) - 1 for col in (move.get("floor_lava_state") or {}).get("columns") or ()
    )
    kw = dict(
        mode=mode,
        allow_square_matches=bool(move.get("allow_square_matches")),
        score_rally_values=rally,
    )
    stack = contextlib.ExitStack()
    with stack:
        if lava:
            stack.enter_context(ms.floor_lava_checked_columns(lava))
        ranked = ms.rank_moves(
            board, specials, include_future_value=True, strategy_context=strategy, **kw
        )
        prioritized = ms.prioritize_ranked_moves(
            ranked, booster_state=booster, turn_state=turn, strategy_context=strategy, **kw
        )
        baseline = prioritized[0] if prioritized else None
        blue_plan = ms.evaluate_blue_plan(board, specials, booster, **kw)
        decision_context = ms.PerkDecisionContext(
            booster=booster, turn=turn, blue_plan=blue_plan,
            objective=ms.PerkObjective.MAX_BLUE,
        )
        decision = runtime.decide_auto_perk(
            board,
            specials,
            perks,
            normal_baseline=baseline,
            decision_context=decision_context,
            strategy_context=strategy,
            include_future_value=True,
            **kw,
        )
    old_action = move.get("selected_action")
    old_perk = move.get("selected_perk_action")
    best = move.get("best_move") or {}
    return {
        "run": run,
        "mode": mode,
        "selected_perks": list(perks),
        "time_left": turn.time_left_seconds,
        "old": {
            "action": old_action,
            "gate": move.get("decision_gate"),
            "perk": (old_perk or {}).get("perk"),
            "slot": (old_perk or {}).get("slot_number"),
            "target": (old_perk or {}).get("target"),
            "move": [best.get("start"), best.get("target")],
            "reason": (old_perk or {}).get("reason") or best.get("reason"),
        },
        "new": decision.as_debug(),
        "baseline_move": (
            [list(baseline.candidate.start), list(baseline.candidate.target)]
            if baseline is not None else None
        ),
    }


def main(argv: list[str]) -> int:
    for run in argv or []:
        print(json.dumps(replay(run), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
