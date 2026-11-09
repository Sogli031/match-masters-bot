"""Autopilot: lokalno prepoznavanje, tok ciklusa, AI rezerva i Stop -- bez ADB-a i bez API-ja."""
from __future__ import annotations

import io
import subprocess
import threading
import time

import numpy as np
import pytest
from PIL import Image

import autopilot as ap
import autopilot_device as dev
from autopilot_ai import AiProposal, parse_proposal
from autopilot_screens import ScreenClassifier

W, H = 900, 1600
BUTTONS = {  # ekran -> (tap ime, box dugmeta)
    "lobby": ("open_modes", (300, 1300, 300, 120)),
    "mode_select": ("play", (100, 500, 300, 160)),
    "results": ("continue", (300, 1400, 300, 120)),
}
COLORS = {"lobby": (40, 90, 200), "mode_select": (200, 120, 40),
          "searching": (120, 40, 140), "results": (220, 200, 60), "shop": (10, 10, 10)}


def _screen(name: str, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(sum(map(ord, name)))  # isti uzorak za isti ekran
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = COLORS.get(name, (128, 128, 128))
    # Naslov ekrana: uzorak jedinstven po ekranu (sidro).
    img[60:200, 150:750] = rng.integers(0, 255, (140, 600, 3), dtype=np.uint8)
    if name in BUTTONS:
        x, y, w, h = BUTTONS[name][1]
        img[y:y + h, x:x + w] = rng.integers(0, 255, (h, w, 3), dtype=np.uint8)
    # Promenljiv deo (npr. broj novcica) koji ne sme da smeta.
    img[900:1000, 100:800] = np.random.default_rng(seed).integers(0, 255, (100, 700, 3), dtype=np.uint8)
    return Image.fromarray(img)


def _unknown(seed: int = 7) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 255, (H, W, 3), dtype=np.uint8))


@pytest.fixture
def screens(tmp_path):
    folder = tmp_path / "screens"
    folder.mkdir()
    rules = {"screens": {}}
    for name in COLORS:
        _screen(name).save(folder / f"{name}.png")
        cfg = {"anchors": [{"box": [150, 60, 600, 140], "min": 0.8}], "taps": {}}
        if name in BUTTONS:
            tap, (x, y, w, h) = BUTTONS[name]
            cfg["taps"][tap] = [x + w // 2, y + h // 2]
        if name == "shop":
            cfg["forbidden"] = True
        if name == "searching":
            cfg["taps"]["cancel"] = [136, 72]
        rules["screens"][name] = cfg
    return ScreenClassifier(rules, screens_dir=folder)


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


class FakeGame:
    """Ekrani menjaju stanje na tap u dugme; 'searching' posle par slika zapocinje mec."""

    TRANSITIONS = {"lobby": "mode_select", "mode_select": "searching",
                   "results": "lobby"}

    def __init__(self, gate, start="lobby", search_frames=3, broken_taps=(), reader_reports_end=True):
        self.gate = gate
        self.reader_reports_end = reader_reports_end
        self.screen = start
        self.taps: list[tuple[int, int]] = []
        self.shots = 0
        self.search_frames = search_frames
        self.broken = set(broken_taps)
        self.autopilot = None
        self.extra_targets: dict[tuple[int, int], str] = {}
        self.swipes: list = []
        self.after_swipe = None
        self._frame = 0

    def screenshot_png(self) -> bytes:
        self.shots += 1
        self._frame += 1
        if self.screen == "searching":
            self.search_frames -= 1
            if self.search_frames <= 0 and self.autopilot is not None:
                self.screen = "results"
                # Reader: mec pocinje pa (posle igre) zavrsava.
                self.autopilot.notify_match(True)
                if self.reader_reports_end:
                    threading.Timer(0.05, self.autopilot.notify_match, args=(False,)).start()
        if self.screen == "unknown":
            return _png(_unknown())
        return _png(_screen(self.screen, seed=self._frame))

    def swipe(self, x1, y1, x2, y2, ms=450):
        self.gate.check()
        self.swipes.append((x1, y1, x2, y2))
        if self.after_swipe:
            self.screen = self.after_swipe

    def tap(self, x, y):
        self.gate.check()
        self.taps.append((x, y))
        if self.screen == "searching" and (x, y) == (136, 72):
            self.screen = "mode_select"
            return
        if (x, y) in self.extra_targets:
            self.screen = self.extra_targets[(x, y)]
            return
        if self.screen in BUTTONS and self.screen not in self.broken:
            bx, by, bw, bh = BUTTONS[self.screen][1]
            if bx <= x < bx + bw and by <= y < by + bh:
                self.screen = self.TRANSITIONS[self.screen]


class FakeAdvisor:
    def __init__(self, *proposals):
        self.proposals = list(proposals)
        self.calls = []

    def propose(self, png, **kwargs):
        self.calls.append(kwargs)
        return self.proposals.pop(0) if self.proposals else AiProposal("pause", reason="nema vise")


def _fast_config(**kw):
    base = dict(games_limit=1, ai_calls_per_match=3, verify_timeout=0.15,
                poll_interval=0.01, unknown_grace=0.05, unknown_grace_transition=0.05,
                after_match_delay=0.01, ai_settle_seconds=0.01, ai_wait_seconds=0.01,
                button_wait_seconds=0.05, search_timeout=5, passive_screen_timeout=0.2)
    base.update(kw)
    return ap.AutopilotConfig(**base)


def _pilot(game, screens, advisor, tmp_path, **kw):
    pilot = ap.Autopilot(game, screens, advisor, game.gate, _fast_config(**kw), log_dir=tmp_path / "log")
    game.autopilot = pilot
    return pilot


def _run(pilot, timeout=10.0):
    thread = pilot.start()
    thread.join(timeout)
    assert not thread.is_alive(), "Autopilot nije zavrsio"
    return pilot.result


# --- prepoznavanje ---------------------------------------------------------

def test_known_screens_are_recognised_locally(screens):
    for name in COLORS:
        cls = screens.classify(_screen(name, seed=5))  # drugi "promenljiv" deo
        assert cls.name == name
    assert screens.classify(_unknown()).name is None
    assert screens.classify(_screen("shop")).forbidden


def test_instance_port_prefers_live_status_port():
    conf = ('bst.instance.Pie64.status.adb_port="5555"\n'
            'bst.instance.Pie64_2.adb_port="5575"\n'
            'bst.instance.Pie64_2.status.adb_port="5577"\n')
    assert dev.instance_port(conf, "Pie64_2") == 5577
    assert dev.instance_port(conf, "Pie64") == 5555
    assert dev.instance_port(conf, "Pie64_9") is None


def test_ai_coordinates_scale_back_to_full_screen():
    proposal = parse_proposal('{"action":"tap","x":225,"y":400,"confidence":0.9,"screen":"s",'
                              '"reason":"r","spends_resources":false}', (2.0, 2.0))
    assert (proposal.x, proposal.y) == (450, 800)


# --- ciklus ----------------------------------------------------------------

def test_full_cycle_known_screens_never_call_api(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate)
    advisor = FakeAdvisor()
    pilot = _pilot(game, screens, advisor, tmp_path)
    assert _run(pilot) == "finished"
    assert advisor.calls == []
    assert pilot.stats.games_done == 1
    assert game.screen == "lobby"
    # lobi -> PLAY na boosteru -> [cekanje, mec] -> rezultati -> lobi
    assert len(game.taps) == 3


def test_unknown_screen_triggers_ai_fallback(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    game.extra_targets[(450, 50)] = "lobby"
    advisor = FakeAdvisor(AiProposal("tap", 450, 50, confidence=0.95, screen="popup", reason="zatvori"))
    pilot = _pilot(game, screens, advisor, tmp_path)
    assert _run(pilot) == "finished"
    assert len(advisor.calls) == 1
    assert "ne prepoznaju" in advisor.calls[0]["why"]
    log = (tmp_path / "log" / "ai_calls.jsonl").read_text(encoding="utf-8")
    assert "ne prepoznaju" in log and "ANTHROPIC" not in log


def test_missing_transition_calls_ai_after_limited_attempts(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, broken_taps={"lobby"})
    advisor = FakeAdvisor(AiProposal("pause", reason="ne znam"))
    pilot = _pilot(game, screens, advisor, tmp_path, max_tap_attempts=2)
    result = _run(pilot)
    assert result.startswith("paused") and "AI nije siguran" in result
    assert len(game.taps) == 2
    assert "izostao posle 2" in advisor.calls[0]["why"]


def test_ai_call_limit_per_match(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    advisor = FakeAdvisor()
    pilot = _pilot(game, screens, advisor, tmp_path, ai_calls_per_match=0)
    assert "limit AI poziva" in _run(pilot)
    assert advisor.calls == []


@pytest.mark.parametrize("proposal,needle", [
    (AiProposal("tap", 10, 10, confidence=0.9, spends_resources=True, screen="shop"), "kupovinu"),
    (AiProposal("tap", 10, 10, confidence=0.8, spends_resources=True, tap_is_free=True), "kupovinu"),
    (AiProposal("tap", 10, 10, confidence=0.3, reason="mozda"), "nije dovoljno siguran"),
    (AiProposal("pause", reason="cudan ekran"), "AI nije siguran"),
])
def test_ai_unsafe_answers_pause_without_click(screens, tmp_path, proposal, needle):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    pilot = _pilot(game, screens, FakeAdvisor(proposal), tmp_path)
    assert needle in _run(pilot)
    assert game.taps == []


def test_ai_repeating_same_click_pauses(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    advisor = FakeAdvisor(AiProposal("tap", 400, 400, confidence=0.9),
                          AiProposal("tap", 410, 405, confidence=0.9))
    pilot = _pilot(game, screens, advisor, tmp_path)
    assert "ponavlja isti klik" in _run(pilot)
    assert game.taps == [(400, 400)]


def test_forbidden_screen_pauses_without_ai(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="shop")
    advisor = FakeAdvisor()
    assert "zabranjen" in _run(_pilot(game, screens, advisor, tmp_path))
    assert advisor.calls == [] and game.taps == []


# --- Stop ------------------------------------------------------------------

def test_stop_blocks_adb_tap_before_it_is_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))
    gate = dev.StopGate()
    device = dev.AdbDevice("adb", "127.0.0.1:5575", gate)
    gate.stop()
    with pytest.raises(dev.StopRequested):
        device.tap(10, 10)
    assert calls == []


def test_stop_during_run_blocks_further_clicks(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, search_frames=10_000)  # zaglavi u cekanju protivnika
    pilot = _pilot(game, screens, FakeAdvisor(), tmp_path)
    thread = pilot.start()
    deadline = time.monotonic() + 5
    while game.screen != "searching" and time.monotonic() < deadline:
        time.sleep(0.01)
    taps_before = len(game.taps)
    started = time.monotonic()
    pilot.stop()
    thread.join(2)
    assert not thread.is_alive() and time.monotonic() - started < 1.0
    assert pilot.result == "stopped"
    game.screen = "lobby"
    with pytest.raises(dev.StopRequested):
        game.tap(450, 1360)
    assert len(game.taps) == taps_before


# --- prave slike korisnika (assets/autopilot) --------------------------------

def test_real_menu_screens_recognised_and_match_screen_unknown():
    from autopilot_screens import PROJECT_ROOT, SCREENS_DIR, reference_files
    classifier = ScreenClassifier()
    files = reference_files()
    assert {"lobby", "mode_select", "results"} <= set(files)
    for name, paths in files.items():
        for path in paths:
            assert classifier.classify(path).name == name, path.name
    probe = PROJECT_ROOT / "assets" / "autopilot" / "check" / "unknown__in_match.png"
    assert classifier.classify(probe).name is None
    refill = classifier.classify(SCREENS_DIR / "refill_perk.png")
    assert not refill.forbidden and classifier.tap_point("refill_perk", "close") == (808, 562)
    # Svaki tap iz toka postoji za ekran koji ima sliku.
    flow = dict(ap.DEFAULT_FLOW, **classifier.config.get("flow", {}))
    for screen, step in flow.items():
        if "tap" in step and screen in files:
            image = files[screen][0]
            assert (classifier.tap_point(screen, step["tap"], image)
                    or classifier.tap_point(screen, step.get("fallback", ""), image)), (screen, step)


def test_results_screen_with_play_again_found_on_real_images():
    """Kraj meca sa PLAY AGAIN levo i CLOSE desno (tehnicka pobeda, 2026-11-09)."""
    from autopilot_screens import PROJECT_ROOT, SCREENS_DIR
    classifier = ScreenClassifier()
    new =SCREENS_DIR / "results__play_again.png"
    old = SCREENS_DIR / "results.png"
    assert classifier.classify(new).name == "results"
    x, y = classifier.tap_point("results", "play_again", new)
    assert 160 < x < 420 and 1395 < y < 1525
    x, y = classifier.tap_point("results", "continue", new)
    assert 555 < x < 735 and 1395 < y < 1525  # CLOSE pomeren udesno
    # Isecak sa korisnikovog snimka (TECHNICAL WIN natpis iznad, protivnik izasao).
    technical = PROJECT_ROOT / "assets" / "autopilot" / "check" / "results__technical_win.png"
    assert classifier.classify(technical).name == "results"
    assert classifier.tap_point("results", "play_again", technical) == classifier.tap_point(
        "results", "play_again", new)
    assert classifier.tap_point("results", "play_again", old) is None
    assert classifier.tap_point("results", "continue", old) == (452, 1455)
    step = classifier.config["flow"]["results"]
    assert step["tap"] == "play_again" and step["fallback"] == "continue"


def test_results_screen_ends_match_and_plays_again_when_reader_stays_active(screens, tmp_path):
    """Reader ne javi kraj meca: Autopilot sam vidi rezultate i pritisne PLAY AGAIN."""
    play_again = (150, 1460)
    screens.rules["results"].taps["play_again"] = play_again
    gate = dev.StopGate()
    game = FakeGame(gate, reader_reports_end=False)
    game.extra_targets[play_again] = "searching"
    advisor = FakeAdvisor()
    pilot = _pilot(game, screens, advisor, tmp_path, games_limit=2,
                   match_screen_check=0.02, match_end_confirmations=2)
    original = game.tap

    def tap(x, y):
        original(x, y)
        if game.screen == "searching":
            game.search_frames = 2

    game.tap = tap
    assert _run(pilot) == "finished"
    assert advisor.calls == []
    assert pilot.stats.games_done == 2
    # lobi, PLAY, [mec], PLAY AGAIN, [mec], CLOSE (limit) -> lobi
    assert game.taps == [(450, 1360), (250, 580), play_again, (450, 1460)]
    assert game.screen == "lobby"
    assert any("iako ga reader jos vodi" in line for line in pilot.stats.events)


def test_real_screens_survive_small_shift_noise_and_brightness():
    import cv2
    from autopilot_screens import reference_files
    classifier = ScreenClassifier()
    rng = np.random.default_rng(1)
    for name, paths in reference_files().items():
        img = cv2.imdecode(np.fromfile(str(paths[0]), np.uint8), cv2.IMREAD_COLOR)
        moved = cv2.warpAffine(img, np.float32([[1, 0, -6], [0, 1, 7]]), (W, H),
                               borderMode=cv2.BORDER_REPLICATE)
        moved[rng.integers(0, H, 400), rng.integers(0, W, 400)] = 255
        moved = cv2.convertScaleAbs(moved, alpha=1.05, beta=-6)
        assert classifier.classify(moved).name == name, name


def test_booster_play_is_found_wherever_it_moves():
    import cv2
    from autopilot_screens import SCREENS_DIR
    classifier = ScreenClassifier()
    img = cv2.imdecode(np.fromfile(str(SCREENS_DIR / "mode_select.png"), np.uint8), cv2.IMREAD_COLOR)
    assert classifier.tap_point("mode_select", "play", img) == (160, 925)
    # Izabran drugi booster: isto PLAY dugme u trecoj koloni.
    moved = img.copy()
    moved[874:976, 66:254] = (40, 20, 60)
    moved[874:976, 650:838] = img[874:976, 66:254]
    assert classifier.tap_point("mode_select", "play", moved) == (744, 925)
    # Nema PLAY (npr. sve zakljucano): nema klika, pa AI ili pauza.
    moved[874:976, 650:838] = (40, 20, 60)
    assert classifier.tap_point("mode_select", "play", moved) is None


def test_missing_play_button_asks_ai_instead_of_clicking(screens, tmp_path):
    screens.rules["mode_select"].taps.pop("play")
    from autopilot_screens import Anchor
    screens.rules["mode_select"].finds["play"] = Anchor((0, 0, 50, 50), np.full((50, 50, 3), 7, np.uint8), 0.99, 2000)
    gate = dev.StopGate()
    game = FakeGame(gate)
    advisor = FakeAdvisor(AiProposal("pause", reason="nema PLAY"))
    result = _run(_pilot(game, screens, advisor, tmp_path))
    assert "AI nije siguran" in result and "nije nadjeno" in advisor.calls[0]["why"]
    assert len(game.taps) == 1  # samo PLAY u lobiju


def test_low_confidence_wait_keeps_waiting_instead_of_pausing(screens, tmp_path):
    # Ekran rezultata jos animira nagrade: AI kaze "wait" sa sig. 0.60 -> cekaj, ne pauziraj.
    screens.rules["mode_select"].taps.pop("play")
    from autopilot_screens import Anchor
    screens.rules["mode_select"].finds["play"] = Anchor((0, 0, 50, 50), np.full((50, 50, 3), 7, np.uint8), 0.99, 2000)
    gate = dev.StopGate()
    game = FakeGame(gate)
    advisor = FakeAdvisor(AiProposal("wait", confidence=0.6, reason="animacija"),
                          AiProposal("pause", reason="i dalje nema PLAY"))
    result = _run(_pilot(game, screens, advisor, tmp_path))
    assert len(advisor.calls) == 2  # posle "wait" je pogledao ponovo
    assert "nije dovoljno siguran" not in result and "AI nije siguran" in result


def test_stale_unknown_timer_from_before_match_does_not_call_ai_early(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    advisor = FakeAdvisor()
    pilot = _pilot(game, screens, advisor, tmp_path, unknown_grace=30, unknown_grace_transition=30)
    pilot._unknown_since = pilot.clock() - 100  # VS ekran pre meca
    pilot.notify_match(True)
    threading.Timer(0.05, pilot.notify_match, args=(False,)).start()
    thread = pilot.start()
    time.sleep(0.5)
    pilot.stop()
    thread.join(2)
    assert advisor.calls == []


def test_screen_tapped_too_often_in_one_cycle_pauses(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate)
    game.TRANSITIONS = dict(FakeGame.TRANSITIONS, mode_select="lobby")  # PLAY vraca u lobi
    advisor = FakeAdvisor()
    result = _run(_pilot(game, screens, advisor, tmp_path, max_taps_per_screen=3))
    assert "se ponavlja" in result and advisor.calls == []
    assert len(game.taps) == 6  # 3x lobi + 3x PLAY, cetvrti put pauza


def test_priced_popup_closed_with_free_x(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    game.extra_targets[(840, 70)] = "lobby"
    advisor = FakeAdvisor(AiProposal("tap", 840, 70, confidence=0.95, spends_resources=True,
                                     tap_is_free=True, screen="refill offer", reason="X"))
    assert _run(_pilot(game, screens, advisor, tmp_path)) == "finished"
    assert game.taps[0] == (840, 70)


def test_ai_scrolls_booster_list_then_gets_hint(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, start="unknown")
    game.after_swipe = "lobby"
    advisor = FakeAdvisor(AiProposal("scroll_down", 450, 800, confidence=0.9, tap_is_free=True))
    assert _run(_pilot(game, screens, advisor, tmp_path)) == "finished"
    assert game.swipes == [(450, 1150, 450, 450)]  # prst ide gore = lista ide dole
    assert "Get back to the lobby" in advisor.calls[0]["hint"]


def test_unlimited_games_until_stopped_by_no_boosters(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate)
    original = game.tap
    plays = {"n": 0}

    def tap(x, y):
        if game.screen == "mode_select":
            plays["n"] += 1
            if plays["n"] > 3:  # cetvrti put nema vise boostera: nepoznat ekran
                game.taps.append((x, y))
                game.screen = "unknown"
                return
        original(x, y)
        if game.screen == "searching":
            game.search_frames = 2  # svaka partija pocinje posle 2 slike

    game.tap = tap
    advisor = FakeAdvisor(AiProposal("pause", reason="no boosters left"))
    pilot = _pilot(game, screens, advisor, tmp_path, games_limit=0)
    result = _run(pilot)
    assert pilot.stats.games_done == 3
    assert result.startswith("paused") and "no boosters left" in result


def test_search_timeout_cancels_and_retries(screens, tmp_path):
    gate = dev.StopGate()
    game = FakeGame(gate, search_frames=10_000)
    pilot = _pilot(game, screens, FakeAdvisor(), tmp_path, search_timeout=0.05, search_retries=2)
    result = _run(pilot)
    assert "nije nadjen ni posle 3" in result
    assert game.taps.count((136, 72)) == 2
