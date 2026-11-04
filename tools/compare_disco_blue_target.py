"""Does the solo blue-first disco still aim the ball at BLUE?

Under `SOLO_DISCO_BLUE_FIRST` the disco swap is ordered by blue service:
indirect (cascade) charge first, then the blue pickup the clear sets up. Swaps
that serve no blue at all still rank -- the ball is spent, never parked -- and
until now the tie among them was broken by score and by the raw count of the
target colour, neither of which knows WHICH colour is being swept away.

A blue target is the worst of that group: the ball's own clear never charges
the meter, so wiping blue banks nothing now and removes the blue the next
ordinary moves would have matched for charge. `_rank_disco_fallback_moves` now
carries a "target is not BLUE" key, placed below the extra-move key (a free
turn still outranks sparing blue) and above score.

This replays every recorded board that had a disco ball on it through the
ordering with and without that key, and reports:

  * how often the ball still lands on BLUE, and how many blue tiles that
    sweeps for no charge,
  * what the new pick gives up in blue service / extras (it must give up
    neither by construction -- the key sits below both -- so anything non-zero
    there is a bug in the change),
  * how unstable the ordering is on its own.

That last one matters: `_best_next_blue_cells_after_disco` simulates the board
the wipe leaves behind, and those holes refill RANDOMLY, so the second ranking
key is redrawn on every call. Measured on 2026-08-28T04:21:55, six identical
calls returned next-blue 0.0, 0.0, 0.0, 2.0, 3.0 and 4.0 for the same
candidate, and the produced order flipped in 3 of 10 repeats. Every number
below is therefore averaged over `--repeat` passes rather than taken from one.

    python tools/compare_disco_blue_target.py [--limit N] [--repeat N] [--verbose]

Set BROCCO_TAIL_BYTES to scan less of the (very large) snapshot log.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import move_strategy as ms  # noqa: E402

SNAPSHOTS = ROOT / "Debug" / "memory_board" / "board_snapshots.jsonl"
TAIL_BYTES = int(os.environ.get("BROCCO_TAIL_BYTES", 400 * 1024 * 1024))
# BroccoBoogie -- the booster that puts disco balls on the board.
BROCCO_ABILITY = 44
# The live in-game lookahead parameters (memory_gui `_fast_lookahead_params`).
LOOKAHEAD_CANDIDATES = 10
LOOKAHEAD_DEPTH = 2
LOOKAHEAD_BEAM = 3


def load_boards(limit=None):
    """One case per distinct recorded board that had a disco ball on it."""
    size = SNAPSHOTS.stat().st_size
    handle = SNAPSHOTS.open("rb")
    handle.seek(max(0, size - TAIL_BYTES))
    handle.readline()
    needle = ('"special_ability_type":%d' % BROCCO_ABILITY).encode()
    cases = []
    seen = set()
    for line in handle:
        if needle not in line:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        snapshot = payload.get("snapshot", payload)
        state = snapshot.get("state") or {}
        me = next(
            (p for p in (state.get("players") or []) if p.get("player_type") == 0),
            None,
        )
        if me is None or me.get("special_ability_type") != BROCCO_ABILITY:
            continue
        if not me.get("is_my_turn") or not state.get("moves"):
            continue
        board = snapshot.get("board")
        special = snapshot.get("special_board")
        if not board or not special:
            continue
        if not any(cell == ms.SPECIAL_DISCO_BALL for row in special for cell in row):
            continue
        signature = json.dumps([board, special], separators=(",", ":"))
        if signature in seen:
            continue
        seen.add(signature)
        rules = state.get("rules") or {}
        cases.append(
            {
                "t": snapshot.get("captured_at"),
                "board": board,
                "special": special,
                "charge": me.get("energy"),
                "maximum": me.get("energy_to_ability"),
                "moves": int(state["moves"]),
                "square": bool(rules.get("is_square_match")),
                "explode": bool(rules.get("specials_auto_explode")),
                "mode": "GameMode.SPECIAL_O_RAMA",
            }
        )
        if limit and len(cases) >= limit:
            break
    return cases


def rank_disco(case):
    """(old order, new order, booster) for one recorded board.

    The new order is the production `_rank_disco_fallback_moves`. The old one
    is rebuilt here from the same helpers with the target-colour key left out
    -- rebuilt rather than monkeypatched, because `_disco_target_color_count`
    is built on `_disco_target_color` and stubbing the latter would silently
    flatten the count tie-breaker too.
    """
    context = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)
    turn = ms.TurnState(remaining_moves=case["moves"], source="memory")
    booster = (
        None
        if case["charge"] is None
        else ms.BoosterState(
            current=case["charge"], maximum=case["maximum"], source="memory"
        )
    )
    ranked = ms.rank_moves(
        case["board"],
        case["special"],
        mode=case["mode"],
        allow_square_matches=case["square"],
        explode_created_specials_immediately=case["explode"],
        lookahead_candidates=LOOKAHEAD_CANDIDATES,
        lookahead_depth=LOOKAHEAD_DEPTH,
        lookahead_beam_width=LOOKAHEAD_BEAM,
        include_future_value=True,
        strategy_context=context,
    )
    new_order = ms._rank_disco_fallback_moves(
        ranked,
        mode=case["mode"],
        allow_square_matches=case["square"],
        booster_state=booster,
        strategy_context=context,
        turn_state=turn,
    )
    if not ms._disco_blue_first(context, turn):
        # Points-first branch (final phase of the turn): the new key lives only
        # in the blue-first branch, so the two orders are identical there.
        return new_order, new_order, booster
    decorated = []
    for index, evaluation in enumerate(ranked):
        if evaluation.disco_moves <= 0:
            continue
        indirect_blue, next_blue = ms._disco_blue_service(
            evaluation, case["mode"], case["square"], None, booster
        )
        decorated.append(
            (
                indirect_blue,
                next_blue,
                ms.has_reliable_same_move_extra(evaluation),
                evaluation.score,
                ms._disco_target_color_count(evaluation),
                -index,          # stable: keep rank_moves order on a full tie
                evaluation,
            )
        )
    old_order = [
        item[-1] for item in sorted(decorated, key=lambda item: item[:-1], reverse=True)
    ]
    return old_order, new_order, booster


def describe(evaluation, case, booster):
    colour = ms._disco_target_color(evaluation)
    service = ms._disco_blue_service(
        evaluation, case["mode"], case["square"], None, booster
    )
    return {
        "colour": colour,
        "is_blue": colour == ms.BLUE,
        "swept": ms._disco_target_color_count(evaluation),
        "service": service,
        "extra": ms.has_reliable_same_move_extra(evaluation),
        "score": evaluation.score,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="stani posle ovoliko razlicitih tabli")
    parser.add_argument("--repeat", type=int, default=5,
                        help="koliko puta da ponovi svaku tablu (redosled je "
                             "nestabilan zbog nasumicnog dopunjavanja)")
    parser.add_argument("--verbose", action="store_true",
                        help="ispisi svaku tablu na kojoj se izbor promenio")
    args = parser.parse_args()

    cases = load_boards(args.limit)
    print(f"snimljenih tabli sa disko kuglom (nas potez, ima poteza): {len(cases)}")
    if not cases:
        return

    total = 0
    blue_before = 0.0
    blue_after = 0.0
    swept_before = 0.0
    swept_after = 0.0
    changed = []
    service_regressions = 0
    extra_regressions = 0
    unstable = 0
    for case in cases:
        picks_old = []
        picks_new = []
        booster = None
        for _ in range(max(1, args.repeat)):
            old_order, new_order, booster = rank_disco(case)
            if not old_order or not new_order:
                break
            picks_old.append(describe(old_order[0], case, booster))
            picks_new.append(describe(new_order[0], case, booster))
        if not picks_old:
            continue
        total += 1
        if len({p["colour"] for p in picks_new}) > 1:
            unstable += 1
        share_old = sum(p["is_blue"] for p in picks_old) / len(picks_old)
        share_new = sum(p["is_blue"] for p in picks_new) / len(picks_new)
        blue_before += share_old
        blue_after += share_new
        swept_before += sum(p["swept"] for p in picks_old if p["is_blue"]) / len(picks_old)
        swept_after += sum(p["swept"] for p in picks_new if p["is_blue"]) / len(picks_new)
        old, new = picks_old[0], picks_new[0]
        if share_old == share_new and old["colour"] == new["colour"]:
            continue
        # Compared on the MEAN across repeats: the second service key is a
        # fresh random draw every call, so a single pair of draws would report
        # regressions that are only the refill noise.
        def mean_service(picks):
            return (
                sum(p["service"][0] for p in picks) / len(picks),
                sum(p["service"][1] for p in picks) / len(picks),
            )
        if mean_service(picks_new) < mean_service(picks_old):
            service_regressions += 1
        if (sum(p["extra"] for p in picks_old) > sum(p["extra"] for p in picks_new)):
            extra_regressions += 1
        changed.append((case, old, new))

    print()
    print(f"tabli sa disko kandidatima:                 {total}")
    print(f"ponavljanja po tabli:                       {max(1, args.repeat)}")
    print()
    print(f"kugla ciljala PLAVU  -- staro:              {blue_before:.1f}")
    print(f"kugla ciljala PLAVU  -- novo:               {blue_after:.1f}")
    print(f"plavih obrisano bez naboja -- staro:        {swept_before:.1f}")
    print(f"plavih obrisano bez naboja -- novo:         {swept_after:.1f}")
    print(f"tabli sa promenjenom metom:                 {len(changed)}")
    print()
    print("kontrola (mora biti 0 -- kljuc stoji ispod usluge i ispod extra):")
    print(f"  izbora sa losijom plavom uslugom (prosek): {service_regressions}")
    print(f"  izbora koji je izgubio extra potez:       {extra_regressions}")
    print()
    print(f"tabli gde i NOVI redosled varira kroz ponavljanja: {unstable}"
          f"  ({100.0 * unstable / max(total, 1):.0f}%)")
    print("  -- to nije ova izmena nego nasumicno dopunjavanje u")
    print("     _best_next_blue_cells_after_disco (vidi docstring skripte).")

    if args.verbose and changed:
        print("\ntable gde se izbor promenio:")
        for case, old, new in changed:
            print(f"  {case['t']}  metar={case['charge']}/{case['maximum']} "
                  f"poteza={case['moves']}")
            print(f"     staro:  meta={old['colour']}"
                  f"{' (PLAVA)' if old['is_blue'] else ''}"
                  f"  brise={old['swept']}  usluga={old['service']}"
                  f"  extra={old['extra']}  score={old['score']:.1f}")
            print(f"     novo:   meta={new['colour']}"
                  f"  brise={new['swept']}  usluga={new['service']}"
                  f"  extra={new['extra']}  score={new['score']:.1f}")


if __name__ == "__main__":
    main()
