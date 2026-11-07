"""What a point of booster charge is actually worth, measured from played moves.

The scoring weights that arbitrate "points now" against "booster charge" were
hand-set and never checked against a match (see the 2026-06-20 note about the
starved calibration loop). The memory path closed that gap without anyone
noticing: every ``Debug/runs/*/observed_delta.json`` carries the booster charge
and our score from *before* and *after* the move, read out of the game itself.

Three numbers come out of that, all in the simulator's own units so they can be
dropped straight into the weights:

* ``charge_cell_value`` -- what one point of charge is worth. Measured as the
  median score an activation actually produces, divided by the meter size, then
  converted from game points into simulator units by the median
  ``points / instant_score`` ratio of ordinary moves.
* ``move_value`` -- what one move is worth (the median ``instant_score`` the bot
  plays), which is the floor on what an extra move is worth.
* ``spend_rate`` -- how much of the charge earned is ever spent, i.e. how much
  to discount charge that does not fill the meter yet.

Split by strategy context, because a Versus round and a Solo Challenge are
different economies: a Versus move is worth ~1.7 points per simulator unit, a
Solo one ~6.0.

    python .\\tools\\measure_charge_value.py            # print the table
    python .\\tools\\measure_charge_value.py --write    # ... and update data/charge_value.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = PROJECT_ROOT / "Debug" / "runs"
DEFAULT_TELEMETRY = PROJECT_ROOT / "Debug" / "telemetry" / "moves.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "charge_value.json"

# Below this a mode's numbers are noise and the caller keeps its own default.
MIN_ACTIVATIONS = 10
MIN_RATIOS = 20


def _empty_bucket() -> dict:
    return {
        "instant_scores": [],
        "point_ratios": [],
        "activation_points": [],
        "charge_gained": 0.0,
        "charge_spent": 0.0,
        "maximums": [],
    }


def _add_move(
    buckets: dict[str, dict],
    context: str,
    points: float,
    charge: float,
    maximum: object,
    instant: object,
) -> None:
    """Fold one played move into its context's bucket.

    Shared by both sources so the light always-on log and a full Debug run are
    measured by exactly the same rules -- otherwise the two would drift and the
    number would depend on which one happened to be recorded.
    """
    bucket = buckets[context]
    if maximum:
        bucket["maximums"].append(int(maximum))
    if charge < 0:
        # The booster fired: this move's score is what the booster bought.
        bucket["charge_spent"] += -charge
        bucket["activation_points"].append(points)
        return
    if charge > 0:
        bucket["charge_gained"] += charge
    if instant and instant > 0:
        bucket["instant_scores"].append(float(instant))
        if points > 0:
            bucket["point_ratios"].append(points / float(instant))


def _telemetry_samples(path: Path) -> dict[str, dict]:
    """The always-on log: one line per move, no images, no run directories."""
    buckets: dict[str, dict] = defaultdict(_empty_bucket)
    files = [path.with_name(path.stem + ".1" + path.suffix), path]
    for source in files:
        if not source.exists():
            continue
        for raw in source.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except ValueError:
                continue
            before, after = line.get("before") or {}, line.get("after") or {}
            if before.get("charge") is None or after.get("charge") is None:
                continue
            if before.get("score") is None or after.get("score") is None:
                continue
            points = after["score"] - before["score"]
            # A negative delta is a new match or a misread, not a move that lost
            # points -- there is no such move.
            if points < 0:
                continue
            _add_move(
                buckets,
                line.get("ctx") or "unknown",
                points,
                after["charge"] - before["charge"],
                before.get("max") or after.get("max"),
                (line.get("pred") or {}).get("instant"),
            )
    return buckets


def _samples(runs_dir: Path) -> dict[str, dict]:
    buckets: dict[str, dict] = defaultdict(_empty_bucket)
    if not runs_dir.exists():
        return buckets
    for run in sorted(runs_dir.glob("*/")):
        try:
            delta = json.loads((run / "observed_delta.json").read_text(encoding="utf-8"))
            move = json.loads((run / "move.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        state = delta.get("state_delta")
        if not isinstance(state, dict):
            continue
        before, after = state.get("before") or {}, state.get("after") or {}
        if any(
            before.get(key) is None or after.get(key) is None
            for key in ("booster_charge", "our_score")
        ):
            continue
        points = after["our_score"] - before["our_score"]
        # A negative delta is a new round or a misread, not a move that lost
        # points -- there is no such move.
        if points < 0:
            continue
        _add_move(
            buckets,
            (move.get("strategy_context") or {}).get("mode") or "unknown",
            points,
            after["booster_charge"] - before["booster_charge"],
            after.get("booster_maximum"),
            (move.get("best_move") or {}).get("instant_score"),
        )
    return buckets


def _merge(first: dict[str, dict], second: dict[str, dict]) -> dict[str, dict]:
    merged: dict[str, dict] = defaultdict(_empty_bucket)
    for source in (first, second):
        for context, bucket in source.items():
            target = merged[context]
            for key, value in bucket.items():
                if isinstance(value, list):
                    target[key].extend(value)
                else:
                    target[key] += value
    return merged


def measure(
    runs_dir: Path = DEFAULT_RUNS,
    telemetry_path: Path = DEFAULT_TELEMETRY,
) -> dict:
    # Both sources, because they overlap rather than duplicate: the always-on
    # log covers every move played since it was switched on, the Debug runs
    # cover the sessions recorded before it existed. A move recorded by both is
    # counted twice, which shifts a median by nothing worth the code to avoid.
    buckets = _merge(_telemetry_samples(telemetry_path), _samples(runs_dir))
    modes: dict[str, dict] = {}
    for context, bucket in buckets.items():
        activations = bucket["activation_points"]
        ratios = bucket["point_ratios"]
        if len(activations) < MIN_ACTIVATIONS or len(ratios) < MIN_RATIOS:
            continue
        maximum = st.mode(bucket["maximums"]) if bucket["maximums"] else 7
        points_per_unit = st.median(ratios)
        booster_points = st.median(activations)
        gained = bucket["charge_gained"]
        modes[context] = {
            "charge_cell_value": round(booster_points / maximum / points_per_unit, 2),
            "booster_value": round(booster_points / points_per_unit, 2),
            "move_value": round(st.median(bucket["instant_scores"]), 2),
            "spend_rate": round(
                min(1.0, bucket["charge_spent"] / gained) if gained else 1.0, 3
            ),
            "points_per_unit": round(points_per_unit, 3),
            "booster_maximum": int(maximum),
            "samples": {
                "activations": len(activations),
                "scored_moves": len(ratios),
            },
        }
    if modes:
        # The pooled value is what a context with too little data of its own
        # falls back to, weighted by how many activations each mode contributed.
        weights = {name: item["samples"]["activations"] for name, item in modes.items()}
        total = sum(weights.values())
        pooled = {
            key: round(
                sum(modes[name][key] * weights[name] for name in modes) / total, 2
            )
            for key in ("charge_cell_value", "booster_value", "move_value")
        }
        pooled["spend_rate"] = round(
            sum(modes[name]["spend_rate"] * weights[name] for name in modes) / total, 3
        )
        pooled["samples"] = {"activations": total}
    else:
        pooled = {}
    return {
        "measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs_dir": str(runs_dir),
        "telemetry": str(telemetry_path),
        "modes": modes,
        "pooled": pooled,
    }


def _format(report: dict) -> str:
    lines = [f"Mereno: {report['measured_at']}", ""]
    for name, item in sorted(report["modes"].items()):
        lines.append(f"--- {name}")
        lines.append(
            f"    jedno punjenje = {item['charge_cell_value']:5.1f} internih jedinica"
        )
        lines.append(
            f"    ceo buster     = {item['booster_value']:5.1f}"
            f"   (meter {item['booster_maximum']})"
        )
        lines.append(f"    jedan potez    = {item['move_value']:5.1f}")
        lines.append(
            f"    spend_rate={item['spend_rate']}  "
            f"poena/jedinica={item['points_per_unit']}  "
            f"uzorak: {item['samples']['activations']} aktivacija / "
            f"{item['samples']['scored_moves']} poteza"
        )
    if report["pooled"]:
        lines.append("")
        lines.append(
            f"pooled: punjenje={report['pooled']['charge_cell_value']} "
            f"buster={report['pooled']['booster_value']} "
            f"potez={report['pooled']['move_value']}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--telemetry", type=Path, default=DEFAULT_TELEMETRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--write", action="store_true", help="Snimi izmereno u data/charge_value.json"
    )
    args = parser.parse_args(argv)

    report = measure(args.runs, args.telemetry)
    if not report["modes"]:
        print(f"Nedovoljno podataka u {args.runs}")
        return 1
    print(_format(report))
    if args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nSnimljeno: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
