"""Are the Cleo extra-move percentages right? Old 1/N model vs native selector.

Takes every played Cleo move in Debug/runs and compares the predicted chance
with whether the turn was kept. Colour guesses are not used: they are read from
a board that has already cascaded and refilled. Only moves with a readable
counter that were not lost to a booster count, as in cleo_audit.py.

The old model is recomputed from the record's own stored scenarios
(extra_move_probability at decision time is the 1/N share); the new one from
the current code, with the use count inferred from the moves of the same turn.

Usage:
    python tools/cleo_odds_audit.py [--runs Debug/runs] [--since 2026-09-15]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402
from tools.cleo_audit import _fill_unmeasured_turn, _load, _rule_context  # noqa: E402


def predict(move: dict, uses: int) -> float | None:
    best = move.get("best_move") or {}
    board, special = move.get("board"), move.get("special_board")
    start, target = best.get("start"), best.get("target")
    if not (board and special and start and target and best.get("direction")):
        return None
    start, target = tuple(start), tuple(target)
    swapped_board, swapped_special = ms.swap_cells(board, special, start, target)
    candidate = ms.MoveCandidate(start, target, ms.Direction(best["direction"]), swapped_board, swapped_special)
    with _rule_context(move), ms.cleo_odds_active({"uses": uses}):
        result = ms._simulate_cleo_candidate(
            candidate, allow_square_matches=bool(move.get("allow_square_matches")), include_future_value=False
        )
    return None if result is None else float(result.cleo_extra_move_probability)


def collect(runs: Path, since: str) -> list[dict]:
    rows, uses, last = [], 1, None
    for run_dir in sorted(runs.iterdir()):
        if run_dir.name < since:
            continue
        move = _load(run_dir / "move.json")
        delta = _load(run_dir / "observed_delta.json")
        if not move or not delta or move.get("selected_action") != "move":
            continue
        cleo = (move.get("best_move") or {}).get("cleo")
        if not cleo:
            continue
        moves = (move.get("turn_state") or {}).get("remaining_moves")
        # Same turn: a counter that did not rise, within a turn's time span.
        same_turn = (
            last is not None and moves is not None and last[1] is not None and moves <= last[1]
            and run_dir.name[:16] == last[0][:16]
        )
        uses = uses + 1 if same_turn else 1
        last = (run_dir.name, moves)
        check = runtime._cleo_prediction_check(_fill_unmeasured_turn(delta, run_dir, move), dict(move["best_move"]))
        kept = None if check is None else check.get("observed_kept_the_turn")
        if kept is None or (check.get("seconds_to_next_decision") or 0) > 60:
            continue
        new = predict(move, uses)
        if new is None:
            continue
        rows.append({"run": run_dir.name, "old": float(cleo.get("extra_move_probability") or 0.0), "new": new,
                     "kept": bool(kept), "uses": uses,
                     "special": bool(move["special_board"][move["best_move"]["target"][0]][move["best_move"]["target"][1]]
                                     not in (0, ms.SPECIAL_CLEO_BUG)
                                     or move["special_board"][move["best_move"]["start"][0]][move["best_move"]["start"][1]]
                                     not in (0, ms.SPECIAL_CLEO_BUG))})
    return rows


def score(rows: list[dict], key: str) -> str:
    brier = sum((r[key] - r["kept"]) ** 2 for r in rows) / len(rows)
    hits = sum((r[key] >= 0.5) == r["kept"] for r in rows)
    return f"{key}: Brier {brier:.3f}, pogodak na pragu 50% {hits}/{len(rows)} ({hits / len(rows):.0%})"


def calibration(rows: list[dict], key: str) -> None:
    buckets = defaultdict(list)
    for r in rows:
        buckets[min(int(r[key] * 5), 4)].append(r["kept"])
    for bucket in sorted(buckets):
        kept = buckets[bucket]
        print(f"  {key} {bucket * 20:3d}-{bucket * 20 + 20:3d}%: {sum(kept):3d}/{len(kept):3d} zadrzano ({sum(kept) / len(kept):.0%})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=ROOT / "Debug" / "runs")
    parser.add_argument("--since", default="2026-09-15")
    parser.add_argument("--dump", type=Path)
    args = parser.parse_args()
    rows = collect(args.runs, args.since)
    print(f"potezi sa citljivim ishodom: {len(rows)}, zadrzano {sum(r['kept'] for r in rows)}")
    for name, part in (("svi", rows), ("obican partner", [r for r in rows if not r["special"]]),
                       ("specijal partner", [r for r in rows if r["special"]])):
        if not part:
            continue
        print(f"[{name}] n={len(part)}")
        print(" ", score(part, "old"))
        print(" ", score(part, "new"))
        calibration(part, "old")
        calibration(part, "new")
    if args.dump:
        args.dump.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
