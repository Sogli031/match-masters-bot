"""How long each search width takes and what it scores (Charles first plan).

For the first resting board of every Charles Solo research session, the
exact planner runs each width to the end (no deadline), booster at once and
booster held. The result says how long the first plan has to be to finish
the next width, and what that width is worth.

    python -m tools.plan_width_curve [--widths 1,4,10,25,60] [--all-cores]

Progress with ETA in Debug/plan_width_curve.progress, result in
Debug/plan_width_curve.txt. Without --all-cores it runs through tools.gentle.
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
    path, hold, width = item
    from strategy_lab import planner
    lab = lab_state(path, hold)
    started = time.monotonic()
    best, stats = planner.plan(lab, width=width)
    return {"session": Path(path).parent.name, "hold": hold, "width": width, "score": best.score,
            "seconds": round(time.monotonic() - started, 1)}


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--widths", default="1,4,10,25,60")
    parser.add_argument("--all-cores", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "Debug/plan_width_curve.txt"))
    args = parser.parse_args(argv)
    widths = [int(w) for w in args.widths.split(",")]
    out = Path(args.out)
    progress = out.with_suffix(".progress")
    # Widest first, so the long items do not end up alone at the end.
    items = [(path, hold, width) for width in sorted(widths, reverse=True)
             for path in sessions() for hold in (False, True)]
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
    lines = ["Sirina pretrage: vreme i skor, prvi snimak svake Charles partije", ""]
    for hold in (False, True):
        lines.append("booster sa cekanjem" if hold else "booster odmah")
        for width in widths:
            rows = [r for r in results if r["hold"] == hold and r["width"] == width]
            if not rows:
                continue
            times = sorted(r["seconds"] for r in rows)
            lines.append(f"  sirina {width:>4}: skor ukupno {sum(r['score'] for r in rows):>6}, "
                         f"vreme medijana {times[len(times) // 2]:.0f} s, najduze {times[-1]:.0f} s")
        lines.append("")
    lines.append("Po partiji (skor/vreme po sirini; odmah | cekanje):")
    for session in sorted({r["session"] for r in results}):
        parts = []
        for hold in (False, True):
            rows = sorted((r for r in results if r["session"] == session and r["hold"] == hold),
                          key=lambda r: r["width"])
            parts.append(" ".join(f"{r['width']}:{r['score']}/{r['seconds']:.0f}s" for r in rows))
        lines.append(f"  {session}: {parts[0]} | {parts[1]}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
