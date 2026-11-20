"""Showdown: the carried plan's next action is played while the board still animates.

Mid-animation the planner refused every swipe and the bot's own pick broke the
line (Showdown 2026-11-20 00:38-00:50: 5-7 of 17-19 swipes planned).
Board: Froggy Showdown research 20261120_001230, record 003.
"""
import copy
from pathlib import Path

import square_solo_live as sl
from strategy_lab import planner
from tools.analyze_research import load
from tools.best_line_search import start_state
from tools.replay_one_to_one import recorded_action

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "race_ahead"


def _setup():
    record, capture = load(FIXTURES / "board.json")
    following, _ = load(FIXTURES / "next.json")
    action, _ = recorded_action(following)
    live = sl.LiveSquareSolo()
    live.carry_after = start_state(record, capture)
    live.carry = planner.Line({}, [action], [0])
    snapshot = {"board": record["board"], "special_board": record["special_board"],
                "state": copy.deepcopy(record["snapshot_state"]), "stable": False}
    return live, snapshot, action


def test_predicted_board_gets_the_next_action_before_rest():
    live, snapshot, action = _setup()
    outcome = live._carried_ahead(snapshot)
    assert outcome["move"]["start"] == tuple(action["start"])
    assert outcome["move"]["target"] == tuple(action["target"])
    assert live.carry.actions == []                  # the line moved on by one
    assert live._carried_ahead(snapshot) is outcome  # asked again: same answer, line not moved twice
    resting = dict(snapshot, stable=True)
    resting["state"] = dict(snapshot["state"], chain_reaction=False, game_state=sl.WAITING_FOR_INPUT)
    assert live._carried_ahead(resting) is outcome   # and once it rests: no fresh plan breaks the line


def test_other_board_or_rest_falls_back_to_plan():
    live, snapshot, _ = _setup()
    other = copy.deepcopy(snapshot)
    other["board"][0][0] = 1 if other["board"][0][0] != 1 else 2   # one piece of another colour
    assert live._carried_ahead(other) is None
    solo = copy.deepcopy(snapshot)
    solo["state"]["rules"]["pvp_mode"] = 1          # Solo Challenge: its own long plan
    assert live._carried_ahead(solo) is None


def test_planned_move_is_reported_as_using_the_drop():
    """A planner move skips the bot's late refill check; that is no "not used"."""
    from types import SimpleNamespace as NS

    import memory_gui
    from refill_monitor import RefillTally

    sent = []
    window = NS(_reader_signals=NS(refill=NS(emit=sent.append)))
    memory_gui.MemoryWindow._report_exact_refill(window, None, "bot nije stigao do izbora poteza", planned=True)
    assert sent[-1]["usage"]["active"] and sent[-1]["usage"]["reason"] is None
    tally = RefillTally()
    tally.add(sent[-1])
    assert "RADI" in tally.usage_text()


def test_timed_race_line_counts_only_swipes_the_clock_allows():
    from strategy_lab.planner import Line, _rank

    state = {"score": 100, "turn_state": {"remaining_moves": 6}, "rank_move_value": 10.0,
             "action_seconds": {"swap": 4.0}}
    assert _rank(Line(dict(state))) == 100 + 6 * 10            # untimed: every move in hand
    assert _rank(Line(dict(state, time_left=9.0))) == 100 + 2 * 10   # 9 s: two swipes
    assert _rank(Line(dict(state, time_left=0.0))) == 100


def test_planner_move_is_recognised_from_its_result():
    """The result has no decision gate: the planner's label marks its moves
    (live 2026-11-20 03:47, every planned swipe reported "nije stigao")."""
    import memory_gui
    import runtime

    planned = runtime.CheckBestMoveResult(best_move_text=runtime.ENGINE_PLAN_LABEL + "Best Move: (2, 2), down",
                                          score_text="")
    own = runtime.CheckBestMoveResult(best_move_text="[dopuna: extra] Best Move: (2, 2), down", score_text="")
    assert memory_gui._planned_by_engine(planned)
    assert not memory_gui._planned_by_engine(own)


def test_answered_board_counts_as_settled_without_a_second_poll():
    """Two equal 50 ms polls make a board stable; a board the race plan already
    predicted and answered can be played on the first one (memory_gui
    _update_auto_plan, with the engine's move phase open)."""
    live, snapshot, _ = _setup()
    assert not live.predicted_now(snapshot)          # nothing answered yet
    live._carried_ahead(snapshot)
    assert live.predicted_now(snapshot)
    other = copy.deepcopy(snapshot)
    other["board"][0][0] = 1 if other["board"][0][0] != 1 else 2
    assert not live.predicted_now(other)


def test_versus_plays_a_predicted_board_at_rest_too():
    """Versus computes only at rest: the predicted board needs no profile read."""
    live, snapshot, action = _setup()
    resting = dict(snapshot, stable=True)
    resting["state"] = dict(snapshot["state"], chain_reaction=False, game_state=sl.WAITING_FOR_INPUT,
                            rules=dict(snapshot["state"]["rules"], pvp_mode=0))
    outcome = live._carried_ahead(resting)
    assert outcome is not None and outcome["move"]["start"] == tuple(action["start"])
