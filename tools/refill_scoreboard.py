"""Koliko simulator pogadja dopunu, po modu.

    python tools/refill_scoreboard.py [--since 2026-11-19]
        Tabela iz Debug/refill_stats.jsonl (svaki provereni potez uzivo,
        refill_monitor.log_verdict).
    python tools/refill_scoreboard.py --replay
        Ponovo proveri svaki sacuvan promasaj iz Debug/refill_misses sa danasnjim
        kodom. Napredak: Debug/refill_scoreboard/progress.txt, rezultat:
        results.jsonl. Pre upisa stari rezultat ide u results.prev.jsonl, pa
        izvestaj kaze sta je od proslog puta popravljeno, a sta pokvareno.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "Debug/refill_scoreboard"
UNCHECKED = ("unsupported", "booster", "gap", "opponent")


def table(rows) -> str:
    """rows: (mode, verdict) pairs -> per-mode lines, worst hit rate first."""
    by_mode = defaultdict(Counter)
    for mode, verdict in rows:
        by_mode[mode or "?"][verdict] += 1
    lines = []
    for mode, c in by_mode.items():
        checked = c["ok"] + c["miss"]
        rate = 100 * c["ok"] / checked if checked else None
        lines.append((rate if rate is not None else 101, -c["miss"], mode, c, checked))
    lines.sort()
    out = [f"{'mod':32} {'pogodak':>8} {'promasaj':>8} {'%':>5} {'neprov.':>8} {'ostalo':>7}"]
    for rate, _, mode, c, checked in lines:
        pct = f"{rate:.0f}" if checked else "-"
        other = sum(v for k, v in c.items() if k not in ("ok", "miss") + UNCHECKED)
        out.append(f"{mode[:32]:32} {c['ok']:>8} {c['miss']:>8} {pct:>5} "
                   f"{sum(c[k] for k in UNCHECKED):>8} {other:>7}")
    return "\n".join(out)


def live(since=None, path=None) -> str:
    path = path or ROOT / "Debug/refill_stats.jsonl"
    if not path.exists():
        return f"{path} jos ne postoji: pusti bota da odigra partiju sa ukljucenom proverom dopune."
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if since is None or item.get("time", "") >= since:
            rows.append((item.get("mode"), item.get("verdict")))
    return table(rows)


def mode_of(folder: Path) -> str:
    """20261119_203212_264442_crystal-cave-master-league -> crystal-cave-master-league"""
    return folder.name.split("_", 3)[-1]


def replay_one(folder: str) -> dict:
    import contextlib
    import io

    from refill_monitor import check_transition
    from simulator_capture import capture_mode
    from strategy_lab import simulation

    folder = Path(folder)
    result = {"folder": folder.name, "mode": mode_of(folder)}
    try:
        a, b = (json.loads((folder / name).read_text(encoding="utf-8")) for name in ("000.json", "001.json"))
        # As TransitionChecker.handle: measuring is allowed outside the certified modes.
        simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(a["profile"]).value}
        with contextlib.redirect_stdout(io.StringIO()):
            move = check_transition(a, b)
        result.update(verdict=move["verdict"] if move else "none", detail=(move or {}).get("detail", ""))
    except Exception as exc:
        result.update(verdict="error", detail=f"{type(exc).__name__}: {exc}")
    return result


def changes(previous: dict, current: list) -> str:
    fixed = [r["folder"] for r in current if r["verdict"] == "ok" and previous.get(r["folder"], "ok") != "ok"]
    broken = [r["folder"] for r in current if r["verdict"] != "ok" and previous.get(r["folder"]) == "ok"]
    lines = [f"Od proslog puta: popravljeno {len(fixed)}, pokvareno {len(broken)}"]
    lines += [f"  POKVARENO {name}" for name in broken]
    return "\n".join(lines)


def replay(misses=None) -> str:
    from tools.gentle import gentle_pool

    misses = misses or ROOT / "Debug/refill_misses"
    items = [str(d) for d in sorted(misses.iterdir()) if (d / "000.json").is_file() and (d / "001.json").is_file()]
    OUT.mkdir(parents=True, exist_ok=True)
    progress, results = OUT / "progress.txt", OUT / "results.jsonl"
    previous = {}
    if results.exists():
        for line in results.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            previous[item["folder"]] = item["verdict"]
        results.replace(OUT / "results.prev.jsonl")
    started = time.monotonic()
    progress.write_text(f"0/{len(items)} pocetak {time.strftime('%H:%M:%S')}\n", encoding="utf-8")
    current = []
    with gentle_pool() as pool, results.open("w", encoding="utf-8") as sink:
        for done, item in enumerate(pool.imap_unordered(replay_one, items), 1):
            current.append(item)
            sink.write(json.dumps(item) + "\n")
            sink.flush()
            elapsed = time.monotonic() - started
            end = time.time() + elapsed / done * (len(items) - done)
            with progress.open("a", encoding="utf-8") as fh:
                fh.write(f"{done}/{len(items)} proteklo {elapsed:.0f} s, kraj oko "
                         f"{time.strftime('%H:%M', time.localtime(end))}\n")
    total = Counter(r["verdict"] for r in current)
    report = (f"Sacuvanih promasaja: {len(current)}; sada: "
              + ", ".join(f"{k} {v}" for k, v in total.most_common()) + "\n\n"
              + table((r["mode"], r["verdict"]) for r in current))
    if previous:
        report += "\n\n" + changes(previous, current)
    (OUT / "report.txt").write_text(report + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", help="samo potezi od ovog vremena, npr. 2026-11-19")
    parser.add_argument("--replay", action="store_true", help="ponovo proveri sacuvane promasaje")
    args = parser.parse_args(argv)
    print(replay() if args.replay else live(args.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
