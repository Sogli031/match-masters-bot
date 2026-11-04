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
UFO_BOOSTERS = (19, 49)     # UFO Beam, UFO Beam SE
UFO_EYE_COUNTS = (0, 1, 2)
PERK_TELEPORT, PERK_ENERGY_BOOST = 3, 22
PERK_LABELS = ("TELEPORT", "ENERGY BOOST")     # strategy_lab.planner.describe
REASONS = (
    ("Special tile spawning", "specijalna polja u dopuni nisu preneta"),
    ("random or equipment special", "na tabli je specijal koji simulator ne zna"),
    (RANDOM_TARGET_REASON, "specijal sa nasumicnom metom nije prenet"),
    ("additional board layer", "dodatni sloj table nije prenet"),
)
VERDICT_LABELS = {"ok": "pogodjeno", "miss": "PROMASAJ", "unsupported": "ne moze da se proveri",
                  "booster": "booster, ne moze da se proveri", "gap": "preskocen potez, nema table pre njega"}


def _translated(reason) -> str:
    text = str(reason)
    return next((serbian for key, serbian in REASONS if key in text), text)


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


def check_transition(rec_a, rec_b) -> dict | None:
    """One move between two resting boards. None when nothing happened."""
    from tools.analyze_research import capture_from, observed, try_transition

    before, want = observed(rec_a), observed(rec_b)
    if before["rng"] == want["rng"] and before["board"] == want["board"]:
        return None
    moves = f"potezi {before['moves']}->{want['moves']}"
    if _booster_fired(rec_a, rec_b) is not None:
        return {"verdict": "booster", "detail": moves}
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
        if report["verdict"] == "unsupported":
            reason = next(iter(report.get("reasons") or {}), "Cleo: nepreneta grana")
            return {"verdict": "unsupported", "detail": f"{moves}, Cleo: {reason}"}
        return {"verdict": "miss", "detail": f"{moves}, Cleo: nema potpuno tacnog ishoda"}
    matches, closest, reasons, eyes = _try_with_ufo_eyes(rec_a, want, try_transition, capture_from)
    if matches:
        armed = f", {eyes} oka" if eyes else ""
        return {"verdict": "ok", "detail": f"{moves}, {sorted({m for m, _ in matches})[0]}{armed}"}
    fired = (any(RANDOM_TARGET_REASON in str(r) for r in reasons)
             and _random_targets(rec_b) < _random_targets(rec_a))
    if fired:
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(RANDOM_TARGET_REASON)}"}
    if closest is None:
        known = [r for r in reasons if "no longer legal" not in str(r)] or list(reasons)
        return {"verdict": "unsupported", "detail": f"{moves}, {_translated(known[0]) if known else 'nema poteza'}"}
    same_rng = closest["rng"][0] == closest["rng"][1]
    if not closest["cells"] and not closest["specials"]:
        # Every refilled piece is right, so the extra draws came after the last
        # refill (Hot Color, recorded +2). The counter is read fresh each move.
        extra = closest["rng"][0] - closest["rng"][1]
        return {"verdict": "ok", "detail": f"{moves}, {closest['action']}, tabla tacna, RNG {extra:+d} posle dopune"}
    perk = _perk_reproducing_board(rec_a, want, try_transition, capture_from)
    if perk is not None:
        return {"verdict": "ok", "detail": f"{moves}, {perk}"}
    return {"verdict": "miss", "detail": (
        f"{moves}, najblize {closest['action']}: razlicitih polja {len(closest['cells'])}"
        + ("+" if len(closest["cells"]) == 10 else "")
        + f", specijala {closest['specials']}, RNG {'isti' if same_rng else 'razlicit'}")}


def save_miss(before, after) -> str:
    """Keep a missed move whatever the toggle says; this process never holds up a move.

    Same layout as a research session: tools/analyze_research.py FOLDER reads it.
    """
    try:
        rules_id = (before["profile"].get("rules") or {}).get("id") or "unknown"
        folder = MISS_DIR / f"{dt.datetime.now():%Y%m%d_%H%M%S_%f}_{rules_id}"
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
        if answer["move"] is not None and answer["move"]["verdict"] == "miss":
            answer["move"]["detail"] += f", {save_miss(previous, record)}"
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
            return "Bot koristi dopunu: cekam prvi izracunat potez"
        totals = f"sa dopunom {self.used}, bez {self.not_used}"
        if self.last_usage["active"]:
            return f"Bot koristi dopunu: DA ({totals})"
        return f"Bot koristi dopunu: NE, {_translated(self.last_usage['reason'])} ({totals})"

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
        skipped = self.counts["unsupported"] + self.counts["booster"] + self.counts["gap"]
        if not hits and not misses:
            return f"Pogadja: jos nema proverljivih poteza (neproverljivih {skipped})"
        total = hits + misses
        return f"Pogadja: {hits} od {total} ({100 * hits // total}%), neproverljivih {skipped}"


if __name__ == "__main__" and "--worker" in sys.argv:
    raise SystemExit(worker_main())
