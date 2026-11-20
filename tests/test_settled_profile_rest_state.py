"""settled_profile polls the light restState while the engine moves, never the full profile."""
import square_solo_live as sl


class Script:
    def __init__(self, rests, counter):
        self.rests, self.counter, self.profiles = list(rests), counter, 0
        self.exports_sync = self

    def rest_state(self):
        return self.rests.pop(0) if len(self.rests) > 1 else self.rests[0]

    def match_profile(self, full):
        self.profiles += 1
        return {"logic_key": "L", "consistent": True, "rules": {}, "config": {},
                "rng": {"<counter>k__BackingField": self.counter},
                "state": {"moves": 5, "currentGameState": sl.WAITING_FOR_INPUT}}


def _rest(counter, state=None, chain=0):
    return {"counter": counter, "moves": 5, "chain_reaction": chain,
            "game_state": sl.WAITING_FOR_INPUT if state is None else state}


def test_profile_is_read_once_after_the_engine_rests():
    moving = [_rest(c, state=3, chain=1) for c in (100, 120, 140)]
    script = Script(moving + [_rest(160), _rest(160)], counter=160)
    profile = sl.LiveSquareSolo().settled_profile(script, timeout=2.0, gap=0)
    assert profile["rng"]["<counter>k__BackingField"] == 160
    assert script.profiles == 1


def test_never_at_rest_reads_no_profile():
    script = Script([_rest(1, state=3, chain=1)], counter=1)
    assert sl.LiveSquareSolo().settled_profile(script, timeout=0.05, gap=0) is None
    assert script.profiles == 0
