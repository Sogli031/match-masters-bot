"""Koliko Cleo simulacija pogadja igru: pogodio / promasio / nepoznato.

Za svaki odigrani Cleo potez u Debug/runs:
  * sa table pre/posle procita koju je boju igra izabrala (boja koja je
    izgubila najvise figura),
  * TRENUTNOM simulacijom (move_strategy) izracuna da li ta boja pravi extra
    za tacno taj smer prevlacenja,
  * uporedi sa brojacem poteza (da li je potez zadrzan).

Presuda i razlozi su isti kao u observed_delta.json -> "cleo_check" (vidi
runtime._cleo_prediction_check); ovde se samo predvidjanje po boji racuna
ponovo, da stari snimci proveravaju i novu simulaciju.

Usage:
    python tools/cleo_audit.py [--runs Debug/runs] [--since 2026-09-15_03]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402

COLOR_NAMES = {1: "plava", 2: "zelena", 3: "zuta", 4: "ljubicasta", 5: "crvena", 6: "narandzasta"}


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rule_context(move: dict) -> contextlib.ExitStack:
    """The match rules the live ranking ran under (runtime.compute_move).

    Without them a mode like "vertical matches destroy the colour" simulates a
    different board than the game played, and the check compares the wrong
    prediction.
    """
    stack = contextlib.ExitStack()
    toggles = (
        ("color_crush_active", move.get("color_crush")),
        ("mushroom_multipliers_active", move.get("mushroom_multipliers")),
        ("vertical_matches_destroy_color_active", move.get("vertical_matches_destroy_color")),
        ("matches_destroy_color_active", move.get("matches_destroy_color")),
        ("all_specials_lightning_active", move.get("all_specials_lightning")),
        ("every_match_is_special_active", move.get("every_match_is_special")),
    )
    for name, enabled in toggles:
        manager = getattr(ms, name, None) or getattr(runtime, name, None)
        if manager is not None and enabled is not None:
            stack.enter_context(manager(bool(enabled)))
    charge = getattr(ms, "charge_colors_active", None) or getattr(runtime, "charge_colors_active", None)
    if charge is not None:
        stack.enter_context(
            charge(move.get("energized_colors") or [], move.get("engine_charge_colors"))
        )
    lines = move.get("line_destruction")
    line_manager = getattr(ms, "line_destruction_active", None) or getattr(
        runtime, "line_destruction_active", None
    )
    if line_manager is not None and isinstance(lines, list) and len(lines) == 2:
        stack.enter_context(line_manager(*lines))
    return stack


def _current_prediction(move: dict) -> dict | None:
    """best_move with its cleo block re-simulated by the current code."""
    best = dict(move.get("best_move") or {})
    board, special = move.get("board"), move.get("special_board")
    start, target = best.get("start"), best.get("target")
    if not (board and special and start and target and best.get("direction")):
        return None
    start, target = tuple(start), tuple(target)
    swapped_board, swapped_special = ms.swap_cells(board, special, start, target)
    candidate = ms.MoveCandidate(
        start, target, ms.Direction(best["direction"]), swapped_board, swapped_special
    )
    with _rule_context(move):
        result = ms._simulate_cleo_candidate(
            candidate,
            allow_square_matches=bool(move.get("allow_square_matches")),
            include_future_value=False,
        )
    if result is None:
        return None
    best["cleo"] = {
        "scenario_colors": [int(color) for color in result.cleo_scenario_colors],
        "scenario_extra_moves": list(result.cleo_scenario_extra_moves),
        "extra_move_probability": result.cleo_extra_move_probability,
    }
    return best


def _fill_unmeasured_turn(delta: dict, run_dir: Path, move: dict) -> dict:
    """Measure the turn across non-move runs (e.g. a booster fired right after).

    The live delta is closed only by the next *move* decision's frame, and a
    booster activation in between leaves it unmeasured. A booster spends no
    move, so the counter on the next move run still answers the question.
    """
    state_delta = delta.get("state_delta") or {}
    if state_delta.get("turn_measured"):
        return delta
    before = (move.get("turn_state") or {}).get("remaining_moves")
    if before is None:
        return delta
    for later in sorted(p for p in run_dir.parent.iterdir() if p.name > run_dir.name):
        later_move = _load(later / "move.json")
        if not later_move:
            continue
        if later_move.get("selected_action") == "move":
            after = (later_move.get("turn_state") or {}).get("remaining_moves")
            if after is None or before - after not in (0, 1):
                return delta
            patched = dict(delta)
            patched["after_run"] = later.name
            patched["state_delta"] = dict(
                state_delta, kept_the_turn=after == before, turn_measured=True
            )
            return patched
        if later_move.get("selected_action") not in ("activate_booster", "none"):
            return delta
    return delta


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=ROOT / "Debug" / "runs")
    parser.add_argument("--since", default="", help="samo runovi od ovog imena naviše")
    args = parser.parse_args()

    tally: dict[str, int] = {}
    for run_dir in sorted(args.runs.iterdir()):
        if run_dir.name < args.since:
            continue
        move = _load(run_dir / "move.json")
        delta = _load(run_dir / "observed_delta.json")
        if not move or not delta or move.get("selected_action") != "move":
            continue
        if "cleo" not in (move.get("best_move") or {}):
            continue
        best = _current_prediction(move)
        if best is None:
            continue
        check = runtime._cleo_prediction_check(
            _fill_unmeasured_turn(delta, run_dir, move), best
        )
        if check is None:
            continue
        tally[check["verdict"]] = tally.get(check["verdict"], 0) + 1
        guess = check.get("actual_color_guess")
        predicted = check.get("predicted_extra_for_actual_color")
        kept = check.get("observed_kept_the_turn")
        print(
            f"{run_dir.name}  {'Cleo->figura' if check['drags_cleo'] else 'figura->Cleo':12} "
            f"P={float(check['predicted_probability'] or 0):.0%}  "
            f"boja={COLOR_NAMES.get(guess, guess)}{'' if check.get('actual_color') else '?'}  "
            f"sim={'extra' if predicted else 'bez' if predicted is False else '?':5} "
            f"igra={'zadrzao' if kept else 'izgubio' if kept is False else '?':7} "
            f"-> {check['verdict'].upper()}"
            + (f"  ({check['reason']})" if check.get("reason") else "")
        )
    hits, misses = tally.get("pogodio", 0), tally.get("promasio", 0)
    likely_hits = tally.get("verovatno pogodio", 0)
    likely_misses = tally.get("verovatno promasio", 0)
    print()
    print(
        f"sigurno: pogodio {hits}, promasio {misses}"
        + (f"  -> tacnost {hits / (hits + misses):.0%}" if hits + misses else "")
    )
    both_hits, both_misses = hits + likely_hits, misses + likely_misses
    print(
        f"sa 'verovatno' (brojac pao pre 8s): pogodio {both_hits}, promasio {both_misses}"
        + (
            f"  -> tacnost {both_hits / (both_hits + both_misses):.0%}"
            if both_hits + both_misses
            else ""
        )
    )
    print(f"nepoznato: {tally.get('nepoznato', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
