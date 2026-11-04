"""Measure what attaching the memory reader actually costs, phase by phase.

The reader used to freeze the game when it was attached before a match had
started. Two explanations fit that symptom and they call for different fixes:

  * the attach itself is fragile (namespace bypass, libil2cpp not up yet), or
  * the *poll* is -- outside a match nothing can be cached, so every cycle pays
    a full `Il2Cpp.gc.choose` heap walk, at 100 ms, in the lobby, where the
    game allocates hardest.

This script separates them. It times each attach phase, then repeatedly calls
the agent's `probe` export, which measures one cold heap walk and nothing else.
No poll is ever opened: the agent starts idle and only `configure` turns the
poll on, which this script deliberately never calls.

Run it, sit in the lobby for a minute, enter a match, play a few moves, leave.
The log then says how expensive an idle attach is, and whether the game
survives it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import matchmasters_board_reader as reader  # noqa: E402

DEFAULT_LOG = reader.PROJECT_ROOT / "Debug" / "memory_board" / "attach_cost.jsonl"


class Phases:
    """Wall clock per attach step, so a crash names the step it died on."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, float]] = []
        self._start = time.perf_counter()

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.entries.append((name, now - self._start))
        self._start = now
        print(f"  {name}: {self.entries[-1][1] * 1000:.0f} ms", flush=True)

    def as_dict(self) -> dict[str, float]:
        return {name: round(seconds * 1000, 1) for name, seconds in self.entries}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=2.0, help="sekundi izmedju merenja")
    parser.add_argument("--seconds", type=float, default=0.0, help="0 = do Ctrl+C")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="u partiji izmeri i cenu jednog celog snapshot-a",
    )
    args = parser.parse_args(argv)

    phases = Phases()
    print("Kacim se (bez polla)...", flush=True)
    adb = reader.find_adb()
    phases.mark("find_adb")
    serial = reader.discover_serial(adb)
    phases.mark(f"discover_serial ({serial})")
    reader.ensure_frida_server(adb, serial)
    phases.mark("ensure_frida_server")

    receiver = reader.BoardReader(
        reader.DEFAULT_OUTPUT, reader.DEFAULT_LATEST, quiet=True
    )
    device, session, script, pid = reader.attach_reader(
        adb,
        serial,
        reader.DEFAULT_PACKAGE,
        reader.DEFAULT_AGENT,
        receiver,
        spawn=False,
        # attach_reader always ends with `configure`, which opens the poll.
        # A long interval and the minimum sample count keep that poll as close
        # to idle as the current agent allows; the probe below is what the
        # measurement actually reads.
        poll_seconds=10.0,
        include_state=False,
        stable_samples=2,
    )
    phases.mark("attach + agent ready")
    print(f"PID {pid}, log: {args.log}", flush=True)
    print("Sedi u lobiju ~1 min, pa udji u partiju. Ctrl+C za kraj.\n", flush=True)

    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "attach",
                    "time": time.time(),
                    "pid": pid,
                    "serial": serial,
                    "phases_ms": phases.as_dict(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        handle.flush()

        samples: list[dict] = []
        deadline = time.time() + args.seconds if args.seconds > 0 else None
        try:
            while deadline is None or time.time() < deadline:
                if receiver.detached_event.is_set():
                    print(f"\nSESIJA PREKINUTA: {receiver.last_error}", flush=True)
                    break
                started = time.perf_counter()
                try:
                    result = script.exports_sync.probe(bool(args.snapshot))
                except Exception as exc:  # the game died or the RPC hung
                    result = {"rpc_error": str(exc)}
                result["rpc_ms"] = round((time.perf_counter() - started) * 1000, 1)
                result["time"] = time.time()
                result["type"] = "probe"
                samples.append(result)
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
                extra = ""
                if result.get("snapshot_ms") is not None:
                    extra = f" snapshot={result['snapshot_ms']}ms"
                if result.get("rpc_error"):
                    extra = f" RPC GRESKA: {result['rpc_error']}"
                # `hasBoard` says "match" in the lobby too (measured), so the
                # print shows the fields that might tell them apart instead of
                # a verdict that is known to be wrong.
                print(
                    f"[{time.strftime('%H:%M:%S')}] "
                    f"choose={result.get('choose_ms')}ms static={result.get('static_read_ms')}ms "
                    f"GameCount={result.get('game_count')} state={result.get('game_state')} "
                    f"moves={result.get('moves')} turns={result.get('turns')}/{result.get('turns_total')} "
                    f"igraca={result.get('players')} instanci={result.get('instances')} "
                    f"hook={result.get('ctor_hook')} "
                    f"({result.get('resolve_by_hook')}/{result.get('resolve_by_choose')})"
                    f"{extra}",
                    flush=True,
                )
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nPrekinuto.", flush=True)

    _summarise(samples)
    for handle_, method in ((script, "unload"), (session, "detach")):
        try:
            getattr(handle_, method)()
        except Exception:
            pass
    return 0


def _summarise(samples: list[dict]) -> None:
    def report(label: str, rows: list[dict]) -> None:
        values = [row["choose_ms"] for row in rows if isinstance(row.get("choose_ms"), (int, float))]
        if not values:
            print(f"{label}: nema merenja")
            return
        print(
            f"{label}: n={len(values)} "
            f"median={statistics.median(values):.0f}ms "
            f"max={max(values):.0f}ms "
            f"instanci={rows[-1].get('instances')}"
        )

    print("\n--- rezultat ---")
    report("sve    ", samples)
    statics = [
        row["static_read_ms"] for row in samples
        if isinstance(row.get("static_read_ms"), (int, float))
    ]
    if statics:
        print(f"static read: median={statistics.median(statics):.0f}ms max={max(statics):.0f}ms")
    # Which fields actually change between lobby and match is the whole point
    # of this pass, so the summary lists their distinct values in order.
    for field in ("game_count", "game_state", "moves", "turns_total", "players"):
        seen: list = []
        for row in samples:
            value = row.get(field)
            if not seen or seen[-1] != value:
                seen.append(value)
        print(f"{field}: {seen}")
    snapshots = [
        row["snapshot_ms"] for row in samples if isinstance(row.get("snapshot_ms"), (int, float))
    ]
    if snapshots:
        print(f"snapshot: median={statistics.median(snapshots):.0f}ms max={max(snapshots):.0f}ms")
    errors = [row for row in samples if row.get("rpc_error") or row.get("error")]
    if errors:
        print(f"gresaka: {len(errors)} (poslednja: {errors[-1].get('rpc_error') or errors[-1].get('error')})")


if __name__ == "__main__":
    raise SystemExit(main())
