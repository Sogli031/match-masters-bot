"""Color Climb (RainbowMultiplierBoard, 35): the dealt pair drives the scoring.

Engine rule (libil2cpp.so, decoded 2026-09-13): ``onGameStart`` shuffles the
four non-charge colours into ``availableColors`` and gives player 0 the first
two and player 1 the last two; ``BeforeCombosDestroy`` raises the current
player's ScoreMultiplier by one per destroyed combo in either of those colours.
"""

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import board_source  # noqa: E402
import move_strategy as ms  # noqa: E402
import runtime  # noqa: E402

CLIMB = ms.GameMode.COLOR_CLIMB
# SlotColor codes: Green 3, Yellow 5, Orange 6, Purple 7 -- the four the board
# deals (recorded order of a live match: Y, P, O, G).
DEALT = [5, 7, 6, 3]


def snapshot(colors=DEALT, current=0, multipliers=(1, 1), local=0):
    players = [
        {
            "index": index,
            "score_multiplier": value,
            "is_my_turn": index == current,
            # PlayerClientControl.Type: 0 marks the local side.
            "player_type": 0 if index == local else 1,
        }
        for index, value in enumerate(multipliers)
    ]
    return {
        "columns": 7,
        "rows": 7,
        "board_fields": {"availableColors": list(colors)},
        "state": {
            "current_player_index": current,
            "players": players,
            "rules": {"id": "color-climb", "board_model_name": 35},
        },
    }


# ---------------------------------------------------------- board_source


def test_seat_zero_gets_the_first_two_colours():
    state = board_source.color_climb_state(snapshot())
    assert state["colors"] == (ms.YELLOW, ms.PURPLE)
    assert state["opponent_colors"] == (ms.ORANGE, ms.GREEN)
    assert state["seat"] == 0
    assert state["multiplier"] == 1


def test_seat_one_gets_the_last_two_colours():
    state = board_source.color_climb_state(snapshot(current=1, multipliers=(3, 5), local=1))
    assert state["colors"] == (ms.ORANGE, ms.GREEN)
    assert state["opponent_colors"] == (ms.YELLOW, ms.PURPLE)
    assert state["multiplier"] == 5
    assert state["opponent_multiplier"] == 3


def test_opponents_turn_keeps_our_pair():
    """The versus recording flips current_player_index every turn."""
    state = board_source.color_climb_state(snapshot(current=1, multipliers=(4, 2), local=0))
    assert state["seat"] == 0
    assert state["colors"] == (ms.YELLOW, ms.PURPLE)
    assert state["multiplier"] == 4
    assert state["opponent_multiplier"] == 2


def test_caller_supplied_seat_wins():
    state = board_source.color_climb_state(snapshot(local=0), seat=1)
    assert state["colors"] == (ms.ORANGE, ms.GREEN)


def test_without_player_type_the_player_on_turn_is_the_seat():
    snap = snapshot(current=1, multipliers=(1, 1))
    for player in snap["state"]["players"]:
        del player["player_type"]
    assert board_source.color_climb_state(snap)["seat"] == 1


def test_board_not_started_is_unknown():
    # Before onGameStart every multiplier is 0 and the list is unshuffled.
    assert board_source.color_climb_state(snapshot(multipliers=(0, 0))) is None


def test_missing_field_is_unknown():
    snap = snapshot()
    snap["board_fields"] = {}
    assert board_source.color_climb_state(snap) is None
    snap["board_fields"] = None
    assert board_source.color_climb_state(snap) is None


def test_score_multiplier_state_names_the_mode():
    assert board_source.score_multiplier_state(snapshot())["mode"] == "color-climb"


# ---------------------------------------------------------- move_strategy


def result(color):
    board = [[ms.RED] * 4 for _ in range(4)]
    board[1][:3] = [color] * 3
    specials = [[ms.EMPTY] * 4 for _ in range(4)]
    candidate = ms.MoveCandidate((0, 1), (1, 1), ms.Direction.DOWN, board, specials)
    match = ms.MatchGroup(frozenset((1, col) for col in range(3)), color, "three")
    return ms.SimulationResult(candidate, board, specials, matches=[match],
                               cascade_matches=[[match]], cascade_count=1,
                               cleared_cells=3, cleared_color_counts={color: 3})


def evaluate(r, mode=CLIMB):
    return ms.evaluate_simulation(r, mode, include_future_value=False)


def test_growth_colours_follow_the_dealt_pair():
    assert ms.multiplier_growth_colors(CLIMB) == frozenset()
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.multiplier_growth_colors(CLIMB) == {ms.YELLOW, ms.PURPLE}
        assert ms.multiplier_growth_colors(ms.GameMode.MULTIPLIER_MADNESS) == {ms.PURPLE}
        assert ms.multiplier_growth_colors(ms.GameMode.NONE) == frozenset()
    assert ms.multiplier_growth_colors(CLIMB) == frozenset()


def test_combo_in_either_dealt_colour_earns_a_point_and_outranks_others():
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(4, 3):
        yellow, purple, green = (evaluate(result(c)) for c in (ms.YELLOW, ms.PURPLE, ms.GREEN))
    assert yellow.multiplier_madness_points == 1
    assert purple.multiplier_madness_points == 1
    assert green.multiplier_madness_points == 0
    assert yellow.mode_bonus - green.mode_bonus == 18
    assert yellow.score > green.score and purple.score > green.score
    assert "color_climb=+1" in yellow.explanation


def test_no_pair_from_memory_pays_nothing():
    with ms.score_multiplier_state(4, 3):
        assert evaluate(result(ms.YELLOW)).multiplier_madness_points == 0
        assert evaluate(result(ms.YELLOW)).mode_bonus == 0


def test_purple_is_not_special_in_color_climb():
    with ms.multiplier_colors_active((ms.YELLOW, ms.GREEN)), ms.score_multiplier_state(2, 3):
        assert evaluate(result(ms.PURPLE)).multiplier_madness_points == 0
        assert evaluate(result(ms.GREEN)).multiplier_madness_points == 1


def test_points_count_every_cascade():
    r = result(ms.YELLOW)
    second = ms.MatchGroup(frozenset({(2, 0), (2, 1), (2, 2)}), ms.PURPLE, "three")
    r.cascade_matches = [[r.matches[0]], [second]]
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(2, 3):
        assert evaluate(r).multiplier_madness_points == 2


def test_setup_bonus_for_jelly_mixy_and_sweep_in_dealt_colours():
    for source in ("jelly", "mixy", "sweep"):
        r = result(ms.RED)
        if source == "jelly":
            r.jelly_converted_color, r.jelly_converted_tiles = ms.YELLOW, 6
        elif source == "mixy":
            r.board[2] = [ms.YELLOW] * 4
            r.intent_events = [{"type": "mixy_conversion", "selected_color": ms.YELLOW,
                                "converted_tiles": 6}]
        else:
            r.board[2] = [ms.YELLOW] * 4
            r.sweep_setup_pairs = 4
            r.intent_events = [{"type": "sweep_se_activation", "color": ms.YELLOW,
                                "setup_recolour_tiles": 0}]
        with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(5, 3):
            paid = evaluate(r)
        with ms.multiplier_colors_active((ms.GREEN, ms.ORANGE)), ms.score_multiplier_state(5, 3):
            unpaid = evaluate(r)
        assert 0 < paid.multiplier_madness_setup_bonus <= 12.6 + 1e-8, source
        assert unpaid.multiplier_madness_setup_bonus == 0, source


def test_lotus_trigger_prefers_a_dealt_colour():
    r = result(ms.YELLOW)
    green = ms.MatchGroup(frozenset({(2, 0), (2, 1), (2, 2)}), ms.GREEN, "three")
    r.cascade_matches[0].append(green)
    r.board[2][:3] = [ms.GREEN] * 3
    zone = frozenset((i, j) for i in range(4) for j in range(4))
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(3, 3):
        e = evaluate(r)
        chosen = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1, CLIMB)
        ordinary = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1, ms.GameMode.NONE)
    assert chosen["color"] == ms.YELLOW
    # Same points either way (both are ordinary colours), so without the
    # multiplier the tie-break order decides and it is not yellow-by-rule.
    assert ordinary["color"] in (ms.YELLOW, ms.GREEN)
    with ms.multiplier_colors_active((ms.GREEN, ms.ORANGE)), ms.score_multiplier_state(3, 3):
        chosen_green = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1, CLIMB)
    assert chosen_green["color"] == ms.GREEN


def test_lotus_trigger_in_dealt_colour_is_mandatory_over_a_bigger_collect():
    """The user's rule: a dealt-colour collect beats a larger one in any other."""
    r = result(ms.YELLOW)
    green = ms.MatchGroup(frozenset({(2, 0), (2, 1), (2, 2)}), ms.GREEN, "three")
    r.cascade_matches[0].append(green)
    # Green fills the rest of the zone so its collect is far larger.
    r.board = [[ms.GREEN] * 4 for _ in range(4)]
    r.board[1][:3] = [ms.YELLOW] * 3
    zone = frozenset((i, j) for i in range(4) for j in range(4))
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(3, 3):
        e = evaluate(r)
        chosen = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1, CLIMB)
        ordinary = ms._best_lotus_trigger_for_zone(e, r.board, (3, 3), zone, 1, ms.GameMode.NONE)
    assert chosen["color"] == ms.YELLOW
    assert ordinary["color"] == ms.GREEN
    assert ordinary["collected"] > chosen["collected"]


def test_lotus_move_tier_reads_the_collect_events():
    pair_move = SimpleNamespace(intent_events=[{"type": "froggy_lotus_collect", "color": ms.YELLOW}])
    other_move = SimpleNamespace(intent_events=[{"type": "froggy_lotus_collect", "color": ms.GREEN}])
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms._color_climb_lotus_tier(pair_move, CLIMB) == 0
        assert ms._color_climb_lotus_tier(other_move, CLIMB) == 1
        # Other modes: no tier at all.
        assert ms._color_climb_lotus_tier(other_move, ms.GameMode.MULTIPLIER_MADNESS) == 0
    # Without a memory reading nothing is tiered.
    assert ms._color_climb_lotus_tier(other_move, CLIMB) == 0


def _lotus_board():
    """A 7x7 board with a lotus at (3, 3), lots of green and three yellow.

    Both triggers touch the lotus zone (the plus around it): green through
    (2, 3), yellow through (4, 3). Green would collect far more tiles.
    """
    size = 7
    board = [[ms.RED if (r + c) % 2 else ms.BLUE for c in range(size)] for r in range(size)]
    specials = [[ms.EMPTY] * size for _ in range(size)]
    specials[3][3] = ms.SPECIAL_FROGGY_LOTUS
    for r in range(0, 3):
        for c in range(size):
            board[r][c] = ms.GREEN
    board[4][2] = board[4][3] = board[4][4] = ms.YELLOW
    green = ms.MatchGroup(frozenset({(2, 2), (2, 3), (2, 4)}), ms.GREEN, "three")
    yellow = ms.MatchGroup(frozenset({(4, 2), (4, 3), (4, 4)}), ms.YELLOW, "three")
    return board, specials, green, yellow


def _lotus_move(board, specials, match, mode):
    start = min(match.cells)
    candidate = ms.MoveCandidate(start, start, ms.Direction.DOWN, board, specials)
    r = ms.SimulationResult(candidate, board, specials, matches=[match],
                            cascade_matches=[[match]], cascade_count=1,
                            cleared_cells=3, cleared_color_counts={match.color: 3})
    return evaluate(r, mode)


def test_lotus_ranking_puts_dealt_colour_collect_first():
    """rank_froggy_lotus_moves: a smaller dealt-colour collect outranks a bigger green one."""
    board, specials, green, yellow = _lotus_board()
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(3, 3):
        moves = [_lotus_move(board, specials, green, CLIMB), _lotus_move(board, specials, yellow, CLIMB)]
        ranked = ms.rank_froggy_lotus_moves(moves, board, specials, mode=CLIMB)
    assert [e.froggy_lotus_color for e in ranked] == [ms.YELLOW, ms.GREEN]
    assert ranked[0].froggy_lotus_collected < ranked[1].froggy_lotus_collected
    # Plain mode: the bigger collect wins, as before.
    plain = [_lotus_move(board, specials, green, ms.GameMode.NONE),
             _lotus_move(board, specials, yellow, ms.GameMode.NONE)]
    ranked_plain = ms.rank_froggy_lotus_moves(plain, board, specials, mode=ms.GameMode.NONE)
    assert ranked_plain[0].froggy_lotus_color == ms.GREEN
    # Color Climb with the pair being green/orange: green leads.
    with ms.multiplier_colors_active((ms.GREEN, ms.ORANGE)), ms.score_multiplier_state(3, 3):
        moves = [_lotus_move(board, specials, yellow, CLIMB), _lotus_move(board, specials, green, CLIMB)]
        ranked = ms.rank_froggy_lotus_moves(moves, board, specials, mode=CLIMB)
    assert ranked[0].froggy_lotus_color == ms.GREEN


def test_mixy_code_moves_in_dealt_colour_are_the_only_offer():
    yellow_move = SimpleNamespace(mixy_code_color=ms.YELLOW, score=10.0)
    green_move = SimpleNamespace(mixy_code_color=ms.GREEN, score=50.0)
    orange_move = SimpleNamespace(mixy_code_color=ms.ORANGE, score=20.0)
    ranked = [green_move, orange_move, yellow_move]
    with ms.multiplier_colors_active((ms.YELLOW, ms.ORANGE)):
        assert ms.color_climb_mixy_code_moves(ranked, CLIMB) == [orange_move, yellow_move]
        assert ms.color_climb_mixy_code_moves(ranked, ms.GameMode.MULTIPLIER_MADNESS) == []
    assert ms.color_climb_mixy_code_moves(ranked, CLIMB) == []


def test_mixy_double_match_picks_the_dealt_colour(monkeypatch=None):
    board = [[(row * 2 + col) % 5 + 1 for col in range(5)] for row in range(5)]
    specials = [[0] * 5 for _ in range(5)]
    for row in (1, 3):
        board[row][1], board[row][2] = ms.YELLOW, ms.GREEN
    board[2][1], board[2][2] = ms.GREEN, ms.YELLOW
    after, after_special = ms.swap_cells(board, specials, (2, 1), (2, 2))
    candidate = ms.MoveCandidate((2, 1), (2, 2), ms.Direction.RIGHT, after, after_special)
    base = evaluate(ms.simulate_candidate(candidate))
    original = ms.rank_moves
    ms.rank_moves = lambda *args, **kwargs: [base]
    try:
        state = ms.MixyMeowState(active=True, code_colors=(ms.GREEN, ms.YELLOW), source="manual")
        with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)), ms.score_multiplier_state(3, 3):
            ranked = ms.rank_mixy_code_moves(board, specials, state, mode=CLIMB,
                                             include_future_value=False, lookahead_candidates=0)
    finally:
        ms.rank_moves = original
    assert ranked[0].mixy_code_color == ms.YELLOW
    assert ranked[0].multiplier_madness_points > 0


# ---------------------------------------------------------- runtime gate


def _extra_evaluation(color, direct=1.0):
    match = ms.MatchGroup(frozenset((1, col) for col in range(4)), color, "four")
    return SimpleNamespace(
        direct_extra_moves=direct, extra_moves=direct, disco_moves=0,
        cascade_matches=[[match]], decision_gate="score_gate",
    )


def test_direct_extra_match_colors_reads_the_swap_row_only():
    e = _extra_evaluation(ms.YELLOW)
    assert ms.direct_extra_match_colors(e) == {ms.YELLOW}
    three = ms.MatchGroup(frozenset((1, col) for col in range(3)), ms.YELLOW, "three")
    e.cascade_matches = [[three], [ms.MatchGroup(frozenset((2, c) for c in range(4)), ms.PURPLE, "four")]]
    assert ms.direct_extra_match_colors(e) == frozenset()


def test_booster_immediate_plays_dealt_colour_extra_first():
    green_extra = _extra_evaluation(ms.GREEN)
    yellow_extra = _extra_evaluation(ms.YELLOW)
    ranked = [green_extra, yellow_extra]
    action, chosen, gate = runtime.select_booster_action_with_gate(
        ranked, True, True, multiplier_extra_colors=(ms.YELLOW, ms.PURPLE)
    )
    assert (action, chosen, gate) == ("move", yellow_extra, "multiplier_color_extra_before_booster_gate")
    # Without a dealt-colour extra the immediate toggle fires as before.
    action, chosen, gate = runtime.select_booster_action_with_gate(
        [green_extra], True, True, multiplier_extra_colors=(ms.YELLOW, ms.PURPLE)
    )
    assert (action, gate) == ("activate_booster", "booster_immediate_toggle_gate")
    # And with no colours (other modes, or no memory reading) nothing changes.
    action, chosen, gate = runtime.select_booster_action_with_gate(
        ranked, True, True, multiplier_extra_colors=()
    )
    assert (action, gate) == ("activate_booster", "booster_immediate_toggle_gate")


def test_color_climb_extra_colors_only_in_the_mode():
    previous = runtime.recognition.curr_mode
    try:
        runtime.recognition.curr_mode = ms.GameMode.MULTIPLIER_MADNESS
        with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
            assert runtime._color_climb_extra_colors() == frozenset()
        runtime.recognition.curr_mode = CLIMB
        with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
            assert runtime._color_climb_extra_colors() == {ms.YELLOW, ms.PURPLE}
        assert runtime._color_climb_extra_colors() == frozenset()
    finally:
        runtime.recognition.curr_mode = previous


# ------------------------------------------- dealt colours before any booster


def _three(color, row=2):
    return ms.MatchGroup(frozenset((row, col) for col in range(3)), color, "three")


def test_cascade_dealt_combo_counts_for_an_extra_in_another_colour():
    """A green four whose sure cascade lands a yellow three goes before the booster."""
    green_extra = _extra_evaluation(ms.GREEN)
    green_extra.cascade_matches.append([_three(ms.YELLOW)])
    plain_green = _extra_evaluation(ms.GREEN)
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.color_climb_dealt_combos(green_extra, CLIMB) == 1
        assert ms.color_climb_dealt_combos(plain_green, CLIMB) == 0
    action, chosen, gate = runtime.select_booster_action_with_gate(
        [plain_green, green_extra], True, True, multiplier_extra_colors=(ms.YELLOW, ms.PURPLE)
    )
    assert (action, chosen, gate) == ("move", green_extra, "multiplier_color_extra_before_booster_gate")


def test_dealt_combo_behind_a_random_refill_is_not_sure():
    e = _extra_evaluation(ms.GREEN)
    e.cascade_matches.append([_three(ms.YELLOW)])
    e.intent_events = [{"type": "uncertain_refill_boundary", "after_cascade": 1, "reason": "lightning"}]
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.color_climb_dealt_combos(e, CLIMB) == 0
        assert ms.color_climb_extra_before_booster([e], CLIMB) is None


def test_extra_before_booster_only_in_color_climb():
    e = _extra_evaluation(ms.YELLOW)
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.color_climb_extra_before_booster([e], CLIMB) is e
        assert ms.color_climb_extra_before_booster([e], ms.GameMode.MULTIPLIER_MADNESS) is None
    assert ms.color_climb_extra_before_booster([e], CLIMB) is None


def _bomb_swap(color, score):
    cell = (5, 5)
    return SimpleNamespace(
        candidate=SimpleNamespace(start=cell, target=(5, 6)),
        direct_extra_moves=0.0, extra_moves=0.0, disco_moves=0, score=score,
        cascade_matches=[[_three(color, row=5)]],
        intent_events=[{"type": "special_activation", "cascade": 1,
                        "special": "bomb", "cell": list(cell)}],
    )


def test_bomb_swaps_pick_the_dealt_colour_among_themselves():
    """Billie Boom: several bomb swaps -- the one matching a dealt colour goes first."""
    green_bomb = _bomb_swap(ms.GREEN, 90.0)
    plain = SimpleNamespace(candidate=SimpleNamespace(start=(0, 0), target=(0, 1)),
                            direct_extra_moves=0.0, extra_moves=0.0, disco_moves=0,
                            score=80.0, cascade_matches=[[_three(ms.RED, row=0)]],
                            intent_events=[])
    yellow_bomb = _bomb_swap(ms.YELLOW, 60.0)
    ordered = [green_bomb, plain, yellow_bomb]
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.color_climb_dealt_first_order(ordered, CLIMB) == [yellow_bomb, plain, green_bomb]
        # Other modes keep the ranking's order.
        assert ms.color_climb_dealt_first_order(ordered, ms.GameMode.NONE) == ordered
    assert ms.color_climb_dealt_first_order(ordered, CLIMB) == ordered


def test_extras_reorder_among_extras_only():
    plain = SimpleNamespace(candidate=SimpleNamespace(start=(0, 0), target=(0, 1)),
                            direct_extra_moves=0.0, extra_moves=0.0, disco_moves=0,
                            cascade_matches=[[_three(ms.YELLOW, row=0)]], intent_events=[])
    green_extra = _extra_evaluation(ms.GREEN)
    yellow_extra = _extra_evaluation(ms.YELLOW)
    with ms.multiplier_colors_active((ms.YELLOW, ms.PURPLE)):
        assert ms.color_climb_dealt_first_order(
            [green_extra, plain, yellow_extra], CLIMB
        ) == [yellow_extra, plain, green_extra]
