"""Monkey JooJoo (booster 40): first cell where the cascade leaves the game.

    python tools/monkey_trace.py Debug/research/FOLDER 002 [--candidates]

For one recorded activation (``002`` means ``002.json -> 003.json``) it plays
the ported throw and then prints, per cascade wave, the destroyed cells that
the game did NOT change between the two records. A cell the game refilled keeps
the same piece 1 time in ~8, so with ~5 waves over the board a cell that is
identical before and after was (almost surely) never destroyed: a wave that
destroys it is the first divergence.

Per wave it also shows the piece the game has there before and after and the
match (colour/kind) that destroyed it, so the fix can be aimed at one cell.

``--candidates`` plays each of the maxTries draws (`engine_monkey.activate`
candidate_index) and prints the same for each; the draw the game actually threw
need not be among them, which shows up as every candidate hitting cells the
game left alone already in the throw.

Output goes to FOLDER/monkey_trace_<NNN>.txt as well (AGENTS.md: never only the
screen).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from simulator_capture import capture_mode, lab_move, resolve_refill_overrides
from tools.analyze_research import grid, load, local_player, observed


def _changed(a, b):
    """Cells whose piece or special differs between the two resting boards."""
    cells = set()
    for name in ("board", "special_board"):
        grid_a, grid_b = a[name], b[name]
        for row in range(len(grid_a)):
            for col in range(len(grid_a[row])):
                if int(grid_a[row][col]) != int(grid_b[row][col]):
                    cells.add((row, col))
    return cells


def _record_waves():
    """Wrap the two clear passes so every cascade's destroyed cells are visible.

    The intent events carry match cells only -- a skull's own area or a chain
    special's cells are a count there -- so the first divergence inside the
    throw cannot be seen from `result.intent_events` alone.
    """
    import contextlib

    import move_strategy as ms

    waves = {}

    @contextlib.contextmanager
    def recording():
        original_specials = ms._clear_cells_with_specials
        original_matches = ms._clear_matches_with_details

        def specials(*args, **kwargs):
            out = original_specials(*args, **kwargs)
            waves.setdefault(int(kwargs.get("cascade_number") or 1), set()).update(out[2])
            return out

        def matches(*args, **kwargs):
            out = original_matches(*args, **kwargs)
            waves.setdefault(int(kwargs.get("cascade_number") or 1), set()).update(out[3])
            return out

        ms._clear_cells_with_specials = specials
        ms._clear_matches_with_details = matches
        try:
            yield waves
        finally:
            ms._clear_cells_with_specials = original_specials
            ms._clear_matches_with_details = original_matches

    return recording()


def trace(folder: Path, stem: str, index=None) -> list[str]:
    import engine_monkey
    import move_strategy as ms
    from strategy_lab import simulation

    files = sorted(folder.glob("[0-9][0-9][0-9].json"))
    before = folder / f"{stem}.json"
    position = files.index(before)
    after = files[position + 1]
    rec_a, cap_a = load(before)
    rec_b = load(after)[0]
    A, B = observed(rec_a), observed(rec_b)
    me_a, me_b = local_player(rec_a), local_player(rec_b)

    resolved = resolve_refill_overrides(cap_a["profile"])
    thresholds = None if resolved.get("resolved") else next(
        iter((resolved.get("threshold_hypotheses") or {None: None}).values()))
    lab = lab_move(cap_a, thresholds=thresholds)
    model = lab["engine_refill"]
    board, special = lab["board"], lab["special_board"]
    mode, square = lab["mode"], bool(lab.get("allow_square_matches"))
    params = None
    config = engine_monkey.config_from(cap_a["profile"], params)
    # The throw index only picks skullsPerActivation: 4 at the first throw, 1 after it.
    activations = 1 if not _skulls(A["special_board"]) else 2

    changed = _changed(A, B)
    lines = [f"{before.stem}->{after.stem}  kandidat {index}",
             f"  tabla 8x8, promenjeno polja {len(changed)}; rng igra {B['rng']}, "
             f"poeni igra {(me_b.get('score') or 0) - (me_a.get('score') or 0)}"]

    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {capture_mode(cap_a["profile"]).value}
    try:
        with simulation.engine_refill(model):
            destroy, skulls, count = engine_monkey.activate(
                board, special, model, params, activations, mode=mode, square=square,
                candidate_index=index)
            placed_board, placed_special = engine_monkey.place_skulls(board, special, skulls)
            candidate = ms.MoveCandidate(simulation.NO_SWAP_CELL, simulation.NO_SWAP_CELL,
                                         ms.Direction.RIGHT, placed_board, placed_special)
            with _record_waves() as waves:
                result = ms._simulate_booster_effect_cells(
                    placed_board, placed_special, candidate, set(destroy),
                    allow_square_matches=square, mode=mode)
            rng_sim = model.rng.counter
    finally:
        simulation.PREFIX_MODES = certified
    if result is None:
        return lines + ["  simulator je vratio None"]

    lines.append(f"  baceno {count} lobanja na {sorted(skulls)}, odmah unisteno {sorted(destroy)}")
    lines.append(f"  rng sim {rng_sim} (razlika prema igri {B['rng'] - rng_sim})")
    stray = [c for c in sorted(destroy) if c not in changed]
    lines.append(f"  lobanje koje igra NIJE promenila: {[(c, int(board[c[0]][c[1]])) for c in stray]}")

    first = None
    for cascade in sorted(waves):
        cells = waves[cascade]
        stray = sorted(c for c in cells if c not in changed)
        if cascade == 1:
            stray = [c for c in stray if c not in set(destroy)]
        lines.append(f"  kaskada {cascade}: unisteno {len(cells)}, polja koja igra nije dirala: {len(stray)}")
        if stray and first is None:
            first = (cascade, stray[0])
    if first is not None:
        cascade, cell = first
        row, col = cell
        lines.append(f"  PRVO RAZILAZENJE: kaskada {cascade}, polje {cell} -- igra ga nije dirala "
                     f"({int(A['board'][row][col])} -> {int(B['board'][row][col])}), "
                     f"sim ga unistava (specijal {int(placed_special[row][col])})")
    else:
        lines.append("  nijedno unisteno polje nije polje koje je igra ostavila netaknuto")

    final_board = grid(result.board)
    differ = sum(1 for r in range(len(final_board)) for c in range(len(final_board[r]))
                 if int(final_board[r][c]) != int(B["board"][r][c]))
    lines.append(f"  krajnja tabla: razlika {differ} polja, kaskada {result.cascade_count}, "
                 f"unisteno {result.cleared_cells}")
    return lines


def _skulls(special):
    return {(r, c) for r, row in enumerate(special) for c, v in enumerate(row) if int(v) == 19}


def main(argv) -> int:
    folders = [Path(a) for a in argv if not a.startswith("-") and not a.isdigit()]
    stems = [a for a in argv if a.isdigit()]
    folder = folders[0] if folders else sorted((ROOT / "Debug" / "research").iterdir())[-1]
    stem = stems[0] if stems else "002"
    indexes = [None] if "--candidates" not in argv else list(range(5))
    out = []
    for index in indexes:
        out.extend(trace(folder, stem, index))
        out.append("")
    text = "\n".join(out)
    (folder / f"monkey_trace_{stem}.txt").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
