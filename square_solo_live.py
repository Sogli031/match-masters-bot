"""Square Match Solo inside Memory GUI: exact refill from live memory.

Before each move the reader's agent returns the match profile (rules, spawn
weights, overrides, engine RNG; tools/matchmasters_board_dump.ts matchProfile)
and the ported RefillSlots (engine_refill) turns it into a model that knows
what drops after every swipe. strategy_lab.planner then searches to the last
move with it, the same search square_solo_gui.py validated on recorded
transitions. Charles plans also model the booster and supported perks.

Every planned move carries its predicted result, and the next board checks
it. A miss on a board the plan actually played turns the planner off for the
rest of the match, so a wrong model can only cost one move.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

PLAN_SECONDS = 6.0
WAITING_FOR_INPUT = -5  # GameLogic.currentGameState at rest
PROFILE_SETTLE_SECONDS = 1.0
BILLIE_DRONE = 14       # move_strategy.SPECIAL_BILLIE_DRONE
# Leave this much of a running turn clock for the swipe itself.
CLOCK_RESERVE_SECONDS = 4.0


def _grid(board) -> list[list[int]]:
    """Plain int rows: the simulator hands back numpy arrays, the reader lists."""
    return [[int(v) for v in row] for row in board]


CHECKMATE_CHARLES = 54
WOOLLY_WORKOUT = 35
FOXY_ROXY_SE = 52
# Boosters the exact plan plays itself (timing, and Woolly's colour): both
# replay exactly. Woolly, Square Match research 2026-11-14 (8 games): 23 of 24
# activations and 80 of 82 swipes exact (refill_monitor.check_transition).
# Foxy Roxy SE (2026-11-17): Color Climb research 20261117_155242, the whole
# game replayed in a chain from the first board (7 activations with their
# cans, 8 sprays, swaps and perks: board, specials, RNG, moves, energy and
# score), engine_foxy.
# Froggy Fu (2026-11-18): Bombs Away research 20261118_103045, all 12
# activations (the entrance attempt, its settle and the lotuses: board,
# specials, RNG, moves and score), engine_froggy_placement; the swaps that
# collect the lotuses replayed before.
FROGGY_FU = 63
# Brocco Boogie (2026-11-18): research 20261113-20261118 (Mutation Lab, Candy
# World, Funky Tiles, Multiplier Mushrooms, Color Crush), 146 of 147
# activations (the six destroyed pieces, the settle and the two disco balls:
# board, specials and RNG), engine_brocco. The miss is Color Crush 153729
# 003->004 (the game drew 244 more, cause not found).
BROCCO_BOOGIE = 44
# Sweep It SE (2026-11-19): Lightning Strike research 20261119_031206, 4 of 4
# activations (the two-colour sweep picked on clones, its settle and the
# broom: board, specials, RNG and score), engine_sweep; 009 and 014 replayed
# with the swipe in the same capture. Each activation cuts the energy colour's
# refill weight (simulation.booster_energy_weight).
SWEEP_IT_SE = 61
# Monkey JooJoo (2026-11-20): Super Sized research 20261120_111530, 10 of 10
# usable activations (006->007 spans two activations), engine_monkey; the
# auto-explode shuffles the thrown skulls first (b__0 0x5f0af1c, build 5.900).
MONKEY_JOOJOO = 40
EXACT_PLAN_BOOSTERS = frozenset((CHECKMATE_CHARLES, WOOLLY_WORKOUT, FOXY_ROXY_SE, FROGGY_FU, BROCCO_BOOGIE,
                                 SWEEP_IT_SE, MONKEY_JOOJOO))
# Boosters planned with Charles's whole-turn policy: a move in hand priced in
# the beam (CHARLES_MOVE_VALUE), the turn clock capping the line and the
# background replan as the per-action search. The booster costs no move for
# both, so a line keeps the moves it frees. Woolly keeps the plain plan.
CHARLES_POLICY_BOOSTERS = frozenset((CHECKMATE_CHARLES, FOXY_ROXY_SE, FROGGY_FU, BROCCO_BOOGIE, SWEEP_IT_SE))
# Points one Charles activation brought, measured 2026-11-14: Super Sized
# research 20261114_172725 (7 activations, mean 49) and Square Match
# 20261114_230724 (5, mean 38); an average swap there gave 43 and 36. The
# activation costs no move, so a full meter is worth about one free move.
CHARLES_FIRE_VALUE = 44
# The plan runs before every Charles move; 6 s each made Color Crush moves take
# 10-15 s. 2.5 s finished only the width-1 pass on the recorded Charles boards,
# so the player chose 5 s (2026-11-14); the plan is anytime.
CHARLES_PLAN_SECONDS = 5.0
# Showdown / Party (Rumble) and Versus: the player (2026-11-19) wants the
# planner there too, but thinking briefly. One short anytime search per move,
# no carried line, background replan or held booster: the race clock and the
# opponent's turns make the long Solo policy pointless.
QUICK_PLAN_SECONDS = 1.5
# The player (2026-11-19, Versus Mighty Mushrooms, 19 s a turn of 2 moves):
# think 5-10 s at the turn's first move, then play that line through the
# turn (a later move searches QUICK_PLAN_SECONDS and keeps the line unless
# it finds better). Research 20261119_154842 turn start 002: 1.5 s found
# +23, 6 s +41 (a 7-action line of extra moves).
QUICK_TURN_START_SECONDS = 6.0
# Versus on a multiplier board: one point of our multiplier is worth this
# many raw points in each of our turns still to come. Research 20261119
# 154842 / 160107: 9-107 raw points a turn, ~50 typical. The turn-only plan
# lost 1600 : 2015 (our x13 against x16, x6 against x11 after round 2).
VERSUS_RAW_POINTS_PER_TURN = 50
# One activation of our booster in Versus (research 20261119, 12 activations
# of All Aboard, Lightsabers and booster 28/37): 9-40 raw points, ~20
# typical, at the multiplier, and the multiplier up by 0-4 (~1).
VERSUS_BOOSTER_RAW_POINTS = 20
VERSUS_BOOSTER_MULTIPLIER_GAIN = 1
# Versus, the turn's first move: our best lines are weighed against the
# opponent's best reply on the board each leaves (the board is shared).
# Research 20261119_165823 board 17: two lines worth 400 to us left the
# opponent 1097 and 460; one worth 356 left 225. Our turn searches in
# 0.1-0.3 s, so the replies use the rest of QUICK_TURN_START_SECONDS.
VERSUS_REPLY_LINES = 15
VERSUS_REPLY_WIDTH = 10
# Our turn's own search gets at most this long (whole in under 0.5 s on the
# recorded boards), the replies the rest up to the deadline after the start.
# The player (2026-11-19 17:20): still slow at 5 s (a turn's first swipe 8 s
# after its start); width 10 and 2.5 s keep the recorded choices.
# 1.0 s reached width 1 on Mighty Mushrooms boards (2026-11-20 04:11-04:22,
# "sirina 4 (~3 s) ne stize"): greedy lines the player called odd moves. The
# search time is its own now (the profile read is not counted), paid once a
# round; the round's other moves play ahead (_carried_ahead).
# Player, 2026-11-20: like the Showdown start, wait for a good plan. Versus
# scores by moves, its clock barely runs through animations, so the search
# widens while a wider pass gains anything (VERSUS_FIRST_RULE), up to this and
# never past the round clock (budget: turn clock less reserve and the read).
# 10 s was never used (width 4 2.8 s, width 10 ~9 s on Mighty Mushrooms), but
# with the replies a round start took 6.7-7.0 s and was too slow (04:44-04:45).
VERSUS_TURN_SEARCH_SECONDS = 3.0
VERSUS_FIRST_RULE = {"min_width": 0, "min_points": 1}
# Showdown / Rumble / Party (pvp_mode 2): a race against the clock, so the
# turn start and later moves think shorter than Versus (player, 2026-11-19:
# "sto brze"). The plan is anytime; the best line found so far is played.
# 2.5 s reached width 1 on every first plan of the 01:17 Showdown, too narrow
# to play (RACE_MIN_WIDTH): the bot played instead, broke the line, and the
# next first plan was width 1 again. Width 10 took 0.6-1.2 s in game and keeps
# the line going through the boosters (plan unapred); 5 s is paid once.
# 25 s waited 10 s and more at the start, nearly losing races (player,
# 2026-11-20): 8 s at most.
RACE_TURN_START_SECONDS = 8.0
# Player, 2026-11-20: wait at the start until the plan is good. The first race
# plan widens while the last widening gained more than the clock the next one
# costs (planner.stop_reason clock_seconds; each pass plans on the clock left
# after the search); 25 s is only the fence.
RACE_PLAN_SECONDS = 1.0
# The race line counts the turn clock as well as the move counter (planner
# time_left): seconds per action on the game clock, Froggy Showdown research
# 20261120_001230; Remove Cross and Energy Boost re-measured
# 2026-11-20 on 19 Showdowns (means, the clock pays the sum: 6.2 and 4.2 s, swipe
# 3.87, booster 7.9). Without the clock a line ran its moves out fast:
# 2026-11-20 00:57:58, 6 moves gone at 78 of 104 s, 26 s unused.
RACE_ACTION_SECONDS = {"swap": 3.9, "booster": 8.0, "remove_cross": 6.2, "energy_boost": 4.2, "teleport": 3.9}
# Race background replan (_start_race_background): a wider search from the
# board this many carried actions ahead, with the share of their clock it may
# take; the line switches when it is done and better by then, never waited for.
# The first plan reaches width 4 live, the best lines came at width 25-150 on
# the recorded Showdowns (tools/best_line_search: 1727-1899 against 1133-1357).
RACE_BG_AHEAD = 3
RACE_BG_SHARE = 0.7


def _timed_after(before, action, after):
    """``after`` with the turn clock the action took (planner.time_left)."""
    if "time_left" not in before:
        return after
    from strategy_lab.planner import _action_seconds
    return dict(after, time_left=float(before["time_left"]) - _action_seconds(before, action))


# A race first plan narrower than this is not played: width 1 is greedy and
# ran the moves out with 29-57 s of clock unused on all three recorded
# Showdown starts (1021 / 483 / 458 points against 1356-1584 at width 10);
# the bot's own ranking keeps its moves with extras instead.
RACE_MIN_WIDTH = 4
# The opponent's replies after our own search (versus_counter_choice); 2.5 s
# made the round start 6.7-7.0 s with the search (2026-11-20 04:44-04:45).
VERSUS_REPLY_DEADLINE_SECONDS = 1.0
# Off: the opponent's board comes from the round-end refill, which the
# simulator does not yet replay (Mighty Mushrooms 2026-11-20: 6 round ends
# need the turn-end thresholds, 3 do not, cause unread). Priced on that guess
# the plan played 3-point "denial" moves to end both rounds (05:20:41,
# 05:21:29) and the opponent still went x1 -> x11 and x10 -> x19.
VERSUS_COUNTER_CHOICE = False


def versus_reply_follows(state: dict | None) -> bool:
    """Versus, and the opponent still has a turn after ours."""
    state = state or {}
    turn = state.get("current_turn")
    return (state.get("rules") or {}).get("pvp_mode") == 0 and isinstance(turn, int) and turn > 1


def versus_reply_value(line_state, state, moves, width=VERSUS_REPLY_WIDTH):
    """The opponent's best next turn on the board a line of ours leaves, in
    the same units as our line's value (points, plus multiplier points at
    VERSUS_RAW_POINTS_PER_TURN for each of their later turns)."""
    from strategy_lab import planner

    opponent = next((p for p in state.get("players") or () if p.get("player_type") != 0), {})
    later = versus_turns_after({"current_turn": int(state["current_turn"]) - 1})
    reply = dict(line_state, turn_state={"remaining_moves": moves, "max_moves": moves}, score=0,
                 score_multiplier=max(1, int(opponent.get("score_multiplier") or 1)),
                 multiplier_value=VERSUS_RAW_POINTS_PER_TURN * later, perks={}, booster_fired=0,
                 booster_state={"current": 0, "maximum": None}, booster_fire_value=None,
                 rank_move_value=None, booster_auto=False)
    best, _ = planner.plan(reply, width=width, max_steps=4 * moves)
    return best.value - planner.Line(reply).value


def versus_counter_choice(lab, state, lines, best, deadline):
    """(line, note): of our best finished lines, the one with the most
    value to us less the opponent's best reply; ``best`` when nothing beats it."""
    from strategy_lab import planner

    moves = (lab.get("turn_state") or {}).get("max_moves") or 2
    base = planner.Line(lab).value
    seen, candidates = set(), []
    for line in sorted(list(lines) + [best], key=lambda l: l.value, reverse=True):
        key = planner._key(line.state)
        if line.actions and key not in seen:
            seen.add(key)
            candidates.append(line)
    rows = []
    for line in candidates[:VERSUS_REPLY_LINES]:
        if rows and time.monotonic() > deadline:
            break
        rows.append((line.value - base - versus_reply_value(line.state, state, moves), line))
    if not rows:
        return best, None
    net, chosen = max(rows, key=lambda row: row[0])
    first = next((n for n, l in rows if l is best or planner._key(l.state) == planner._key(best.state)), None)
    note = (f"odgovor protivnika: {len(rows)} linija, izabrana neto {net:.0f}"
            + (f" (najbolja po poenima neto {first:.0f})" if first is not None and chosen is not best else ""))
    return chosen, note


def versus_turns_after(state: dict | None) -> int:
    """Our Versus turns after this one: currentTurn counts every player's turn
    down to 1 (ours 7, 5, 3, 1 of 8; 5, 3, 1 of 6)."""
    turn = (state or {}).get("current_turn")
    return max(0, (int(turn) - 1) // 2) if isinstance(turn, int) else 0
# Live policy, replayed on the exact simulator 2026-11-15 (research 233705,
# 232927, 230724): a 60 s first plan, then 10 s per action keeping the
# previous line unless beaten, scored 1871 / 1708 / ~1726 against the bot's
# 1227 / 2076 (with two perks) / 1134; 5 s from scratch each action gave
# 626 / 893 / 911. A Solo turn has 1500 s.
# One fresh plan that may hold a full booster (planner booster_hold; it can
# still fire at once, so it covers the at-once lines). tools/plan_width_curve
# 2026-11-15 01:45, 14 Charles games, each width run to the end: at once
# 24708 / 26319 / 29854 at width 10 / 25 / 60, holding 21474 / 29013 / 33170
# (width 60 median 173 s, longest 368 s, 12 processes beside the game). The
# old 60 + 60 s stopped at width 10 (~26090); the player chose 5 minutes,
# then (with the replans every 3 actions, +12.4 %) a shorter wait: 150 s
# still finishes width 25 (live 02:05: widths 1-25 done well inside 300 s),
# and the replans make up the rest.
# Since 2026-11-17 the first plan has no fixed time: it searches until a
# wider pass brings nothing (planner.STOP_RULE) or the turn clock would no
# longer leave time to play its best line (plan_anytime clock); this is only
# the fence against an excessive wait (the player: "as long as it needs, but
# not excessive"). Measured (tools/plan_stop_curve, Debug/plan_stop_curve.txt,
# 41 first boards): the 150 s fence scored 462764 in 3389 s, 300 s +17.5 %
# for +151 s per game; widths keep paying up to 60 (+12 % median), which a
# Charles first board reaches in ~470 s, Foxy Roxy SE in ~35-60 s.
CHARLES_FIRST_SECONDS = 600.0
# The player (2026-11-17): the whole match, every plan and the play, has to
# fit in 15 minutes, or in the challenge turn clock when that ends first.
# Every plan of the Charles-policy boosters (the first one and the background
# replans) searches until it stops paying or until what is left of this time
# would no longer play its best line (LiveSquareSolo._time_left,
# planner.plan_anytime clock); a background replan is no longer cut by its
# own short time, the bot waits for it -- but only as long as the carried
# line still plays to its end after the wait (2026-11-18,
# LiveSquareSolo._start_background).
MATCH_PLAN_SECONDS = 900.0
# The first plan runs this one width: the narrower ones only lose
# (tools/plan_stop_curve 2026-11-17, 41 first boards: 4 beat 1 on 41, 10
# beat 4 on 37, 25 beat 10 on 39). The player (2026-11-19): 25 for a quick
# start, the background replans up to 60 from the first move (before, 60
# only over the last 6 moves). Vertical Rush + Sweep 12:46: the width-60
# replans raised a 39026 line to 236786; Debug/plan_check 13:30, lines
# priced at the multiplier: width 25 1037806, 60 976333 from the first board
# (60 took twice as long, and the turn clock runs while the bot plans).
# The player (2026-11-19 18:40): the replans too only up to 25 (60 took
# ~10 min and did not beat 25 at the multiplier).
FIRST_MAX_WIDTH = 25
BG_MAX_WIDTH = 25
# The first plan looks this many actions ahead (the player, 2026-11-19): at
# 4 s an action the turn clock held ~370, and a width-25 Sweep plan of that
# length kept the bot waiting over 4 minutes while the game's clock ran;
# 100 actions still took 136 s on a Sweep board, so 50.
FIRST_PLAN_STEPS = 50
# Solo (a refill booster, not Charles) plans this far ahead: 60 actions. The
# search used to take the planner's 300, and a Solo Challenge's refill chain
# makes such a line exist: 2026-11-20 03:09:57 the background plan priced 293
# actions at 12360 against the carried line's 2408 for 50, so it won on length
# alone, and the match it was measured against ended at 2832. 60 actions is
# over a turn of moves (10) with the refills the match actually delivers: the
# median Solo Challenge match in Debug/runs (scored segments, 2026-11-10 on)
# is 51 moves, 96 at the 75th percentile. The bot replans every few actions,
# so the tail beyond this is not lost, only not priced.
SOLO_PLAN_STEPS = 60
# 10 s at first; the carried line was kept on 97 of 102 replayed actions and on
# every live action of the first game (2026-11-15 00:06), so the per-move
# search is short: the player found 10 s per move too slow.
CHARLES_NEXT_SECONDS = 2.0
# Every few actions of a carried line, a full search again from the current
# board, kept only if it beats the line. tools/replan_compare 2026-11-15
# 02:55, 16 Charles games, first plan width 60, then width 25 every 3
# actions: 36983 -> 41565 (+12.4 %), 9 games better, none worse; a replan
# took 25-90 s at first, under 1 s near the end (12 processes busy).
# The replan runs in a worker process from the board the carried line
# reaches CHARLES_BG_AHEAD actions later (the refill is exact, so that board
# is known), while the bot plays those actions: the player found a 60 s
# stop every 3 actions too long (2026-11-15 03:20).
# Live 2026-11-15 15:23 and 16:08 (plans of 100-121 actions, a move in hand
# priced): 4 actions ahead and 40 s never finished a pass while the line was
# long (width 25 cut on 14 and 18 replans in a row, the cut line at about
# half the carried score), and the bot waited for them 10 and 18 times (58
# and 126 s). So the replan looks further ahead while the line is long (an
# eighth of it, 4 to CHARLES_BG_AHEAD_MAX actions), searches for the time
# those actions take to play (8 s each in those games) and starts at the
# first plan's own width, the one a pass is known to finish (LiveSquareSolo.
# bg_width). Not measured yet: a time-true replay of the replans is hours.
CHARLES_BG_AHEAD = 4
CHARLES_BG_AHEAD_MAX = 10
CHARLES_BG_ACTION_SECONDS = 7.5
# What a background replan looks at when the bot has no clock-derived step
# count: Charles takes its line to the end, a solo plan stops at
# SOLO_PLAN_STEPS (exact planner 2026-11-20: a 293-action line scored 12360).
# The player (2026-11-20): the background replans took too long (live
# 2026-11-20 06:07 a width-25 pass ran 281 s while the bot waited for it).
# Every replan now runs at one width, 25 (BG_MAX_WIDTH, the widest the measured
# curve pays up to), and is fenced at BG_PLAN_SECONDS; its horizon is chosen so
# the pass fits that fence, and both lines are compared over the horizon the
# replan looked at.
BG_PLAN_SECONDS = 15.0
# Without a measured pace yet (the first plan's pass gives it): look this far.
BG_FALLBACK_STEPS = 15
# Vegas Views: the tile comes back on a new cell after the move that destroys
# it, and the simulator does not model that conversion or its engine draws, so
# such a move starts a fresh first plan (live 2026-11-20 07:14-07:15: 54 s and
# 58 s). Width 25 stays; the first plan looks this far instead of 50.
VEGAS_FIRST_STEPS = 20
# A plan restarted mid-match (the board was not the one the last plan
# predicted: a Vegas tile, a Froggy lotus that came out differently) is not
# the match's first plan. It is searched briefly, with the widths that fit,
# instead of a fresh whole-match plan -- live 2026-11-20 Froggy Fu sat 75 s on
# such a restart (the player: "nekad uspe da pogodi nekad ne zato se
# resetuje"). The background replans carry the line on from there.
# The player (2026-11-20): longer. Column Mania 09:56 the 15 s restart reached
# width 4 (+614 over 20 actions); width 25 on that board gave +1389.
RESTART_PLAN_SECONDS = 50.0
# Solo with flag refills (soloRefillMode): the beam prices a move in hand at
# this many points (planner._rank; the line is still chosen by its score).
# tools/solo_move_value_check 2026-11-20, width 25 to the end, 8 boards a mode
# (score gained at price 0 / 200 / 400 / 800): Column Mania 7624 / 11614 /
# 11982 / 13665, Crazy Columns 9916 / 13314 / 13820 / 13820, Mutation Lab
# 3995 / 11102 / 11102 / 11059, Score Market 3491 / 4433 x3, Funky Tiles ML
# 2122 / 2651 x3, Super Sized (3) 814 / 1673 / 1588 / 1810; worse on 1 board
# of 43. Unpriced, the beam spent moves for points and the match ran out.
SOLO_MOVE_VALUE = 400
RESTART_PLAN_STEPS = 20
BG_PLAN_STEPS = 300


def _bg_ahead(actions_left: int) -> int:
    """How many carried actions ahead the background replan starts."""
    return min(CHARLES_BG_AHEAD_MAX, max(CHARLES_BG_AHEAD, actions_left // 8))
# What a move still in hand counts for when the beam picks its lines
# (planner._rank, rank_move_value). tools/plan_width_curve --move-prices
# 2026-11-15, 23 Charles games, first board, booster held, width 10: price 0
# 36081 points in all, 60 96556, 80 118373, 100 143470, 140 142784. The lines
# keep the moves a booster or a +1 cascade leaves, so the plans grow from 25
# to 112 actions on average (201 at most). Charles only: Woolly is not measured.
CHARLES_MOVE_VALUE = 100
# Such a plan can outlast the turn clock (1500 s; live 2026-11-15 05:25 the
# first board had 1074 s left), so a line gets only the actions the clock
# allows. The cap costs points (--max-steps, same 23 games, price 100, width
# 10: 90 actions 110697, 130 actions 133799, no cap 143470), so the seconds
# per action matter. One action took 8.8 s in that game (36 actions,
# 05:28:13-05:33:31), 2.1 s of it the per-move search, which is now skipped
# while a background replan is pending (it kept the carried line on all 36
# actions there, and on 97 of 102 replayed ones). About 7 s is expected
# then, not measured live yet; every replan reads the clock again, so an
# estimate that is off is corrected within a few actions.
CHARLES_ACTION_SECONDS = 8.5
# The game's own turn clock stops for animations and boosters: one action
# takes 1-4 s of it (Vertical Rush research 20261119_143212, 20 actions,
# 1.1-4.4 s, one 8.8 s). At 8.5 s the last 21 s held one action, and a full
# booster before the last swipe was cut off (live 14:34:17).
GAME_CLOCK_ACTION_SECONDS = 4.0

_BG_POOL = None
# Every finished planner pass, first plan and background replans alike, goes
# to this callable (memory_gui sets the Qt signal's emit; set_pass_listener).
PASS_LISTENER = None


def set_pass_listener(listener):
    global PASS_LISTENER
    PASS_LISTENER = listener


def _tell(info):
    listener = PASS_LISTENER
    if listener is not None:
        try:
            listener(info)
        except Exception:
            pass


def _drain_passes(queue):
    """Main process: the worker's passes, as they finish, to the listener."""
    while True:
        try:
            info = queue.get()
        except Exception:
            return
        if info is None:
            return
        _tell(info)


def _background_pool():
    """One worker process for the background replans, kept across matches.

    Its passes come back through a queue the worker gets at start (a plain
    multiprocessing queue cannot go with each task), read by a daemon thread.
    """
    global _BG_POOL
    if _BG_POOL is None:
        import multiprocessing
        import threading
        from concurrent.futures import ProcessPoolExecutor
        from strategy_lab import planner

        queue = multiprocessing.Queue()
        _BG_POOL = ProcessPoolExecutor(max_workers=1, initializer=planner.set_pass_queue, initargs=(queue,))
        threading.Thread(target=_drain_passes, args=(queue,), name="planner-passes", daemon=True).start()
    return _BG_POOL


def _replay_line(state, actions):
    """The background plan's actions replayed on this process's own state."""
    from strategy_lab import planner
    from strategy_lab.simulation import step

    gains = []
    for action in actions:
        result = step(state, action)
        if not result.get("supported"):
            return None
        state = result["state"]
        gains.append(result.get("score_gain"))
    return planner.Line(state, list(actions), gains)


SWEEP_BROOM_SPECIAL = 45
OPPOSITE = {"left": "right", "right": "left", "up": "down", "down": "up"}


def broom_first(special_board, move):
    """A swipe onto a Sweep It SE broom drags the broom instead: the game
    swallowed a piece dragged onto it (live 2026-11-19 04:27, eight tries of
    (3,5) -> (3,6)) and took the broom dragged back (the same outcome, the
    simulator plays both ends alike); 9 of 9 recorded broom swipes start on it."""
    (r1, c1), (r2, c2) = move["start"], move["target"]
    if (move.get("kind", "swap") == "swap" and move.get("direction") in OPPOSITE
            and special_board[r2][c2] == SWEEP_BROOM_SPECIAL and special_board[r1][c1] != SWEEP_BROOM_SPECIAL):
        return dict(move, start=move["target"], target=move["start"], direction=OPPOSITE[move["direction"]])
    return move


def _ahead_key(snapshot):
    """What _carried_ahead matches a snapshot on: board, specials, moves, charge."""
    state = snapshot.get("state") or {}
    me = next((p for p in state.get("players") or () if p.get("player_type") == 0), {})
    return (str(_grid(snapshot["board"])), str(_grid(snapshot["special_board"])),
            state.get("moves"), me.get("energy"))


def _plan_key(state):
    """Match the board and the resources the remaining plan depends on."""
    charge = state.get("booster_state") or {}
    return (str(_grid(state["board"])), str(_grid(state["special_board"])),
            state["engine_refill"].rng.counter, (state.get("turn_state") or {}).get("remaining_moves"),
            charge.get("current"), charge.get("maximum"), _perk_inventory_key(state.get("perks")),
            tuple(state.get("column_multipliers") or ()))


PLAN_KEY_NAMES = ("tabla", "specijali", "RNG", "potezi", "punjenje boostera", "max punjenja",
                  "perkovi", "mnozioci kolona")


def _replayable(predicted, actual) -> bool:
    """Two _plan_key tuples with the same board, specials, RNG and perks that
    differ only in what a replay recomputes: the booster's charge, the Column
    Mania multipliers, or more moves than predicted.

    Column Mania 2026-11-20 09:56-09:57: the line carried stale multipliers
    (x1 where the game had x2) and so priced its moves low; a booster then
    reached the 1000 flag the line did not (moves 3 -> 5) and the line was
    dropped for a width-4 restart. Fewer moves than predicted is not replayed:
    the line may run past the turn's end.
    """
    if predicted is None or actual is None or len(predicted) != len(actual) or predicted == actual:
        return False
    moves_ok = predicted[3] == actual[3] or (
        predicted[3] is not None and actual[3] is not None and actual[3] > predicted[3])
    return predicted[:3] == actual[:3] and predicted[5:7] == actual[5:7] and moves_ok


def _perk_inventory_key(perks):
    return tuple(sorted((perk, count) for perk, count in (perks or {}).items() if count > 0))


def charles_booster(state: dict | None) -> bool:
    """The local player's booster is Checkmate Charles (snapshot state)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") == CHECKMATE_CHARLES
               for p in (state or {}).get("players") or [])


def charles_policy_booster(state: dict | None) -> bool:
    """The local player's booster plays Charles's policy (Charles, Foxy Roxy SE)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") in CHARLES_POLICY_BOOSTERS
               for p in (state or {}).get("players") or [])


def exact_plan_booster(state: dict | None) -> bool:
    """The local player's booster is one the exact plan plays (Charles, Woolly)."""
    return any(p.get("player_type") == 0 and p.get("special_ability_type") in EXACT_PLAN_BOOSTERS
               for p in (state or {}).get("players") or [])


def quick_plan(state: dict | None) -> bool:
    """Showdown / Party (Rumble) or Versus: plan briefly (QUICK_PLAN_SECONDS)."""
    return ((state or {}).get("rules") or {}).get("pvp_mode") in (0, 2)   # PvP, Rumble


def race_plan(state: dict | None) -> bool:
    """Showdown / Rumble / Party: the timed race, planned with RACE_* seconds."""
    return ((state or {}).get("rules") or {}).get("pvp_mode") == 2


def charles_eligible(state: dict | None) -> bool:
    """A booster the exact plan plays: Solo with the long plan, Showdown /
    Versus with the quick one (quick_plan).

    Charles moves replay exactly (research 20261114_172725 Super Sized 22 of
    23, the other one a gap; 20261114_230724 Square Match 6 of 6). An arena the
    planner cannot simulate returns no move and the bot's own pick stays.
    """
    return exact_plan_booster(state)


BOOSTER_NAMES = {CHECKMATE_CHARLES: "Checkmate Charles", WOOLLY_WORKOUT: "Woolly Workout",
                 FOXY_ROXY_SE: "Foxy Roxy SE", FROGGY_FU: "Froggy Fu", BROCCO_BOOGIE: "Brocco Boogie",
                 SWEEP_IT_SE: "Sweep It SE", MONKEY_JOOJOO: "Monkey JooJoo"}


def planner_support(state: dict | None, mode_value: str | None) -> str | None:
    """Why the exact planner cannot plan this match, or None when it can.

    The planner plays a board (Solo, Showdown or Versus) when our booster's
    activation is ported (EXACT_PLAN_BOOSTERS) and the arena's mode replays
    exactly (strategy_lab.simulation.PREFIX_MODES). The reason names what is
    missing, so a recording can be made for it.
    """
    from strategy_lab.simulation import PREFIX_MODES

    state = state or {}
    rules = state.get("rules") or {}
    missing = []
    local = next((p for p in state.get("players") or () if p.get("player_type") == 0), None)
    booster = (local or {}).get("special_ability_type")
    if booster not in EXACT_PLAN_BOOSTERS and not quick_plan(state):
        # Versus / Showdown: the plan plays the swipes only (planner.actions
        # adds no booster it cannot replay) and the bot keeps firing it.
        name = (local or {}).get("special_ability_name") or f"tip {booster}"
        missing.append(f"booster {name} nije podrzan")
    if mode_value not in PREFIX_MODES:
        missing.append(f"mod {rules.get('id') or mode_value} nije podrzan")
    return "; ".join(missing) or None


def eligible(rules: dict | None) -> bool:
    rules = rules or {}
    return ((rules.get("id") in ("square-match", "color-crush") and rules.get("pvp_mode") == 1)
            or (rules.get("id") == "rainbow" and rules.get("pvp_mode") == 2))


def _ball_slots(snapshot):
    """Colourless pieces with the colour the slot keeps under them; the board shows only 99.

    Disco balls (26, 28), Foxy Roxy (31), Cleo (32) and the Sweep SE broom (38); EngineRefill keeps the last
    two only where Match & Hatch's random specials are ported."""
    return [{"row": slot["row"], "col": slot["col"], "color": slot["color"], "value": slot["value"]}
            for slot in snapshot.get("slots") or [] if slot.get("value") in (26, 28, 31, 32, 38)]


def _profile_players(snapshot, memory_players=None):
    """The snapshot's players as profile players.

    The periodic snapshot leaves ``spawn_bonus`` null; only the manual dump
    reads it. The Versus refill thresholds need it (versus_adaptive_thresholds),
    so a missing index/score/spawnBonus is taken from the memory profile's own
    players (match_profile reads those fields), matched by engine index. Square
    Match Versus 2026-11-10 02:20: every move fell back to the base thresholds
    while the recorder, on the manual dump, called the formula exact.
    """
    players = ((snapshot.get("state") or {}).get("players")) or []
    memory = {}
    for player in memory_players or ():
        model = (player or {}).get("model") or {}
        if type(model.get("index")) is int:
            memory[model["index"]] = model
    out = []
    for player in players:
        if not isinstance(player, dict):
            continue
        out.append({"player_type": player.get("player_type"),
                    "model": {"index": player.get("index"), "slotType": player.get("slot_type"),
                              "score": player.get("score"), "spawnBonus": player.get("spawn_bonus"),
                              "energy": player.get("energy"),
                              "specialAbilityType": player.get("special_ability_type"),
                              "boardAbilities": None},
                    "board_abilities": []})
        model, known = out[-1]["model"], memory.get(player.get("index"))
        for key in ("score", "spawnBonus"):
            if model[key] is None and known is not None:
                model[key] = known.get(key)
    return out


def _resting_profile(reader, script, snapshot):
    """(profile, reason): the memory profile of this snapshot's board at rest.

    The move waits for this: the engine gets PROFILE_SETTLE_SECONDS to finish
    resolving. A board still not at rest gives None.
    """
    state = snapshot.get("state") or {}
    if (not snapshot.get("stable", True) or state.get("chain_reaction")
            or state.get("game_state") not in (None, WAITING_FOR_INPUT)):
        return None, "tabla jos nije mirna"
    deadline = time.monotonic() + PROFILE_SETTLE_SECONDS
    while True:
        try:
            profile = reader.read_profile(script)
        except Exception as exc:
            return None, f"citanje memorije: {exc}"
        live = profile.get("state") or {}
        if (live.get("moves") == state.get("moves") and not live.get("<ChainReaction>k__BackingField")
                and live.get("currentGameState") in (None, WAITING_FOR_INPUT)):
            return copy.copy(profile), None
        if time.monotonic() >= deadline:
            return None, "igra jos razresava potez"
        time.sleep(0.05)


def _cleo_slots(snapshot):
    return [copy.deepcopy(slot) for slot in snapshot.get("slots") or [] if slot.get("value") == 32]


def cleo_odds_profile(reader, script, snapshot):
    """Memory values for the Cleo odds, independent of the exact refill switch.

    None without a figure on the board, or when the board is not at rest or
    could not be read; the ranking then falls back to the config's PvP values.
    """
    slots = _cleo_slots(snapshot)
    if not slots:
        return None
    profile, _reason = _resting_profile(reader, script, snapshot)
    if profile is not None:
        profile["cleo_slots"] = slots
    return profile


def _solo_snapshot_matches_profile(state, profile):
    """An extra or perk can change the RNG without spending a move."""
    live = profile.get("state") or {}
    players = state.get("players") or []
    live_players = profile.get("players") or []
    checks = [
        (state.get("moves"), live.get("moves")),
        (state.get("moves_made_this_turn"), live.get("<MovesMadeThisTurn>k__BackingField")),
    ]
    if len(players) == len(live_players) == 1:
        captured = live_players[0].get("model") or {}
        checks.extend((players[0].get(key), captured.get(key)) for key in ("score", "energy"))
    return all(before is None or after is None or before == after for before, after in checks)


def exact_refill_session(reader, script, snapshot, board, max_plies=None, *, resting_profile=None,
                         validate_solo_state=False):
    """(session, reason) for the ordinary ranking; session None means plain ranking."""
    from engine_refill import EngineRefill, ExactRefillSession, UnsupportedRefill, color_maps

    state = snapshot.get("state") or {}
    if resting_profile is None:
        profile, reason = _resting_profile(reader, script, snapshot)
        if profile is None:
            return None, reason
    else:
        profile = resting_profile.copy()
    if validate_solo_state and not _solo_snapshot_matches_profile(state, profile):
        return None, "Solo: tabla i profil nisu iz istog poteza"
    profile["players"] = _profile_players(snapshot, profile.get("players"))
    profile["ball_slots"] = _ball_slots(snapshot)
    # Loaded logic / board extraData come from the dynamic profile RPC. The
    # display dump's extraData is a limited string view and cannot replace it.
    profile["raw_slots"] = copy.deepcopy(snapshot.get("slots"))
    profile["cleo_slots"] = _cleo_slots(snapshot)
    try:
        hot = None
        fields = snapshot.get("board_fields") or {}
        if fields.get("currHotColor") is not None:
            _, engine_to_sim = color_maps(profile)
            hot = (engine_to_sim.get(fields["currHotColor"]), engine_to_sim.get(fields.get("nextHotColor")))
        try:
            model = EngineRefill.from_profile(profile)
        except UnsupportedRefill as exc:
            # engine_refill.APPROXIMATE_REFILL: a mode the exact port does not
            # cover still gets the live-RNG drop, marked as a guess.
            model = EngineRefill.from_profile(profile, approximate=True)
            model.unported(str(exc))
            if "Special tile" in str(exc):
                _save_special_tile_config(profile)
        from engine_mixy import MixyPassive
        me_state = next((p for p in state.get("players") or [] if p.get("player_type") == 0), {})
        model.mixy = MixyPassive.from_player(me_state, color_maps(profile)[1], profile)
        if any(int(v) == BILLIE_DRONE for row in snapshot.get("special_board") or [] for v in row):
            from engine_billie import BilliePassive
            try:
                model.billie = BilliePassive.from_record({
                    "profile": profile, "snapshot_state": state,
                    "billie_slots": [slot for slot in snapshot.get("slots") or [] if slot.get("value") == 25]})
            except UnsupportedRefill as exc:
                if model.approximate is None:
                    model.approximate = []
                model.unported(str(exc))
        extra = {} if max_plies is None else {"max_plies": max_plies}
        session = ExactRefillSession(model, board, hot=hot, special_board=snapshot.get("special_board"),
                                     follow_moves=len(state.get("players") or []) <= 1, **extra)
        rules = profile.get("rules") or {}
        # Jelly SE is a booster: its zone and uses-left counter
        # (JellySEUsesLeftKeyPlayer0) sit in extraData in every mode, not only
        # Bullseye Bash (Column Mania, Mighty Mushrooms, 2026-11-09). Without
        # them the refill gave up on every move with a zone on the board.
        from board_source import jelly_zone_state

        jelly = jelly_zone_state(snapshot) or {}
        if jelly.get("cells"):
            session.jelly_uses_left = jelly.get("uses_left")
            session.jelly_cells = frozenset(jelly["cells"])
            # The overlay belongs to this capture. A move that leaves the zone
            # alone keeps it on the same cells (research 2026-11-11: 6 of 6),
            # so up to two such moves are followed (ExactRefillSession.finish
            # stops at a conversion); converted boards are not.
            session.max_plies = 2
        session.moves_left = state.get("moves")
        # Solo only: the move counter is the whole match. In versus the charge
        # carries into later rounds, so the counter says nothing about it.
        session.solo = len(state.get("players") or []) <= 1
        me = next((p for p in state.get("players") or [] if p.get("player_type") == 0), {})
        if me.get("energy_full"):
            session.blue_missing = 0
        elif me.get("energy_to_ability") is not None and me.get("energy") is not None:
            session.blue_missing = max(0, me["energy_to_ability"] - me["energy"])
            # Per-colour charge (memory_gui._charge_scale): the ranking counts
            # charge on the BOOSTER_MAX_CHARGE scale, so the room does too.
            from board_source import charging_weights
            weights = charging_weights(snapshot)
            if weights and any(value != 1 for value in weights.values()) and me["energy_to_ability"]:
                from move_strategy import BOOSTER_MAX_CHARGE
                session.blue_missing *= BOOSTER_MAX_CHARGE / float(me["energy_to_ability"])
        return session, None
    except (UnsupportedRefill, KeyError, TypeError, ValueError) as exc:
        if "Special tile" in str(exc):
            _save_special_tile_config(profile)
        return None, str(exc)


# Solo Challenge Teleport (offline, 152 recorded solo boards, 2026-11-09):
# median +24% of the points still to come, best on the first move it can go
# (92 of 145 plans; holding it gained 2.4 points on average, held for the
# last two moves it fell to +17%). Whether one board's Teleport is worth 10%
# is below the search noise, so it is not judged: it goes first, on the pair
# whose exact line to the end of the match scores best.
TELEPORT_PAIR_SECONDS = 15.0     # Solo Challenge: no clock pressure (player, 2026-11-09)
TELEPORT_PAIR_CANDIDATES = 6
PERK_TELEPORT_ENGINE = 3


def teleport_exact_pair(reader, script, snapshot, *, seconds=TELEPORT_PAIR_SECONDS) -> dict:
    """The Teleport pair to play now, from exact plans to the end of the match.

    Returns {"pair": ((r,c),(r,c)) | None, "note": str}; None leaves the
    choice to the bot's own perk ranking.
    """
    from simulator_capture import decode_dictionary, lab_move
    import board_source

    profile, reason = _resting_profile(reader, script, snapshot)
    if profile is None:
        return {"pair": None, "note": f"bez profila: {reason}"}
    state = snapshot.get("state") or {}
    profile["players"] = _profile_players(snapshot, profile.get("players"))
    profile["ball_slots"] = _ball_slots(snapshot)
    score = decode_dictionary((profile.get("rules") or {}).get("_colorScoreOverride")) or {}
    me = next((p for p in state.get("players", []) if p.get("player_type") == 0), {})
    capture = {"profile": profile, "simulator_input": {
        "board": copy.deepcopy(snapshot["board"]), "special_board": copy.deepcopy(snapshot["special_board"]),
        "froggy_params": me.get("special_ability_params"), "booster_cost": me.get("energy_to_ability"),
        "active_mutations": snapshot.get("active_mutations"),
        "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
    try:
        lab = lab_move(capture)
    except Exception as exc:
        return {"pair": None, "note": f"simulator: {type(exc).__name__}: {exc}"}
    return best_teleport_pair(lab, seconds=seconds)


def best_teleport_pair(lab, *, seconds=TELEPORT_PAIR_SECONDS, candidates=TELEPORT_PAIR_CANDIDATES) -> dict:
    """teleport_exact_pair on a ready simulator state (also used offline).

    The ``candidates`` Teleports with the best immediate gain are each played
    out to the end with the exact refill, swipes only after it.
    """
    from strategy_lab import planner, simulation

    with_tp = dict(lab, perks={PERK_TELEPORT_ENGINE: 1})
    # Only the pair is taken from this: every mode the refill covers counts,
    # as in tools/analyze_research.try_transition.
    certified = simulation.PREFIX_MODES
    simulation.PREFIX_MODES = set(certified) | {lab.get("mode")}
    try:
        first_steps = []
        for action in planner.actions(with_tp):
            if action.get("kind") != "teleport":
                continue
            result = simulation.step(with_tp, action)
            if result.get("supported"):
                first_steps.append((result["score_gain"], action, result["state"]))
        first_steps.sort(key=lambda item: item[0], reverse=True)
        best_score, best_action = None, None
        share = seconds / max(1, min(candidates, len(first_steps)))
        for _gain, action, after in first_steps[:candidates]:
            line, _ = planner.plan_anytime(dict(after, perks={}), share)
            if best_score is None or line.score > best_score:
                best_score, best_action = line.score, action
    finally:
        simulation.PREFIX_MODES = certified
    if best_action is None:
        return {"pair": None, "note": "nema podrzanog Teleporta"}
    pair = (tuple(best_action["start"]), tuple(best_action["target"]))
    return {"pair": pair, "note": f"{pair[0]}<->{pair[1]}, plan do kraja {best_score}"}


SPECIAL_TILE_DUMP_DIR = Path(__file__).resolve().parent / "Debug/refill_unsupported"


def _save_special_tile_config(profile) -> None:
    """Once per board model: the special-tile config the refill does not port yet,
    so the next port starts from the game's own numbers, not a guess."""
    try:
        from simulator_capture import decode_dictionary
        board_model = (profile.get("rules") or {}).get("boardModelName")
        target = SPECIAL_TILE_DUMP_DIR / f"special_tiles_board_{board_model}.json"
        if target.exists():
            return
        data = decode_dictionary(profile["spawning"].get("specialTilesData")) or {}
        document = {"boardModelName": board_model,
                    "specialTilesData": {str(k): decode_dictionary(v) if isinstance(v, dict) else v
                                         for k, v in data.items()},
                    "profile": profile}
        SPECIAL_TILE_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:  # Diagnostics only; never stop the move.
        pass


@dataclass
class Expectation:
    signature: object
    action: dict
    board: list
    special_board: list
    rng_counter: int
    lab: dict | None = None     # the state planned from, to identify another move
    capture: dict | None = None  # profile + boards planned from, saved on a miss


@dataclass
class LiveSquareSolo:
    """Per-match state; the GUI keeps one and calls reset() between matches."""
    static: dict | None = None          # rules + config of this GameLogic
    logic_key: str | None = None
    disabled_reason: str | None = None
    expectation: Expectation | None = None
    # The last plan, keyed by board + RNG counter. Memory GUI discards and
    # restarts a computation when its plan key moves (the turn clock ticks
    # while the planner runs), so the same board is asked for again at once.
    cached_key: tuple | None = None
    cached_outcome: dict | None = None
    # Checkmate Charles: the rest of the last plan and the state it expects
    # next (board, specials, RNG counter, moves); see plan().
    carry: object | None = None
    carry_key: tuple | None = None
    # The simulated state carry_key describes: the board the carried line's
    # next action starts from (_carried_ahead plays it before the board rests).
    carry_after: dict | None = None
    # _carried_ahead's last answer, by the snapshot it matched: Memory GUI asks
    # again for the same board after every cancelled computation.
    ahead_key: tuple | None = None
    ahead_outcome: dict | None = None
    # Background replan: the future, the board key it planned from and how
    # many plan() calls have passed since it was started.
    bg: object | None = None
    bg_key: tuple | None = None
    bg_deadline: float = 0.0
    bg_calls: int = 0
    bg_ahead: int = CHARLES_BG_AHEAD    # how far ahead the running replan started
    # The width the race replan starts from (Showdown / Rumble, _start_race_
    # background): the first plan's widest whole pass, then the widest a race
    # replan ran whole. The Solo replans use BG_MAX_WIDTH constantly.
    bg_width: int = 0
    # The actions the turn clock still allows after the action being played
    # (None: no clock); the replan's board is _bg_ahead actions further.
    bg_steps: int | None = None
    # The dynamic stop (planner.STOP_RULE) holds for the Charles-policy
    # boosters; Woolly's replans keep the plain anytime search.
    dynamic: bool = True
    # When this match's first plan started (MATCH_PLAN_SECONDS counts from it)
    # and the time left for the background replan the next move starts.
    match_started: float | None = None
    bg_left: float | None = None
    # Seconds a pass takes per width and per line action, measured on this
    # match's last whole pass (first plan or replan): how far a replan's fence
    # reaches (_bg_horizon). 2026-11-18 width 150: 301 s / 42, 243 s / 43,
    # 144 s / 21 actions (0.036-0.048).
    bg_pace: float | None = None
    # Seconds one action takes of the clock the plan reads (plan() sets it).
    action_seconds: float = CHARLES_ACTION_SECONDS
    # When this plan() call read the turn clock (_time_left).
    clock_read_at: float | None = None
    stats: dict = field(default_factory=lambda: {"exact": 0, "miss": 0, "other_move": 0})
    # A refill miss since the GUI last looked (it turns the recording on).
    miss_seen: bool = False
    # The turn the expectation was made in: Versus hands the board to the
    # opponent, and the board after their turn is no miss of ours.
    expect_turn: object = None
    # Actions played since the expectation was made (memory_gui counts every
    # played result). More than one: the bot played its own moves in between
    # (Showdown 2026-11-19 12:06:34 / 12:06:59), so the board is no miss.
    played: int = 0

    def reset(self):
        self.__init__()

    def _start_race_background(self):
        """The race: a wider search from the board RACE_BG_AHEAD carried
        actions ahead, in the background worker (planner.background_plan)."""
        from strategy_lab import planner
        from strategy_lab.simulation import step

        if self.bg is not None or self.carry is None or self.carry_after is None:
            return
        actions = self.carry.actions
        if len(actions) <= RACE_BG_AHEAD:
            return
        state = self.carry_after
        for action in actions[:RACE_BG_AHEAD]:
            result = step(state, action)
            if not result.get("supported"):
                return
            state = _timed_after(state, action, result["state"])
        seconds = RACE_BG_AHEAD * RACE_ACTION_SECONDS["swap"] * RACE_BG_SHARE
        try:
            self.bg = _background_pool().submit(planner.background_plan, state, seconds, self.bg_width or 0,
                                                300, None, False, None, None, BG_MAX_WIDTH)
        except Exception:
            self.bg = None      # no worker: the carried line plays on
            return
        self.bg_key, self.bg_calls, self.bg_ahead = _plan_key(state), 0, RACE_BG_AHEAD
        self.bg_deadline = time.monotonic() + seconds

    def _race_take_background(self, after):
        """At the board the race replan started from: its line, if it is done
        and scores more than the carried one from here. Never waited for."""
        from strategy_lab import planner

        if self.bg is None or self.bg_key != _plan_key(after):
            return
        future, self.bg = self.bg, None
        if not future.done():
            return      # not in time: the carried line plays on, the next replan starts
        try:
            result = future.result(timeout=0)
        except Exception:
            return
        if result.get("full_width"):
            self.bg_width = result["full_width"]
        line = _replay_line(after, result["actions"]) if result.get("actions") else None
        current = _replay_line(after, self.carry.actions)
        if line is None or current is None or line.value <= current.value:
            _tell({"chosen": True, "source": "pozadinski plan", "taken": False,
                   "score": None if line is None else line.score, "width": result.get("width"),
                   "carried": None if current is None else current.score})
            return
        _tell({"chosen": True, "source": "pozadinski plan", "taken": True, "score": line.score,
               "width": result.get("width"), "carried": current.score,
               "first": [planner.describe(a) for a in line.actions[:5]]})
        self.carry = line

    def predicted_now(self, snapshot) -> bool:
        """The snapshot is the board the race plan already answered (_carried_ahead)."""
        return (self.ahead_key is not None and snapshot.get("board") is not None
                and snapshot.get("special_board") is not None and _ahead_key(snapshot) == self.ahead_key)

    def _carried_ahead(self, snapshot):
        """Showdown / Rumble / Party and Versus (quick_plan): while the board still animates,
        the carried line's next action, if the snapshot already shows the board
        the line predicted (board, specials, moves, charge). None otherwise, and
        plan() goes on as before.

        Asked mid-animation the planner refused every swipe ("tabla jos nije
        mirna") and the bot's own pick broke the line: it led 5-7 of 17-19
        swipes (Showdown 2026-11-20 00:38-00:50), the line it threw away
        scored 1813 against 1022. The RNG is not read here (only at rest); a
        different drop would have shown a different board.
        """
        from strategy_lab import planner
        from strategy_lab.simulation import step

        state = snapshot.get("state") or {}
        if not quick_plan(state) or snapshot.get("board") is None or snapshot.get("special_board") is None:
            return None
        seen = _ahead_key(snapshot)
        if seen == self.ahead_key:
            # Asked again for a board already answered, also once it rests: the
            # line has moved on, a fresh plan here broke it (01:22:35 -> 01:22:38).
            return self.ahead_outcome
        # At rest too: a predicted board plays on at once. The profile read and
        # short search of plan() took 1.3-1.8 s a move in Versus (2026-11-20
        # 04:14:17-04:14:35) and ~1 s in Showdown ("nastavljam prethodni plan",
        # 04:26:35-04:27:12, the board settled a second before the swipe).
        after = self.carry_after
        if self.carry is None or not self.carry.actions or after is None:
            return None
        predicted = (str(_grid(after["board"])), str(_grid(after["special_board"])),
                     (after.get("turn_state") or {}).get("remaining_moves"),
                     (after.get("booster_state") or {}).get("current"))
        if predicted != seen:
            return None
        if race_plan(state):
            self._race_take_background(after)
            if not self.carry.actions:
                return None
        action = self.carry.actions[0]
        result = step(after, action)
        if not result.get("supported"):
            return None
        self.carry = planner.Line(self.carry.state, self.carry.actions[1:], self.carry.gains[1:])
        self.carry_after = _timed_after(after, action, result["state"])
        self.carry_key = _plan_key(self.carry_after)
        if race_plan(state):
            self._start_race_background()
        self.expectation = None     # no RNG read for it: the refill check stays with the GUI
        log = [f"plan unapred (tabla predvidjena tokom animacije): {planner.describe(action)}"]
        if action.get("kind") == "booster":
            outcome = {"move": None, "booster": True, "booster_color": action.get("color"),
                       "note": "plan unapred: booster", "log": log}
        else:
            outcome = {"move": broom_first(after["special_board"], {
                           "kind": action.get("kind", "swap"), "start": tuple(action.get("start") or action["cell"]),
                           "target": tuple(action.get("target") or action["cell"]), "direction": action.get("direction")}),
                       "note": "plan unapred", "log": log}
        self.ahead_key, self.ahead_outcome = seen, outcome
        return outcome

    def _time_left(self, turn_time_left, now=None):
        """Seconds the plans may still count on, less CLOCK_RESERVE_SECONDS:
        the challenge turn clock when the mode has one, else
        MATCH_PLAN_SECONDS from the first plan of the match."""
        now = time.monotonic() if now is None else now
        if turn_time_left is not None:
            # The game's own clock (it stops for animations and boosters):
            # Bombs Away 2026-11-18 16:06 ended its 105 actions with 1011 of
            # 1500 s left, yet the 15-minute fence cut the first plan's line
            # from 104 actions to 78 (6927 -> 5142). The player: in a Solo
            # Challenge the wait costs nothing, only the clock to the end does.
            # It was read when this plan() started; the search since then runs on it.
            read = self.clock_read_at if self.clock_read_at is not None else now
            return float(turn_time_left) - (now - read) - CLOCK_RESERVE_SECONDS
        started = self.match_started if self.match_started is not None else now
        return MATCH_PLAN_SECONDS - (now - started) - CLOCK_RESERVE_SECONDS

    def _start_background(self, after, actions, baseline=None):
        """Plan from the board _bg_ahead carried actions after this one.

        ``baseline``: the value the carried line reaches (the same line from
        any of its boards)."""
        from strategy_lab import planner
        from strategy_lab.simulation import step

        self.bg = None
        ahead = _bg_ahead(len(actions))
        if len(actions) <= ahead:
            return
        state = after
        for action in actions[:ahead]:
            result = step(state, action)
            if not result.get("supported"):
                return
            state = result["state"]
        seconds = ahead * CHARLES_BG_ACTION_SECONDS
        if self.bg_steps is None:
            # Charles' replans look to the end of its line (300); a solo one
            # stops at SOLO_PLAN_STEPS, the horizon the first plan used.
            steps = BG_PLAN_STEPS if self.dynamic else SOLO_PLAN_STEPS
        else:
            steps = max(1, self.bg_steps - ahead)
        clock = None
        if self.dynamic and self.bg_left is not None:
            # No short time of its own, but never past what the carried line
            # still needs to play: live 2026-11-18 08:40 a width-150 replan
            # took 243 s, the bot stood 200 s, and the clock cut the 3291 line
            # to 26 actions (2432).
            if self.bg_left - ahead * self.action_seconds < self.action_seconds:
                return
            rest = len(actions) - ahead
            room = self.bg_left - rest * self.action_seconds
            if room < self.action_seconds:
                return      # the match has no time for a replan: the line plays on
            seconds, steps = room, BG_PLAN_STEPS
            clock = {"left": self.bg_left, "busy": ahead * self.action_seconds,
                     "action_seconds": self.action_seconds}
        # One width, 25, and a short fence (the player, 2026-11-20): widening
        # here took minutes and the bot waited for it. The horizon is what
        # fits the fence at this match's own pace.
        seconds = min(seconds, BG_PLAN_SECONDS)
        steps = self._bg_horizon(steps, seconds)
        try:
            # baseline: the carried line's value; the dynamic stop
            # (planner.STOP_RULE) measures each pass against it.
            self.bg = _background_pool().submit(planner.background_plan, state, seconds, BG_MAX_WIDTH,
                                                steps, baseline, None if self.dynamic else False, clock,
                                                None, BG_MAX_WIDTH)
        except Exception:
            return      # no worker: the carried line and the 2 s checks go on
        self.bg_key, self.bg_calls, self.bg_ahead = _plan_key(state), 0, ahead
        self.bg_deadline = time.monotonic() + seconds

    def _bg_horizon(self, steps, seconds):
        """Actions a width-BG_MAX_WIDTH pass fits inside ``seconds`` here.

        ``bg_pace`` is this match's measured seconds per width per action (the
        last whole pass: the first plan's or a replan's). Without it the
        caller's steps, up to BG_FALLBACK_STEPS, are kept.
        """
        if not self.bg_pace or seconds <= 0:
            return max(1, min(steps, BG_FALLBACK_STEPS))
        return max(1, min(steps, int(seconds / (self.bg_pace * BG_MAX_WIDTH))))

    def _measure_pace(self, passes, actions):
        """bg_pace from the last whole pass: seconds per width per line action."""
        whole = [(w, s) for w, s, done in passes or () if done and s and w]
        if whole and actions:
            width, seconds = whole[-1]
            self.bg_pace = seconds / (width * actions)

    def _take_background(self, lab, carried, log, announce, fit=None):
        """The background plan for this board, if it beats the carried line.

        ``fit``: how many actions the clock still plays now (a callable); both
        lines are compared cut to it, as they would be played. Live
        2026-11-18 08:43:59 a 3502 replan beat the 3291 line at full length,
        and then only 26 of its 43 actions fitted."""
        future, self.bg = self.bg, None
        wait = max(0.0, self.bg_deadline - time.monotonic()) + 5.0
        if not future.done() and announce is not None:
            try:
                announce(wait, True)
            except Exception:
                pass
        try:
            result = future.result(timeout=wait)
        except Exception as exc:
            log.append(f"pozadinski plan nije stigao ({type(exc).__name__})")
            return carried
        from strategy_lab import planner

        if result.get("full_width"):
            self.bg_width = result["full_width"]
        passes = planner.describe_passes(result.get("passes"))
        why = f"; stao: {result['stop_reason']}" if result.get("stop_reason") else ""
        passes = f" (prolazi {passes}{why})" if passes else ""
        line = _replay_line(lab, result["actions"]) if result.get("actions") else None
        if line is not None:
            self._measure_pace(result.get("passes"), len(line.actions))
        against = carried
        if line is not None:
            if fit is not None:
                steps = max(1, int(fit()))
            elif carried.actions:
                # No clock to cut both lines to: cut them to the same number
                # of actions anyway, since a line's score grows with its
                # length and comparing a 293-action replan with a 50-action
                # carried line decides nothing (2026-11-20 03:09:57: 12360
                # against 2408, taken, in a match that ended at 2832). Only
                # that common horizon is priced and carried; the next replan
                # extends it again from the board it reaches.
                steps = min(len(line.actions), len(carried.actions))
            else:
                steps = None
            if steps is not None and len(line.actions) < steps:
                # The replan priced a shorter horizon than the line has left
                # (width 25 and a short fence): compare over the horizon it
                # looked at, as the carried line would be played from here.
                steps = len(line.actions)
            if steps is not None:
                if len(line.actions) > steps:
                    line = _replay_line(lab, result["actions"][:steps])
                if line is not None and len(carried.actions) > steps:
                    against = _replay_line(lab, carried.actions[:steps]) or carried
        if line is not None and line.value > against.value:
            log.append(f"pozadinski plan: sirina {result.get('width')}, skor {line.score} "
                       f"umesto {against.score}, prelazim{passes}")
            _tell({"chosen": True, "source": "pozadinski plan", "taken": True, "score": line.score,
                   "width": result.get("width"), "carried": against.score,
                   "first": [planner.describe(a) for a in line.actions[:5]]})
            return line
        log.append(f"pozadinski plan: sirina {result.get('width')}, skor {result.get('score')}, "
                   f"ostaje {carried.score}{passes}")
        _tell({"chosen": True, "source": "pozadinski plan", "taken": False, "score": result.get("score"),
               "width": result.get("width"), "carried": carried.score})
        return carried

    def read_profile(self, script) -> dict:
        profile = script.exports_sync.match_profile(self.static is None)
        if profile.get("logic_key") != self.logic_key or self.static is None:
            if "rules" not in profile:
                profile = script.exports_sync.match_profile(True)
            self.static = {"rules": profile["rules"], "config": profile["config"]}
            self.logic_key = profile.get("logic_key")
            self.disabled_reason = None
            self.expectation = None
        if not profile.get("consistent", False):
            raise RuntimeError("RNG se pomerio tokom citanja")
        return {**profile, **self.static}

    def settled_profile(self, script, timeout=3.0, gap=0.25):
        """A profile read with the engine at rest (and still at rest after it).

        The engine resolves a move step by step with its animation, so a read
        mid-cascade pairs a half-finished RNG with a board that is not final.
        While it moves only ``restState`` (four field reads) is polled: the
        full profile walk racing a Teleport crashed the game (2026-11-20
        09:28, 14:02, SIGSEGV in the Frida thread).
        """
        deadline = time.monotonic() + timeout

        def mark(rest):
            return (rest.get("counter"), rest.get("moves"), rest.get("chain_reaction"),
                    rest.get("game_state"))

        def at_rest(rest):
            return rest.get("game_state") in (None, WAITING_FOR_INPUT) and not rest.get("chain_reaction")

        previous = script.exports_sync.rest_state()
        while True:
            time.sleep(gap)
            current = script.exports_sync.rest_state()
            if mark(previous) == mark(current) and at_rest(current):
                profile = self.read_profile(script)
                st = profile.get("state") or {}
                if ((profile.get("rng") or {}).get("<counter>k__BackingField") == current.get("counter")
                        and st.get("moves") == current.get("moves")):
                    return profile
                current = script.exports_sync.rest_state()
            if time.monotonic() > deadline:
                return None
            previous = current

    def check_expectation(self, snapshot, profile) -> str | None:
        """Compare the board the last plan predicted with this one."""
        expected, self.expectation = self.expectation, None
        if expected is None:
            return None
        counter = (profile.get("rng") or {}).get("<counter>k__BackingField")
        same_board = (_grid(snapshot["board"]) == _grid(expected.board)
                      and _grid(snapshot["special_board"]) == _grid(expected.special_board))
        if same_board and counter == expected.rng_counter:
            self.stats["exact"] += 1
            return "dopuna predvidjena tacno"
        # Not the plan's result. If some other swap from the same state gives
        # exactly this board, the bot just played that one and the model is
        # still right; booster/perk turns are not reproduced by swaps.
        played = self._identify_swap(expected.lab, snapshot, counter)
        if played is not None:
            self.stats["other_move"] += 1
            return f"odigran drugi potez ({played}), dopuna i za njega tacna"
        self.stats["miss"] += 1
        # The GUI turns the research recording on (memory_gui, planner_miss).
        self.miss_seen = True
        saved = self._save_miss(expected, snapshot, profile)
        mode_id = (expected.capture or {}).get("profile", {}).get("rules", {}).get("id")
        if mode_id in ("color-crush", "rainbow"):
            self.disabled_reason = f"{mode_id}: ishod se nije poklopio; obican bot do kraja partije"
        return f"potez se ne moze reprodukovati (booster/perk ili greska modela){saved}"

    @staticmethod
    def _save_miss(expected, snapshot, profile):
        """Keep the evidence: profile and boards before, plan, board after."""
        import datetime as dt
        import json
        from pathlib import Path

        try:
            folder = Path(__file__).resolve().parent / "Debug/square_live_misses"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
            path.write_text(json.dumps({
                "before": expected.capture, "planned_action": expected.action,
                "predicted": {"board": _grid(expected.board), "special_board": _grid(expected.special_board),
                              "rng_counter": expected.rng_counter},
                "after": {"profile": profile, "board": _grid(snapshot["board"]),
                          "special_board": _grid(snapshot["special_board"]), "state": snapshot.get("state")},
            }, default=str), encoding="utf-8")
            return f"; snimljeno {path.name}"
        except Exception as exc:
            return f"; snimak nije uspeo: {exc}"

    @staticmethod
    def _identify_swap(lab, snapshot, counter):
        if lab is None:
            return None
        from strategy_lab import planner
        from strategy_lab.simulation import step

        board, special = _grid(snapshot["board"]), _grid(snapshot["special_board"])
        for action in planner.actions(lab):
            if action.get("kind", "swap") != "swap":
                continue
            result = step(lab, action)
            if not result.get("supported"):
                continue
            after = result["state"]
            if (after["engine_refill"].rng.counter == counter and _grid(after["board"]) == board
                    and _grid(after["special_board"]) == special):
                return planner.describe(action)
        return None

    def plan(self, script, snapshot, *, seconds=PLAN_SECONDS, turn_time_left=None,
             announce=None, perks=None) -> dict:
        """Choose the next action for the resting board and remaining resources."""
        from simulator_capture import lab_move, prepare_input  # noqa: F401  (heavy imports, lazy)
        from strategy_lab import planner
        from strategy_lab.simulation import step
        import board_source
        from simulator_capture import decode_dictionary

        log = []
        if self.disabled_reason:
            return {"move": None, "note": f"planer iskljucen: {self.disabled_reason}", "log": log}
        started = self.clock_read_at = time.monotonic()
        self.action_seconds = (GAME_CLOCK_ACTION_SECONDS if turn_time_left is not None
                               else CHARLES_ACTION_SECONDS)
        state = snapshot.get("state") or {}
        ahead = self._carried_ahead(snapshot)
        if ahead is not None:
            return ahead
        # GameState -5 waits for input; -7 is still resolving the last move
        # (the snapshot's "stable" is true there too).
        if (not snapshot.get("stable", True) or state.get("chain_reaction")
                or state.get("game_state") not in (None, WAITING_FOR_INPUT)):
            return {"move": None, "note": "tabla jos nije mirna", "log": log}
        profile = self.settled_profile(script)
        if profile is None:
            return {"move": None, "note": "igra jos razresava potez", "log": log}
        from simulator_capture import FUNKY_TILES_BOARD
        if profile["rules"].get("boardModelName") == FUNKY_TILES_BOARD:
            from engine_refill import FUNKY_MAX_TILES
            cells = board_source.funky_tile_cells(snapshot)
            if cells is not None and len(cells) < FUNKY_MAX_TILES:
                # A destroyed marker is not back in memory yet: planned now the
                # move start draws for it and the line is lost (live 2026-11-18 11:40).
                return {"move": None, "note": "tabla jos nije mirna", "log": log}
        if not _solo_snapshot_matches_profile(state, profile):
            # The snapshot is from before the last move: this request is stale
            # and the GUI replaces it; the expectation waits for the new board.
            return {"move": None, "note": "tabla i memorija nisu iz istog trenutka", "log": log}
        # Charles and Woolly: the plan owns the booster, perks and replans.
        charles = exact_plan_booster(state)
        # Showdown / Versus: the booster still plays, the long Solo policy not.
        quick = quick_plan(state)
        long_plan = charles and not quick
        local = next((p for p in state.get("players") or () if p.get("player_type") == 0), {})
        # Versus with a booster the plan cannot play: a full meter usually goes
        # first and changes the board, so the long search would be thrown away
        # (live 2026-11-19 16:09:50: plan 4 s, booster, plan 3.3 s). Only a
        # short one: the bot lets an extra move go before the booster, and
        # that swipe should still come from the plan (live 16:19:39).
        booster_first = bool(quick and not charles and local.get("energy_to_ability")
                             and (local.get("energy") or 0) >= local["energy_to_ability"])
        perks = dict(perks or {}) if charles else {}
        key = (str(_grid(snapshot["board"])), str(_grid(snapshot["special_board"])),
               (profile.get("rng") or {}).get("<counter>k__BackingField"), state.get("moves"),
               tuple(p.get("energy") for p in state.get("players") or ()),
               _perk_inventory_key(perks))
        if key == self.cached_key and self.cached_outcome is not None:
            return {**self.cached_outcome, "log": []}
        # An inventory change on the same board invalidates the plan without
        # counting the unplayed action as a refill miss.
        if self.expect_turn != state.get("current_turn") or self.played > 1:
            self.expectation = None
        note = (self.check_expectation(snapshot, profile)
                if self.cached_key is None or key[:-1] != self.cached_key[:-1] else None)
        if note:
            log.append(note)
            if self.disabled_reason:
                return {"move": None, "note": note, "log": log}
        profile = copy.copy(profile)
        profile["players"] = _profile_players(snapshot, profile.get("players"))
        # The colours under the colourless pieces, as the recorder and the
        # replay (analyze_research) give them. Without them EngineRefill.balls
        # is None: Color Climb 2026-11-17 22:40 (Foxy Roxy SE), the live first
        # plan scored 3276 at width 60 against 49939 from the same board
        # replayed, and lost 4396/7050; on board 021 the booster line
        # (5324) was missing and the plan kept 4358.
        profile["ball_slots"] = _ball_slots(snapshot)
        score = decode_dictionary(profile["rules"].get("_colorScoreOverride")) or {}
        capture = {"profile": profile, "simulator_input": {
            "board": copy.deepcopy(snapshot["board"]), "special_board": copy.deepcopy(snapshot["special_board"]),
            # Funky Tiles' marker layer (CellModel.cellType 3), as the recorder keeps it.
            "cell_types": copy.deepcopy(snapshot.get("cell_types")),
            "froggy_params": next((p.get("special_ability_params") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "booster_cost": next((p.get("energy_to_ability") for p in state.get("players", [])
                                   if p.get("player_type") == 0), None),
            "score_multiplier": next((p.get("score_multiplier") for p in state.get("players", [])
                                      if p.get("player_type") == 0), None),
            "multiplier_colors": (board_source.color_climb_state(snapshot) or {}).get("colors"),
            "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in score.items()}}}
        lit = board_source.lights_up_state(
            dict(snapshot, columns=len(snapshot["board"][0]) if snapshot.get("board") else None))
        if lit is not None:
            capture["simulator_input"]["lights_up_column"] = lit["column"]
        mania = board_source.column_mania_state(
            dict(snapshot, columns=len(snapshot["board"][0]) if snapshot.get("board") else None))
        if mania is not None:
            capture["simulator_input"]["column_multipliers"] = mania["multipliers"]
        if profile["rules"].get("id") == "the-floor-is-lava":
            # The columns one match from erupting, as tools/analyze_research.capture_from
            # reads them; unread stays None and plan_refusal stops the plan.
            counts = board_source.floor_lava_column_counts(
                dict(snapshot, columns=len(snapshot["board"][0]) if snapshot.get("board") else None))
            if counts:
                capture["simulator_input"]["floor_lava_columns"] = tuple(
                    column for column, count in counts.items() if count == 1)
        lab = lab_move(capture)
        # Vegas Views: the live tile state comes from the snapshot's cell_types
        # layer (board_source.vegas_views_state), the same source memory_gui
        # uses for the runtime path; lab_move does not add it because it goes
        # through simulator_capture which only knows the recording path
        # (vegas_cells from cell_types in a saved capture).
        if lab.get("vegas_views_state") is None:
            vv = board_source.vegas_views_state(snapshot)
            if vv is not None:
                lab["vegas_views_state"] = vv
        from strategy_lab.simulation import plan_refusal
        refusal = plan_refusal(lab)
        if refusal:
            return {"move": None, "note": refusal, "log": log}
        if profile["rules"].get("id") == "rainbow" and any(
                int(v) == 20 for row in lab["special_board"] for v in row):
            # Do not promote an ordinary exact swap over a potentially better
            # Froggy gather that the exact planner cannot yet price/resolve.
            return {"move": None, "note": "Rainbow lotus: izbor preuzima Froggy strategija", "log": log}
        lab["perks"] = perks
        if race_plan(state) and turn_time_left is not None:
            lab["time_left"] = max(0.0, float(turn_time_left) - (time.monotonic() - started))
            lab["action_seconds"] = dict(RACE_ACTION_SECONDS)
        if quick and (state.get("rules") or {}).get("pvp_mode") == 0 and lab.get("score_multiplier") is not None:
            # Versus: a multiplier point raised now pays in our later turns.
            lab["multiplier_value"] = VERSUS_RAW_POINTS_PER_TURN * versus_turns_after(state)
        if charles:
            # Checkmate Charles (ported exactly): the line fires the booster as
            # soon as the meter is full, as the bot does (planner.actions,
            # booster_auto), so the plan sees what the blast and its knights do.
            charge = lab.get("booster_state") or {}
            lab["booster_state"] = {"current": charge.get("current") or 0, "maximum": charge.get("maximum")}
            lab["booster_auto"] = True
        elif quick and local.get("energy_to_ability"):
            # Versus / Showdown with a booster the plan cannot play: the bot
            # fires it, so the plan prices the charge (planner.Line.value, a
            # full meter banked as one activation, a partial one pro rata).
            # Live 2026-11-19 16:42: unpriced, the meter sat at 6 of 7 for five
            # turns and the match was lost 272 : 761.
            charge = lab.get("booster_state") or {}
            multiplier = max(1, int(lab.get("score_multiplier") or 1))
            lab["booster_state"] = {"current": charge.get("current") or 0,
                                    "maximum": charge.get("maximum") or local["energy_to_ability"]}
            lab["booster_fire_value"] = (VERSUS_BOOSTER_RAW_POINTS * multiplier
                                         + VERSUS_BOOSTER_MULTIPLIER_GAIN * (lab.get("multiplier_value") or 0))
        else:
            lab["booster_state"] = {"current": 0, "maximum": None}
        # The rest of the last plan, when this board is the one it predicted
        # (board, specials and RNG): kept unless a new search beats it.
        carried = None
        key_now = _plan_key(lab)
        if (long_plan or quick) and self.carry is not None and self.carry.actions:
            if self.carry_key == key_now:
                carried = self.carry
            else:
                differ = ", ".join(f"{name} {p} -> {a}" for name, p, a in zip(
                    PLAN_KEY_NAMES, self.carry_key or (), key_now)
                    if p != a and name not in ("tabla", "specijali"))
                if self.carry_key is not None and self.carry_key[:2] != key_now[:2]:
                    differ = "tabla/specijali" + (f", {differ}" if differ else "")
                if _replayable(self.carry_key, key_now):
                    # The board is the predicted one, a resource is not (the
                    # meter, score, multipliers, a flag's moves): the line is
                    # replayed from the real state instead of a fresh plan.
                    # Bombs Away 2026-11-18 09:02 and 09:05: the meter 6 and 5
                    # predicted, the game 7; each cost a 127 s / 97 s first plan.
                    replayed = _replay_line(lab, self.carry.actions)
                    if replayed is not None:
                        log.append(f"{differ} (predvidjeno -> u igri): nastavljam plan")
                        carried = replayed
                if carried is None and self.carry_key is not None:
                    log.append(f"plan ne vazi: {differ or 'nepoznato'}")
        if long_plan and self.bg is not None:
            self.bg_calls += 1
            if carried is not None and (self.bg_key == key_now or _replayable(self.bg_key, key_now)):
                fit = None
                if charles_policy_booster(state):
                    def fit():
                        return self._time_left(turn_time_left) / self.action_seconds
                carried = self._take_background(lab, carried, log, announce, fit)
            elif carried is None or self.bg_calls > self.bg_ahead + 1:
                self.bg = None      # a miss or another line: its board will not come
        self.dynamic = charles_policy_booster(state) and not quick
        opening = self.match_started is None
        if self.match_started is None:
            self.match_started = started
        if quick:
            # The turn's first move thinks for the whole turn; later moves
            # play that line on (carried) unless a short search beats it.
            race = race_plan(state)
            seconds = ((RACE_PLAN_SECONDS if race else QUICK_PLAN_SECONDS)
                       if carried is not None or booster_first
                       else VERSUS_TURN_SEARCH_SECONDS if versus_reply_follows(state)
                       else RACE_TURN_START_SECONDS if race
                       else QUICK_TURN_START_SECONDS)
        elif charles:
            seconds = CHARLES_NEXT_SECONDS if carried is not None else CHARLES_FIRST_SECONDS
            if carried is not None and self.bg is not None and charles_policy_booster(state):
                seconds = 0.0   # the background replan is the search; the clock pays per action
            lab["booster_hold"] = True
        prep = time.monotonic() - started
        if quick and carried is None:
            # Versus / Showdown: the seconds are the search's own. The profile
            # read before it took ~2 s of a 1 s Versus budget, and almost every
            # move said "nema vremena za plan" (Mighty Mushrooms 2026-11-20
            # 04:03-04:05: one plan in 13 moves, its search 0.2 s of 2.2 s).
            # A carried line plays on without that search (04:11, 2.3-2.7 s a move).
            budget = seconds
        else:
            budget = seconds - prep
        if turn_time_left is not None:
            budget = min(budget, float(turn_time_left) - CLOCK_RESERVE_SECONDS - prep)
        if budget < 0.5 and carried is None:
            return {"move": None, "note": f"nema vremena za plan (priprema {prep:.1f} s, "
                                          f"sat {'?' if turn_time_left is None else f'{float(turn_time_left):.0f} s'})",
                    "log": log}
        # Charles: a move in hand has a price in the beam, and a line gets
        # only the actions the turn clock allows after this search.
        steps = None
        clock = None
        self.bg_steps = None
        if self.dynamic:
            lab["rank_move_value"] = (SOLO_MOVE_VALUE if (lab.get("solo_flag_rules") or {}).get("refill")
                                      else CHARLES_MOVE_VALUE)
            left = self._time_left(turn_time_left)
            if carried is None and opening:
                # The match's first plan: no fixed time. Each pass gets the
                # actions the match time leaves after it, and the search ends
                # before it would not leave time to play its best line.
                clock = {"left": left, "action_seconds": self.action_seconds}
                budget = left
                # Only the first FIRST_PLAN_STEPS actions: the background
                # replans take the line to the end while the bot plays.
                # Vegas Views: the tile comes back on a new cell after the
                # move that destroys it and the simulator does not model that
                # conversion, so the line starts again after such a move
                # (live 2026-11-20 07:14-07:15: 54 s and 58 s); the width
                # stays 25, the horizon is short.
                steps = (VEGAS_FIRST_STEPS
                         if (profile.get("rules") or {}).get("id") == "vegas-views"
                         else FIRST_PLAN_STEPS)
            elif carried is None:
                # A restart, not the match's first plan: a short search with
                # the narrow widths that fit, so an unpredictable board (a
                # Froggy lotus, a Vegas tile) is answered in seconds, not 75.
                budget = min(left, RESTART_PLAN_SECONDS)
                steps = RESTART_PLAN_STEPS
                log.append(f"plan iznova, kratko: {RESTART_PLAN_SECONDS:.0f} s, "
                           f"{RESTART_PLAN_STEPS} akcija")
            else:
                steps = max(1, int((left - max(budget, 0.0)) / self.action_seconds))
                self.bg_steps = steps - 1
                if carried is not None and len(carried.actions) > steps:
                    # The play ran slower than planned: the clock ends the
                    # carried line early, so it counts only that far.
                    shorter = _replay_line(lab, carried.actions[:steps])
                    if shorter is not None:
                        log.append(f"sat: od {len(carried.actions)} akcija plana staje jos {steps}")
                        carried = shorter
        elif not quick:
            # Solo with a refill booster: the refill chain lets the simulation
            # play far more actions than the match will ever hold, and the
            # planner would otherwise use its own 300 (SOLO_PLAN_STEPS).
            steps = SOLO_PLAN_STEPS
            if (lab.get("solo_flag_rules") or {}).get("refill"):
                # A flag fills the moves back: a move in hand is worth more
                # than a few points now (planner._rank, SOLO_MOVE_VALUE).
                lab["rank_move_value"] = SOLO_MOVE_VALUE
        if budget >= 0.5:
            if announce is not None:
                # The GUI counts down to the move (memory_gui._plan_countdown).
                try:
                    announce(budget, carried is not None)
                except Exception:
                    pass
            # The first plan holds the turn clock: it does not start a width it
            # cannot finish (stop_early). The background replans' time is free.
            # The first plan stops by itself once a wider pass no longer
            # pays (planner.STOP_RULE); its seconds are only the fence. Its
            # passes go to the GUI as they finish (PASS_LISTENER).
            first = carried is None
            race_first = first and quick and race_plan(state) and "time_left" in lab
            race_rule = {"min_width": 0, "min_points": 1, "clock_seconds": lab.get("time_left")}
            best, stats = planner.plan_anytime(
                lab, budget, finish_cut=first, stop_early=first,
                **({} if steps is None else {"max_steps": steps}),
                **({"on_pass": lambda info: _tell(dict(info, source="prvi plan"))} if first else {}),
                **({"rule": race_rule, "clock": {"left": lab["time_left"],
                                                 "action_seconds": RACE_ACTION_SECONDS["swap"]}}
                   if race_first else
                   {"rule": VERSUS_FIRST_RULE} if first and quick and versus_reply_follows(state) else
                   {"rule": planner.STOP_RULE} if first and charles_policy_booster(state) else {}),
                **({} if clock is None else {"clock": clock, "widths": (FIRST_MAX_WIDTH,)}))
            if first:
                self.bg_width = stats.get("full_width") or 0
                # Vegas Views (and any Solo without a turn clock): the first
                # plan may finish only a narrow pass (e.g. width 10) because
                # the board is settled fast; the background replans still use
                # the full width the player asked for (player, 2026-11-20).
                if not self.dynamic:
                    self.bg_width = max(self.bg_width, BG_MAX_WIDTH)
                whole = [p for p in stats.get("pass_info") or () if p.get("complete")]
                if whole:
                    self._measure_pace([(whole[-1]["width"], whole[-1]["seconds"], True)],
                                       whole[-1]["actions"])
                if clock is not None:
                    self.bg_steps = max(1, int(self._time_left(turn_time_left) / self.action_seconds)) - 1
                log.append(f"prvi plan: sirina {stats.get('width')}, skor {best.score} "
                           f"(prolazi {planner.describe_passes(stats.get('passes'))}; "
                           f"stao: {stats.get('stop_reason')})")
                if quick and carried is None and (stats.get("width") or 0) < RACE_MIN_WIDTH:
                    self.carry = self.carry_key = self.carry_after = None
                    return {"move": None, "note": f"plan preuzak (sirina {stats.get('width')}), igra bot",
                            "log": log}
                if quick and VERSUS_COUNTER_CHOICE and versus_reply_follows(state):
                    # The search's own finished lines (planner.plan stats): a
                    # second search of the turn took 9.5 s live (17:09:59, a
                    # line with extras), leaving the turn 8 s.
                    # From the end of our own search: a longer first search
                    # (VERSUS_TURN_SEARCH_SECONDS) must not eat the replies' time.
                    reply_deadline = time.monotonic() + VERSUS_REPLY_DEADLINE_SECONDS
                    if turn_time_left is not None:
                        left = float(turn_time_left) - CLOCK_RESERVE_SECONDS - (time.monotonic() - started)
                        reply_deadline = min(reply_deadline, time.monotonic() + max(0.0, left) / 2)
                    best, note = versus_counter_choice(lab, state, stats.get("lines") or (), best,
                                                       reply_deadline)
                    if note:
                        log.append(note)
        else:
            best = carried
        if carried is not None and carried.value >= best.value:
            best = carried
            log.append("nastavljam prethodni plan")
        self.carry = self.carry_key = self.carry_after = None
        if not best.actions:
            return {"move": None, "note": "planer nema podrzan potez", "log": log}
        action = best.actions[0]
        result = step(lab, action)
        if result.get("supported"):
            after = result["state"]
            self.expectation = Expectation(snapshot.get("signature"), action, after["board"],
                                           after["special_board"], after["engine_refill"].rng.counter, lab, capture)
            self.expect_turn = state.get("current_turn")
            self.played = 0
            if long_plan or quick:
                self.carry = planner.Line(best.state, best.actions[1:], best.gains[1:])
                self.carry_key = _plan_key(after)
                self.carry_after = _timed_after(lab, action, after)
                if quick and race_plan(state):
                    self.bg = None      # a new line: the old replan's board will not come
                    self._start_race_background()
                if long_plan and (self.bg is None or best is not carried):
                    self.bg_left = (self._time_left(turn_time_left) - self.action_seconds
                                    if self.dynamic else None)
                    self._start_background(after, self.carry.actions, best.value)
        log.append(f"plan do kraja: skor {best.score} za {len(best.actions)} poteza, "
                   f"prvi {planner.describe(action)} ({time.monotonic() - started:.1f} s)")
        if action.get("kind") == "booster":
            # The bot fires the full booster itself; the plan goes on after it.
            outcome = {"move": None, "booster": True, "booster_color": action.get("color"),
                       "note": f"tacna dopuna: plan {best.score}, prvo booster", "log": log}
            self.cached_key, self.cached_outcome = key, outcome
            return outcome
        outcome = {"move": broom_first(lab["special_board"], {
                       "kind": action.get("kind", "swap"), "start": tuple(action.get("start") or action["cell"]),
                       "target": tuple(action.get("target") or action["cell"]), "direction": action.get("direction")}),
                   "note": f"tacna dopuna: plan {best.score}", "log": log}
        self.cached_key, self.cached_outcome = key, outcome
        return outcome
