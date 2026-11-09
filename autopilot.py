"""Autopilot: vodi meni Match Masters-a na Pie64_2, a mec prepusta postojecem Auto botu.

Ciklus: lobi -> (izabrani mod) -> ulaz -> cekanje protivnika -> [reader
potvrdi pocetak meca -> Auto igra -> reader javi kraj] -> rezultati -> lobi.
Posle zadatog broja partija staje.

- Poznati ekrani se prepoznaju lokalno (`autopilot_screens`), bez API-ja.
- Posle svakog klika se novim screenshotom proverava da li je stigao
  ocekivani ekran; klik se ponavlja najvise `max_tap_attempts` puta.
- Claude (`autopilot_ai`) se zove samo kad ekran nije prepoznat (duze od
  `unknown_grace`) ili kad prelaz izostane posle svih pokusaja, i najvise
  `ai_calls_per_match` puta po mecu. Dok mec traje, Autopilot ne klikce;
  stanje prati reader, a Autopilot samo na par sekundi gleda ekran: ako je
  stigao ekran rezultata (ili lobi), mec je gotov i kad reader to ne javi.
- Na ekranu rezultata Autopilot pritisne PLAY AGAIN (nova partija odmah);
  kad PLAY AGAIN nema ili je limit partija dostignut, CLOSE (lobi).
- Stop (StopGate) odmah blokira svaki novi klik i budi svako cekanje.
"""
from __future__ import annotations

import io
import json
import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from autopilot_device import DeviceError, StopGate, StopRequested
from autopilot_screens import Classification, ScreenClassifier

PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "Debug" / "autopilot"

DEFAULT_FLOW: dict[str, dict] = {
    "lobby": {"tap": "open_modes", "expect": ["mode_select", "searching"]},
    "mode_select": {"tap": "play", "expect": ["searching"]},
    "searching": {"wait": True},
    "results": {"tap": "play_again", "fallback": "continue",
                "expect": ["searching", "mode_select", "lobby"], "fallback_expect": ["lobby"]},
}
LOBBY = "lobby"
SEARCHING = "searching"
RESULTS = "results"
# Ekrani koji znace da je mec sigurno gotov, sta god reader mislio.
MATCH_OVER_SCREENS = (RESULTS, LOBBY)


class Paused(RuntimeError):
    """Autopilot staje i prikazuje razlog; Start nastavlja."""


@dataclass
class AutopilotConfig:
    games_limit: int = 1  # 0 = bez limita (igra dok ima boostera)
    ai_calls_per_match: int = 6
    ai_min_confidence: float = 0.7
    # Na ekranu sa cenom sme samo besplatan X/Continue, uz vecu sigurnost.
    ai_free_tap_confidence: float = 0.85
    max_tap_attempts: int = 2
    verify_timeout: float = 6.0
    poll_interval: float = 0.8
    button_wait_seconds: float = 8.0  # koliko cekamo dugme koje kasni pre nego sto pitamo AI
    unknown_grace: float = 6.0
    # Posle "cekanja protivnika" i posle meca dolaze animacije (VS ekran,
    # brojanje poena): nepoznat ekran tu sme duze da potraje pre AI-ja.
    unknown_grace_transition: float = 20.0
    search_timeout: float = 240.0
    search_retries: int = 3  # posle toliko CANCEL-a bez protivnika: pauza
    match_max_seconds: float = 1500.0
    # Tokom meca: na koliko sekundi se gleda ekran, i koliko uzastopnih
    # ekrana rezultata/lobija zavrsava mec kad reader kraj ne javi.
    match_screen_check: float = 3.0
    match_end_confirmations: int = 2
    after_match_delay: float = 3.0
    passive_screen_timeout: float = 30.0
    ai_settle_seconds: float = 2.5
    ai_wait_seconds: float = 5.0  # AI kaze "wait" (animacija/ucitavanje): pauza pre novog pogleda
    repeat_tap_radius: float = 40.0
    # Isti ekran klikan vise puta u jednom ciklusu = petlja (npr. PLAY ->
    # Refill -> X -> PLAY ...): pauza umesto beskonacnog klikanja.
    max_taps_per_screen: int = 4


@dataclass
class AutopilotStats:
    games_done: int = 0
    ai_calls_this_match: int = 0
    ai_calls_total: int = 0
    taps: int = 0
    phase: str = "idle"
    last_screen: str | None = None
    events: list[str] = field(default_factory=list)


class Autopilot:
    def __init__(self, device, classifier: ScreenClassifier, advisor, gate: StopGate,
                 config: AutopilotConfig, *, flow: dict | None = None,
                 on_status: Callable[[str], None] | None = None,
                 log_dir: Path = LOG_DIR, clock: Callable[[], float] = time.monotonic):
        self.device = device
        self.classifier = classifier
        self.advisor = advisor
        self.gate = gate
        self.config = config
        self.flow = dict(DEFAULT_FLOW)
        self.flow.update((flow if flow is not None else classifier.config.get("flow", {})) or {})
        self.on_status = on_status
        self.log_dir = Path(log_dir)
        self.clock = clock
        self.stats = AutopilotStats()
        self._match_active = threading.Event()
        self._match_seen = threading.Event()
        self._phase = "to_match"
        self._last_ai_tap: tuple[tuple[int, int], object] | None = None  # (tacka, sličica ekrana)
        self._unknown_since: float | None = None
        self._passive_since: tuple[str, float] | None = None
        self._searching_since: float | None = None
        self._grace = config.unknown_grace
        self._screen_taps: dict[str, int] = {}
        self._scrolls: list[str] = []
        self._search_retries = 0
        self._button_waits = 0  # uzastopni pogledi bez trazenog dugmeta (pre AI poziva)
        self._thread: threading.Thread | None = None
        self.result: str | None = None

    # --- spolja (GUI nit) -------------------------------------------------
    def notify_match(self, active: bool) -> None:
        """Reader je javio pocetak/kraj meca."""
        if active:
            self._match_active.set()
            self._match_seen.set()
        else:
            self._match_active.clear()

    def start(self) -> threading.Thread:
        self._thread = threading.Thread(target=self.run, name="autopilot", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        self.gate.stop()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --- log ----------------------------------------------------------------
    def _status(self, message: str) -> None:
        line = time.strftime("%H:%M:%S ") + message
        self.stats.events.append(line)
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with (self.log_dir / "autopilot.log").open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d ") + line + "\n")
        except OSError:
            pass
        if self.on_status is not None:
            self.on_status(message)

    def _log_ai(self, entry: dict) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            with (self.log_dir / "ai_calls.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # --- glavna petlja ------------------------------------------------------
    def run(self) -> str:
        cfg = self.config
        self._status(f"Autopilot start: igra mod koji igra ponudi, partija={cfg.games_limit or 'bez limita'}, "
                     f"AI limit po mecu={cfg.ai_calls_per_match}")
        try:
            while not self.gate.stopped:
                self._tick()
            self.result = "stopped"
            self._status("Autopilot zaustavljen (Stop)")
        except StopRequested:
            self.result = "stopped"
            self._status("Autopilot zaustavljen (Stop) - klik blokiran")
        except Paused as exc:
            self.result = f"paused: {exc}"
            self._status(f"PAUZA: {exc}")
        except _Finished as exc:
            self.result = "finished"
            self._status(str(exc))
        except DeviceError as exc:
            self.result = f"paused: {exc}"
            self._status(f"PAUZA (ADB): {exc}")
        self.stats.phase = "idle"
        return self.result

    def _set_phase(self, phase: str) -> None:
        if phase != self._phase:
            self._phase = phase
        self.stats.phase = phase

    def _tick(self) -> None:
        cfg = self.config
        # `_match_seen` keeps a start that came and went between two checks
        # (a very short match, or a slow screenshot) from being missed.
        if self._match_active.is_set() or self._match_seen.is_set():
            self._match_seen.clear()
            self._play_match()
            return
        png = self.device.screenshot_png()
        cls = self.classifier.classify(_png_image(png))
        if self._match_active.is_set() or self._match_seen.is_set():
            return
        if cls.forbidden:
            raise Paused(f"ekran '{cls.name}' je oznacen kao zabranjen (kupovina/trosenje)")
        if not cls.known:
            self._handle_unknown(png, why="lokalna pravila ne prepoznaju ekran")
            return
        self._seen_known(cls)
        screen = cls.name
        if screen in (LOBBY, RESULTS) and self._phase == "to_lobby":
            self.stats.games_done += 1
            limit = cfg.games_limit or "bez limita"
            where = "nazad u lobiju" if screen == LOBBY else "ekran rezultata"
            self._status(f"Partija {self.stats.games_done}/{limit} zavrsena, {where}")
            self._screen_taps.clear()
            if cfg.games_limit and self.stats.games_done >= cfg.games_limit:
                # Na rezultatima: CLOSE do lobija, tamo stop (ne PLAY AGAIN).
                self._set_phase("finishing")
            else:
                self._set_phase("to_match")
        if screen == LOBBY and self._phase == "finishing":
            raise _Finished(f"Gotovo: {self.stats.games_done} partija, lobi, stop")
        step = self.flow.get(screen)
        if step is None:
            self._passive(screen, png)
            return
        if step.get("wait"):
            if screen == SEARCHING:
                self._grace = cfg.unknown_grace_transition
                now = self.clock()
                if self._searching_since is None:
                    self._searching_since = now
                    self._status("Cekam protivnika (lokalno, bez API-ja)")
                elif now - self._searching_since > cfg.search_timeout:
                    self._searching_since = None
                    self._search_retries += 1
                    cancel = self.classifier.tap_point(SEARCHING, "cancel")
                    if cancel is None or self._search_retries > cfg.search_retries:
                        raise Paused(f"protivnik nije nadjen ni posle {self._search_retries} pokusaja "
                                     f"od po {cfg.search_timeout:.0f}s")
                    self._status(f"Protivnik nije nadjen za {cfg.search_timeout:.0f}s: CANCEL i ponovo "
                                 f"({self._search_retries}/{cfg.search_retries})")
                    self._screen_taps.clear()
                    self._tap_and_verify(SEARCHING, "cancel", cancel, ["mode_select", LOBBY])
                    return
            else:
                self._passive(screen, png)
                return
            self._sleep(cfg.poll_interval)
            return
        self._searching_since = None
        tap_name = str(step["tap"])
        expect = list(step.get("expect", []))
        fallback = step.get("fallback")
        fallback_expect = list(step.get("fallback_expect", expect))
        image = _png_image(png)
        if fallback and self._phase == "finishing":
            tap_name, expect = str(fallback), fallback_expect  # limit: CLOSE, ne nova partija
        point = self.classifier.tap_point(screen, tap_name, image)
        if point is None and fallback and tap_name != fallback:
            # npr. nema PLAY AGAIN (stari izgled ekrana rezultata): CLOSE.
            fb_point = self.classifier.tap_point(screen, str(fallback), image)
            if fb_point is not None:
                tap_name, point, expect = str(fallback), fb_point, fallback_expect
        if point is None:
            if self.classifier.has_tap(screen, tap_name):
                if self._button_waits * cfg.poll_interval < cfg.button_wait_seconds:
                    # Dugme cesto kasni (ekran rezultata animira nagrade): sacekaj bez AI.
                    self._button_waits += 1
                    if self._button_waits == 1:
                        self._status(f"Cekam da se pojavi dugme '{tap_name}' ({screen})")
                    self._sleep(cfg.poll_interval)
                    return
                self._button_waits = 0
                self._ai_step(png, why=f"dugme '{tap_name}' nije nadjeno na ekranu '{screen}'",
                              expected=expect)
                return
            raise Paused(f"nema koordinata za tap '{tap_name}' na ekranu '{screen}' (data/autopilot_rules.json)")
        self._button_waits = 0
        self._tap_and_verify(screen, tap_name, point, expect)

    def _passive(self, screen: str, png: bytes) -> None:
        """Poznat ekran bez akcije u toku: cekaj, a ako predugo stoji, pitaj AI."""
        now = self.clock()
        if self._passive_since is None or self._passive_since[0] != screen:
            self._passive_since = (screen, now)
        elif now - self._passive_since[1] > self.config.passive_screen_timeout:
            self._passive_since = None
            self._ai_step(png, why=f"ekran '{screen}' nema akciju u pravilima i stoji "
                                   f"{self.config.passive_screen_timeout:.0f}s")
            return
        self._sleep(self.config.poll_interval)

    def _seen_known(self, cls: Classification) -> None:
        self._unknown_since = None
        self._last_ai_tap = None
        if cls.name != SEARCHING:
            self._grace = self.config.unknown_grace if self._phase == "to_match" else self._grace
        if cls.name != self.stats.last_screen:
            self._status(f"Ekran: {cls.name} ({cls.score:.2f})")
        self.stats.last_screen = cls.name

    def _handle_unknown(self, png: bytes, why: str) -> None:
        now = self.clock()
        if self._unknown_since is None:
            self._unknown_since = now
        if now - self._unknown_since < self._grace:
            self._sleep(self.config.poll_interval)
            return
        self._unknown_since = None
        self._ai_step(png, why=why)

    def _play_match(self) -> None:
        cfg = self.config
        self._set_phase("in_match")
        self.stats.ai_calls_this_match = 0
        self._searching_since = None
        # Tajmeri iz pre meca (VS ekran je nepoznat) ne smeju da se prenesu:
        # inace AI krene odmah posle meca umesto posle grace-a.
        self._unknown_since = None
        self._passive_since = None
        self._screen_taps.clear()
        self._scrolls.clear()
        self._search_retries = 0
        self._button_waits = 0  # uzastopni pogledi bez trazenog dugmeta (pre AI poziva)
        self._status("Reader: mec poceo - igra postojeci Auto, Autopilot ne klikce")
        started = self.clock()
        next_check = started + cfg.match_screen_check
        over_hits = 0
        by_screen = None
        while self._match_active.is_set():
            if self.gate.wait(min(0.5, cfg.match_screen_check)):
                raise StopRequested("Stop tokom meca")
            now = self.clock()
            if now - started > cfg.match_max_seconds:
                raise Paused(f"mec traje duze od {cfg.match_max_seconds:.0f}s bez kraja od readera")
            if now < next_check:
                continue
            next_check = now + cfg.match_screen_check
            # Reader ume da ostane na "mec u toku" (npr. tehnicka pobeda kad
            # protivnik izadje): ekran rezultata/lobi je dovoljan dokaz kraja.
            try:
                cls = self.classifier.classify(_png_image(self.device.screenshot_png()))
            except DeviceError:
                continue
            over_hits = over_hits + 1 if cls.name in MATCH_OVER_SCREENS else 0
            if over_hits >= max(1, cfg.match_end_confirmations) and self._match_active.is_set():
                by_screen = cls.name
                self._match_active.clear()
                self._match_seen.clear()
        if by_screen:
            self._status(f"Ekran '{by_screen}': mec je gotov, iako ga reader jos vodi kao aktivan")
        else:
            self._status("Reader: mec zavrsen - vracam se u lobi")
        self._set_phase("to_lobby")
        self._grace = cfg.unknown_grace_transition
        self.stats.last_screen = None
        self._sleep(cfg.after_match_delay)

    def _tap(self, point: tuple[int, int]) -> None:
        self.device.tap(*point)  # StopGate se proverava u samom tapu
        self.stats.taps += 1

    def _tap_and_verify(self, screen: str, tap_name: str, point, expect: list[str]) -> None:
        cfg = self.config
        count = self._screen_taps.get(screen, 0) + 1
        self._screen_taps[screen] = count
        if count > cfg.max_taps_per_screen:
            raise Paused(f"ekran '{screen}' se ponavlja ({count - 1}x u istom ciklusu) - verovatno petlja")
        for attempt in range(1, cfg.max_tap_attempts + 1):
            self._status(f"Tap '{tap_name}' na '{screen}' {point} (pokusaj {attempt}), cekam {expect}")
            self._tap(point)
            outcome = self._await_transition(screen, expect)
            if outcome in ("expected", "match"):
                return
            if outcome == "other_known":
                self._status(f"Posle '{tap_name}' stigao drugi poznat ekran; nastavljam od njega")
                return
            if outcome == "unknown":
                if SEARCHING in expect:
                    # Ulaz u mec: VS/ucitavanje pre ekrana cekanja nije greska.
                    self._grace = cfg.unknown_grace_transition
                return  # glavna petlja vodi nepoznat ekran (grace pa AI)
        png = self.device.screenshot_png()
        self._ai_step(png, why=f"prelaz '{screen}' -> {expect} izostao posle "
                               f"{cfg.max_tap_attempts} klika na '{tap_name}'", expected=expect)

    def _await_transition(self, screen: str, expect: list[str]) -> str:
        cfg = self.config
        deadline = self.clock() + cfg.verify_timeout
        last = "same"
        while self.clock() < deadline:
            self._sleep(cfg.poll_interval)
            if self._match_active.is_set() or self._match_seen.is_set():
                return "match"
            cls = self.classifier.classify(_png_image(self.device.screenshot_png()))
            if cls.name in expect:
                self._seen_known(cls)
                return "expected"
            if cls.known and cls.name != screen:
                last = "other_known"
            elif not cls.known:
                last = "unknown"
            else:
                last = "same"
        return last

    # --- AI -----------------------------------------------------------------
    def _expected_now(self) -> list[str]:
        if self._phase in ("to_lobby", "finishing"):
            return [RESULTS, LOBBY]
        last = self.stats.last_screen
        step = self.flow.get(last or "", {})
        return list(step.get("expect", [])) or [LOBBY, SEARCHING]

    def _ai_hint(self) -> str:
        """Cilj za AI: iz pravila ekrana (`ai_hint`), inace opsti."""
        screens = self.classifier.config.get("screens", {})
        hint = screens.get(self.stats.last_screen or "", {}).get("ai_hint", "")
        if hint and self._scrolls:
            hint += f" Scroll history on this screen so far: {', '.join(self._scrolls[-8:])}."
        return hint or ("Get back to the lobby or into a new match: close any pop-up with X, "
                        "or press Continue/OK/Collect if there is no X.")

    def _ai_step(self, png: bytes, *, why: str, expected: list[str] | None = None) -> None:
        cfg = self.config
        expected = expected or self._expected_now()
        if self.stats.ai_calls_this_match >= cfg.ai_calls_per_match:
            raise Paused(f"dostignut limit AI poziva po mecu ({cfg.ai_calls_per_match}); poslednji razlog: {why}")
        self.gate.check()
        self.stats.ai_calls_this_match += 1
        self.stats.ai_calls_total += 1
        stamp = time.strftime("%Y%m%d_%H%M%S")
        shot = self.log_dir / "ai_screens" / f"{stamp}_{self.stats.ai_calls_total}.png"
        try:
            shot.parent.mkdir(parents=True, exist_ok=True)
            shot.write_bytes(png)
        except OSError:
            shot = None
        step = f"{self._phase}; poslednji ekran={self.stats.last_screen or '-'}"
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "why": why, "step": step,
                 "expected": expected, "call": self.stats.ai_calls_this_match,
                 "limit": cfg.ai_calls_per_match, "screenshot": str(shot) if shot else None}
        self._status(f"AI poziv {self.stats.ai_calls_this_match}/{cfg.ai_calls_per_match}: {why}")
        from autopilot_ai import AiUnavailable
        try:
            proposal = self.advisor.propose(png, step=step, expected=expected, why=why,
                                            last_screen=self.stats.last_screen, hint=self._ai_hint())
        except AiUnavailable as exc:
            entry["error"] = str(exc)
            self._log_ai(entry)
            raise Paused(f"AI nedostupan: {exc}") from exc
        entry["proposal"] = {"action": proposal.action, "x": proposal.x, "y": proposal.y,
                             "confidence": proposal.confidence, "screen": proposal.screen,
                             "reason": proposal.reason, "spends_resources": proposal.spends_resources,
                             "tap_is_free": proposal.tap_is_free}
        entry["meta"] = proposal.meta
        self._log_ai(entry)
        self._status(f"AI: {proposal.action} ({proposal.x},{proposal.y}) sig={proposal.confidence:.2f} "
                     f"- {proposal.screen}: {proposal.reason}")
        if proposal.action == "pause":
            raise Paused(f"AI nije siguran: {proposal.reason}")
        if proposal.action == "wait":
            # Cekanje nista ne dira (npr. ekran rezultata jos animira nagrade), pa ne
            # trazi visoku sigurnost; cekamo duze da sledeci pogled vidi dugmad.
            self._status("AI: ekran se jos menja, cekam pa gledam ponovo")
            self._sleep(cfg.ai_wait_seconds)
            return
        if proposal.confidence < cfg.ai_min_confidence:
            raise Paused(f"AI nije dovoljno siguran ({proposal.confidence:.2f}): {proposal.reason}")
        if proposal.spends_resources:
            # Ekran sa cenom: dozvoljeno je samo besplatno zatvaranje (X / Continue),
            # i to samo kad je AI bas siguran.
            if not (proposal.action == "tap" and proposal.tap_is_free
                    and proposal.confidence >= cfg.ai_free_tap_confidence):
                raise Paused(f"ekran trazi kupovinu/trosenje, a nema sigurnog besplatnog izlaza ({proposal.screen})")
            self._status("Ekran sa cenom: AI zatvara besplatnim dugmetom, nista se ne kupuje")
        if proposal.action in ("scroll_down", "scroll_up"):
            x = min(800, max(100, proposal.x or 450))
            top, bottom = 450, 1150
            start, end = (bottom, top) if proposal.action == "scroll_down" else (top, bottom)
            self.gate.check()
            self.device.swipe(x, start, x, end)
            self._scrolls.append(proposal.action.replace("scroll_", ""))
            self._sleep(cfg.ai_settle_seconds)
            return
        point = (proposal.x, proposal.y)
        width, height = 900, 1600
        if not (0 <= point[0] < width and 0 <= point[1] < height):
            raise Paused(f"AI predlaze tap van ekrana {point}")
        thumb = _screen_thumb(png)
        if self._last_ai_tap is not None and math.dist(point, self._last_ai_tap[0]) <= cfg.repeat_tap_radius \
                and _same_screen(thumb, self._last_ai_tap[1]):
            # Isto mesto je u redu ako je ekran drugaciji (CLOSE na rezultatima,
            # pa COLLECT na stikerima); pauza samo kad klik nista nije promenio.
            raise Paused(f"AI ponavlja isti klik {point} bez promene ekrana")
        self._last_ai_tap = (point, thumb)
        self._tap(point)
        self._sleep(cfg.ai_settle_seconds)
        after = self.classifier.classify(_png_image(self.device.screenshot_png()))
        self._log_ai({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "result_after_tap": after.name or "nepoznat",
                      "score": round(after.score, 3)})
        self._status(f"Posle AI klika: {after.name or 'i dalje nepoznat ekran'}")
        if after.known:
            self._seen_known(after)

    def _sleep(self, seconds: float) -> None:
        if self.gate.wait(seconds):
            raise StopRequested("Stop")


class _Finished(Exception):
    pass


def _screen_thumb(png: bytes):
    from autopilot_screens import _thumb, _to_bgr
    try:
        return _thumb(_to_bgr(_png_image(png)))
    except Exception:  # noqa: BLE001 - lose slike (testovi): bez poredjenja
        return None


def _same_screen(a, b, threshold: float = 0.97) -> bool:
    if a is None or b is None:
        return True  # ne znamo: ostaje stara (oprezna) provera
    from autopilot_screens import _correlation
    return _correlation(a, b) >= threshold


def _png_image(png: bytes):
    from PIL import Image
    return Image.open(io.BytesIO(png)).convert("RGB")
