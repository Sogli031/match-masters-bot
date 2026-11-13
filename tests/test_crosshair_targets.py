"""Crosshair targets from BoardModel.GetCrosshair 0x59718d8 (engine RNG).

Square Match rules carry additionalData.gemPickThreshold: maxTotalPieces 7,
selectionOrder "maxEnergyPieces,maxMatchingColorPieces,maxClassicSpecialPieces"
with counts 3, 0, 0. Each pick shuffles its Where list (x-major) with one draw
per candidate; a strategy with count 0 draws nothing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import move_strategy as ms
from engine_refill import SquareRefill
from engine_rng import EngineRNG
from tests.test_engine_refill import entries, profile


def crosshair_profile(energy=3, matching=0, specials=0, total=7,
                      order="maxEnergyPieces,maxMatchingColorPieces,maxClassicSpecialPieces"):
    p = profile()
    gem = entries({"maxTotalPieces": total, "selectionOrder": order, "maxClassicSpecialPieces": specials,
                   "maxEnergyPieces": energy, "maxMatchingColorPieces": matching})
    p["rules"]["additionalData"] = entries({"gemPickThreshold": gem})
    return p


def board7():
    return [[1 + (x + 2 * y) % 6 for x in range(7)] for y in range(7)]


def where(board):
    return [(y, x) for x in range(len(board[0])) for y in range(len(board))]


def expected(seed, board, special, source, ignore, energy, total):
    """The same algorithm spelled out by hand for the default selection order."""
    rng = EngineRNG.from_seed(seed)
    ignored, selected = set(ignore), []

    def pick(amount, keep):
        ignored.update(selected)
        amount = min(amount, total - len(selected))
        if amount <= 0:
            return
        candidates = [c for c in where(board) if board[c[0]][c[1]] > 0 and keep(c)]
        selected.extend(rng.shuffled(candidates)[:amount])

    pick(energy, lambda c: board[c[0]][c[1]] == 1 and c not in ignored)
    pick(total - len(selected), lambda c: c not in ignored)
    pick(total - len(selected), lambda c: c not in selected)
    return selected, rng.counter


def test_energy_first_then_any_free_piece_with_one_draw_per_candidate():
    board, special = board7(), [[0] * 7 for _ in range(7)]
    source, ignore = (3, 3), {(3, 3), (3, 4), (3, 5)}
    m = SquareRefill.from_profile(crosshair_profile(), seed=4321)
    picks = m.crosshair_targets(board, special, source, ignore)
    want, draws = expected(4321, board, special, source, ignore, 3, 7)
    assert picks == want and len(picks) == 7
    assert sum(board[y][x] == 1 for y, x in picks[:3]) == 3
    assert not set(picks) & ignore
    blues = sum(v == 1 for row in board for v in row)
    assert m.pending_effect_draws == draws == blues + (49 - len(ignore) - 3)
    assert m.rng.counter == 0     # booked for the refill, not consumed yet


def test_zero_count_strategies_draw_nothing():
    board, special = board7(), [[0] * 7 for _ in range(7)]
    m = SquareRefill.from_profile(crosshair_profile(energy=0, total=2), seed=7)
    picks = m.crosshair_targets(board, special, (0, 0), {(0, 0)})
    assert len(picks) == 2
    assert m.pending_effect_draws == 48   # only the any-piece fallback shuffles


def test_classic_specials_strategy_takes_specials_only():
    board, special = board7(), [[0] * 7 for _ in range(7)]
    for cell in [(0, 1), (2, 2), (5, 6)]:
        special[cell[0]][cell[1]] = ms.SPECIAL_BOMB
    m = SquareRefill.from_profile(crosshair_profile(energy=0, specials=2, total=2,
                                                    order="maxClassicSpecialPieces"), seed=99)
    picks = m.crosshair_targets(board, special, (4, 4), {(4, 4)})
    assert len(picks) == 2 and all(special[y][x] == ms.SPECIAL_BOMB for y, x in picks)
    assert m.pending_effect_draws == 3


def test_without_config_the_caller_keeps_its_model():
    m = SquareRefill.from_profile(profile(), seed=1)
    assert m.crosshair_targets(board7(), [[0] * 7 for _ in range(7)], (0, 0), set()) is None


def test_simulator_uses_engine_targets_when_the_hook_is_active():
    board, special = board7(), [[0] * 7 for _ in range(7)]
    m = SquareRefill.from_profile(crosshair_profile(), seed=4321)
    with ms.engine_refill_active(fireworks=m.fireworks_targets):
        cells = ms._crosshair_effect_cells(board, special, 3, 3, excluded_cells={(3, 4)})
        assert ms._crosshair_targets_exact(board, special, 3, 3)
    want, _ = expected(4321, board, special, (3, 3), {(3, 3), (3, 4)}, 3, 7)
    assert cells == {(3, 3), *want}
