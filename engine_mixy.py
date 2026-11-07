"""Mixy Meow's passive on a swipe, as the engine runs it (libil2cpp 5.817).

MixyMeow.OnPlayerInitiatedMatch queues <>c__DisplayClass67_0.<OnPlayerInitiatedMatch>b__0
while TargetColor is unset (1) and UsesLeft >= 1. That callback runs
CheckCombo over the swipe's own combos; the first combo whose colour is in
ActiveColors calls FoundTargetColor:

* UsesLeft -= 1, TargetColor = that colour,
* SourceColors = ActiveColors without the target.

ConvertColor then repaints every paintable piece of a SourceColor into the
target -- all of them, no randomness -- and the swap continues on the repainted
board (AfterValidSwapPerformed), so its matches are found again there.

Ported: use #2 (UsesLeft 1 -> 0). On the 2026-11-07 Funky Tiles + Mixy
recording these replay exactly (board, specials and RNG counter).

Not ported: use #1. AfterCombosDestroy re-deals the code with
RandomizeActiveColors while UsesLeft is still >= 1, and that changes the refill
in a way no placement of its draws reproduces (the counter can agree while the
refilled colours do not). Such a swipe is reported as unsupported
(``model.mixy_redealt``), never predicted.
"""
from __future__ import annotations

from dataclasses import dataclass

MIXY_MEOW = 59
NO_TARGET = 1               # TargetColor while no code colour was matched


@dataclass
class MixyPassive:
    code: frozenset            # simulator colours of ActiveColors
    uses_left: int

    @classmethod
    def from_player(cls, player: dict, engine_to_sim: dict):
        """Our player's live code, or None when no swipe can trigger it."""
        if (player or {}).get("special_ability_type") != MIXY_MEOW:
            return None
        fields = player.get("special_ability_fields") or {}
        uses = (player.get("special_ability_engine") or {}).get("uses_left")
        if fields.get("TargetColor", NO_TARGET) != NO_TARGET or not isinstance(uses, int) or uses < 1:
            return None
        code = frozenset(engine_to_sim[c] for c in fields.get("activeColors") or () if c in engine_to_sim)
        return cls(code, uses) if code else None


def convert_swap(model, candidate, allow_square_matches: bool):
    """The swipe's candidate after Mixy's repaint, or the candidate unchanged.

    On a code match it takes the use; a use that re-deals the code sets
    ``model.mixy_redealt`` (the caller must not trust that swipe).
    """
    import move_strategy as ms

    mixy = getattr(model, "mixy", None)
    if mixy is None or mixy.uses_left < 1:
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
    model.mixy = MixyPassive(mixy.code, mixy.uses_left - 1)
    if mixy.uses_left - 1 >= 1:
        model.mixy_redealt = True
    return ms.MoveCandidate(candidate.start, candidate.target, candidate.direction, board, specials)
