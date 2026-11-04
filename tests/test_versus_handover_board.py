import move_strategy as ms


def _board():
    # Debug/runs 2026-09-19_03-08-20_779: one blue pickup at (4,6)->(5,6), which
    # the blue tier played as its only candidate without pricing the handover.
    return [
        [2, 4, 4, 2, 3, 6, 2],
        [5, 2, 4, 3, 6, 6, 5],
        [2, 6, 3, 5, 4, 3, 1],
        [1, 5, 6, 1, 2, 5, 5],
        [1, 4, 1, 5, 4, 4, 1],
        [4, 4, 2, 6, 1, 1, 3],
        [2, 1, 5, 3, 6, 6, 5],
    ]


def _empty_specials():
    return [[0] * 7 for _ in range(7)]


def _evaluations():
    ranked = ms.rank_moves(_board(), _empty_specials(), lookahead_depth=1)
    blue = [item for item in ranked if item.blue_cells > 0]
    plain = [item for item in ranked if item.blue_cells == 0]
    assert blue and len(plain) >= 2
    return blue[0], plain[0], plain[1]


def _handover():
    turn = ms.TurnState(remaining_moves=1, source="memory", moves_left_in_match=3)
    return turn, ms.StrategyContext(mode=ms.STRATEGY_VERSUS_2)


def _key(evaluation):
    return (evaluation.candidate.start, evaluation.candidate.target)


def _order(monkeypatch, decorated, head_size, replies):
    monkeypatch.setattr(
        ms,
        "_versus_handover_opponent_reply_value",
        lambda evaluation, *args: replies[_key(evaluation)],
    )
    turn, context = _handover()
    return ms._versus_handover_threat_order(
        decorated, "None", False, None, False, turn, context, head_size=head_size
    )


def test_challenger_priority_is_capped_at_the_best_blue_move():
    blue, strong, weak = _evaluations()
    merged, head_size = ms._with_handover_blue_challengers(
        [(10.0, blue)], [(2.0, weak), (60.0, strong)]
    )
    assert head_size == 3
    assert [priority for priority, _evaluation in merged] == [10.0, 10.0, 2.0]
    assert [_key(item) for _priority, item in merged] == [_key(blue), _key(strong), _key(weak)]


def test_challenger_wins_only_by_the_board_it_leaves(monkeypatch):
    blue, strong, weak = _evaluations()
    merged, head_size = ms._with_handover_blue_challengers(
        [(10.0, blue)], [(60.0, strong), (2.0, weak)]
    )
    # Equal boards left behind: blue first, however many points the challenger has.
    same = {_key(blue): 20.0, _key(strong): 20.0, _key(weak): 20.0}
    assert _key(_order(monkeypatch, merged, head_size, same)[0][1]) == _key(blue)
    # The blue pickup hands over a fat reply, the challenger a dead board.
    denied = {_key(blue): 90.0, _key(strong): 3.0, _key(weak): 90.0}
    ordered = _order(monkeypatch, merged, head_size, denied)
    assert _key(ordered[0][1]) == _key(strong)
    assert "handover_vs_blue" in ordered[0][1].explanation


def test_single_blue_pickup_is_priced_on_the_handover_move():
    ranked = ms.rank_moves(_board(), _empty_specials(), lookahead_depth=1)
    turn, context = _handover()
    booster = ms.BoosterState(current=0, maximum=7, source="memory")
    handover = ms._rank_blue_priority_moves(
        ranked, "None", False, None, False, booster, turn, context
    )
    assert any("opp_reply=" in item.explanation for item in handover)
    # Earlier in the turn the next move is ours: blue tier only, nothing priced.
    early = ms.TurnState(remaining_moves=3, source="memory", moves_left_in_match=5)
    blue_only = ms._rank_blue_priority_moves(
        ranked, "None", False, None, False, booster, early, context
    )
    assert blue_only and all(item.blue_cells > 0 for item in blue_only)
    assert not any("opp_reply=" in item.explanation for item in blue_only)


def test_defensive_threat_uses_the_priced_reply_value(monkeypatch):
    blue, _strong, _weak = _evaluations()
    replies = ms._versus_handover_opponent_replies(blue, "None", False, None, False, {}, {}, {})
    reply_value = ms._best_opponent_reply_value(replies)
    extras = max(
        [max(result.extra_moves, result.direct_extra_moves) for _item, result in replies],
        default=0.0,
    )
    threat = ms._versus_handover_opponent_threat(blue, "None", False, None, False, {}, {}, {})
    assert threat == ms.VERSUS_DEFENSIVE_OPP_EXTRA_WEIGHT * extras + reply_value
