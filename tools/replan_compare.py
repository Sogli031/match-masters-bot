"""Charles: does planning again later in the turn find more points?

For the first resting board of every Charles Solo research session, the
exact planner makes the first plan (booster held, --first-width) and plays
it on the exact simulator. Policy "replan" also plans again from the
current state every --every actions (--width), keeping the old line unless
the new one scores more. The simulator is the game's own refill, so the
played line's final score is what the game would give.

    python -m tools.replan_compare [--first-width 60] [--width 60] [--every 3] [--all-cores]

Progress with ETA in Debug/replan_compare.progress, result in
Debug/replan_compare.txt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.booster_hold_compare import _idle_only, lab_state, sessions  # noqa: E402


def work(item):
    path, first_width, width, every, price = item
    from strategy_lab import planner
    from strategy_lab.simulation import step

    state = lab_state(path, True)
    if price:
        state["rank_charge_value"] = price
    started = time.monotonic()
    first, _ = planner.plan(state, width=first_width)
    first_seconds = time.monotonic() - started
    line = list(first.actions)
    played, replans, gains, replan_seconds = 0, 0, [], []
    while line:
        if played and every and played % every == 0:
            t = time.monotonic()
            best, _ = planner.plan(state, width=width)
            replan_seconds.append(round(time.monotonic() - t, 1))
            # The rest of the current line, replayed, is what we compare with.
            rest = state
            for action in line:
                result = step(rest, action)
                if not result.get("supported"):
                    break
                rest = planner._bank_full_meter(result["state"])
            current = planner.Line(rest).value
            replans += 1
            if best.value > current and best.actions:
                gains.append(best.value - current)
                line = list(best.actions)
        result = step(state, line.pop(0))
        if not result.get("supported"):
            break
        state = planner._bank_full_meter(result["state"])
        played += 1
    return {"session": Path(path).parent.name, "first": first.score, "final": state.get("score") or 0,
            "replans": replans, "improved": len(gains), "first_seconds": round(first_seconds, 1),
            "replan_seconds": replan_seconds}


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--first-width", type=int, default=60)
    parser.add_argument("--width", type=int, default=60)
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--price", type=float, default=0.0)
    parser.add_argument("--all-cores", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "Debug/replan_compare.txt"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    progress = out.with_suffix(".progress")
    items = [(path, args.first_width, args.width, args.every, args.price) for path in sessions()]
    results, started = [], time.monotonic()
    progress.write_text(f"0/{len(items)} pocetak {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
    if args.all_cores:
        from multiprocessing import Pool
        _idle_only()
        pool_cm = Pool(min(len(items), os.cpu_count() or 1), initializer=_idle_only)
    else:
        pool_cm = gentle_pool()
    with pool_cm as pool:
        for result in pool.imap_unordered(work, items):
            results.append(result)
            done = len(results)
            elapsed = time.monotonic() - started
            eta = time.time() + elapsed / done * (len(items) - done)
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{done}/{len(items)} proteklo {elapsed:.0f} s, kraj oko "
                         f"{time.strftime('%H:%M', time.localtime(eta))}: {json.dumps(result)}\n")
    lines = [f"Ponovni plan svakih {args.every} akcija (sirina {args.width}), prvi plan sirina "
             f"{args.first_width}, booster sa cekanjem", ""]
    for r in sorted(results, key=lambda r: r["session"]):
        lines.append(f"{r['session']}: prvi plan {r['first']}, odigrano {r['final']} "
                     f"({r['final'] - r['first']:+d}), boljih planova {r['improved']} od {r['replans']}, "
                     f"vreme ponovnih planova {r['replan_seconds']}")
    first = sum(r["first"] for r in results)
    final = sum(r["final"] for r in results)
    lines += ["", f"Ukupno: prvi plan {first}, sa ponovnim planovima {final} ({final - first:+d}, "
              f"{100 * (final - first) / max(first, 1):+.1f} %)"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
