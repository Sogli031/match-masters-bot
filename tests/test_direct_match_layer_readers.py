"""Every "combos of the performed swap" rule ignores a swap that matched nothing.

`cascade_matches[0]` is the swap's own layer only when the swap made a match. A
special+special combo, a disco or skull swap and a booster/perk effect start the
list with the first DROP cascade (`has_direct_match_layer` False). Found on the
Froggy lotus 2026-09-20 19:23:00 (tests/test_froggy_lotus_direct_only.py); the
same read sat in Floor Is Lava, Vertical Rush, Lights Up, Column Mania, the
direct-extra colours, the square check, the Mixy code and the cascade numbers of
`_same_move_extra_cascades`.
"""
from types import SimpleNamespace

import move_strategy as ms

# A horizontal three in columns 1-3 that only FELL IN after the swap's effect.
DROP_THREE = ms.MatchGroup(
    cells=frozenset({(4, 1), (4, 2), (4, 3)}), color=ms.BLUE, kind="three"
)
DROP_FOUR = ms.MatchGroup(
    cells=frozenset({(5, 0), (5, 1), (5, 2), (5, 3)}), color=ms.YELLOW, kind="four"
)
DROP_SQUARE = ms.MatchGroup(
    cells=frozenset({(5, 0), (5, 1), (6, 0), (6, 1)}), color=ms.YELLOW, kind="square"
)


def _stub(cascade_matches, has_direct_match_layer, **extra):
    return SimpleNamespace(
        cascade_matches=cascade_matches,
        matches=[match for cascade in cascade_matches for match in cascade],
        has_direct_match_layer=has_direct_match_layer,
        **extra,
    )


def test_direct_swap_layer_helper():
    cascades = [[DROP_THREE], [DROP_FOUR]]
    assert ms._direct_swap_layer(cascades) == [DROP_THREE]
    assert ms._direct_swap_layer(cascades, False) == []
    # The `matches` fallback is for synthetic results without a cascade list,
    # never for a move known to have no direct layer.
    assert ms._direct_swap_layer([], True, [DROP_FOUR]) == [DROP_FOUR]
    assert ms._direct_swap_layer([], False, [DROP_FOUR]) == []
    assert ms._performed_swap_matches(_stub(cascades, True)) == [DROP_THREE]
    assert ms._performed_swap_matches(_stub(cascades, False)) == []


def test_floor_lava_marks_nothing_without_a_direct_match():
    cascades = [[DROP_THREE]]
    assert ms.floor_lava_transition(cascades, (2, 7)) == ((2,), (1, 3, 7))
    assert ms.floor_lava_transition(
        cascades, (2, 7), has_direct_match_layer=False
    ) == ((), (2, 7))


def test_vertical_rush_ignores_a_drop_cascade():
    weights = ms.MODE_WEIGHTS[ms.GameMode.VERTICAL_RUSH]
    matched = _stub([[DROP_THREE]], True)
    matchless = _stub([[DROP_THREE]], False)
    assert ms._mode_match_bonus(matched, weights) == weights["horizontal_match"]
    assert ms._mode_match_bonus(matchless, weights) == 0.0
    # The gate forgives only a penalty the move really pays.
    matched.score = matchless.score = -1.0
    assert ms._survives_evaluation_score_gate(matched, ms.GameMode.VERTICAL_RUSH)
    assert not ms._survives_evaluation_score_gate(matchless, ms.GameMode.VERTICAL_RUSH)


def test_lights_up_pays_nothing_for_a_drop_cascade(monkeypatch):
    monkeypatch.setattr(ms, "_LIGHTS_UP_COLUMN", 2)
    cascades = [[DROP_THREE]]
    assert ms._lights_up_multiplier_points(cascades, [DROP_THREE]) == 1.0
    assert (
        ms._lights_up_multiplier_points(
            cascades, [DROP_THREE], has_direct_match_layer=False
        )
        == 0.0
    )


def test_column_mania_raises_nothing_for_a_drop_cascade(monkeypatch):
    monkeypatch.setattr(ms, "_COLUMN_MANIA_MULTIPLIERS", (1,) * 7)
    cascades = [[DROP_THREE]]
    assert ms._column_mania_growth_columns(cascades, [DROP_THREE]) == (1, 2, 3)
    assert (
        ms._column_mania_growth_columns(
            cascades, [DROP_THREE], has_direct_match_layer=False
        )
        == ()
    )


def test_evaluation_readers_ignore_a_drop_cascade():
    matched = _stub([[DROP_FOUR, DROP_SQUARE]], True)
    matchless = _stub([[DROP_FOUR, DROP_SQUARE]], False)
    assert ms.direct_extra_match_colors(matched) == {ms.YELLOW}
    assert ms.direct_extra_match_colors(matchless) == frozenset()
    assert ms._has_direct_square_match(matched)
    assert not ms._has_direct_square_match(matchless)
    assert ms._mixy_code_colors_from_evaluation(matched) == {ms.YELLOW}
    assert ms._mixy_code_colors_from_evaluation(matchless) == set()
    assert ms.evaluation_matches_mixy_code(matched, (ms.YELLOW,))
    assert not ms.evaluation_matches_mixy_code(matchless, (ms.YELLOW,))


def test_same_move_extra_cascades_use_intent_event_numbers():
    # Matched swap: the list starts at cascade 1. Matchless: the effect is
    # cascade 1 and has no entry, so the first drop cascade is number 2.
    assert ms._same_move_extra_cascades(
        _stub([[DROP_THREE], [DROP_FOUR]], True, intent_events=[])
    ) == {2}
    assert ms._same_move_extra_cascades(
        _stub([[DROP_THREE], [DROP_FOUR]], False, intent_events=[])
    ) == {3}


def _skull_chain(first_special):
    """2026-09-19_01-57-40_588 rank 1: a special caught in the combo's own clear
    (cascade 1), then a four that falls in (cascade 2)."""
    return _stub(
        [[DROP_FOUR]],
        False,
        extra_moves=1.0,
        direct_extra_moves=0.0,
        cleo_scenario_count=0,
        intent_events=[
            {"type": "special_effect", "cascade": 1, "special": "joojoo_skull"},
            {"type": "special_activation", "cascade": 1, "special": first_special},
            {"type": "match", "cascade": 2, "kind": "four", "tile_count": 4},
        ],
    )


def test_random_special_inside_the_combo_voids_the_cascade_extra():
    assert not ms.has_reliable_same_move_extra(_skull_chain("joojoo_skull"))


def test_stable_special_inside_the_combo_keeps_the_cascade_extra():
    # 2026-09-19 22:38:02: Bomb+Bomb with a horizontal chained in, a four in
    # cascade 2 -- the turn was kept.
    assert ms.has_reliable_same_move_extra(_skull_chain("horizontal"))


# The 2026-09-20 19:23:00 board of tests/test_froggy_lotus_direct_only.py: the
# Bomb+Bomb at (2,6)/(3,6) matches nothing and drops a blue three in.
BOARD = [
    [2, 1, 6, 3, 4, 5, 6],
    [1, 4, 1, 6, 3, 2, 1],
    [1, -1, 5, 4, 3, 3, 4],
    [5, 3, 1, 5, 4, 1, 2],
    [1, 3, 1, 4, 3, 2, 5],
    [5, 4, 2, 4, 5, 6, 5],
    [3, 3, 5, 5, 6, 4, 6],
]
SPECIALS = [
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 20, 0, 0, 3, 0, 3],
    [0, 0, 0, 0, 0, 0, 3],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 46, 0],
    [0, 0, 0, 0, 0, 0, 0],
]
RALLY = {6: 3.0, 4: 4.0, 3: 5.0, 2: 2.0}
BOMB_PAIR = {(2, 6), (3, 6)}


def test_real_bomb_combo_marks_no_lava_column():
    ranked = ms.rank_moves(
        BOARD,
        SPECIALS,
        mode=ms.GameMode.FLOOR_IS_LAVA,
        allow_square_matches=True,
        score_rally_values=RALLY,
    )
    combos = [e for e in ranked if {e.candidate.start, e.candidate.target} == BOMB_PAIR]
    assert combos
    # Swiped up, the blast drops a blue three into column 2 -- which used to be
    # "marked" as if the swipe had matched there.
    assert any(evaluation.cascade_matches for evaluation in combos)
    for evaluation in combos:
        assert not evaluation.has_direct_match_layer
        assert evaluation.floor_lava_checked_columns_after == ()
        assert evaluation.floor_lava_destroyed_columns == ()
