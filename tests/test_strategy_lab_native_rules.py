from strategy_lab.native_rules import BUILD,calculate_result,terminal_observation
import pytest

def test_terminal_observation_does_not_guess_from_nonterminal_states():
    assert terminal_observation(-7) is None
    assert terminal_observation(2)['winner_player_index']==0
    assert terminal_observation(7)['reason']=='concede'

@pytest.mark.parametrize('score,expected',[(799,3),(800,2),(801,2)])
def test_solo_threshold(score,expected):
    assert calculate_result(build=BUILD,pvp_mode=1,scores=[score],solo_targets=[400,800])==expected

def test_result_precedence_and_tie():
    assert calculate_result(build=BUILD,pvp_mode=0,scores=[100,100])==3
    assert calculate_result(build=BUILD,pvp_mode=0,scores=[1,999],win_by_rounds=True,rounds_won=[2,1])==2
    assert calculate_result(build=BUILD,pvp_mode=2,scores=[100],rumble_cutoff=100)==2
    with pytest.raises(ValueError):calculate_result(build='old',pvp_mode=0,scores=[100,1])
