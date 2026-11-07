"""How often a confirmed available perk was still unused at the last handover.

Usage: python tools/perk_handover_report.py [Debug/perk_handover_audit.jsonl]

runtime.record_final_handover_perk_audit writes one line per swipe that hands
over the last versus turn. An extra that keeps the turn after all produces a
second line for the same turn, so lines less than TURN_GAP_SECONDS apart are
one handover and the last of them counts.
"""

from __future__ import annotations

import datetime
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "Debug" / "perk_handover_audit.jsonl"
TURN_GAP_SECONDS = 30.0


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def handovers(entries: list[dict]) -> list[dict]:
    result: list[dict] = []
    previous_time = None
    for entry in entries:
        try:
            when = datetime.datetime.fromisoformat(entry["time"])
        except (KeyError, ValueError):
            when = None
        same_turn = (
            result
            and when is not None
            and previous_time is not None
            and (when - previous_time).total_seconds() < TURN_GAP_SECONDS
        )
        if same_turn:
            result[-1] = entry
        else:
            result.append(entry)
        previous_time = when
    return result


def summarize(entries: list[dict]) -> dict:
    turns = handovers(entries)
    with_unused = [turn for turn in turns if turn.get("unused_confirmed", 0) > 0]
    reasons = Counter(
        slot.get("decision_reason") or slot.get("source_reason") or "unknown"
        for turn in with_unused
        for slot in turn.get("slots", [])
        if slot.get("available")
    )
    return {
        "final_handovers": len(turns),
        "handovers_with_unused_perk": len(with_unused),
        "unused_perks": sum(turn.get("unused_confirmed", 0) for turn in turns),
        "reasons": dict(reasons.most_common()),
        "runs": [turn.get("run") for turn in with_unused],
    }


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else DEFAULT_LOG
    print(json.dumps(summarize(load(path)), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
