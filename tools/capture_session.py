"""Snimaj partiju na Enter: posle svakog poteza jedan capture i odmah poredjenje.

Svaki snimak je obican tools/capture_match.py capture (agent se kaci, cita i
odvaja; nema stalnog readera). Uzastopni snimci iste partije se porede sa
ported dopunom preko tools/verify_refill.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import load_capture
from tools import capture_match, verify_refill


def _label(entry):
    a = entry["action"]
    kind = a.get("kind", "swap")
    text = f"{a['start']}->{a['target']}" + ("" if kind == "swap" else f" ({kind})")
    return text + (f" [pragovi: {entry['hypothesis']}]" if entry.get("hypothesis") else "")


def summarize(previous, current):
    before, after = load_capture(previous), load_capture(current)
    if before["profile"]["rng"]["_seed"] != after["profile"]["rng"]["_seed"]:
        return "nova partija - poredjenje krece od ovog snimka"
    if verify_refill.observed(before) == verify_refill.observed(after):
        return "igra nije odigrala potez (stanje isto kao prethodni snimak) - snimi ponovo posle poteza"
    try:
        report = verify_refill.compare(previous, current)
    except Exception as exc:  # unsupported branch, unreadable package, ...
        return f"poredjenje nije moguce: {exc}"
    exact = sorted({_label(r) for r in report if r.get("match")})
    if exact:
        return "POKLAPA SE: " + ", ".join(exact)
    tried = [r for r in report if r["supported"]]
    if not tried:
        reasons = sorted({r["reason"] for r in report})
        return "nijedan potez nije podrzan: " + "; ".join(reasons)
    best = min(tried, key=verify_refill._distance)
    lines = [f"NE POKLAPA SE; najblizi potez {_label(best)} (dopune {best['refills']}):"]
    lines += ["  " + d for d in best["differences"]]
    hints = sorted({(_label(r), tuple(r["extra_draw_before_refill"]))
                    for r in tried if r.get("extra_draw_before_refill")})
    for label, calls in hints:
        lines.append(f"  {label}: +1 RNG izvlacenje pre dopune {list(calls)} daje tacno poklapanje")
    return "\n".join(lines)


def advise(capture_dir, seconds, width):
    """Plan the rest of the turn from this capture and name the next swipe."""
    from simulator_capture import lab_move
    from strategy_lab import planner

    try:
        state = lab_move(load_capture(capture_dir))
        started = time.monotonic()
        best, stats = planner.plan(state, width=width, deadline=started + seconds)
    except Exception as exc:
        return f"plan nije moguc: {exc}"
    if not best.actions:
        return "plan: nema podrzanog poteza"
    gain = best.score - (state.get("score") or 0)
    return (f"PREDLOG: {planner.describe(best.actions[0])}  "
            f"(plan do kraja: skor {best.score}, {gain:+d}, {len(best.actions)} poteza, "
            f"{time.monotonic() - started:.0f} s)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-plan", action="store_true", help="bez predloga poteza")
    parser.add_argument("--plan-seconds", type=float, default=10)
    parser.add_argument("--plan-width", type=int, default=40)
    args = parser.parse_args(argv)
    session = ROOT / "Debug/match_captures" / ("session_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    session.mkdir(parents=True)
    print(f"Folder: {session}")
    print("Enter = snimi (tabla mora da miruje, Memory GUI zatvoren), q + Enter = kraj.")
    previous = None
    number = 0
    while True:
        try:
            command = input(f"[{number:02d}] > ").strip().lower()
        except EOFError:
            break
        if command in ("q", "quit", "kraj"):
            break
        output = session / f"{number:02d}_{dt.datetime.now().strftime('%H%M%S')}"
        try:
            code = capture_match.main(["--out", str(output)])
        except Exception as exc:
            print(f"Snimak nije uspeo: {exc}\nSacekaj da tabla miruje pa pritisni Enter ponovo.")
            continue
        if code not in (0, 2) or not output.is_dir():
            print("Snimak nije sacuvan; pokusaj ponovo.")
            continue
        print(verify_refill.format_info(verify_refill.describe_capture(load_capture(output))))
        if previous is not None:
            print(summarize(previous, output))
        if not args.no_plan:
            print(advise(output, args.plan_seconds, args.plan_width))
        previous = output
        number += 1
    print(f"Snimljeno: {number}. Folder: {session}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
