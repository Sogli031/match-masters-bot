"""Known Solo Challenge objectives, kept separate from opponent/clock policy."""

from dataclasses import asdict, dataclass, replace
import math


@dataclass(frozen=True)
class SoloGoalState:
    targets: tuple[int, ...]
    score: int
    refill_moves: int = 0
    overflow: bool = True
    continue_after_last: bool = False
    unused_moves_energy: float = 0.0
    multiplier: float = 1.0

    @property
    def next_target(self) -> int | None:
        return next((target for target in self.targets if target > self.score), None)

    @property
    def gap(self) -> int | None:
        target = self.next_target
        return None if target is None else target - self.score

    @property
    def has_next_stage(self) -> bool:
        return self.next_target is not None and self.next_target < self.targets[-1]

    @property
    def complete(self) -> bool:
        return self.next_target is None

    @property
    def values_unused_moves(self) -> bool:
        """Moves left when the challenge ends pay energy (soloUnusedMovesEnergyWorth)."""
        return self.unused_moves_energy > 0

    def progress_points(self, points: float) -> float:
        """Points that can still advance an unfinished flag."""
        if self.complete:
            return 0.0
        return min(self.credited_points(points), self.targets[-1] - self.score)

    def after_points(self, points: float) -> "SoloGoalState":
        return replace(self, score=self.score + int(self.progress_points(points)))

    def credited_points(self, points: float) -> float:
        """The engine clips this move at a threshold when overflow is off."""
        points = max(0.0, float(points))
        if self.gap is None or self.overflow:
            return points
        if not self.has_next_stage and self.continue_after_last:
            return points
        return min(points, float(self.gap))

    @classmethod
    def from_payload(cls, payload) -> "SoloGoalState | None":
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            return None
        try:
            raw = payload.get("targets")
            score = payload.get("score")
            if not isinstance(raw, (list, tuple)) or isinstance(score, bool):
                return None
            if not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0:
                return None
            if any(isinstance(t, bool) or not isinstance(t, (int, float))
                   or not math.isfinite(t) or t <= 0 or int(t) != t for t in raw):
                return None
            targets = tuple(sorted(set(int(t) for t in raw)))
            if not targets:
                return None
            multiplier = float(payload.get("multiplier", 1) or 1)
            unused = float(payload.get("unused_moves_energy", 0) or 0)
            if not math.isfinite(multiplier) or not math.isfinite(unused):
                return None
            return cls(targets, int(score),
                       max(0, int(payload.get("refill_moves", 0) or 0)),
                       bool(payload.get("overflow", True)),
                       bool(payload.get("continue_after_last", False)),
                       max(0.0, unused), max(1.0, multiplier))
        except (TypeError, ValueError, OverflowError):
            return None


def goal_from_snapshot(snapshot) -> dict | None:
    """Use the memory score/rules; absent or malformed data disables policy."""
    if not isinstance(snapshot, dict):
        return None
    state = snapshot.get("state") or {}
    players = state.get("players") or []
    rules = state.get("rules") or {}
    if not state.get("is_singleplayer_board") or len(players) != 1:
        return None
    me = players[0]
    engine = rules.get("engine_fields") or {}
    targets = rules.get("solo_targets")
    if targets is None:
        targets = engine.get("soloTargets")
    refill = rules.get("solo_refill_mode")
    if refill is None:
        refill = engine.get("soloRefillMode", False)
    moves_per_turn = rules.get("moves_per_turn")
    if moves_per_turn is None:
        moves_per_turn = engine.get("movesPerTurn")
    goal = SoloGoalState.from_payload(dict(
        targets=targets, score=me.get("score"),
        refill_moves=(moves_per_turn if refill else 0),
        overflow=engine.get("soloOverflowPastTarget", True),
        continue_after_last=engine.get("soloContinueAfterLastTarget", False),
        unused_moves_energy=engine.get("soloUnusedMovesEnergyWorth", 0),
        multiplier=me.get("score_multiplier", 1),
    ))
    if goal is None:
        return None
    return asdict(goal)
