"""Regression boards from the Froggy Fu match on 2026-10-16 at 02:04."""
from dataclasses import replace
import json
from pathlib import Path

import pytest
import move_strategy as ms
from tools.rebuild_evaluation import build_states


FRAMES = json.loads((Path(__file__).parent / "fixtures/dustville_wanted.json").read_text())


def rank_frame(index):
    frame = FRAMES[index]
    states = build_states(frame)
    with ms.froggy_gather_region_active(7, True):
        candidates = ms.rank_moves(frame["board"], frame["special_board"],
            mode=states["mode"], score_rally_values=states["score_rally_values"],
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"],
            strategy_context=states["strategy_context"])
        ranked = ms.prioritize_ranked_moves(candidates,
            allow_square_matches=frame["allow_square_matches"],
            explode_created_specials_immediately=frame["specials_explode_immediately"], **states)
    return ranked, states


@pytest.mark.parametrize("index", range(5))
def test_recorded_board_collects_two_wanted_tiles(index):
    ranked, states = rank_frame(index)
    assert ranked[0].mode_targets == 2
    assert ms._dustville_wanted_charge(ranked[0], states["mode"]) == 4


def test_known_extra_still_precedes_wanted_collection():
    ranked, _ = rank_frame(5)
    assert ms.has_reliable_same_move_extra(ranked[0])


def test_charge_floor_excludes_already_cleared_and_missing_blues():
    ranked, states = rank_frame(0)
    item = ranked[0]
    count = sum(c == ms.BLUE for row in item.candidate.board for c in row)
    item = replace(item, blue_cells=count - 1)
    assert ms._dustville_wanted_charge(item, states["mode"]) == 1
    assert ms._dustville_wanted_charge(replace(item, blue_cells=count), states["mode"]) == 0
    assert ms._dustville_wanted_charge(item, ms.GameMode.NONE) == 0
    uncertain = replace(item, intent_events=[dict(type="uncertain_refill_boundary", after_cascade=0)])
    assert ms._dustville_wanted_charge(uncertain, states["mode"]) == 0


def test_old_residual_cannot_penalize_wanted_shots(monkeypatch):
    ranked, states = rank_frame(0)
    monkeypatch.setattr(ms, "_LEARNED_RANK_DEPTH", 1)
    monkeypatch.setattr(ms.learned_value.model(), "enabled", True)
    def invalid_model(*args, **kwargs):
        raise AssertionError("old residual lacks Dustville shot outcomes")
    monkeypatch.setattr(ms.learned_value, "residual_adjustment", invalid_model)
    assert ms._learned_residual(ranked[0], "solo_6", states["booster_state"],
        states["turn_state"], states["strategy_context"], "early", states["mode"]) == 0


def disco_on_orange():
    """A disco ball swiped onto orange; two orange cells are wanted figures."""
    pattern = (ms.RED, ms.GREEN, ms.PURPLE, ms.YELLOW, ms.BLUE)
    board = [[pattern[(row * 2 + col) % 5] for col in range(7)] for row in range(7)]
    specials = [[ms.EMPTY] * 7 for _ in range(7)]
    board[3][3], specials[3][3] = 99, ms.SPECIAL_DISCO_BALL
    board[3][4] = ms.ORANGE
    for cell in ((0, 0), (6, 6)):
        board[cell[0]][cell[1]] = ms.ORANGE
        specials[cell[0]][cell[1]] = ms.SPECIAL_MODE_TARGET
    return ms.MoveCandidate((3, 3), (3, 4), ms.Direction.RIGHT, board, specials)


def test_disco_on_orange_pops_wanted_figures_without_their_shots():
    # Player, 2026-11-07: the figures pop, the booster does not fill
    # (recorded 091625 003 and 009: charge 3->3 and 2->2).
    candidate = disco_on_orange()
    plain = ms._simulate_disco_candidate(candidate, mode=ms.GameMode.NONE)
    dustville = ms._simulate_disco_candidate(candidate, mode=ms.GameMode.DUSTVILLE_DUEL)
    assert plain.mode_targets == 2
    assert dustville.mode_targets == 0
    assert not any(e.get("type") == "mode_target_collect" for e in dustville.intent_events)
    wiped = [e for e in dustville.intent_events if e.get("type") == ms.DUSTVILLE_DISCO_WANTED_EVENT]
    assert [e["count"] for e in wiped] == [2]


def test_wiped_figures_do_not_claim_collection_bonus():
    candidate = disco_on_orange()
    result = ms._simulate_disco_candidate(candidate, mode=ms.GameMode.DUSTVILLE_DUEL)
    evaluation = ms.evaluate_simulation(result, ms.GameMode.DUSTVILLE_DUEL, include_future_value=False)
    assert evaluation.mode_targets == 0
    assert evaluation.mode_bonus == 0


RUN_09_56_03 = Path(__file__).resolve().parents[1] / "Debug/runs/2026-11-07_09-56-03_761/move.json"


@pytest.mark.skipif(not RUN_09_56_03.is_file(), reason="Dustville disco run not present")
def test_disco_setup_board_keeps_wanted_figures():
    """The ball may set up blue, but must not fire figures in its first wave."""
    frame = json.loads(RUN_09_56_03.read_text(encoding="utf-8"))
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"], mode=states["mode"],
        score_rally_values=states["score_rally_values"], allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"],
        strategy_context=states["strategy_context"])
    ranked = ms.prioritize_ranked_moves(candidates, allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"], **states)
    assert (ranked[0].candidate.start, ranked[0].candidate.target) == ((4, 2), (4, 1))
    assert not any(e.get("type") in (ms.DUSTVILLE_DISCO_WANTED_EVENT,
                                    "dustville_wanted_shots") and e.get("cascade") == 1
                   for e in ranked[0].intent_events)


def test_charge_counts_collected_wanted_figures_but_not_wiped_ones():
    ranked, states = rank_frame(0)
    item = ranked[0]
    assert item.mode_targets == 2
    charge = ms._booster_charge_cells_for_mode(item, states["mode"])
    assert charge == item.blue_cells + ms._dustville_wanted_charge(item, states["mode"]) > item.blue_cells
    wiped = ms._simulate_disco_candidate(disco_on_orange(), mode=ms.GameMode.DUSTVILLE_DUEL)
    evaluation = ms.evaluate_simulation(wiped, ms.GameMode.DUSTVILLE_DUEL, include_future_value=False)
    assert ms._booster_charge_cells_for_mode(evaluation, ms.GameMode.DUSTVILLE_DUEL) == evaluation.blue_cells


def test_wanted_minimum_shots_can_finish_meter_before_uncertain_refill():
    ranked, states = rank_frame(3)
    item = ranked[0]
    assert item.mode_targets == 2
    assert states["booster_state"].remaining == 1
    assert ms._move_has_uncertain_cascade(item)
    assert ms._dustville_reliable_charge(item, states["booster_state"], states["mode"]) == 1


def test_exact_refill_keeps_an_unfollowable_top_pick_with_as_much_blue(monkeypatch):
    from types import SimpleNamespace as NS
    top = NS(candidate=NS(start=(0, 0), target=(0, 1)), blue_cells=2.75, score=71.0)
    sure = NS(candidate=NS(start=(1, 0), target=(1, 1)), blue_cells=3.0, score=15.0)
    results = {(0, 0): NS(exact_refill_supported=False),
               (1, 0): NS(exact_refill_supported=True, extra_moves=0, blue_cells=3.0, board=[], special_board=[])}
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached",
                        lambda board, candidate, *a, **k: results[tuple(candidate.start)])
    session = NS(knows=lambda *a: True, use_special_keys=False, blue_missing=99, moves_left=5)
    monkeypatch.setattr(ms, "_EXACT_REFILL", session)
    assert ms.exact_refill_choice([top, sure], [[1]], [[0]]) is None
    top.blue_cells = 1.0      # clearly less blue: the sure charge wins
    choice = ms.exact_refill_choice([top, sure], [[1]], [[0]])
    assert choice is not None and choice[0] is sure


# These boards are from the last 10:06-10:17 Dustville games. This replay has
# the captured board and meter, but not the live ExactRefillSession RNG state.
# The exact-refill override is tested separately below.
BETTER_REPLAY_CHOICES = (
    ("10-07-49_738", (6, 0), (6, 1)),
    ("10-07-58_206", (6, 3), (5, 3)),
    ("10-08-37_640", (5, 4), (5, 5)),
    ("10-09-47_334", (3, 2), (3, 3)),
    ("10-13-16_291", (3, 2), (3, 3)),
    ("10-13-38_697", (6, 3), (6, 4)),
    ("10-14-05_168", (5, 4), (5, 5)),
    ("10-17-17_178", (4, 5), (4, 4)),
    ("10-17-26_330", (2, 2), (3, 2)),
    ("10-47-21_151", (2, 0), (1, 0)),
    ("11-21-06_906", (5, 4), (6, 4)),
    ("11-22-59_343", (5, 3), (5, 2)),
)


@pytest.mark.parametrize("run_suffix,start,target", BETTER_REPLAY_CHOICES)
def test_recent_dustville_replay_prioritizes_reliable_charge(run_suffix, start, target):
    files = list((Path(__file__).resolve().parents[1] / "Debug/runs").glob(
        f"2026-11-07_{run_suffix}/move.json"))
    if not files:
        pytest.skip("recorded Dustville run not present")
    frame = json.loads(files[0].read_text(encoding="utf-8"))
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"],
        mode=states["mode"], score_rally_values=states["score_rally_values"],
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"],
        strategy_context=states["strategy_context"])
    ranked = ms.prioritize_ranked_moves(candidates,
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"], **states)
    chosen = ranked[0]
    assert (chosen.candidate.start, chosen.candidate.target) == (start, target)
    old = next(item for item in candidates if
        item.candidate.start == tuple(frame["best_move"]["start"]) and
        item.candidate.target == tuple(frame["best_move"]["target"]))
    charge = lambda item: ms._dustville_reliable_charge(
        item, states["booster_state"], states["mode"])
    assert charge(chosen) >= charge(old)


def test_dustville_exact_refill_does_not_trade_56_points_for_fractional_blue(monkeypatch):
    from types import SimpleNamespace as NS
    high = NS(candidate=NS(start=(5, 6), target=(6, 6)), blue_cells=2.75,
              mode_targets=0, intent_events=[], cleo_scenario_count=0, score=71.0)
    low = NS(candidate=NS(start=(6, 0), target=(6, 1)), blue_cells=3.0,
             mode_targets=0, intent_events=[], cleo_scenario_count=0, score=15.0)
    results = {(5, 6): NS(exact_refill_supported=True, extra_moves=0,
                          disco_moves=0, blue_cells=2.75, board=[], special_board=[]),
               (6, 0): NS(exact_refill_supported=True, extra_moves=0,
                          disco_moves=0, blue_cells=3.0, board=[], special_board=[])}
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached",
                        lambda board, candidate, *a, **k: results[tuple(candidate.start)])
    monkeypatch.setattr(ms, "_EXACT_REFILL", NS(knows=lambda *a: True,
                        use_special_keys=False, blue_missing=3, moves_left=5))
    assert ms.exact_refill_choice([high, low], [[1]], [[0]],
                                 mode=ms.GameMode.DUSTVILLE_DUEL) is None


def test_dustville_exact_refill_keeps_free_disco_before_paid_move(monkeypatch):
    from types import SimpleNamespace as NS
    disco = NS(candidate=NS(start=(0, 0), target=(0, 1)), blue_cells=0,
               mode_targets=0, intent_events=[], cleo_scenario_count=0,
               score=40.0, disco_moves=1)
    paid = NS(candidate=NS(start=(1, 0), target=(1, 1)), blue_cells=2,
              mode_targets=0, intent_events=[], cleo_scenario_count=0,
              score=90.0, disco_moves=0)
    results = {(0, 0): NS(exact_refill_supported=True, extra_moves=0,
                          blue_cells=0, board=[], special_board=[]),
               (1, 0): NS(exact_refill_supported=True, extra_moves=0,
                          blue_cells=2, board=[], special_board=[])}
    monkeypatch.setattr(ms, "_simulate_created_candidate_cached",
                        lambda board, candidate, *a, **k: results[tuple(candidate.start)])
    monkeypatch.setattr(ms, "_EXACT_REFILL", NS(knows=lambda *a: True,
                        use_special_keys=False, blue_missing=3, moves_left=5))
    assert ms.exact_refill_choice([disco, paid], [[1]], [[0]],
                                 mode=ms.GameMode.DUSTVILLE_DUEL) is None


def test_latest_game_prefers_a_certain_booster_fill():
    from tools.rebuild_evaluation import build_evaluation
    run = Path(__file__).resolve().parents[1] / "Debug/runs/2026-11-07_10-41-58_093"
    if not run.is_dir():
        pytest.skip("latest Dustville run not present")
    frame = json.loads((run / "move.json").read_text(encoding="utf-8"))
    candidates = json.loads((run / "candidates.json").read_text(encoding="utf-8"))
    states = build_states(frame)
    old = next(c for c in candidates if c["start"] == [6, 3] and c["target"] == [5, 3])
    fill = next(c for c in candidates if c["start"] == [4, 1] and c["target"] == [4, 2])
    evaluation = lambda c: build_evaluation(c, frame["board"], frame["special_board"])
    charge = lambda c: ms._dustville_reliable_charge(evaluation(c), states["booster_state"], states["mode"])
    assert old["score"] > fill["score"] and fill["blue_cells"] == 3
    assert charge(fill) > charge(old)
    observed = json.loads((run / "observed_delta.json").read_text(encoding="utf-8"))
    assert observed["state_delta"]["booster_charge_gained"] == 0


@pytest.mark.parametrize("run_suffix", (
    "10-53-20_140", "10-54-42_716", "11-01-09_362",
    "11-01-39_595", "11-03-17_488",
))
def test_recent_disco_extra_cannot_wipe_wanted_figures(run_suffix):
    run = Path(__file__).resolve().parents[1] / "Debug/runs" / f"2026-11-07_{run_suffix}"
    if not run.is_dir():
        pytest.skip("recorded Dustville run not present")
    frame = json.loads((run / "move.json").read_text(encoding="utf-8"))
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"],
        mode=states["mode"], score_rally_values=states["score_rally_values"],
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"],
        strategy_context=states["strategy_context"])
    wiping = lambda item: any(e.get("type") == ms.DUSTVILLE_DISCO_WANTED_EVENT
                              and e.get("count", 0) > 0 for e in item.intent_events)
    old = next(item for item in candidates if
        item.candidate.start == tuple(frame["best_move"]["start"]) and
        item.candidate.target == tuple(frame["best_move"]["target"]))
    assert old.disco_moves > 0 and wiping(old)
    assert any(item.disco_moves > 0 and not wiping(item) for item in candidates)
    ranked = ms.prioritize_ranked_moves(candidates,
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"], **states)
    assert ranked and all(not wiping(item) for item in ranked)


@pytest.mark.parametrize("run_suffix", ("11-23-21_087", "11-23-28_375"))
def test_disco_first_wave_wanted_shots_do_not_count_as_charge(run_suffix):
    run = Path(__file__).resolve().parents[1] / "Debug/runs" / f"2026-11-07_{run_suffix}"
    if not run.is_dir():
        pytest.skip("recorded Dustville run not present")
    frame = json.loads((run / "move.json").read_text(encoding="utf-8"))
    observed = json.loads((run / "observed_delta.json").read_text(encoding="utf-8"))
    assert observed["state_delta"]["booster_charge_gained"] == 0
    assert any(e.get("type") == "dustville_wanted_shots" and e.get("cascade") == 1
               for e in frame["best_move"]["intent_events"])
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"],
        mode=states["mode"], score_rally_values=states["score_rally_values"],
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"],
        strategy_context=states["strategy_context"])
    filtered = ms._without_dustville_wasting_discos(
        candidates, states["mode"], states["strategy_context"])
    assert len(filtered) < len(candidates)
    assert any(item.disco_moves > 0 for item in filtered)
    assert all(not (item.disco_moves > 0 and any(
        e.get("type") == "dustville_wanted_shots" and e.get("cascade") == 1
        for e in item.intent_events)) for item in filtered)


def test_disco_later_cascade_wanted_shots_still_charge():
    run = Path(__file__).resolve().parents[1] / "Debug/runs/2026-11-07_11-23-03_019"
    if not run.is_dir():
        pytest.skip("recorded Dustville run not present")
    frame = json.loads((run / "move.json").read_text(encoding="utf-8"))
    states = build_states(frame)
    candidates = ms.rank_moves(frame["board"], frame["special_board"],
        mode=states["mode"], score_rally_values=states["score_rally_values"],
        allow_square_matches=frame["allow_square_matches"],
        explode_created_specials_immediately=frame["specials_explode_immediately"],
        strategy_context=states["strategy_context"])
    filtered = ms._without_dustville_wasting_discos(
        candidates, states["mode"], states["strategy_context"])
    assert any(item.disco_moves > 0 and item.mode_targets >= 2
               and any(e.get("type") == "mode_target_collect" and e.get("cascade") == 2
                       for e in item.intent_events) for item in filtered)
