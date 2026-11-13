import move_strategy as ms


# Debug/runs/2026-09-26_20-21-35_594 (Purple Gem Mode, Monkey Joo Joo skulls):
# dragging the yellow skull (3,4) onto the red skull (3,3) lines up four yellow
# skulls in column 3 -- a direct extra on top of the skull combo.
BOARD = [
    [5, 2, 1, 4, 1, 4, 1],
    [4, 6, 5, 1, 3, 3, 6],
    [1, 2, 6, 3, 6, 5, 2],
    [1, 4, 4, 2, 3, 5, 1],
    [3, 2, 4, 3, 4, 2, 6],
    [2, 1, 6, 3, 4, 3, 4],
    [6, 1, 5, 2, 6, 3, 4],
]
SPECIALS = [
    [0, 0, 0, 122, 0, 0, 0],
    [19, 0, 0, 0, 0, 0, 19],
    [0, 0, 0, 19, 19, 0, 19],
    [0, 19, 0, 19, 19, 2, 0],
    [0, 0, 19, 19, 0, 0, 0],
    [0, 0, 0, 19, 121, 0, 0],
    [19, 0, 0, 0, 0, 0, 46],
]


def _ranked():
    return ms.rank_moves(
        BOARD,
        SPECIALS,
        mode="Purple Gem Mode",
        allow_square_matches=True,
        include_future_value=True,
        strategy_context="solo_6",
    )


def test_skull_dragged_into_a_four_is_a_direct_extra():
    ranked = _ranked()
    move = next(
        item for item in ranked
        if tuple(item.candidate.start) == (3, 4) and tuple(item.candidate.target) == (3, 3)
    )
    assert move.direct_extra_moves == 1.0
    assert ms.has_guaranteed_true_extra(move)
    assert ranked[0] is move


def test_skull_pair_the_other_way_makes_no_four():
    move = next(
        item for item in _ranked()
        if tuple(item.candidate.start) == (3, 3) and tuple(item.candidate.target) == (3, 4)
    )
    assert move.direct_extra_moves == 0.0


def test_skull_pair_plan_text_counts_blue_cells():
    # Debug/runs 2026-11-13 19:5x: the plan read "including None blue cells"
    # for every skull and Disco Ball explosion.
    import runtime

    move = next(
        item for item in _ranked()
        if tuple(item.candidate.start) == (3, 4) and tuple(item.candidate.target) == (3, 3)
    )
    skull = next(e for e in move.intent_events
                 if e.get("type") == "special_effect" and e.get("special") == "joojoo_skull")
    assert isinstance(skull["blue_cells"], int)
    text = runtime.render_move_intent_text(
        {"selected_action": "move",
         "best_move": {"start": [3, 4], "target": [3, 3], "direction": "left",
                       "intent_events": move.intent_events}})
    assert "None blue" not in text
    assert f"including {skull['blue_cells']} blue cells" in text


def test_plan_text_without_blue_count_drops_the_clause():
    import runtime

    text = runtime.render_move_intent_text(
        {"selected_action": "move",
         "best_move": {"start": [0, 0], "target": [0, 1], "direction": "right",
                       "intent_events": [{"type": "special_effect", "special": "cleo_bug",
                                          "cell": [0, 1], "cleared_cells": 3}]}})
    assert "None" not in text and "clears 3 cells from (0,1)." in text
