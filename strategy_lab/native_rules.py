"""Reconstructed result selection, not the trigger for ending a match.

Source: build 145d6d8793109a, GameLogic::CalculateEndGame RVA 0x595d720;
GameState/PVPMode enum and field offsets captured from the same live build.
"""
BUILD='145d6d8793109a'


def terminal_observation(game_state):
    names={2:(0,'score'),3:(1,'score'),4:(0,'technical'),5:(1,'technical'),6:(0,'concede'),7:(1,'concede')}
    if type(game_state) is not int or game_state not in names:return None
    winner,reason=names[game_state]
    return dict(winner_player_index=winner,reason=reason,source='engine_GameState_enum',build=BUILD)


def calculate_result(*, build, pvp_mode, scores, solo_targets=None, rumble_cutoff=None,
                     win_by_rounds=False, win_by_best_round=False, rounds_won=None, best_round_scores=None):
    if build!=BUILD:raise ValueError('Unverified game build')
    def integers(values):
        if not values or any(type(v) is not int for v in values):raise ValueError('Exact integer values required')
        return values
    score=integers(scores)
    if pvp_mode==1:
        targets=integers(solo_targets)
        won=score[0]>=targets[-1]
    elif pvp_mode==2:
        integers([rumble_cutoff]);won=score[0]>=rumble_cutoff
    elif pvp_mode==0:
        metric=rounds_won if win_by_rounds else best_round_scores if win_by_best_round else scores
        metric=integers(metric)
        if len(metric)!=2:raise ValueError('Two players required')
        won=metric[0]>metric[1] # native `cinc ..., le`: ties take Player2Win
    else:raise ValueError('Unknown PVPMode')
    return 2 if won else 3
