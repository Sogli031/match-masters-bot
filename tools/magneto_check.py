"""El Magneto SE (booster 48): every recorded activation against the simulator.

    python tools/magneto_check.py [--captured] [FOLDER ...]

Each pair NNN -> NNN+1 whose action is activate_booster is replayed 1:1 (the
recorded engine RNG) and compared on the board, the specials, the RNG counter,
the score and the meter.

Two modes, because the port has two halves:

* ``--captured`` feeds the path the snapshot recorded (``<magnets>`` with
  ``<colors>`` from the after-record), so only the geometry -- the swaps
  ``MakeColorSwaps`` makes -- is under test;
* without it, ``engine_magneto.predict`` builds the path from the code (the
  m-subsets of the board colours minus the player's and red, the four side
  middles), so the pick is under test too.

The report goes to FOLDER/magneto_check.txt as well as the screen; the exit
status is 1 when an activation is not exact.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move, resolve_refill_overrides   # noqa: E402
from tools.analyze_research import grid, load, local_player, observed            # noqa: E402

BOOSTER = 48
DEFAULT = ROOT / "tests" / "fixtures" / "el_magneto_se"


def _folders(args) -> list[Path]:
    args = [a for a in args if not a.startswith("--")]
    if args:
        return [Path(a) for a in args]
    return sorted(p for p in DEFAULT.iterdir() if p.is_dir()) if DEFAULT.is_dir() else []


def _detail(record):
    marker = record.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) > 2 and isinstance(marker[2], dict):
        return marker[2]
    return None


def _activation(path_a, path_b, a, b) -> str | None:
    detail = _detail(b)
    if not detail or detail.get("action") != "activate_booster":
        return "nije aktivacija"
    if int(path_b.stem) - int(path_a.stem) != 1:
        return "preskocena tabla"
    marker_a, marker_b = a.get("refill_input"), b.get("refill_input")
    if (isinstance(marker_a, (list, tuple)) and isinstance(marker_b, (list, tuple))
            and marker_a and marker_b and marker_a[0] == marker_b[0]):
        return "rucni/protivnikov potez"
    if detail.get("manual"):
        return "manual"
    return None


def captured_path(record):
    """The path the game played, from the after-record's ability fields."""
    fields = ((record.get("profile") or {}).get("ability_detail") or {}).get("fields") or {}
    magnets = [(int(p["x"]), int(p["y"])) for p in fields.get("<magnets>k__BackingField") or ()]
    colors = [int(c) for c in fields.get("<colors>k__BackingField") or ()]
    if not magnets or len(magnets) != len(colors):
        return None
    return list(zip(magnets, colors))


def check_pair(rec_a, cap_a, rec_b, captured):
    import engine_magneto
    from strategy_lab import simulation

    # The activation is measured, not planned: step refuses it until the pick
    # converges (simulation.EL_MAGNETO_SE_PORTED).
    simulation.EL_MAGNETO_SE_PORTED = True
    engine_magneto.OVERRIDE_PATH = captured_path(rec_b) if captured else None
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        resolved = resolve_refill_overrides(cap_a["profile"])
        thresholds = None if resolved.get("resolved") else next(
            iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
        lab = lab_move(cap_a, thresholds=thresholds)
        lab["check_cascade_timing"] = True
        lab["booster_type"] = BOOSTER
        path = engine_magneto.OVERRIDE_PATH
        result = simulation.step(lab, {"kind": "booster"})
    except Exception as exc:                      # noqa: BLE001 — reported, not hidden
        return {"skip": f"{type(exc).__name__}: {exc}"}
    finally:
        simulation.PREFIX_MODES = certified
        engine_magneto.OVERRIDE_PATH = None
    if not result.get("supported"):
        return {"skip": result.get("reason") or "simulator"}
    state = result["state"]
    want = observed(rec_b)
    board, special = grid(state["board"]), grid(state["special_board"])
    me_a, me_b = local_player(rec_a), local_player(rec_b)
    return {
        "cells": sum(board[r][c] != want["board"][r][c]
                     for r in range(len(board)) for c in range(len(board[r]))),
        "specials": sum(special[r][c] != want["special_board"][r][c]
                        for r in range(len(special)) for c in range(len(special[r]))),
        "rng": (want["rng"], state["engine_refill"].rng.counter),
        "points": ((me_b.get("score") or 0) - (me_a.get("score") or 0), result.get("score_gain")),
        "charge": (me_b.get("energy"), (state.get("booster_state") or {}).get("current")),
        "path": path,
        "intent": [e for e in result.get("intent_events") or () if e.get("type", "").startswith("magneto")],
    }


def analyze(folder: Path, captured: bool) -> tuple[list[str], int, int]:
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    lines = [f"Sesija: {folder.name}, snimaka: {len(files)}, "
             f"rezim: {'snimljena putanja' if captured else 'izbor iz koda'}"]
    exact = usable = 0
    for a, b in zip(files, files[1:]):
        rec_a, cap_a = load(a)
        rec_b, _ = load(b)
        head = f"{a.stem}->{b.stem}"
        why = _activation(a, b, rec_a, rec_b)
        if why:
            if why != "nije aktivacija":
                lines.append(f"{head}: PRESKOCENO - {why}")
            continue
        usable += 1
        got = check_pair(rec_a, cap_a, rec_b, captured)
        if "skip" in got:
            lines.append(f"{head}: NIJE PROVERENO - {got['skip']}")
            continue
        wrong = []
        if got["cells"]:
            wrong.append(f"tabla {got['cells']} polja")
        if got["specials"]:
            wrong.append(f"specijali {got['specials']}")
        if got["rng"][0] != got["rng"][1]:
            wrong.append(f"rng {got['rng'][0]} vs {got['rng'][1]}")
        if got["points"][0] != got["points"][1]:
            wrong.append(f"poeni {got['points'][0]} vs {got['points'][1]}")
        if got["charge"][0] != got["charge"][1]:
            wrong.append(f"metar {got['charge'][0]} vs {got['charge'][1]}")
        exact += not wrong
        path = got["path"] or ()
        detail = (f"putanja {[(m, c) for m, c in path]}, tabla {got['cells']} polja, "
                  f"specijali {got['specials']}, rng {got['rng'][0]}->{got['rng'][1]}, "
                  f"poeni +{got['points'][0]} (port +{got['points'][1]}), "
                  f"metar {got['charge'][0]}->{got['charge'][1]}")
        lines.append(f"{head}: {'TACNO' if not wrong else 'RAZLIKA: ' + ', '.join(wrong)}\n    {detail}")
    lines.append("")
    lines.append(f"UKUPNO: tacno u {exact} od {usable} aktivacija "
                 f"({'geometrija' if captured else 'geometrija + izbor'})")
    return lines, exact, usable


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    captured = "--captured" in args
    folders = _folders(args)
    if not folders:
        print("nema foldera sa snimcima")
        return 2
    status = 0
    for folder in folders:
        lines, exact, usable = analyze(folder, captured)
        text = "\n".join(lines)
        (folder / "magneto_check.txt").write_text(text, encoding="utf-8")
        print(text)
        if exact != usable:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
