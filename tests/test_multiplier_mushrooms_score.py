"""Multiplier Mushrooms (board 29): exact-plan score through scoreMultiplier."""
from types import SimpleNamespace

import move_strategy as ms
from strategy_lab import simulation


def _result(cascades, mushrooms):
    total = {}
    for _, counts in cascades:
        for color, n in counts.items():
            total[color] = total.get(color, 0) + n
    events = [{"type": "mushroom_collect", "cascade": c, "multipliers": [1] * n} for c, n in mushrooms.items()]
    return SimpleNamespace(intent_events=events, cascade_color_counts=cascades, cleared_color_counts=total)


def test_each_cascade_scores_at_the_multiplier_after_its_own_mushrooms():
    # research 20261116_183919 008->009: 5 x 7 + 26 x 9 = 269, multiplier 7 -> 9.
    after = {}
    result = _result([(1, {1: 5}), (2, {2: 26})], {2: 2})
    assert simulation._multiplier_score({"score_multiplier": 7}, result, {}, after) == 269
    assert after["score_multiplier"] == 9


def test_no_mushroom_is_plain_count_times_multiplier():
    after = {}
    result = _result([(1, {3: 34})], {})
    assert simulation._multiplier_score({"score_multiplier": 15}, result, {}, after) == 510
    assert after["score_multiplier"] == 15


def test_mode_is_planned_and_other_boards_keep_no_multiplier():
    assert ms.GameMode.MULTIPLIER_MUSHROOMS.value in simulation.PREFIX_MODES
    assert ms.SimulationResult.__dataclass_fields__["cascade_color_counts"].default_factory() == []


def test_color_climb_raises_per_combo_in_our_pair_before_the_pass_scores():
    # One three in our colour 4 and one in colour 1 (not ours), then a pass of 5.
    events = [{"type": "match", "cascade": 1, "kind": "three", "color": 4, "tile_count": 3},
              {"type": "match", "cascade": 1, "kind": "three", "color": 1, "tile_count": 3},
              {"type": "match", "cascade": 2, "kind": "auto_explode", "color": 4, "tile_count": 1}]
    result = SimpleNamespace(intent_events=events, cascade_color_counts=[(1, {4: 3, 1: 3}), (2, {2: 5})],
                             cleared_color_counts={4: 3, 1: 3, 2: 5})
    after = {}
    move = {"score_multiplier": 2, "multiplier_colors": (4, 2), "max_score_multiplier": 9999}
    assert simulation._multiplier_score(move, result, {}, after) == 6 * 3 + 5 * 3
    assert after["score_multiplier"] == 3


def test_color_climb_without_the_pair_and_mighty_mushrooms_are_not_planned():
    model = lambda board: SimpleNamespace(profile={"rules": {"boardModelName": board}})
    assert simulation.plan_refusal({"mode": ms.GameMode.COLOR_CLIMB.value, "engine_refill": model(35),
                                    "score_multiplier": 1})
    assert simulation.plan_refusal({"mode": ms.GameMode.COLOR_CLIMB.value, "engine_refill": model(35),
                                    "score_multiplier": 1, "multiplier_colors": (4, 2)}) is None
    assert simulation.plan_refusal({"mode": ms.GameMode.MULTIPLIER_MUSHROOMS.value,
                                    "engine_refill": model(30)})
    assert simulation.plan_refusal({"mode": ms.GameMode.MULTIPLIER_MUSHROOMS.value,
                                    "engine_refill": model(29)}) is None


def test_gem_grab_and_other_purple_gem_boards():
    model = lambda board: SimpleNamespace(profile={"rules": {"boardModelName": board}})
    assert ms.GameMode.PURPLE_GEM.value in simulation.PREFIX_MODES
    assert simulation.plan_refusal({"mode": ms.GameMode.PURPLE_GEM.value, "engine_refill": model(3)}) is None
    assert simulation.plan_refusal({"mode": ms.GameMode.PURPLE_GEM.value, "engine_refill": model(0)})


def test_energy_boost_knights_take_any_colour_for_the_favour_blue_roll():
    import engine_knights

    class Rng:
        counter = 0

        def chance(self, percent):
            return True

        def next(self):
            self.counter += 1
            return self.counter     # rising keys keep the L-jump list order

    board = [[2] * 5 for _ in range(5)]
    special = [[0] * 5 for _ in range(5)]
    special[2][2] = engine_knights.SIM_KNIGHT
    board[0][1] = engine_knights.SIM_BLUE      # the second L jump in the list is blue
    state = lambda any_colour: engine_knights.KnightState(
        moves=(1,), favor_special=(0,), favor_blue=(100,), uses=0, activations=0,
        any_colour_charges=any_colour)
    plain = engine_knights.knight_area(board, special, Rng(), state(False), [], explodes=lambda c: True)
    boosted = engine_knights.knight_area(board, special, Rng(), state(True), [], explodes=lambda c: True)
    assert plain[1] == (0, 1)          # blue wins the roll
    assert boosted[1] != (0, 1)        # every colour charges: the first candidate stays


def _flag_move(score, refill=True, overflow=False, targets=(150, 450, 1200)):
    return {"score": score, "solo_targets": list(targets),
            "solo_flag_rules": {"refill": refill, "overflow": overflow, "continue_after_last": True}}


def test_solo_flag_stops_the_score_and_refills_the_moves():
    # The Floor Is Lava research 20261117_114312 009->010: 134 + 28 -> 150, moves 3 -> 6.
    after = {"turn_state": {"remaining_moves": 3, "max_moves": 6, "owner_after": "us"}}
    assert simulation._solo_targets(_flag_move(134), after, 28.0) == 16
    assert after["turn_state"]["remaining_moves"] == 6


def test_the_last_flag_overflows_and_gives_no_moves():
    # Mutation Lab research 20261114_222505 080->081: 5749 -> 5761 over 5750, moves 7 -> 6.
    after = {"turn_state": {"remaining_moves": 6, "max_moves": 7}}
    assert simulation._solo_targets(_flag_move(5749, targets=(420, 1200, 5750)), after, 12.0) == 12
    assert after["turn_state"]["remaining_moves"] == 6


def test_flags_off_without_the_rules():
    after = {"turn_state": {"remaining_moves": 3, "max_moves": 6}}
    move = dict(_flag_move(134), solo_flag_rules=None)
    assert simulation._solo_targets(move, after, 28.0) == 28.0
    assert after["turn_state"]["remaining_moves"] == 3


def test_floor_is_lava_is_planned_only_with_the_columns_read():
    assert ms.GameMode.FLOOR_IS_LAVA.value in simulation.PREFIX_MODES
    assert simulation.plan_refusal({"mode": ms.GameMode.FLOOR_IS_LAVA.value, "floor_lava_columns": None})
    assert simulation.plan_refusal({"mode": ms.GameMode.FLOOR_IS_LAVA.value, "floor_lava_columns": (3,)}) is None


def test_plan_swipe_missing_from_the_ranking_is_evaluated():
    import runtime
    board = [[1, 2, 3, 4, 5], [2, 3, 4, 5, 1], [3, 4, 5, 1, 2], [1, 1, 2, 1, 3], [5, 1, 2, 3, 4]]
    special = [[0] * 5 for _ in range(5)]
    pair = ((3, 2), (2, 2))
    seen = []
    planned = runtime.engine_plan_swipe([], pair, evaluate_missing=lambda p: seen.append(p) or "eval")
    assert planned == "eval" and seen == [pair]
    evaluation = runtime.evaluate_plan_pair(board, special, ((3, 2), (3, 3)), ms.GameMode.NONE.value,
                                            include_future_value=False)
    assert evaluation is not None and tuple(evaluation.candidate.start) == (3, 2)


def test_lights_up_counts_only_the_swipes_combos_in_the_lit_column():
    from types import SimpleNamespace
    move = {"score_multiplier": 5, "lights_up_column": 3}
    events = [
        {"type": "match", "cascade": 1, "kind": "three", "color": 6, "tile_count": 3,
         "cells": [[6, 3], [6, 4], [6, 5]]},
        # A cascade combo in the lit column raises nothing (research 125632, 004).
        {"type": "match", "cascade": 2, "kind": "four", "color": 2, "tile_count": 4,
         "cells": [[1, 1], [1, 2], [1, 3], [1, 4]]},
    ]
    result = SimpleNamespace(intent_events=events, cascade_color_counts=[(1, {6: 3}), (2, {2: 4})],
                             cleared_color_counts={6: 3, 2: 4})
    after = {}
    gain = simulation._multiplier_score(move, result, {}, after)
    assert after["score_multiplier"] == 6
    assert gain == 6 * 3 + 6 * 4
    perk_after = {}
    simulation._multiplier_score(move, result, {}, perk_after, perk=True)
    assert perk_after["score_multiplier"] == 5


def test_lights_up_is_refused_without_the_lit_column():
    assert simulation.plan_refusal({"mode": ms.GameMode.LIGHTS_UP.value, "lights_up_column": None,
                                    "score_multiplier": 1})
    assert simulation.plan_refusal({"mode": ms.GameMode.LIGHTS_UP.value, "lights_up_column": 2,
                                    "score_multiplier": 1}) is None


def test_floor_lava_perk_move_marks_and_erupts_nothing():
    cascades = [[ms.MatchGroup(color=1, cells=frozenset({(5, 1), (5, 2), (5, 3)}), kind="three"),
                 ms.MatchGroup(color=5, cells=frozenset({(0, 3), (1, 3), (2, 3), (3, 3)}), kind="four")]]
    assert ms.floor_lava_transition(cascades, ()) == ((3,), (1, 2))
    with ms.floor_lava_perk_move():
        assert ms.floor_lava_transition(cascades, (4,)) == ((), (4,))
