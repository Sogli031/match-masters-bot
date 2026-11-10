"""Rekonstrukcija runtime rangiranja iz snimljenih kandidata (Debug/runs).

candidates.json cuva sve komponente ocene jednog kandidata, ali ne i konacni
prioritet po kome je bot rangirao (``move_strategy._weighted_priority``). Ovaj
modul sastavi MoveEvaluation iz snimljenog dict-a i stanja iz move.json i
pozove isti prioritet -- sa iskljucenim naucenim korekcijama, da bude cista
heuristika. Tako model vrednosti uci rezidual prema *stvarnoj* skali po kojoj
se u igri rangira, a ne prema ``score`` (koji, na primer, plave vrednuje
1/celija dok prioritet vrednuje 5.5/celija -- rezidual prema score bi ih
brojao dvaput).

Noviji snimci nose i ``priority_score`` upisan u igri; ``check_reconstruction``
poredi rekonstrukciju sa njim.
"""

from __future__ import annotations

import os
import sys
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Isto sto igra racuna pre reziduala: kalibrisani mnozioci (learned_weights)
# ukljuceni, model vrednosti iskljucen -- inace bi model ucio rezidual prema
# skali koja u igri ne postoji i, na primer, popust na buducnost brojao dvaput.
os.environ.setdefault("MEMORY_GUI_LEARNED_VALUE", "weights")

import move_strategy as ms  # noqa: E402

_EVALUATION_FIELDS = {f.name for f in fields(ms.MoveEvaluation)}
_SKIP_FIELDS = {"candidate", "cascade_matches", "intent_events", "explanation"}


def _direction(value) -> ms.Direction:
    try:
        return ms.Direction(str(value))
    except ValueError:
        return ms.Direction.RIGHT


def _cascade_matches(expected_cascades) -> list[list[ms.MatchGroup]]:
    result = []
    for cascade in expected_cascades or []:
        groups = []
        for match in cascade.get("matches") or []:
            cells = frozenset(tuple(int(v) for v in cell) for cell in match.get("cells") or [])
            groups.append(
                ms.MatchGroup(cells=cells, color=int(match.get("color") or 0), kind=str(match.get("kind") or ""))
            )
        result.append(groups)
    return result


def _coerce(name: str, value):
    if name in ("cleo_blue_cells_by_scenario", "cleo_scenario_weights", "cleo_scenario_colors", "cleo_scenario_scores"):
        return tuple(value or ())
    if name in ("floor_lava_destroyed_columns", "floor_lava_checked_columns_after"):
        # Debug ih upisuje 1-bazirano; nazad na 0-bazirano.
        return tuple(int(v) - 1 for v in value or ())
    if name == "cleared_color_counts":
        return {int(k): float(v) for k, v in (value or {}).items()}
    if name == "effect_source_counts":
        return {str(k): float(v) for k, v in (value or {}).items()}
    return value


def build_evaluation(candidate: dict, board, special_board) -> ms.MoveEvaluation:
    start = tuple(int(v) for v in candidate["start"])
    target = tuple(int(v) for v in candidate["target"])
    move_candidate = ms.MoveCandidate(
        start=start,
        target=target,
        direction=_direction(candidate.get("direction")),
        board=[list(row) for row in board],
        special_board=[list(row) for row in special_board],
    )
    kwargs = {}
    for name in _EVALUATION_FIELDS:
        if name in _SKIP_FIELDS or name not in candidate:
            continue
        kwargs[name] = _coerce(name, candidate[name])
    return ms.MoveEvaluation(
        candidate=move_candidate,
        explanation=str(candidate.get("explanation") or ""),
        intent_events=list(candidate.get("intent_events") or []),
        cascade_matches=_cascade_matches(candidate.get("expected_cascades")),
        **kwargs,
    )


def build_states(move: dict):
    booster = move.get("booster_state") or {}
    turn = move.get("turn_state") or {}
    rounds = move.get("round_state") or {}
    sc = move.get("strategy_context") or {}
    score_state = move.get("score_state") or {}
    resolved = ((move.get("screen_state_read") or {}).get("resolved")) or {}
    current_round = rounds.get("current")
    total_rounds = rounds.get("total")
    booster_state = ms.BoosterState(
        current=booster.get("current"),
        maximum=int(booster.get("maximum") or ms.BOOSTER_MAX_CHARGE),
        source=str(booster.get("source") or "unknown"),
    )
    turn_state = ms.TurnState(
        remaining_moves=turn.get("remaining_moves"),
        source=str(turn.get("source") or "unknown"),
        moves_left_in_match=turn.get("moves_left_in_match"),
        is_final_round=bool(
            current_round is not None
            and total_rounds is not None
            and int(current_round) >= int(total_rounds) - 1
        ),
        current_round=current_round,
        total_rounds=total_rounds,
        time_left_seconds=turn.get("time_left_seconds"),
        seconds_per_move=turn.get("seconds_per_move"),
    )
    context_kwargs = {
        "mode": str(sc.get("mode") or ms.STRATEGY_UNKNOWN),
        "score_strategy": str(score_state.get("strategy") or ms.SCORE_STRATEGY_NORMAL),
        "our_score": score_state.get("our_score", resolved.get("our_score")),
        "opponent_score": score_state.get("opponent_score", resolved.get("opponent_score")),
        "score_deficit": score_state.get("score_deficit", resolved.get("score_deficit")),
        "expected_safe_points": score_state.get("expected_safe_points"),
        "score_confidence": score_state.get("confidence"),
    }
    context_fields = {f.name for f in fields(ms.StrategyContext)}
    for key in ("booster_rush", "solo_challenge"):
        if key in context_fields and key in sc:
            context_kwargs[key] = bool(sc.get(key))
    strategy_context = ms.StrategyContext(**{k: v for k, v in context_kwargs.items() if k in context_fields})
    # New logs preserve every dataclass input, including clock and horizon.
    exact = move.get("ranking_context") or {}
    def restore(cls, key, fallback):
        payload = exact.get(key)
        if not isinstance(payload, dict):
            return fallback
        names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in payload.items() if k in names}
        if cls is ms.TurnState:
            if "opponent_charge_colors" in kwargs:
                kwargs["opponent_charge_colors"] = tuple(kwargs["opponent_charge_colors"] or ())
            if isinstance(kwargs.get("opponent_booster"), dict):
                kwargs["opponent_booster"] = ms.BoosterState(**kwargs["opponent_booster"])
        return cls(**kwargs)
    booster_state = restore(ms.BoosterState, "booster_state", booster_state)
    turn_state = restore(ms.TurnState, "turn_state", turn_state)
    strategy_context = restore(ms.StrategyContext, "strategy_context", strategy_context)
    rally = {int(k): float(v) for k, v in (move.get("score_rally_values") or {}).items()}
    return {
        "mode": str(move.get("mode") or "None"),
        "booster_state": booster_state,
        "turn_state": turn_state,
        "score_rally_values": rally or None,
        "strategy_context": strategy_context,
    }


def runtime_priority(move: dict, candidate: dict) -> float:
    """Heuristicki prioritet kandidata, kako bi ga igra izracunala (bez naucenih korekcija)."""
    states = build_states(move)
    evaluation = build_evaluation(candidate, move["board"], move["special_board"])
    return float(
        ms._weighted_priority(
            evaluation,
            states["mode"],
            states["booster_state"],
            states["turn_state"],
            states["score_rally_values"],
            states["strategy_context"],
        )
    )


def check_reconstruction(move: dict, candidate: dict) -> float | None:
    """Razlika rekonstrukcije od prioriteta upisanog u igri, ili None bez zapisa."""
    logged = candidate.get("priority_score")
    if logged is None:
        return None
    return runtime_priority(move, candidate) - float(logged)
