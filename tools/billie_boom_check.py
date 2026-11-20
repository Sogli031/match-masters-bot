"""Billie Boom (41): every recorded activation against the simulator.

    python tools/billie_boom_check.py [Debug/research/FOLDER ...]

Each pair NNN -> NNN+1 whose action is activate_booster is replayed 1:1
(refill_input detail, the recorded engine RNG) and compared on the board, the
specials, the RNG counter, the score and the meter. The sucked colour group the
simulator chose is printed next to the miss so a wrong choice is visible.

Without arguments the Billie Boom fixtures are used (tests/fixtures/
billie_boom). Report on screen; exit status 1 when an activation is not exact.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
from tools.analyze_research import grid, load, local_player, observed

BOOSTER = 41
DEFAULT = (ROOT / "tests" / "fixtures" / "billie_boom")


def _folders(args) -> list[Path]:
    if args:
        return [Path(a) for a in args]
    return sorted(p for p in DEFAULT.iterdir() if p.is_dir()) if DEFAULT.is_dir() else []


def _detail(record):
    marker = record.get("refill_input")
    if isinstance(marker, (list, tuple)) and len(marker) > 2 and isinstance(marker[2], dict):
        return marker[2]
    return None


def _activation(path_a, path_b, a, b) -> str | None:
    """Why this pair is not a usable activation (or None)."""
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


def check_pair(rec_a, cap_a, rec_b):
    from strategy_lab import simulation

    # The activation is measured, not planned: step refuses it until the
    # colour-pair pick converges (simulation.BILLIE_BOOM_PORTED).
    simulation.BILLIE_BOOM_PORTED = True
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        resolved = resolve_refill_overrides(cap_a["profile"])
        thresholds = None if resolved.get("resolved") else next(
            iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
        lab = lab_move(cap_a, thresholds=thresholds)
        lab["check_cascade_timing"] = True
        lab["booster_type"] = BOOSTER
        result = simulation.step(lab, {"kind": "booster"})
    except Exception as exc:
        return {"skip": f"{type(exc).__name__}: {exc}"}
    finally:
        simulation.PREFIX_MODES = certified
    if not result.get("supported"):
        return {"skip": result.get("reason") or "simulator"}
    state = result["state"]
    want = observed(rec_b)
    board, special = grid(state["board"]), grid(state["special_board"])
    me_a, me_b = local_player(rec_a), local_player(rec_b)
    colors = next((e.get("colors") for e in result.get("intent_events") or ()
                   if e.get("type") == "billie_booster_colors"), None)
    return {
        "cells": sum(board[r][c] != want["board"][r][c]
                     for r in range(len(board)) for c in range(len(board[r]))),
        "specials": sum(special[r][c] != want["special_board"][r][c]
                        for r in range(len(special)) for c in range(len(special[r]))),
        "rng": (want["rng"], state["engine_refill"].rng.counter),
        "points": ((me_b.get("score") or 0) - (me_a.get("score") or 0), result.get("score_gain")),
        "charge": (me_b.get("energy"), (state.get("booster_state") or {}).get("current")),
        "colors": colors,
    }


def analyze(folder: Path) -> tuple[list[str], int, int]:
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    lines = [f"Sesija: {folder.name}, snimaka: {len(files)}"]
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
        got = check_pair(rec_a, cap_a, rec_b)
        if "skip" in got:
            lines.append(f"{head}: NIJE PROVERENO - {got['skip']}")
            continue
        wrong = []
        if got["cells"]:
            wrong.append(f"tabla {got['cells']} polja")
        if got["specials"]:
            wrong.append(f"specijali {got['specials']}")
        if got["rng"][0] is not None and got["rng"][0] != got["rng"][1]:
            wrong.append(f"rng {got['rng'][0]}/{got['rng'][1]}")
        if got["points"][0] != got["points"][1]:
            wrong.append(f"poeni {got['points'][0]}/{got['points'][1]}")
        if got["charge"][0] is not None and got["charge"][0] != got["charge"][1]:
            wrong.append(f"metar {got['charge'][0]}/{got['charge'][1]}")
        exact += not wrong
        colors = f", boje {got['colors']}" if got.get("colors") else ""
        lines.append(f"{head}: {'TACNO' if not wrong else 'RAZLIKA: ' + ', '.join(wrong)}{colors}")
    return lines, exact, usable


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    total = total_exact = 0
    report = []
    for folder in _folders(args):
        lines, exact, usable = analyze(folder)
        report.extend(lines)
        total += usable
        total_exact += exact
    report.append("")
    report.append(f"UKUPNO: tacno {total_exact} od {total} upotrebljivih aktivacija")
    text = "\n".join(report)
    print(text)
    for folder in _folders(args):
        (folder / "billie_boom_check.txt").write_text(text, encoding="utf-8")
        break
    return 0 if total_exact == total else 1


if __name__ == "__main__":
    sys.exit(main())
