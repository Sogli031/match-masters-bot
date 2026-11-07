"""Rules read out of libil2cpp.so on 2026-10-14 (see docs/booster_logic_from_code.md).

* one extra move per move (GameLogic.gotExtraTurnDuringMove),
* a booster's own blast never returns the move (IsAbilityUsedThisMove),
* UFO SE eyes do not fill on a move the booster was used in,
* Cleo piece picks an extra-move colour unless the extra is prevented.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402

Y, P, O, G, R, B = ms.YELLOW, ms.PURPLE, ms.ORANGE, ms.GREEN, ms.RED, ms.BLUE


def blank_result(**kwargs):
    return ms.SimulationResult(candidate=None, board=[], special_board=[], **kwargs)


def test_simulation_result_holds_at_most_one_extra_move():
    result = blank_result(extra_moves=2.0, direct_extra_moves=3.0)
    assert result.extra_moves == 1.0
    assert result.direct_extra_moves == 1.0
    result.extra_moves += 1.0
    assert result.extra_moves == 1.0
    fractional = blank_result(extra_moves=0.4)
    assert fractional.extra_moves == 0.4


def test_two_fours_in_one_swap_earn_one_extra():
    # Post-swap board: a red four in row 0 and a green four in row 4.
    board = [
        [R, R, R, R, Y],
        [P, O, Y, P, O],
        [Y, P, O, Y, P],
        [O, Y, P, O, Y],
        [G, G, G, G, P],
    ]
    specials = [[ms.EMPTY] * 5 for _ in range(5)]
    candidate = ms.MoveCandidate((0, 3), (0, 4), ms.Direction.RIGHT, board, specials)
    result = ms.simulate_candidate(candidate)
    fours = [m for m in result.cascade_matches[0] if len(m.cells) >= 4]
    assert len(fours) == 2
    assert result.extra_moves == 1.0
    assert result.direct_extra_moves == 1.0


def test_booster_target_simulation_never_returns_the_move():
    def simulate():
        return blank_result(extra_moves=1.0, direct_extra_moves=1.0)

    result = ms._average_booster_target_simulation(simulate, seed=1)
    assert result.extra_moves == 0.0
    assert result.direct_extra_moves == 0.0


def ufo_swap():
    """Post-swap board with one red line through the target (2,2)."""
    board = [
        [Y, P, O, G, P],
        [P, O, Y, P, O],
        [R, R, R, O, Y],
        [O, Y, P, O, P],
        [P, O, Y, P, O],
    ]
    specials = [[ms.EMPTY] * 5 for _ in range(5)]
    return ms.MoveCandidate((2, 3), (2, 2), ms.Direction.LEFT, board, specials)


def abductions(result):
    return [e for e in result.intent_events if e["type"] == ms.UFO_ABDUCTION_EVENT]


def test_ufo_eyes_wait_while_the_booster_was_used_this_move():
    with ms.ufo_abduction_active(2), ms.ability_used_active(True):
        result = ms.simulate_candidate(ufo_swap())
    assert abductions(result) == []


def test_free_move_perk_does_not_stop_the_ufo_eyes():
    # special_ability folds the free-move perk in for the board-model hooks;
    # the eye fill reads the booster half only.
    with ms.ufo_abduction_active(2), ms.ability_used_active(True, booster_used=False):
        result = ms.simulate_candidate(ufo_swap())
    events = abductions(result)
    assert len(events) == 1
    assert events[0]["colors"] == [R]


def test_an_l_with_a_five_arm_is_a_five():
    # Five across row 0, plus two below its first cell: GetComboType asks
    # IsFiveShapeFast before RShape.
    cells = [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (1, 0), (2, 0)]
    assert ms.classify_cells(cells) == "five"
    # A plain 3+3 L stays an L.
    assert ms.classify_cells([(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)]) == "l"
    # A four with a three through it is still not a five.
    assert ms.classify_cells(
        [(0, 0), (0, 1), (0, 2), (0, 3), (1, 1), (2, 1)]
    ) != "five"


def test_extra_moves_off_when_the_ruleset_disables_them():
    board = [
        [R, R, R, R, Y],
        [P, O, Y, P, O],
        [Y, P, O, Y, P],
        [O, Y, P, O, Y],
        [P, Y, O, P, O],
    ]
    specials = [[ms.EMPTY] * 5 for _ in range(5)]
    candidate = ms.MoveCandidate((0, 3), (0, 4), ms.Direction.RIGHT, board, specials)
    assert ms.simulate_candidate(candidate).extra_moves == 1.0
    with ms.extra_moves_enabled_active(False):
        result = ms.simulate_candidate(candidate)
    assert result.extra_moves == 0.0
    assert result.direct_extra_moves == 0.0
    with ms.extra_moves_enabled_active(None):
        assert ms.simulate_candidate(candidate).extra_moves == 1.0


def test_booster_blast_blue_is_wasted_not_charged():
    def simulate():
        return blank_result(blue_cells=5.0)

    result = ms._average_booster_target_simulation(simulate, seed=1)
    assert result.blue_cells == 0.0
    assert result.wasted_blue_cells == 5.0


def test_special_blast_cells_score_times_the_combo_multiplier():
    # A horizontal line special at (2,0) inside a red three: the match clears
    # (2,0)-(2,2); the blast adds the rest of row 2.
    board = [
        [Y, P, O, G, P],
        [P, O, Y, P, O],
        [R, R, R, O, Y],
        [O, Y, P, O, P],
        [P, O, Y, P, O],
    ]
    specials = [[ms.EMPTY] * 5 for _ in range(5)]
    specials[2][0] = ms.SPECIAL_HORIZONTAL
    candidate = ms.MoveCandidate((2, 3), (2, 2), ms.Direction.LEFT, board, specials)
    rally = {c: 1.0 for c in (Y, P, O, G, R, B)}
    plain = ms._instant_score(ms.simulate_candidate(candidate), rally)
    with ms.special_combo_score_multiplier_active(3):
        tripled = ms.simulate_candidate(candidate)
    # (2,3) and (2,4) are the blast-only cells: +2 each at x3.
    assert ms._instant_score(tripled, rally) == plain + 4.0
    # Colour readers never see the surplus.
    assert tripled.cleared_color_counts.get(O, 0) == ms.simulate_candidate(
        candidate
    ).cleared_color_counts.get(O, 0)
