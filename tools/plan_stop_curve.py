"""Score and time of every search width, for the planner's dynamic stop.

For Charles and Foxy Roxy SE Solo research sessions the exact planner runs
each width to the end (no deadline) with the live policy (booster held, a
move in hand priced at CHARLES_MOVE_VALUE, the turn clock as max_steps), from
the first resting board (the first plan) and from boards a third and two
thirds into the game (the background replans). Every pass of plan_anytime is
an independent search, so this table replays any stopping rule exactly:
which pass it stops after, the score it keeps and the seconds it waited
(--evaluate).

    python -m tools.plan_stop_curve [--widths 1,4,10,25,60,150] [--all-cores]
    python -m tools.plan_stop_curve --evaluate

Progress with ETA in Debug/plan_stop_curve.progress, one JSON line per item
in Debug/plan_stop_curve.jsonl (kept: --resume skips what is there), the
evaluation in Debug/plan_stop_curve.txt.
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

BOOSTERS = (54, 52)     # Checkmate Charles, Foxy Roxy SE (CHARLES_POLICY_BOOSTERS)
OUT = ROOT / "Debug/plan_stop_curve.jsonl"
NL = chr(10)
# Actions the turn clock allows the first plan: (1500 s - 4 s reserve - 150 s
# first plan) / CHARLES_ACTION_SECONDS 8.5. Later boards get their share.
FIRST_STEPS = 158


def boards():
    """(path, part, max_steps): first board, and 1/3 and 2/3 when the game is long."""
    from tools.analyze_research import local_player
    out = []
    for folder in sorted((ROOT / "Debug/research").glob("*")):
        files = sorted(folder.glob("[0-9][0-9][0-9].json"))
        if not files:
            continue
        record = json.loads(files[0].read_text(encoding="utf-8"))
        me = local_player(record) or {}
        if me.get("special_ability_type", me.get("specialAbilityType")) not in BOOSTERS:
            continue
        out.append((str(files[0]), 0, FIRST_STEPS))
        if len(files) >= 9:
            # Only a third in: two thirds in took as long per width and the
            # whole table ran over 3 hours (2026-11-17).
            for part in (1,):
                out.append((str(files[len(files) * part // 3]), part, FIRST_STEPS * (3 - part) // 3))
    return out


def lab_state(path):
    from square_solo_live import CHARLES_MOVE_VALUE
    from tools.booster_hold_compare import lab_state as base

    lab = base(path, True)
    lab["rank_move_value"] = CHARLES_MOVE_VALUE
    return lab


def work(item):
    path, part, max_steps, width = item
    from strategy_lab import planner
    lab = lab_state(path)
    started = time.monotonic()
    best, stats = planner.plan(lab, width=width, max_steps=max_steps)
    seconds = round(time.monotonic() - started, 2)
    start = lab.get("score") or 0
    targets = [t for t in lab.get("solo_targets") or () if t > start]
    return {"session": Path(path).parent.name, "file": Path(path).name, "part": part, "width": width,
            "start": start, "score": best.score, "value": best.value, "actions": len(best.actions),
            "boosters": sum(a.get("kind") == "booster" for a in best.actions),
            "target": targets[0] if targets else None,
            "reaches": bool(targets) and best.score >= targets[0],
            "seconds": seconds, "simulated": stats["simulated"]}


def measure(args):
    from tools.gentle import gentle_pool
    from tools.booster_hold_compare import _idle_only

    widths = [int(w) for w in args.widths.split(",")]
    out = Path(args.out)
    progress = out.with_suffix(".progress")
    done_keys = set()
    if args.resume and out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done_keys.add((r["session"], r["file"], r["width"]))
    # Widest first, so the long items do not end up alone at the end.
    items = [(path, part, steps, width) for width in sorted(widths, reverse=True)
             for path, part, steps in boards()
             if (Path(path).parent.name, Path(path).name, width) not in done_keys]
    started = time.monotonic()
    progress.write_text(f"0/{len(items)} pocetak {time.strftime('%H:%M:%S')}"
                        f"{' (sva jezgra, idle)' if args.all_cores else ''}\n", encoding="utf-8")
    if args.all_cores:
        from multiprocessing import Pool
        _idle_only()
        pool_cm = Pool(min(len(items), os.cpu_count() or 1), initializer=_idle_only)
    else:
        pool_cm = gentle_pool()
    with pool_cm as pool, out.open("a", encoding="utf-8") as sink:
        for done, result in enumerate(pool.imap_unordered(work, items), 1):
            sink.write(json.dumps(result) + "\n")
            sink.flush()
            elapsed = time.monotonic() - started
            eta = time.time() + elapsed / done * (len(items) - done)
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{done}/{len(items)} proteklo {elapsed:.0f} s, kraj oko "
                         f"{time.strftime('%H:%M', time.localtime(eta))}: {json.dumps(result)}\n")


def load(path=OUT):
    """{(session, file, part): {width: row}}."""
    table = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        table.setdefault((r["session"], r["file"], r["part"]), {})[r["width"]] = r
    return table


def replay_rule(rows, rule, start_width=0, baseline=None, budget=None):
    """Run planner.plan_anytime's stop decision over measured passes.

    Returns (value of the line kept, seconds waited, widths run, reason).
    ``budget``: the old fixed time (a pass that would end past it is cut and
    counts only its time; its line is not kept -- the live cut line was never
    better than the widest whole pass in the logs).
    """
    from strategy_lab import planner

    widths = [w for w in sorted(rows) if w >= start_width]
    passes, best, waited, reason = [], baseline, 0.0, "sve sirine"
    for width in widths:
        r = rows[width]
        if rule is not None and passes:
            stop = planner.stop_reason(passes, width, baseline=baseline, rule=rule)
            if stop:
                reason = stop
                break
        if budget is not None and waited + r["seconds"] > budget:
            waited = budget
            reason = "isteklo vreme"
            break
        waited += r["seconds"]
        passes.append({"width": width, "seconds": r["seconds"], "complete": True, "value": r["value"]})
        if best is None or r["value"] >= best:
            best = r["value"]
    return best, waited, [p["width"] for p in passes], reason


def _rules():
    """The grid of rules tried: relative threshold, gain per second, min width."""
    for min_width in (4, 10, 25):
        for rel in (0.0, 0.25, 0.5, 1.0, 2.0, 4.0):
            for per_second in (0.0, 0.01, 0.03, 0.1):
                yield {"min_gain": rel / 100, "min_points": 0, "gain_per_second": per_second / 100,
                       "gain_decay": 1.0, "min_width": min_width}


def _first_total(first, rule, fence):
    score = wait = 0.0
    for rows in first.values():
        value, waited, _, _ = replay_rule(rows, rule, budget=fence)
        score += value
        wait += waited
    return score, wait


def _bg_total(mid, rule, start_width, fence):
    """Background replans: from the first plan's width against the carried
    line (stand-in: this board's width-10 line, a narrower earlier search)."""
    score = wait = 0.0
    for rows in mid.values():
        carried = rows.get(10, rows[min(rows)])["value"]
        value, waited, _, _ = replay_rule(rows, rule, start_width=start_width, baseline=carried,
                                          budget=fence)
        score += value
        wait += waited
    return score, wait


def evaluate(args):
    from strategy_lab import planner

    table = load(args.out)
    scale = args.scale
    lines = [f"Dinamicko zaustavljanje planera, {len(table)} tabli iz {args.out}",
             f"(vremena u zivim sekundama: izmereno x {scale:g})", ""]
    lines.append("Dobitak po sirini (vrednost prema prethodnoj sirini, % skora):")
    widths = sorted({w for rows in table.values() for w in rows})
    for part in (0, 1, 2):
        for a, b in zip(widths, widths[1:]):
            gains = [(rows[b]["value"] - rows[a]["value"]) / max(1, rows[a]["value"]) * 100
                     for (s, f, p), rows in table.items() if p == part and a in rows and b in rows]
            times = [rows[b]["seconds"] * scale for (s, f, p), rows in table.items()
                     if p == part and b in rows]
            if gains:
                gains.sort()
                times.sort()
                lines.append(f"  deo {part}: {a:>4} -> {b:<4} tabli {len(gains):2d}, medijana "
                             f"{gains[len(gains) // 2]:+6.2f} %, prosek {sum(gains) / len(gains):+6.2f} %, "
                             f"bolje {sum(g > 0 for g in gains)}, gore {sum(g < 0 for g in gains)}; "
                             f"vreme {b}: medijana {times[len(times) // 2]:.0f} s")
    # After a small gain, what does the next width bring? (is stopping safe)
    lines += ["", "Posle malog dobitka (< 0.5 %), sta donese sledeca sirina:"]
    for part in (0, 1, 2):
        after = []
        for rows in (r for (s, f, p), r in table.items() if p == part):
            ws = sorted(rows)
            for x, y, z in zip(ws, ws[1:], ws[2:]):
                g1 = (rows[y]["value"] - max(rows[w]["value"] for w in ws if w <= x)) / max(1, rows[x]["value"])
                if y >= 10 and g1 < 0.005:
                    after.append((rows[z]["value"] - max(rows[w]["value"] for w in ws if w <= y))
                                 / max(1, rows[y]["value"]) * 100)
        if after:
            after.sort()
            lines.append(f"  deo {part}: {len(after)} slucajeva, medijana {after[len(after) // 2]:+.2f} %, "
                         f"prosek {sum(after) / len(after):+.2f} %, najvise {after[-1]:+.2f} %")
    first = {k: rows for k, rows in table.items() if k[2] == 0}
    mid = {k: rows for k, rows in table.items() if k[2] != 0}
    fence_old = 150.0 / scale
    old_score = old_wait = 0.0
    for rows in first.values():
        value, waited, _, _ = replay_old(rows, fence_old)
        old_score += value
        old_wait += waited
    lines += ["", f"Prvi plan, {len(first)} tabli. Stari (150 s, stop_early): skor {old_score:.0f}, "
              f"cekanje {old_wait * scale:.0f} s"]
    best_rows = []
    for fence_live in (150.0, 200.0, 300.0):
        for rule in _rules():
            score, wait = _first_total(first, rule, fence_live / scale)
            best_rows.append((score >= old_score and wait <= old_wait, score, -wait, fence_live, rule))
    best_rows.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    lines.append("  najbolja pravila (skor >= stari i cekanje <= staro prvo):")
    for ok, score, wait, fence_live, rule in best_rows[:25]:
        lines.append(f"    {'OK ' if ok else '   '}granica {fence_live:.0f} s, prag {rule['min_gain'] * 100:.2f} %, "
                     f"isplativost {rule['gain_per_second'] * 100:.2f} %/s, od sirine {rule['min_width']}: "
                     f"skor {score:.0f} ({score - old_score:+.0f}), cekanje {-wait * scale:.0f} s "
                     f"({(-wait - old_wait) * scale:+.0f})")
    # Background replans: the old one ran to its deadline (ahead x 7.5 s).
    fence_bg = 4 * 7.5 / scale
    old_bg, old_bg_wait = _bg_total(mid, None, 25, fence_bg)
    lines += ["", f"Pozadinski plan, {len(mid)} tabli, od sirine 25, {4 * 7.5:.0f} s: stari skor "
              f"{old_bg:.0f}, racunanje {old_bg_wait * scale:.0f} s"]
    for rule in [dict(planner.STOP_RULE)] + [r for r in _rules() if r["min_width"] == 10]:
        score, wait = _bg_total(mid, rule, 25, fence_bg)
        lines.append(f"    prag {rule['min_gain'] * 100:.2f} %, isplativost {rule['gain_per_second'] * 100:.2f} %/s: "
                     f"skor {score:.0f} ({score - old_bg:+.0f}), racunanje {wait * scale:.0f} s "
                     f"({(wait - old_bg_wait) * scale:+.0f})")
    lines += ["", f"Trenutno planner.STOP_RULE {planner.STOP_RULE}, granica {args.fence:.0f} s, po tabli:"]
    rule = planner.STOP_RULE
    for (session, name, p), rows in sorted(first.items()):
        value, waited, run, why = replay_rule(rows, rule, budget=args.fence / scale)
        ov, ow, _, _ = replay_old(rows, fence_old)
        lines.append(f"  {session} {name}: {value:.0f} (staro {ov:.0f}), {waited * scale:.0f} s "
                     f"(staro {ow * scale:.0f}), sirine {run}, {why}")
    score, wait = _first_total(first, rule, args.fence / scale)
    lines.append(f"  ukupno: skor {score:.0f} prema starom {old_score:.0f} ({score - old_score:+.0f}), "
                 f"cekanje {wait * scale:.0f} s prema {old_wait * scale:.0f} s")
    out = Path(args.out).with_suffix(".txt")
    out.write_text(NL.join(lines) + NL, encoding="utf-8")
    print(NL.join(lines))


def replay_old(rows, seconds):
    """The old first plan: stop_early by PASS_TIME_GROWTH, cut pass counted to the deadline."""
    from strategy_lab import planner

    best = None
    waited = 0.0
    last = None
    for width in sorted(rows):
        r = rows[width]
        if last is not None and last[1] * width / last[0] * planner.PASS_TIME_GROWTH > seconds - waited:
            break
        if waited + r["seconds"] > seconds:
            waited = seconds
            break
        waited += r["seconds"]
        last = (width, r["seconds"])
        if best is None or r["value"] >= best:
            best = r["value"]
    return best, waited, None, None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--widths", default="1,4,10,25,60,150")
    parser.add_argument("--all-cores", action="store_true", help="sva jezgra, idle prioritet")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="zive sekunde po izmerenoj sekundi (za poredjenje sa 150 s)")
    parser.add_argument("--fence", type=float, default=150.0, help="gornja granica prvog plana (zive s)")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    if args.evaluate:
        evaluate(args)
    else:
        measure(args)


if __name__ == "__main__":
    main()
