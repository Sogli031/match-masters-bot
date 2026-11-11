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


def mutation_lab_pick_targets(engine, solo_targets) -> tuple[list[int], int]:
    """(score thresholds that open a Mutation Lab pick, moves each pick adds).

    MatchRulesModel.mutationLabTargetsPerSoloTarget holds one list per solo
    target, e.g. [[0, 100, 250, 500]] under soloTargets [2100]; crossing one
    offers a mutation and mutationLabMovesRefill more moves (3). The lists are
    read as offsets from the previous solo target -- the same as absolute with
    the single target recorded so far. 0 opens the match and buys nothing.
    """
    if not isinstance(engine, dict) or not engine.get("isMutationLab"):
        return [], 0
    try:
        moves = int(engine.get("mutationLabMovesRefill") or 0)
    except (TypeError, ValueError):
        return [], 0
    per_target = engine.get("mutationLabTargetsPerSoloTarget")
    if moves <= 0 or not isinstance(per_target, (list, tuple)):
        return [], 0
    try:
        ends = sorted(int(t) for t in solo_targets or ())
    except (TypeError, ValueError):
        return [], 0
    picks = set()
    for index, offsets in enumerate(per_target):
        if not isinstance(offsets, (list, tuple)) or index >= len(ends):
            continue
        base = ends[index - 1] if index > 0 else 0
        for offset in offsets:
            if isinstance(offset, bool) or not isinstance(offset, (int, float)):
                continue
            value = base + int(offset)
            if base < value < ends[index]:
                picks.add(value)
    return sorted(picks), moves


def _decoded_engine_rules(engine, decoded_rules, targets, rules_id=None) -> dict:
    """``engine`` with list fields the snapshot left undecoded taken from
    ``decoded_rules`` (the exact-refill reader's match_profile rules).

    The snapshot's engine_fields carries a nested list such as
    mutationLabTargetsPerSoloTarget only as its type name; match_profile
    decodes it. Those rules are cached per match, so they are used only when
    they are this match's: the same rules id and the same solo targets.
    """
    if not isinstance(decoded_rules, dict):
        return engine
    match_id = rules_id if rules_id is not None else engine.get("id")
    if decoded_rules.get("id") != match_id or (
            list(decoded_rules.get("soloTargets") or []) != list(targets or [])):
        return engine
    merged = dict(engine)
    if not isinstance(merged.get("mutationLabTargetsPerSoloTarget"), (list, tuple)):
        merged["mutationLabTargetsPerSoloTarget"] = decoded_rules.get("mutationLabTargetsPerSoloTarget")
    for key in ("isMutationLab", "mutationLabMovesRefill"):
        if merged.get(key) is None:
            merged[key] = decoded_rules.get(key)
    return merged


def goal_from_snapshot(snapshot, decoded_rules=None) -> dict | None:
    """Use the memory score/rules; absent or malformed data disables policy.

    ``decoded_rules``: optional MatchRulesModel fields decoded in full (the
    exact-refill reader's match_profile), for lists the snapshot cannot carry.
    """
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
    refill_moves = moves_per_turn if refill else 0
    picks, pick_moves = mutation_lab_pick_targets(
        _decoded_engine_rules(engine, decoded_rules, targets, rules.get("id")), targets)
    if picks:
        # A Mutation Lab pick is a stage the score crosses: it hands out
        # mutationLabMovesRefill moves, so the move that crosses it is not the
        # last one (2026-11-11 15:28:52: 88 -> 100 on the last move, then 3
        # moves and the 6/7 meter carried on). Real stages refill more; the
        # smaller refill is the one a crossing is sure to buy.
        real_stages = [t for t in targets if t < max(targets)]
        refill_moves = min(refill_moves, pick_moves) if real_stages and refill_moves else pick_moves
        targets = sorted(set(int(t) for t in targets) | set(picks))
    goal = SoloGoalState.from_payload(dict(
        targets=targets, score=me.get("score"),
        refill_moves=refill_moves,
        overflow=engine.get("soloOverflowPastTarget", True),
        continue_after_last=engine.get("soloContinueAfterLastTarget", False),
        unused_moves_energy=engine.get("soloUnusedMovesEnergyWorth", 0),
        multiplier=me.get("score_multiplier", 1),
    ))
    if goal is None:
        return None
    return asdict(goal)
