"""With the drop known, several extras are played in the order that runs longest.

The player (2026-11-07): play first the extra that does not wreck the other one,
or that leaves an even better one behind, so the run takes the most points.
"""
from types import SimpleNamespace

import move_strategy as ms


def _result(name, extra, points, board):
    return SimpleNamespace(name=name, extra_moves=extra, disco_moves=0, blue_cells=0,
                           points=points, board=board, special_board=None)


def _pick(monkeypatch, tree, order=("a", "b")):
    """tree: {move: (extra, points, board_after)}; boards hold the moves on them."""
    boards = {"root": list(order), "after-a": [], "after-b": ["c"], "after-c": []}

    def simulate(board, candidate, *args):
        extra, points, after = tree[candidate.start]
        return _result(candidate.start, extra, points, after)

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate)
    monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [
        SimpleNamespace(start=name, target="t") for name in boards.get(board, [])])
    monkeypatch.setattr(ms, "_exact_plan_points", lambda result, *args: result.points)
    session = SimpleNamespace(knows=lambda board: board in boards, blue_missing=99)
    evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t")) for name in order]
    with ms.exact_refill_active(session):
        pick = ms.exact_refill_choice(evaluations, "root", None)
    return pick[0].candidate.start, pick[1]


def test_extra_that_leaves_another_extra_goes_first(monkeypatch):
    # a: 50 points and the run ends; b: 10 points, then c is an extra worth 20.
    tree = {"a": (1, 50, "after-a"), "b": (1, 10, "after-b"), "c": (1, 20, "after-c")}
    assert _pick(monkeypatch, tree) == ("b", "niz extra poteza")


def test_bigger_points_win_when_no_run_follows(monkeypatch):
    tree = {"a": (1, 50, "after-a"), "b": (1, 10, "after-b"), "c": (0, 99, "after-c")}
    assert _pick(monkeypatch, tree) == ("a", "niz extra poteza")


def test_tie_keeps_the_bots_order(monkeypatch):
    tree = {"a": (1, 30, "after-a"), "b": (1, 30, "after-a")}
    assert _pick(monkeypatch, tree, order=("b", "a"))[0] == "b"


def test_search_past_its_time_keeps_the_old_pick(monkeypatch):
    tree = {"a": (1, 50, "after-a"), "b": (1, 10, "after-b"), "c": (1, 20, "after-c")}
    monkeypatch.setattr(ms, "EXACT_EXTRA_PLAN_SECONDS", -1.0)
    assert _pick(monkeypatch, tree) == ("a", "extra")


# --- Refill off: the run is planned on the tiles already on the board --------

SOLO = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)


def _visible(monkeypatch, tree, context=SOLO, uncertain=()):
    boards = {"root": ["a", "b"], "after-a": [], "after-b": ["c"], "after-c": []}

    def simulate(board, candidate, *args):
        extra, points, after = tree[candidate.start]
        events = [{"type": "uncertain_refill_boundary"}] if candidate.start in uncertain else []
        return SimpleNamespace(extra_moves=extra, disco_moves=0, points=points, board=after,
                               special_board=None, intent_events=events, cleo_scenario_count=0)

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate)
    monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [
        SimpleNamespace(start=name, target="t") for name in boards.get(board, [])])
    monkeypatch.setattr(ms, "_exact_plan_points", lambda result, *args: result.points)
    monkeypatch.setattr(ms, "has_reliable_same_move_extra", lambda evaluation: True)
    evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t"), disco_moves=0)
                   for name in ("a", "b")]
    pick = ms.plan_visible_extra_sequence(evaluations, "root", None, strategy_context=context)
    return None if pick is None else pick.candidate.start


RUN = {"a": (1, 50, "after-a"), "b": (1, 10, "after-b"), "c": (1, 20, "after-c")}


def test_refill_off_plays_the_extra_that_opens_a_run(monkeypatch):
    assert _visible(monkeypatch, RUN) == "b"


def test_refill_off_does_not_plan_past_a_random_boundary(monkeypatch):
    assert _visible(monkeypatch, RUN, uncertain=("b",)) == "a"


def test_refill_off_planning_is_solo_challenge_only(monkeypatch):
    assert _visible(monkeypatch, RUN, context=ms.StrategyContext(mode=ms.STRATEGY_SOLO_6)) is None


def test_known_drop_leaves_it_to_the_exact_planner(monkeypatch):
    with ms.exact_refill_active(SimpleNamespace(knows=lambda board: True, blue_missing=99)):
        assert _visible(monkeypatch, RUN) is None


# --- Charge (player, 2026-11-11): fill the booster without spending a move ---

def _charged_pick(monkeypatch, blue_missing):
    # a: an extra worth 20 that banks nothing; b: an extra worth 7 whose 4 blue
    # complete the meter. Neither leaves a further extra.
    tree = {"a": (1, 20, "after-a"), "b": (1, 7, "after-a")}
    blue = {"a": 0, "b": 4}
    boards = {"root": ["a", "b"], "after-a": []}

    def simulate(board, candidate, *args):
        extra, points, after = tree[candidate.start]
        return SimpleNamespace(name=candidate.start, extra_moves=extra, disco_moves=0,
                               blue_cells=blue[candidate.start], points=points,
                               board=after, special_board=None)

    monkeypatch.setattr(ms, "_simulate_created_candidate_cached", simulate)
    monkeypatch.setattr(ms, "generate_candidates", lambda board, special: [
        SimpleNamespace(start=name, target="t") for name in boards.get(board, [])])
    monkeypatch.setattr(ms, "_exact_plan_points", lambda result, *args: result.points)
    monkeypatch.setattr(ms, "evaluate_simulation", lambda result, *args, **kwargs: result)
    monkeypatch.setattr(ms, "_booster_charge_cells_for_mode", lambda item, mode: item.blue_cells)
    session = SimpleNamespace(knows=lambda board: board in boards, blue_missing=blue_missing)
    evaluations = [SimpleNamespace(candidate=SimpleNamespace(start=name, target="t")) for name in ("a", "b")]
    with ms.exact_refill_active(session):
        pick = ms.exact_refill_choice(evaluations, "root", None)
    return pick[0].candidate.start


def test_extra_that_fills_the_booster_beats_more_points(monkeypatch):
    assert _charged_pick(monkeypatch, blue_missing=1) == "b"


def test_charge_counts_nothing_on_a_full_meter(monkeypatch):
    assert _charged_pick(monkeypatch, blue_missing=0) == "a"
