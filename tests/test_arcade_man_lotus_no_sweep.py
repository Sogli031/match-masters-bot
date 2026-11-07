"""Arcade Man: a swipe that fires a Froggy lotus sweeps no line.

Recorded 2026-11-06 (Debug/runs 15:02-15:07, research 20261106_150156_arcade-man):
with the sweep the bot expected 7-10 blue from yellow/orange lotus moves and
1-5 arrived, so it passed over the blue lotus with an empty meter. Without the
sweep the prediction matches the meter, and the blue lotus wins.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms

RUN = ROOT / "Debug" / "runs" / "2026-11-06_15-02-43_271" / "move.json"
RESEARCH = ROOT / "Debug" / "research" / "20261106_150156_arcade-man"


def test_blue_lotus_wins_with_an_empty_meter():
    if not RUN.exists() or not RESEARCH.exists():
        pytest.skip("Arcade Man recording is not on this machine")
    from tools.analyze_research import local_player

    move = json.loads(RUN.read_text(encoding="utf-8"))
    record = next(
        r for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESEARCH.glob("[0-9]*.json")))
        if r["board"] == move["board"]
    )
    gather = ms.froggy_gather_config_from_params(local_player(record).get("special_ability_params"))
    rally = {int(k): float(v) for k, v in (move.get("score_rally_values") or {}).items()}
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=5, source="memory", time_left_seconds=1400.0, seconds_per_move=6.5)
    context = ms.StrategyContext(mode="solo_6", booster_rush=True, solo_challenge=True)
    with ms.froggy_gather_region_active(*gather):
        ranked = ms.rank_moves(move["board"], move["special_board"], mode=ms.GameMode.ARCADE_MAN.value,
                               score_rally_values=rally, strategy_context=context)
        lotus = ms.rank_froggy_lotus_moves(
            ranked, move["board"], move["special_board"], mode=ms.GameMode.ARCADE_MAN.value,
            score_rally_values=rally, booster_state=booster, turn_state=turn, strategy_context=context)
    assert lotus[0].froggy_lotus_color == ms.BLUE
    yellow = next(e for e in lotus if e.froggy_lotus_color == ms.YELLOW)
    assert yellow.blue_cells <= 4  # 3 charged in the game; the sweep said 9


def test_recorded_arcade_man_session_replays(monkeypatch):
    """28 of 33 recorded moves exact: skulls spawned by the refill, the lotus
    sweep on the firing match. 002/040 fire random lightning, 033 a skull blast
    whose reach is not read yet, 019/026 are open."""
    from refill_monitor import check_transition
    from strategy_lab import simulation

    files = sorted(RESEARCH.glob("[0-9][0-9][0-9].json"))
    if not files:
        pytest.skip("Arcade Man recording is not on this machine")
    monkeypatch.setattr(simulation, "PREFIX_MODES",
                        set(simulation.PREFIX_MODES) | {ms.GameMode.ARCADE_MAN.value})
    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    verdicts = [
        (check_transition(records[i - 1], records[i]) or {}).get("verdict")
        for i in range(1, len(records))
    ]
    # 28 with the uncommitted Froggy blob rules, 27 without them.
    assert verdicts.count("ok") >= 27
