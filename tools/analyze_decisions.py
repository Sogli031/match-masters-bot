"""Offline analiza odluka iz Debug/runs (turn_analyzer + turn_validation).

    python tools/analyze_decisions.py decision 2026-10-31_11-46-47_172 [--all] [--trace]
    python tools/analyze_decisions.py match    2026-10-31_11-46-47_172
    python tools/analyze_decisions.py day      2026-10-31 [--context versus]
    python tools/analyze_decisions.py validate --day 2026-10-31 [--context versus] [--mode "Multiplier Mushrooms Studio"]
    python tools/analyze_decisions.py refill-stats [--since 2026-10-01]
    python tools/analyze_decisions.py compare  STARI.json NOVI.json
    python tools/analyze_decisions.py index

Zajednicke opcije: --seed N (podrazumevano 0), --samples N, --detailed
(64 grane za bliske kandidate umesto 8), --max-steps N, --workers N, --out DIR.
Izlaz: Debug/analysis/<ime>.md (citljivo, svaki red vodi do Debug foldera) i
<ime>.json (masinski: verzija koda/modela, konfiguracija, seed, sve akcije).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import turn_analyzer as ta  # noqa: E402
import turn_validation as tv  # noqa: E402

CONTEXT_CHOICES = ta.CONTEXTS + ("all",)


# ---------------------------------------------------------------------------
# Ucitavanje


def _decisions_for_day(day: str, context: str) -> list:
    decisions = ta.load_decisions(ta.list_runs(day))
    if context != "all":
        decisions = [d for d in decisions if d.context == context]
    ta.segment_matches(decisions)
    return decisions


def _match_of(run: str) -> list:
    day = run[:10]
    decisions = ta.load_decisions(ta.list_runs(day))
    target = next((d for d in decisions if d.run == run), None)
    if target is None:
        raise SystemExit(f"run {run} nije pronadjen u {ta.RUNS_DIR}")
    same = [d for d in decisions if d.context == target.context]
    matches = ta.segment_matches(same)
    for members in matches:
        if any(d.run == run for d in members):
            return members
    return [target]


def _config(args) -> dict:
    return {"seed": args.seed, "samples": args.samples, "detailed": args.detailed,
            "max_steps": args.max_steps, "fast_samples": ta.DEFAULT_FAST_SAMPLES,
            "detailed_samples": ta.DEFAULT_DETAILED_SAMPLES, "tie_sigmas": ta.TIE_SIGMAS,
            "clock_seconds_per_action": ta.CLOCK_SECONDS_PER_ACTION}


def _analyze_one(payload):
    decision, config, traces = payload
    started = time.perf_counter()
    try:
        result = ta.analyze_decision(decision, seed=config["seed"], samples=config["samples"],
                                     detailed=config["detailed"], max_steps=config["max_steps"], traces=traces)
    except Exception as exc:  # jedna losa odluka ne sme da obori celu partiju
        return {"run": decision.run, "error": f"{type(exc).__name__}: {exc}", "path": str(decision.path)}
    result["seconds"] = round(time.perf_counter() - started, 2)
    return ta.strip_for_json(result)


def analyze_many(decisions: list, config: dict, workers: int, traces: bool = False) -> tuple[list, list]:
    todo, skipped = [], []
    for decision in decisions:
        reason = ta.skip_reason(decision)
        if reason:
            skipped.append({"run": decision.run, "reason": reason, "path": str(decision.path)})
        else:
            todo.append(decision)
    payloads = [(d, config, traces) for d in todo]
    if workers > 1 and len(payloads) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_analyze_one, payloads))
    else:
        results = [_analyze_one(p) for p in payloads]
    return results, skipped


# ---------------------------------------------------------------------------
# Formatiranje


def _f(value, digits=0):
    if value is None:
        return "-"
    return f"{value:,.{digits}f}".replace(",", " ")


def _rel(path: str, out_dir: Path) -> str:
    try:
        return os.path.relpath(path, out_dir).replace("\\", "/")
    except ValueError:
        return Path(path).as_uri()


def _round_phrase(r: dict) -> str:
    left = r.get("remaining_moves")
    phrase = {1: "poslednji potez reda", 2: "dva poteza u redu", 3: "tri poteza u redu"}.get(left, f"{left} poteza u redu")
    if r["context"] != ta.CTX_VERSUS:
        phrase = f"{left} preostalih poteza"
    return f"Runda {r.get('round')}/{r.get('total_rounds')}, {phrase}, x{_f(r.get('multiplier'), 0)}"


def headline(r: dict) -> str:
    v = r.get("verdict") or {}
    played = v.get("played_label") or (r.get("proposed") or {}).get("type")
    actual = r.get("outcome") or {}
    actual_text = ""
    if actual.get("status") == "potvrdjeno" and actual.get("points") is not None:
        actual_text = f" Stvarno je odigrana putanja dala {actual['points']:+d} poena ({actual.get('source')})."
    if not v.get("played_key"):
        return (f"{_round_phrase(r)}. Bot je odigrao {played}, ali ta akcija nije medju legalnim akcijama "
                f"rekonstruisanog stanja. Simulator predlaze {v.get('best_label')}.{actual_text}")
    d = v.get("diff_vs_played") or {}
    caveats = []
    if v.get("booster_dependent"):
        if v.get("booster_selection_unverified"):
            caveats.append("izbor zavisi od nepotvrdjenog pravila izbora Doctor Color putanje")
        else:
            caveats.append("izbor zavisi od empirijskog bustera, pa ni akcija ni meta nisu potvrdjene")
    if v.get("limit_cut_after_extension"):
        caveats.append("deo grana nije stigao do predaje ni posle produzenja, pobednik nije utvrdjen")
    if v.get("perk_residual_note"):
        caveats.append(v["perk_residual_note"])
    caveat_text = (" Napomena: " + "; ".join(caveats) + ".") if caveats else ""
    if v.get("tie_with_played") and caveats and v.get("best_key") != v.get("played_key"):
        return (f"{_round_phrase(r)}. Bot je odigrao {played}. Simulator na prvo mesto stavlja {v.get('best_label')} "
                f"({_f(d.get('mean'))} +/- {_f(d.get('se'))} poena, simulirano), ali pobednik nije utvrdjen.{caveat_text}{actual_text}")
    if v.get("tie_with_played"):
        return (f"{_round_phrase(r)}. Bot je odigrao {played}. Simulator predlaze {v.get('best_label')}; "
                f"razlika do predaje reda je {_f(d.get('mean'))} +/- {_f(d.get('se'))} poena (simulirano) -- "
                f"priblizno izjednaceno.{actual_text}")
    return (f"{_round_phrase(r)}. Bot je odigrao {played}. Simulator predlaze {v.get('best_label')}. "
            f"Procenjena razlika do predaje reda je {_f(d.get('mean'))} +/- {_f(d.get('se'))} poena (simulirano). "
            f"Glavni razlog je {v.get('reason_vs_played')}. Pouzdanost je {v.get('confidence')}.{caveat_text}{actual_text}")


def _action_table(r: dict, show_all: bool) -> list[str]:
    rows = r["actions"]
    if not show_all:
        keep = rows[:3] + [a for a in rows if a["played"] and a["rank"] > 3]
        rows = keep
    lines = [
        "| # | akcija | razmatrao bot | odmah E | do predaje E | od toga buster | bez bustera E | raspon p10-p90 | +/-SE proseka | razlika vs odigrano | P(jos odluka) | P(extra) | perkova na predaji | protivnik odgovor (jed.) | napomene |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for a in rows:
        vs = a.get("vs_played") or {}
        notes = []
        if a["played"]:
            notes.append("**odigrano**")
        if a["guaranteed_extra"]:
            notes.append("garantovani extra")
        if a["share_limit"]:
            notes.append(f"prekinuto {a['share_limit']:.0%} (limit ili bez poteza)")
        elif a.get("extended_branches"):
            notes.append(f"{a['extended_branches']} grana produzeno do predaje")
        if a["share_unsupported"]:
            notes.append(f"empirijski buster {a['share_unsupported']:.0%}")
        if a["equivalent"]:
            notes.append(f"+{len(a['equivalent'])} ekvivalentnih")
        opp = a.get("opponent_reply_units") or {}
        lines.append(
            f"| {a['rank']} | {a['label']} | {a['historical']} | {_f(a['immediate']['mean'])} | "
            f"{_f(a['total']['mean'])} | {_f(a.get('booster_points_mean'))} | {_f((a.get('total_ex_booster') or {}).get('mean'))} | "
            f"{_f(a['total']['p10'])}-{_f(a['total']['p90'])} | "
            f"{_f(a['total']['se'])} (n={a['total']['n']}) | "
            f"{'-' if a['played'] else (_f(vs.get('mean')) + ' +/- ' + _f(vs.get('se')))} | "
            f"{a['p_another_decision']:.0%} | {a['p_extra_first']:.0%} | {_f(a.get('perks_left_mean'), 2)} | {_f(opp.get('mean'), 1)} | {', '.join(notes)} |"
        )
    return lines


def decision_markdown(r: dict, out_dir: Path, show_all: bool = False) -> str:
    if r.get("error"):
        return f"## {r['run']}\n\nGreska u analizi: `{r['error']}`\n"
    link = _rel(r["path"], out_dir)
    perks = "; ".join(f"slot {p['slot']}: {ta.PERK_LABELS.get(p['perk'], p['perk']) or '-'} ({p['status']})" for p in r["perks"])
    out = r.get("outcome") or {}
    lines = [
        f"## Odluka {r['run']}",
        "",
        f"[izvorni Debug folder]({link}) · {r['context_label']} ({r['context_source']}) · {r['mode']} · "
        f"{r['time']} · skor {r.get('our_score')}:{r.get('opp_score')} · sat {_f(r.get('time_left'), 1)} s · "
        f"buster {r['booster']['charge']}/{r['booster']['max']} · x{_f(r['multiplier'], 1)} ({r['multiplier_source']})",
        "",
        f"Perkovi: {perks}",
        "",
        f"**{headline(r)}**",
        "",
        f"Predlozeno: `{json.dumps(r['proposed'], ensure_ascii=False)}` · poslato: {'da' if r['sent'] else 'ne'} · "
        f"potvrdjen ishod: {out.get('status')}"
        + (f" ({out.get('note')})" if out.get("note") else "")
        + (f" · stvarno {out.get('points'):+d} poena ({out.get('source')})" if out.get("points") is not None else ""),
        "",
        f"Legalnih pocetnih akcija: {len(r['actions'])}. Poeni su u poenima igre (x mnozilac). "
        f"Kraj reda: {r['scope']}.",
        "",
        *_action_table(r, show_all),
        "",
    ]
    v = r.get("verdict") or {}
    if v.get("second_key"):
        gap = v.get("gap_to_second") or {}
        lines.append(
            f"Prva dva izbora: {v['best_label']} vs {v['second_label']}: {_f(gap.get('mean'))} +/- {_f(gap.get('se'))} "
            f"({'pouzdan pobednik' if v.get('reliable_winner') else 'nema pouzdanog pobednika'}); razlog: {v.get('reason_vs_second')}."
        )
    if v.get("opponent_reply_diff_units") is not None:
        lines.append(
            f"Versus procena predate table (odvojeno od nasih poena): predlog ostavlja protivniku "
            f"{v['opponent_reply_diff_units']:+.1f} jedinica u odnosu na odigrano (najbolji neposredni odgovor, bez njegovog bustera)."
        )
    best = r["actions"][0] if r["actions"] else None
    played = next((a for a in r["actions"] if a["played"]), None)
    for name, row in (("odigrano", played), ("predlog", best)):
        if row and row.get("first_unknown"):
            lines.append(f"Prvo mesto neizvesnosti ({name}): {row['first_unknown']}.")
    lines.append(f"Dopuna: {r['refill_source']}. Buster: {r['booster']['model_source']}.")
    if v.get("best_without_booster"):
        lines.append(f"Najbolje bez poena bustera: {v['best_without_booster']}.")
    if v.get("perk_residual_note"):
        lines.append(f"Perk sada ili kasnije: {v['perk_residual_note']}.")
    if v.get("depends_on_unverified"):
        lines.append("Rangiranje zavisi od neproverenih pravila: " + "; ".join(v["depends_on_unverified"]) + ".")
    for item in r.get("unsupported") or []:
        lines.append(f"Nepodrzano (legalno, nije rangirano): {item['label']} -- {item['reason']}.")
    for item in r.get("limitations") or []:
        lines.append(f"Ogranicenje: {item}.")
    lines.append("")
    for trace in r.get("traces") or []:
        lines += trace_markdown(trace)
    return "\n".join(lines)


def _cells(cells):
    return " ".join(f"({c[0]},{c[1]})" for c in cells[:12]) + (" ..." if len(cells) > 12 else "")


def trace_markdown(trace: dict) -> list[str]:
    lines = [f"### Dnevnik dogadjaja: {trace.get('label')} (grana {trace.get('branch')}, seed {trace.get('seed')})", ""]
    if trace.get("error"):
        return lines + [trace["error"], ""]
    for step in trace.get("steps") or []:
        if step.get("wave") == "protivnik":
            lines.append(f"- protivnik: najbolji neposredan odgovor {step['best_reply_units']:g} jedinica ({step['note']})")
            continue
        lines.append(f"- korak {step['step']}: +{_f(step['points'])} poena; prva neizvesnost: {step.get('first_unknown')}")
        for event in step["events"]:
            wave = event.get("wave")
            if wave in ("swipe", "perk") and "events" in event:
                lines.append(f"  - {event.get('label') or event.get('perk')}: {_f(event['units'], 1)} jed. x {_f(event['multiplier'], 1)} = {_f(event['points'])}"
                             + (" (garantovani extra)" if event.get("guaranteed_extra") else ""))
                for inner in event["events"]:
                    kind = inner.get("type")
                    if kind == "match":
                        lines.append(f"    - kaskada {inner.get('cascade')}: spoj {inner.get('kind')} boje {inner.get('color')} {_cells(inner.get('cells') or [])}")
                    elif kind in ("special_activation", "special_effect"):
                        extra = f", ocisceno {inner.get('cleared_cells')}" if inner.get("cleared_cells") is not None else ""
                        lines.append(f"    - kaskada {inner.get('cascade')}: {kind} {inner.get('special')} @ {inner.get('cell')}{extra}")
                    elif kind == "uncertain_refill_boundary":
                        lines.append(f"    - GRANICA: dalje zavisi od nepoznate dopune ({inner.get('reason')})")
                    else:
                        lines.append(f"    - {kind}: { {k: v for k, v in inner.items() if k != 'type'} }")
            elif wave == "dopuna":
                lines.append(f"  - dopuna: {event['n']} plocica uzorkovano ({event['drawn']})")
            elif wave == "kaskada posle dopune":
                lines.append(f"  - kaskada posle dopune: {_f(event['units'], 1)} jed. x {_f(event['multiplier'], 1)} = {_f(event['points'])}"
                             + (" (+extra, nesiguran)" if event.get("extra") else ""))
            elif wave == "buster":
                if event.get("action"):
                    if event.get("ability") == 27:
                        lines.append(f"  - Doctor Color aktiviran: putanja {event.get('path')} (boje simulatora); poeni iz kaskada ispod ({event['note']})")
                    else:
                        lines.append(f"  - buster aktiviran: {_f(event['points'])} poena ({event['note']})")
                else:
                    lines.append(f"  - buster {event['from']:g} -> {event['to']:g} (korisno {event['useful']:g}, propalo {event['wasted']:g})")
            elif wave == "mnozilac":
                lines.append(f"  - mnozilac {event.get('from')} -> {event.get('to')}" if "to" in event else f"  - mnozilac: {event.get('note')}")
            elif wave == "red":
                if "turn_over" in event:
                    lines.append(f"  - kraj reda: {event['turn_over']}")
                else:
                    lines.append(f"  - potezi {event['moves_left'][0]} -> {event['moves_left'][1]}: {event['why']}")
            else:
                lines.append(f"  - {wave}: { {k: v for k, v in event.items() if k != 'wave'} }")
    lines.append(f"- ukupno do kraja reda: {_f(trace.get('total'))} poena; kraj: {trace.get('ended_by')}")
    lines.append("")
    return lines


def _reliable_gap(r: dict) -> float:
    v = r.get("verdict") or {}
    d = v.get("diff_vs_played") or {}
    if not d.get("n") or v.get("tie_with_played") or v.get("booster_dependent") or v.get("limit_cut_after_extension"):
        return 0.0
    return d["mean"] - ta.TIE_SIGMAS * (d.get("se") or 0.0)


def match_markdown(results: list, skipped: list, out_dir: Path, title: str, total_seconds: float) -> str:
    ok = [r for r in results if not r.get("error")]
    lines = [f"# {title}", "",
             f"Odluka pronadjeno: {len(results) + len(skipped)} · analizirano: {len(ok)} · "
             f"greska: {len(results) - len(ok)} · preskoceno: {len(skipped)} · vreme: {total_seconds:.0f} s", "",
             "Razlike su simulirane do predaje reda (uparene grane, isti seed-ovi); stvarni poeni stoje samo uz odigranu akciju.", "",
             "| # | vreme | kontekst | runda | potezi | x | odigrano | stvarno | predlog | razlika (sim) | pouzdanost | Debug |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for index, r in enumerate(sorted(results, key=lambda x: x["run"]), start=1):
        link = _rel(r["path"], out_dir)
        if r.get("error"):
            lines.append(f"| {index} | {r['run'][11:19]} | | | | | greska: {r['error']} | | | | | [run]({link}) |")
            continue
        v = r.get("verdict") or {}
        d = v.get("diff_vs_played") or {}
        out = r.get("outcome") or {}
        diff = "-" if not v.get("played_key") else (
            "isto" if v.get("best_key") == v.get("played_key") else
            f"{_f(d.get('mean'))} +/- {_f(d.get('se'))}" + (" (~izjednaceno)" if v.get("tie_with_played") else ""))
        lines.append(
            f"| {index} | {r['time']} | {r['context_label']} | {r.get('round')}/{r.get('total_rounds')} | {r.get('remaining_moves')} | "
            f"{_f(r.get('multiplier'), 0)} | {v.get('played_label') or (r.get('proposed') or {}).get('type')} | "
            f"{out.get('points') if out.get('points') is not None else out.get('status')} | {v.get('best_label')} | {diff} | "
            f"{v.get('confidence') or '-'} | [run]({link}) |")
    top = sorted(ok, key=_reliable_gap, reverse=True)[:5]
    top = [r for r in top if _reliable_gap(r) > 0]
    lines += ["", "## Pet odluka sa najvecom pouzdano procenjenom razlikom", ""]
    if not top:
        lines.append("Nijedna odluka nema razliku koja je pouzdano veca od nule.")
    for r in top:
        lines.append(f"- [{r['run']}]({_rel(r['path'], out_dir)}): {headline(r)}")
    if skipped:
        lines += ["", "## Preskocene odluke", ""]
        for s in skipped:
            lines.append(f"- [{s['run']}]({_rel(s['path'], out_dir)}): {s['reason']}")
    return "\n".join(lines) + "\n"


def _write(out_dir: Path, name: str, markdown: str, payload: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / f"{name}.md"
    js = out_dir / f"{name}.json"
    md.write_text(markdown, encoding="utf-8")
    js.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return md, js


# ---------------------------------------------------------------------------
# Komande


def cmd_decision(args):
    members = _match_of(args.run)
    decision = next(d for d in members if d.run == args.run)
    reason = ta.skip_reason(decision)
    if reason:
        raise SystemExit(f"odluka se preskace: {reason}")
    started = time.perf_counter()
    result = _analyze_one((decision, _config(args), args.trace))
    seconds = time.perf_counter() - started
    out_dir = Path(args.out)
    md = f"# Analiza odluke\n\n" + decision_markdown(result, out_dir, show_all=args.all) + f"\nVreme: {seconds:.1f} s\n"
    payload = {"provenance": ta.provenance(_config(args)), "decisions": [result]}
    paths = _write(out_dir, f"decision_{args.run}", md, payload)
    print(md)
    print("\n".join(str(p) for p in paths))


def _run_group(decisions, args, name, title):
    started = time.perf_counter()
    results, skipped = analyze_many(decisions, _config(args), args.workers, traces=False)
    seconds = time.perf_counter() - started
    out_dir = Path(args.out)
    md = match_markdown(results, skipped, out_dir, title, seconds)
    md += "\n" + "\n".join(decision_markdown(r, out_dir) for r in sorted(results, key=lambda x: x["run"]))
    payload = {"provenance": ta.provenance(_config(args)), "decisions": results, "skipped": skipped,
               "seconds": seconds}
    paths = _write(out_dir, name, md, payload)
    print(md.split("\n## Odluka")[0])
    print("\n".join(str(p) for p in paths))


def cmd_match(args):
    members = _match_of(args.run)
    first = members[0]
    title = (f"Partija {first.run[:10]} {first.time_label}-{members[-1].time_label}: "
             f"{ta.PROFILES[first.context].label if first.context else '?'} · {first.mode}")
    _run_group(members, args, f"match_{first.run}", title)


def cmd_day(args):
    decisions = _decisions_for_day(args.day, args.context)
    _run_group(decisions, args, f"day_{args.day}_{args.context}", f"Sve odluke {args.day} ({args.context})")


def cmd_validate(args):
    days = args.day or []
    decisions = []
    for day in days:
        decisions += _decisions_for_day(day, args.context)
    if args.mode:
        decisions = [d for d in decisions if d.mode == args.mode]
    started = time.perf_counter()
    report = _validate_parallel(decisions, args.samples or 16, args.seed, args.workers)
    report["seconds"] = time.perf_counter() - started
    out_dir = Path(args.out)
    name = f"validation_{'_'.join(days)}_{args.context}" + (f"_{args.mode.replace(' ', '-')}" if args.mode else "")
    md = validation_markdown(report)
    _write(out_dir, name, md, {"provenance": ta.provenance(_config(args)), **report})
    print(md)


def _validate_match(payload):
    members, samples, seed = payload
    return tv.validate(members, samples=samples, seed=seed)


def _validate_parallel(decisions, samples, seed, workers) -> dict:
    """tv.validate po partijama u paraleli, pa spajanje (grupe se racunaju iz slucajeva)."""
    groups = {}
    for decision in decisions:
        groups.setdefault(decision.match_id, []).append(decision)
    payloads = [(members, samples, seed) for members in groups.values()]
    if workers > 1 and len(payloads) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(_validate_match, payloads))
    else:
        parts = [_validate_match(p) for p in payloads]
    coverage, skipped, a_cases, b_cases = {}, {}, [], []
    for part in parts:
        for key, value in part["coverage"].items():
            coverage[key] = coverage.get(key, 0) + value
        for key, value in part["skipped"].items():
            skipped[key] = skipped.get(key, 0) + value
        a_cases += part["phase_a"]["cases"]
        b_cases += part["phase_b"]["cases"]
    rc = [c for c in a_cases if "observed_refill_cascade" in c]
    return {
        "refill_cascade": ({"n": len(rc), "observed_rate": sum(c["observed_refill_cascade"] for c in rc) / len(rc),
                            "model_rate": sum(c["model_refill_cascade_rate"] for c in rc) / len(rc)} if rc else None),
        "coverage": coverage, "skipped": skipped,
        "phase_a": {"by_group": tv.aggregate_a(a_cases), "cases": a_cases},
        "phase_b": {"by_group": tv.aggregate_b(b_cases), "cases": b_cases},
        "refill": tv.build_refill_stats(a_cases),
    }


def validation_markdown(report: dict) -> str:
    lines = ["# Validacija simulatora", "",
             f"Pokrivenost: {report['coverage']} · preskoceno: {report['skipped']} · vreme {report['seconds']:.0f} s", "",
             "## Faza A: tacnost pravila (pre prve nepoznate dopune)", "",
             "| mod / tip akcije | slucajeva | provere (ok / greska / nepotvrdivo) |", "|---|---|---|"]
    for key, group in report["phase_a"]["by_group"].items():
        checks = {}
        for name, value in group.items():
            if ":" in name:
                check, verdict = name.split(":")
                checks.setdefault(check, {})[verdict] = value
        text = "; ".join(f"{c} {v.get('ok', 0)}/{v.get('greska', 0)}/{v.get('nepotvrdivo', 0)}" for c, v in checks.items())
        lines.append(f"| {key} | {group.get('slucajeva', 0)} | {text} |")
    errors = [c for c in report["phase_a"]["cases"] if any(str(v).startswith("GRESKA") for v in c["checks"].values())]
    if errors:
        lines += ["", "Greske pravila (prvih 15):", ""]
        for c in errors[:15]:
            bad = {k: v for k, v in c["checks"].items() if str(v).startswith("GRESKA")}
            lines.append(f"- {c['run']} ({c['mode']}, {c['action_type']}): {bad}")
    rc = report.get("refill_cascade")
    if rc:
        lines += ["", f"Kaskade posle dopune: stvarno {rc['observed_rate']:.0%}, model {rc['model_rate']:.0%} (n={rc['n']})."]
    lines += ["", "## Faza B: tacnost prognoze (raspodela vs stvarni ishod)", "",
              "| mod / tip / nasumicnost | n | MAE | pristrasnost (stvarno - sim) | rel. | pokrivenost p10-p90 | sr. percentil | extra: sim / stvarno (Brier) | jos nasa odluka: sim / stvarno (Brier) | obecani extra dobijen | red: n / pristrasnost | red bez odstupanja politike: n / pristrasnost |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, g in report["phase_b"]["by_group"].items():
        lines.append(
            f"| {key} | {g['n']} | {_f(g['mean_abs_err'])} | {_f(g['mean_bias'])} | {g['mean_rel_bias']:+.0%} | "
            f"{g['coverage_p10_p90']:.0%} | {g['mean_percentile']:.2f} | {g['extra_rate_pred_vs_obs'] or '-'} ({_f(g['brier_extra'], 3)}) | "
            f"{g['another_rate_pred_vs_obs'] or '-'} ({_f(g['brier_another'], 3)}) | {g['promised_extra_kept'] or '-'} | "
            f"{g['turn_cases']} / {_f(g['turn_mean_bias'])} | {g['turn_cases_policy_match']} / {_f(g['turn_mean_bias_policy_match'])} |")
    lines += ["", "Pokrivenost p10-p90 bi trebalo da bude oko 80%, srednji percentil oko 0.50. "
              "Red: kad je bot kasnije u redu birao drugacije od politike nastavka, razlika ukupnih poena "
              "moze poticati od kasnijeg izbora; zato je izdvojen red bez odstupanja.", ""]
    rs = report.get("refill") or {}
    for mode, stats in (rs.get("modes") or {}).items():
        lines.append(f"Dopuna {mode}: {stats['tiles']} plocica, udeo boja {json.dumps({k: round(v, 3) for k, v in stats['color_share'].items()})}, "
                     f"chi2 vs ravnomerno {stats['chi2_vs_uniform']:.1f} (dof {stats['dof']}), specijali {json.dumps({k: round(v, 3) for k, v in stats['special_share'].items()})}")
    return "\n".join(lines) + "\n"


def _refill_day(payload):
    day, names = payload
    decisions = ta.load_decisions(names)
    ta.segment_matches(decisions)
    report = tv.validate(decisions, phase="a")
    keep = ("run", "mode", "context", "refill_tiles", "observed_refill_cascade", "model_refill_cascade_rate")
    return day, [{k: c[k] for k in keep if k in c} for c in report["phase_a"]["cases"]]


def cmd_refill_stats(args):
    names = [n for n in ta.list_runs() if not args.since or n >= args.since]
    days = sorted({n[:10] for n in names})
    payloads = [(day, [n for n in names if n.startswith(day)]) for day in days]
    cases = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for day, day_cases in pool.map(_refill_day, payloads):
            cases += day_cases
            print(f"  {day}: {len(day_cases)} slucajeva faze A", flush=True)
    stats = tv.build_refill_stats(cases)
    stats["since"] = args.since
    ta.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    ta.REFILL_STATS_PATH.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    for mode, s in stats["modes"].items():
        print(f"{mode}: {s['tiles']} plocica iz {s['runs']} poteza, chi2={s['chi2_vs_uniform']:.1f} (dof {s['dof']})")
    print(ta.REFILL_STATS_PATH)


def cmd_compare(args):
    a = json.loads(Path(args.old).read_text(encoding="utf-8"))
    b = json.loads(Path(args.new).read_text(encoding="utf-8"))
    pa, pb = a.get("provenance", {}), b.get("provenance", {})
    print(f"stari: {pa.get('analyzer_version')} {pa.get('git_commit')} seed={pa.get('config', {}).get('seed')}")
    print(f"novi:  {pb.get('analyzer_version')} {pb.get('git_commit')} seed={pb.get('config', {}).get('seed')}")
    for name in sorted(set(pa.get("code_sha256", {})) | set(pb.get("code_sha256", {}))):
        if pa.get("code_sha256", {}).get(name) != pb.get("code_sha256", {}).get(name):
            print(f"  promenjen kod: {name}")
    old = {r["run"]: r for r in a.get("decisions", []) if not r.get("error")}
    new = {r["run"]: r for r in b.get("decisions", []) if not r.get("error")}
    changed = 0
    print("\n| run | stari predlog | novi predlog | stara razlika | nova razlika |\n|---|---|---|---|---|")
    for run in sorted(set(old) & set(new)):
        vo, vn = old[run].get("verdict") or {}, new[run].get("verdict") or {}
        if vo.get("best_key") != vn.get("best_key"):
            changed += 1
            do, dn = vo.get("diff_vs_played") or {}, vn.get("diff_vs_played") or {}
            print(f"| {run} | {vo.get('best_label')} | {vn.get('best_label')} | {_f(do.get('mean'))} | {_f(dn.get('mean'))} |")
    print(f"\nzajednickih odluka: {len(set(old) & set(new))}, promenjen predlog: {changed}, "
          f"samo u starom: {len(set(old) - set(new))}, samo u novom: {len(set(new) - set(old))}")


def cmd_index(args):
    added = ta.build_snapshot_index(force=args.force, verbose=True)
    print(f"dodato {added} redova -> {ta.SNAPSHOT_INDEX_PATH}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", type=int, default=0)
    common.add_argument("--samples", type=int, default=None, help="najvise grana po akciji")
    common.add_argument("--detailed", action="store_true", help="detaljan rezim (vise grana za bliske kandidate)")
    common.add_argument("--max-steps", type=int, default=ta.DEFAULT_MAX_STEPS, help="eksplicitni limit simulacije")
    common.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    common.add_argument("--out", default=str(ta.ANALYSIS_DIR))
    common.add_argument("--no-index", action="store_true", help="ne osvezavaj indeks memorijskih snimaka")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("decision", parents=[common])
    p.add_argument("run")
    p.add_argument("--all", action="store_true", help="prikazi sve akcije, ne samo odigranu i tri najbolje")
    p.add_argument("--trace", action="store_true", help="dnevnik dogadjaja za odigranu i najbolju akciju")
    p.set_defaults(func=cmd_decision)
    p = sub.add_parser("match", parents=[common])
    p.add_argument("run")
    p.set_defaults(func=cmd_match)
    p = sub.add_parser("day", parents=[common])
    p.add_argument("day")
    p.add_argument("--context", choices=CONTEXT_CHOICES, default=ta.CTX_VERSUS)
    p.set_defaults(func=cmd_day)
    p = sub.add_parser("validate", parents=[common])
    p.add_argument("--day", action="append", required=True)
    p.add_argument("--context", choices=CONTEXT_CHOICES, default=ta.CTX_VERSUS)
    p.add_argument("--mode", default=None)
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("refill-stats", parents=[common])
    p.add_argument("--since", default=None)
    p.set_defaults(func=cmd_refill_stats)
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_compare, no_index=True)
    p = sub.add_parser("index")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_index, no_index=True)
    args = parser.parse_args(argv)
    if not getattr(args, "no_index", False) and args.command != "index":
        ta.build_snapshot_index()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
