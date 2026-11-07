"""Strategy review fixes (2026-09-22).

One focused check per fixed review item in move_strategy.py; the items that
were checked and deliberately left alone have a test pinning the measured
behaviour instead (Blow Em Up's created-special charge).
"""
from dataclasses import replace

import move_strategy as ms


def _no_match_board():
    # A 7x7 colour board with no run of three anywhere.
    pattern = [2, 3, 4, 6, 2, 3, 4]
    return [[pattern[(col + 2 * row) % 7] for col in range(7)] for row in range(7)]


def _empty_specials():
    return [[0] * 7 for _ in range(7)]


# --- 1. Versus handover board goes through the special-swap simulation -------

def _rocket_bomb_board():
    board = _no_match_board()
    specials = _empty_specials()
    specials[3][3] = ms.SPECIAL_HORIZONTAL
    specials[3][4] = ms.SPECIAL_BOMB
    return board, specials


def test_handover_board_of_a_matchless_special_combo_is_exploded(monkeypatch):
    board, specials = _rocket_bomb_board()
    ranked = ms.rank_moves(board, specials)
    combo = next(
        item
        for item in ranked
        if {item.candidate.start, item.candidate.target} == {(3, 3), (3, 4)}
    )
    assert not combo.cascade_matches or not combo.has_direct_match_layer
    seen = {}

    def capture(board_arg, special_arg, *args):
        seen["board"] = ms.grid_to_lists(board_arg)
        seen["special"] = ms.grid_to_lists(special_arg)
        return []

    monkeypatch.setattr(ms, "_rank_candidate_results_cached", capture)
    ms._versus_handover_opponent_replies(combo, "None", False, None, False, {}, {}, {})
    expected = ms._simulate_post_move_result(combo, "None", False, None, False)
    assert expected is not None
    assert seen["board"] == ms.grid_to_lists(expected.board)
    # The rocket and the bomb are gone from the board the opponent inherits.
    assert seen["special"][3][3] != ms.SPECIAL_HORIZONTAL
    assert seen["special"][3][4] != ms.SPECIAL_BOMB


# --- 2. Froggy lotus: the rush pays the charge it took the flat credit for ----

LOTUS_BOARD = [
    [2, 1, 6, 3, 4, 5, 6],
    [1, 4, 1, 6, 3, 2, 1],
    [1, -1, 5, 4, 3, 3, 4],
    [5, 3, 1, 5, 4, 1, 2],
    [1, 3, 1, 4, 3, 2, 5],
    [5, 4, 2, 4, 5, 6, 5],
    [3, 3, 5, 5, 6, 4, 6],
]
LOTUS_SPECIALS = [
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 20, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
]


def _lotus_moves(context):
    ranked = ms.rank_moves(LOTUS_BOARD, LOTUS_SPECIALS)
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    lotus = ms.rank_froggy_lotus_moves(
        ranked,
        LOTUS_BOARD,
        LOTUS_SPECIALS,
        booster_state=booster,
        strategy_context=context,
    )
    return {
        (item.candidate.start, item.candidate.target): item for item in lotus
    }, {(item.candidate.start, item.candidate.target): item for item in ranked}


def test_rush_lotus_score_carries_its_charge_value():
    rush = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, booster_rush=True)
    lotus, ranked = _lotus_moves(rush)
    blue = [item for item in lotus.values() if item.froggy_lotus_charge_cells > 0]
    assert blue
    for item in blue:
        base = ranked[(item.candidate.start, item.candidate.target)]
        assert not base.froggy_lotus_gathered
        assert item.froggy_lotus_charge_value > 0
        extra = item.extra_move_bonus - base.extra_move_bonus
        expected = base.score + item.froggy_lotus_bonus + extra + item.froggy_lotus_charge_value
        assert abs(item.score - expected) < 1e-6
        # Charge is not board points.
        assert abs(item.instant_score - (base.instant_score + item.froggy_lotus_bonus)) < 1e-6


def test_point_race_lotus_keeps_charge_out_of_the_score():
    race = ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)
    lotus, ranked = _lotus_moves(race)
    blue = [item for item in lotus.values() if item.froggy_lotus_charge_cells > 0]
    assert blue
    for item in blue:
        base = ranked[(item.candidate.start, item.candidate.target)]
        extra = item.extra_move_bonus - base.extra_move_bonus
        assert abs(item.score - (base.score + item.froggy_lotus_bonus + extra)) < 1e-6


# --- 3. Blow Em Up: the created special's cell charges twice (measured) -------

def test_blow_em_up_blue_four_charges_the_created_special_again():
    # Not a double count: four recorded specialsAutoExplode blue fours
    # (2026-09-19 02-58-49 / 03-07-32, 2026-09-20 19-31-47, 2026-09-18
    # 23-08-11) filled the meter by physical blue + 1, which is what this
    # predicts. Pinned so the "fix" is not applied again.
    board = [
        [2, 3, 4, 6, 2, 3, 4],
        [3, 4, 6, 2, 3, 4, 6],
        [4, 6, 2, 3, 4, 6, 2],
        [1, 1, 5, 1, 6, 2, 3],
        [6, 2, 1, 4, 2, 3, 4],
        [2, 3, 4, 6, 3, 4, 6],
        [3, 4, 6, 2, 4, 6, 2],
    ]
    ranked = ms.rank_moves(board, _empty_specials(), explode_created_specials_immediately=True)
    four = next(
        item
        for item in ranked
        if {item.candidate.start, item.candidate.target} == {(3, 2), (4, 2)}
    )
    assert four.blue_cells == 5


# --- 5. A chained Joo Joo skull ray leaves a lotus / drone standing -----------

def test_chained_skull_ray_does_not_clear_a_blocked_lotus():
    board = _no_match_board()
    specials = _empty_specials()
    board[3][3] = ms.BLUE
    specials[3][0] = ms.SPECIAL_HORIZONTAL
    specials[3][3] = ms.SPECIAL_JOOJOO_SKULL
    board[0][3] = ms.BLOCKED
    specials[0][3] = ms.SPECIAL_FROGGY_LOTUS
    board[6][3] = ms.BLOCKED
    specials[6][3] = ms.SPECIAL_BILLIE_DRONE
    work = ms.clone_grid(board)
    work_special = ms.clone_grid(specials)
    _count, _activated, cleared, *_rest = ms._clear_cells_with_specials(
        work, work_special, {(3, 0)}
    )
    # The skull fired (its column was cleared) ...
    assert (3, 3) in cleared and (1, 3) in cleared and (5, 3) in cleared
    # ... but the blocked cells kept their pieces.
    assert (0, 3) not in cleared and (6, 3) not in cleared
    assert work_special[0][3] == ms.SPECIAL_FROGGY_LOTUS
    assert work_special[6][3] == ms.SPECIAL_BILLIE_DRONE


# --- 6. Disco next-extra key is seeded and keeps the explode flag -------------

def test_disco_next_extra_simulation_is_seeded_and_explodes(monkeypatch):
    ranked = ms.rank_moves(LOTUS_BOARD, _empty_specials())
    evaluation = next(item for item in ranked if not ms._move_has_uncertain_cascade(item))
    seen = []

    def fake(original_board, candidate, **kwargs):
        rng = ms._RANDOM_SPECIAL_TARGET_RNG
        seen.append(
            (
                kwargs.get("explode_created_specials_immediately"),
                rng.getstate() if rng is not None else None,
            )
        )
        return None

    monkeypatch.setattr(ms, "_simulate_created_candidate", fake)
    assert ms._best_next_extra_score_after_disco(
        evaluation, "None", False, None, explode_created_specials_immediately=True
    ) == 0.0
    assert ms._disco_post_board_evaluations(
        evaluation, "None", False, None, explode_created_specials_immediately=True
    ) is None
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    assert ms._best_next_blue_cells_after_disco(
        evaluation, "None", False, None, booster, explode_created_specials_immediately=True
    ) == 0.0
    assert len(seen) == 3
    assert all(explode is True and state is not None for explode, state in seen)
    # One seed for all three: the next-extra key draws what the blue key draws,
    # and cannot flip between repeats.
    assert seen[0][1] == seen[1][1] == seen[2][1]


# --- 7. Random-special resampling keeps the rally table, averages Cleo --------

def test_random_special_samples_average_the_cleo_scores():
    board, specials = _rocket_bomb_board()
    ranked = ms.rank_moves(board, specials)
    base = ms.simulate_candidate(ranked[0].candidate)
    first = replace(base, cleo_scenario_count=2, cleo_risk_score=10.0, cleo_average_score=12.0,
                    cleo_worst_score=4.0, cleo_best_score=20.0, cleo_extra_move_probability=0.0)
    second = replace(first, cleo_risk_score=30.0, cleo_average_score=32.0,
                     cleo_worst_score=8.0, cleo_best_score=40.0, cleo_extra_move_probability=1.0)
    averaged = ms._average_random_special_results([first, second])
    assert averaged.cleo_risk_score == 20.0
    assert averaged.cleo_average_score == 22.0
    assert averaged.cleo_worst_score == 6.0
    assert averaged.cleo_best_score == 30.0
    assert averaged.cleo_extra_move_probability == 0.5
    assert averaged.cleo_scenario_count == 2


def test_random_special_resampling_passes_the_rally_table(monkeypatch):
    board, specials = _rocket_bomb_board()
    ranked = ms.rank_moves(board, specials)
    base = ms.simulate_candidate(ranked[0].candidate)
    base = replace(
        base,
        intent_events=[{"type": "special_activation", "special": "lightning"}],
    )
    rally = {1: 3.0}
    seen = []

    def fake(*args, **kwargs):
        seen.append(kwargs.get("score_rally_values"))
        return base

    monkeypatch.setattr(ms, "_simulate_created_candidate", fake)
    ms._average_random_special_outcomes(
        board, ranked[0].candidate, base, False, "None", False, False, None,
        score_rally_values=rally,
    )
    assert seen and all(value is rally for value in seen)


# --- 9. Cleo tier 2 needs an actual extra chance ------------------------------

def test_cleo_partner_without_an_extra_is_not_tier_two():
    board = _no_match_board()
    ranked = ms.rank_moves(board, _empty_specials()) or None
    evaluation = ranked[0] if ranked else None
    if evaluation is None:
        board[3][2] = board[3][0]
        ranked = ms.rank_moves(board, _empty_specials())
        evaluation = ranked[0]
    start, target = evaluation.candidate.start, evaluation.candidate.target
    specials = _empty_specials()
    specials[start[0]][start[1]] = ms.SPECIAL_CLEO_BUG
    tier_board = [list(row) for row in board]
    tier_board[target[0]][target[1]] = ms.RED  # not a charge colour
    no_extra = replace(evaluation, extra_moves=0.0, direct_extra_moves=0.0)
    some_extra = replace(evaluation, extra_moves=0.5, direct_extra_moves=0.0)
    assert not ms.has_guaranteed_true_extra(some_extra)
    assert ms._cleo_priority_tier(no_extra, tier_board, specials) == 3
    assert ms._cleo_priority_tier(some_extra, tier_board, specials) == 2


# --- 10. Perk stale-match scan pairs pre-perk colours with pre-perk specials --

def test_perk_clear_stale_scan_uses_the_original_special_board(monkeypatch):
    board = _no_match_board()
    specials = _empty_specials()
    specials[2][2] = ms.SPECIAL_BOMB
    seen = []
    original = ms._preexisting_match_cell_groups

    def spy(board_arg, allow_square_matches=False, match_scan_cache=None, special_board=None):
        seen.append(ms.grid_to_lists(special_board))
        return original(board_arg, allow_square_matches, match_scan_cache, special_board)

    monkeypatch.setattr(ms, "_preexisting_match_cell_groups", spy)
    ms._simulate_clear_cells_perk(
        board, specials, {(2, 2)}, mode="None", allow_square_matches=False
    )
    assert seen and seen[0] == specials


# --- 11. A dragged lotus resolves on the cell it landed on -------------------

def test_dragged_lotus_collects_around_its_new_cell():
    board = _no_match_board()
    specials = _empty_specials()
    # Lotus at (2,1); dragging it up swaps the 3 at (1,1) into (2,1), which
    # completes 3-3-3-3 on row 2. The lotus itself lands on (1,1).
    board[2] = [3, ms.BLOCKED, 3, 3, 2, 6, 4]
    board[1][1] = 3
    specials[2][1] = ms.SPECIAL_FROGGY_LOTUS
    ranked = ms.rank_moves(board, specials)
    lotus = ms.rank_froggy_lotus_moves(ranked, board, specials)
    dragged = [
        item
        for item in lotus
        if {item.candidate.start, item.candidate.target} == {(2, 1), (1, 1)}
    ]
    assert dragged
    for item in dragged:
        cells = [
            event["lotus_cells"]
            for event in item.intent_events
            if event.get("type") == "froggy_lotus_collect"
        ]
        assert cells and all(cell == [[1, 1]] for cell in cells)


# --- 13. count_legal_next_moves: the per-call cache changes nothing ----------

def test_count_legal_next_moves_matches_the_uncached_count():
    board, specials = _rocket_bomb_board()
    board = [list(row) for row in board]
    board[0][2] = board[0][0]
    expected = 0
    pairs = set()
    for candidate in ms.generate_candidates(board, specials):
        pair = frozenset({candidate.start, candidate.target})
        if len(pair) > 1 and pair in pairs:
            continue
        if ms._candidate_creates_swapped_match(board, candidate, False):
            pairs.add(pair)
            expected += 1
    assert ms.count_legal_next_moves(board, specials) == expected
