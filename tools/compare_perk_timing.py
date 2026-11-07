"""Perk sada ili posle: na istoj tabli ravnopravno poredi tri opcije.

    python tools/compare_perk_timing.py RUN [RUN ...] [--seed 0] [--samples 64]

Za svaku odluku: najbolji obican swipe (perk ostaje politici nastavka),
najbolji perk odmah (sa najboljom metom) i, gde postoji garantovani extra,
"extra pa perk" (meta se bira na tabli posle extra). Najbolji predstavnik svake
opcije se bira po proseku iz brze analize, a onda se tri predstavnika odigraju
na istih `--samples` seed-ova, pa su razlike uparene. Pise se i razlika bez
poena bustera, jer efekat bustera nije simuliran.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import turn_analyzer as ta  # noqa: E402

OPTIONS = ("swipe", "perk odmah", "extra pa perk")


def _option(plan) -> str | None:
    if plan["kind"] == "swap":
        return "swipe"
    if plan["kind"] == "perk":
        return "perk odmah"
    if plan["kind"] == "sequence" and plan["key"].endswith("@najbolja"):
        return "extra pa perk"
    return None


def _paired(a, b, field):
    if field == "total_ex":
        diffs = [(x.total - x.booster_points) - (y.total - y.booster_points) for x, y in zip(a, b)]
    else:
        diffs = [getattr(x, field) - getattr(y, field) for x, y in zip(a, b)]
    mean = statistics.fmean(diffs)
    se = statistics.stdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else 0.0
    return mean, se


def compare(payload):
    decision, seed, samples = payload
    started = time.perf_counter()
    analysis = ta.DecisionAnalysis(decision, seed=seed)
    quick = analysis.run()
    plans, _ = analysis.root_plans()
    by_key = {p["key"]: p for p in plans}
    chosen = {}
    for row in quick["actions"]:
        option = _option(by_key[row["key"]])
        if option and option not in chosen:
            chosen[option] = row["key"]
    branches = {opt: [analysis.rollout(by_key[key], i) for i in range(samples)] for opt, key in chosen.items()}
    out = {"run": decision.run, "mode": decision.mode, "round": decision.round, "total_rounds": decision.total_rounds,
           "remaining_moves": decision.remaining_moves, "multiplier": analysis.root.multiplier,
           "booster": f"{decision.booster_charge}/{decision.booster_max}", "final_turn": analysis.final_turn,
           "played": quick["verdict"].get("played_label"), "actual": (decision.outcome or {}).get("points"),
           "options": {}, "pairs": [], "seconds": None}
    for opt, items in branches.items():
        totals = [b.total for b in items]
        out["options"][opt] = {
            "label": by_key[chosen[opt]]["label"],
            "total": statistics.fmean(totals),
            "se": statistics.stdev(totals) / len(totals) ** 0.5,
            "ex_booster": statistics.fmean(b.total - b.booster_points for b in items),
            "booster": statistics.fmean(b.booster_points for b in items),
            "cut": sum(1 for b in items if b.ended_by in ta.CUT_ENDINGS) / len(items),
            "perks_left": statistics.fmean(b.perks_left for b in items),
            "perk_used_in_continuation": sum(1 for b in items if b.perks_used) / len(items),
        }
    names = [o for o in OPTIONS if o in branches]
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            mean, se = _paired(branches[a], branches[b], "total")
            mean_ex, se_ex = _paired(branches[a], branches[b], "total_ex")
            out["pairs"].append({"a": a, "b": b, "diff": mean, "se": se, "diff_ex_booster": mean_ex, "se_ex": se_ex,
                                 "clear": abs(mean) > ta.TIE_SIGMAS * se,
                                 "clear_ex_booster": abs(mean_ex) > ta.TIE_SIGMAS * se_ex})
    out["seconds"] = round(time.perf_counter() - started, 1)
    return out


def _fmt(x):
    return f"{x:,.0f}".replace(",", " ")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default=str(ta.ANALYSIS_DIR / "perk_timing.json"))
    args = parser.parse_args(argv)
    days = sorted({r[:10] for r in args.runs})
    decisions = {}
    for day in days:
        loaded = ta.load_decisions(ta.list_runs(day))
        for context in {d.context for d in loaded}:
            ta.segment_matches([d for d in loaded if d.context == context])
        decisions.update({d.run: d for d in loaded})
    payloads = [(decisions[r], args.seed, args.samples) for r in args.runs]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(compare, payloads))
    lines = ["# Perk sada ili posle (uparene grane)", "",
             f"seed {args.seed}, {args.samples} grana po opciji; poeni do predaje reda (simulirano).", ""]
    for r in results:
        lines += [f"## {r['run']} -- {r['mode']}, runda {r['round']}/{r['total_rounds']}, potezi {r['remaining_moves']}, "
                  f"x{r['multiplier']:.0f}, buster {r['booster']}" + (" (poslednji red partije)" if r["final_turn"] else ""),
                  "", f"Bot je odigrao {r['played']} (stvarno {r['actual']} poena).", "",
                  "| opcija | akcija | do predaje E | +/-SE | od toga buster | bez bustera | prekinuto | perk iskoriscen u nastavku | perkova na predaji |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for opt in OPTIONS:
            o = r["options"].get(opt)
            if o:
                lines.append(f"| {opt} | {o['label']} | {_fmt(o['total'])} | {_fmt(o['se'])} | {_fmt(o['booster'])} | "
                             f"{_fmt(o['ex_booster'])} | {o['cut']:.0%} | {o['perk_used_in_continuation']:.0%} | {o['perks_left']:.2f} |")
            else:
                lines.append(f"| {opt} | nije moguce na ovoj tabli | | | | | | | |")
        lines.append("")
        for p in r["pairs"]:
            lines.append(f"- {p['a']} - {p['b']}: {_fmt(p['diff'])} +/- {_fmt(p['se'])} "
                         f"({'jasno' if p['clear'] else 'nejasno'}); bez bustera {_fmt(p['diff_ex_booster'])} +/- "
                         f"{_fmt(p['se_ex'])} ({'jasno' if p['clear_ex_booster'] else 'nejasno'})")
        lines += [f"- vreme: {r['seconds']} s", ""]
    md = "\n".join(lines)
    Path(args.out).write_text(json.dumps({"provenance": ta.provenance(vars(args)), "results": results},
                                         indent=1, ensure_ascii=False), encoding="utf-8")
    Path(args.out).with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(args.out)


if __name__ == "__main__":
    main()
