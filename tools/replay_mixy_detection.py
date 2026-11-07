"""Replay Mixy code detection over saved Debug runs.

The Mixy suitcase is read from the live screen, so a misread is only reproducible
from the frame that produced it. Every Debug run stores the full screen as
``state.png``; this script re-runs the detector over those frames so a threshold
change can be measured against real popups instead of guessed at.

Usage:
    python tools/replay_mixy_detection.py                  # every run
    python tools/replay_mixy_detection.py 2026-08-08       # runs matching prefix
    python tools/replay_mixy_detection.py --crops out_dir  # also dump the region
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recognition  # noqa: E402
from move_strategy import BLUE, GREEN, ORANGE, PURPLE, RED, YELLOW  # noqa: E402

COLOR_NAMES = {
    RED: "RED",
    ORANGE: "ORANGE",
    YELLOW: "YELLOW",
    GREEN: "GREEN",
    BLUE: "BLUE",
    PURPLE: "PURPLE",
}


def recorded_state(run_dir: Path):
    """What the bot detected when the run was played, if it logged it."""
    move_path = run_dir / "move.json"
    if not move_path.exists():
        return None
    try:
        payload = json.loads(move_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload.get("mixy_meow")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", nargs="?", default="", help="only runs whose name starts with this")
    parser.add_argument("--runs-dir", default="Debug/runs")
    parser.add_argument("--profile", default="regular")
    parser.add_argument("--crops", default=None, help="directory to write the cropped code region into")
    args = parser.parse_args()

    recognition.apply_board_profile(args.profile, allow_uncalibrated_layout=True)
    region = recognition.mixy_meow_code_region()
    print(f"profile={args.profile} region={region}")

    crops_dir = Path(args.crops) if args.crops else None
    if crops_dir is not None:
        crops_dir.mkdir(parents=True, exist_ok=True)

    runs_root = Path(args.runs_dir)
    if not runs_root.is_dir():
        print(f"No debug runs directory at {runs_root.resolve()}")
        return 1
    runs = sorted(path for path in runs_root.glob(f"{args.prefix}*") if path.is_dir())
    active = 0
    changed = 0
    checked = 0
    for run in runs:
        state_path = run / "state.png"
        if not state_path.exists():
            continue
        image = Image.open(state_path).convert("RGB")
        state = recognition.detect_mixy_meow_code_state(image)
        checked += 1
        active += bool(state.active)

        recorded = recorded_state(run)
        marker = " "
        if recorded is not None and bool(recorded.get("active")) != state.active:
            marker = "*"
            changed += 1

        colors = ", ".join(COLOR_NAMES.get(color, str(color)) for color in state.code_colors)
        print(
            f"{marker} {run.name}  active={str(state.active):<5} "
            f"[{colors}]  {state.reason}"
        )

        if crops_dir is not None:
            x, y, width, height = region
            image.crop((x, y, x + width, y + height)).save(crops_dir / f"{run.name}.png")

    print(f"\nchecked={checked} active={active} changed_vs_recorded={changed}")
    print("* = detector now disagrees with what the run logged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
