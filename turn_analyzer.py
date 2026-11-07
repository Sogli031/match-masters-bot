"""Offline analizator odluka: sta je bot odigrao, sta je jos mogao i koja
pocetna akcija ima najvece ocekivane poene do kraja naseg reda.

Tri razdvojene operacije (pravila igre su odvojena od strategije):

* ``legal_actions(state)``  -- sve sto nas igrac sada moze da uradi. Nikakav
  gate ne izbacuje akciju zato sto deluje slabo; jedini filter je legalnost
  (swipe mora da napravi spoj ili aktivira specijal, buster mora biti pun,
  perk mora biti u slotu).
* ``step(state, action, rng)`` -- novo stanje, dnevnik dogadjaja i stvarni
  simulirani poeni igre. Extra potez i punjenje bustera ne donose poene; poeni
  dolaze tek kad se buster stvarno ispali.
* ``choose_action(state)`` -- strategija nastavka (POLICY_DOC). Vidi samo
  trenutno razresenu tablu i resurse, nikad seed, buduce plocice ni sledeci
  debug snimak. Njena heuristicka ocena se vodi odvojeno od poena.

Poznato se razresava deterministicki (simulator iz move_strategy). Prva
nepoznata plocica ili nasumicna meta se belezi kao granica neizvesnosti i od
nje se uzorkuje: boje (i mode figure) dopune iz izmerene raspodele istog moda
(``refill_stats``), nasumicne mete iz seed-ovanog RNG-a. Svaka grana ima
sopstvenu kopiju stanja i RNG; grana ``i`` svih pocetnih akcija koristi isti
seed (common random numbers), pa rezultat akcije A ne zavisi od toga sta je
simulirano pre nje.

Stvarni ishod (observed_delta, memorijski snimci posle odluke, sledeci run)
koristi se samo za proveru, nikad za predvidjanje alternativne grane.
"""

from __future__ import annotations

import bisect
import contextlib
import datetime as dt
import glob
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

import move_strategy as ms

ANALYZER_VERSION = "1.2.0"
ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "Debug" / "runs"
SNAPSHOT_DIR = ROOT / "Debug" / "memory_board"
ANALYSIS_DIR = ROOT / "Debug" / "analysis"
SNAPSHOT_INDEX_PATH = ANALYSIS_DIR / "snapshot_index.jsonl"
SNAPSHOT_INDEX_STATE = ANALYSIS_DIR / "snapshot_index.state.json"
REFILL_STATS_PATH = ANALYSIS_DIR / "refill_stats.json"

CTX_VERSUS = "versus"
CTX_SHOWDOWN = "showdown"
CTX_RUMBLE = "rumble"
CTX_PARTY = "party"
CTX_SOLO_CHALLENGE = "solo_challenge"
CONTEXTS = (CTX_VERSUS, CTX_SHOWDOWN, CTX_RUMBLE, CTX_PARTY, CTX_SOLO_CHALLENGE)

# Match3Engine.RumbleType (memory_gui.RUMBLE_TYPE_LABELS)
_RUMBLE_TYPE_CONTEXT = {1: CTX_RUMBLE, 2: CTX_SHOWDOWN, 3: CTX_PARTY}
# Bez memorijskog snimka solo trka se prepoznaje po broju rundi -- izmereno na
# snimcima 2026-10-29..31: Showdown/Master League 1 runda, Classic Rumble 3.
# Party (rumble_type 3) nije uhvacen u snimcima; 2 runde je pretpostavka i
# izvor se zato pise kao "heuristika".
_ROUNDS_CONTEXT = {1: CTX_SHOWDOWN, 2: CTX_PARTY, 3: CTX_RUMBLE}

MATCH_GAP_SECONDS = 240
SNAPSHOT_MATCH_WINDOW = 8.0
OUTCOME_WINDOW_SECONDS = 20.0
# Sat reda: pravila (pauseTimerForAnimations / pauseTimerForBoosters) zaustavljaju
# tajmer tokom animacija, pa jedna akcija trosi samo vreme odluke i swipe-a.
# Izmereno iz memorijskih snimaka 2026-10-31 11:46:09-11:46:47 (Multiplier
# Mushrooms, versus): 19.91 s -> 10.64 s za 12 akcija = ~0.77 s po akciji.
# Botovo seconds_per_move (6.5 s) je zidno vreme sa animacijama i ne vazi za sat.
CLOCK_SECONDS_PER_ACTION = 0.77
BOOSTER_SECONDS = CLOCK_SECONDS_PER_ACTION
PERK_SECONDS = CLOCK_SECONDS_PER_ACTION
DEFAULT_SECONDS_PER_MOVE = CLOCK_SECONDS_PER_ACTION
DEFAULT_MAX_STEPS = 30
# Grane koje udare u limit se jednom produze (isti seed, isti pocetak) na
# ovoliko puta veci limit; ako i dalje nisu zavrsene, pobednik se ne proglasava.
LIMIT_EXTENSION_FACTOR = 3
EXTRA_THEN_PERK_SWAPS = 5
ENDED_LIMIT = "limit simulacije"
ENDED_NO_MOVES = "nema legalnog swipe-a (mesanje table nije modelovano)"
# Grane koje se nisu zavrsile predajom reda: poeni do tog mesta su donja granica,
# ne rezultat reda, pa ne smeju da odluce pobednika.
CUT_ENDINGS = frozenset({ENDED_LIMIT, ENDED_NO_MOVES, "plan nelegalan posle prve akcije"})
MAX_SETTLE_ROUNDS = 12
DEFAULT_FAST_SAMPLES = 8
DEFAULT_DETAILED_SAMPLES = 64
TIE_SIGMAS = 2.0
# Izmereno iz memorijskih snimaka 2026-10-31 10:39-10:52 UTC (Multiplier
# Mushrooms): score_multiplier raste u koracima od +1 po pecurki, i novi
# mnozilac vec vazi za poene istog poteza (2044 -> 2236 = 12 celija x 16).
MUSHROOM_MULTIPLIER_STEP = 1.0
REFILL_MIN_TILES = 150

POLICY_DOC = (
    "choose_action (ista za sve pocetne akcije): (1) pun buster se ispaljuje "
    "pre sledeceg swipe-a; (2) ako postoji swipe sa garantovanim extra, igra se "
    "najbolji takav (perk ceka); (3) u poslednjem redu partije, pred swipe koji "
    "predaje red, trosi se perk sa najboljom metom ako mu je heuristika > 0 "
    "(Remove Cross/Hammer: deterministicke jedinice + korisno punjenje; Energy "
    "Boost: dodatno korisno punjenje najboljeg swipe-a); u ranijim redovima perk "
    "se cuva i pise se kao zaostao pri predaji; (4) inace pohlepni swipe po "
    "heuristici = deterministicke jedinice + move_value ako je extra garantovan "
    "+ charge_cell_value po korisnoj plavoj (data/charge_value.json). Nasumicne "
    "mete u heuristici su procenjene jednim fiksnim uzorkom (Random(0)), ne "
    "uzorkom grane."
)

SUPPORTED_PERKS = {ms.PERK_REMOVE_CROSS, ms.PERK_HAMMER, ms.PERK_ENERGY_BOOST}
PERK_LABELS = {
    ms.PERK_REMOVE_CROSS: "Remove Cross", ms.PERK_HAMMER: "Hammer",
    ms.PERK_ENERGY_BOOST: "Energy Boost", ms.PERK_SHUFFLE: "Shuffle",
    ms.PERK_STAR_MAKER: "Star Maker", ms.PERK_TELEPORT: "Teleport",
    ms.PERK_CHECKERBOARD: "Checkerboard", ms.PERK_MINI_CLEO: "Mini Cleo",
    ms.PERK_MINI_COBRA: "Mini Cobra", ms.PERK_MINI_MASTERMIND: "Mini Mastermind",
    ms.PERK_MINI_WAND: "Mini Wand", ms.PERK_CREATE_LIGHTNING: "Create Lightning",
    ms.PERK_DETONATOR: "Detonator", ms.PERK_BOMB_DELIVERY: "Bomb Delivery",
}

# Pravila koja ucestvuju u rangiranju a nisu nezavisno potvrdjena na snimcima.
UNVERIFIED_RULES = {
    "doctor_color_selection": "Doctor Color: prebojavanje simulirano; izbor putanje uniforman, pickBehavior stringovi jos nepotvrdjeni",
    "booster_empirical": "efekat bustera nije simuliran: empirijski prosek poena po aktivaciji",
    "refill_uniform": "raspodela dopune nije izmerena za ovaj mod: ravnomerne boje (neprovereno)",
    "energy_boost_order": "da li Energy Boost vazi za Remove Cross clear pre swipe-a nije potvrdjeno; modelovano: vazi samo za sledeci swipe",
    "growth_unmodeled": "rast mnozioca ovog moda nije modelovan (mnozilac drzan konstantnim)",
    "multiplier_estimated": "mnozilac nije iz memorije: procena iz prethodnih potvrdjenih poteza",
    "booster_choice": "izbor zavisi od bustera (empirijski poeni, tabla posle bustera nije simulirana): izbor mete nepotvrdjen",
    "limit_undecided": "deo grana ni posle produzenja nije stigao do predaje reda: pobednik nije utvrdjen",
}


# ---------------------------------------------------------------------------
# Profili konteksta


@dataclass(frozen=True)
class ContextProfile:
    key: str
    label: str
    has_opponent: bool
    scope: str
    clock_bound: bool
    economy_key: str


PROFILES = {
    CTX_VERSUS: ContextProfile(CTX_VERSUS, "Versus", True, "red (movesPerTurn + extra)", True, "versus_2"),
    CTX_SHOWDOWN: ContextProfile(CTX_SHOWDOWN, "Showdown", False, "runda na sat", True, "solo_race"),
    CTX_RUMBLE: ContextProfile(CTX_RUMBLE, "Rumble", False, "runda na sat", True, "solo_race"),
    CTX_PARTY: ContextProfile(CTX_PARTY, "Party", False, "runda na sat", True, "solo_race"),
    CTX_SOLO_CHALLENGE: ContextProfile(
        CTX_SOLO_CHALLENGE, "Solo Challenge", False, "preostali potezi partije", False, "solo_challenge"
    ),
}


def _load_economy() -> dict:
    try:
        return json.loads((ROOT / "data" / "charge_value.json").read_text(encoding="utf-8")).get("modes") or {}
    except (OSError, ValueError):
        return {}


ECONOMY = _load_economy()


def economy_for(profile: ContextProfile) -> dict:
    values = ECONOMY.get(profile.economy_key) or ECONOMY.get("solo_6") or {}
    return {
        "charge_cell_value": float(values.get("charge_cell_value", ms.FALLBACK_CHARGE_CELL_VALUE)),
        "booster_value": float(values.get("booster_value", 35.0)),
        "move_value": float(values.get("move_value", 15.0)),
    }


# ---------------------------------------------------------------------------
# Memorijski snimci: kompaktan indeks (vreme, pravila, mnozilac, skor)


def _parse_utc(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def run_timestamp(run: str) -> float | None:
    """Lokalno vreme iz imena run foldera, kao Unix vreme."""
    try:
        base = dt.datetime.strptime(run[:19], "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
    millis = int(run[20:23]) if len(run) >= 23 and run[20:23].isdigit() else 0
    return base.timestamp() + millis / 1000.0


def _snapshot_row(snapshot: dict) -> dict | None:
    state = snapshot.get("state") or {}
    rules = state.get("rules") or {}
    players = state.get("players") or []
    me = next((p for p in players if p.get("player_type") == 0), None)
    if not rules or me is None:
        return None
    op = next((p for p in players if p.get("player_type") != 0), None)
    t = _parse_utc(snapshot.get("captured_at"))
    if t is None:
        return None
    return {
        "t": round(t, 3), "id": rules.get("id"), "title": rules.get("title"),
        "pvp": rules.get("pvp_mode"), "rumble": rules.get("rumble_type"),
        "colors": rules.get("colors_count"), "mpt": rules.get("moves_per_turn"),
        "tpt": rules.get("time_per_turn"), "extra": rules.get("extra_move_enabled"),
        "rounds_total": state.get("rounds_total"), "round": state.get("current_round"),
        "moves": state.get("moves"), "time": state.get("remaining_time"),
        "my_turn": me.get("is_my_turn"), "score": me.get("score"),
        "mult": me.get("score_multiplier"), "energy": me.get("energy"),
        "energy_max": me.get("energy_to_ability"), "ability": me.get("special_ability_type"),
        "op_score": (op or {}).get("score"), "op_mult": (op or {}).get("score_multiplier"),
        "op_ability": (op or {}).get("special_ability_type"),
    }


def build_snapshot_index(force: bool = False, verbose: bool = False) -> int:
    """Skenira board_snapshots*.jsonl jednom (inkrementalno) i pamti indeks."""
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    state = {}
    if SNAPSHOT_INDEX_STATE.exists() and not force:
        try:
            state = json.loads(SNAPSHOT_INDEX_STATE.read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    _SNAPSHOT_CACHE.clear()
    rows = load_snapshot_index() if state else []
    added = 0
    for path in sorted(glob.glob(str(SNAPSHOT_DIR / "board_snapshots*.jsonl"))):
        name = os.path.basename(path)
        size = os.path.getsize(path)
        if state.get(name) == size:
            continue
        if verbose:
            print(f"  indeksiram {name} ({size // 1_000_000} MB)", flush=True)
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if '"players"' not in line:
                    continue
                try:
                    row = _snapshot_row(json.loads(line).get("snapshot") or {})
                except ValueError:
                    continue
                if row is not None:
                    rows.append(row)
                    added += 1
        state[name] = size
    unique = {(row["t"], row.get("score")): row for row in rows}
    rows = sorted(unique.values(), key=lambda r: r["t"])
    with SNAPSHOT_INDEX_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    SNAPSHOT_INDEX_STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    _SNAPSHOT_CACHE.clear()
    return added


_SNAPSHOT_CACHE: dict = {}


def load_snapshot_index() -> list[dict]:
    if "rows" not in _SNAPSHOT_CACHE:
        rows = []
        if SNAPSHOT_INDEX_PATH.exists():
            with SNAPSHOT_INDEX_PATH.open(encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
        _SNAPSHOT_CACHE["rows"] = rows
        _SNAPSHOT_CACHE["times"] = [row["t"] for row in rows]
    return _SNAPSHOT_CACHE["rows"]


def snapshot_before(ts: float | None, our_score=None) -> dict | None:
    """Poslednji snimak NE POSLE odluke (u prozoru) -- samo ono sto je igrac video."""
    if ts is None:
        return None
    rows = load_snapshot_index()
    if not rows:
        return None
    hi = bisect.bisect_right(_SNAPSHOT_CACHE["times"], ts)
    fallback = None
    for index in range(hi - 1, -1, -1):
        row = rows[index]
        if ts - row["t"] > SNAPSHOT_MATCH_WINDOW:
            break
        if our_score is None or row.get("score") == our_score:
            return row
        if fallback is None:
            fallback = dict(row, mult_unreliable=True)
    return fallback


def snapshots_between(t0: float, t1: float) -> list[dict]:
    rows = load_snapshot_index()
    times = _SNAPSHOT_CACHE.get("times") or []
    lo = bisect.bisect_left(times, t0)
    hi = bisect.bisect_right(times, t1)
    return rows[lo:hi]


# ---------------------------------------------------------------------------
# Odluke iz Debug/runs


def _load_json(path: Path):
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _as_int(value):
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def classify_context(move: dict, snapshot: dict | None = None) -> tuple[str | None, str]:
    sc = move.get("strategy_context") or {}
    mode = sc.get("mode")
    if mode == "versus_2":
        return CTX_VERSUS, "move.json strategy_context=versus_2"
    if mode != "solo_6":
        return None, f"nepoznat strategy mode {mode!r}"
    if sc.get("solo_challenge"):
        return CTX_SOLO_CHALLENGE, "move.json solo_challenge"
    if snapshot is not None and snapshot.get("rumble") in _RUMBLE_TYPE_CONTEXT:
        return _RUMBLE_TYPE_CONTEXT[snapshot["rumble"]], "memorija rumble_type"
    if snapshot is not None and snapshot.get("pvp") == 1:
        return CTX_SHOWDOWN, "memorija pvp_mode=1 (solo trka na sat)"
    resolved = (move.get("screen_state_read") or {}).get("resolved") or {}
    rounds = resolved.get("total_rounds") or (move.get("round_state") or {}).get("total")
    if rounds in _ROUNDS_CONTEXT:
        return _ROUNDS_CONTEXT[rounds], f"heuristika ({rounds} runde)"
    return CTX_SHOWDOWN, "heuristika (podrazumevano)"


@dataclass
class Decision:
    run: str
    path: Path
    ts: float | None
    move: dict
    delta: dict
    candidates: list
    context: str | None
    context_source: str
    snapshot: dict | None
    mode: str
    round: int | None
    total_rounds: int | None
    remaining_moves: int | None
    turn_owner: str | None
    time_left: float | None
    seconds_per_move: float | None
    our_score: int | None
    opp_score: int | None
    booster_charge: int | None
    booster_max: int | None
    perks: tuple
    proposed: dict
    sent: bool
    outcome: dict
    multiplier: float | None = None
    multiplier_source: str = "nepoznat"
    match_id: int | None = None
    match_index: int = 0
    perk_status: list = field(default_factory=list)
    booster_history_units: list = field(default_factory=list)

    @property
    def time_label(self) -> str:
        return self.run[11:19].replace("-", ":")


def _proposed_action(move: dict) -> dict:
    action = move.get("selected_action") or "none"
    best = move.get("best_move") or {}
    if action == "activate_perk":
        perk = move.get("selected_perk_action") or {}
        target = perk.get("target")
        if isinstance(target, list) and len(target) == 2 and not isinstance(target[0], list):
            target = tuple(target)
        return {"type": "perk", "perk": perk.get("perk"), "slot": perk.get("slot_number"), "target": target}
    if action == "activate_booster":
        return {"type": "booster"}
    if action == "move" and best.get("start") is not None:
        return {
            "type": "swap", "start": tuple(best["start"]), "target": tuple(best["target"]),
            "direction": best.get("direction"), "instant_score": _as_float(best.get("instant_score")),
        }
    return {"type": "none", "action": action}


def _outcome(move: dict, delta: dict | None) -> dict:
    if not delta:
        return {"status": "bez_zapisa", "note": "nema observed_delta.json (prekid snimanja ili poslednji run)"}
    score = delta.get("score_delta") or {}
    state = delta.get("state_delta") or {}
    after = state.get("after") or {}
    before = state.get("before") or {}
    changed = _as_int((delta.get("board_delta") or {}).get("changed_count"))
    points = _as_int(score.get("our_points_gained")) if score.get("confirmed") else None
    result = {
        "status": "potvrdjeno", "source": "observed_delta", "points": points,
        "kept_turn": state.get("kept_the_turn"), "after_turn_owner": after.get("turn_owner"),
        "after_round": after.get("current_round"), "after_remaining_moves": after.get("remaining_moves"),
        "changed_cells": changed, "after_run": delta.get("after_run"),
        "charge_gained": state.get("booster_charge_gained"),
    }
    if not score.get("confirmed"):
        after_score = (score.get("after") or {}).get("our_score")
        before_score = (score.get("before") or {}).get("our_score")
        if after_score == 0 and (before_score or 0) > 0:
            result["status"] = "kraj_partije"
            result["note"] = "skor posle poteza je 0 (partija gotova ili nova): observed_delta ne potvrdjuje ishod"
        else:
            result["status"] = "nepotvrdjeno"
            result["note"] = "poeni nisu potvrdjeni (nepotpun prelaz)"
    elif changed == 0 and points == 0 and move.get("selected_action") == "move":
        result["status"] = "progutan"
        result["note"] = "tabla nepromenjena i 0 poena: swipe nije prosao"
    if before.get("current_round") is not None and after.get("current_round") not in (None, before.get("current_round")):
        result["round_changed"] = True
    return result


def memory_outcome(decision: "Decision", next_ts: float | None) -> dict | None:
    """Ishod odluke iz memorijskih snimaka posle nje (samo za proveru)."""
    if decision.ts is None or decision.our_score is None:
        return None
    end = min(next_ts, decision.ts + OUTCOME_WINDOW_SECONDS) if next_ts else decision.ts + OUTCOME_WINDOW_SECONDS
    rows = snapshots_between(decision.ts, end)
    best = None
    turn_passed = False
    for row in rows:
        score = row.get("score")
        if score is None or score < decision.our_score:
            break  # nova partija
        best = row
        if row.get("my_turn") is False:
            turn_passed = True
            break
    if best is None:
        return None
    return {
        "points": int(best["score"]) - int(decision.our_score),
        "turn_passed": turn_passed,
        "mult_after": best.get("mult"),
        "at": best["t"],
    }


def load_decision(run_dir: Path) -> Decision | None:
    run_dir = Path(run_dir)
    move = _load_json(run_dir / "move.json")
    if not isinstance(move, dict):
        return None
    delta = _load_json(run_dir / "observed_delta.json")
    candidates = _load_json(run_dir / "candidates.json")
    resolved = (move.get("screen_state_read") or {}).get("resolved") or {}
    ts = run_timestamp(run_dir.name)
    our_score = _as_int(resolved.get("our_score"))
    snapshot = snapshot_before(ts, our_score)
    context, source = classify_context(move, snapshot)
    turn = move.get("turn_state") or {}
    booster = move.get("booster_state") or {}
    sent = bool(move.get("play_enabled")) and bool(
        move.get("will_play") or move.get("will_activate_booster") or move.get("will_activate_perk")
    )
    return Decision(
        run=run_dir.name, path=run_dir, ts=ts, move=move, delta=delta or {},
        candidates=candidates if isinstance(candidates, list) else [],
        context=context, context_source=source, snapshot=snapshot,
        mode=str(move.get("mode") or "None"),
        round=_as_int(resolved.get("current_round") or (move.get("round_state") or {}).get("current")),
        total_rounds=_as_int(resolved.get("total_rounds") or (move.get("round_state") or {}).get("total")),
        remaining_moves=_as_int(resolved.get("remaining_moves", turn.get("remaining_moves"))),
        turn_owner=resolved.get("turn_owner"),
        time_left=_as_float(turn.get("time_left_seconds")),
        seconds_per_move=_as_float(turn.get("seconds_per_move")),
        our_score=our_score, opp_score=_as_int(resolved.get("opponent_score")),
        booster_charge=_as_int(booster.get("current", resolved.get("booster_charge"))),
        booster_max=_as_int(booster.get("maximum", resolved.get("booster_maximum"))),
        perks=tuple(move.get("selected_perks") or ("none", "none")),
        proposed=_proposed_action(move), sent=sent, outcome=_outcome(move, delta),
    )


def list_runs(day: str | None = None) -> list[str]:
    names = sorted(n for n in os.listdir(RUNS_DIR) if (RUNS_DIR / n).is_dir())
    return [n for n in names if n.startswith(day)] if day else names


def load_decisions(names) -> list[Decision]:
    return [d for d in (load_decision(RUNS_DIR / n) for n in names) if d is not None]


def segment_matches(decisions: list[Decision]) -> list[list[Decision]]:
    """Partija = uzastopni runovi istog konteksta i moda, bez pauze > 240 s i
    bez pada naseg skora ili runde (to se desava samo kad pocne nova partija)."""
    matches: list[list[Decision]] = []
    previous = None
    for decision in sorted(decisions, key=lambda d: d.run):
        new = previous is None
        if not new:
            gap = (decision.ts or 0) - (previous.ts or 0)
            new = (
                decision.context != previous.context
                or decision.mode != previous.mode
                or gap > MATCH_GAP_SECONDS
                or (decision.our_score is not None and previous.our_score is not None
                    and decision.our_score < previous.our_score)
                or (decision.round is not None and previous.round is not None
                    and decision.round < previous.round)
            )
        if new:
            matches.append([])
        matches[-1].append(decision)
        previous = decision
    for match_id, members in enumerate(matches, start=1):
        for index, decision in enumerate(members):
            decision.match_id = match_id
            decision.match_index = index
        annotate_match(members)
    return matches


def _observed_turn_flags(decision: Decision, nxt: Decision | None, out: dict) -> None:
    """Dve odvojene stvarne cinjenice, samo za proveru:

    * ``next_is_ours`` -- sledeca odluka (neposredan nastavak) je i dalje nasa;
    * ``observed_extra`` -- swipe nije potrosio potez (preostali potezi sledece
      nase odluke nisu manji).

    ``kept_the_turn`` iz observed_delta je u versusu False i kad potezi padnu
    sa 3 na 2 a mi i dalje igramo, pa se ne koristi kao ni jedno ni drugo.
    """
    out["kept_the_turn_record"] = out.get("kept_turn")
    passed = out.get("after_turn_owner") not in (None, "us") or out.get("round_changed") \
        or bool((out.get("memory") or {}).get("turn_passed"))
    immediate = (nxt is not None and out.get("after_run") == nxt.run and nxt.round == decision.round
                 and nxt.turn_owner in (None, "us"))
    if passed:
        out["next_is_ours"] = False
    elif immediate:
        out["next_is_ours"] = True
    else:
        out["next_is_ours"] = None
    out["observed_extra"] = None
    if decision.proposed["type"] == "swap":
        if immediate and nxt.remaining_moves is not None and decision.remaining_moves is not None:
            out["observed_extra"] = nxt.remaining_moves >= decision.remaining_moves
        elif passed and decision.remaining_moves == 1:
            out["observed_extra"] = False
    # Zadrzano zbog kompatibilnosti starih izvestaja: "jos jedna nasa odluka".
    out["kept_turn"] = out["next_is_ours"]


def annotate_match(members: list[Decision]) -> None:
    """Mnozilac, istorija bustera i status perk slotova -- samo iz proslosti.

    Ishod odluke i (ako observed_delta ne potvrdjuje) ishod iz memorije se
    dopisuju u ``outcome`` za proveru, a u procenu ulaze tek kod SLEDECIH odluka.
    """
    seen_perk = [None, None]
    ratios: list[float] = []
    booster_units: list[float] = []
    for position, decision in enumerate(members):
        snap = decision.snapshot
        if snap and snap.get("mult") and not snap.get("mult_unreliable"):
            decision.multiplier = float(snap["mult"])
            decision.multiplier_source = "memorija (score_multiplier)"
        elif ratios:
            decision.multiplier = statistics.median(ratios[-3:])
            decision.multiplier_source = f"procena iz {min(3, len(ratios))} prethodna potvrdjena poteza"
        elif (decision.our_score or 0) == 0 and (decision.round or 1) == 1:
            decision.multiplier = 1.0
            decision.multiplier_source = "pocetak partije (x1)"
        else:
            decision.multiplier = None
            decision.multiplier_source = "nepoznat"
        decision.booster_history_units = list(booster_units)
        status = []
        for slot, perk in enumerate(decision.perks[:2]):
            if perk and perk != ms.PERK_NONE:
                seen_perk[slot] = perk
                status.append({"slot": slot + 1, "perk": perk, "status": "dostupan"})
            elif seen_perk[slot]:
                low_time = decision.time_left is not None and decision.time_left < 8.0
                status.append({"slot": slot + 1, "perk": seen_perk[slot],
                               "status": "nepoznato (GUI ga skriva pri malo vremena)" if low_time else "iskoriscen"})
            else:
                status.append({"slot": slot + 1, "perk": None, "status": "prazan"})
        decision.perk_status = status
        next_ts = members[position + 1].ts if position + 1 < len(members) else None
        mem = memory_outcome(decision, next_ts)
        if mem is not None:
            decision.outcome["memory"] = mem
            if decision.outcome.get("status") in ("kraj_partije", "nepotvrdjeno", "bez_zapisa") and mem["points"] >= 0:
                decision.outcome["points"] = mem["points"]
                decision.outcome["status"] = "potvrdjeno"
                decision.outcome["source"] = "memorija"
                if mem["turn_passed"]:
                    decision.outcome["after_turn_owner"] = "opponent"
                    decision.outcome["kept_turn"] = False
        out = decision.outcome
        nxt = members[position + 1] if position + 1 < len(members) else None
        _observed_turn_flags(decision, nxt, out)
        if out.get("status") == "potvrdjeno" and out.get("points") and out["points"] > 0:
            proposed = decision.proposed
            if proposed["type"] == "swap" and (proposed.get("instant_score") or 0) > 0:
                ratios.append(out["points"] / proposed["instant_score"])
            if proposed["type"] == "booster" and decision.multiplier:
                booster_units.append(out["points"] / decision.multiplier)


def skip_reason(decision: Decision) -> str | None:
    if decision.context is None:
        return f"kontekst nije prepoznat ({decision.context_source})"
    if decision.turn_owner not in (None, "us"):
        return f"nije nas red (turn_owner={decision.turn_owner})"
    board = decision.move.get("board")
    if not board or not decision.move.get("special_board"):
        return "nema table u move.json"
    if any(value == 0 for row in board for value in row):
        return "tabla ima neprepoznata polja"
    if decision.proposed["type"] == "none":
        return f"bot nije predlozio akciju (selected_action={decision.proposed.get('action')}, gate={decision.move.get('decision_gate')})"
    return None


# ---------------------------------------------------------------------------
# Pravila moda i raspodela dopune


def load_refill_stats() -> dict:
    data = _load_json(REFILL_STATS_PATH)
    return data if isinstance(data, dict) else {}


_REFILL_STATS = None


def refill_stats() -> dict:
    global _REFILL_STATS
    if _REFILL_STATS is None:
        _REFILL_STATS = load_refill_stats()
    return _REFILL_STATS


@dataclass
class RuleSet:
    mode: str
    game_mode: object
    square: bool
    explode: bool
    rally: dict | None
    colors: tuple
    refill_table: tuple  # ((color, special), weight), ...
    refill_source: str
    lava_columns: tuple
    extra_enabled: bool
    solo_board: bool
    multiplier_growth: str | None
    move: dict
    unverified: set = field(default_factory=set)

    def stack(self, lava_columns=None):
        move = self.move
        stack = contextlib.ExitStack()
        line = move.get("line_destruction") or [False, False]
        for manager in (
            ms.color_crush_active(bool(move.get("color_crush")), single_player=self.solo_board),
            ms.charge_colors_active(tuple(move.get("energized_colors") or ()), move.get("engine_charge_colors")),
            ms.mushroom_multipliers_active(bool(move.get("mushroom_multipliers"))),
            ms.vertical_matches_destroy_color_active(bool(move.get("vertical_matches_destroy_color"))),
            ms.matches_destroy_color_active(bool(move.get("matches_destroy_color"))),
            ms.all_specials_lightning_active(bool(move.get("all_specials_lightning"))),
            ms.every_match_is_special_active(bool(move.get("every_match_is_special"))),
            ms.line_destruction_active(bool(line[0]), bool(line[1])),
            ms.floor_lava_checked_columns(self.lava_columns if lava_columns is None else lava_columns),
            ms.funky_tile_cells(tuple(tuple(c) for c in (move.get("funky_tile_cells") or ()))),
            ms.jelly_zone_cells(tuple(tuple(c) for c in (move.get("jelly_zone_cells") or ()))),
        ):
            stack.enter_context(manager)
        return stack

    def draw_tile(self, rng: random.Random) -> tuple[int, int]:
        roll = rng.random()
        acc = 0.0
        for (color, special), weight in self.refill_table:
            acc += weight
            if roll <= acc:
                return color, special
        return self.refill_table[-1][0]


def build_rules(decision: Decision) -> RuleSet:
    move = decision.move
    rally = {int(k): float(v) for k, v in (move.get("score_rally_values") or {}).items()} or None
    board = move["board"]
    present = sorted({v for row in board for v in row if 1 <= v <= 7})
    snap = decision.snapshot or {}
    colors = tuple(range(1, int(snap.get("colors") or 6) + 1))
    if any(c not in colors for c in present):
        colors = tuple(sorted(set(colors) | set(present)))
    unverified = set()
    all_stats = refill_stats().get("modes") or {}
    stats = all_stats.get(f"{move.get('mode')}|{decision.context}")
    scope = "isti mod i kontekst"
    if not stats or stats.get("tiles", 0) < REFILL_MIN_TILES:
        stats = all_stats.get(str(move.get("mode")))
        scope = "isti mod, svi konteksti"
    if snap.get("id") == "square-match":
        # Legacy mode=None buckets mix unrelated rulesets and booster pieces
        # (including skulls/mushrooms). They are not Square Match refill data.
        stats = all_stats.get(f"square-match|{decision.context}")
        scope = "square-match rules id i kontekst"
    if stats and stats.get("tiles", 0) >= REFILL_MIN_TILES:
        total = float(sum(stats["counts"].values()))
        table = tuple(
            ((int(key.split(":")[0]), int(key.split(":")[1])), count / total)
            for key, count in sorted(stats["counts"].items())
            if int(key.split(":")[0]) in colors or int(key.split(":")[0]) >= 1
        )
        source = f"izmereno ({scope}): {stats['tiles']} plocica posle smirivanja iz {stats.get('runs')} poteza"
    else:
        table = tuple(((c, 0), 1.0 / len(colors)) for c in colors)
        source = "ravnomerno (neprovereno: premalo izmerene dopune za ovaj mod)"
        unverified.add("refill_uniform")
    game_mode = ms.normalize_game_mode(move.get("mode"))
    growth = None
    if game_mode is ms.MULTIPLIER_MUSHROOMS_MODE:
        growth = "mushrooms"
    elif game_mode is ms.MOVES_MULTIPLIER_MODE:
        growth = "per_move"
    elif ms.is_multiplier_growth_mode(game_mode):
        unverified.add("growth_unmodeled")
    return RuleSet(
        mode=str(move.get("mode") or "None"), game_mode=game_mode,
        square=bool(move.get("allow_square_matches")),
        explode=bool(move.get("specials_explode_immediately")),
        rally=rally, colors=colors, refill_table=table, refill_source=source,
        # runtime.floor_lava_debug_state pise kolone 1-based; simulator radi 0-based.
        lava_columns=tuple(int(c) - 1 for c in ((move.get("floor_lava_state") or {}).get("columns") or ())),
        extra_enabled=snap.get("extra") is not False,
        solo_board=decision.context != CTX_VERSUS,
        multiplier_growth=growth, move=move, unverified=unverified,
    )


# ---------------------------------------------------------------------------
# Stanje i akcije


@dataclass
class GameState:
    board: list
    special: list
    moves_left: int
    charge: float | None
    charge_max: float | None
    perks: tuple
    eb_pending: bool
    sm: float | None          # score_multiplier iz memorije (raste u nekim modovima)
    legend: float             # poeni po jedinici simulatora pri sm=1 (ili ceo mnozilac kad sm nije poznat)
    lava: tuple
    time_left: float | None
    steps: int = 0
    over: str | None = None

    @property
    def multiplier(self) -> float:
        return self.legend * self.sm if self.sm is not None else self.legend

    @property
    def booster_ready(self) -> bool:
        return self.charge is not None and self.charge_max is not None and self.charge >= self.charge_max

    def copy(self) -> "GameState":
        return replace(self, board=[r[:] for r in self.board], special=[r[:] for r in self.special])


def _units(result, rules: RuleSet) -> float:
    return float(ms._instant_score(result, rules.rally, rules.game_mode))


def _legal(result) -> bool:
    return result is not None and bool(result.matches or result.activated_specials or result.created_specials)


def _grid_key(board, special, lava=()):
    return (np.asarray(board, dtype=np.int16).tobytes(), np.asarray(special, dtype=np.int16).tobytes(), tuple(lava))


def _uses_random_targets(result) -> bool:
    try:
        return bool(ms._result_activated_random_target_special(result))
    except Exception:
        return False


def _first_boundary(result) -> dict | None:
    for event in result.intent_events or []:
        if event.get("type") == "uncertain_refill_boundary":
            return {"cascade": event.get("after_cascade"), "reason": event.get("reason")}
    return None


def _without_perk(perks: tuple, perk: str) -> tuple:
    items = list(perks)
    if perk in items:
        items.remove(perk)
    return tuple(items)


def _sim_swap(board, candidate, rules, lava, rng):
    with rules.stack(lava), ms.random_special_target_rng(rng):
        return ms._simulate_created_candidate(
            board, candidate, allow_square_matches=rules.square, mode=rules.mode,
            include_future_value=False, explode_created_specials_immediately=rules.explode,
        )


def _sim_clear(board, special, cells, rules, lava, rng):
    with rules.stack(lava), ms.random_special_target_rng(rng):
        return ms._simulate_clear_cells_perk(
            board, special, cells, mode=rules.mode, allow_square_matches=rules.square,
            explode_created_specials_immediately=rules.explode,
        )


def legal_swaps(state: GameState, rules: RuleSet, cache: dict) -> list:
    """Sve legalne zamene (oba smera) sa deterministickim rezultatom.

    Nasumicne mete u ovom rezultatu su iz svezeg Random(0) po kandidatu, pa je
    rezultat isti bez obzira na redosled poziva i kes."""
    key = ("swaps",) + _grid_key(state.board, state.special, state.lava)
    if key in cache:
        return cache[key]
    out = []
    for candidate in ms.generate_candidates(state.board, state.special):
        for oriented in (candidate, ms.flip_swap_candidate(candidate)):
            result = _sim_swap(state.board, oriented, rules, state.lava, random.Random(0))
            if _legal(result):
                out.append((oriented, result))
    cache[key] = out
    return out


def perk_cells(perk: str, target) -> set:
    size = ms.BOARD_SIZE
    if perk == ms.PERK_REMOVE_CROSS:
        row, col = target
        return {(row, i) for i in range(size)} | {(i, col) for i in range(size)}
    if perk == ms.PERK_HAMMER:
        return {tuple(target)}
    return set()


def swipe_label(candidate) -> str:
    (r0, c0), (r1, c1) = candidate.start, candidate.target
    return f"swipe ({r0},{c0})->({r1},{c1}) {candidate.direction.value}"


def _activates_special(candidate) -> bool:
    special = candidate.special_board
    return any(ms._is_activatable_special(int(special[r][c])) for r, c in (candidate.start, candidate.target))


def legal_actions(state: GameState, rules: RuleSet, cache: dict) -> tuple[list[dict], list[dict]]:
    """(legalne akcije, legalne ali nepodrzane). Bez ikakvog score gate-a.

    Smerovi swipe-a i mete perka koje daju potpuno isti deterministicki ishod
    (tabla, specijali, jedinice, extra, plave, nasumicnost) dele racunanje;
    ostali se cuvaju odvojeno.
    """
    if state.over:
        return [], []
    actions, unsupported = [], []
    groups: dict = {}
    for candidate, result in legal_swaps(state, rules, cache):
        sig = ("swap", _grid_key(result.board, result.special_board), round(_units(result, rules), 4),
               result.extra_moves > 0, round(float(result.blue_cells), 4), _uses_random_targets(result))
        label = swipe_label(candidate)
        if sig in groups:
            groups[sig]["equivalent"].append(label)
            continue
        entry = {
            "key": f"swap {candidate.start}->{candidate.target}", "kind": "swap", "label": label,
            "start": tuple(candidate.start), "target": tuple(candidate.target),
            "direction": candidate.direction.value, "candidate": candidate, "result": result,
            "equivalent": [], "special_activation": _activates_special(candidate),
            "det_units": _units(result, rules), "guaranteed_extra": result.extra_moves > 0,
        }
        groups[sig] = entry
        actions.append(entry)
    if state.charge is not None and state.booster_ready:
        actions.append({"key": "booster", "kind": "booster", "label": "aktiviraj buster", "equivalent": [],
                        "unverified": {"booster_empirical"}})
    for perk in dict.fromkeys(state.perks):
        if perk not in SUPPORTED_PERKS:
            unsupported.append({"perk": perk, "label": PERK_LABELS.get(perk, perk),
                                "reason": "efekat perka nije verno simuliran u analizatoru -- nije rangiran"})
            continue
        if perk == ms.PERK_ENERGY_BOOST:
            if state.charge is None or state.charge_max is None:
                unsupported.append({"perk": perk, "label": "Energy Boost",
                                    "reason": "punjenje nepoznato -- vrednost se ne moze proceniti"})
                continue
            actions.append({"key": "perk energy_boost", "kind": "perk", "perk": perk, "target": None,
                            "label": "Energy Boost", "equivalent": []})
            continue
        seen = {}
        for row in range(ms.BOARD_SIZE):
            for col in range(ms.BOARD_SIZE):
                if perk == ms.PERK_HAMMER and not ms._is_board_piece(state.board[row][col]):
                    continue
                result = _sim_clear(state.board, state.special, perk_cells(perk, (row, col)), rules,
                                    state.lava, random.Random(0))
                sig = ("perk", _grid_key(result.board, result.special_board), round(_units(result, rules), 4),
                       _uses_random_targets(result))
                label = f"{PERK_LABELS[perk]} @({row},{col})"
                if sig in seen:
                    seen[sig]["equivalent"].append(label)
                    continue
                entry = {"key": f"perk {perk}@({row},{col})", "kind": "perk", "perk": perk, "target": (row, col),
                         "label": label, "equivalent": [], "det_units": _units(result, rules),
                         "det_blue": float(result.blue_cells)}
                seen[sig] = entry
                actions.append(entry)
    return actions, unsupported


# ---------------------------------------------------------------------------
# step: jedna akcija, stvarni poeni i dnevnik dogadjaja


def _grid_lists(grid):
    return [list(map(int, row)) for row in grid]


# docs/doctor_color.md, engine colors translated to move_strategy colors.
DOCTOR_COLOR_PATHS = tuple(tuple(getattr(ms, color) for color in path) for path in (
    ("ORANGE", "GREEN", "YELLOW"), ("ORANGE", "YELLOW", "GREEN"),
    ("ORANGE", "PURPLE", "YELLOW"), ("ORANGE", "YELLOW", "PURPLE"),
    ("GREEN", "YELLOW", "PURPLE"), ("GREEN", "ORANGE", "PURPLE"),
    ("GREEN", "PURPLE", "YELLOW"), ("GREEN", "YELLOW", "ORANGE"),
    ("PURPLE", "ORANGE", "YELLOW"), ("PURPLE", "YELLOW", "ORANGE"),
    ("PURPLE", "GREEN", "YELLOW"), ("PURPLE", "ORANGE", "GREEN"),
    ("YELLOW", "ORANGE", "PURPLE"), ("YELLOW", "PURPLE", "GREEN"),
))


def doctor_color_paths(board):
    colors = {int(color) for row in board for color in row}
    return [path for path in DOCTOR_COLOR_PATHS if set(path) <= colors]


def doctor_color_convert(board, special, path):
    """Convert both sources before resolving matches; preserve special types.

    SPECIAL_MODE_TARGET represents engine BoardSpecial (16), which is excluded.
    The supported Square Match board has no multi-color mode pieces.
    """
    converted = _grid_lists(board)
    for source, target in zip(path, path[1:]):
        for r, row in enumerate(converted):
            for c, color in enumerate(row):
                if color == source and special[r][c] != ms.SPECIAL_MODE_TARGET:
                    row[c] = target
    return converted


def _mushroom_count(result) -> float:
    """Broj sakupljenih pecurki (ne zbir 'kapa').

    Uz mushroom_multipliers simulator u `multiplier_mushrooms` sabira vrednost
    kape po boji (1-4). Memorijski snimci Multiplier Mushrooms Studio
    (2026-10-31 10:45-10:47 UTC) pokazuju score_multiplier u koracima od +1
    (15,16,17,...,27), pa se rast racuna po pecurki."""
    cells = sum(len(e.get("cells") or ()) for e in (result.intent_events or ()) if e.get("type") == "mushroom_collect")
    if cells:
        return float(cells)
    return 0.0 if ms.mushroom_multipliers_enabled() else float(result.multiplier_mushrooms)


def _apply_growth(state: GameState, rules: RuleSet, mushrooms: float, events: list) -> float:
    if mushrooms <= 0 or rules.multiplier_growth != "mushrooms":
        return 0.0
    if state.sm is None:
        events.append({"wave": "mnozilac", "note": "pecurka aktivirana, ali sm nije poznat iz memorije: rast nije modelovan"})
        return 0.0
    before = state.sm
    state.sm += mushrooms * MUSHROOM_MULTIPLIER_STEP
    events.append({"wave": "mnozilac", "from": before, "to": state.sm, "mushrooms": mushrooms})
    return state.sm - before


def _charge(state: GameState, gained: float, events: list, why: str) -> float:
    if state.charge is None or state.charge_max is None or gained <= 0:
        return 0.0
    before = state.charge
    useful = min(max(0.0, state.charge_max - before), gained)
    state.charge = min(state.charge_max, before + gained)
    events.append({"wave": "buster", "from": before, "to": state.charge, "gained": gained,
                   "useful": useful, "wasted": gained - useful, "why": why})
    return useful


def _result_events(result, cascade_offset=0) -> list:
    out = []
    for event in result.intent_events or []:
        item = {k: v for k, v in event.items() if k in ("type", "cascade", "kind", "color", "cells", "special",
                                                        "cell", "cleared_cells", "reason", "tile_count")}
        if "cascade" in item and isinstance(item["cascade"], (int, float)):
            item["cascade"] = item["cascade"] + cascade_offset
        out.append(item)
    return out


def _settle(state: GameState, rules: RuleSet, rng: random.Random, events: list, info: dict) -> float:
    """Dopuna (uzorkovana) i kaskade dok se tabla ne smiri. Vraca poene."""
    points = 0.0
    for wave in range(MAX_SETTLE_ROUNDS):
        holes = [(r, c) for r, row in enumerate(state.board) for c, v in enumerate(row) if v == ms.EMPTY]
        if holes:
            if info.get("first_unknown") is None:
                info["first_unknown"] = {"where": "dopuna", "tiles": len(holes), "wave": wave + 1}
            drawn = {}
            for r, c in holes:
                color, special = rules.draw_tile(rng)
                state.board[r][c] = color
                state.special[r][c] = special
                drawn[f"{color}:{special}"] = drawn.get(f"{color}:{special}", 0) + 1
            events.append({"wave": "dopuna", "n": len(holes), "cells": [list(h) for h in holes],
                           "drawn": drawn, "source": rules.refill_source})
        candidate = ms.MoveCandidate((0, 0), (0, 0), ms.Direction.RIGHT, state.board, state.special)
        with rules.stack(()), ms.random_special_target_rng(rng):
            result = ms.simulate_candidate(candidate, allow_square_matches=rules.square, mode=rules.mode,
                                           explode_created_specials_immediately=rules.explode)
        if not (result.matches or result.activated_specials):
            break
        growth = _apply_growth(state, rules, _mushroom_count(result), events)
        info["growth"] += growth
        units = _units(result, rules)
        wave_points = units * state.multiplier
        points += wave_points
        info["activated"] += float(result.activated_specials)
        info["blue"] += float(result.blue_cells)
        if result.extra_moves > 0:
            info["extra_uncertain"] = True
        events.append({"wave": "kaskada posle dopune", "events": _result_events(result),
                       "units": units, "multiplier": state.multiplier, "points": wave_points,
                       "extra": result.extra_moves > 0})
        state.board, state.special = _grid_lists(result.board), _grid_lists(result.special_board)
        if not any(v == ms.EMPTY for row in state.board for v in row):
            break
    return points


def _turn_check(state: GameState, profile: ContextProfile, max_steps: int) -> str | None:
    if state.moves_left <= 0:
        return "predaja (potezi)" if profile.has_opponent else "kraj (potezi)"
    if state.time_left is not None and state.time_left <= 0:
        return "predaja (sat)" if profile.has_opponent else "kraj (sat)"
    if state.steps >= max_steps:
        return ENDED_LIMIT
    return None


@dataclass
class StepResult:
    state: GameState
    points: float
    events: list
    info: dict


class Simulator:
    """Pravila igre jednog konteksta: legal_actions, step i kraj reda."""

    def __init__(self, rules: RuleSet, profile: ContextProfile, economy: dict, booster_units: float,
                 seconds_per_move: float, max_steps: int, final_turn: bool = False,
                 ability: int | None = None):
        self.ability = ability
        self.final_turn = final_turn
        self.rules = rules
        self.profile = profile
        self.economy = economy
        self.booster_units = booster_units
        self.seconds_per_move = seconds_per_move
        self.max_steps = max_steps
        self.cache: dict = {}

    def legal_actions(self, state: GameState):
        actions, unsupported = legal_actions(state, self.rules, self.cache)
        if self.ability == 27:
            for action in actions:
                if action["kind"] == "booster":
                    action["unverified"] = {"doctor_color_selection"}
        return actions, unsupported

    def step(self, state: GameState, action: dict, rng: random.Random) -> StepResult:
        rules = self.rules
        state = state.copy()
        events: list = []
        info = {"growth": 0.0, "activated": 0.0, "blue": 0.0, "first_unknown": None, "extra": False,
                "guaranteed_extra": False, "extra_uncertain": False, "unverified": set(action.get("unverified") or ()),
                "random": False}
        state.steps += 1
        points = 0.0
        kind = action["kind"]
        if kind == "booster" and self.ability == 27:
            info["unverified"].discard("booster_empirical")
            info["unverified"].add("doctor_color_selection")
            paths = doctor_color_paths(state.board)
            # A shuffled subset followed by a uniform choice has a uniform
            # marginal over available paths. Score-biased pickBehavior remains
            # unknown, explicitly carried as a limitation in every branch.
            path = rng.choice(paths) if paths else None
            events.append({"wave": "buster", "action": "aktivacija", "from": state.charge,
                           "to": 0.0, "ability": 27, "path": list(path) if path else [],
                           "note": "Doctor Color: dve boje u trecu, zatim kaskade; uniformni izbor putanje"})
            state.charge = 0.0
            info["random"] = bool(paths)
            info["first_unknown"] = {"where": "Doctor Color izbor putanje"} if paths else None
            if path:
                state.board = doctor_color_convert(state.board, state.special, path)
                points += _settle(state, rules, rng, events, info)
                _charge(state, info["blue"], events, "plave iz Doctor Color kaskada")
            if state.time_left is not None:
                state.time_left -= BOOSTER_SECONDS
        elif kind == "booster":
            points = self.booster_units * state.multiplier
            events.append({"wave": "buster", "action": "aktivacija", "from": state.charge, "to": 0.0,
                           "units": self.booster_units, "multiplier": state.multiplier, "points": points,
                           "note": "empirijski model, efekat na tabli nije simuliran"})
            state.charge = 0.0
            info["first_unknown"] = {"where": "buster (efekat nije simuliran)"}
            if state.time_left is not None:
                state.time_left -= BOOSTER_SECONDS
        elif kind == "perk" and action["perk"] == ms.PERK_ENERGY_BOOST:
            state.perks = _without_perk(state.perks, action["perk"])
            state.eb_pending = True
            events.append({"wave": "perk", "perk": "Energy Boost", "note": "sledeci swipe: direktan efekat puni buster"})
            if state.time_left is not None:
                state.time_left -= PERK_SECONDS
        elif kind == "perk":
            perk = action["perk"]
            state.perks = _without_perk(state.perks, perk)
            result = _sim_clear(state.board, state.special, perk_cells(perk, action["target"]), rules, state.lava, rng)
            info["random"] = _uses_random_targets(result)
            if info["random"]:
                info["first_unknown"] = {"where": "nasumicna meta specijala", "wave": 1}
            growth = _apply_growth(state, rules, _mushroom_count(result), events)
            info["growth"] += growth
            units = _units(result, rules)
            points += units * state.multiplier
            info["activated"] += float(result.activated_specials)
            info["blue"] += float(result.blue_cells)
            events.append({"wave": "perk", "perk": PERK_LABELS[perk], "target": list(action["target"]),
                           "events": _result_events(result), "units": units, "multiplier": state.multiplier,
                           "points": units * state.multiplier})
            if state.eb_pending:
                events.append({"wave": "perk", "note": "Energy Boost ostaje za sledeci swipe (neprovereno)"})
                info["unverified"].add("energy_boost_order")
            state.board, state.special = _grid_lists(result.board), _grid_lists(result.special_board)
            points += _settle(state, rules, rng, events, info)
            _charge(state, info["blue"], events, "plave iz perka i kaskada")
            if state.time_left is not None:
                state.time_left -= PERK_SECONDS
        else:
            candidate, result = action["candidate"], action["result"]
            if _uses_random_targets(result):
                result = _sim_swap(state.board, candidate, rules, state.lava, rng) or result
                info["random"] = True
                info["first_unknown"] = {"where": "nasumicna meta specijala", "wave": 1}
            boundary = _first_boundary(result)
            if boundary and info["first_unknown"] is None:
                info["first_unknown"] = {"where": f"granica simulatora ({boundary['reason']})",
                                         "wave": boundary.get("cascade")}
            growth = _apply_growth(state, rules, _mushroom_count(result), events)
            info["growth"] += growth
            units = _units(result, rules)
            det_points = units * state.multiplier
            points += det_points
            info["activated"] += float(result.activated_specials)
            info["guaranteed_extra"] = result.extra_moves > 0 and rules.extra_enabled
            events.append({"wave": "swipe", "label": swipe_label(candidate), "events": _result_events(result),
                           "units": units, "multiplier": state.multiplier, "points": det_points,
                           "guaranteed_extra": info["guaranteed_extra"],
                           "deterministic": not info["random"]})
            lava_before = state.lava
            if lava_before or rules.game_mode is ms.FLOOR_IS_LAVA_MODE:
                try:
                    destroyed, after = ms.floor_lava_transition(result.cascade_matches, lava_before,
                                                                result.has_direct_match_layer)
                    state.lava = tuple(after)
                    events.append({"wave": "lava", "erupted": list(destroyed), "marks_after": list(after)})
                except Exception as exc:  # pragma: no cover - zastita od promene API-ja
                    events.append({"wave": "lava", "note": f"prelaz nije izracunat: {exc}"})
            blue_direct = float(result.blue_cells)
            state.board, state.special = _grid_lists(result.board), _grid_lists(result.special_board)
            points += _settle(state, rules, rng, events, info)
            blue_total = blue_direct + info["blue"]
            if state.eb_pending:
                boosted = float(result.direct_effect_cells or result.direct_match_cells)
                if boosted > blue_direct:
                    events.append({"wave": "perk", "note": f"Energy Boost: {boosted:g} direktnih celija puni buster"})
                blue_total = max(blue_total, boosted + info["blue"])
                state.eb_pending = False
            _charge(state, blue_total, events, "plave iz swipe-a i kaskada")
            info["extra"] = (info["guaranteed_extra"] or info["extra_uncertain"]) and rules.extra_enabled
            moves_before = state.moves_left
            if not info["extra"]:
                state.moves_left -= 1
            if state.time_left is not None:
                state.time_left -= self.seconds_per_move
            if rules.multiplier_growth == "per_move" and state.sm is not None:
                state.sm += 1
            events.append({"wave": "red", "moves_left": [moves_before, state.moves_left],
                           "why": ("garantovani extra" if info["guaranteed_extra"] else
                                   "extra iz kaskade posle dopune (nesiguran)" if info["extra"] else
                                   "obican potez trosi potez")})
        state.over = _turn_check(state, self.profile, self.max_steps)
        if state.over:
            events.append({"wave": "red", "turn_over": state.over})
        return StepResult(state, points, events, info)

    # -- strategija ------------------------------------------------------

    def _swap_value(self, state: GameState, action: dict) -> float:
        cv, mv = self.economy["charge_cell_value"], self.economy["move_value"]
        room = (state.charge_max - state.charge) if state.charge is not None and state.charge_max else 0.0
        value = action["det_units"] + (mv if action["guaranteed_extra"] else 0.0)
        return value + cv * min(room, float(action["result"].blue_cells))

    def perk_value(self, state: GameState, action: dict, best_swap: dict | None) -> float:
        """Heuristika perka (ne poeni): sta donosi odmah na ovoj tabli."""
        cv = self.economy["charge_cell_value"]
        room = (state.charge_max - state.charge) if state.charge is not None and state.charge_max else 0.0
        if action["perk"] == ms.PERK_ENERGY_BOOST:
            if best_swap is None:
                return 0.0
            result = best_swap["result"]
            boosted = float(result.direct_effect_cells or result.direct_match_cells)
            return cv * (min(room, boosted) - min(room, float(result.blue_cells)))
        return action["det_units"] + cv * min(room, float(action.get("det_blue", 0.0)))

    def best_perk_action(self, state: GameState, perk: str | None = None, actions=None):
        actions = actions if actions is not None else self.legal_actions(state)[0]
        swaps = [a for a in actions if a["kind"] == "swap"]
        best_swap = max(swaps, key=lambda a: (self._swap_value(state, a), a["key"]), default=None)
        best, best_value = None, 0.0
        for action in actions:
            if action["kind"] != "perk" or (perk is not None and action["perk"] != perk):
                continue
            value = self.perk_value(state, action, best_swap)
            if value > best_value:
                best, best_value = action, value
        return best, best_value

    def choose_action(self, state: GameState) -> tuple[dict | None, float]:
        """Politika nastavka (POLICY_DOC): vidi samo trenutnu tablu i resurse."""
        actions, _ = self.legal_actions(state)
        if not actions:
            return None, 0.0
        booster = next((a for a in actions if a["kind"] == "booster"), None)
        if booster is not None:
            return booster, self.booster_units
        swaps = [a for a in actions if a["kind"] == "swap"]
        if not swaps:
            if self.final_turn:
                perk, value = self.best_perk_action(state, actions=actions)
                if perk is not None:
                    return perk, value
            return None, 0.0
        extras = [a for a in swaps if a["guaranteed_extra"]]
        if extras:
            best_extra = max(extras, key=lambda a: (self._swap_value(state, a), a["key"]))
            return best_extra, self._swap_value(state, best_extra)
        if self.final_turn and state.moves_left <= 1 and state.perks:
            perk, value = self.best_perk_action(state, actions=actions)
            if perk is not None:
                return perk, value
        best = max(swaps, key=lambda a: (self._swap_value(state, a), a["key"]))
        return best, self._swap_value(state, best)

    def opponent_reply(self, state: GameState) -> float:
        """Najbolji neposredan odgovor protivnika na predatu tablu (jedinice)."""
        swaps = legal_swaps(state, self.rules, self.cache)
        return max((_units(result, self.rules) for _c, result in swaps), default=0.0)


# ---------------------------------------------------------------------------
# Grane (rollout) i analiza jedne odluke


@dataclass
class Branch:
    immediate: float = 0.0
    total: float = 0.0
    another_decision: bool = False
    ended_by: str = ""
    first_extra: bool = False
    guaranteed_extra: bool = False
    extras: int = 0
    booster_fires: int = 0
    growth: float = 0.0
    activated: float = 0.0
    charge_useful: float = 0.0
    opponent_units: float | None = None
    random: bool = False
    unverified: set = field(default_factory=set)
    first_unknown: dict | None = None
    steps: int = 0
    trace: list | None = None
    policy_values: list = field(default_factory=list)
    booster_points: float = 0.0
    perks_left: int = 0
    perks_used: list = field(default_factory=list)
    extended: bool = False


def branch_rng(seed: int, run: str, index: int) -> random.Random:
    """Isti seed za granu `index` svih pocetnih akcije jedne odluke."""
    digest = hashlib.sha256(f"{seed}|{run}|{index}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


class DecisionAnalysis:
    def __init__(self, decision: Decision, seed: int = 0, max_steps: int = DEFAULT_MAX_STEPS):
        self.decision = decision
        self.seed = seed
        self.profile = PROFILES[decision.context]
        self.economy = economy_for(self.profile)
        self.rules = build_rules(decision)
        self.limitations: list[str] = []
        self.unverified: set = set(self.rules.unverified)
        snap = decision.snapshot or {}
        sm = float(snap["mult"]) if snap.get("mult") and not snap.get("mult_unreliable") else None
        legend = 1.0
        if sm is None:
            if decision.multiplier is None:
                self.limitations.append("mnozilac nepoznat: poeni prikazani pri x1")
            else:
                legend = float(decision.multiplier)
                self.unverified.add("multiplier_estimated")
            if self.rules.multiplier_growth:
                self.limitations.append("rast mnozioca u nastavku nije modelovan (nema memorijskog snimka)")
                self.unverified.add("growth_unmodeled")
        history = decision.booster_history_units
        if history:
            booster_units = statistics.fmean(history)
            booster_source = f"empirijski: prosek {len(history)} ranijih aktivacija u ovoj partiji"
        else:
            booster_units = self.economy["booster_value"]
            booster_source = "data/charge_value.json booster_value (prosek konteksta)"
        if snap.get("ability") == 27:
            booster_source = "Doctor Color: prebojavanje + kaskade; uniformni izbor putanje (nepotvrdjen pickBehavior)"
        self.booster_source = booster_source
        perks = []
        for status in decision.perk_status:
            if status["status"] == "dostupan":
                perks.append(status["perk"])
            elif status["status"].startswith("nepoznato"):
                self.limitations.append(f"slot {status['slot']} ({status['perk']}): dostupnost nepoznata -- ne razmatra se")
        moves_left = decision.remaining_moves
        if moves_left is None:
            moves_left = 1
            self.limitations.append("broj preostalih poteza nepoznat: pretpostavljen 1")
        # Poslednji red partije: posle njega neiskorisceni perk ne vredi nista.
        self.final_turn = bool(decision.round is not None and decision.total_rounds is not None
                               and decision.round >= decision.total_rounds)
        self.sim = Simulator(self.rules, self.profile, self.economy, booster_units,
                             DEFAULT_SECONDS_PER_MOVE, max_steps, final_turn=self.final_turn,
                             ability=snap.get("ability"))
        self.root = GameState(
            board=_grid_lists(decision.move["board"]), special=_grid_lists(decision.move["special_board"]),
            moves_left=int(moves_left),
            charge=float(decision.booster_charge) if decision.booster_charge is not None else None,
            charge_max=float(decision.booster_max) if decision.booster_max is not None else None,
            perks=tuple(perks), eb_pending=False, sm=sm, legend=legend, lava=self.rules.lava_columns,
            time_left=decision.time_left if self.profile.clock_bound else None,
        )
        if self.root.charge is None:
            self.limitations.append("punjenje bustera nepoznato: buster i Energy Boost se ne razmatraju")
        self.opp_multiplier = float(snap["op_mult"]) if snap.get("op_mult") else None

    # -- pocetni planovi ----------------------------------------------------

    def root_plans(self) -> tuple[list[dict], list[dict]]:
        actions, unsupported = self.sim.legal_actions(self.root)
        plans = [{"key": a["key"], "label": a["label"], "kind": a["kind"], "first": a, "then": None,
                  "equivalent": a["equivalent"]} for a in actions]
        # Redosled dve slobodne akcije (oba perka): EB -> RC@t i RC@t -> EB.
        eb = next((a for a in actions if a["kind"] == "perk" and a["perk"] == ms.PERK_ENERGY_BOOST), None)
        targeted = [a for a in actions if a["kind"] == "perk" and a.get("target") is not None]
        if eb is not None and targeted:
            for t in targeted:
                plans.append({"key": f"{eb['key']} -> {t['key']}", "label": f"Energy Boost -> {t['label']}",
                              "kind": "sequence", "first": eb, "then": t, "equivalent": []})
                plans.append({"key": f"{t['key']} -> {eb['key']}", "label": f"{t['label']} -> Energy Boost",
                              "kind": "sequence", "first": t, "then": eb, "equivalent": []})
        # Extra pa perk: garantovani extra prvo, perk na tabli koja tada postoji
        # (meta se bira tada, istom heuristikom kao u nastavku).
        perks = sorted({a["perk"] for a in actions if a["kind"] == "perk"})
        extras = sorted((a for a in actions if a["kind"] == "swap" and a["guaranteed_extra"]),
                        key=lambda a: (-a["det_units"], a["key"]))[:EXTRA_THEN_PERK_SWAPS]
        for swap in extras:
            for perk in perks:
                label = PERK_LABELS.get(perk, perk)
                plans.append({"key": f"{swap['key']} -> perk {perk}@najbolja", "kind": "sequence",
                              "label": f"{swap['label']} (extra) -> {label} @najbolja meta tada",
                              "first": swap, "then": {"kind": "perk_best", "perk": perk, "key": f"perk_best {perk}"},
                              "equivalent": []})
        return plans, unsupported

    def rollout(self, plan: dict, index: int, trace: bool = False, max_steps: int | None = None) -> Branch:
        rng = branch_rng(self.seed, self.decision.run, index)
        previous_limit = self.sim.max_steps
        if max_steps is not None:
            self.sim.max_steps = max_steps
        try:
            return self._rollout(plan, rng, trace)
        finally:
            self.sim.max_steps = previous_limit

    def _rollout(self, plan: dict, rng: random.Random, trace: bool) -> Branch:
        sim = self.sim
        branch = Branch(trace=[] if trace else None)
        state = self.root
        steps = [plan["first"]] + ([plan["then"]] if plan.get("then") else [])
        for position, action in enumerate(steps):
            if position == 1:
                # Drugi korak plana mora biti legalan i na novoj tabli.
                current, _ = sim.legal_actions(state)
                if action["kind"] == "perk_best":
                    wanted = action["perk"]
                    action, _value = sim.best_perk_action(state, wanted, actions=current)
                    if action is None:
                        # Nijedna meta nema pozitivnu heuristiku: perk se ipak igra
                        # (to je plan), na prvoj legalnoj meti po kljucu.
                        same = sorted((a for a in current if a["kind"] == "perk" and a["perk"] == wanted),
                                      key=lambda a: a["key"])
                        action = same[0] if same else None
                else:
                    action = next((a for a in current if a["key"] == action["key"]), None)
                if action is None:
                    branch.ended_by = "plan nelegalan posle prve akcije"
                    break
            out = sim.step(state, action, rng)
            self._absorb(branch, out, first=(position == 0), action=action)
            state = out.state
            if state.over:
                break
        while not state.over and not branch.ended_by:
            action, value = sim.choose_action(state)
            if action is None:
                branch.ended_by = ENDED_NO_MOVES
                break
            branch.policy_values.append(value)
            out = sim.step(state, action, rng)
            self._absorb(branch, out, first=False, action=action)
            state = out.state
        branch.ended_by = branch.ended_by or state.over or "?"
        branch.steps = state.steps
        branch.perks_left = len(state.perks)
        if self.profile.has_opponent and branch.ended_by.startswith("predaja"):
            branch.opponent_units = sim.opponent_reply(state)
            if branch.trace is not None:
                branch.trace.append({"wave": "protivnik", "best_reply_units": branch.opponent_units,
                                     "note": "najbolji neposredan swipe protivnika na predatoj tabli (bez njegovog bustera)"})
        return branch

    def _absorb(self, branch: Branch, out: StepResult, first: bool, action: dict | None = None) -> None:
        info = out.info
        branch.total += out.points
        if action is not None and action["kind"] == "booster":
            branch.booster_points += out.points
        if action is not None and action["kind"] == "perk":
            branch.perks_used.append(action["label"])
        if first:
            branch.immediate = out.points
            branch.first_extra = info["extra"]
            branch.guaranteed_extra = info["guaranteed_extra"]
            branch.another_decision = not out.state.over
            branch.first_unknown = info["first_unknown"]
        if info["extra"]:
            branch.extras += 1
        branch.booster_fires += sum(1 for e in out.events if e.get("action") == "aktivacija")
        branch.growth += info["growth"]
        branch.activated += info["activated"]
        branch.charge_useful += sum(e.get("useful", 0.0) for e in out.events if e.get("wave") == "buster")
        branch.random = branch.random or info["random"] or info["first_unknown"] is not None
        branch.unverified |= info["unverified"]
        if branch.trace is not None:
            branch.trace.append({"step": out.state.steps, "points": out.points, "events": out.events,
                                 "first_unknown": info["first_unknown"]})

    # -- glavni tok -----------------------------------------------------------

    def run(self, samples: int | None = None, detailed: bool = False) -> dict:
        budget = samples or (DEFAULT_DETAILED_SAMPLES if detailed else DEFAULT_FAST_SAMPLES)
        base = min(budget, DEFAULT_FAST_SAMPLES)
        plans, unsupported = self.root_plans()
        played_key = match_played(self.decision, plans)
        branches = {p["key"]: [self.rollout(p, i) for i in range(base)] for p in plans}
        # Usmerene dodatne grane: najbolji i svi kandidati cija uparena razlika
        # sa njim nije jasna dobijaju jos grana (isti seed-ovi 0..n-1 za sve).
        while True:
            means = {k: statistics.fmean(b.total for b in v) for k, v in branches.items() if v}
            if not means:
                break
            best_key = max(means, key=lambda k: (means[k], k))
            grow = []
            for plan in plans:
                key = plan["key"]
                if len(branches[key]) >= budget:
                    continue
                if key != best_key:
                    d = paired(branches[best_key], branches[key])
                    if d["n"] and d["mean"] > TIE_SIGMAS * (d["se"] or 0) + 1e-9:
                        continue
                grow.append(plan)
            if not grow:
                break
            for plan in grow:
                n = len(branches[plan["key"]])
                branches[plan["key"]].extend(self.rollout(plan, i) for i in range(n, min(budget, n * 2)))
        self._extend_cut_branches(plans, branches, played_key)
        rows = [self._row(plan, branches[plan["key"]], played_key, branches.get(played_key)) for plan in plans]
        rows.sort(key=lambda r: (-r["total"]["mean"], r["key"]))
        for rank, row in enumerate(rows, start=1):
            row["rank"] = rank
        verdict = self._verdict(rows, branches)
        return {
            "run": self.decision.run, "path": str(self.decision.path),
            "context": self.decision.context, "context_label": self.profile.label,
            "context_source": self.decision.context_source, "scope": self.profile.scope,
            "mode": self.decision.mode, "time": self.decision.time_label,
            "round": self.decision.round, "total_rounds": self.decision.total_rounds,
            "remaining_moves": self.decision.remaining_moves, "time_left": self.decision.time_left,
            "our_score": self.decision.our_score, "opp_score": self.decision.opp_score,
            "multiplier": self.root.multiplier, "multiplier_source": self.decision.multiplier_source,
            "opponent_multiplier": self.opp_multiplier,
            "booster": {"charge": self.decision.booster_charge, "max": self.decision.booster_max,
                        "model_units": self.sim.booster_units, "model_source": self.booster_source},
            "refill_source": self.rules.refill_source,
            "perks": self.decision.perk_status,
            "proposed": _jsonable(self.decision.proposed), "sent": self.decision.sent,
            "outcome": _jsonable(self.decision.outcome),
            "played_key": played_key,
            "actions": rows, "unsupported": unsupported,
            "limitations": self.limitations,
            "unverified_rules": sorted(self.unverified | set().union(*(r["unverified"] for r in rows)) if rows else self.unverified),
            "verdict": verdict, "samples_budget": budget, "seed": self.seed,
        }

    def _extend_cut_branches(self, plans, branches, played_key) -> None:
        """Grane prekinute limitom kod kandidata koji odlucuju (prva tri i
        odigrana akcija) ponovo se odigravaju sa duzim limitom, istim seed-om."""
        means = {k: statistics.fmean(b.total for b in v) for k, v in branches.items() if v}
        top = sorted(means, key=lambda k: (-means[k], k))[:3]
        keys = set(top) | ({played_key} if played_key else set())
        longer = self.sim.max_steps * LIMIT_EXTENSION_FACTOR
        for plan in plans:
            if plan["key"] not in keys:
                continue
            items = branches[plan["key"]]
            for index, branch in enumerate(items):
                if branch.ended_by == ENDED_LIMIT:
                    extended = self.rollout(plan, index, max_steps=longer)
                    extended.extended = True
                    items[index] = extended

    def _row(self, plan, items: list[Branch], played_key, played_items) -> dict:
        n = max(1, len(items))
        ends: dict = {}
        for b in items:
            ends[b.ended_by] = ends.get(b.ended_by, 0) + 1
        opp = [b.opponent_units for b in items if b.opponent_units is not None]
        first = plan["first"]
        row = {
            "key": plan["key"], "label": plan["label"], "kind": plan["kind"],
            "start": first.get("start"), "target": first.get("target"), "direction": first.get("direction"),
            "perk": first.get("perk"), "equivalent": plan["equivalent"],
            "special_activation": bool(first.get("special_activation")),
            "historical": historical_considered(self.decision, plan),
            "played": plan["key"] == played_key,
            "immediate": summary([b.immediate for b in items]),
            "total": summary([b.total for b in items]),
            "p_another_decision": sum(b.another_decision for b in items) / n,
            "p_extra_first": sum(b.first_extra for b in items) / n,
            "guaranteed_extra": all(b.guaranteed_extra for b in items) if items else False,
            "extras_mean": sum(b.extras for b in items) / n,
            "booster_fires_mean": sum(b.booster_fires for b in items) / n,
            "growth_mean": sum(b.growth for b in items) / n,
            "activated_mean": sum(b.activated for b in items) / n,
            "charge_useful_mean": sum(b.charge_useful for b in items) / n,
            "ended_by": ends,
            "share_limit": sum(v for k, v in ends.items() if k in CUT_ENDINGS) / n,
            "share_unsupported": sum(1 for b in items if "booster_empirical" in b.unverified) / n,
            "first_unknown": next((b.first_unknown for b in items if b.first_unknown), None),
            "unverified": sorted(set().union(*(b.unverified for b in items))) if items else [],
            "opponent_reply_units": summary(opp) if opp else None,
            "policy_value_mean": statistics.fmean([v for b in items for v in b.policy_values]) if any(b.policy_values for b in items) else None,
            "booster_points_mean": sum(b.booster_points for b in items) / n,
            "total_ex_booster": summary([b.total - b.booster_points for b in items]),
            "perks_left_mean": sum(b.perks_left for b in items) / n,
            "perks_used": sorted({p for b in items for p in b.perks_used}),
            "extended_branches": sum(1 for b in items if b.extended),
        }
        row["continuation_mean"] = row["total"]["mean"] - row["immediate"]["mean"]
        if played_items:
            row["vs_played"] = paired(items, played_items)
        if self.opp_multiplier and opp:
            row["opponent_reply_points"] = statistics.fmean(opp) * self.opp_multiplier
        return row

    def _verdict(self, rows, branches) -> dict:
        if not rows:
            return {"status": "nema legalnih akcija"}
        best = rows[0]
        out = {"best_key": best["key"], "best_label": best["label"]}
        if len(rows) > 1:
            second = rows[1]
            d = paired(branches[best["key"]], branches[second["key"]])
            out["second_key"] = second["key"]
            out["second_label"] = second["label"]
            out["gap_to_second"] = d
            out["reliable_winner"] = bool(d["n"]) and d["mean"] > TIE_SIGMAS * (d["se"] or 0) + 1e-9
            out["reason_vs_second"] = main_reason(best, second)
        played = next((r for r in rows if r["played"]), None)
        if played is None:
            out["played"] = "odigrana akcija nije medju legalnim akcijama ovog stanja"
        else:
            d = paired(branches[best["key"]], branches[played["key"]])
            out["played_key"] = played["key"]
            out["played_label"] = played["label"]
            out["played_rank"] = played["rank"]
            out["diff_vs_played"] = d
            out["tie_with_played"] = best["key"] == played["key"] or d["mean"] <= TIE_SIGMAS * (d["se"] or 0) + 1e-9
            out["reason_vs_played"] = main_reason(best, played) if best["key"] != played["key"] else None
            out["confidence"] = confidence(d, best, played)
            if best.get("opponent_reply_units") and played.get("opponent_reply_units"):
                out["opponent_reply_diff_units"] = (best["opponent_reply_units"]["mean"]
                                                    - played["opponent_reply_units"]["mean"])
        depends = set(best["unverified"]) | (set(played["unverified"]) if played else set())
        compared = [best] + ([rows[1]] if len(rows) > 1 else []) + ([played] if played else [])
        # Buster: poeni bustera su empirijski, a tabla posle njega se ne simulira.
        # Ako se poredjene akcije razlikuju u busteru toliko da to moze da promeni
        # pobednika, izbor (i meta) nije potvrdjen.
        ex_best = max(rows, key=lambda r: (r["total_ex_booster"]["mean"], r["key"]))
        out["best_without_booster"] = ex_best["label"]
        booster_dependent = False
        for other in compared[1:]:
            if other["key"] == best["key"]:
                continue
            gap = best["total"]["mean"] - other["total"]["mean"]
            booster_gap = best["booster_points_mean"] - other["booster_points_mean"]
            if booster_gap > 1e-9 and booster_gap >= gap:
                booster_dependent = True
        if ex_best["key"] != best["key"]:
            booster_dependent = True
        out["booster_dependent"] = booster_dependent
        out["booster_selection_unverified"] = any("doctor_color_selection" in r["unverified"] for r in compared)
        if booster_dependent and out["booster_selection_unverified"]:
            depends.add("doctor_color_selection")
            out["reliable_winner"] = False
            if out.get("confidence"):
                out["confidence"] = "nepotvrdjeno (izbor Doctor Color putanje); " + out["confidence"]
        elif booster_dependent:
            depends.add("booster_choice")
            out["reliable_winner"] = False
            if out.get("confidence"):
                out["confidence"] = "nepotvrdjeno (zavisi od bustera); " + out["confidence"]
        # Limit: posle produzenja i dalje prekinute grane => pobednik nije utvrdjen.
        still_cut = sorted({r["label"] for r in compared if r["share_limit"] > 0})
        out["limit_cut_after_extension"] = still_cut
        if still_cut:
            depends.add("limit_undecided")
            out["reliable_winner"] = False
            if played is not None:
                out["tie_with_played"] = True
            if out.get("confidence"):
                out["confidence"] = "pobednik nije utvrdjen (limit); " + out["confidence"]
        # Perk sada vs sacuvan: pre poslednjeg reda zaostali perk vredi i posle predaje.
        if not self.final_turn and played and abs(best["perks_left_mean"] - played["perks_left_mean"]) > 1e-9:
            out["perk_residual_note"] = (
                f"predlog na predaji ostavlja {best['perks_left_mean']:.2f} perka, odigrano {played['perks_left_mean']:.2f}; "
                "vrednost sacuvanog perka za kasnije redove nije u poenima do predaje"
            )
        out["final_turn"] = self.final_turn
        out["depends_on_unverified"] = [UNVERIFIED_RULES.get(k, k) for k in sorted(depends)]
        return out

    def trace(self, key: str, index: int = 0) -> dict:
        plans, _ = self.root_plans()
        plan = next((p for p in plans if p["key"] == key), None)
        if plan is None:
            return {"key": key, "error": "akcija nije legalna u ovom stanju"}
        branch = self.rollout(plan, index, trace=True)
        return {"key": key, "label": plan["label"], "branch": index, "seed": self.seed,
                "immediate": branch.immediate, "total": branch.total, "ended_by": branch.ended_by,
                "first_unknown": branch.first_unknown, "opponent_reply_units": branch.opponent_units,
                "steps": _jsonable(branch.trace)}


def analyze_decision(decision: Decision, *, seed: int = 0, samples: int | None = None, detailed: bool = False,
                     max_steps: int = DEFAULT_MAX_STEPS, traces: bool = False) -> dict:
    analysis = DecisionAnalysis(decision, seed=seed, max_steps=max_steps)
    result = analysis.run(samples=samples, detailed=detailed)
    if traces:
        keys = [result["verdict"].get("played_key"), result["verdict"].get("best_key")]
        result["traces"] = [analysis.trace(k) for k in dict.fromkeys(k for k in keys if k)]
    return result


# ---------------------------------------------------------------------------
# Statistika


def summary(values: list[float]) -> dict:
    n = len(values)
    mean = statistics.fmean(values) if values else 0.0
    sd = statistics.stdev(values) if n > 1 else 0.0
    ordered = sorted(values)

    def q(p):
        return ordered[min(n - 1, max(0, int(round(p * (n - 1)))))] if ordered else 0.0

    return {"mean": mean, "se": sd / math.sqrt(n) if n > 1 else 0.0, "sd": sd,
            "p10": q(0.10), "p90": q(0.90), "min": ordered[0] if ordered else 0.0,
            "max": ordered[-1] if ordered else 0.0, "n": n}


def paired(a: list[Branch], b: list[Branch]) -> dict:
    """Uparena razlika ukupnih poena A - B po istim seed-ovima grana."""
    n = min(len(a), len(b))
    diffs = [a[i].total - b[i].total for i in range(n)]
    if not diffs:
        return {"mean": 0.0, "se": None, "n": 0}
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    return {"mean": statistics.fmean(diffs), "se": sd / math.sqrt(n) if n > 1 else 0.0, "n": n}


REASON_LABELS = {
    "extra": "garantovani extra potez (jos jedna nasa odluka)",
    "extra_chance": "veca sansa za extra iz kaskade (nesigurno)",
    "special": "aktivacija specijala",
    "multiplier": "rast mnozioca",
    "booster": "buster (ispaljivanje ili punjenje do pune skale)",
    "setup": "priprema narednog poteza (vise poena u nastavku reda)",
    "immediate": "vise neposrednih poena",
}


def main_reason(a: dict, b: dict) -> str:
    imm = a["immediate"]["mean"] - b["immediate"]["mean"]
    cont = a["continuation_mean"] - b["continuation_mean"]
    tags = []
    if a["guaranteed_extra"] and not b["guaranteed_extra"]:
        tags.append("extra")
    elif a["p_extra_first"] - b["p_extra_first"] > 0.25:
        tags.append("extra_chance")
    if a["growth_mean"] - b["growth_mean"] > 0.25:
        tags.append("multiplier")
    if a["activated_mean"] - b["activated_mean"] >= 1:
        tags.append("special")
    if a["booster_fires_mean"] - b["booster_fires_mean"] > 0.3 or a["kind"] == "booster":
        tags.append("booster")
    if imm >= cont:
        lead = "special" if "special" in tags else ("multiplier" if "multiplier" in tags else "immediate")
    else:
        lead = next((t for t in tags if t in ("extra", "extra_chance", "booster", "multiplier")), "setup")
    text = f"{REASON_LABELS[lead]} [odmah {imm:+.0f}, nastavak {cont:+.0f}]"
    others = [REASON_LABELS[t] for t in tags if t != lead]
    return text + (" + " + "; ".join(others) if others else "")


def confidence(d: dict, a: dict, b: dict) -> str:
    if not d["n"]:
        return "nema podataka"
    se = d["se"] or 0.0
    if se <= 1e-9:
        level = "visoka (deterministicki ishod)" if abs(d["mean"]) > 1e-6 else "izjednaceno"
    else:
        z = abs(d["mean"]) / se
        level = "visoka" if z >= 4 else ("srednja" if z >= TIE_SIGMAS else "niska (nema pouzdanog pobednika)")
    if a["share_limit"] or b["share_limit"]:
        level += "; deo grana prekinut limitom"
    if a["share_unsupported"] or b["share_unsupported"]:
        level += "; ukljucen empirijski buster"
    return level


def match_played(decision: Decision, plans: list[dict]) -> str | None:
    proposed = decision.proposed
    if proposed["type"] == "swap":
        want = f"({proposed['start'][0]},{proposed['start'][1]})->({proposed['target'][0]},{proposed['target'][1]})"
        for plan in plans:
            if plan["kind"] != "swap":
                continue
            first = plan["first"]
            if (first["start"], first["target"]) == (proposed["start"], proposed["target"]):
                return plan["key"]
            if any(want in label for label in plan["equivalent"]):
                return plan["key"]
    elif proposed["type"] == "booster":
        return "booster" if any(p["key"] == "booster" for p in plans) else None
    elif proposed["type"] == "perk":
        perk, target = proposed.get("perk"), proposed.get("target")
        for plan in plans:
            first = plan["first"]
            if plan["kind"] != "perk" or first.get("perk") != perk:
                continue
            if target is None or tuple(first.get("target") or ()) == tuple(target):
                return plan["key"]
            if target is not None and any(label.endswith(f"@({target[0]},{target[1]})") for label in plan["equivalent"]):
                return plan["key"]
    return None


def historical_considered(decision: Decision, plan: dict) -> str:
    first = plan["first"]
    if plan["kind"] == "swap":
        if not decision.candidates:
            return "nepoznato (nema candidates.json)"
        pair = {first["start"], first["target"]}
        for cand in decision.candidates:
            if cand.get("start") is not None and {tuple(cand["start"]), tuple(cand["target"])} == pair:
                same = (tuple(cand["start"]), tuple(cand["target"])) == (first["start"], first["target"])
                return "da" if same else "da (drugi smer)"
        return "ne"
    if plan["kind"] == "perk":
        for cand in decision.move.get("perk_candidates") or []:
            if cand.get("perk") == first["perk"] and (
                first.get("target") is None or tuple(cand.get("target") or ()) == tuple(first["target"])
            ):
                return "da"
        return "ne"
    if plan["kind"] == "booster":
        return "da" if decision.proposed["type"] == "booster" else "nepoznato"
    return "ne (redosled perkova)"


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def strip_for_json(result: dict) -> dict:
    return _jsonable(result)


# ---------------------------------------------------------------------------
# Provenance


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def provenance(config: dict) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                                timeout=5).stdout.strip() or None
    except Exception:
        commit = None
    return {
        "analyzer_version": ANALYZER_VERSION, "git_commit": commit,
        "code_sha256": {name: _sha(ROOT / name) for name in
                        ("turn_analyzer.py", "move_strategy.py", "learned_value.py", "runtime.py")},
        "model_sha256": _sha(ROOT / "models" / "move_value_model.json"),
        "weights_sha256": _sha(ROOT / "data" / "learned_weights.json"),
        "economy_sha256": _sha(ROOT / "data" / "charge_value.json"),
        "refill_stats_sha256": _sha(REFILL_STATS_PATH),
        "policy": POLICY_DOC, "config": config,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
