"""Check engine_foxy_powerup against recorded Foxy Roxy SE powerup activations.

    python tools/check_foxy_powerup.py [refill_misses folders...]

Each refill miss of a booster carries the game's own trace (swap_traces):
the RNG before Use, the RNG when Use ended, the board before and at the
first destroy pass. The plain paint (engine_foxy.paint) draws first, then the
variant; the painted cells and the RNG at the end of Use must agree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(folder: Path):
    import engine_foxy
    import engine_foxy_powerup as fp
    from engine_refill import SIM_TO_ENGINE
    from engine_rng import EngineRNG

    before = json.loads((folder / "000.json").read_text(encoding="utf-8"))
    after = json.loads((folder / "001.json").read_text(encoding="utf-8"))
    traces = [t for t in after.get("swap_traces") or () if t.get("kind") == "booster"]
    if not traces:
        return f"{folder.name}: nema traga boostera"
    trace = traces[0]
    grid = trace["grid"]
    destroy = next((e for e in trace["events"] if e.get("type") == "destroy_pass" and e.get("grid")), None)
    profile = before["profile"]
    rng = EngineRNG.from_capture(profile)
    if rng.counter != trace["before_rng_counter"]:
        return f"{folder.name}: RNG snimka {rng.counter} != trag {trace['before_rng_counter']}"
    board, special = before["board"], before["special_board"]
    local = next(p for p in before["snapshot_state"]["players"] if p.get("player_type") == 0)
    params = local.get("special_ability_params")
    config = engine_foxy.config_from_profile(profile, params)
    blue, red = 1, 5
    engine_foxy.paint(board, special, rng, config, blue, red)
    after_paint = rng.counter
    variant = fp.config_from(params, profile)
    view = fp.Board(board, special, SIM_TO_ENGINE,
                    lambda x, y: engine_foxy.participates(board, special, x, y))
    activations = int(profile.get("cleo_activates_this_turn") or 0) + 1
    patterns = fp.activation_patterns(view, rng, variant, activations)
    painted = {}
    for points, color in patterns:
        for p in points:
            if view.paintable(p):
                painted[p] = color
    want = {}
    if destroy:
        for y, row in enumerate(destroy["grid"]):
            for x, cell in enumerate(row):
                if cell[0] != grid[y][x][0]:
                    want[(x, y)] = cell[0]
    ok_rng = rng.counter == trace["use_rng_after"]
    ok_cells = all(painted.get(p) == c for p, c in want.items())
    return (f"{folder.name}: aktivacija {activations}, RNG posle paint {after_paint}, posle varijante "
            f"{rng.counter} (igra {trace['use_rng_after']}) {'OK' if ok_rng else 'RAZLIKA'}; "
            f"polja {'OK' if ok_cells else 'RAZLIKA'} (igra {len(want)}, mi {len(painted)}); "
            f"sabloni {[(len(p), c) for p, c in patterns]}")


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    folders = [Path(a) for a in args] or sorted((ROOT / "Debug/refill_misses").glob("20261118_091*_bombs-away"))
    for folder in folders:
        try:
            print(check(folder))
        except Exception as exc:  # a check: one odd record must not stop the rest
            print(f"{folder.name}: greska {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
