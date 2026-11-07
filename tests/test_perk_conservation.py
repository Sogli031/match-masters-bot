import move_strategy as ms
import runtime

# Player, 2026-10-08: perks went too early and were gone when the board had
# nothing. Energy Boost only when it fills the whole booster; Remove Cross only
# when there is nothing else (not next to disco balls, a good move or a perk
# worth firing).
MODE = "Multiplier Mushrooms Studio"


def _rank(board, specials, perks, current, rally, remaining_moves):
    kw = dict(mode=MODE, score_rally_values=rally)
    booster = ms.BoosterState(current=current, maximum=7, source="memory")
    turn = ms.TurnState(remaining_moves=remaining_moves, source="memory")
    ranked = ms.rank_moves(board, specials, include_future_value=True, strategy_context="solo_6", **kw)
    baseline = ms.prioritize_ranked_moves(
        ranked, booster_state=booster, turn_state=turn, strategy_context="solo_6", **kw
    )[0]
    blue_plan = ms.evaluate_blue_plan(board, specials, booster, **kw)
    context = ms.PerkDecisionContext(
        booster=booster, turn=turn, blue_plan=blue_plan, objective=ms.PerkObjective.MAX_BLUE
    )
    return runtime.rank_selected_perk_actions(
        board, specials, perks, normal_baseline=baseline, decision_context=context,
        booster_active=False, strategy_context="solo_6", include_future_value=True, **kw
    )


def test_energy_boost_charges_without_filling_on_a_board_without_blue():
    # Debug/runs/2026-10-08_12-02-56: Energy Boost for 5 charge of 7, fills=False.
    # Held back on 2026-10-08; since 2026-10-11 (player) a board with no blue
    # match spends it on the charge.
    board = [[4, 99, 5, 6, 99, 4, 6], [2, 6, 2, 2, 5, 5, 1], [5, 1, 6, 3, 4, 1, 6],
             [4, 5, 2, 4, 6, 6, 2], [5, 99, 4, 1, 6, 3, 5], [1, 5, 3, 1, 1, 4, 5],
             [5, 6, 3, 3, 4, 2, 3]]
    specials = [[0, 16, 0, 0, 16, 17, 0], [0] * 7, [0, 0, 17, 0, 0, 0, 0], [0] * 7,
                [0, 16, 0, 0, 0, 0, 0], [0] * 7, [0] * 7]
    actions = _rank(board, specials, ["energy_boost", "none"], 0, {4: 4.0, 6: 3.0, 2: 2.0, 3: 5.0}, 5)
    assert actions and actions[0].perk_key == ms.PERK_ENERGY_BOOST
    assert actions[0].net_gain > 0


def test_remove_cross_waits_next_to_disco_balls():
    # Debug/runs/2026-10-08_12-04-33: three disco balls, Remove Cross thrown.
    board = [[5, 5, 1, 6, 2, 2, 1], [99, 5, 1, 4, 2, 99, 6], [6, 2, 4, 6, 3, 3, 4],
             [3, 5, 5, 4, 6, 2, 99], [4, 1, 2, 3, 6, 5, 6], [1, 4, 4, 5, 1, 4, 5],
             [1, 2, 6, 5, 5, 6, 1]]
    specials = [[0] * 7, [16, 0, 0, 0, 0, 16, 0], [0] * 7, [0, 0, 0, 0, 0, 0, 16],
                [0, 0, 17, 17, 17, 0, 0], [0] * 7, [0] * 7]
    actions = _rank(board, specials, ["none", "remove_cross"], 0, {6: 3.0, 2: 2.0, 4: 4.0, 3: 5.0}, 6)
    assert not [a for a in actions if a.perk_key == ms.PERK_REMOVE_CROSS]


def _action(perk, net_gain):
    return ms.PerkAction(
        perk_key=perk, target=None, score=0.0, gross_score=0.0, threshold=0.0,
        baseline_score=0.0, net_gain=net_gain,
    )


def test_remove_cross_is_the_last_resort_among_perks():
    cross = _action(ms.PERK_REMOVE_CROSS, 20.0)
    hammer = _action(ms.PERK_HAMMER, 5.0)
    assert ms.remove_cross_last_resort([cross, hammer]) == [hammer]
    weak_hammer = _action(ms.PERK_HAMMER, -1.0)
    assert ms.remove_cross_last_resort([cross, weak_hammer]) == [cross, weak_hammer]


def test_energy_boost_fires_when_a_plain_match_fills_the_booster():
    # Debug/runs/2026-10-08_12-19-36: booster 6/7, a plain three with Energy
    # Boost fills it; EB was never used and the match ended at 6/7.
    board = [[4, 2, 2, 3, 6, 1, 1], [3, 5, 4, 5, 6, 5, 6], [5, 2, 1, 2, 4, 5, 1],
             [3, 4, 1, 2, 2, 1, 4], [6, 2, 3, 5, 6, 2, 3], [3, 6, 6, 4, 2, 1, 2],
             [4, 3, 3, 2, 5, 4, 5]]
    specials = [[0] * 7, [0] * 7, [0] * 7, [0, 0, 0, 17, 0, 0, 0], [0] * 7,
                [0, 17, 0, 1, 0, 0, 0], [0] * 7]
    actions = _rank(board, specials, ["energy_boost", "none"], 6, {4: 4.0, 2: 2.0, 3: 5.0, 6: 3.0}, 3)
    assert actions and actions[0].perk_key == ms.PERK_ENERGY_BOOST
    assert actions[0].net_gain > 0


def test_energy_boost_waits_when_a_blue_match_fills_on_its_own():
    # Debug/runs/2026-10-08_12-27-06: booster 4/7 and three blue to match; EB
    # was spent on a non-blue extra move instead.
    board = [[5, 1, 2, 6, 4, 6, 1], [3, 2, 5, 3, 4, 2, 1], [3, 5, 6, 2, 2, 1, 6],
             [1, 2, 4, 3, 5, 2, 4], [4, 3, 6, 5, 2, 6, 2], [1, 3, 6, 4, 5, 1, 1],
             [5, 4, 3, 6, 3, 3, 5]]
    specials = [[0] * 7 for _ in range(7)]
    specials[5][2] = 17
    actions = _rank(board, specials, ["energy_boost", "none"], 4, {2: 2.0, 6: 3.0, 4: 4.0, 3: 5.0}, 6)
    assert not [a for a in actions if a.perk_key == ms.PERK_ENERGY_BOOST]


# Player, 2026-10-11: perks fill the booster as early as possible; they wait
# only while a blue match fills the booster on its own.
def _rank_mode(board, specials, perks, current, maximum, mode, remaining_moves):
    kw = dict(mode=mode, score_rally_values={2: 1.0, 3: 1.0, 4: 1.0, 6: 1.0})
    booster = ms.BoosterState(current=current, maximum=maximum, source="memory")
    turn = ms.TurnState(remaining_moves=remaining_moves, source="memory")
    ranked = ms.rank_moves(board, specials, include_future_value=True, strategy_context="solo_6", **kw)
    baseline = ms.prioritize_ranked_moves(
        ranked, booster_state=booster, turn_state=turn, strategy_context="solo_6", **kw
    )[0]
    blue_plan = ms.evaluate_blue_plan(board, specials, booster, **kw)
    context = ms.PerkDecisionContext(
        booster=booster, turn=turn, blue_plan=blue_plan, objective=ms.PerkObjective.MAX_BLUE
    )
    actions = runtime.rank_selected_perk_actions(
        board, specials, perks, normal_baseline=baseline, decision_context=context,
        booster_active=False, strategy_context="solo_6", include_future_value=True, **kw
    )
    return actions, baseline, context


def test_energy_boost_fires_on_a_board_without_blue():
    # Debug/runs/2026-10-11_22-00-35: booster 0/7, no blue match anywhere; both
    # perks were held and a plain move was played.
    board = [[5, 3, 6, 1, 4, 6, 4], [6, 5, 4, 1, 5, 6, 4], [6, 6, 4, 6, 2, 3, 2],
             [1, 2, 3, 3, 2, 3, 2], [3, 4, 5, 3, 6, 5, 5], [3, 2, 4, 1, 2, 4, 2],
             [1, 3, 4, 1, 1, 5, 5]]
    specials = [[0] * 7 for _ in range(7)]
    specials[0][6] = 17
    specials[5][6] = 17
    actions, baseline, context = _rank_mode(
        board, specials, ["energy_boost", "remove_cross"], 0, 7, "Multiplier Madness", 6
    )
    assert not context.blue_plan.can_fill_now
    assert actions and actions[0].perk_key == ms.PERK_ENERGY_BOOST
    assert ms.perk_activation_decision(actions[0], baseline, context, "solo_6")[0]


def test_remove_cross_fires_next_to_a_good_move_without_blue():
    # Debug/runs/2026-10-11_20-49-21: booster 3/6, no blue match; Remove Cross
    # waited behind an ordinary "smart" move.
    board = [[6, 1, 6, 1, 4, 4, 5], [6, 5, 3, 2, 4, 2, 2], [3, 6, 6, 4, 5, 1, 2],
             [4, 6, 2, 1, 5, 3, 3], [5, 4, 1, 3, 4, 2, 4], [3, 1, 3, 2, 5, 1, 5],
             [6, 2, 5, 3, 2, 1, 1]]
    specials = [[0, 0, 0, 0, 17, 0, 0], [0] * 7, [0] * 7, [0, 17, 0, 0, 2, 0, 0],
                [0, 0, 0, 0, 17, 0, 0], [0, 0, 0, 3, 0, 0, 0], [3, 0, 0, 0, 0, 0, 0]]
    actions, baseline, context = _rank_mode(
        board, specials, ["none", "remove_cross"], 3, 6, "Multiplier Mushrooms Studio", 6
    )
    assert actions and actions[0].perk_key == ms.PERK_REMOVE_CROSS
    assert actions[0].booster_charge_cells > 0
    assert ms.perk_activation_decision(actions[0], baseline, context, "solo_6")[0]


def test_perk_fires_next_to_a_blue_three_that_cannot_fill_the_booster():
    # Debug/runs/2026-10-11_22-12-52: booster 0/6 with a blue three on the
    # board. Holding perks behind any blue three left them unused for whole
    # matches (2026-10-12 00:08-00:11), so a three that cannot fill waits.
    board = [[6, 6, 4, 3, 3, 2, 4], [3, 1, 6, 4, 1, 1, 5], [5, 4, 2, 5, 6, 6, 1],
             [2, 5, 4, 5, 5, 3, 1], [4, 2, 4, 6, 2, 3, 2], [4, 1, 2, 6, 2, 5, 3],
             [5, 6, 1, 1, 4, 5, 1]]
    specials = [[0] * 7 for _ in range(7)]
    specials[0][4] = 1
    specials[5][2] = 17
    actions, baseline, context = _rank_mode(
        board, specials, ["energy_boost", "remove_cross"], 0, 6, "Multiplier Mushrooms Studio", 6
    )
    assert context.blue_plan.best_now >= 3 and not context.blue_plan.can_fill_now
    assert actions and ms.perk_activation_decision(actions[0], baseline, context, "solo_6")[0]


def test_perks_wait_while_a_blue_match_fills_the_booster():
    # Same board at 4/6: the blue three fills the booster on its own.
    board = [[6, 6, 4, 3, 3, 2, 4], [3, 1, 6, 4, 1, 1, 5], [5, 4, 2, 5, 6, 6, 1],
             [2, 5, 4, 5, 5, 3, 1], [4, 2, 4, 6, 2, 3, 2], [4, 1, 2, 6, 2, 5, 3],
             [5, 6, 1, 1, 4, 5, 1]]
    specials = [[0] * 7 for _ in range(7)]
    specials[0][4] = 1
    specials[5][2] = 17
    actions, _baseline, context = _rank_mode(
        board, specials, ["energy_boost", "remove_cross"], 4, 6, "Multiplier Mushrooms Studio", 6
    )
    assert context.blue_plan.can_fill_now
    assert actions == []
