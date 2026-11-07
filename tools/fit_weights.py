"""Merenje ekonomije i kalibracija tezina iz odigranih partija (Debug/runs).

Umesto rucnog stelovanja konstanti u move_strategy.py, ovaj alat cita sta je
igra stvarno uradila posle poteza. Novi mnozioci prihvataju se samo posle
provere na kasnijim danima, uz interval pouzdanosti po partijama:

  data/charge_value.json      -- samo uz --write-economy, inace ostaje postojeci:
        koliko vredi jedna celija punjenja, ceo buster i jedan potez, u
        jedinicama simulatora, po kontekstu i skupno
  data/learned_weights.json   -- kalibracija predvidjanja (cita learned_value):
        realizacija plavih (direktne / posredne), realizacija extra poteza po
        vrsti, skala buducnosti (lookahead + potencijal table)

    python tools/fit_weights.py [--since 2026-08-25] [--dry-run] [--runs DIR]

Definicije (sve po kontekstu solo_race / solo_challenge / versus_2):
  points_per_unit   = poeni koje igra da / instant_score simulatora (odnos suma)
  booster_value     = prosecni poeni jedne aktivacije bustera / points_per_unit
  charge_cell_value = prosek vrednost_aktivacije / njen sopstveni maksimum metra
  move_value        = prosecna vrednost obicnog poteza: poeni/ppu + punjenje*ccv
  spend_rate        = potroseno punjenje (aktivacije*maksimum) / zaradjeno
  blue_realization  = direktne ostaju 1.0; posredne se fituju pre ogranicenja
                      metra, kao u runtime-u, pa proveravaju na kasnijim partijama
  extra_realization = udeo zadrzanih poteza po vrsti obecanja: direktan /
                      pouzdana kaskada / nepouzdana kaskada / bez obecanja
  future_realization= nagib vrednosti *sledeceg* poteza po lookahead+potencijal
                      ovog poteza (1.0 = heuristika ih vrednuje tacno)
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import shutil
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from run_dataset import (  # noqa: E402
    CONTEXTS,
    CTX_SOLO_CHALLENGE,
    CTX_SOLO_RACE,
    CTX_VERSUS,
    RUNS_DIR,
    game_moves,
    load_samples,
    realized_cells,
    realized_value,
    temporal_split,
    continuation_pairs,
)

CHARGE_VALUE_PATH = ROOT / "data" / "charge_value.json"
LEARNED_WEIGHTS_PATH = ROOT / "data" / "learned_weights.json"


def _write_atomic(path, payload):
    pending = path.with_suffix('.tmp.json')
    pending.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    pending.replace(path)

EXTRA_GATES = {
    "true_extra_gate",
    "same_move_extra_gate",
    "mixy_extra_move_gate",
    "ufo_predicted_extra_gate",
}


def _f(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extra_kind(move: dict) -> str:
    """Vrsta obecanog extra poteza kandidata, iz njegovih dijagnostika."""
    if _f(move.get("direct_extra_moves")) >= 1.0:
        return "direct"
    if _f(move.get("extra_moves")) < 1.0:
        return "none"
    events = move.get("intent_events") or []
    rejected = any(
        isinstance(event, dict) and event.get("type") == "extra_move_rejected"
        for event in events
    )
    uncertain = bool((move.get("intent_summary") or {}).get("has_uncertain_boundary"))
    if rejected or uncertain:
        return "cascade_unreliable"
    return "cascade_reliable"


def measure_economy(samples, ctx: str) -> dict:
    """Ekonomija u jedinicama simulatora (celije), ne u poenima.

    Poeni po celiji rastu tokom partije, pa se svaka aktivacija i svaki potez
    prvo dele lokalnim mnozilacem (procenjenim iz susednih poteza iste
    partije, vidi run_dataset.annotate_games) i tek onda usrednjavaju.
    """
    moves = [s for s in samples if s.ctx == ctx and s.is_move and not s.swallowed]
    multipliers = [s.multiplier for s in moves if s.multiplier]
    ppu = statistics.mean(multipliers) if multipliers else None
    ppu_median = statistics.median(multipliers) if multipliers else None
    activations = [
        s
        for s in samples
        if s.ctx == ctx and s.is_activation and s.points_gained is not None and s.multiplier_hat
    ]
    maxima = [int(_f(s.before.get("booster_maximum"), 0)) for s in activations]
    maxima = [m for m in maxima if m > 0]
    booster_maximum = collections.Counter(maxima).most_common(1)[0][0] if maxima else 7
    booster_cells = [s.points_gained / s.multiplier_hat for s in activations]
    booster_value = statistics.mean(booster_cells) if booster_cells else None
    booster_median = statistics.median(booster_cells) if booster_cells else None
    per_charge = [s.points_gained / s.multiplier_hat / _f(s.before.get("booster_maximum"))
                  for s in activations if _f(s.before.get("booster_maximum")) > 0]
    ccv = statistics.mean(per_charge) if per_charge else None
    valued = [
        s for s in moves if realized_cells(s) is not None and s.charge_gained is not None
        and not s.charge_censored
    ]
    point_values = [realized_cells(s) for s in valued]
    total_values = (
        [realized_cells(s) + s.charge_gained * ccv for s in valued] if ccv else []
    )
    # `move_value` (koji cita move_strategy kao MEASURED_MOVE_VALUE) ostaje na
    # ranijoj definiciji -- medijana *poena* jednog poteza -- da tezina extra
    # poteza (move_value * tempo 2.0) ne promeni skalu preko noci. Medijana, ne
    # prosek: prosek vuku retke kaskade od 100+ celija. Puna vrednost poteza
    # (poeni + punjenje) ide uz nju kao `move_value_total` i nju koristi cilj
    # modela vrednosti (run_dataset.realized_value).
    move_value = statistics.median(point_values) if point_values else None
    move_value_total = statistics.median(total_values) if total_values else None
    move_value_mean = statistics.mean(total_values) if total_values else None
    earned = sum(s.charge_gained for s in moves if s.charge_gained is not None)
    spent = sum(_f(s.before.get("booster_maximum")) for s in activations)
    spend_rate = min(1.0, spent / earned) if earned > 0 else None
    return {
        "points_per_unit": None if ppu is None else round(ppu, 3),
        "points_per_unit_median": None if ppu_median is None else round(ppu_median, 3),
        "booster_value": None if booster_value is None else round(booster_value, 2),
        "booster_value_median": None if booster_median is None else round(booster_median, 2),
        "charge_cell_value": None if ccv is None else round(ccv, 2),
        "move_value": None if move_value is None else round(move_value, 2),
        "move_value_total": None if move_value_total is None else round(move_value_total, 2),
        "move_value_mean": None if move_value_mean is None else round(move_value_mean, 2),
        "spend_rate": None if spend_rate is None else round(spend_rate, 3),
        "booster_maximum": booster_maximum,
        "samples": {
            "activations": len(activations),
            "scored_moves": len(multipliers),
            "valued_moves": len(valued),
        },
    }


def pooled_economy(blocks: list[dict]) -> dict:
    """Skupno: prosek po broju aktivacija (kao i raniji merac)."""
    valid = [b for b in blocks if b.get("charge_cell_value")]
    if not valid:
        return {}
    weights = [max(1, b["samples"]["activations"]) for b in valid]
    total = float(sum(weights))

    def avg(key):
        return round(sum(_f(b[key]) * w for b, w in zip(valid, weights)) / total, 3)

    return {
        "charge_cell_value": avg("charge_cell_value"),
        "booster_value": avg("booster_value"),
        "move_value": avg("move_value"),
        "spend_rate": avg("spend_rate"),
        "samples": {"activations": sum(b["samples"]["activations"] for b in valid)},
    }


def fit_blue_realization(samples, ctx: str) -> dict:
    rows = []
    for s in samples:
        if s.ctx != ctx or not s.is_move or s.swallowed:
            continue
        if s.charge_gained is None or s.charge_censored or s.charge_room is None:
            continue
        if s.charge_room <= 0:
            continue
        total = min(_f(s.move.get("blue_cells")), s.charge_room)
        direct = min(_f(s.move.get("direct_blue_cells")), total)
        indirect = max(0.0, total - direct)
        rows.append((direct, indirect, min(s.charge_gained, s.charge_room)))
    if not rows:
        return {"samples": 0}
    matrix = np.array([[d, i] for d, i, _ in rows])
    target = np.array([c for _, _, c in rows])
    coef, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    direct_n = int((matrix[:, 0] > 0).sum())
    indirect_n = int((matrix[:, 1] > 0).sum())
    predicted = matrix.sum(axis=1)
    return {
        "direct": round(float(max(0.0, coef[0])), 3),
        "indirect": round(float(max(0.0, coef[1])), 3),
        "direct_samples": direct_n,
        "indirect_samples": indirect_n,
        "samples": len(rows),
        "mean_predicted": round(float(predicted.mean()), 3),
        "mean_observed": round(float(target.mean()), 3),
        "mae_raw": round(float(np.abs(predicted - target).mean()), 3),
        "mae_calibrated": round(float(np.abs(matrix @ coef - target).mean()), 3),
    }


def fit_extra_realization(samples, ctx: str) -> dict:
    kept_by_kind = collections.defaultdict(list)
    for s in samples:
        if s.ctx != ctx or not s.is_move or s.swallowed or s.kept_turn is None:
            continue
        kept_by_kind[extra_kind(s.move)].append(1.0 if s.kept_turn else 0.0)
    block = {"samples": sum(len(v) for v in kept_by_kind.values())}
    for kind in ("direct", "cascade_reliable", "cascade_unreliable", "none"):
        values = kept_by_kind.get(kind) or []
        block[kind] = round(statistics.mean(values), 3) if values else None
        block[kind + "_samples"] = len(values)
    return block


def fit_future_realization(samples, ctx: str, economy: dict, horizons=(1, 3)) -> dict:
    """Koliko obecana buducnost (lookahead_bonus + board_potential) stvarno
    stigne: nagib vrednosti sledecih h poteza iste partije po obecanju.
    ``scale`` je nagib za najduzi horizont (heuristika ne kaze *kada* se
    buducnost naplacuje, pa se uzima najsiri prozor)."""
    result = {"samples": 0}
    for horizon in horizons:
        xs, ys = [], []
        for current, following in continuation_pairs([s for s in samples if s.ctx == ctx], horizon):
            values = [realized_value(s, economy, require_turn=False) for s in following]
            if any(v is None for v in values):
                continue
            xs.append(_f(current.move.get("lookahead_bonus")) + _f(current.move.get("board_potential")))
            ys.append(sum(values))
        if len(xs) < 20:
            result[f"h{horizon}"] = {"samples": len(xs)}
            continue
        x = np.array(xs)
        y = np.array(ys)
        if x.std() < 1e-9:
            result[f"h{horizon}"] = {"samples": len(xs), "scale": None}
            continue
        slope, intercept = np.polyfit(x, y, 1)
        block = {
            "scale": round(float(slope), 3),
            "intercept": round(float(intercept), 2),
            "correlation": round(float(np.corrcoef(x, y)[0, 1]), 3),
            "samples": len(xs),
            "mean_future_value": round(float(x.mean()), 2),
        }
        result[f"h{horizon}"] = block
        result.update({"scale": block["scale"], "correlation": block["correlation"], "samples": len(xs), "mean_future_value": block["mean_future_value"]})
    return result


def _paired_validation(raw_errors, new_errors, games):
    """Paired bootstrap by game, so long extra chains do not fake precision."""
    raw_errors, new_errors = np.asarray(raw_errors), np.asarray(new_errors)
    grouped = collections.defaultdict(list)
    for game, gain in zip(games, raw_errors - new_errors):
        grouped[game].append(float(gain))
    gains = np.array([np.mean(v) for v in grouped.values()])
    lower = None
    if len(gains) >= 5:
        rng = np.random.default_rng(42)
        boot = rng.choice(gains, size=(2000, len(gains)), replace=True).mean(axis=1)
        lower = float(np.quantile(boot, 0.025))
    return {"samples": len(raw_errors), "games": len(gains),
            "mae_raw": float(raw_errors.mean()) if len(raw_errors) else None,
            "mae_calibrated": float(new_errors.mean()) if len(new_errors) else None,
            "game_gain_lower_95": lower,
            "accepted": bool(len(raw_errors) >= 40 and lower is not None and lower > 0
                             and new_errors.mean() < raw_errors.mean())}


def validated_blue(train, test, ctx):
    def rows(samples):
        result = []
        for s in samples:
            if (s.ctx != ctx or not s.is_move or s.swallowed or s.charge_censored
                    or s.charge_gained is None or not s.charge_room or s.charge_room <= 0):
                continue
            total = max(0.0, _f(s.move.get("blue_cells")))
            direct = min(total, max(0.0, _f(s.move.get("direct_blue_cells"))))
            result.append((direct, total-direct, s.charge_room,
                           min(s.charge_gained, s.charge_room), s.game_id))
        return np.asarray(result, dtype=float).reshape(-1, 5)
    tr, te = rows(train), rows(test)
    def predict(r, factor):
        return np.minimum(r[:, 0] + factor*r[:, 1], r[:, 2])
    grid = sorted(set([1.0] + [round(float(x), 3) for x in np.arange(0.25, 2.001, 0.025)]),
                  key=lambda x: abs(x-1.0))
    factor = min(grid, key=lambda x: np.mean(abs(predict(tr, x)-tr[:, 3]))) if len(tr) else 1.0
    val = _paired_validation(abs(predict(te, 1)-te[:, 3]),
                             abs(predict(te, factor)-te[:, 3]), te[:, 4])
    # Never improve aggregate MAE by inventing more missed/false meter fills.
    if len(te):
        actual = te[:, 3] >= te[:, 2]
        raw_fill = np.mean((predict(te, 1) >= te[:, 2]) != actual)
        new_fill = np.mean((predict(te, factor) >= te[:, 2]) != actual)
        val.update(fill_error_raw=float(raw_fill), fill_error_calibrated=float(new_fill))
        val['accepted'] = val['accepted'] and bool(new_fill <= raw_fill)
    n = int((tr[:, 1] > 0).sum())
    val['accepted'] = val['accepted'] and n >= 40
    return {'direct': 1.0, 'indirect': factor if val['accepted'] else 1.0,
            'candidate_indirect': factor, 'samples': len(tr),
            'direct_samples': int((tr[:, 0] > 0).sum()), 'indirect_samples': n,
            'validation': val}


def validated_future(train, test, ctx, economy):
    def rows(samples):
        result = []
        for current, following in continuation_pairs([s for s in samples if s.ctx == ctx]):
            value = realized_value(following[0], economy, require_turn=False)
            if value is not None:
                result.append((_f(current.move.get('lookahead_bonus')) +
                               _f(current.move.get('board_potential')), value, current.game_id))
        return np.asarray(result, dtype=float).reshape(-1, 3)
    tr, te = rows(train), rows(test)
    baseline = 0.25
    def intercept(scale):
        return float(np.median(tr[:, 1] - scale*tr[:, 0])) if len(tr) else 0.0
    grid = (0.25, 0.1, 0.0)
    scale = min(grid, key=lambda x: np.mean(abs(intercept(x)+x*tr[:, 0]-tr[:, 1]))) if len(tr) else baseline
    raw = abs(intercept(baseline)+baseline*te[:, 0]-te[:, 1])
    calibrated = abs(intercept(scale)+scale*te[:, 0]-te[:, 1])
    val = _paired_validation(raw, calibrated, te[:, 2])
    val['accepted'] = val['accepted'] and len(tr) >= 40
    return {'scale': scale if val['accepted'] else baseline, 'candidate_scale': scale,
            'samples': len(tr), 'validation': val}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None, help="prvi run (YYYY-MM-DD), podrazumevano svi")
    parser.add_argument("--runs", default=str(RUNS_DIR))
    parser.add_argument("--dry-run", action="store_true", help="samo ispis, bez pisanja fajlova")
    parser.add_argument("--write-economy", action="store_true", help="izricito primeni novi cenovnik; podrazumevano samo kalibracija")
    parser.add_argument("--blend", type=float, default=None, help="samo upisi blend za model (0..1)")
    args = parser.parse_args(argv)

    print(f"Citam {args.runs} ...", flush=True)
    samples = load_samples(Path(args.runs), since=args.since)
    moves = [s for s in samples if s.is_move]
    print(
        f"runova {len(samples)}, poteza {len(moves)}, progutanih {sum(s.swallowed for s in moves)}, "
        f"aktivacija {sum(s.is_activation for s in samples)}"
    )
    print("po kontekstu:", dict(collections.Counter(s.ctx for s in samples)))

    contexts = {}
    for ctx in CONTEXTS:
        economy = measure_economy(samples, ctx)
        contexts[ctx] = {
            "economy": economy,
            "blue_realization": fit_blue_realization(samples, ctx),
            "extra_realization": fit_extra_realization(samples, ctx),
            "future_realization": fit_future_realization(samples, ctx, economy),
        }

    print("\n=== Ekonomija (jedinice simulatora) ===")
    print(f"{'ctx':16} {'ppu':>6} {'buster':>8} {'celija':>7} {'potez':>7} {'spend':>6}  akt / potezi")
    for ctx, block in contexts.items():
        e = block["economy"]
        print(
            f"{ctx:16} {_fmt(e['points_per_unit']):>6} {_fmt(e['booster_value']):>8} "
            f"{_fmt(e['charge_cell_value']):>7} {_fmt(e['move_value']):>7} {_fmt(e['spend_rate']):>6}  "
            f"{e['samples']['activations']} / {e['samples']['scored_moves']}"
        )
    old = _read(CHARGE_VALUE_PATH)
    if old:
        print("ranije (charge_value.json):")
        for mode, e in (old.get("modes") or {}).items():
            print(
                f"{mode:16} {_fmt(e.get('points_per_unit')):>6} {_fmt(e.get('booster_value')):>8} "
                f"{_fmt(e.get('charge_cell_value')):>7} {_fmt(e.get('move_value')):>7} {_fmt(e.get('spend_rate')):>6}"
            )

    print("\n=== Realizacija plavih (punjenje po predvidjenoj celiji) ===")
    for ctx, block in contexts.items():
        b = block["blue_realization"]
        if b.get("samples"):
            print(
                f"{ctx:16} direktne x{b['direct']} (n={b['direct_samples']}), posredne x{b['indirect']} "
                f"(n={b['indirect_samples']}); predvidjeno {b['mean_predicted']} vs izmereno {b['mean_observed']}; "
                f"MAE {b['mae_raw']} -> {b['mae_calibrated']}"
            )
    print("\n=== Realizacija extra poteza (udeo zadrzanih) ===")
    for ctx, block in contexts.items():
        x = block["extra_realization"]
        print(
            f"{ctx:16} direktan {_fmt(x.get('direct'))} (n={x.get('direct_samples')}), "
            f"pouzdana kaskada {_fmt(x.get('cascade_reliable'))} (n={x.get('cascade_reliable_samples')}), "
            f"nepouzdana {_fmt(x.get('cascade_unreliable'))} (n={x.get('cascade_unreliable_samples')}), "
            f"bez obecanja {_fmt(x.get('none'))} (n={x.get('none_samples')})"
        )
    print("\n=== Buducnost (lookahead + potencijal -> vrednost sledecih poteza) ===")
    for ctx, block in contexts.items():
        f = block["future_realization"]
        parts = []
        for key in ("h1", "h3"):
            h = f.get(key) or {}
            parts.append(
                f"{key}: nagib {_fmt(h.get('scale'))} kor {_fmt(h.get('correlation'))} n={h.get('samples')}"
            )
        print(f"{ctx:16} " + "; ".join(parts) + f"; prosecna buducnost {_fmt(f.get('mean_future_value'))}")

    train, test, cutoff = temporal_split(samples)
    if not train or not test:
        print("Nema najmanje dva dana za odvojenu proveru; nista nije upisano.")
        return 1
    previous_weights = _read(LEARNED_WEIGHTS_PATH) or {}
    print(f"\n=== Hronoloska provera: trening pre {cutoff}, test od {cutoff} ===")
    for ctx in CONTEXTS:
        economy = measure_economy(train, ctx)
        blue = validated_blue(train, test, ctx)
        future = validated_future(train, test, ctx, economy)
        contexts[ctx] = {
            'economy': economy, 'blue_realization': blue, 'future_realization': future,
            # Extra changes need their own policy-aware validation; keep the
            # deployed rates instead of overwriting them with an all-data fit.
            'extra_realization': ((previous_weights.get('contexts') or {}).get(ctx) or {}).get('extra_realization', {}),
        }
        print(ctx, json.dumps({'blue': blue, 'future': future}))

    solo_blocks = [contexts[CTX_SOLO_RACE]["economy"], contexts[CTX_SOLO_CHALLENGE]["economy"]]
    solo_pooled = pooled_economy(solo_blocks)
    versus_economy = contexts[CTX_VERSUS]["economy"]
    charge_value = {
        "measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "runs_dir": str(Path(args.runs).resolve()),
        "tool": "tools/fit_weights.py",
        "modes": {
            "versus_2": _charge_mode_block(versus_economy),
            "solo_6": {
                **solo_pooled,
                "points_per_unit": contexts[CTX_SOLO_RACE]["economy"].get("points_per_unit"),
                "booster_maximum": contexts[CTX_SOLO_RACE]["economy"].get("booster_maximum"),
                "samples": {
                    "activations": solo_pooled.get("samples", {}).get("activations", 0),
                    "scored_moves": sum(b["samples"]["scored_moves"] for b in solo_blocks),
                },
            },
            "solo_race": _charge_mode_block(contexts[CTX_SOLO_RACE]["economy"]),
            "solo_challenge": _charge_mode_block(contexts[CTX_SOLO_CHALLENGE]["economy"]),
        },
        "pooled": pooled_economy([e for e in (versus_economy, solo_pooled)]),
    }
    learned = {
        "fitted_at": charge_value["measured_at"],
        "runs": len(samples),
        "moves": len(moves),
        "enabled": True,
        "apply": previous_weights.get("apply") or {"blue": True, "extra": True, "future": True},
        "contexts": contexts,
        "pooled": _pooled_calibration(contexts),
        "validation": {"method": "chronological_whole_days_game_bootstrap", "test_since": cutoff,
                       "train_runs": len(train), "test_runs": len(test)},
    }
    if args.blend is not None:
        learned["blend"] = args.blend

    if args.dry_run:
        print("\n--dry-run: nista nije upisano.")
        return 0
    if not args.write_economy:
        print("Cenovnik sacuvan: nova merenja su dijagnostika, ne automatska zamena tezina.")
    elif not charge_value["pooled"]:
        print("\nNema dovoljno aktivacija za ekonomiju; charge_value.json nije dirnut.")
    else:
        if CHARGE_VALUE_PATH.exists():
            shutil.copyfile(CHARGE_VALUE_PATH, CHARGE_VALUE_PATH.with_suffix(".prev.json"))
        _write_atomic(CHARGE_VALUE_PATH, charge_value)
        print(f"\nUpisano {CHARGE_VALUE_PATH}")
    LEARNED_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LEARNED_WEIGHTS_PATH.exists():
        shutil.copyfile(LEARNED_WEIGHTS_PATH, LEARNED_WEIGHTS_PATH.with_suffix('.prev.json'))
    _write_atomic(LEARNED_WEIGHTS_PATH, learned)
    print(f"Upisano {LEARNED_WEIGHTS_PATH}")
    return 0


def _charge_mode_block(economy: dict) -> dict:
    return {
        "charge_cell_value": economy.get("charge_cell_value"),
        "booster_value": economy.get("booster_value"),
        "move_value": economy.get("move_value"),
        "spend_rate": economy.get("spend_rate"),
        "points_per_unit": economy.get("points_per_unit"),
        "booster_maximum": economy.get("booster_maximum"),
        "samples": economy.get("samples"),
    }


def _pooled_calibration(contexts: dict) -> dict:
    """Skupna kalibracija za nepoznat kontekst: prosek po broju uzoraka."""
    pooled = {}
    for key in ("blue_realization", "extra_realization", "future_realization"):
        blocks = [c[key] for c in contexts.values() if c[key].get("samples")]
        if not blocks:
            pooled[key] = {"samples": 0}
            continue
        merged = {"samples": sum(b["samples"] for b in blocks)}
        for field in set().union(*(b.keys() for b in blocks)):
            if field == "samples" or field.endswith("_samples"):
                if field != "samples":
                    merged[field] = sum(int(b.get(field) or 0) for b in blocks)
                continue
            pairs = [
                (b[field], b.get(field.replace("direct", "direct") + "_samples") or b["samples"])
                for b in blocks
                if isinstance(b.get(field), (int, float))
            ]
            if pairs:
                total = sum(w for _, w in pairs)
                merged[field] = round(sum(v * w for v, w in pairs) / total, 3) if total else None
        pooled[key] = merged
    return pooled


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _fmt(value) -> str:
    return "-" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    raise SystemExit(main())
