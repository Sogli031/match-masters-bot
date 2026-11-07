"""Replay the recorded Mixy frames through the live use/spend trackers.

Reads Debug/memory_board/board_snapshots.jsonl and drives
MemoryWindow._track_mixy_code_spend over every frame that carries a Mixy
booster, then reports what the trackers concluded per activation. Used to
check the per-activation use budget against the engine's own behaviour
(re-deals, refunds) without a running game.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PATH = ROOT / "Debug" / "memory_board" / "board_snapshots.jsonl"
TAIL_BYTES = int(os.environ.get("MIXY_TAIL_BYTES", 900 * 1024 * 1024))


def load_frames():
    size = PATH.stat().st_size
    handle = PATH.open("rb")
    handle.seek(max(0, size - TAIL_BYTES))
    handle.readline()
    frames = []
    for line in handle:
        if b'"special_ability_type":59' not in line:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        snapshot = payload.get("snapshot", payload)
        state = snapshot.get("state") or {}
        me = next(
            (
                player
                for player in (state.get("players") or [])
                if player.get("special_ability_type") == 59
            ),
            None,
        )
        if me is None:
            continue
        stamp = snapshot.get("captured_at") or ""
        try:
            seconds = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        frames.append((seconds, stamp, state, me))
    return frames


def make_tracker():
    """A bare object carrying only the Mixy tracker state and methods."""
    import memory_gui

    window = types.SimpleNamespace()
    window._log = lambda message: None
    window._mixy_spent_code = None
    window._mixy_spent_colors = set()
    window._mixy_spend_armed = True
    window._mixy_uses_this_activation = 0
    window._mixy_max_uses = 0
    window._mixy_prev_phase = None
    window._mixy_prev_energy = None
    window._mixy_transient_live = False
    window._mixy_code_reported = None
    cls = memory_gui.MemoryWindow
    for name in (
        "_track_mixy_code_spend",
        "_track_mixy_activation_uses",
        "_mixy_max_uses_from",
        "_memory_mixy_state",
    ):
        setattr(window, name, getattr(cls, name).__get__(window, types.SimpleNamespace))
    window.ABILITY_MIXY_MEOW = cls.ABILITY_MIXY_MEOW
    window.MIXY_CODE_PHASES = cls.MIXY_CODE_PHASES
    window.MIXY_DEFAULT_MAX_USES = cls.MIXY_DEFAULT_MAX_USES
    return window


def main():
    frames = load_frames()
    print(f"mixy frames: {len(frames)}")
    window = make_tracker()

    counts = {}
    exhausted_frames = 0
    live_frames = 0
    over_budget = 0
    timeline = []
    prev_uses = None
    for seconds, stamp, state, me in frames:
        window._track_mixy_code_spend(me)
        uses = window._mixy_uses_this_activation
        cap = window._mixy_max_uses
        if cap and uses > cap:
            over_budget += 1
        counts[uses] = counts.get(uses, 0) + 1
        fields = me.get("special_ability_fields") or {}
        if isinstance(fields.get("activeColors"), list) and fields["activeColors"]:
            live_frames += 1
            if cap and uses >= cap:
                exhausted_frames += 1
        if uses != prev_uses:
            timeline.append(
                (
                    stamp[11:19],
                    uses,
                    cap,
                    fields.get("activeColors"),
                    sorted(window._mixy_spent_colors),
                )
            )
            prev_uses = uses

    print(f"max_uses read from engine: {window._mixy_max_uses}")
    print(f"frames by use count: {dict(sorted(counts.items()))}")
    print(f"frames over the engine budget: {over_budget}")
    print(
        f"frames with a code drawn: {live_frames}, of which declared exhausted: "
        f"{exhausted_frames} ({100.0 * exhausted_frames / max(live_frames, 1):.0f}%)"
    )
    print("\nuse-count transitions (last 40):")
    for row in timeline[-40:]:
        print(f"  {row[0]}  uses={row[1]}/{row[2]}  code={row[3]}  spent={row[4]}")


if __name__ == "__main__":
    main()
