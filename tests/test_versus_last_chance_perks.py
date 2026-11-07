"""Versus last chance: an unused perk goes before the last handover.

Debug/runs 2026-10-31_11-37-47_566 (Floor Is Lava) and _11-46-47_172
(Multiplier Mushrooms Studio): final versus round, last move, slot 2 Remove
Cross available, perk_candidates empty, score_gate swipe handed the last turn
over. Remove Cross was skipped as long as the normal move was "smart".
11-48-34_981 / 11-48-39_431 are the positive control (slot 2 before slot 1).
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

import move_strategy as ms
import runtime
from tools.replay_perk_endgame import replay

RUNS = Path(__file__).resolve().parents[1] / "Debug" / "runs"
LAVA = "2026-10-31_11-37-47_566"
MUSHROOMS = "2026-10-31_11-46-47_172"
CONTROL_SLOT_2 = "2026-10-31_11-48-34_981"
CONTROL_SLOT_1 = "2026-10-31_11-48-39_431"


def _needs(run):
    if not (RUNS / run / "move.json").exists():
        pytest.skip(f"Debug/runs/{run} not present")


def _slot_reason(decision, slot):
    return next(entry["reason"] for entry in decision["slot_reasons"] if entry["slot"] == slot)


@pytest.mark.parametrize("run", [LAVA, MUSHROOMS])
def test_missed_final_handover_now_spends_remove_cross(run):
    _needs(run)
    result = replay(run)
    assert result["old"]["action"] == "move"
    assert result["old"]["gate"] == "score_gate"
    new = result["new"]
    assert new["last_chance"] == {"active": True, "reason": "last_move"}
    assert new["action"] == "activate_perk"
    assert new["gate"] == "perk_last_chance_gate"
    assert new["selected"]["perk"] == ms.PERK_REMOVE_CROSS
    assert new["selected"]["slot_number"] == 2
    assert new["selected"]["target"] is not None
    assert _slot_reason(new, 1) == "slot_unavailable"
    assert _slot_reason(new, 2) == "selected"


def test_lava_replay_reproduces_the_historical_swipe():
    _needs(LAVA)
    # The marks are recorded 1-based; replayed 0-based the baseline is the
    # swipe that was actually played.
    result = replay(LAVA)
    assert sorted(map(tuple, result["baseline_move"])) == sorted(
        map(tuple, result["old"]["move"])
    )


def test_old_branch_was_the_smart_move_skip():
    _needs(MUSHROOMS)
    diagnostics = {}
    result = replay(MUSHROOMS)
    assert result["new"]["action"] == "activate_perk"
    # Without the last-chance window the same board produces nothing, and the
    # reason names the branch.
    move = json.loads((RUNS / MUSHROOMS / "move.json").read_text())
    from tools.replay_perk_endgame import contexts

    booster, turn, strategy = contexts(move)
    kw = dict(mode=move["mode"], allow_square_matches=True, score_rally_values=None)
    ranked = ms.rank_moves(move["board"], move["special_board"], strategy_context=strategy, **kw)
    baseline = ms.prioritize_ranked_moves(
        ranked, booster_state=booster, turn_state=turn, strategy_context=strategy, **kw
    )[0]
    context = ms.PerkDecisionContext(
        booster=booster, turn=turn,
        blue_plan=ms.evaluate_blue_plan(move["board"], move["special_board"], booster, **kw),
        objective=ms.PerkObjective.MAX_BLUE,
    )
    actions = runtime.rank_selected_perk_actions(
        move["board"], move["special_board"], ("none", "remove_cross"),
        normal_baseline=baseline, decision_context=context, strategy_context=strategy,
        diagnostics=diagnostics, **kw,
    )
    assert actions == []
    assert diagnostics[ms.PERK_REMOVE_CROSS] == "remove_cross_normal_move_smart"


@pytest.mark.parametrize(
    "run, perk, slot",
    [(CONTROL_SLOT_2, ms.PERK_REMOVE_CROSS, 2), (CONTROL_SLOT_1, ms.PERK_ENERGY_BOOST, 1)],
)
def test_positive_control_slot_2_before_slot_1_is_unchanged(run, perk, slot):
    _needs(run)
    result = replay(run)
    assert result["old"]["perk"] == perk and result["old"]["slot"] == slot
    new = result["new"]
    assert new["last_chance"]["active"] is False
    assert new["action"] == "activate_perk"
    assert new["selected"]["perk"] == perk
    assert new["selected"]["slot_number"] == slot


def test_two_perks_last_move_fires_the_non_swipe_perk_first():
    # Energy Boost plays the swipe itself; fired first on the last move it
    # would end the turn with Remove Cross still unused.
    _needs(MUSHROOMS)
    new = replay(MUSHROOMS, selected_perks=("energy_boost", "remove_cross"))["new"]
    assert new["action"] == "activate_perk"
    assert new["selected"]["perk"] == ms.PERK_REMOVE_CROSS
    assert new["selected"]["slot_number"] == 2


def test_two_perks_slots_swapped_still_fires_remove_cross_first():
    _needs(MUSHROOMS)
    new = replay(MUSHROOMS, selected_perks=("remove_cross", "energy_boost"))["new"]
    assert new["selected"]["perk"] == ms.PERK_REMOVE_CROSS
    assert new["selected"]["slot_number"] == 1


def _turn(remaining, *, final=True, time_left=None):
    return ms.TurnState(
        remaining_moves=remaining, source="memory", is_final_round=final,
        current_round=2 if final else 1, total_rounds=2,
        time_left_seconds=time_left, seconds_per_move=6.5,
    )


def test_last_chance_window():
    versus = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
    assert ms.versus_perk_last_chance(_turn(1), versus, 1) == (True, "last_move")
    assert ms.versus_perk_last_chance(_turn(2), versus, 1)[0] is False
    # Two unused perks open the window one move earlier.
    assert ms.versus_perk_last_chance(_turn(2), versus, 2) == (True, "two_perks_early_window")
    assert ms.versus_perk_last_chance(_turn(3), versus, 2)[0] is False
    # The clock caps the move counter: 3 moves but only ~1 move of clock.
    assert ms.versus_perk_last_chance(_turn(3, time_left=9.0), versus, 1) == (True, "last_move")
    assert ms.versus_perk_last_chance(_turn(1, final=False), versus, 2) == (
        False, "not_final_round",
    )
    assert ms.versus_perk_last_chance(_turn(1), ms.StrategyContext(ms.STRATEGY_SOLO_6), 2)[0] is False


def _evaluation_with_direct_extra(run):
    from tools.replay_perk_endgame import contexts, load_run

    move = load_run(run)
    booster, turn, strategy = contexts(move)
    kw = dict(mode=move["mode"], allow_square_matches=True, score_rally_values=None)
    ranked = ms.rank_moves(move["board"], move["special_board"], strategy_context=strategy, **kw)
    baseline = ms.prioritize_ranked_moves(
        ranked, booster_state=booster, turn_state=turn, strategy_context=strategy, **kw
    )[0]
    return move, booster, turn, strategy, kw, replace(baseline, direct_extra_moves=1.0, extra_moves=1.0)


def test_guaranteed_extra_is_preserved_and_the_window_waits():
    _needs(MUSHROOMS)
    move, booster, turn, strategy, kw, baseline = _evaluation_with_direct_extra(MUSHROOMS)
    assert ms.has_reliable_same_move_extra(baseline)
    assert ms.versus_perk_last_chance(turn, strategy, 1, baseline) == (
        False, "direct_guaranteed_extra",
    )
    context = ms.PerkDecisionContext(
        booster=booster, turn=turn,
        blue_plan=ms.evaluate_blue_plan(move["board"], move["special_board"], booster, **kw),
        objective=ms.PerkObjective.MAX_BLUE,
    )
    decision = runtime.decide_auto_perk(
        move["board"], move["special_board"], ("none", "remove_cross"),
        normal_baseline=baseline, decision_context=context, strategy_context=strategy, **kw,
    )
    assert decision.selected is None
    assert decision.slot_reasons[1]["reason"] == "direct_guaranteed_extra"


def test_unavailable_slot_reports_the_source_reason():
    _needs(MUSHROOMS)
    move, booster, turn, strategy, kw, _ = _evaluation_with_direct_extra(MUSHROOMS)
    context = ms.PerkDecisionContext(booster=booster, turn=turn, objective=ms.PerkObjective.MAX_BLUE)
    status = (
        {"slot": 1, "perk": "energy_boost", "available": False, "source": "memory", "reason": "used_engine"},
        {"slot": 2, "perk": "remove_cross", "available": False, "source": "memory", "reason": "low_turn_time<=8s"},
    )
    decision = runtime.decide_auto_perk(
        move["board"], move["special_board"], ("none", "none"),
        normal_baseline=None, decision_context=context, strategy_context=strategy,
        perk_slot_status=status, blocked_reason="no_available_slot", **kw,
    )
    assert decision.selected is None and decision.candidates == []
    reasons = {entry["slot"]: entry for entry in decision.slot_reasons}
    assert reasons[1]["reason"] == "slot_unavailable:used_engine"
    assert reasons[1]["perk"] == "energy_boost"
    assert reasons[2]["reason"] == "slot_unavailable:low_turn_time<=8s"


def test_low_clock_on_the_last_chance_starts_no_perk():
    _needs(MUSHROOMS)
    move, booster, _turn_state, strategy, kw, _ = _evaluation_with_direct_extra(MUSHROOMS)
    turn = _turn(1, time_left=7.0)
    context = ms.PerkDecisionContext(booster=booster, turn=turn, objective=ms.PerkObjective.MAX_BLUE)
    decision = runtime.decide_auto_perk(
        move["board"], move["special_board"], ("none", "remove_cross"),
        normal_baseline=None, decision_context=context, strategy_context=strategy, **kw,
    )
    assert decision.selected is None
    assert decision.slot_reasons[1]["reason"].startswith("low_turn_time")


def test_last_move_fires_at_zero_net_gain_but_not_below():
    action = ms.PerkAction(
        perk_key=ms.PERK_REMOVE_CROSS, target=(0, 0), score=0.0, gross_score=0.0,
        threshold=0.0, baseline_score=0.0, net_gain=0.0,
    )
    assert ms.perk_activation_decision(action, None, last_chance=True, last_move=True)[0]
    assert not ms.perk_activation_decision(action, None)[0]
    worse = replace(action, net_gain=-1.0)
    fires, _margin, gate = ms.perk_activation_decision(worse, None, last_chance=True, last_move=True)
    assert not fires and gate == "perk_preserve_horizon_gate"


def test_reserve_never_holds_a_perk_on_the_last_chance():
    action = ms.PerkAction(
        perk_key=ms.PERK_REMOVE_CROSS, target=(0, 0), score=0.0, gross_score=0.0,
        threshold=10.0, baseline_score=0.0, net_gain=1.0,
    )
    context = ms.PerkDecisionContext(turn=ms.TurnState(remaining_moves=1, current_round=1, total_rounds=4))
    versus = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
    assert ms.should_reserve_last_perk(["remove_cross"], action, context, versus)
    assert not ms.should_reserve_last_perk(
        ["remove_cross"], action, context, versus, last_chance=True
    )


def test_floor_lava_guard_drops_targets_that_cost_the_eruption():
    baseline = ms.MoveEvaluation.__new__(ms.MoveEvaluation)
    object.__setattr__(baseline, "floor_lava_destroyed_columns", (2,))
    object.__setattr__(baseline, "instant_score", 40.0)
    object.__setattr__(baseline, "mode_bonus", 0.0)
    follow_up = ms.MoveEvaluation.__new__(ms.MoveEvaluation)
    object.__setattr__(follow_up, "floor_lava_destroyed_columns", ())
    object.__setattr__(follow_up, "instant_score", 10.0)
    object.__setattr__(follow_up, "mode_bonus", 0.0)
    weak = ms.PerkAction(
        perk_key=ms.PERK_REMOVE_CROSS, target=(1, 1), score=0.0, gross_score=0.0,
        threshold=0.0, baseline_score=0.0, follow_up=follow_up, immediate_points=20.0,
    )
    strong = replace(weak, target=(2, 2), immediate_points=35.0)
    diagnostics = {}
    kept = runtime._drop_floor_lava_effect_losses(
        [weak, strong], baseline, "The Floor Is Lava", diagnostics
    )
    assert kept == [strong]
    assert runtime._drop_floor_lava_effect_losses([weak], baseline, "The Floor Is Lava", diagnostics) == []
    assert diagnostics[ms.PERK_REMOVE_CROSS] == "floor_lava_effect_lost"
    # Other modes are untouched.
    assert runtime._drop_floor_lava_effect_losses([weak], baseline, "Multiplier Mushrooms Studio") == [weak]


def test_final_handover_audit_counts_confirmed_unused_perks(tmp_path):
    versus = ms.StrategyContext(ms.STRATEGY_VERSUS_2)
    status = (
        {"slot": 1, "perk": "energy_boost", "available": False, "reason": "used_bot"},
        {"slot": 2, "perk": "remove_cross", "available": True, "reason": "available"},
    )
    log = tmp_path / "audit.jsonl"
    audit = runtime.record_final_handover_perk_audit(
        turn_state=_turn(1, time_left=11.0), strategy_context=versus,
        played_evaluation=None, selected_perks=("none", "remove_cross"),
        perk_slot_status=status,
        perk_slot_reasons=[{"slot": 2, "reason": "floor_lava_effect_lost"}],
        mode="The Floor Is Lava", log_path=log,
    )
    assert audit["unused_confirmed"] == 1
    assert audit["slots"][1]["decision_reason"] == "floor_lava_effect_lost"
    assert len(log.read_text().splitlines()) == 1
    # Not the last handover: nothing recorded.
    assert runtime.record_final_handover_perk_audit(
        turn_state=_turn(2), strategy_context=versus, played_evaluation=None,
        selected_perks=("none", "remove_cross"), log_path=log,
    ) is None
    assert runtime.record_final_handover_perk_audit(
        turn_state=_turn(1, final=False), strategy_context=versus, played_evaluation=None,
        selected_perks=("none", "remove_cross"), log_path=log,
    ) is None


def _memory_window(**attrs):
    from types import SimpleNamespace

    import memory_gui

    window = SimpleNamespace(
        PerksCheck=SimpleNamespace(isChecked=lambda: True),
        _perk_keys=("energy_boost", "remove_cross"),
        _perk_types=(13, 20),
        _used_perk_slots=set(),
        _used_perk_slot_sources={},
        _perk_pending_confirmation=None,
        _turn_clock_key=("turn", 2, 0),
        _log=lambda message: None,
    )
    for name in ("_perk_confirmation_pending", "_perk_slot_status", "_note_used_board_ability"):
        setattr(window, name, getattr(memory_gui.MemoryWindow, name).__get__(window))
    window.__dict__.update(attrs)
    return window, memory_gui


def test_unconfirmed_perk_blocks_a_second_perk_until_memory_confirms():
    window, memory_gui = _memory_window()
    select = memory_gui.MemoryWindow._selected_perks_for_request.__get__(window)
    assert select({}, None) == ("energy_boost", "remove_cross")
    window._perk_pending_confirmation = (2, window._turn_clock_key)
    assert select({}, None) == (runtime.PERK_NONE, runtime.PERK_NONE)
    reasons = {entry["slot"]: entry["reason"] for entry in window._perk_slot_status()}
    assert reasons[1] == "pending_confirmation_slot_2"
    # Memory confirms slot 2: the block lifts, slot 2 is spent, slot 1 is free.
    window._note_used_board_ability(
        {"is_board_ability_used_this_move": True, "board_ability_used_this_move": 20}
    )
    assert window._perk_pending_confirmation is None
    assert select({}, None) == ("energy_boost", runtime.PERK_NONE)
    status = {entry["slot"]: entry for entry in window._perk_slot_status()}
    assert status[2]["reason"] == "used_engine" and not status[2]["available"]


def test_unconfirmed_perk_block_ends_with_the_turn():
    window, memory_gui = _memory_window()
    select = memory_gui.MemoryWindow._selected_perks_for_request.__get__(window)
    window._perk_pending_confirmation = (1, ("turn", 1, 0))
    assert select({}, None) == ("energy_boost", "remove_cross")
    assert window._perk_pending_confirmation is None
