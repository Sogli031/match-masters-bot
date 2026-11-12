"""Da li dopuna pogadja: svaka mirna tabla se proverava prema simulatoru, uzivo.

Provera radi u posebnom procesu (`python refill_monitor.py --worker`, nizi
prioritet): move_strategy drzi pravila i dopunu u globalnim promenljivama, pa bi
simulacija u procesu GUI-ja menjala rezultat poteza koji bot bas racuna. Pad
procesa samo gasi proveru. Bez uticaja na izbor poteza; na disk ide samo promasaj
(Debug/refill_misses), i kad je prekidac "Snimaj svaki potez" iskljucen.

Provera je samo merenje, pa propusta i modove koje simulator jos nije
sertifikovao za planer; to ne ukljucuje planer u tim modovima.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import queue
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MISS_DIR = Path(os.environ.get("REFILL_MISS_DIR") or ROOT / "Debug/refill_misses")
RANDOM_TARGET_REASON = "random target outcome"
# SPECIAL_LIGHTNING, SPECIAL_CROSSHAIR and Match & Hatch's Cleo, Bandit, skull and
# Foxy: their activation picks random cells.
RANDOM_TARGET_CODES = (4, 46, 13, 18, 19, 29)
# Draws between the game and the nearest checkable swipe beyond which a random
# special fired in the same move is the likelier story (a refill is 7 per hole).
RANDOM_TARGET_DRAW_GAP = 70
UFO_BOOSTERS = (19, 49)     # UFO Beam, UFO Beam SE
UFO_EYE_COUNTS = (0, 1, 2)
PERK_TELEPORT, PERK_ENERGY_BOOST = 3, 22
PERK_LABELS = ("TELEPORT", "ENERGY BOOST")     # strategy_lab.planner.describe
REASONS = (
    ("Special tile spawning", "specijalna polja u dopuni nisu preneta"),
    ("Funky Tiles: cell types", "Funky Tiles: snimak nema funky polja (snimak od pre 2026-11-07 18:05)"),
    ("Cleo booster figure", "Cleo figura iz boostera: tacno prevlacenje nije preneto, bot igra po verovatnoci"),
    ("random or equipment special", "na tabli je specijal koji simulator ne zna"),
    (RANDOM_TARGET_REASON, "specijal sa nasumicnom metom nije prenet"),
    ("Sweep SE broom swipe", "pokretanje metle jos nije potpuno preneto"),
    ("Sweep SE paint", "metla prefarbava nasumicna polja (PvP), nije preneto"),
    ("Mixy code match", "Mixy: prvi spoj boje iz koda izvlaci novi kod, to nije preneto"),
    ("additional board layer", "dodatni sloj table nije prenet"),
    ("Dustville cascade", "Dustville: specijal ili wanted figura u kaskadi nije preneta"),
    ("Color Crush cascade special timing", "Color Crush: redosled aktivacije specijala u kaskadi nije prenet"),
    ("Candy World: candy conversion", "Candy World: nova bombona iz dopune nije preneta"),
    ("Fireworks Festival: rocket conversion", "Fireworks Festival: nova raketa iz dopune nije preneta"),
    ("Unported simulator special/color", "na tabli je komad koji dopuna ne zna, racuna se kao obican"),
    ("Adaptive thresholds", "pragovi sprecavanja meca nisu preneti, uzeti osnovni"),
    ("Live event spawning", "event komadi u dopuni nisu preneti"),
    ("Legacy createWeightsList", "stari izbor boja nije prenet"),
    ("Forced-combo", "prisilni spoj u dopuni nije prenet"),
    ("WeightsRandomizer", "tabela nasumicnih specijala nije preneta"),
    ("Random special table", "tabela nasumicnih specijala nije preneta"),
    ("raw drone colour", "Billie: boja drona nije procitana"),
)
DUSTVILLE_CASCADE_REASON = "Dustville cascade"
MIXY_CODE_REASON = "Mixy code match"
MIXY_MEOW = 59

VERDICT_LABELS = {"ok": "pogodjeno", "miss": "PROMASAJ", "unsupported": "ne moze da se proveri",
                  "booster": "booster, ne moze da se proveri", "gap": "preskocen potez, nema table pre njega",
                  "opponent": "potez protivnika, ne proverava se"}


def _translated(reason) -> str:
    text = str(reason)
    serbian = next((serbian for key, serbian in REASONS if key in text), None)
    if serbian is None:
        return text
    # "...: tile values [19, 41]" names what is missing; keep it after the translation.
    detail = text.split("tile values ", 1)[1] if "tile values " in text else ""
    return f"{serbian} (polja {detail})" if detail else serbian


# Why the exact refill was not used, by what the player can do about it.
MOVE_REASONS = ("ovaj potez", "Least Points", "igra se samo", "Froggy lotus", "Mixy kod",
                "potez je izabran", "bot nije rangirao", "bot nije stigao", "kandidati imaju")
READ_REASONS = ("tabla jos nije mirna", "igra jos razresava", "citanje memorije",
                "tabla se promenila", "potez se ne racuna iz memorije")
FAILED_PREFIX = "dopuna nije uspela: "


def usage_reason(reason) -> tuple[str, str]:
    """(kind, text): "off", "move" (this move only), "read" (memory not read in
    time) or "mode" (the mode or a piece on the board is not ported)."""
    text = str(reason or "")
    if text.startswith("iskljuceno"):
        return "off", text
    if any(text.startswith(key) for key in MOVE_REASONS):
        return "move", text
    if any(text.startswith(key) for key in READ_REASONS):
        return "read", text
    if text.startswith(FAILED_PREFIX):
        # Every candidate of this move hit a random effect the refill cannot
        # follow (Mixy re-deal, a cascade special, ...): this move, not the mode.
        return "move", "nepredvidiv efekat: " + _translated(text[len(FAILED_PREFIX):])
    return "mode", _translated(text)


def _random_targets(record) -> int:
    return sum(int(v) in RANDOM_TARGET_CODES for row in record["special_board"] for v in row)


def _booster_fired(rec_a, rec_b):
    """Any player's booster, so a versus opponent's does not read as a miss."""
    before = (rec_a.get("snapshot_state") or {}).get("players") or []
    after = {p.get("index"): p for p in (rec_b.get("snapshot_state") or {}).get("players") or []}
    for player in before:
        later = after.get(player.get("index")) or {}
        if ((player.get("energy_full") and (later.get("energy") or 0) < (player.get("energy") or 0))
                or later.get("is_ability_used_this_move")):
            return player.get("special_ability_type")
    return None


def mixy_uses_left(record):
    """``MixyMeow.UsesLeft`` of our player on this record, or None (no Mixy)."""
    players = (record.get("snapshot_state") or {}).get("players") or []
    me = next((p for p in players if p.get("player_type") == 0), None) or {}
    if me.get("special_ability_type") != MIXY_MEOW:
        return None
    engine = me.get("special_ability_engine") or {}
    if isinstance(engine.get("uses_left"), int):
        return engine["uses_left"]
    raw = (record.get("board_extra_data_view") or {}).get(f"MixyMeowUsesLeftKeyPlayer{me.get('index', 0)}")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


SWEEP_BROOM_REASON = "Sweep SE broom swipe"


def _broom_swiped(rec_a, rec_b) -> bool:
    """A Sweep SE broom left the board: a broom swipe, not ported exactly yet."""
    import move_strategy as ms
    if ms.SWEEP_EXACT_PORTED:
        return False
    count = lambda rec: sum(row.count(ms.SPECIAL_SWEEP_SE_BROOM) for row in rec.get("special_board") or [])
    return count(rec_b) < count(rec_a)


def _mixy_code_spent(rec_a, rec_b) -> bool:
    """A swap took Mixy code use #1, after which the code is re-dealt
    (RandomizeActiveColors), which is not ported. Use #2 replays (engine_mixy)."""
    before, after = mixy_uses_left(rec_a), mixy_uses_left(rec_b)
    return before is not None and after is not None and after < before and after >= 1


def _opponent_to_move(record) -> bool:
    """Whether the board waits for another player's move, not ours."""
    players = (record.get("snapshot_state") or {}).get("players") or []
    me = next((p for p in players if p.get("player_type") == 0), None)
    return (me is not None and me.get("is_my_turn") is False
            and any(p.get("is_my_turn") for p in players if p is not me))


def _try_with_ufo_eyes(rec_a, want, try_transition, capture_from):
    """(matches, closest, reasons, eyes). The record does not say how many eyes
    were armed, so a UFO player's move is tried with each count."""
    import move_strategy as ms

    me = next((p for p in (rec_a.get("snapshot_state") or {}).get("players") or []
               if p.get("player_type") == 0), {})
    counts = UFO_EYE_COUNTS if me.get("special_ability_type") in UFO_BOOSTERS else (0,)
    capture = capture_from(rec_a)
    best = None
    for eyes in counts:
        with ms.ufo_abduction_active(eyes):
            matches, closest, reasons = try_transition(capture, want)
            if (not matches and capture.get("simulator_input", {}).get("billie") is not None
                    and any(p.get("type") == 22 for p in me.get("board_abilities") or [])):
                perk_matches, perk_closest, perk_reasons = try_transition(capture, want, perks={22: 1})
                if perk_matches:
                    matches, closest, reasons = perk_matches, perk_closest, perk_reasons
        if matches:
            return matches, closest, reasons, eyes
        if eyes:
            played = _swap_reproducing_board(rec_a, want, eyes)
            if played is not None:
                return [(played, None)], None, reasons, eyes
        if best is None or (closest is not None and (best[0] is None or closest["distance"] < best[0]["distance"])):
            best = (closest, reasons)
    return [], best[0], best[1], 0


def _perk_reproducing_board(rec_a, want, try_transition, capture_from) -> str | None:
    """The move behind a perk: Teleport (every pair) or Energy Boost. The record
    does not list the perks left, so both are tried; only a board matching to
    the last cell counts."""
    import move_strategy as ms

    me = next((p for p in (rec_a.get("snapshot_state") or {}).get("players") or []
               if p.get("player_type") == 0), {})
    counts = UFO_EYE_COUNTS if me.get("special_ability_type") in UFO_BOOSTERS else (0,)
    capture = capture_from(rec_a)
    for eyes in counts:
        with ms.ufo_abduction_active(eyes):
            matches, closest, _ = try_transition(capture, want, {PERK_TELEPORT: 1, PERK_ENERGY_BOOST: 1})
        armed = f", {eyes} oka" if eyes else ""
        played = sorted({m for m, _ in matches if m.startswith(PERK_LABELS)})
        if played:
            return played[0] + armed
        if (closest is not None and closest["action"].startswith(PERK_LABELS)
                and not closest["cells"] and not closest["specials"]):
            extra = closest["rng"][0] - closest["rng"][1]
            return f"{closest['action']}{armed}, tabla tacna, RNG {extra:+d} posle dopune"
    return None


def _swap_reproducing_board(rec_a, want, eyes) -> str | None:
    """The bot's own simulation under armed eyes.

    simulation.step refuses these moves as an uncertain boundary, because the
    eye's colour is a prediction; a board matching to the last cell settles it.
    """
    import move_strategy as ms
    from engine_refill import EngineRefill, ExactRefillSession
    from simulator_capture import capture_mode

    profile = rec_a["profile"]
    mode = capture_mode(profile).value
    square = bool(profile["spawning"].get("<SquareMatchesAvailable>k__BackingField"))
    grid = lambda board: [[int(v) for v in row] for row in board]
    with ms.ufo_abduction_active(eyes):
        for candidate in ms.generate_candidates(rec_a["board"], rec_a["special_board"]):
            for oriented in (candidate, ms.flip_swap_candidate(candidate)):
                session = ExactRefillSession(EngineRefill.from_profile(profile), rec_a["board"])
                session.approximate_fallback = False    # a check, not a guess
                with ms.exact_refill_active(session):
                    result = ms._simulate_created_candidate_cached(
                        rec_a["board"], oriented, square, mode, False, False, {}, {})
                if (result is not None and grid(result.board) == want["board"]
                        and grid(result.special_board) == want["special_board"]):
                    return f"{tuple(oriented.start)} -> {tuple(oriented.target)}"
    return None


def data_state(record) -> dict:
    """Does the ported refill cover this match? {"level": ima|delimicno|nema, "text"}."""
    from engine_refill import UnsupportedRefill
    from simulator_capture import lab_move, resolve_refill_overrides
    from tools.analyze_research import capture_from

    capture = capture_from(record)
    if any(int(v) == 14 for row in record.get("special_board") or [] for v in row):
        if capture["simulator_input"].get("billie") is not None:
            return {"level": "delimicno", "text": "Billie dopuna ukljucena za predvidive poteze; deo kaskada jos promasuje"}
        return {"level": "nema", "text": "Billie: nedostaju sirovi podaci drona ili varijanta nije preneta"}
    resolved = resolve_refill_overrides(capture["profile"])
    hypotheses = resolved.get("threshold_hypotheses") or {}
    try:
        lab_move(capture, thresholds=None if resolved.get("resolved") else next(iter(hypotheses.values()), None))
    except UnsupportedRefill as exc:
        return {"level": "nema", "text": _translated(exc)}
    if resolved.get("resolved"):
        return {"level": "ima", "text": "tacna formula"}
    if hypotheses:
        return {"level": "delimicno", "text": f"formula nije preneta, proba se {len(hypotheses)} pretpostavki"}
    return {"level": "nema", "text": _translated(resolved.get("reason") or "grana dopune nije razresena")}


def _free_swap_between(rec_a, rec_b) -> bool:
    """Two resting boards one plain swap apart, specials and RNG untouched."""
    board_a, board_b = rec_a.get("board") or [], rec_b.get("board") or []
    if (rec_a.get("special_board") != rec_b.get("special_board")
            or len(board_a) != len(board_b) or not board_a):
        return False
    rng = lambda rec: ((rec.get("profile") or {}).get("rng") or {}).get("<counter>k__BackingField")
    if rng(rec_a) != rng(rec_b):
        return False
    changed = [(r, c) for r in range(len(board_a)) for c in range(len(board_a[r]))
               if board_a[r][c] != board_b[r][c]]
    if len(changed) != 2:
        return False
    (r1, c1), (r2, c2) = changed
    return (abs(r1 - r2) + abs(c1 - c2) == 1
            and board_a[r1][c1] == board_b[r2][c2] and board_a[r2][c2] == board_b[r1][c1])


def _mutation_added(rec_a, rec_b) -> bool:
    """Mutation Lab: the after board carries more active mutations than the before board."""
    return len(rec_b.get("active_mutations") or ()) > len(rec_a.get("active_mutations") or ())


SPECIAL_JOOJOO_SKULL = 19  # move_strategy.SPECIAL_JOOJOO_SKULL


def _joojoo_new_skulls(rec_a, want, closest) -> str | None:
    """Monkey JooJoo outside Solo: board exact, only the returned skulls and their draws differ.

    In Solo the skulls are simulated (EngineRefill.joojoo_end_move). Elsewhere
    the matchable chance is not recorded; every refilled piece is still right,
    so this checks the refill, not where the skulls went.
    """
    from engine_refill import joojoo_passive, joojoo_refill_ported

    if (closest is None or closest["cells"] or not closest["specials"]
            or closest["rng"][0] <= closest["rng"][1] or not joojoo_passive(rec_a["profile"])
            or joojoo_refill_ported(rec_a["profile"])):
        return None
    got = closest["special_board"]
    if any(
            want["special_board"][r][c] != got[r][c]
            and not (want["special_board"][r][c] == SPECIAL_JOOJOO_SKULL and got[r][c] == 0)
            for r in range(len(got)) for c in range(len(got[r]))):
        return None
    extra = closest["rng"][0] - closest["rng"][1]
    return (f"tabla tacna, JooJoo: {closest['specials']} novih lobanja i RNG +{extra} "
            "posle poteza (pasiva, nije proverena)")


def check_transition(rec_a, rec_b) -> dict | None:
    """One move between two resting boards. None when nothing happened."""
    import move_strategy as ms
    from tools.analyze_research import (
        capture_from, observed, recorded_jelly_active, recorded_jelly_state, try_transition,
    )

    before, want = observed(rec_a), observed(rec_b)
    if before["rng"] == want["rng"] and before["board"] == want["board"]:
        return None
    moves = f"potezi {before['moves']}->{want['moves']}"
    input_before, input_after = rec_a.get("refill_input"), rec_b.get("refill_input")
    if input_before is not None and input_after is not None:
        count = input_after[0] - input_before[0]
        if count > 1:
            return {"verdict": "gap", "detail": moves}
        if count == 1 and input_after[1] == "activate_perk":
            return {"verdict": "unsupported", "detail": f"{moves}, odigran perk"}
        if count == 1 and input_after[1] == "activate_booster":
            return {"verdict": "booster", "detail": moves}
        if count == 0 and input_after[1] == "activate_booster":
            # The board went on changing after the booster with no new input
            # (Monkey JooJoo, Hot Color research 20261112_001019 010->011:
            # same move counters, +118 draws): still the booster's work.
            return {"verdict": "booster", "detail": f"{moves}, nastavak boostera bez novog poteza"}
        if count == 0 and input_after[1] == "move":
            state_before = rec_a["profile"]["state"]
            state_after = rec_b["profile"]["state"]
            move_counter = "<MovesMadeThisTurn>k__BackingField"
            turn_counter = "<Turns>k__BackingField"
            if all(state_before.get(key) is not None and state_before[key] == state_after.get(key)
                   for key in (move_counter, turn_counter)):
                return {"verdict": "gap", "detail": f"{moves}, promena table bez novog poteza"}
    if _free_swap_between(rec_a, rec_b):
        # Swap Freely (anySwapValid): two tiles changed places, nothing matched,
        # nothing fell. Exactly what the engine does; not a refill to check.
        return {"verdict": "ok", "detail": f"{moves}, slobodna zamena (bez meca i dopune)"}
    if _booster_fired(rec_a, rec_b) is not None:
        return {"verdict": "booster", "detail": moves}
    if _opponent_to_move(rec_a):
        # Versus: the bot only plans its own moves. The opponent's refill runs
        # from the other player's side of the colour table, so a "miss" there
        # said nothing about the bot (Moves Multiplier 2026-11-07 18:53-18:55:
        # 6 of 7 misses were the opponent's moves).
        return {"verdict": "opponent", "detail": moves}
    jelly = recorded_jelly_state(rec_a) or {}
    if recorded_jelly_active(jelly) and (
        not ms.JELLY_EXACT_PORTED or not jelly.get("cells")
    ):
        return {"verdict": "unsupported", "detail": f"{moves}, Jelly SE: aktivna zona, dopuna ne moze da se proveri"}
    if _broom_swiped(rec_a, rec_b):
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(SWEEP_BROOM_REASON)}"}
    if _mixy_code_spent(rec_a, rec_b):
        detail = f"{moves}, {_translated(MIXY_CODE_REASON)}"
        # A trace ending at the settled RNG counter isolates a terminal
        # re-deal from the draws that actually refill the board.
        terminal_redeal = next((
            trace["before_redeal"]["rng_counter"]
            for trace in rec_b["profile"].get("mixy_redeal_trace") or ()
            if trace.get("logic_key") == rec_a["profile"].get("logic_key")
            and trace["before_redeal"]["target_color"] != 1
            and before["rng"] <= trace["before_redeal"]["rng_counter"] < want["rng"]
            and trace["after_redeal"]["rng_counter"] == want["rng"]
        ), None)
        capture = capture_from(rec_a)
        expected = want
        if terminal_redeal is not None:
            expected = dict(want, rng=terminal_redeal, trailing_rng_draws=want["rng"] - terminal_redeal)
        board_matches = False
        for origin in ("swap_origin", "conversion_origin"):
            capture["verify_mixy_redeal_board"] = origin
            matches, closest, _ = try_transition(capture, expected)
            if matches and terminal_redeal is not None:
                return {"verdict": "ok", "detail":
                        f"{moves}, Mixy: dopuna tacna; {expected['trailing_rng_draws']} RNG za novi kod iz traga"}
            board_matches |= bool(closest is not None and not closest["cells"] and not closest["specials"])
            if matches or (board_matches and terminal_redeal is None):
                break
        if matches or board_matches:
            return {"verdict": "unsupported", "detail":
                    f"{moves}, Mixy: tabla i specijali tacni, RNG novog koda nije proveren"}
        return {"verdict": "unsupported", "detail": detail}
    cleos = lambda rec: sum(row.count(13) for row in rec.get("special_board") or [])
    if cleos(rec_b) < cleos(rec_a):
        # Cleo never qualifies through the legacy board-only/UFO/perk fallback.
        # A lower figure count suggests a swipe; without a recorded input event
        # the strict replay searches both orientations and says so explicitly.
        from tools.verify_cleo import measure
        report = measure(rec_a, rec_b)
        if report["matches"]:
            action = report["matches"][0]
            return {"verdict": "ok", "detail":
                    f"{moves}, Cleo {action['start']}->{action['target']}, tabla/specijali/ceo RNG/potezi tacni"}
        reasons = report.get("reasons") or {}
        unported_partner = next((reason for reason in reasons
                                 if "Cleo: special partner not ported" in reason), None)
        if report["verdict"] == "unsupported" or unported_partner:
            # A swipe that makes no match is "no longer legal" for every Cleo
            # board; it said nothing while the real boundary hid behind it
            # (2026-11-07 17:28). Name the most frequent other reason.
            informative = {k: v for k, v in reasons.items() if "no longer legal" not in str(k)} or reasons
            reason = unported_partner or max(informative, key=informative.get, default="Cleo: nepreneta grana")
            return {"verdict": "unsupported", "detail": f"{moves}, Cleo: {_translated(reason)}"}
        return {"verdict": "miss", "detail": f"{moves}, Cleo: nema potpuno tacnog ishoda"}
    matches, closest, reasons, eyes = _try_with_ufo_eyes(rec_a, want, try_transition, capture_from)
    if matches:
        armed = f", {eyes} oka" if eyes else ""
        return {"verdict": "ok", "detail": f"{moves}, {sorted({m for m, _ in matches})[0]}{armed}"}
    if recorded_jelly_active(jelly):
        renewed = recorded_jelly_state(rec_b) or {}
        uses = jelly.get("uses_left")
        if (isinstance(uses, int) and uses > 1 and renewed.get("uses_left") == uses - 1
                and renewed.get("cells") and renewed["cells"] != jelly.get("cells")):
            # Replay the consumed zone using the final-use path to check the
            # board independently of the new zone and its RNG draws.
            capture = capture_from(rec_a)
            capture["simulator_input"]["jelly_uses_left"] = 1
            for trace in rec_b["profile"].get("jelly_renewal_trace") or ():
                start = trace.get("before_rng_counter")
                points = trace.get("selected_points") or ()
                if (trace.get("logic_key") != rec_a["profile"].get("logic_key")
                        or not isinstance(start, int) or not before["rng"] <= start < want["rng"]
                        or trace.get("after_rng_counter") != want["rng"]
                        or {(y, x) for x, y in points} != set(renewed["cells"])):
                    continue
                draws = want["rng"] - start
                expected = dict(want, rng=start, trailing_rng_draws=draws)
                matches, _, _ = try_transition(capture, expected)
                if matches:
                    return {"verdict": "ok", "detail":
                            f"{moves}, Jelly SE: dopuna tacna; nova zona i {draws} RNG iz traga"}
            matches, closest, _ = try_transition(capture, want)
            if matches or (closest is not None and not closest["cells"] and not closest["specials"]):
                return {"verdict": "unsupported", "detail":
                        f"{moves}, Jelly SE: tabla i specijali tacni, nova zona i RNG nisu provereni"}
        return {"verdict": "unsupported", "detail": f"{moves}, Jelly SE: potez nije pokriven tacnim portom"}
    fired = (any(RANDOM_TARGET_REASON in str(r) for r in reasons)
             and _random_targets(rec_b) < _random_targets(rec_a))
    if fired:
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(RANDOM_TARGET_REASON)}"}
    # A Lightning made and fired inside the same move (a lotus blob's five,
    # specialsAutoExplode) never stands on either board, so the count above
    # cannot see it. When such a swipe exists and no checkable one comes near
    # the game's draw count, the played move was most likely that one
    # (Blow 'em up 2026-11-06: 150-280 draws apart, 3 of 8 "misses").
    if (any(RANDOM_TARGET_REASON in str(r) for r in reasons) and closest is not None
            and abs(closest["rng"][0] - closest["rng"][1]) > RANDOM_TARGET_DRAW_GAP):
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(RANDOM_TARGET_REASON)} (u istom potezu)"}
    # Same for a Dustville swipe whose wanted volley or special lands in a
    # cascade (2026-11-07 09:08:20 / 09:08:51): uncheckable, not a miss.
    if (any(DUSTVILLE_CASCADE_REASON in str(r) for r in reasons) and closest is not None
            and abs(closest["rng"][0] - closest["rng"][1]) > RANDOM_TARGET_DRAW_GAP):
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(DUSTVILLE_CASCADE_REASON)}"}
    if closest is None:
        known = [r for r in reasons if "no longer legal" not in str(r)] or list(reasons)
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(known[0]) if known else 'nema poteza'}"}
    same_rng = closest["rng"][0] == closest["rng"][1]
    if not closest["cells"] and not closest["specials"]:
        # Every refilled piece is right, so the extra draws came after the last
        # refill (Hot Color, recorded +2). The counter is read fresh each move.
        extra = closest["rng"][0] - closest["rng"][1]
        return {"verdict": "ok", "detail": f"{moves}, {closest['action']}, tabla tacna, RNG {extra:+d} posle dopune"}
    joojoo = _joojoo_new_skulls(rec_a, want, closest)
    if joojoo is not None:
        return {"verdict": "ok", "detail": f"{moves}, {closest['action']}, {joojoo}"}
    perk = _perk_reproducing_board(rec_a, want, try_transition, capture_from)
    if perk is not None:
        return {"verdict": "ok", "detail": f"{moves}, {perk}"}
    if _mutation_added(rec_a, rec_b):
        # Mutation Lab picked a new mutation inside this move and it acted at
        # once (type 10: three random specials, 48-90 draws). The simulator
        # cannot know the pick: 29 saved "misses" through 2026-11-09 were these.
        return {"verdict": "unsupported", "detail": f"{moves}, Mutation Lab: nova mutacija u ovom potezu, nije preneta"}
    cascade_reason = next((reason for reason in reasons
                           if "Color Crush cascade special timing" in str(reason)), None)
    if cascade_reason is not None:
        # We search possible swipes without knowing which one was played.
        # An unchecked legal swipe leaves the mismatch inconclusive.
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(cascade_reason)}"}
    return {"verdict": "miss", "detail": (
        f"{moves}, najblize {closest['action']}: razlicitih polja {len(closest['cells'])}"
        + ("+" if len(closest["cells"]) == 10 else "")
        + f", specijala {closest['specials']}, RNG {'isti' if same_rng else 'razlicit'}")}


def save_miss(before, after, directory=None) -> str:
    """Keep a replay pair whatever the recording toggle says.

    Same layout as a research session: tools/analyze_research.py FOLDER reads it.
    """
    try:
        rules_id = (before["profile"].get("rules") or {}).get("id") or "unknown"
        folder = (directory if directory is not None else MISS_DIR) / f"{dt.datetime.now():%Y%m%d_%H%M%S_%f}_{rules_id}"
        folder.mkdir(parents=True, exist_ok=True)
        for name, record in (("000.json", before), ("001.json", after)):
            (folder / name).write_text(json.dumps(record, default=str), encoding="utf-8")
        return f"snimljeno {folder.name}"
    except OSError as exc:
        return f"snimak nije uspeo: {exc}"


class TransitionChecker:
    """Process side: keeps the previous board and answers one record at a time."""

    def __init__(self):
        self.previous = None

    def handle(self, record, gap=False) -> dict:
        from simulator_capture import capture_mode
        from strategy_lab import simulation

        simulation.PREFIX_MODES = set(simulation.PREFIX_MODES) | {capture_mode(record["profile"]).value}
        rules = record["profile"].get("rules") or {}
        answer = {"title": rules.get("title") or rules.get("id"), "data": data_state(record), "move": None}
        previous, self.previous = self.previous, record
        if previous is None:
            return answer
        if previous["profile"]["rng"].get("_seed") != record["profile"]["rng"].get("_seed"):
            return answer
        answer["move"] = {"verdict": "gap", "detail": ""} if gap else check_transition(previous, record)
        move = answer["move"]
        if move is not None and move["verdict"] == "miss":
            move["detail"] += f", {save_miss(previous, record)}"
        elif move is not None and move["verdict"] == "unsupported" and _mixy_code_spent(previous, record):
            directory = MISS_DIR.with_name("refill_unsupported") / "mixy_redeal"
            move["detail"] += f", {save_miss(previous, record, directory)}"
        return answer


def worker_main() -> int:
    """stdin/stdout JSON lines; every stray print of the imports goes to stderr."""
    channel, sys.stdout = sys.stdout, sys.stderr
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    checker = TransitionChecker()
    for line in sys.stdin:
        message = json.loads(line)
        if message["kind"] == "reset":
            checker = TransitionChecker()
            continue
        try:
            answer = checker.handle(message["record"], message.get("gap", False))
        except Exception as exc:
            answer = {"error": f"{type(exc).__name__}: {exc}"}
        answer["generation"] = message["generation"]
        channel.write(json.dumps(answer) + "\n")
        channel.flush()
    return 0


class RefillMonitorClient:
    """GUI side: never blocks the caller; a dead process just ends the checks."""

    def __init__(self, on_answer):
        self._on_answer = on_answer
        self._queue = queue.Queue()
        self._process = None
        self._generation = 0
        self._lock = threading.Lock()

    def _start(self):
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        self._process = subprocess.Popen(
            [sys.executable, str(ROOT / "refill_monitor.py"), "--worker"], cwd=str(ROOT), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", creationflags=flags)
        threading.Thread(target=self._write, args=(self._process,), daemon=True).start()
        threading.Thread(target=self._read, args=(self._process,), daemon=True).start()

    def send(self, record, gap=False):
        with self._lock:
            if getattr(sys, "frozen", False):
                return
            if self._process is None:
                try:
                    self._start()
                except OSError as exc:
                    self._on_answer({"error": f"provera nije pokrenuta: {exc}"})
                    return
            self._queue.put({"kind": "record", "generation": self._generation, "gap": gap, "record": record})

    def reset(self):
        with self._lock:
            self._generation += 1
            if self._process is not None:
                self._queue.put({"kind": "reset"})

    def close(self):
        with self._lock:
            process, self._process = self._process, None
        if process is not None:
            self._queue.put(None)
            process.kill()

    def _write(self, process):
        while True:
            message = self._queue.get()
            if message is None:
                return
            try:
                process.stdin.write(json.dumps(message, default=str) + "\n")
                process.stdin.flush()
            except (OSError, ValueError):
                return

    def _read(self, process):
        for line in process.stdout:
            answer = json.loads(line)
            if answer.get("generation") == self._generation:
                self._on_answer(answer)
        if self._process is process:
            self._on_answer({"error": "proces provere se ugasio"})


class RefillTally:
    """What the panel shows for the running match."""

    def __init__(self):
        self.counts = Counter()
        self.data = None
        self.title = None
        self.used = 0
        self.not_used = 0
        self.last_usage = None

    def usage_text(self) -> str:
        """Did the ordinary ranking know what falls when it picked its moves?"""
        if self.last_usage is None:
            return "Dopuna: cekam prvi izracunat potez"
        totals = f"u partiji: sa dopunom {self.used}, bez {self.not_used}"
        if self.last_usage["active"]:
            if self.last_usage.get("approximate"):
                # engine_refill.APPROXIMATE_REFILL: exact port stops here.
                text = _translated(self.last_usage["approximate"])
                return f"Dopuna: RADI PRIBLIZNO u ovom potezu - {text} ({totals})"
            return f"Dopuna: RADI u ovom potezu ({totals})"
        kind, text = usage_reason(self.last_usage["reason"])
        if kind == "off":
            return "Dopuna: ISKLJUCENA prekidacem"
        if kind == "mode":
            # Even the approximate fallback failed on this board (an error,
            # not a mode the refill refuses).
            return f"Dopuna: NE u ovom potezu - greska u dopuni: {text} ({totals})"
        if kind == "read":
            return f"Dopuna: NE u ovom potezu - memorija nije procitana: {text} ({totals})"
        return f"Dopuna: NE u ovom potezu - {text} ({totals})"

    def add(self, answer) -> str | None:
        """Take one answer; returns the log line for its move, if any."""
        if answer.get("usage"):
            self.last_usage = answer["usage"]
            if self.last_usage["active"]:
                self.used += 1
            else:
                self.not_used += 1
            return None
        if answer.get("error"):
            return f"provera: {answer['error']}"
        self.data = answer.get("data") or self.data
        self.title = answer.get("title") or self.title
        move = answer.get("move")
        if move is None:
            return None
        self.counts[move["verdict"]] += 1
        detail = f": {move['detail']}" if move.get("detail") else ""
        return f"{VERDICT_LABELS[move['verdict']]}{detail}"

    def data_text(self) -> str:
        if self.data is None:
            return "Podaci: cekam prvu mirnu tablu"
        level = {"ima": "IMA", "delimicno": "DELIMICNO", "nema": "NEMA"}[self.data["level"]]
        return f"Podaci za {self.title or 'ovaj mod'}: {level} ({self.data['text']})"

    def hit_text(self) -> str:
        hits, misses = self.counts["ok"], self.counts["miss"]
        skipped = (self.counts["unsupported"] + self.counts["booster"] + self.counts["gap"]
                   + self.counts["opponent"])
        if not hits and not misses:
            return f"Pogadja: jos nema proverljivih poteza (neproverljivih {skipped})"
        total = hits + misses
        return f"Pogadja: {hits} od {total} ({100 * hits // total}%), neproverljivih {skipped}"


if __name__ == "__main__" and "--worker" in sys.argv:
    raise SystemExit(worker_main())
