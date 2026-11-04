"""Shared match-context/profile keys for runtime debug and learning."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


_SAFE_CHARS = re.compile(r"[^a-z0-9_]+")

SCORE_STRATEGY_AHEAD = "ahead"
SCORE_STRATEGY_NORMAL = "normal"
SCORE_STRATEGY_COMEBACK = "comeback"
SAFE_POINTS_PER_REMAINING_MOVE = 30
SERIOUS_SCORE_DEFICIT = 80
MEANINGFUL_SCORE_LEAD = 25


def slug(value: Any, default: str = "unknown") -> str:
    text = str(value if value is not None else default).strip().lower()
    text = text.replace(" ", "_").replace("-", "_")
    text = _SAFE_CHARS.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or default


def round_key_from_state(current_round: Any, total_rounds: Any) -> str:
    try:
        current = int(current_round)
        total = int(total_rounds)
    except (TypeError, ValueError):
        return "single"
    if current <= 0 or total <= 1:
        return "single"
    if current >= total:
        return "final_round"
    return f"r{current}of{total}"


def turn_phase_from_remaining(remaining_moves: Any) -> str:
    try:
        remaining = int(remaining_moves)
    except (TypeError, ValueError):
        return "unknown"
    if remaining <= 1:
        return "final_move"
    if remaining <= 3:
        return "mid"
    return "early"


def score_strategy_from_state(score_deficit: Any, moves_left: Any) -> str:
    """Choose the objective from score pressure, not from utility weights.

    Positive deficit means the opponent is ahead.  A comeback is required when
    the gap is already serious or a conservative 30-points-per-move projection
    cannot close it.  Missing score data intentionally preserves normal play.
    """
    deficit = _int_or_none(score_deficit)
    if deficit is None:
        return SCORE_STRATEGY_NORMAL
    moves = _int_or_none(moves_left)
    expected_safe_points = (
        max(1, moves) * SAFE_POINTS_PER_REMAINING_MOVE
        if moves is not None
        else None
    )
    if deficit >= SERIOUS_SCORE_DEFICIT:
        return SCORE_STRATEGY_COMEBACK
    if expected_safe_points is not None and deficit > expected_safe_points:
        return SCORE_STRATEGY_COMEBACK
    if deficit <= -MEANINGFUL_SCORE_LEAD:
        return SCORE_STRATEGY_AHEAD
    return SCORE_STRATEGY_NORMAL


@dataclass(frozen=True)
class MatchContext:
    strategy_mode: str
    game_mode: str
    booster: str
    booster_action_mode: str
    round_key: str
    turn_phase: str
    remaining_moves: int | None = None
    moves_left_in_match: int | None = None
    current_round: int | None = None
    total_rounds: int | None = None
    our_score: int | None = None
    opponent_score: int | None = None
    score_deficit: int | None = None
    expected_safe_points: int | None = None
    score_strategy: str = SCORE_STRATEGY_NORMAL
    score_confidence: float | None = None

    @property
    def profile_key(self) -> str:
        return (
            f"strategy-{self.strategy_mode}__"
            f"mode-{self.game_mode}__"
            f"booster-{self.booster}__"
            f"round-{self.round_key}__"
            f"turn-{self.turn_phase}"
        )

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profile_key"] = self.profile_key
        return payload


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def build_match_context(
    *,
    strategy_mode: Any = None,
    game_mode: Any = None,
    booster: Any = None,
    booster_action_mode: Any = None,
    remaining_moves: Any = None,
    moves_left_in_match: Any = None,
    current_round: Any = None,
    total_rounds: Any = None,
    our_score: Any = None,
    opponent_score: Any = None,
    score_deficit: Any = None,
    score_confidence: Any = None,
) -> MatchContext:
    action_slug = slug(booster_action_mode, "none")
    booster_slug = slug(booster, "none")
    if booster_slug in {"default", "unknown", "none"} and action_slug not in {"none", "unknown"}:
        booster_slug = action_slug
    round_key = round_key_from_state(current_round, total_rounds)
    resolved_our_score = _int_or_none(our_score)
    resolved_opponent_score = _int_or_none(opponent_score)
    resolved_deficit = _int_or_none(score_deficit)
    if (
        resolved_deficit is None
        and resolved_our_score is not None
        and resolved_opponent_score is not None
    ):
        resolved_deficit = resolved_opponent_score - resolved_our_score
    resolved_moves_left = _int_or_none(moves_left_in_match)
    if resolved_moves_left is None:
        resolved_moves_left = _int_or_none(remaining_moves)
    expected_safe_points = (
        max(1, resolved_moves_left) * SAFE_POINTS_PER_REMAINING_MOVE
        if resolved_moves_left is not None
        else None
    )
    try:
        resolved_score_confidence = (
            float(score_confidence) if score_confidence is not None else None
        )
    except (TypeError, ValueError):
        resolved_score_confidence = None
    return MatchContext(
        strategy_mode=slug(strategy_mode),
        game_mode=slug(game_mode, "none"),
        booster=booster_slug,
        booster_action_mode=action_slug,
        round_key=round_key,
        turn_phase=turn_phase_from_remaining(remaining_moves),
        remaining_moves=_int_or_none(remaining_moves),
        moves_left_in_match=_int_or_none(moves_left_in_match),
        current_round=_int_or_none(current_round),
        total_rounds=_int_or_none(total_rounds),
        our_score=resolved_our_score,
        opponent_score=resolved_opponent_score,
        score_deficit=resolved_deficit,
        expected_safe_points=expected_safe_points,
        score_strategy=score_strategy_from_state(resolved_deficit, resolved_moves_left),
        score_confidence=resolved_score_confidence,
    )


def match_context_from_move_data(move_data: dict[str, Any]) -> MatchContext:
    existing = move_data.get("match_context")
    if isinstance(existing, dict):
        return build_match_context(
            strategy_mode=existing.get("strategy_mode"),
            game_mode=existing.get("game_mode"),
            booster=existing.get("booster"),
            booster_action_mode=existing.get("booster_action_mode"),
            remaining_moves=existing.get("remaining_moves"),
            moves_left_in_match=existing.get("moves_left_in_match"),
            current_round=existing.get("current_round"),
            total_rounds=existing.get("total_rounds"),
            our_score=existing.get("our_score"),
            opponent_score=existing.get("opponent_score"),
            score_deficit=existing.get("score_deficit"),
            score_confidence=existing.get("score_confidence"),
        )

    turn_state = move_data.get("turn_state") or {}
    strategy_context = move_data.get("strategy_context") or {}
    round_state = move_data.get("round_state") or {}
    return build_match_context(
        strategy_mode=strategy_context.get("mode"),
        game_mode=move_data.get("mode"),
        booster=move_data.get("active_booster"),
        booster_action_mode=move_data.get("booster_action_mode"),
        remaining_moves=turn_state.get("remaining_moves"),
        moves_left_in_match=turn_state.get("moves_left_in_match"),
        current_round=round_state.get("current"),
        total_rounds=round_state.get("total"),
        our_score=(move_data.get("score_state") or {}).get("our_score"),
        opponent_score=(move_data.get("score_state") or {}).get("opponent_score"),
        score_deficit=(move_data.get("score_state") or {}).get("score_deficit"),
        score_confidence=(move_data.get("score_state") or {}).get("confidence"),
    )
