"""Trening modela vrednosti poteza iz odigranih partija (Debug/runs).

Cilj nije da zameni heuristiku nego da je *ispravi*: model uci rezidual --
koliko je stvarna vrednost odigranog poteza (poeni u jedinicama simulatora +
punjenje metra * vrednost celije + zadrzan potez * vrednost poteza) odstupila
od pouzdanog prioriteta upisanog u novom snimku (ranking schema v2).
Stare ocene iz kesa po koordinatama ne koriste se kao trening cilj. U igri se na
prioritet kandidata dodaje ``blend * rezidual`` (learned_value.residual_adjustment).

    python tools/fit_weights.py            # zasebno proverena kalibracija
    python tools/train_value_model.py [--since 2026-08-25] [--blend 0.5] [--dry-run]

Osobine (learned_value.FEATURE_NAMES): komponente ocene kandidata, kontekst
(rezim, metar, potezi, runda, razlika u skoru, faza) i sazetak table pre poteza.
Isti kod pravi osobine u treningu (iz candidates.json/move.json) i u igri (iz
MoveEvaluation), pa nema razlike u ulazu.

Validacija u main: trening na ranijim danima, test posle treninga postojeceg
modela; ekonomija i procena mnozioca izolovane su od testa. Proverava stvarni
blend/clamp, interval po partijama i pokrivenost konteksta. Stare k-fold funkcije
ostaju samo za dijagnostiku i ne odlucuju o upisu. Bez dokaza ostaje stari
fajl. Izlaz: models/move_value_model.json -- stabla u cistom JSON-u, bez
sklearn-a u runtime-u.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
# Rekonstrukcija prioriteta: kalibrisani mnozioci da, model vrednosti ne
# (vidi rebuild_evaluation).
os.environ["MEMORY_GUI_LEARNED_VALUE"] = "weights"

import learned_value  # noqa: E402
import rebuild_evaluation  # noqa: E402
from run_dataset import RUNS_DIR, load_samples, realized_value, temporal_split, CONTEXTS  # noqa: E402

MODEL_PATH = learned_value.VALUE_MODEL_PATH
WEIGHTS_PATH = learned_value.LEARNED_WEIGHTS_PATH


def build_rows(samples, economies: dict):
    xs, ys, priorities, days, ctxs = [], [], [], [], []
    rebuild_failures = 0
    logged_checks = []
    for s in samples:
        if not s.is_move or s.swallowed or s.charge_censored:
            continue
        economy = economies.get(s.ctx)
        if not economy:
            continue
        target = realized_value(s, economy, require_turn=True)
        if target is None:
            continue
        logged = s.move.get("priority_score")
        # Never label an old decision with today's reconstructed policy.
        # Missing clocks and changed weights can differ by tens of points.
        if (logged is None or
                (s.raw.get('ranking_provenance') or {}).get('schema_version', 0) < 2):
            rebuild_failures += 1
            continue
        try:
            priority = float(logged)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(priority) or not np.isfinite(target):
            continue
        try:
            logged_checks.append(rebuild_evaluation.runtime_priority(s.raw, s.move) - priority)
        except Exception:
            pass
        before = s.before or {}
        row = learned_value.features(
            s.move,
            s.ctx,
            s.board,
            s.special_board,
            charge=before.get("booster_charge"),
            charge_max=before.get("booster_maximum"),
            remaining_moves=before.get("remaining_moves"),
            current_round=before.get("current_round"),
            total_rounds=before.get("total_rounds"),
            score_deficit=before.get("score_deficit"),
            phase=s.move.get("phase") or "unknown",
        )
        xs.append(row)
        ys.append(target)
        priorities.append(priority)
        days.append(s.day)
        ctxs.append(s.ctx)
    if rebuild_failures:
        print(f"  bez pouzdanog prioriteta/schema v2: {rebuild_failures} poteza (preskoceni)")
    if logged_checks:
        gaps = np.abs(np.array(logged_checks))
        print(
            f"  provera rekonstrukcije prema upisanom prioritetu: n={len(gaps)}, "
            f"medijana |razlika| {np.median(gaps):.3f}, max {gaps.max():.3f}"
        )
    return (
        np.array(xs, dtype=float).reshape(-1, len(learned_value.FEATURE_NAMES)),
        np.array(ys),
        np.array(priorities),
        np.array(days),
        np.array(ctxs),
    )


def make_model(seed=0):
    from sklearn.ensemble import GradientBoostingRegressor

    return GradientBoostingRegressor(
        loss="huber",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=3,
        subsample=0.8,
        min_samples_leaf=20,
        random_state=seed,
    )


# Rezidual je u jedinicama stvarne vrednosti; na skalu prioriteta ga vraca
# 1/b, ali b je nagib *preko* odluka (prioritet nosi i buducnost, tempo, premije
# koje se na jednom potezu ne naplate), pa 1/b = 4-5 preterano pojacava
# razlike *unutar* jedne odluke. Kapa od 2x drzi uticaj modela u opsegu koji
# heuristika sama koristi za pojedinacne bonuse.
RESIDUAL_SCALE_MAX = 2.0


def residual_scale(b: float) -> float:
    return min(RESIDUAL_SCALE_MAX, 1.0 / b)


def linear_baseline(priorities, ys):
    """realized ~ a + b * priority. Prioritet je skala za rangiranje, ne
    predvidjanje (tempo x2 za extra, premija za pun metar...), pa je ~2x veci
    od stvarne vrednosti; ta *globalna* skala se ne uci kroz stabla nego se
    skine linearno, a model uci samo ono sto od nje odstupa po kandidatu."""
    matrix = np.column_stack([np.ones_like(priorities), priorities])
    coef, *_ = np.linalg.lstsq(matrix, ys, rcond=None)
    a, b = float(coef[0]), float(coef[1])
    if b <= 0.05:
        b = 0.05
    return a, b


def day_folds(days, folds=5):
    unique_days = sorted(set(days))
    rng = np.random.default_rng(0)
    rng.shuffle(unique_days)
    buckets = {day: index % folds for index, day in enumerate(unique_days)}
    return np.array([buckets[d] for d in days])


def cross_validate(xs, ys, priorities, days, ctxs, blend: float, folds=5):
    fold_of = day_folds(days, folds)
    linear_pred = np.zeros_like(ys)
    model_pred = np.zeros_like(ys)
    blended_pred = np.array(priorities, dtype=float)
    fold_models = {}
    for fold in range(folds):
        train = fold_of != fold
        test = fold_of == fold
        if test.sum() == 0 or train.sum() < 100:
            continue
        a, b = linear_baseline(priorities[train], ys[train])
        model = make_model(fold)
        model.fit(xs[train], ys[train] - (a + b * priorities[train]))
        residual = model.predict(xs[test])
        linear_pred[test] = a + b * priorities[test]
        model_pred[test] = linear_pred[test] + residual
        # U igri: prioritet + blend * rezidual / b (nazad na skalu prioriteta).
        blended_pred[test] = priorities[test] + blend * np.clip(
            residual * residual_scale(b), -learned_value.RESIDUAL_CLAMP, learned_value.RESIDUAL_CLAMP
        )
        fold_models[fold] = (a, b, model)
    report = {}
    for label, mask in [("sve", np.ones_like(ys, dtype=bool))] + [
        (ctx, ctxs == ctx) for ctx in sorted(set(ctxs))
    ]:
        if mask.sum() == 0:
            continue
        y = ys[mask]
        var = float(((y - y.mean()) ** 2).mean()) or 1.0
        p = priorities[mask]
        report[label] = {
            "n": int(mask.sum()),
            "mae_linear": round(float(np.abs(linear_pred[mask] - y).mean()), 2),
            "mae_with_model": round(float(np.abs(model_pred[mask] - y).mean()), 2),
            "r2_linear": round(1.0 - float(((linear_pred[mask] - y) ** 2).mean()) / var, 3),
            "r2_with_model": round(1.0 - float(((model_pred[mask] - y) ** 2).mean()) / var, 3),
            "spearman_priority": round(_spearman(p, y), 3),
            "spearman_with_model": round(_spearman(model_pred[mask], y), 3),
            "spearman_blended": round(_spearman(blended_pred[mask], y), 3),
        }
    return report, fold_models, fold_of


def decision_changes(samples, economies, fold_models, fold_of_day: dict, blend: float, limit=3000):
    """Na koliko snimljenih odluka bi model (test preklop tog dana) promenio
    kandidata sa najvisim prioritetom. Ignorise kategorijske nivoe rangiranja
    (extra / disko / metla) -- gornja granica uplitanja, ne tacan broj."""
    checked = 0
    changed = 0
    for s in samples:
        if checked >= limit:
            break
        if not s.is_move or s.swallowed or len(s.candidates) < 2:
            continue
        fold = fold_of_day.get(s.day)
        if fold is None or fold not in fold_models:
            continue
        a, b, model = fold_models[fold]
        before = s.before or {}
        rows, priorities = [], []
        try:
            for cand in s.candidates:
                priorities.append(rebuild_evaluation.runtime_priority(s.raw, cand))
                rows.append(
                    learned_value.features(
                        cand,
                        s.ctx,
                        s.board,
                        s.special_board,
                        charge=before.get("booster_charge"),
                        charge_max=before.get("booster_maximum"),
                        remaining_moves=before.get("remaining_moves"),
                        current_round=before.get("current_round"),
                        total_rounds=before.get("total_rounds"),
                        score_deficit=before.get("score_deficit"),
                        phase=cand.get("phase") or "unknown",
                    )
                )
        except Exception:
            continue
        priorities = np.array(priorities)
        residual = np.clip(
            model.predict(np.array(rows)) * residual_scale(b),
            -learned_value.RESIDUAL_CLAMP,
            learned_value.RESIDUAL_CLAMP,
        )
        adjusted = priorities + blend * residual
        checked += 1
        if int(np.argmax(priorities)) != int(np.argmax(adjusted)):
            changed += 1
    return checked, changed


def _spearman(a, b) -> float:
    from scipy.stats import spearmanr

    value = spearmanr(a, b).correlation
    return 0.0 if value is None or np.isnan(value) else float(value)


def export_trees(model) -> list[dict]:
    trees = []
    for estimator in model.estimators_[:, 0]:
        tree = estimator.tree_
        trees.append(
            {
                "left": [int(v) for v in tree.children_left],
                "right": [int(v) for v in tree.children_right],
                "feature": [int(v) for v in tree.feature],
                "threshold": [float(v) for v in tree.threshold],
                "value": [float(v) for v in tree.value[:, 0, 0]],
            }
        )
    return trees


def feature_importance(model, names, top=15):
    pairs = sorted(zip(model.feature_importances_, names), reverse=True)[:top]
    return [(name, round(float(weight), 3)) for weight, name in pairs]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None)
    parser.add_argument("--runs", default=str(RUNS_DIR))
    parser.add_argument("--blend", type=float, default=0.5, help="udeo reziduala u rangiranju (0..1)")
    parser.add_argument("--test-since", default=None,
                        help="YYYY-MM-DD: prvi dan test skupa (podrazumevano prvi dan posle treninga starog modela)")
    parser.add_argument("--contexts", default=None,
                        help="zarezima odvojeni konteksti na koje se model uci i primenjuje "
                             "(npr. solo_race,solo_challenge); ostali ostaju cista heuristika")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="upisi i kada model ne popravlja gresku")
    args = parser.parse_args(argv)

    if not 0 <= args.blend <= 1:
        parser.error("--blend mora biti izmedju 0 i 1")
    print(f"Citam {args.runs} ...", flush=True)
    samples = load_samples(Path(args.runs), since=args.since)
    incumbent = learned_value.ValueModel(learned_value._read_json(MODEL_PATH))
    trained_day = str(incumbent.data.get('trained_at') or '')[:10]
    later_days = sorted({s.day for s in samples if s.day > trained_day})
    cutoff = args.test_since or (later_days[0] if incumbent.enabled and later_days else None)
    if incumbent.enabled and not later_days and not args.test_since:
        print("Nema novih dana posle treninga postojeceg modela; sacuvan postojeci model.")
        return 1
    only_contexts = None
    if args.contexts:
        only_contexts = sorted({c.strip() for c in args.contexts.split(",") if c.strip()})
        unknown = [c for c in only_contexts if c not in CONTEXTS]
        if unknown:
            parser.error(f"nepoznat kontekst: {unknown}")
        samples = [s for s in samples if s.ctx in only_contexts]
    train, test, cutoff = temporal_split(samples, cutoff=cutoff)
    from fit_weights import measure_economy, _paired_validation
    economies = {ctx: measure_economy(train, ctx) for ctx in CONTEXTS}
    xs, ys, priorities, days, ctxs = build_rows(train, economies)
    tx, ty, tp, td, tc = build_rows(test, economies)
    if len(ys) < 100 or len(ty) < 40:
        print(f"Nedovoljno potpunih uzoraka: trening {len(ys)}, test {len(ty)}; model sacuvan.")
        return 1
    print(f"uzoraka {len(ys)} (dana {len(set(days))}), osobina {xs.shape[1]}")
    print("po kontekstu:", {str(ctx): int((ctxs == ctx).sum()) for ctx in sorted(set(ctxs))})
    residual_all = ys - priorities
    print(
        f"cilj (stvarna vrednost): prosek {ys.mean():.1f}, medijana {np.median(ys):.1f}, std {ys.std():.1f}; "
        f"prioritet: prosek {priorities.mean():.1f}; rezidual: prosek {residual_all.mean():.1f}, std {residual_all.std():.1f}"
    )

    a, b = linear_baseline(priorities, ys)
    model = make_model(0)
    model.fit(xs, ys - (a + b * priorities))
    residual = model.predict(tx)
    adjusted = tp + args.blend * np.clip(residual * residual_scale(b),
                                        -learned_value.RESIDUAL_CLAMP, learned_value.RESIDUAL_CLAMP)
    # Evaluate the actual clipped/blended runtime correction, not a full
    # residual that production never uses. Economy is frozen from train only.
    base = a + b*tp
    predicted = a + b*adjusted
    report = {}
    for label, mask in [('sve', np.ones(len(ty), dtype=bool))] + [(ctx, tc == ctx) for ctx in CONTEXTS]:
        if not mask.any():
            continue
        report[label] = {'n': int(mask.sum()),
                         'mae_linear': float(np.mean(abs(base[mask]-ty[mask]))),
                         'mae_blended': float(np.mean(abs(predicted[mask]-ty[mask]))),
                         'spearman_priority': _spearman(tp[mask], ty[mask]),
                         'spearman_blended': _spearman(adjusted[mask], ty[mask])}
    # build_rows preserves order; match its eligible logged samples to games.
    eligible = [s for s in test if s.is_move and not s.swallowed and not s.charge_censored
                and s.move.get('priority_score') is not None
                and (s.raw.get('ranking_provenance') or {}).get('schema_version', 0) >= 2
                and realized_value(s, economies.get(s.ctx, {}), require_turn=True) is not None]
    games = [s.game_id for s in eligible]
    if len(games) != len(ty):
        print('Nepodudarni uzorci validacije; model nije upisan.')
        return 1
    validation = _paired_validation(abs(base-ty), abs(predicted-ty), games)
    if incumbent.enabled:
        old_adjusted = tp + incumbent.blend*np.array([incumbent.residual(list(row)) for row in tx])
        old_error = abs(a+b*old_adjusted-ty)
        validation['against_incumbent'] = _paired_validation(old_error, abs(predicted-ty), games)
        validation['accepted'] = validation['accepted'] and validation['against_incumbent']['accepted']
    # Do not replace a multi-context model based on improvements only in solo.
    required = set(ctxs)
    validation['missing_contexts'] = sorted(ctx for ctx in required if int((tc == ctx).sum()) < 30)
    validation['accepted'] = validation['accepted'] and not validation['missing_contexts']
    validation['accepted'] = validation['accepted'] and all(
        r['mae_blended'] <= r['mae_linear'] and r['spearman_blended'] >= r['spearman_priority']
        for k, r in report.items() if k != 'sve' and r['n'] >= 30)
    improves = validation['accepted']
    print(f'\n=== Trening pre {cutoff}; odvojen test od {cutoff} ===')
    print(json.dumps({'metrics': report, 'validation': validation}, indent=2))
    print(f"\nlinearna osnova: stvarna vrednost ~ {a:.2f} + {b:.3f} * prioritet")
    print("najvaznije osobine reziduala:")
    for name, weight in feature_importance(model, learned_value.FEATURE_NAMES):
        print(f"  {name:32} {weight}")
    init = float(model._raw_predict_init(xs[:1])[0, 0])
    payload = {
        "trained_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "tool": "tools/train_value_model.py",
        "enabled": True,
        # Samo ovi konteksti dobijaju korekciju (learned_value.residual_adjustment);
        # None = svi, kao ranije.
        "contexts": only_contexts,
        "blend": args.blend,
        "target": "realized_value - (a + b * logged_priority)",
        "baseline": {"a": round(a, 3), "b": round(b, 4)},
        # Rezidual je u jedinicama stvarne vrednosti; u igri se mnozi ovim da
        # se vrati na skalu prioriteta (1/b, ograniceno na RESIDUAL_SCALE_MAX).
        "residual_scale": round(residual_scale(b), 4),
        "validation": {**validation, "test_since": cutoff, "method": "chronological_game_bootstrap"},
        "economies": economies,
        "ranking_provenance": learned_value.ranking_provenance(),
        "feature_names": list(learned_value.FEATURE_NAMES),
        "samples": int(len(ys)),
        "days": len(set(days)),
        "init": init,
        "learning_rate": float(model.learning_rate),
        "metrics": report,
        "trees": export_trees(model),
    }
    if args.dry_run:
        print("\n--dry-run: nista nije upisano.")
        return 0
    if not improves and not args.force:
        print("\nModel nije prosao odvojenu proveru; postojeci fajl je sacuvan.")
        return 1
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists():
        import shutil
        shutil.copyfile(MODEL_PATH, MODEL_PATH.with_suffix('.prev.json'))
    pending = MODEL_PATH.with_suffix('.tmp.json')
    pending.write_text(json.dumps(payload), encoding="utf-8")
    pending.replace(MODEL_PATH)
    print(f"\nUpisano {MODEL_PATH} ({MODEL_PATH.stat().st_size // 1024} KB, {len(payload['trees'])} stabala, blend {args.blend})")
    check = learned_value.ValueModel(json.loads(MODEL_PATH.read_text(encoding="utf-8")))
    sample_rows = xs[:200]
    ours = np.array([check.raw(list(row)) for row in sample_rows])
    theirs = model.predict(sample_rows)
    print(f"provera JSON stabala: max odstupanje od sklearn-a {np.abs(ours - theirs).max():.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
