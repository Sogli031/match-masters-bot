"""A replay plays under the mutations in force, and the vertical wipe's exception."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import move_strategy as ms  # noqa: E402
import simulator_capture as sc  # noqa: E402


def mutation(kind, active=True):
    return {"type": kind, "config": {"isActivated": active}}


def test_only_activated_mutations_count():
    mutations = [mutation(30), mutation(6, active=False), mutation("25"), {"type": None, "config": {"isActivated": True}},
                 {"config": {"isActivated": True}}, "junk"]
    assert sc.active_mutation_types(mutations) == {30, 25}
    assert sc.active_mutation_types(None) == set()


def _capture(mutations):
    colors = [2, 3, 4, 5]
    board = [[colors[(r + c) % 4] for c in range(7)] for r in range(7)]
    player = {"player_type": 0, "model": {"index": 0, "score": 0, "energy": 0}}
    return {"profile": {}, "simulator_input": {"board": board, "special_board": [[0] * 7 for _ in range(7)],
                                               "active_mutations": mutations, "score_rally_values": {}}, "_player": player}


def test_lab_move_takes_the_flags_from_the_mutations(monkeypatch):
    class Model:
        billie = None

    monkeypatch.setattr("engine_refill.EngineRefill.from_profile", classmethod(lambda cls, *a, **k: Model()))
    monkeypatch.setattr(sc, "capture_mode", lambda profile: ms.GameMode.NONE)
    monkeypatch.setattr(sc, "booster_cost", lambda profile: 7)
    profile = {"rules": {"id": "mutation-lab-solo-mode"}, "spawning": {}, "state": {"moves": 5},
               "players": [{"player_type": 0, "model": {"score": 0, "energy": 0}}]}

    def lab(*types):
        capture = _capture([mutation(kind) for kind in types])
        capture["profile"] = profile
        return sc.lab_move(capture)

    plain = lab()
    assert not plain["specials_explode_immediately"] and not plain["vertical_matches_destroy_color"]
    assert not plain["matches_destroy_color"] and plain["line_destruction"] == (False, False)
    assert lab(6)["specials_explode_immediately"]
    assert lab(7)["every_match_is_special"]
    assert lab(22)["line_destruction"] == (True, False)
    assert lab(23)["line_destruction"] == (False, True)
    assert lab(25)["matches_destroy_color"]
    assert lab(30)["vertical_matches_destroy_color"]


VERTICAL = ms.MatchGroup(frozenset({(0, 0), (1, 0), (2, 0)}), 2, "three")
HORIZONTAL = ms.MatchGroup(frozenset({(6, 0), (6, 1), (6, 2)}), 3, "three")
OTHER_COLUMN = ms.MatchGroup(frozenset({(0, 5), (1, 5), (2, 5)}), 4, "three")
L_SHAPE = ms.MatchGroup(frozenset({(3, 3), (4, 3), (5, 3), (5, 4), (5, 5)}), 6, "l")
SPECIALS = [[0] * 7 for _ in range(7)]


def test_vertical_rule_wipes_a_column_and_a_lone_l():
    assert ms._match_destroy_colors(SPECIALS, [VERTICAL]) == {2}
    assert ms._match_destroy_colors(SPECIALS, [L_SHAPE]) == {6}
    assert ms._match_destroy_colors(SPECIALS, [VERTICAL, OTHER_COLUMN]) == {2, 4}
    assert ms._match_destroy_colors(SPECIALS, [VERTICAL, HORIZONTAL]) == {2}


def test_vertical_rule_wipes_nothing_on_an_l_with_a_second_match():
    assert ms._match_destroy_colors(SPECIALS, [L_SHAPE, VERTICAL]) == set()


def test_matches_explode_color_keeps_every_color():
    assert ms._match_destroy_colors(SPECIALS, [L_SHAPE, VERTICAL], vertical_only=False) == {2, 6}
