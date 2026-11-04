"""Replay snimljenih Solo Challenge tabli (Debug/memory_board/board_snapshots.jsonl)
kroz zivo rangiranje (rank_moves + prioritize_ranked_moves, solo_challenge
kontekst, lookahead 10/2/3).

    python tools/replay_solo_specials.py disco [--limit N]
        Brocco table sa kuglom: SOLO_DISCO_NEVER_BLUE iskljucen vs ukljucen --
        koliko puta kugla cilja plavu, koliko plavih brise, parkiranja.
    python tools/replay_solo_specials.py sweep [--limit N]
        Sweep SE table sa metlom: da li se igra metla, da li je to linija sa
        najvise korisnog punjenja, koliko puta metla stoji dok sweep puni metar.

REPLAY_TAIL_BYTES ogranicava koliko se (ogromnog) snapshot loga cita s kraja.
"""
import argparse
from pathlib import Path
import json
import os
import sys

ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
import move_strategy as ms  # noqa: E402

SNAPSHOTS = os.path.join(ROOT, "Debug", "memory_board", "board_snapshots.jsonl")
TAIL_BYTES = int(os.environ.get("REPLAY_TAIL_BYTES", 600 * 1024 * 1024))
COL = {1: "BLUE", 2: "green", 3: "yellow", 4: "purple", 5: "red", 6: "orange"}
LOOK = dict(lookahead_candidates=10, lookahead_depth=2, lookahead_beam_width=3)
CTX = ms.StrategyContext(mode=ms.STRATEGY_SOLO_6, solo_challenge=True)


def load_boards(ability, special_code, limit=None):
    size = os.path.getsize(SNAPSHOTS)
    handle = open(SNAPSHOTS, "rb")
    handle.seek(max(0, size - TAIL_BYTES))
    handle.readline()
    needle = ('"special_ability_type":%d' % ability).encode()
    cases, seen = [], set()
    for line in handle:
        if needle not in line:
            continue
        try:
            payload = json.loads(line.decode("utf-8"))
        except ValueError:
            continue
        snapshot = payload.get("snapshot", payload)
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        me = next((p for p in players if p.get("player_type") == 0), None)
        if me is None or me.get("special_ability_type") != ability:
            continue
        if not me.get("is_my_turn") or not state.get("moves"):
            continue
        if len(players) > 1:
            continue  # not alone on the board -> not the solo challenge
        board = snapshot.get("board")
        special = snapshot.get("special_board")
        if not board or not special:
            continue
        if not any(cell == special_code for row in special for cell in row):
            continue
        sig = json.dumps([board, special], separators=(",", ":"))
        if sig in seen:
            continue
        seen.add(sig)
        rules = state.get("rules") or {}
        cases.append({
            "t": snapshot.get("captured_at"), "board": board, "special": special,
            "charge": me.get("energy"), "maximum": me.get("energy_to_ability"),
            "moves": int(state["moves"]), "square": bool(rules.get("is_square_match")),
            "explode": bool(rules.get("specials_auto_explode")),
        })
        if limit and len(cases) >= limit:
            break
    return cases


def rank(case):
    booster = None if case["charge"] is None else ms.BoosterState(
        current=case["charge"], maximum=case["maximum"], source="memory")
    turn = ms.TurnState(remaining_moves=case["moves"], source="memory")
    ranked = ms.rank_moves(
        case["board"], case["special"], mode="None",
        allow_square_matches=case["square"],
        explode_created_specials_immediately=case["explode"],
        include_future_value=True, strategy_context=CTX, **LOOK,
    )
    return ranked, booster, turn


def prioritize(ranked, case, booster, turn):
    return ms.prioritize_ranked_moves(
        ranked, mode="None", allow_square_matches=case["square"],
        explode_created_specials_immediately=case["explode"],
        booster_state=booster, turn_state=turn, strategy_context=CTX,
    )


def desc(e):
    if e is None:
        return "None"
    col = ms._disco_target_color(e)
    sw = ms._sweep_se_target_color(e)
    kind = "disco" if e.disco_moves > 0 else ("sweep" if sw is not None else "plain")
    tgt = COL.get(col, col) if kind == "disco" else (COL.get(sw, sw) if kind == "sweep" else "-")
    return f"{kind}:{tgt} {e.candidate.start}->{e.candidate.target} score={e.score:.0f} extra={e.extra_moves:.0f} blue={e.blue_cells:.1f}"


def run_disco(limit):
    cases = load_boards(44, ms.SPECIAL_DISCO_BALL, limit)
    print("solo Brocco boards with a ball:", len(cases))
    stats = dict(total=0, blue_off=0, blue_on=0, changed=0, parked=0, parked_all_blue=0,
                 swept_off=0, swept_on=0, top_disco_off=0, top_disco_on=0)
    details = []
    for case in cases:
        ranked, booster, turn = rank(case)
        if not ranked:
            continue
        ms.SOLO_DISCO_NEVER_BLUE = False
        off = prioritize(ranked, case, booster, turn)
        ms.SOLO_DISCO_NEVER_BLUE = True
        on = prioritize(ranked, case, booster, turn)
        if not off or not on:
            continue
        stats["total"] += 1
        a, b = off[0], on[0]
        a_blue = ms._is_blue_target_disco(a)
        b_blue = ms._is_blue_target_disco(b)
        stats["blue_off"] += a_blue
        stats["blue_on"] += b_blue
        stats["top_disco_off"] += a.disco_moves > 0
        stats["top_disco_on"] += b.disco_moves > 0
        if a_blue:
            stats["swept_off"] += ms._disco_target_color_count(a)
        if b_blue:
            stats["swept_on"] += ms._disco_target_color_count(b)
        if (a.candidate.start, a.candidate.target) != (b.candidate.start, b.candidate.target):
            stats["changed"] += 1
            details.append((case, a, b))
        if b.disco_moves <= 0:
            stats["parked"] += 1
            discos = [e for e in ranked if e.disco_moves > 0]
            if discos and all(ms._is_blue_target_disco(e) for e in discos):
                stats["parked_all_blue"] += 1
    print(json.dumps({k: float(v) for k, v in stats.items()}, indent=1))
    for case, a, b in details:
        print(f"  {case['t']} meter={case['charge']}/{case['maximum']} moves={case['moves']}")
        print(f"     off: {desc(a)}")
        print(f"     on : {desc(b)}")


def run_sweep(limit):
    cases = load_boards(61, ms.SPECIAL_SWEEP_SE_BROOM, limit)
    print("solo Sweep SE boards with a broom:", len(cases))
    stats = dict(total=0, top_sweep=0, top_plain_extra=0, top_other=0, blue_sweep=0,
                 sweep_best_charge=0, sweep_not_best_charge=0, sweep_fills=0,
                 broom_idle_while_fill_sweep=0, broom_idle_while_better_charge_sweep=0,
                 final_phase=0, meter_full=0)
    details = []
    for case in cases:
        ranked, booster, turn = rank(case)
        if not ranked:
            continue
        pri = prioritize(ranked, case, booster, turn)
        if not pri:
            continue
        stats["total"] += 1
        top = pri[0]
        remaining = (booster.remaining if booster is not None else None) or 0
        if remaining <= 0:
            stats["meter_full"] += 1
        if ms._turn_phase(turn) == "final":
            stats["final_phase"] += 1

        def charge(e):
            return ms._useful_total_charge_cells(e, booster, "None", None, CTX, turn)

        sweeps = [e for e in ranked if ms._sweep_se_target_color(e) is not None]
        best_sweep_charge = max((charge(e) for e in sweeps), default=0.0)
        top_sweep = ms._sweep_se_target_color(top)
        if top_sweep is not None:
            stats["top_sweep"] += 1
            stats["blue_sweep"] += top_sweep == ms.BLUE
            c = charge(top)
            if c + 1e-9 >= best_sweep_charge:
                stats["sweep_best_charge"] += 1
            else:
                stats["sweep_not_best_charge"] += 1
                details.append(("sweep not best charge", case, top, max(sweeps, key=charge)))
            if remaining > 0 and c >= remaining - 1e-9:
                stats["sweep_fills"] += 1
        else:
            if top.extra_moves > 0:
                stats["top_plain_extra"] += 1
            else:
                stats["top_other"] += 1
            if remaining > 0 and sweeps:
                bc = best_sweep_charge
                if bc >= remaining - 1e-9:
                    stats["broom_idle_while_fill_sweep"] += 1
                    details.append(("broom idle, a sweep fills", case, top, max(sweeps, key=charge)))
                elif bc > charge(top) + 1e-9:
                    stats["broom_idle_while_better_charge_sweep"] += 1
    print(json.dumps({k: float(v) for k, v in stats.items()}, indent=1))
    for label, case, top, alt in details[:40]:
        print(f"  [{label}] {case['t']} meter={case['charge']}/{case['maximum']} moves={case['moves']}")
        print(f"     played: {desc(top)}  useful_charge={ms._useful_total_charge_cells(top, ms.BoosterState(current=case['charge'], maximum=case['maximum'], source='memory'), 'None', None, CTX, ms.TurnState(remaining_moves=case['moves'], source='memory')):.1f}")
        print(f"     sweep : {desc(alt)}  useful_charge={ms._useful_total_charge_cells(alt, ms.BoosterState(current=case['charge'], maximum=case['maximum'], source='memory'), 'None', None, CTX, ms.TurnState(remaining_moves=case['moves'], source='memory')):.1f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("what", choices=["disco", "sweep"])
    p.add_argument("--limit", type=int, default=None)
    a = p.parse_args()
    (run_disco if a.what == "disco" else run_sweep)(a.limit)
