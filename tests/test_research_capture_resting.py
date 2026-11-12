"""The move's own resting read feeds the refill check (capture_resting).

Crazy Columns 2026-11-12 00:46-00:48 (research off, Auto): the watcher's read
was lost on 28 of 29 moves because the swipe does not wait for it.
"""
from research_recorder import ResearchRecorder

BOARD = [[1, 2], [3, 4]]
SPECIAL = [[0, 0], [0, 20]]


def _snapshot(moves=5):
    return {"board": BOARD, "special_board": SPECIAL, "slots": [{"value": 40}],
            "board_fields": {}, "state": {"moves": moves, "players": []}}


def _profile(counter=100, moves=5, game_state=-5):
    return {"rng": {"<counter>k__BackingField": counter},
            "state": {"moves": moves, "currentGameState": game_state}, "players": [], "rules": {"id": "x"}}


def _recorder():
    recorder, seen = ResearchRecorder(), []
    recorder.on_capture = lambda entry, missed: seen.append((entry, missed))
    return recorder, seen


def test_resting_board_goes_to_the_check_once():
    recorder, seen = _recorder()
    assert recorder.capture_resting(_snapshot(), _profile(), (7, "move", None))
    assert not recorder.capture_resting(_snapshot(), _profile(), (7, "move", None))
    entry, missed = seen[0]
    assert not missed and entry["refill_input"] == (7, "move", None)
    assert entry["board"] == BOARD and entry["special_board"] == SPECIAL
    assert entry["profile"]["rng"]["<counter>k__BackingField"] == 100
    assert entry["raw_slots"] == [{"value": 40}]


def test_a_new_rng_on_the_same_board_is_a_new_record():
    recorder, seen = _recorder()
    recorder.capture_resting(_snapshot(), _profile(100), None)
    recorder.capture_resting(_snapshot(), _profile(140), None)
    assert len(seen) == 2


def test_a_board_not_at_rest_is_not_handed_over():
    recorder, seen = _recorder()
    assert not recorder.capture_resting(_snapshot(), _profile(game_state=-7), None)
    assert not recorder.capture_resting(_snapshot(moves=5), _profile(moves=4), None)
    assert seen == []
