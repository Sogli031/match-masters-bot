"""Provera simulatora analizatora na stvarno odigranim akcijama.

Faza A -- tacnost pravila. Uporedjuje samo ono sto sledi iz vidljive table pre
prve nepoznate dopune: legalnost odigrane akcije, celije koje simulator smatra
poznatim (sve van rupa za dopunu), mesta specijala, deterministicke poene,
punjenje i garantovani extra. Upotrebljava se samo kad je posle akcije i dalje
nas red i kad je sledeci run neposredan nastavak (njegova tabla je tada tacno
ishod te akcije). Kad nesto ne moze nezavisno da se potvrdi, to se pise.

Faza B -- tacnost prognoze. Za odigranu akciju simulira raspodelu neposrednih
poena i nastavka reda i gleda gde stvarni ishod pada u tu raspodelu: percentil,
pokrivenost p10-p90, sistematsko odstupanje po modu i tipu akcije, zadrzavanje
reda. Kad je bot kasnije u istom redu birao drugacije od politike nastavka,
razlika ukupnih poena je oznacena (moze poticati od kasnijeg izbora).

Usput se meri raspodela dopune (boja + mode figura na rupama) po modu i pise u
Debug/analysis/refill_stats.json; analizator je koristi umesto ravnomerne.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter, defaultdict

import move_strategy as ms
import turn_analyzer as ta

REFILL_MODEL_SAMPLES = 16


def _action_type(decision, plan) -> str:
    if decision.proposed["type"] == "booster":
        return "buster"
    if decision.proposed["type"] == "perk":
        return f"perk:{decision.proposed.get('perk')}"
    if plan is not None and plan["first"].get("special_activation"):
        return "swipe:aktivacija specijala"
    return "swipe:obican"


def _immediate_next(decision, members_by_run) -> "ta.Decision | None":
    after = (decision.outcome or {}).get("after_run")
    if not after:
        return None
    nxt = members_by_run.get(after)
    if nxt is None or nxt.turn_owner != "us":
        return None
    if decision.outcome.get("after_turn_owner") != "us" or decision.outcome.get("round_changed"):
        return None
    return nxt


def phase_a_case(decision, nxt, analysis) -> dict:
    """Pravila na jednoj odigranoj akciji, pre prve nepoznate dopune."""
    plans, _unsupported = analysis.root_plans()
    key = ta.match_played(decision, plans)
    plan = next((p for p in plans if p["key"] == key), None)
    case = {"run": decision.run, "mode": decision.mode, "context": decision.context,
            "action_type": _action_type(decision, plan), "checks": {}}
    checks = case["checks"]
    if decision.proposed["type"] in ("swap", "perk"):
        checks["legal"] = "ok" if plan is not None else "GRESKA: odigrana akcija nije legalna u simulatoru"
    if plan is None or decision.proposed["type"] == "booster":
        if decision.proposed["type"] == "booster":
            checks["effect"] = ("nepotvrdivo deterministicki: Doctor Color izbor putanje nije poznat"
                                if analysis.sim.ability == 27 else
                                "nepotvrdivo: efekat bustera nije simuliran")
        return case
    first = plan["first"]
    rules = analysis.rules
    state = analysis.root
    if first["kind"] == "swap":
        result = first["result"]
        if ta._uses_random_targets(result):
            checks["cells"] = "nepotvrdivo: nasumicne mete specijala pre dopune"
            case["random"] = True
            return case
    elif first.get("perk") == ms.PERK_ENERGY_BOOST:
        checks["effect"] = "nepotvrdivo: Energy Boost menja samo punjenje sledeceg swipe-a"
        return case
    else:
        result = ta._sim_clear(state.board, state.special, ta.perk_cells(first["perk"], first["target"]),
                               rules, state.lava, random.Random(0))
        if ta._uses_random_targets(result):
            checks["cells"] = "nepotvrdivo: nasumicne mete specijala pre dopune"
            case["random"] = True
            return case
    board_after = nxt.move["board"]
    special_after = nxt.move["special_board"]
    holes = [(r, c) for r, row in enumerate(result.board) for c, v in enumerate(row) if v == ms.EMPTY]
    known = [(r, c) for r in range(len(result.board)) for c in range(len(result.board)) if (r, c) not in set(holes)]
    color_bad = [(r, c) for r, c in known if int(result.board[r][c]) != int(board_after[r][c])]
    special_place_bad = [(r, c) for r, c in known
                         if (int(result.special_board[r][c]) != 0) != (int(special_after[r][c]) != 0)]
    special_type_bad = [(r, c, int(result.special_board[r][c]), int(special_after[r][c])) for r, c in known
                        if int(result.special_board[r][c]) and int(special_after[r][c])
                        and int(result.special_board[r][c]) != int(special_after[r][c])]
    special_bad = special_place_bad
    case["known_cells"] = len(known)
    case["holes"] = len(holes)
    case["color_mismatch"] = len(color_bad)
    case["special_mismatch"] = len(special_place_bad)
    if special_type_bad:
        case["special_type_mismatch"] = [
            {"cell": [r, c], "sim": sim, "igra": real} for r, c, sim, real in special_type_bad
        ]
    det_units = ta._units(result, rules)
    observed = decision.outcome.get("points")
    mult = state.multiplier
    case["det_points"] = det_units * mult
    case["observed_points"] = observed
    refill_cascade = observed is not None and observed > det_units * mult + 0.5 * mult
    if observed is not None and decision.multiplier_source.startswith("memorija") and holes:
        case["observed_refill_cascade"] = bool(refill_cascade)
        hits = 0
        for index in range(REFILL_MODEL_SAMPLES):
            probe = ta.replace(state, board=ta._grid_lists(result.board), special=ta._grid_lists(result.special_board))
            info = {"growth": 0.0, "activated": 0.0, "blue": 0.0, "first_unknown": None, "extra_uncertain": False}
            if ta._settle(probe, rules, random.Random(index), [], info) > 0:
                hits += 1
        case["model_refill_cascade_rate"] = hits / REFILL_MODEL_SAMPLES
    if special_type_bad:
        pairs = ", ".join(f"sim {t['sim']} / igra {t['igra']}" for t in case["special_type_mismatch"])
        checks["special_type"] = f"GRESKA: tip kreiranog specijala ({pairs})"
    elif any(int(result.special_board[r][c]) for r, c in known):
        checks["special_type"] = "ok"
    if not color_bad and not special_bad:
        checks["cells"] = "ok"
        checks["specials"] = "ok"
        case["refill_tiles"] = [
            f"{int(board_after[r][c])}:{int(special_after[r][c])}" for r, c in holes
        ]
    elif refill_cascade:
        checks["cells"] = (f"nepotvrdivo: kaskada posle dopune pomerila poznate celije "
                           f"({len(color_bad)} boja, {len(special_bad)} specijala razlicito)")
    else:
        checks["cells"] = f"GRESKA: {len(color_bad)} poznatih celija se razlikuje"
        checks["specials"] = "ok" if not special_bad else f"GRESKA: {len(special_bad)} specijala na drugom mestu"
        case["mismatch_cells"] = [list(c) for c in color_bad[:10]]
    if observed is not None and decision.multiplier_source.startswith("memorija"):
        if refill_cascade:
            checks["points"] = f"vise od det. dela (kaskada posle dopune): det {det_units * mult:.0f}, stvarno {observed}"
        elif abs(observed - det_units * mult) <= 0.5 * mult:
            checks["points"] = "ok"
        else:
            checks["points"] = f"GRESKA: det {det_units * mult:.0f}, stvarno {observed}"
    else:
        checks["points"] = "nepotvrdivo: mnozilac nije iz memorije"
    charge = decision.outcome.get("charge_gained")
    if charge is not None and analysis.root.charge is not None:
        predicted = float(result.blue_cells)
        room = (analysis.root.charge_max or 0) - analysis.root.charge
        predicted_gain = min(room, predicted)
        if refill_cascade:
            checks["charge"] = f"nepotvrdivo (dopuna): det {predicted_gain:g}, stvarno {charge}"
        else:
            checks["charge"] = "ok" if abs(predicted_gain - float(charge)) < 0.5 else f"GRESKA: det {predicted_gain:g}, stvarno {charge}"
    if first["kind"] == "swap":
        guaranteed = result.extra_moves > 0
        case["guaranteed_extra"] = guaranteed
        observed_extra = decision.outcome.get("observed_extra")
        if guaranteed:
            if observed_extra is None:
                checks["extra"] = "nepotvrdivo: broj poteza posle akcije nije zabelezen"
            else:
                checks["extra"] = "ok" if observed_extra else "GRESKA: obecani extra, potez je potrosen"
    return case


def build_refill_stats(cases: list[dict]) -> dict:
    modes = defaultdict(Counter)
    runs = Counter()
    for case in cases:
        tiles = case.get("refill_tiles")
        if not tiles:
            continue
        for key in (case["mode"], f"{case['mode']}|{case.get('context')}"):
            modes[key].update(tiles)
            runs[key] += 1
    out = {"note": ("Boja:specijal na celijama koje simulator ostavlja praznim, merene na potezima "
                    "posle kojih je red ostao nas i sve poznate celije su se slozile. Ishod je "
                    "posle smirivanja table (bez spojeva), pa nije sirovi tok dopune."),
           "modes": {}}
    for mode, counter in modes.items():
        tiles = sum(counter.values())
        colors = Counter()
        for key, value in counter.items():
            colors[int(key.split(":")[0])] += value
        k = len(colors) or 1
        expected = tiles / k
        chi2 = sum((v - expected) ** 2 / expected for v in colors.values()) if expected else 0.0
        out["modes"][mode] = {
            "tiles": tiles, "runs": runs[mode], "counts": dict(counter),
            "color_share": {str(c): v / tiles for c, v in sorted(colors.items())},
            "chi2_vs_uniform": chi2, "dof": k - 1,
            "special_share": {key: v / tiles for key, v in counter.items() if not key.endswith(":0")},
        }
    return out


def phase_b_case(decision, analysis, samples: int, turn_members: list, policy_check: bool = True) -> dict | None:
    plans, _ = analysis.root_plans()
    key = ta.match_played(decision, plans)
    plan = next((p for p in plans if p["key"] == key), None)
    if plan is None:
        return None
    branches = [analysis.rollout(plan, i) for i in range(samples)]
    imm = sorted(b.immediate for b in branches)
    observed = decision.outcome.get("points")
    if observed is None:
        return None
    below = sum(1 for v in imm if v < observed) + 0.5 * sum(1 for v in imm if v == observed)
    s = ta.summary(imm)
    case = {
        "run": decision.run, "mode": decision.mode, "context": decision.context,
        "action_type": _action_type(decision, plan),
        "random": any(b.random for b in branches),
        "observed": observed, "pred_mean": s["mean"], "p10": s["p10"], "p90": s["p90"],
        "percentile": below / len(imm), "inside_p10_p90": s["p10"] <= observed <= s["p90"],
        "pred_another": sum(b.another_decision for b in branches) / len(branches),
        "observed_another": decision.outcome.get("next_is_ours"),
        "pred_extra": sum(b.first_extra for b in branches) / len(branches),
        "observed_extra": decision.outcome.get("observed_extra"),
        "promised_extra": all(b.guaranteed_extra for b in branches),
        "multiplier_source": decision.multiplier_source,
        "unverified": sorted(set().union(*(b.unverified for b in branches))),
    }
    # Ceo red: stvarni poeni od ove odluke do predaje vs simulirani ukupni.
    if turn_members:
        obs_turn = [m.outcome.get("points") for m in turn_members]
        if all(p is not None for p in obs_turn):
            case["observed_turn"] = sum(obs_turn)
            case["pred_turn_mean"] = statistics.fmean(b.total for b in branches)
            case["pred_turn_p10"] = ta.summary([b.total for b in branches])["p10"]
            case["pred_turn_p90"] = ta.summary([b.total for b in branches])["p90"]
            diverged = []
            if policy_check:
                for later in turn_members[1:]:
                    if ta.skip_reason(later):
                        continue
                    la = ta.DecisionAnalysis(later, seed=analysis.seed)
                    action, _value = la.sim.choose_action(la.root)
                    lplans, _ = la.root_plans()
                    pk = ta.match_played(later, lplans)
                    if action is None or pk != action["key"]:
                        diverged.append(later.run)
            case["bot_diverged_from_policy"] = diverged
    return case


def turn_slice(members: list, index: int) -> list:
    """Odluke od `index` do predaje istog reda; [] ako predaja nije zabelezena."""
    first = members[index]
    out = []
    for decision in members[index:]:
        if decision.round != first.round or decision.turn_owner not in (None, "us"):
            return []
        out.append(decision)
        outcome = decision.outcome
        if outcome.get("after_turn_owner") not in (None, "us") or outcome.get("round_changed"):
            return out
    return []


def aggregate_a(cases: list[dict]) -> dict:
    groups = defaultdict(lambda: Counter())
    for case in cases:
        key = f"{case['mode']} | {case['action_type']}"
        g = groups[key]
        g["slucajeva"] += 1
        for name, value in case["checks"].items():
            if value == "ok":
                g[f"{name}:ok"] += 1
            elif value.startswith("GRESKA"):
                g[f"{name}:greska"] += 1
            else:
                g[f"{name}:nepotvrdivo"] += 1
    return {k: dict(v) for k, v in sorted(groups.items())}


def aggregate_b(cases: list[dict]) -> dict:
    groups = defaultdict(list)
    for case in cases:
        groups[f"{case['mode']} | {case['action_type']} | {'nasumicno' if case['random'] else 'det.'}"].append(case)
    out = {}
    for key, items in sorted(groups.items()):
        bias = [c["observed"] - c["pred_mean"] for c in items]
        rel = [(c["observed"] - c["pred_mean"]) / max(1.0, c["pred_mean"]) for c in items]
        kept = [c for c in items if c["observed_another"] is not None]
        extra_known = [c for c in items if c.get("observed_extra") is not None]
        promised = [c for c in items if c["promised_extra"] and c.get("observed_extra") is not None]
        turns = [c for c in items if "observed_turn" in c]
        clean_turns = [c for c in turns if not c.get("bot_diverged_from_policy")]
        out[key] = {
            "n": len(items),
            "mean_abs_err": statistics.fmean(abs(b) for b in bias),
            "mean_bias": statistics.fmean(bias),
            "mean_rel_bias": statistics.fmean(rel),
            "coverage_p10_p90": sum(c["inside_p10_p90"] for c in items) / len(items),
            "mean_percentile": statistics.fmean(c["percentile"] for c in items),
            "brier_another": (statistics.fmean((c["pred_another"] - float(bool(c["observed_another"]))) ** 2 for c in kept)
                              if kept else None),
            "brier_extra": (statistics.fmean((c["pred_extra"] - float(bool(c["observed_extra"]))) ** 2 for c in extra_known)
                            if extra_known else None),
            "extra_rate_pred_vs_obs": (f"{statistics.fmean(c['pred_extra'] for c in extra_known):.0%} / "
                                       f"{statistics.fmean(float(bool(c['observed_extra'])) for c in extra_known):.0%}"
                                       if extra_known else None),
            "another_rate_pred_vs_obs": (f"{statistics.fmean(c['pred_another'] for c in kept):.0%} / "
                                         f"{statistics.fmean(float(bool(c['observed_another'])) for c in kept):.0%}"
                                         if kept else None),
            "promised_extra_kept": (f"{sum(1 for c in promised if c['observed_extra'])}/{len(promised)}"
                                    if promised else None),
            "turn_cases": len(turns),
            "turn_mean_bias": statistics.fmean(c["observed_turn"] - c["pred_turn_mean"] for c in turns) if turns else None,
            "turn_cases_policy_match": len(clean_turns),
            "turn_mean_bias_policy_match": (statistics.fmean(c["observed_turn"] - c["pred_turn_mean"] for c in clean_turns)
                                            if clean_turns else None),
        }
    return out


def validate(decisions: list, *, samples: int = 16, seed: int = 0, phase: str = "ab", progress=None) -> dict:
    """Obe faze nad zadatim odlukama (vec segmentiranim u partije)."""
    by_run = {d.run: d for d in decisions}
    by_match = defaultdict(list)
    for d in decisions:
        by_match[d.match_id].append(d)
    coverage = Counter()
    skipped = Counter()
    a_cases, b_cases = [], []
    for match_id, members in by_match.items():
        members.sort(key=lambda d: d.run)
        for index, decision in enumerate(members):
            coverage["pronadjeno odluka"] += 1
            reason = ta.skip_reason(decision)
            if reason:
                skipped[reason.split(" (")[0]] += 1
                continue
            if decision.outcome.get("status") != "potvrdjeno":
                skipped[f"ishod: {decision.outcome.get('status')}"] += 1
                continue
            coverage["analizirano"] += 1
            analysis = ta.DecisionAnalysis(decision, seed=seed)
            if "a" in phase:
                nxt = _immediate_next(decision, by_run)
                if nxt is not None:
                    a_cases.append(phase_a_case(decision, nxt, analysis))
                else:
                    coverage["faza A: nema neposrednog nastavka (red presao ili prekid)"] += 1
            if "b" in phase:
                case = phase_b_case(decision, analysis, samples, turn_slice(members, index))
                if case is not None:
                    b_cases.append(case)
                else:
                    coverage["faza B: odigrana akcija nije legalna ili nema poena"] += 1
            if progress:
                progress(decision.run)
    rc = [c for c in a_cases if "observed_refill_cascade" in c]
    refill_cascade = None
    if rc:
        refill_cascade = {
            "n": len(rc),
            "observed_rate": sum(c["observed_refill_cascade"] for c in rc) / len(rc),
            "model_rate": statistics.fmean(c["model_refill_cascade_rate"] for c in rc),
        }
    return {
        "refill_cascade": refill_cascade,
        "coverage": dict(coverage), "skipped": dict(skipped),
        "phase_a": {"by_group": aggregate_a(a_cases), "cases": a_cases},
        "phase_b": {"by_group": aggregate_b(b_cases), "cases": b_cases},
        "refill": build_refill_stats(a_cases),
    }
