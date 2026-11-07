import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import move_strategy as ms


def result(color=ms.PURPLE):
    board = [[ms.GREEN] * 4 for _ in range(4)]
    board[1][:3] = [color] * 3
    specials = [[ms.EMPTY] * 4 for _ in range(4)]
    candidate = ms.MoveCandidate((0, 1), (1, 1), ms.Direction.DOWN, board, specials)
    match = ms.MatchGroup(frozenset((1, col) for col in range(3)), color, 'three')
    return ms.SimulationResult(candidate, board, specials, matches=[match],
                               cascade_matches=[[match]], cascade_count=1,
                               cleared_cells=3, cleared_color_counts={color: 3})


def evaluate(r, mode=ms.GameMode.MULTIPLIER_MADNESS):
    return ms.evaluate_simulation(r, mode, include_future_value=False)


@pytest.mark.parametrize('multiplier', [1, 10, 50])
def test_purple_growth_keeps_priority_at_high_multiplier(multiplier):
    with ms.score_multiplier_state(multiplier, 3):
        purple, yellow = evaluate(result()), evaluate(result(ms.YELLOW))
        assert purple.multiplier_madness_points == 1
        assert purple.mode_bonus - yellow.mode_bonus == pytest.approx(18)
        assert purple.score > yellow.score
        assert ms._weighted_priority(purple, ms.GameMode.MULTIPLIER_MADNESS) > ms._weighted_priority(
            yellow, ms.GameMode.MULTIPLIER_MADNESS)


def test_count_combos_including_lotus_blob_not_tiles_or_special_clears():
    r = result()
    blob = replace(r.matches[0], cells=frozenset((i, j) for i in range(4) for j in range(4)))
    r.cascade_matches = [[blob], [r.matches[0]]]
    r.cleared_color_counts = {ms.PURPLE: 30}
    assert evaluate(r).multiplier_madness_points == 2
    r.cascade_matches, r.matches = [], []
    assert evaluate(r).multiplier_madness_points == 0


@pytest.mark.parametrize('source', ['jelly', 'mixy', 'sweep'])
def test_purple_setup_reaches_live_point_race_ranking(source):
    r = result(ms.YELLOW)
    if source == 'jelly':
        r.jelly_converted_color, r.jelly_converted_tiles = ms.PURPLE, 6
    elif source == 'mixy':
        r.board[2] = [ms.PURPLE] * 4
        r.intent_events = [{'type': 'mixy_conversion', 'selected_color': ms.PURPLE,
                            'converted_tiles': 6}]
    else:
        r.board[2] = [ms.PURPLE] * 4
        r.sweep_setup_pairs = 4
        r.intent_events = [{'type': 'sweep_se_activation', 'color': ms.PURPLE,
                            'setup_recolour_tiles': 0}]
    with ms.score_multiplier_state(20, 3):
        e = evaluate(r)
        assert e.multiplier_madness_points == 0
        assert 0 < e.multiplier_madness_setup_bonus <= 12.6 + 1e-8
        without = replace(e, score=e.score-e.multiplier_madness_setup_bonus,
                          mode_bonus=e.mode_bonus-e.multiplier_madness_setup_bonus,
                          multiplier_madness_setup_bonus=0)
        ctx = ms.StrategyContext(mode='solo_6')
        assert ms._weighted_priority(e, ms.GameMode.MULTIPLIER_MADNESS, strategy_context=ctx) > (
            ms._weighted_priority(without, ms.GameMode.MULTIPLIER_MADNESS, strategy_context=ctx))
        assert evaluate(r, ms.GameMode.NONE).multiplier_madness_setup_bonus == 0


def test_consumed_mixy_conversion_is_not_future_multiplier():
    r = result(ms.YELLOW)
    r.intent_events = [{'type': 'mixy_conversion', 'selected_color': ms.PURPLE, 'converted_tiles': 9}]
    assert evaluate(r).multiplier_madness_setup_bonus == 0


def test_no_growth_value_without_remaining_moves_and_other_modes_unchanged():
    with ms.score_multiplier_state(20, 0):
        assert evaluate(result()).mode_bonus == 0
    with ms.score_multiplier_state(20, 3):
        assert ms._score_multiplier_point_value(ms.MODE_WEIGHTS[ms.GameMode.MOVES_MULTIPLIER]) == .9
        assert evaluate(result(), ms.GameMode.NONE).mode_bonus == 0


def test_lotus_trigger_prefers_purple_for_multiplier_only_in_madness():
    r = result()
    yellow = ms.MatchGroup(frozenset({(2, 0), (2, 1), (2, 2)}), ms.YELLOW, 'three')
    r.cascade_matches[0].append(yellow)
    r.board[2][:3] = [ms.YELLOW] * 3
    e = evaluate(r)
    zone = frozenset((i, j) for i in range(4) for j in range(4))
    with ms.score_multiplier_state(30, 3):
        chosen = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1,
                                                ms.GameMode.MULTIPLIER_MADNESS)
        ordinary = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1,
                                                  ms.GameMode.NONE)
    assert chosen['color'] == ms.PURPLE
    assert ordinary['color'] == ms.YELLOW


def test_mixy_preserves_original_colors_for_swipe_direction():
    r = result()
    r.candidate.board[0][1] = ms.GREEN
    simulated, count = ms._simulate_mixy_conversion_candidate(
        r.candidate, (ms.GREEN, ms.PURPLE), ms.PURPLE,
        mode=ms.GameMode.MULTIPLIER_MADNESS, allow_square_matches=False,
        explode_created_specials_immediately=False, match_scan_cache={})
    assert count > 0
    assert simulated.candidate is r.candidate


def test_mixy_double_match_selects_purple_and_drags_it_toward_match(monkeypatch):
    board = [[(row * 2 + col) % 5 + 1 for col in range(5)] for row in range(5)]
    specials = [[0] * 5 for _ in range(5)]
    for row in (1, 3):
        board[row][1], board[row][2] = ms.PURPLE, ms.GREEN
    board[2][1], board[2][2] = ms.GREEN, ms.PURPLE
    after, after_special = ms.swap_cells(board, specials, (2, 1), (2, 2))
    candidate = ms.MoveCandidate((2, 1), (2, 2), ms.Direction.RIGHT, after, after_special)
    base = evaluate(ms.simulate_candidate(candidate))
    monkeypatch.setattr(ms, 'rank_moves', lambda *args, **kwargs: [base])
    state = ms.MixyMeowState(active=True, code_colors=(ms.GREEN, ms.PURPLE), source='manual')
    with ms.score_multiplier_state(30, 3):
        ranked = ms.rank_mixy_code_moves(board, specials, state, mode='Multiplier Madness',
                                         include_future_value=False, lookahead_candidates=0)
    assert ranked[0].mixy_code_color == ms.PURPLE
    assert ranked[0].multiplier_madness_points > 0
    assert ms.oriented_swipe(ranked[0]) == ((2, 2), 'left')


# --- 2026-09-19: a multiplier point priced on the match clock -----------------


def test_point_value_follows_the_match_clock_and_the_standing_multiplier():
    value = ms._multiplier_madness_point_value
    # Opening: capped, far above the flat 18.
    with ms.score_multiplier_state(1, 6, 100.0):
        assert value() == ms.MULTIPLIER_POINT_VALUE_CAP
    # ~30 s in at x13: about the old flat price (3.7 * 75 / 13).
    with ms.score_multiplier_state(13, 6, 75.0):
        assert value() == pytest.approx(21.35, abs=0.01)
    # Second half: the curve is under the floor, the floor holds the near-ties.
    with ms.score_multiplier_state(30, 6, 30.0):
        assert value() == ms.MULTIPLIER_POINT_VALUE_FLOOR
    # Last seconds: nothing left to multiply, points decide.
    with ms.score_multiplier_state(36, 2, 8.0):
        assert value() == pytest.approx(3.7 * 8 / 36)
    # No match clock (versus, Solo Challenge, screen path): the flat price stays.
    with ms.score_multiplier_state(36, 2):
        assert value() == 18
    assert ms._SCORE_MULTIPLIER_SECONDS_LEFT is None


def test_purple_beats_a_slightly_bigger_move_mid_match_but_not_a_much_bigger_one():
    def clears(color, cells):
        r = result(color)
        r.cleared_cells = cells
        return r

    with ms.score_multiplier_state(25, 6, 50.0):
        purple = evaluate(clears(ms.PURPLE, 3))
        a_bit_more = evaluate(clears(ms.YELLOW, 6))
        much_more = evaluate(clears(ms.YELLOW, 20))
    assert purple.score > a_bit_more.score
    assert much_more.score > purple.score


def test_ready_multiplier_matches_counts_one_swap_away():
    P, G, Y = ms.PURPLE, ms.GREEN, ms.YELLOW
    board = [
        [P, P, G, P],   # (0,3) -> (0,2) completes the row
        [G, Y, G, Y],
        [Y, G, Y, G],
        [G, Y, G, Y],
    ]
    assert ms._ready_multiplier_matches(board, frozenset({P})) == 1
    # The tile that moves cannot also be part of the line it leaves behind.
    board[0] = [P, P, G, Y]
    assert ms._ready_multiplier_matches(board, frozenset({P})) == 0
    # An unknown refill cell is not a piece: nothing can be swapped into it.
    board[0] = [P, P, ms.EMPTY, P]
    assert ms._ready_multiplier_matches(board, frozenset({P})) == 0


def test_ready_purple_setup_is_paid_only_on_the_clock_while_a_point_is_worth_it():
    r = result(ms.RED)
    r.board = [
        [ms.PURPLE, ms.PURPLE, ms.GREEN, ms.PURPLE],
        [ms.GREEN, ms.YELLOW, ms.GREEN, ms.YELLOW],
        [ms.YELLOW, ms.GREEN, ms.YELLOW, ms.GREEN],
        [ms.GREEN, ms.YELLOW, ms.GREEN, ms.YELLOW],
    ]
    with ms.score_multiplier_state(5, 6, 80.0):
        early = evaluate(r)
        assert early.multiplier_madness_setup_bonus == pytest.approx(
            0.35 * ms._multiplier_madness_point_value())
    with ms.score_multiplier_state(30, 6, 30.0):
        assert evaluate(r).multiplier_madness_setup_bonus == 0
    with ms.score_multiplier_state(5, 6):
        assert evaluate(r).multiplier_madness_setup_bonus == 0


# --- 2026-09-19: a multiplier extra goes before every other extra -------------
# 02:43:25, Multiplier Madness, 84 s left: a two-extra orange move was played
# ahead of a purple four; its cascade destroyed the purple match and the +1 was
# lost. The player's rule: a purple extra ALWAYS has priority.

def _extra(color, extra_moves, score, cells):
    board = [[ms.GREEN, ms.RED] * 3 for _ in range(6)]
    specials = [[ms.EMPTY] * 6 for _ in range(6)]
    candidate = ms.MoveCandidate((0, 0), (0, 1), ms.Direction.RIGHT, board, specials)
    match = ms.MatchGroup(frozenset(cells), color, 'four')
    return ms.MoveEvaluation(
        candidate, score=score, instant_score=len(cells), special_bonus=0, blue_bonus=0,
        mode_bonus=0, extra_move_bonus=18, disco_move_bonus=0, extra_moves=extra_moves,
        disco_moves=0, cascade_count=1, board_potential=0, lookahead_bonus=0,
        explanation='', cascade_matches=[[match]], direct_extra_moves=1,
        multiplier_madness_points=1.0 if color == ms.PURPLE else 0.0,
    )


def test_purple_extra_leads_the_extra_tier_only_in_multiplier_modes(monkeypatch):
    monkeypatch.setattr(ms, '_with_extra_move_chain_bonus', lambda e, *a, **k: e)
    monkeypatch.setattr(ms, '_with_extra_preservation_metadata', lambda e, *a, **k: e)
    purple = _extra(ms.PURPLE, 1, 105.7, [(0, c) for c in range(4)])
    orange = _extra(ms.ORANGE, 2, 179.8, [(3, c) for c in range(4)])

    def first(mode):
        ranked = ms._rank_extra_priority_moves(
            [orange, purple], mode, False, None, False)
        return ranked[0].multiplier_madness_points

    with ms.score_multiplier_state(3, 6, 84.0):
        assert first('Multiplier Madness') == 1.0
    # Anywhere else purple is just a colour and two extras beat one.
    assert first('None') == 0.0
