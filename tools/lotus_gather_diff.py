"""Read a Froggy lotus "gather" frame and diff it against the board before the move.

The lotus does not eat tiles where they stand: it teleports every tile of the
matched colour into the eight cells around itself and pops that ring.  What the
simulator cannot answer is where the tiles that *used to sit in the ring* end up,
and that answer is only visible in the animation frame between the gather and the
pop -- the settled board that the bot scans afterwards has already cascaded and
refilled past it.

That frame is an ordinary screenshot, so the existing recognizer can label it.
Point this script at such a screenshot plus the Debug run that produced the move
and it prints, cell by cell, what moved where.

Usage:
    python tools/lotus_gather_diff.py gather.png --run 2026-08-14_20-51-41_805
    python tools/lotus_gather_diff.py gather.png --run <run> --no-swap

The frame may be a full-screen capture (cropped with the board profile, like
``state.png``) or an already-cropped board image (like ``board.png``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recognition  # noqa: E402
from move_strategy import BLOCKED, SPECIAL_FROGGY_LOTUS, normalize_game_mode  # noqa: E402
from recognition import create_board  # noqa: E402

COLOR_NAMES = {
    BLOCKED: "blok",
    0: "----",
    1: "plav",
    2: "zele",
    3: "zuta",
    4: "ljub",
    5: "crve",
    6: "nara",
}


def tile_name(color: int, special: int) -> str:
    name = COLOR_NAMES.get(int(color), str(color))
    if int(special) == SPECIAL_FROGGY_LOTUS:
        return "LOTUS"
    if int(special):
        return f"{name}+{int(special)}"
    return name


def _recognize_once(image: Image.Image) -> tuple[list[list[int]], list[list[int]]]:
    """Label ``image`` with the live recognizer instead of the screen."""
    original = recognition.capture_debug_screenshot
    recognition.capture_debug_screenshot = (
        lambda *args, **kwargs: image.convert("RGB")
    )
    try:
        return recognition.update_board_2(
            create_board(), create_board(), write_screenshot=False
        )
    finally:
        recognition.capture_debug_screenshot = original


def recognize(
    image: Image.Image, preferred_mode: str
) -> tuple[list[list[int]], list[list[int]], str]:
    """Label ``image``, falling back when a recognition mode reads nothing.

    The ML-primary path returns an all-empty board on some gather frames (the
    2026-08-14 21:07 blue lotus frame is one), and an empty board silently reads
    as "every tile moved".  Trying the other modes turns that into a labelled
    board plus a note about which path produced it.
    """
    order = [preferred_mode] + [
        mode for mode in ("hybrid", "off", "only") if mode != preferred_mode
    ]
    for mode in order:
        recognition.set_ml_recognition_mode(mode)
        board, special_board = _recognize_once(image)
        filled = sum(1 for row in board for value in row if value)
        if filled >= len(board) * len(board) // 2:
            return board, special_board, mode
    raise SystemExit(
        "no recognition mode could label this frame -- is the board region "
        f"({recognition.left}, {recognition.up}, {recognition.width}, "
        f"{recognition.height}) where the board actually is in this screenshot?"
    )


def load_frame(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGB")
    board_size = (recognition.width, recognition.height)
    if image.size == board_size:
        return image
    crop = (
        recognition.left,
        recognition.up,
        recognition.left + recognition.width,
        recognition.up + recognition.height,
    )
    if image.size[0] < crop[2] or image.size[1] < crop[3]:
        raise SystemExit(
            f"{path.name} is {image.size}, too small for board region {crop}. "
            "Pass a full-screen capture or an already-cropped board image."
        )
    return image.crop(crop)


def played_swap(move: dict) -> tuple[tuple[int, int], tuple[int, int]] | None:
    best = move.get("best_move") or {}
    start, target = best.get("start"), best.get("target")
    if not start or not target:
        return None
    return (int(start[0]), int(start[1])), (int(target[0]), int(target[1]))


def apply_swap(board, special_board, swap) -> None:
    (r1, c1), (r2, c2) = swap
    board[r1][c1], board[r2][c2] = board[r2][c2], board[r1][c1]
    special_board[r1][c1], special_board[r2][c2] = (
        special_board[r2][c2],
        special_board[r1][c1],
    )


def lotus_ring(special_board) -> tuple[tuple[int, int] | None, set[tuple[int, int]]]:
    size = len(special_board)
    for row in range(size):
        for col in range(size):
            if special_board[row][col] != SPECIAL_FROGGY_LOTUS:
                continue
            ring = {
                (row + dr, col + dc)
                for dr in (-1, 0, 1)
                for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0)
                and 0 <= row + dr < size
                and 0 <= col + dc < size
            }
            return (row, col), ring
    return None, set()


def print_board(title: str, board, special_board, mark: set[tuple[int, int]] = frozenset()) -> None:
    print(f"\n{title}")
    for row, values in enumerate(board):
        cells = []
        for col, value in enumerate(values):
            text = tile_name(value, special_board[row][col])
            cells.append(f"[{text:>6}]" if (row, col) in mark else f" {text:>6} ")
        print("".join(cells))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frame", help="screenshot taken while the lotus holds the gathered ring")
    parser.add_argument("--run", required=True, help="Debug run that chose the move (name or path)")
    parser.add_argument("--runs-dir", default="Debug/runs")
    parser.add_argument("--profile", default="regular")
    parser.add_argument(
        "--no-swap",
        action="store_true",
        help="compare against the board as scanned, without applying the played swap",
    )
    parser.add_argument(
        "--ml-mode",
        default="only",
        # Replaying board.png of run 2026-08-14_20-51-41_805 reproduces all 49
        # cells including specials under "only"; "hybrid" mislabels three bombs
        # and the lotus, which would show up here as phantom movement.
        help="ML recognition mode to replay with (only/hybrid/off)",
    )
    args = parser.parse_args()

    run_dir = Path(args.run)
    if not run_dir.exists():
        run_dir = Path(args.runs_dir) / args.run
    move_path = run_dir / "move.json"
    if not move_path.exists():
        raise SystemExit(f"no move.json in {run_dir}")
    move = json.loads(move_path.read_text(encoding="utf-8"))

    recognition.apply_board_profile(args.profile, allow_uncalibrated_layout=True)
    # Specials are labelled differently per game mode and ML mode, so replay the
    # frame under the same settings the run was played with or bombs come back as
    # a different special than the run recorded.
    recognition.curr_mode = normalize_game_mode(move.get("mode", "None"))

    before = [row[:] for row in move["board"]]
    before_special = [row[:] for row in move["special_board"]]
    swap = played_swap(move)
    if swap and not args.no_swap:
        apply_swap(before, before_special, swap)

    lotus, ring = lotus_ring(before_special)
    after, after_special, used_mode = recognize(load_frame(Path(args.frame)), args.ml_mode)

    print(
        f"run={run_dir.name} swap={swap if not args.no_swap else 'not applied'}"
        f" lotus={lotus} ml_mode={used_mode}"
    )
    print_board("PRE (tabla iz run-a, posle swap-a)", before, before_special, ring)
    print_board("GATHER FREJM (prepoznato sa slike)", after, after_special, ring)

    collected_color = None
    for event in (move.get("best_move") or {}).get("intent_events", []):
        if event.get("type") == "froggy_lotus_collect":
            collected_color = int(event["color"])
    sources = {
        (row, col)
        for row, values in enumerate(before)
        for col, value in enumerate(values)
        if value == collected_color and (row, col) not in ring
    }

    print(f"\nprsten oko lotusa: {sorted(ring)}")
    print(f"pokupljena boja: {COLOR_NAMES.get(collected_color, collected_color)}")
    print(f"izvorne celije te boje van prstena ({len(sources)}): {sorted(sources)}")

    print("\nPROMENE VAN PRSTENA (tu se vidi kuda su izgurane figure)")
    moved = 0
    for row, values in enumerate(before):
        for col, value in enumerate(values):
            if (row, col) in ring:
                continue
            new_value = after[row][col]
            if new_value == value and after_special[row][col] == before_special[row][col]:
                continue
            moved += 1
            origin = " <- izvor pokupljene" if (row, col) in sources else ""
            print(
                f"  ({row},{col}) {tile_name(value, before_special[row][col]):>6}"
                f" -> {tile_name(new_value, after_special[row][col]):>6}{origin}"
            )
    print(f"\npromenjeno van prstena: {moved}, nepromenjeno: {49 - len(ring) - moved}")
    print(
        "\nAko su izvorne celije dobile bas one figure koje su stajale u prstenu,"
        "\nrazmena je uparena i cela tabla posle lotusa je predvidljiva."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
