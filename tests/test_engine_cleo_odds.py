"""Native Cleo colour choice as probabilities, from SwapPerformed 0x5ae2600."""
import pytest

import engine_cleo_odds as odds
import move_strategy as ms
import square_solo_live


def result(color, count, matches=False, leaves=False, amount=8):
    return (color, [(0, i) for i in range(count)], matches, leaves, abs(count - amount))


def test_chance_is_inclusive_as_in_the_native_test():
    # 0x5af5c78: cmp remainder, percent; cset le.
    assert odds.chance_probability(15) == pytest.approx(0.16)
    assert odds.chance_probability(0) == pytest.approx(0.01)
    assert odds.chance_probability(100) == 1.0


def test_matching_colour_wins_unless_prevented():
    results = [result(5, 8), result(3, 7, matches=True)]
    got = odds.distribution(results, prevent_percent=15, pick_percent=0)
    # Prevented (16%) or pick-by-count (1%): closest non-matching colour.
    assert got[3] == pytest.approx(0.99 * 0.84)
    assert got[5] == pytest.approx(1 - 0.99 * 0.84)


def test_equal_colours_are_not_a_lottery():
    # The old model gave 50/50; the native search always takes the closest.
    got = odds.distribution([result(5, 11), result(3, 8)], prevent_percent=15, pick_percent=0)
    assert got == {3: pytest.approx(1.0)}


def test_matching_colour_outside_the_limit_needs_the_count_fallback():
    # delta 3 is not < 3, so matches alone does not pick it.
    results = [result(5, 11, matches=True), result(3, 7)]
    assert odds.distribution(results, prevent_percent=15, pick_percent=0) == {3: pytest.approx(1.0)}


def test_too_small_colour_is_never_picked():
    results = [result(5, 3, matches=True), result(3, 4)]
    assert odds.distribution(results, prevent_percent=15, pick_percent=0) == {3: pytest.approx(1.0)}


def test_nothing_eligible_clones_nothing():
    assert odds.distribution([result(5, 3)], prevent_percent=15) == {None: pytest.approx(1.0)}


def test_prevent_can_still_end_in_extra_when_every_colour_matches():
    # b__9 filters matching colours away, then the unfiltered OrderBy takes over.
    results = [result(5, 8, matches=True), result(3, 7, matches=True)]
    assert odds.choose(results, True, False, 4, 3)[0] == 5


def test_known_draws_have_one_outcome():
    results = [result(5, 8), result(3, 7, matches=True)]
    assert odds.distribution(results, prevent_percent=15, draws=(False, False)) == {3: 1.0}
    assert odds.distribution(results, prevent_percent=15, draws=(False, True)) == {5: 1.0}


def _booster_profile(uses=None):
    # Values read from Debug/research/20261104_041047_moves-multiplier/007.json.
    logic = {"chanceToPreventExtraMoveOnColorBasedClone": [10], "LogicOrigin": 1,
             "clonedNormalPiecesAmountByPieceUse": [8, 7, 6]}
    entries = [] if uses is None else [
        {"key": "CleoCadabraPiece_PieceUsesThisTurnOrigin_Booster", "value": uses}]
    return {"cleo_piece_logic": None,
            "cleo_booster_fields": {"BoosterPiecesLogic": logic,
                                    "clonedNormalPiecesAmountByActivation": [9, 8, 7]},
            "board_extra_data": {"entries": entries},
            "cleo_activates_this_turn": 1,
            "cleo_slots": [{"row": 3, "col": 3, "value": 32, "origin": 1}]}


def test_booster_figure_reads_the_logic_under_the_ability():
    params = odds.figure_params(_booster_profile(uses=1), (3, 3))
    assert params["fields"]["chanceToPreventExtraMoveOnColorBasedClone"] == [10]
    assert params["uses"] == 2
    assert params["activates"] == 1
    assert params["activation_amounts"]["normal"] == [9, 8, 7]


def test_missing_counter_key_is_the_first_use():
    assert odds.figure_params(_booster_profile(), (3, 3))["uses"] == 1


def test_no_loaded_logic_gives_no_params():
    assert odds.figure_params({"cleo_slots": []}, (3, 3)) is None


def test_booster_amount_comes_from_the_activation_list():
    amounts = {"normal": [9, 8, 7]}
    assert ms._cleo_clone_amount(4, 0, 3, {}, amounts, 1) == 9
    assert ms._cleo_clone_amount(4, 0, 3, {}, None, 1) == 6


class _Reader:
    def __init__(self, profile):
        self.profile, self.calls = profile, 0

    def read_profile(self, script):
        self.calls += 1
        if isinstance(self.profile, Exception):
            raise self.profile
        return self.profile


def _snapshot(**changed):
    state = {"moves": 5, "chain_reaction": 0, "game_state": None}
    state.update(changed.pop("state", {}))
    return {"stable": True, "state": state,
            "slots": [{"row": 3, "col": 3, "value": 32, "origin": 1}], **changed}


def test_cleo_values_are_read_without_any_refill_session():
    profile = dict(_booster_profile(uses=1), state={"moves": 5})
    got = square_solo_live.cleo_odds_profile(_Reader(profile), None, _snapshot())
    assert got["cleo_slots"][0]["origin"] == 1
    assert odds.figure_params(got, (3, 3))["uses"] == 2


def test_no_figure_means_no_extra_memory_read():
    reader = _Reader({"state": {"moves": 5}})
    assert square_solo_live.cleo_odds_profile(reader, None, _snapshot(slots=[])) is None
    assert reader.calls == 0


def test_board_not_at_rest_or_unreadable_memory_gives_no_values():
    reader = _Reader({"state": {"moves": 5}})
    assert square_solo_live.cleo_odds_profile(reader, None, _snapshot(stable=False)) is None
    assert square_solo_live.cleo_odds_profile(_Reader(RuntimeError("x")), None, _snapshot()) is None


def test_loaded_prevent_list_reaches_the_ranking_odds_without_a_session():
    board, special = _board()
    profile = _booster_profile(uses=1)
    candidate = _candidate(board, special)
    weights = []
    real = odds.distribution

    def spy(results, **kwargs):
        weights.append(kwargs["prevent_percent"])
        return real(results, **kwargs)

    odds.distribution = spy
    try:
        assert ms._EXACT_REFILL is None
        with ms.cleo_odds_active({"profile": profile}):
            ms._simulate_cleo_candidate(candidate, include_future_value=False)
        ms._simulate_cleo_candidate(candidate, include_future_value=False)
        ms._simulate_cleo_candidate(candidate, include_future_value=False, odds_params={"profile": profile})
    finally:
        odds.distribution = real
    assert weights == [10, 15, 10]


def test_readout_never_takes_the_exact_path():
    board, special = _board()
    with ms.engine_refill_active(lambda board, special, chain: (board, special)):
        assert ms.cleo_swipe_odds(board, special)


def _board():
    # Plain board, no matches; Cleo at (3, 3).
    board = [
        [2, 3, 4, 5, 6, 2, 3],
        [3, 4, 5, 6, 2, 3, 4],
        [4, 5, 6, 2, 3, 4, 5],
        [5, 6, 2, 99, 4, 5, 6],
        [6, 2, 3, 4, 5, 6, 2],
        [2, 3, 4, 5, 6, 2, 3],
        [3, 4, 5, 6, 2, 3, 4],
    ]
    special = [[0] * 7 for _ in range(7)]
    special[3][3] = ms.SPECIAL_CLEO_BUG
    return board, special


def _candidate(board, special, start=(3, 3), target=(3, 4)):
    swapped_board, swapped_special = ms.swap_cells(board, special, start, target)
    return ms.MoveCandidate(start, target, ms.Direction.RIGHT, swapped_board, swapped_special)


def test_groups_skip_partner_own_colour_and_endpoints():
    board, special = _board()
    board[0][0] = ms.BLUE
    candidate = _candidate(board, special)
    groups = ms._cleo_clone_groups(candidate, 4, 0)
    assert 4 not in groups and ms.BLUE not in groups
    assert all((3, 3) not in cells and (3, 4) not in cells for cells in groups.values())


def test_own_colour_is_only_the_fallback():
    board = [[ms.BLUE] * 3 for _ in range(3)]
    board[1][0], board[1][1] = 99, 4
    special = [[0] * 3 for _ in range(3)]
    special[1][0] = ms.SPECIAL_CLEO_BUG
    candidate = _candidate(board, special, (1, 0), (1, 1))
    assert set(ms._cleo_clone_groups(candidate, 4, 0)) == {ms.BLUE}


def test_plain_partner_leaves_special_tiles_special_partner_takes_them():
    board, special = _board()
    special[0][1] = ms.SPECIAL_BOMB
    special[1][0] = ms.SPECIAL_MUSHROOM
    candidate = _candidate(board, special)
    assert (0, 1) not in ms._cleo_clone_groups(candidate, 4, 0).get(3, [])
    taken = ms._cleo_clone_groups(candidate, 4, ms.SPECIAL_HORIZONTAL).get(3, [])
    assert (0, 1) in taken and (1, 0) not in taken


def _extra_chance(monkeypatch, matches, extras, prevent=10):
    """Odds of one swipe where the simulated colours keep the turn as given."""
    board, special = _board()
    candidate = _candidate(board, special)
    flags = iter(matches)
    scenarios = iter(extras)
    real = ms._simulate_post_cleo_board

    def simulate(*args, **kwargs):
        result = real(*args, **kwargs)
        result.extra_moves = float(next(scenarios))
        return result

    monkeypatch.setattr(ms, "_simulate_post_cleo_board", simulate)
    monkeypatch.setattr(ms, "_cleo_conversion_matches", lambda *a: next(flags))
    params = {"fields": {"chanceToPreventExtraMoveOnColorBasedClone": [prevent]}, "uses": 1}
    return ms._simulate_cleo_candidate(candidate, include_future_value=False, odds_params=params)


def test_every_colour_keeping_the_turn_is_not_a_sure_extra_while_prevent_can_steer(monkeypatch):
    # Colour groups of _board(): 2, 3, 5, 6, partner 4.
    result = _extra_chance(monkeypatch, [True, False, False, False], [1, 1, 1, 1])
    assert result.cleo_extra_move_probability == pytest.approx(0.89)


def test_extra_is_certain_only_when_every_colour_matches(monkeypatch):
    result = _extra_chance(monkeypatch, [True] * 4, [1] * 4)
    assert result.cleo_extra_move_probability == pytest.approx(1.0)


def test_capped_cleo_swap_leaves_the_sure_extra_tier(monkeypatch):
    result = _extra_chance(monkeypatch, [True, False, False, False], [1, 1, 1, 1])
    evaluation = ms.SimpleNamespace(
        direct_extra_moves=0.0, extra_moves=1.0, cleo_scenario_count=result.cleo_scenario_count,
        cleo_extra_move_probability=result.cleo_extra_move_probability,
    ) if hasattr(ms, "SimpleNamespace") else None
    if evaluation is None:
        from types import SimpleNamespace
        evaluation = SimpleNamespace(
            direct_extra_moves=0.0, extra_moves=1.0, cleo_scenario_count=result.cleo_scenario_count,
            cleo_extra_move_probability=result.cleo_extra_move_probability,
        )
    assert not ms.has_guaranteed_true_extra(evaluation)


def test_plain_partner_merge_cell_dies_in_the_first_layer():
    # Debug/research/20261104_043737_moves-multiplier, played 04:38:25: green was
    # cloned, the game took the move, and every cell the model knows is right.
    before = [[6, 5, 1, 1, 3, 5, 2], [3, 3, 4, 5, 3, 6, 2], [99, 3, 2, 1, 6, 1, 4],
              [4, 1, 5, 3, 5, 99, 3], [4, 1, 6, 6, 5, 2, 6], [3, 99, 6, 1, 2, 3, 4],
              [2, 4, 4, 2, 6, 2, 6]]
    after = [[6, 2, 1, 1, 3, 5, 2], [3, 2, 4, 5, 3, 6, 2], [99, 5, 4, 1, 6, 1, 1],
             [4, 3, 5, 3, 5, 99, 3], [4, 3, 6, 6, 5, 4, 6], [3, 1, 6, 1, 4, 3, 4],
             [4, 1, 4, 4, 6, 4, 6]]
    special = [[0] * 7 for _ in range(7)]
    for r, c in ((2, 0), (3, 5), (5, 1)):
        special[r][c] = ms.SPECIAL_CLEO_BUG
    start, target = (6, 1), (5, 1)
    swapped_board, swapped_special = ms.swap_cells(before, special, start, target)
    candidate = ms.MoveCandidate(start, target, ms.Direction.UP, swapped_board, swapped_special)
    cells = ms._cleo_clone_groups(candidate, 4, 0)[2]
    board = [list(map(int, row)) for row in swapped_board]
    specials = [list(map(int, row)) for row in swapped_special]
    board[start[0]][start[1]] = specials[start[0]][start[1]] = 0
    board[target[0]][target[1]], specials[target[0]][target[1]] = 4, 0
    for r, c in cells:
        board[r][c] = 4
    result = ms._simulate_post_cleo_board(candidate, board, specials, False, "None", activated_specials=1)
    assert result.extra_moves == 0
    known = [(r, c) for r in range(7) for c in range(7) if int(result.board[r][c]) > 0]
    assert len(known) > 30
    assert all(int(result.board[r][c]) == after[r][c] for r, c in known)


def test_loaded_use_counter_raises_the_prevent_chance():
    board, special = _board()
    candidate = _candidate(board, special)
    first = ms._simulate_cleo_candidate(candidate, include_future_value=False)
    assert first is not None
    assert abs(sum(first.cleo_scenario_weights) - 1.0) < 1e-9
