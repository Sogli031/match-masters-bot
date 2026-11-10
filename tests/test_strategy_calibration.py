import copy
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import learned_value as lv
import move_strategy as ms
import rebuild_evaluation as rebuild
from run_dataset import (RunSample, annotate_games, continuation_pairs, load_sample,
                         realized_value, temporal_split)
from fit_weights import measure_economy, validated_blue, _paired_validation


def sample(run='2026-09-01_10-00-00_000', **kw):
    data = dict(run=run, day=run[:10], ctx='solo_race', strategy_mode='solo_6',
                action='move', gate='score_gate', booster='default',
                before={'booster_charge': 0, 'booster_maximum': 7, 'remaining_moves': 4,
                        'current_round': 0, 'turn_owner': 'us'},
                after={'current_round': 0, 'turn_owner': 'us'},
                move={'instant_score': 3, 'blue_cells': 3, 'direct_blue_cells': 3},
                board=[[1, 1]], special_board=[[0, 0]], points_gained=3,
                charge_gained=3, charge_room=7, kept_turn=True)
    data.update(kw)
    return RunSample(**data)


def evaluation(blue=3):
    return ms.MoveEvaluation(ms.MoveCandidate((0, 0), (0, 1), ms.Direction.RIGHT,
                            [[1, 1]], [[0, 0]]),
                            score=3, instant_score=3, special_bonus=0, blue_bonus=0,
                            mode_bonus=0, extra_move_bonus=0, disco_move_bonus=0,
                            extra_moves=0, disco_moves=0, cascade_count=0,
                            board_potential=0, lookahead_bonus=0, explanation='',
                            blue_cells=blue, direct_blue_cells=blue)


def weights(accepted=False):
    return lv.LearnedWeights({'enabled': True, 'apply': {'future': False, 'extra': False},
        'contexts': {'solo_race': {'blue_realization': {
            'direct': .893, 'indirect': .825, 'direct_samples': 100,
            'indirect_samples': 100, 'validation': {'accepted': accepted}}}}})


@pytest.mark.parametrize('accepted', [False, True])
@pytest.mark.parametrize('moves', [1, 5])
def test_exact_direct_fill_keeps_its_priority(accepted, moves):
    e = evaluation()
    state = ms.BoosterState(current=4, maximum=7)
    turn = ms.TurnState(remaining_moves=moves, is_final_round=True)
    ctx = ms.StrategyContext(mode='solo_6')
    with patch.object(lv, 'weights', return_value=lv.LearnedWeights(None)):
        neutral = ms._weighted_priority(e, 'None', state, turn, strategy_context=ctx)
    with patch.object(lv, 'weights', return_value=weights(accepted)):
        actual = ms._weighted_priority(e, 'None', state, turn, strategy_context=ctx)
    assert actual == pytest.approx(neutral)
    assert ms._base_blue_priority_components_for_cells(3, state)[1] > 0


def test_full_meter_does_not_pay_for_more_charge():
    assert ms._base_blue_priority_components_for_cells(3, ms.BoosterState(7, 7))[:3] == (0, 0, 0)


def test_unvalidated_legacy_indirect_correction_is_neutral():
    assert weights().blue_multipliers('solo_race') == (1, 1)
    assert weights(True).blue_multipliers('solo_race') == (1, .825)


def test_future_zero_requires_validation_and_is_not_charge_clamped():
    d = {'contexts': {'solo_race': {'future_realization': {'scale': 0, 'samples': 100}}}}
    assert lv.LearnedWeights(d).future_scale('solo_race') == .25
    d['contexts']['solo_race']['future_realization']['validation'] = {'accepted': True}
    assert lv.LearnedWeights(d).future_scale('solo_race') == 0


def test_clock_caps_search_and_reconstruction_roundtrips_every_field():
    turn = ms.TurnState(remaining_moves=8, time_left_seconds=7, seconds_per_move=6.5,
                        current_round=0, total_rounds=3, moves_left_in_match=15,
                        opponent_booster=ms.BoosterState(5, 7, "memory"),
                        opponent_charge_colors=(ms.RED,), opponent_next_turn_moves=2)
    ctx = ms.StrategyContext(mode='solo_6', booster_rush=True)
    exact = {'turn_state': asdict(turn), 'strategy_context': asdict(ctx),
             'booster_state': asdict(ms.BoosterState(4, 7))}
    states = rebuild.build_states(json.loads(json.dumps({'ranking_context': exact})))
    assert states['turn_state'] == turn
    assert states['strategy_context'] == ctx
    assert ms._time_bound_turn(states['turn_state'], ctx)
    assert ms.clamp_lookahead_depth(4, turn) == 1
    # Points-only explicitly plans across configured later rounds; their
    # clocks reset, so the current clock must not erase that horizon.
    assert ms.clamp_points_only_lookahead_depth(4, turn) == 4
    assert ms.clamp_points_only_lookahead_depth(4, replace(turn, is_final_round=True)) == 1
    assert ms.clamp_lookahead_depth(4, replace(turn, time_left_seconds=None)) == 4


def test_temporal_split_cannot_use_test_multiplier_for_training():
    a = sample(points_gained=3)
    b = sample('2026-09-01_10-00-01_000', points_gained=6)
    c = sample('2026-09-02_10-00-00_000', points_gained=30000)
    original = [a, b, c]
    train, test, cutoff = temporal_split(original)
    assert cutoff == '2026-09-02'
    assert train[0].multiplier_hat == 2
    assert test[0].multiplier_hat is None
    assert a.multiplier_hat is None  # no mutation of the caller's dataset


@pytest.mark.parametrize('break_kind', ['booster', 'round', 'opponent', 'after_run'])
def test_future_pairs_do_not_cross_intervening_actions(break_kind):
    a = sample()
    b = sample('2026-09-01_10-00-01_000')
    annotate_games([a, b])
    a.after_run = b.run
    assert len(list(continuation_pairs([a, b]))) == 1
    if break_kind == 'booster': b.game_index += 1
    elif break_kind == 'round': b.before = {**b.before, 'current_round': 1}
    elif break_kind == 'opponent': a.kept_turn = False
    else: a.after_run = 'different_run'
    assert not list(continuation_pairs([a, b]))


def test_censored_charge_cannot_be_a_model_target():
    s = sample(charge_censored=True, multiplier_hat=1)
    assert realized_value(s, {'charge_cell_value': 5, 'move_value': 10}) is None


def test_each_activation_uses_its_own_meter_maximum():
    a = sample(action='activate_booster', points_gained=14, multiplier_hat=1)
    b = sample(action='activate_booster', points_gained=14, multiplier_hat=1,
               before={'booster_maximum': 14})
    assert measure_economy([a, b], 'solo_race')['charge_cell_value'] == 1.5


def test_many_moves_in_one_game_cannot_pass_confidence_gate():
    result = _paired_validation(np.ones(100), np.zeros(100), np.ones(100))
    assert result['samples'] == 100 and result['games'] == 1
    assert not result['accepted']


def test_blue_fit_preserves_direct_counts_and_does_not_consult_test_for_selection():
    tr = [sample(charge_gained=3) for _ in range(50)]
    te = [sample(charge_gained=0) for _ in range(50)]
    for i, s in enumerate(te): s.game_id = i // 5
    result = validated_blue(tr, te, 'solo_race')
    assert result['direct'] == 1 and result['indirect'] == 1
    assert result['candidate_indirect'] == 1
    assert not result['validation']['accepted']


def test_round_boundary_and_missing_measurements_are_not_extra_or_swallowed(tmp_path):
    mv = {'selected_action': 'move', 'best_move': {'score': 3},
          'strategy_context': {'mode': 'solo_6'}}
    delta = {'state_delta': {'before': {'current_round': 0, 'turn_owner': 'us'},
              'after': {'current_round': 1, 'turn_owner': 'us'}, 'remaining_moves_gained': 0},
             'board_delta': {'changed_count': 0}}
    (tmp_path/'move.json').write_text(json.dumps(mv))
    (tmp_path/'observed_delta.json').write_text(json.dumps(delta))
    s = load_sample(tmp_path)
    assert s.kept_turn is None
    assert not s.swallowed


def test_training_uses_recorded_priority_not_reconstruction():
    import train_value_model as tv
    s = sample(multiplier_hat=1)
    s.move['priority_score'] = 17
    s.raw['ranking_provenance'] = {'schema_version': 2}
    with patch.object(tv.rebuild_evaluation, 'runtime_priority', return_value=72):
        rows = tv.build_rows([s], {'solo_race': {'charge_cell_value': 5, 'move_value': 10}})
    assert rows[2].tolist() == [17]


def test_training_rejects_unlogged_priority_even_if_reconstruction_works():
    import train_value_model as tv
    s = sample(multiplier_hat=1)
    with patch.object(tv.rebuild_evaluation, 'runtime_priority', return_value=72):
        rows = tv.build_rows([s], {'solo_race': {'charge_cell_value': 5, 'move_value': 10}})
    assert len(rows[1]) == 0


def test_debug_priority_cannot_leak_between_boards_or_decisions():
    a = evaluation()
    b = replace(a, candidate=replace(a.candidate, board=[[2, 2]]))
    lv.begin_decision()
    lv.remember_priority(a, 17)
    assert lv.last_priorities.get(lv.candidate_key(b)) is None
    lv.begin_decision()
    assert lv.last_priorities.get(lv.candidate_key(a)) is None


def test_legacy_coordinate_cached_priority_is_not_a_training_label():
    import train_value_model as tv
    s = sample(multiplier_hat=1)
    s.move['priority_score'] = 17
    rows = tv.build_rows([s], {'solo_race': {'charge_cell_value': 5, 'move_value': 10}})
    assert len(rows[1]) == 0
