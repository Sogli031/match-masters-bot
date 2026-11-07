"""Test Color Crush cascade-wipe hypotheses against a recorded research session.

For each non-booster pair, every legal swipe (+ Teleport perk path) is played
through the exact refill model while the engine's crush wipe follows one of
several rule variants. A variant passes a pair only when the whole action
matches the recorded post-board, post-specials and RNG counter.

Variants:
  A  port's current rule: wipe only on the direct swipe (cascade 1)
  B  once per move, first cascade wave containing a crushable match
  C  each color crushed once per move, at the wave where it first matches
  D  B, but tiles ON A SPECIAL survive the wipe
  E  C + the same special-sparing exception
  N  no wipe at all

    python tools/crush_wipe_lab.py [Debug/research/FOLDER] [--pairs 000,004]
"""
from __future__ import annotations

import argparse
import importlib
import io
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VARIANT_CODE = r'''
def _crush_gate(cascade_number, matches, board, special_board, variant):
    Recorded per-move state: first call is cascade 1.
    colors_landed = {
        match.color for match in matches
        if match.color not in color_crush_inert_colors() and _is_normal_color(match.color)
    }
    if variant in ("A",):
        water = cascade_number == 1
        return _color_crush_cells(board, matches) if water else set()

    if variant in ("B", "D", "E", "C"):
        if cascade_number == 1:
            _CRUSH_MEMO.clear(); _CRUSH_MEMO["fired"] = False
            _CRUSH_MEMO["colors"] = set()
        if variant in ("B", "D"):
            if _CRUSH_MEMO.get("fired"):
                return set()
        target_colors = (
            colors_landed - _CRUSH_MEMO.get("colors", set()) if variant in ("C", "E")
            else colors_landed
        )
        if not target_colors:
            return set()
        _CRUSH_MEMO["fired"] = True
        _CRUSH_MEMO.setdefault("colors", set()).update(target_colors)
        cells = set()
        for row, line in enumerate(board):
            for col, value in enumerate(line):
                if value in target_colors:
                    if variant in ("D", "E") and special_board[row][col]:
                        continue
                    cells.add((row, col))
        return cells
    return set()
'''

VARIANT_CODE = VARIANT_CODE.replace(
    "def _crush_gate(cascade_number, matches, board, special_board, variant):\n    Recorded per-move state: first call is cascade 1.\n",
    """_CRUSH_MEMO: dict = {}

def _crush_gate(cascade_number, matches, board, special_board, variant):
    # Per-move memo; cascade 1 starts the move.
""",
)

WIPE_BLOCK_OLD = """    if _COLOR_CRUSH_ACTIVE and cascade_number == 1:
        initial_cells.update(_color_crush_cells(board, matches))"""

WIPE_BLOCK_NEW = """    if _COLOR_CRUSH_ACTIVE and variant_number != "N":
        gate_cells = _crush_gate(cascade_number, matches, board, special_board, variant_number)
        if gate_cells:
            initial_cells.update(gate_cells)"""


def build_variant_module(path: str):
    source = Path(path).read_text(encoding="utf-8")
    if WIPE_BLOCK_OLD not in source:
        raise RuntimeError("crush wipe block not found")
    source = source.replace(WIPE_BLOCK_OLD, WIPE_BLOCK_NEW)
    module = types.ModuleType("move_strategy")
    module.__name__ = "move_strategy"
    module.__file__ = path
    module.__dict__["variant_number"] = "A"
    # dataclasses resolve postponed annotations through sys.modules[cls.__module__]
    sys.modules.setdefault("move_strategy", module)
    exec(compile(source, path, "exec"), module.__dict__)
    exec(VARIANT_CODE, module.__dict__)
    return module


def main(argv=None):
    argp = argparse.ArgumentParser()
    argp.add_argument("folder", nargs="?", type=Path)
    argp.add_argument("--pairs", type=str, default=None)
    args = argp.parse_args(argv)
    folder = args.folder
    if folder is None:
        sessions = sorted(p for p in (ROOT / "Debug/research").glob("*") if p.is_dir())
        if not sessions:
            print("Nema sesija")
            return 1
        folder = sessions[-1]

    # Publish the variant module as move_strategy BEFORE anything imports it.
    variant_module = build_variant_module(str(ROOT / "move_strategy.py"))
    sys.modules["move_strategy"] = variant_module

    from strategy_lab import planner
    from simulator_capture import lab_move, resolve_refill_overrides, threshold_hypotheses
    from strategy_lab.simulation import step
    from tools.analyze_research import booster_used, load, observed

    variants = ["A", "B", "C", "D", "E", "N"]
    score = {v: {"yes": 0, "no": 0} for v in variants}
    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    only = {p.strip() for p in args.pairs.split(",")} if args.pairs else None
    for a, b in zip(files, files[1:]):
        if only is not None and a.stem not in only:
            continue
        rec_a, cap_a = load(a)
        rec_b, _ = load(b)
        pre, want = observed(rec_a), observed(rec_b)
        if rec_a["profile"]["rng"].get("_seed") != rec_b["profile"]["rng"].get("_seed"):
            continue
        if booster_used(rec_a, rec_b):
            continue
        resolved = resolve_refill_overrides(cap_a["profile"])
        hypotheses = ({None: None} if resolved.get("resolved")
                      else dict(resolved.get("threshold_hypotheses") or {}))
        for name, thresholds in threshold_hypotheses(cap_a["profile"]).items():
            hypotheses.setdefault(name, thresholds)

        results = {}
        for rule in variants:
            variant_module.__dict__["variant_number"] = rule
            hits = []
            for hyp_name, thresholds in hypotheses.items():
                lab = lab_move(cap_a, thresholds=thresholds)
                lab["perks"] = {22: 1, 3: 1}
                matched = None
                for action in planner.actions(lab):
                    result = step(lab, action)
                    if not result.get("supported"):
                        continue
                    after = result["state"]
                    got = [[int(v) for v in row] for row in after["board"]]
                    got_spec = [[int(v) for v in row] for row in after["special_board"]]
                    if (got == want["board"] and got_spec == want["special_board"]
                            and after["engine_refill"].rng.counter == want["rng"]):
                        matched = (hyp_name, planner.describe(action))
                        break
                if matched:
                    hits.append(matched)
                    break
            results[rule] = hits[:1]
            score[rule]["yes" if hits else "no"] += 1
        summary = " ".join(
            f"{rule}{'Y' if results[rule] else '.'}" for rule in variants
        )
        print(f"{a.stem}->{b.stem} delta {want['rng'] - pre['rng']}: {summary}")
        for rule in variants:
            if results[rule]:
                print(f"    {rule}: {results[rule][0][0]} {results[rule][0][1]}")
    print("score:", {v: f"{d['yes']}Y/{d['no']}N" for v, d in score.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
