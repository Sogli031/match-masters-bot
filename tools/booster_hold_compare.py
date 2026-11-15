"""Checkmate Charles: fire a full booster at once vs. let the plan hold it.

For the first resting board of every Charles Solo research session, the
exact planner plans the whole turn twice with the same time budget:
"odmah" (booster_auto, the live rule) and "kasnije" (booster_hold: a full
meter may wait while swipes go on). Final scores are compared.

    python -m tools.booster_hold_compare [--seconds 60] [--out Debug/booster_hold.txt]

Runs through tools.gentle (idle priority, last core, 2 workers); progress
with ETA goes to <out>.progress after every item.
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

CHARLES = 54


def sessions():
    from tools.analyze_research import local_player
    out = []
    for folder in sorted((ROOT / "Debug/research").glob("*")):
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        if not files:
            continue
        record = json.loads(files[0].read_text(encoding="utf-8"))
        me = local_player(record) or {}
        if me.get("special_ability_type", me.get("specialAbilityType")) == CHARLES:
            out.append(str(files[0]))
    return out


def lab_state(path, hold):
    from simulator_capture import lab_move
    from tools.analyze_research import capture_from, local_player

    record = json.loads(Path(path).read_text(encoding="utf-8"))
    lab = lab_move(capture_from(record))
    me = local_player(record) or {}
    lab["perks"] = {int(a["type"]): 1 for a in me.get("board_abilities") or [] if a.get("type") in (22, 3)}
    charge = lab.get("booster_state") or {}
    lab["booster_state"] = {"current": charge.get("current") or 0, "maximum": charge.get("maximum")}
    lab["booster_auto"] = True
    lab["booster_hold"] = hold
    return lab


def held_boosters(lab, actions):
    """How many times the line swiped with a full meter (booster held)."""
    from strategy_lab.simulation import step
    state, held = lab, 0
    for action in actions:
        charge = state.get("booster_state") or {}
        full = charge.get("maximum") is not None and (charge.get("current") or 0) >= charge["maximum"]
        if full and action.get("kind", "swap") != "booster":
            held += 1
        state = step(state, action)["state"]
    return held


def work(item):
    path, hold, seconds = item
    from strategy_lab import planner
    lab = lab_state(path, hold)
    started = time.monotonic()
    best, stats = planner.plan_anytime(lab, seconds)
    return {"session": Path(path).parent.name, "hold": hold, "score": best.score,
            "steps": len(best.actions), "boosters": sum(a.get("kind") == "booster" for a in best.actions),
            "held": held_boosters(lab_state(path, hold), best.actions) if hold else 0,
            "width": stats.get("width"), "seconds": round(time.monotonic() - started, 1),
            "first": planner.describe(best.actions[0]) if best.actions else None}


def _idle_only():
    """Idle priority on every core (--all-cores): the game still wins a core."""
    import ctypes
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), 0x40)


def main(argv=None):
    from tools.gentle import gentle_pool

    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--out", default=str(ROOT / "Debug/booster_hold.txt"))
    parser.add_argument("--all-cores", action="store_true",
                        help="only when the player allows it: every core, still idle priority")
    parser.add_argument("--resume", action="store_true", help="keep the results already in <out>.progress")
    args = parser.parse_args(argv)
    out = Path(args.out)
    progress = out.with_suffix(".progress")
    items = [(path, hold, args.seconds) for path in sessions() for hold in (False, True)]
    results = []
    if args.resume and progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            if ": {" in line:
                results.append(json.loads(line.split(": ", 1)[1]))
        kept = {(r["session"], r["hold"]) for r in results}
        items = [i for i in items if (Path(i[0]).parent.name, i[1]) not in kept]
    total, resumed, started = len(items) + len(results), len(results), time.monotonic()
    with progress.open("a" if args.resume else "w", encoding="utf-8") as fh:
        fh.write(f"{len(results)}/{total} pocetak {time.strftime('%H:%M:%S')}"
                 f"{' (sva jezgra)' if args.all_cores else ''}\n")
    if args.all_cores:
        import os
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
            eta = time.time() + elapsed / (done - resumed) * (total - done)
            len_items = total
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{done}/{len_items} proteklo {elapsed:.0f} s, kraj oko "
                         f"{time.strftime('%H:%M', time.localtime(eta))}: {json.dumps(result)}\n")
    by = {}
    for r in results:
        by.setdefault(r["session"], {})[r["hold"]] = r
    lines = [f"Booster odmah vs kasnije, {args.seconds:.0f} s po planu, prvi snimak svake Charles partije", ""]
    total_now = total_hold = 0
    for session in sorted(by):
        now, hold = by[session][False], by[session][True]
        total_now += now["score"]
        total_hold += hold["score"]
        lines.append(f"{session}: odmah {now['score']} (boostera {now['boosters']}, sirina {now['width']}) | "
                     f"kasnije {hold['score']} (boostera {hold['boosters']}, cekao {hold['held']}x, "
                     f"sirina {hold['width']}) | razlika {hold['score'] - now['score']:+d}")
    lines += ["", f"Ukupno: odmah {total_now}, kasnije {total_hold}, razlika {total_hold - total_now:+d}"]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
