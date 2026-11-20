"""Planner reference: the same plan before and after a speed change.

For the first resting board of every recorded session in tests/fixtures,
plan(state, width=W) is run to the end; actions, score, value and the
simulation count go to a JSON file. With --compare the new run is checked
against an older file: any difference in a plan is printed.

    python -m tools.plan_reference --out Debug/plan_ref_before.json
    python -m tools.plan_reference --out Debug/plan_ref_after.json --compare Debug/plan_ref_before.json

Progress with ETA in <out>.progress. Runs through tools.gentle.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def boards(limit, per=4):
    """Up to ``per`` numbered captures, spread out, of every fixture session folder."""
    found = []
    for folder in sorted(ROOT.glob("tests/fixtures/*/*")):
        if folder.is_dir():
            numbered = sorted(folder.glob("[0-9][0-9][0-9].json"))
            step = max(1, len(numbered) // per)
            found.extend(numbered[::step][:per])
    return found[:limit]


def load(path):
    """The lab state of a capture, or None when the planner cannot take it."""
    from simulator_capture import capture_mode, lab_move
    from strategy_lab import simulation
    from tools.analyze_research import capture_from

    record = json.loads(Path(path).read_text(encoding="utf-8"))
    capture = capture_from(record)
    lab = lab_move(capture)
    if lab.get("engine_refill") is None:
        return None
    simulation.PREFIX_MODES.add(capture_mode(lab["engine_refill"].profile))
    simulation.PREFIX_MODES.add(lab.get("mode"))
    return lab


def work(item):
    path, width, max_steps, settings = item
    from strategy_lab import planner
    try:
        state = load(path)
        if state is None:
            return {"board": path, "skip": "no engine refill"}
        state.update(settings)
        started = time.perf_counter()
        best, stats = planner.plan(state, width=width, max_steps=max_steps)
        seconds = time.perf_counter() - started
    except Exception as exc:  # a fixture the lab cannot load is skipped, not fatal
        return {"board": path, "skip": f"{type(exc).__name__}: {exc}"}
    return {"board": path, "actions": json.loads(json.dumps(best.actions, default=str)),
            "score": best.score, "value": best.value, "simulated": stats["simulated"],
            "expanded": stats["expanded"], "seconds": round(seconds, 2)}


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", required=True)
    parser.add_argument("--compare")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=JSON",
                        help="planner setting put into every state, e.g. rank_special_value=20")
    args = parser.parse_args(argv)
    out = Path(args.out)
    progress = out.with_suffix(".progress")
    settings = {k: json.loads(v) for k, v in (item.split("=", 1) for item in args.set)}
    items = [(str(p.relative_to(ROOT)), args.width, args.max_steps, settings) for p in boards(args.limit)]
    results, started = [], time.monotonic()
    progress.write_text(f"0/{len(items)} pocetak {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
    with gentle_pool() as pool:
        for result in pool.imap_unordered(work, items):
            results.append(result)
            done, elapsed = len(results), time.monotonic() - started
            eta = time.time() + elapsed / done * (len(items) - done)
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{done}/{len(items)} proteklo {elapsed:.0f} s, kraj oko "
                         f"{time.strftime('%H:%M:%S', time.localtime(eta))}\n")
    results.sort(key=lambda r: r["board"])
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    planned = [r for r in results if "skip" not in r]
    print(f"{len(planned)} planova, {len(results) - len(planned)} preskoceno, "
          f"ukupno {sum(r['seconds'] for r in planned):.1f} s plana, "
          f"{sum(r['simulated'] for r in planned)} simulacija, "
          f"zbir vrednosti {sum(r['value'] for r in planned):.0f}")
    if args.compare:
        old = {r["board"]: r for r in json.loads(Path(args.compare).read_text(encoding="utf-8"))}
        same = differ = better = worse = 0
        old_seconds = new_seconds = 0.0
        for r in planned:
            o = old.get(r["board"])
            if o is None or "skip" in o:
                continue
            keys = ("actions", "score", "value", "simulated")
            if all(o[k] == r[k] for k in keys):
                same += 1
            else:
                differ += 1
                print("RAZLIKA", r["board"], {k: (o[k], r[k]) for k in keys if o[k] != r[k] and k != "actions"},
                      "akcije" if o["actions"] != r["actions"] else "")
            better += r["value"] > o["value"]
            worse += r["value"] < o["value"]
            old_seconds += o["seconds"]
            new_seconds += r["seconds"]
        print(f"vrednost bolja na {better}, losija na {worse}; zbir "
              f"{sum(old[r['board']]['value'] for r in planned if r['board'] in old):.0f} -> "
              f"{sum(r['value'] for r in planned if r['board'] in old):.0f}")
        print(f"isto {same}, razlicito {differ}; vreme {old_seconds:.1f} s -> {new_seconds:.1f} s "
              f"({old_seconds / max(new_seconds, 1e-9):.2f}x)")


if __name__ == "__main__":
    main()
