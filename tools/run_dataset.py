"""Zajednicki citac Debug/runs za ucenje iz odigranih partija.

Svaki run direktorijum (move.json + observed_delta.json + candidates.json) je
jedna odluka bota. Ovaj modul ih pretvara u ravne uzorke koje koriste:

  * tools/fit_weights.py       -- merenje ekonomije i kalibracija tezina
  * tools/train_value_model.py -- trening modela vrednosti poteza

Uzorak nosi ono sto je bot *predvideo* (odigrani kandidat sa svim komponentama
ocene), sta je igra *uradila* (poeni, punjenje metra, da li je potez zadrzan)
i kontekst (rezim, metar, potezi, runda, razlika u skoru, tabla pre poteza).

Filtriranje koje svi potrosaci dele:
  * progutan swipe (tabla nepromenjena, 0 poena, 0 punjenja) se odbacuje --
    potez se nije desio, ne sme da uci "potezi ne rade nista";
  * punjenje bez merenja (metar ispaljen izmedju dva citanja) dobija donju
    granicu `observed_charge_at_least` i oznaku `charge_censored`;
  * zadrzan potez: u solo rezimu brojac poteza nepromenjen (extra), u versusu
    `kept_the_turn`; None kada se ne moze reci.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "Debug" / "runs"

CTX_SOLO_RACE = "solo_race"
CTX_SOLO_CHALLENGE = "solo_challenge"
CTX_VERSUS = "versus_2"
CONTEXTS = (CTX_SOLO_RACE, CTX_SOLO_CHALLENGE, CTX_VERSUS)


@dataclass
class RunSample:
    run: str
    day: str
    ctx: str
    strategy_mode: str
    action: str
    gate: str | None
    booster: str
    before: dict
    after: dict
    move: dict | None
    board: list | None
    special_board: list | None
    candidates: list = field(default_factory=list)
    # Ceo move.json (stanja bustera/poteza/runde, kontekst strategije, rally
    # vrednosti...) -- treba rekonstrukciji runtime prioriteta.
    raw: dict = field(default_factory=dict)
    points_gained: int | None = None
    charge_gained: float | None = None
    charge_censored: bool = False
    charge_room: float | None = None
    kept_turn: bool | None = None
    moves_gained: int | None = None
    changed_cells: int | None = None
    swallowed: bool = False
    # Popunjava annotate_games(): partija kojoj run pripada i redni broj u njoj,
    # izmereni mnozilac poena (poeni / instant_score ovog poteza) i njegova
    # procena iz susednih poteza iste partije (bez ovog poteza).
    game_id: int | None = None
    game_index: int = 0
    multiplier: float | None = None
    multiplier_hat: float | None = None
    after_run: str | None = None

    @property
    def is_move(self) -> bool:
        return self.action == "move" and self.move is not None

    @property
    def is_activation(self) -> bool:
        return self.action == "activate_booster"


def ctx_label(strategy_context: dict | None) -> str:
    sc = strategy_context or {}
    mode = sc.get("mode")
    if mode == "solo_6":
        return CTX_SOLO_CHALLENGE if sc.get("solo_challenge") else CTX_SOLO_RACE
    if mode == "versus_2":
        return CTX_VERSUS
    return str(mode or "unknown")


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


def load_sample(run_dir: Path) -> RunSample | None:
    move = _load_json(run_dir / "move.json")
    if not isinstance(move, dict):
        return None
    delta = _load_json(run_dir / "observed_delta.json") or {}
    candidates = _load_json(run_dir / "candidates.json") or []
    sc = move.get("strategy_context") or {}
    action = str(move.get("selected_action") or "none")
    state_delta = delta.get("state_delta") or {}
    before = state_delta.get("before") or (
        (move.get("screen_state_read") or {}).get("resolved") or {}
    )
    after = state_delta.get("after") or {}
    score_delta = delta.get("score_delta") or {}
    points = None
    if score_delta.get("confirmed"):
        points = _as_int(score_delta.get("our_points_gained"))
    check = delta.get("prediction_check") or {}
    charge = state_delta.get("booster_charge_gained")
    censored = False
    room = None
    try:
        room = float(before.get("booster_maximum")) - float(before.get("booster_charge"))
    except (TypeError, ValueError):
        room = None
    if charge is None and check.get("charge_spent_between") and check.get(
        "observed_charge_at_least"
    ) is not None:
        charge = float(check["observed_charge_at_least"])
        censored = True
    elif charge is not None:
        charge = float(charge)
    moves_gained = _as_int(state_delta.get("remaining_moves_gained"))
    kept = state_delta.get("kept_the_turn")
    ctx = ctx_label(sc)
    same_round = (before.get("current_round") is not None and
                  before.get("current_round") == after.get("current_round"))
    if (ctx != CTX_VERSUS and kept is None and moves_gained is not None
            and same_round and before.get("turn_owner") == "us"
            and after.get("turn_owner") == "us"):
        # Solo: nema protivnika, brojac pada za jedan po obicnom potezu.
        if moves_gained == 0:
            kept = True
        elif moves_gained == -1:
            kept = False
    changed = _as_int((delta.get("board_delta") or {}).get("changed_count"))
    swallowed = bool(
        action == "move"
        and changed == 0
        and points == 0
        and charge == 0
    )
    booster = str(move.get("active_booster") or "default")
    return RunSample(
        run=run_dir.name,
        day=run_dir.name[:10],
        ctx=ctx,
        strategy_mode=str(sc.get("mode") or "unknown"),
        action=action,
        gate=move.get("decision_gate"),
        booster=booster,
        before=before,
        after=after,
        move=move.get("best_move") if action == "move" else None,
        board=move.get("board"),
        special_board=move.get("special_board"),
        candidates=candidates if isinstance(candidates, list) else [],
        raw=move,
        points_gained=points,
        charge_gained=charge,
        charge_censored=censored,
        charge_room=room,
        kept_turn=kept if isinstance(kept, bool) else None,
        moves_gained=moves_gained,
        changed_cells=changed,
        swallowed=swallowed,
        after_run=delta.get("after_run"),
    )


def iter_samples(runs_dir: Path = RUNS_DIR, since: str | None = None, progress=None):
    names = sorted(os.listdir(runs_dir))
    total = len(names)
    for index, name in enumerate(names):
        if since and name < since:
            continue
        sample = load_sample(runs_dir / name)
        if progress and index % 1000 == 0:
            progress(index, total)
        if sample is not None:
            yield sample


def load_samples(runs_dir: Path = RUNS_DIR, since: str | None = None, verbose=True):
    def report(index, total):
        if verbose:
            print(f"  ucitano {index}/{total} runova", flush=True)

    samples = list(iter_samples(runs_dir, since, report if verbose else None))
    annotate_games(samples)
    return samples


# ---------------------------------------------------------------------------
# Partije i mnozilac poena
#
# Poeni koje igra daje za istu ociscenu celiju rastu tokom partije (izmereno
# 2026-09-03 nad versus runovima: 1x na pocetku, 12-14x pri kraju), pa poeni
# nisu stabilna valuta. Stabilna valuta je jedinica simulatora (instant_score,
# ~ocisene celije). Mnozilac za jedan run se ne cita iz igre nego procenjuje
# iz susednih poteza iste partije, bez samog poteza -- da procena ne bude
# kruzna.

GAME_GAP_SECONDS = 90
MULTIPLIER_NEIGHBOURS = 4


def run_seconds(run: str) -> float | None:
    import datetime as dt

    try:
        return dt.datetime.strptime(run[:19], "%Y-%m-%d_%H-%M-%S").timestamp()
    except ValueError:
        return None


def annotate_games(samples: list[RunSample], neighbours: int = MULTIPLIER_NEIGHBOURS) -> None:
    import statistics
    from collections import defaultdict

    samples.sort(key=lambda s: s.run)
    game = 0
    index = 0
    previous = None
    for sample in samples:
        new_game = (previous is None or sample.ctx != previous.ctx or sample.day != previous.day
                    or sample.raw.get("mode") != previous.raw.get("mode"))
        if not new_game:
            now, then = run_seconds(sample.run), run_seconds(previous.run)
            if now is None or then is None or now - then > GAME_GAP_SECONDS:
                new_game = True
        if not new_game:
            before_now = sample.before.get("our_score")
            before_then = previous.before.get("our_score")
            if before_now is not None and before_then is not None and before_now < before_then:
                new_game = True
        if new_game:
            game += 1
            index = 0
        sample.game_id = game
        sample.game_index = index
        index += 1
        previous = sample
        sample.multiplier = None
        if (
            sample.is_move
            and not sample.swallowed
            and not sample.charge_censored
            and sample.points_gained
            and sample.points_gained > 0
        ):
            instant = _as_float(sample.move.get("instant_score"))
            if instant > 0:
                sample.multiplier = sample.points_gained / instant
    by_game = defaultdict(list)
    for sample in samples:
        by_game[sample.game_id].append(sample)
    for members in by_game.values():
        for position, sample in enumerate(members):
            window = members[max(0, position - neighbours) : position + neighbours + 1]
            values = [
                other.multiplier
                for other in window
                if other is not sample and other.multiplier is not None
                and other.before.get("current_round") == sample.before.get("current_round")
            ]
            sample.multiplier_hat = statistics.median(values) if values else None


def _as_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def realized_cells(sample: RunSample) -> float | None:
    """Poeni poteza preracunati u jedinice simulatora."""
    if sample.points_gained is None or not sample.multiplier_hat:
        return None
    return sample.points_gained / sample.multiplier_hat


def realized_value(sample: RunSample, economy: dict, require_turn: bool = True) -> float | None:
    """Sta je potez stvarno doneo, u jedinicama simulatora:
    poeni/mnozilac + punjenje * vrednost celije + (zadrzan potez) * vrednost poteza."""
    ccv = economy.get("charge_cell_value")
    # Zadrzan potez vredi ceo sledeci potez: poeni + punjenje (move_value_total),
    # ne samo poeni (move_value, koji move_strategy koristi za skalu extra tezine).
    move_value = economy.get("move_value_total") or economy.get("move_value")
    if ccv is None or move_value is None:
        return None
    cells = realized_cells(sample)
    if cells is None or sample.charge_gained is None or sample.charge_censored:
        return None
    if sample.kept_turn is None and require_turn:
        return None
    value = cells + sample.charge_gained * ccv
    if sample.kept_turn:
        value += move_value
    return value


def game_moves(samples: list[RunSample]) -> dict[int, list[RunSample]]:
    """Odigrani (ne progutani) potezi po partiji, u redosledu."""
    from collections import defaultdict

    result = defaultdict(list)
    for sample in samples:
        if sample.is_move and not sample.swallowed:
            result[sample.game_id].append(sample)
    return result


def temporal_split(samples: list[RunSample], test_fraction: float = 0.2, cutoff=None):
    """Whole days and games, with multiplier estimation isolated per split."""
    import copy
    days = sorted({s.day for s in samples})
    if len(days) < 2:
        return [], [], None
    test_days = max(1, min(len(days) - 1, int(len(days) * test_fraction + 0.5)))
    cutoff = cutoff or days[-test_days]
    train = [copy.copy(s) for s in samples if s.day < cutoff]
    test = [copy.copy(s) for s in samples if s.day >= cutoff]
    annotate_games(train)
    annotate_games(test)
    return train, test, cutoff


def continuation_pairs(samples, horizon=1):
    """Only uninterrupted own moves: no booster, opponent, round or gap."""
    for members in game_moves(samples).values():
        for i, current in enumerate(members):
            following = members[i + 1:i + 1 + horizon]
            if len(following) != horizon:
                continue
            chain = [current] + following
            if all(
                a.kept_turn is True and a.after_run == b.run
                and b.game_index == a.game_index + 1
                and a.before.get("current_round") is not None
                and a.before.get("current_round") == b.before.get("current_round")
                and a.after.get("turn_owner") == b.before.get("turn_owner") == "us"
                for a, b in zip(chain, chain[1:])
            ):
                yield current, following
