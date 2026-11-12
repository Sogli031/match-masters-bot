"""Mixy Meow's passive on a swipe, as the engine runs it (libil2cpp 5.817).

MixyMeow.OnPlayerInitiatedMatch queues <>c__DisplayClass67_0.<OnPlayerInitiatedMatch>b__0
while TargetColor is unset (1) and UsesLeft >= 1. That callback runs
CheckCombo over the swipe's own combos; the first combo whose colour is in
ActiveColors calls FoundTargetColor:

* UsesLeft -= 1, NumOfPassiveUsesThisTurn += 1, TargetColor = that colour,
* SourceColors = ActiveColors without the target.

ConvertColor then repaints every paintable piece of a SourceColor into the
target -- all of them, no randomness -- and the swap continues on the repainted
board (AfterValidSwapPerformed), so its matches are found again there.

Use #1 (UsesLeft still >= 1 afterwards) re-deals the code:
AfterCombosDestroy -> RandomizeActiveColors (0x5a7788c), see ``redeal``. In
every recording it is the swipe's last RNG work, after all refills, so it is
run on the resting board (``finish_swipe``). The specials that swipe creates in
its own combos sit at the conversion origin (move_strategy
mixy_redeal_replay_active). 2026-11-12: 20 of 20 recorded re-deals whose board
replays give the exact new code and RNG (Debug/refill_unsupported/mixy_redeal,
Multiplier Madness trace 20261112_020924).
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIXY_MEOW = 59
NO_TARGET = 1               # TargetColor while no code colour was matched
# Order of the colour list RandomizeActiveColors filters by the spawning
# colours before shuffling (a static engine list). Recovered from the recorded
# re-deals: it is the only order that fits all of them.
REDEAL_COLOR_ORDER = (6, 3, 5, 7, 4, 2)
REDEAL_FIELDS = ("colorsToPickByActivation", "chanceToPickBlueByMatchesNoBlueMatchAvailable",
                 "chanceToPickBlueByMatchesBlueMatchAvailable", "chanceToRemoveMaxScoreColorByActivation",
                 "chanceToPickMaxScoreColorByActivation")


@dataclass(frozen=True)
class MixyPassive:
    code: frozenset            # simulator colours of ActiveColors
    uses_left: int
    # RandomizeActiveColors' config (REDEAL_FIELDS, chanceToPreventColors), or
    # None when the snapshot lacks it -- then a re-deal is not predicted.
    config: dict | None = field(default=None, compare=False)
    # NumOfPassiveUsesThisTurn before this swipe.
    uses_this_turn: int = field(default=0, compare=False)
    # The swipe took use #1: the code is re-dealt when the swipe ends.
    redeal_pending: bool = field(default=False, compare=False)

    @classmethod
    def from_player(cls, player: dict, engine_to_sim: dict, profile: dict | None = None):
        """Our player's live code, or None when no swipe can trigger it."""
        if (player or {}).get("special_ability_type") != MIXY_MEOW:
            return None
        fields = player.get("special_ability_fields") or {}
        uses = (player.get("special_ability_engine") or {}).get("uses_left")
        if fields.get("TargetColor", NO_TARGET) != NO_TARGET or not isinstance(uses, int) or uses < 1:
            return None
        code = frozenset(engine_to_sim[c] for c in fields.get("activeColors") or () if c in engine_to_sim)
        if not code:
            return None
        config = None
        if all(isinstance(fields.get(name), list) and fields[name] for name in REDEAL_FIELDS):
            config = {name: list(fields[name]) for name in REDEAL_FIELDS}
            config["code_length"] = len(fields.get("activeColors") or ())
            config["prevent"] = _prevent_colors(fields)
        return cls(code, uses, config, _uses_this_turn(player, profile))


def _prevent_colors(fields):
    """chanceToPreventColors as [(colour, chance)], None when not readable.

    Agents before 2026-11-12 wrote the dictionary as its type name or not at
    all; every recorded config with it readable was empty, and so is each
    re-deal they recorded (one more draw per entry would show), so a missing
    value reads as empty.
    """
    value = fields.get("chanceToPreventColors")
    if isinstance(value, dict):
        entries = value.get("entries") if "entries" in value else [
            {"key": k, "value": v} for k, v in value.items()]
        return [(int(e["key"]), int(e["value"])) for e in entries or ()]
    return []


def _uses_this_turn(player, profile) -> int:
    """MixyMeowNumOfPassiveUsesThisTurnKey{index} from the board extra data (absent = 0)."""
    index = (player or {}).get("index", 0)
    key = f"MixyMeowNumOfPassiveUsesThisTurnKey{index}"
    data = (profile or {}).get("board_extra_data") or {}
    for entry in data.get("entries") or ():
        if entry.get("key") == key:
            try:
                return int(entry.get("value"))
            except (TypeError, ValueError):
                return 0
    return 0


def convert_swap(model, candidate, allow_square_matches: bool):
    """The swipe's candidate after Mixy's repaint, or the candidate unchanged.

    On a code match it takes the use. A use that leaves UsesLeft >= 1 re-deals
    the code when the swipe ends (``finish_swipe``); without the re-deal config
    it sets ``model.mixy_redealt`` (the caller must not trust that swipe).
    """
    import move_strategy as ms

    mixy = getattr(model, "mixy", None)
    if mixy is None or mixy.uses_left < 1 or mixy.redeal_pending:
        return candidate
    matches = ms.find_matches(candidate.board, allow_square_matches, candidate.special_board)
    target = next((m.color for m in matches if int(m.color) in mixy.code), None)
    if target is None:
        return candidate
    sources = set(mixy.code) - {int(target)}
    board = [list(row) for row in candidate.board]
    specials = [list(row) for row in candidate.special_board]
    for r, row in enumerate(board):
        for c, color in enumerate(row):
            if color in sources and ms._mixy_convertible_cell(color, specials[r][c]):
                board[r][c] = int(target)
    redeal = mixy.uses_left - 1 >= 1
    model.mixy = MixyPassive(mixy.code, mixy.uses_left - 1, mixy.config, mixy.uses_this_turn + 1,
                             redeal_pending=redeal)
    if redeal and redeal_unsupported(model) is not None:
        model.mixy_redealt = True
    return ms.MoveCandidate(candidate.start, candidate.target, candidate.direction, board, specials)


def redeal_pending(model) -> bool:
    mixy = getattr(model, "mixy", None)
    return bool(mixy is not None and mixy.redeal_pending and not getattr(model, "mixy_redealt", False))


def redeal_unsupported(model) -> str | None:
    """Why the pending re-deal cannot be predicted exactly, or None."""
    mixy = model.mixy
    config = mixy.config
    if config is None or config.get("prevent") is None:
        return "Mixy re-deal: config not in the snapshot"
    profile = getattr(model, "profile", None) or {}
    if _my_slot(profile) is None or not (profile.get("spawning") or {}).get("gameColors"):
        return "Mixy re-deal: player slot or spawning colours unknown"
    if _activation_index(config) is None:
        return "Mixy re-deal: activation index ambiguous"
    return None


def _my_slot(profile):
    me = next((p for p in profile.get("players") or () if p.get("player_type") == 0), None)
    return ((me or {}).get("model") or {}).get("slotType")


def _at(values, index):
    """List value at min(index, Count - 1), as the engine's clamped lookup."""
    return values[max(0, min(index, len(values) - 1))]


def _activation_index(config):
    """ActivatesThisTurn - 1 is not in the snapshot; the live code was dealt
    with colorsToPickByActivation[that index] colours, so its length names it.
    None when two indices fit and their chances differ."""
    picks = config["colorsToPickByActivation"]
    fits = [i for i, amount in enumerate(picks) if amount == config["code_length"]]
    if not fits:
        return None
    values = {(_at(config["chanceToRemoveMaxScoreColorByActivation"], i),
               _at(config["chanceToPickMaxScoreColorByActivation"], i)) for i in fits}
    return fits[0] if len(values) == 1 else None


def _move_colors(board, allow_square_matches):
    """Colours some legal swap of two pieces matches with a moved piece
    (BoardAnalyzer.GetPossibleMoves + NumOfPossibleMoves' predicate)."""
    import move_strategy as ms

    size_r, size_c = len(board), len(board[0])
    colors = set()
    for r in range(size_r):
        for c in range(size_c):
            for dr, dc in ((0, 1), (1, 0)):
                y, x = r + dr, c + dc
                if y >= size_r or x >= size_c:
                    continue
                a, b = board[r][c], board[y][x]
                if a == b or not (ms._is_normal_color(a) and ms._is_normal_color(b)):
                    continue
                if a in colors and b in colors:
                    continue
                swapped = [list(row) for row in board]
                swapped[r][c], swapped[y][x] = b, a
                for match in ms.find_matches(swapped, allow_square_matches):
                    if (r, c) in match.cells or (y, x) in match.cells:
                        colors.add(int(match.color))
    return colors


def redeal(model, board, allow_square_matches: bool = False):
    """RandomizeActiveColors on the resting simulator ``board``: the new code
    as simulator colours. Draws from ``model.rng`` as the engine does: four
    Chance, the shuffle (one Next per colour), one Chance per
    chanceToPreventColors entry. No other draw: a pick only reads the board."""
    from engine_refill import color_maps

    mixy, profile = model.mixy, model.profile
    config = mixy.config
    rng = model.rng
    sim_to_engine, engine_to_sim = color_maps(profile)
    uses = mixy.uses_this_turn            # already counts this swipe's use
    activation = _activation_index(config)
    amount = config["colorsToPickByActivation"][activation]
    pick_blue_no_move = rng.chance(_at(config["chanceToPickBlueByMatchesNoBlueMatchAvailable"], uses))
    pick_blue_move = rng.chance(_at(config["chanceToPickBlueByMatchesBlueMatchAvailable"], uses))
    remove_max = rng.chance(_at(config["chanceToRemoveMaxScoreColorByActivation"], activation))
    pick_max = rng.chance(_at(config["chanceToPickMaxScoreColorByActivation"], activation))
    game_colors = set(profile["spawning"]["gameColors"]) - {NO_TARGET}
    candidates = [color for color in REDEAL_COLOR_ORDER if color in game_colors]
    candidates = rng.shuffled(candidates)
    for color, chance in config["prevent"]:
        if rng.chance(chance) and color in candidates:
            candidates.remove(color)

    sim_moves = _move_colors(board, allow_square_matches)
    moves = {sim_to_engine[c] for c in sim_moves if c in sim_to_engine}
    me = _my_slot(profile)
    code = []
    if pick_blue_move if me in moves else pick_blue_no_move:
        code.append(me)
        if me in candidates:
            candidates.remove(me)
    overrides = (profile.get("rules") or {}).get("_colorScoreOverride")
    if overrides:
        scores = {int(e["key"]): int(e["value"]) for e in overrides.get("entries") or ()}
        best, best_score = NO_TARGET, 1
        for color in candidates:
            if color in scores and scores[color] > best_score:
                best, best_score = color, scores[color]
        if best != NO_TARGET:
            if remove_max and best in candidates:
                candidates.remove(best)
            if pick_max:
                code.append(best)
                if best in candidates:
                    candidates.remove(best)
    if me in candidates:
        candidates.remove(me)
    for color in list(candidates):
        if amount <= len(code) or color in code or color not in moves:
            continue
        code.append(color)
        candidates.remove(color)
    code += candidates[:max(0, amount - len(code))]
    return [engine_to_sim[c] for c in code if c in engine_to_sim]


def finish_swipe(model, board):
    """Run a pending re-deal on the swipe's resting board; the code is live again."""
    if not redeal_pending(model):
        return
    mixy = model.mixy
    square = bool((model.profile.get("spawning") or {}).get("<SquareMatchesAvailable>k__BackingField"))
    code = redeal(model, board, square)
    model.mixy = MixyPassive(frozenset(code), mixy.uses_left, dict(mixy.config, code_length=len(code)),
                             mixy.uses_this_turn)
