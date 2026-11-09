"""Lokalno prepoznavanje ekrana za Autopilot (bez API poziva).

Referentne slike: `assets/autopilot/screens/<ekran>.png` ili
`<ekran>__<varijanta>.png` (npr. `results__win.png`, `results__loss.png`).
Ime fajla je ime ekrana.

Pravila: `data/autopilot_rules.json`. Za svaki ekran mogu da se zadaju
"sidra" -- pravougaonici u referentnoj slici koji su na tom ekranu uvek
isti (natpis, dugme). Sidro se trazi u novom screenshotu u okolini svog
mesta (`search` px) i mora da ima slicnost >= `min`. Ekran bez sidara se
poredi kao cela umanjena slika (grublje, dok sidra ne budu podesena).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
SCREENS_DIR = PROJECT_ROOT / "assets" / "autopilot" / "screens"
RULES_PATH = PROJECT_ROOT / "data" / "autopilot_rules.json"
REFERENCE_SIZE = (900, 1600)  # (sirina, visina) screencap-a Pie64_2
THUMB_SIZE = (45, 80)
DEFAULT_ANCHOR_MIN = 0.85
DEFAULT_THUMB_MIN = 0.93
DEFAULT_SEARCH = 16


def _to_bgr(image) -> np.ndarray:
    """PIL slika, putanja ili ndarray -> BGR uint8 u referentnoj velicini."""
    if isinstance(image, (str, Path)):
        data = np.fromfile(str(image), dtype=np.uint8)
        array = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if array is None:
            raise ValueError(f"Ne mogu da otvorim sliku {image}")
    elif isinstance(image, np.ndarray):
        array = image if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        array = array[:, :, :3]
    else:  # PIL
        array = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    if (array.shape[1], array.shape[0]) != REFERENCE_SIZE:
        array = cv2.resize(array, REFERENCE_SIZE, interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(array)


def _thumb(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, THUMB_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt((a * a).sum() * (b * b).sum()))
    if denom < 1e-6:
        # Obe ravne povrsine: iste ako su priblizno iste boje.
        return 1.0 if abs(float(a.mean()) - float(b.mean())) < 1e-3 else 0.0
    return float((a * b).sum() / denom)


@dataclass
class Anchor:
    box: tuple[int, int, int, int]
    template: np.ndarray
    min_score: float = DEFAULT_ANCHOR_MIN
    search: int = DEFAULT_SEARCH

    def locate(self, bgr: np.ndarray) -> tuple[int, int] | None:
        """Gornji levi ugao najboljeg pogotka po celom ekranu, ako prolazi prag."""
        result = np.nan_to_num(cv2.matchTemplate(bgr, self.template, cv2.TM_CCOEFF_NORMED), nan=0.0)
        _, best, _, (bx, by) = cv2.minMaxLoc(result)
        h, w = self.template.shape[:2]
        patch = bgr[by:by + h, bx:bx + w].astype(np.float32)
        diff = float(np.abs(patch.mean(axis=(0, 1)) - self.template.astype(np.float32).mean(axis=(0, 1))).max())
        if min(best, 1.0 - diff / 60.0) < self.min_score:
            return None
        return int(bx), int(by)

    def score(self, bgr: np.ndarray) -> float:
        x, y, w, h = self.box
        H, W = bgr.shape[:2]
        x0, y0 = max(0, x - self.search), max(0, y - self.search)
        x1, y1 = min(W, x + w + self.search), min(H, y + h + self.search)
        window = bgr[y0:y1, x0:x1]
        if window.shape[0] < h or window.shape[1] < w:
            return 0.0
        result = np.nan_to_num(cv2.matchTemplate(window, self.template, cv2.TM_CCOEFF_NORMED), nan=0.0)
        _, best, _, (bx, by) = cv2.minMaxLoc(result)
        patch = window[by:by + h, bx:bx + w].astype(np.float32)
        # Korelacija ne vidi osvetljenje: zatamnjen lobi iza popupa bi
        # prosao kao pravi. Prosecna boja mora da se slaze.
        diff = float(np.abs(patch.mean(axis=(0, 1)) - self.template.astype(np.float32).mean(axis=(0, 1))).max())
        color = max(0.0, 1.0 - diff / 60.0)
        if float(self.template.std()) < 2.0:
            return color  # jednobojno sidro: samo boja znaci nesto
        return float(min(best, color))


@dataclass
class ScreenRule:
    name: str
    anchors: list[Anchor] = field(default_factory=list)
    thumbs: list[np.ndarray] = field(default_factory=list)
    thumb_min: float = DEFAULT_THUMB_MIN
    taps: dict[str, tuple[int, int]] = field(default_factory=dict)
    # Dugmad koja se traze po celom ekranu (mesto zavisi od stanja igre).
    finds: dict[str, Anchor] = field(default_factory=dict)
    forbidden: bool = False
    note: str = ""
    # Drugi izgledi istog ekrana (`anchors_alt`): dovoljno je da prodje jedan skup.
    alt_anchors: list[list[Anchor]] = field(default_factory=list)

    def score(self, bgr: np.ndarray, thumb: np.ndarray) -> tuple[float, bool]:
        if self.anchors:
            best: tuple[float, bool] = (0.0, False)
            for group in [self.anchors, *self.alt_anchors]:
                scores = [anchor.score(bgr) for anchor in group]
                ok = all(s >= a.min_score for s, a in zip(scores, group))
                cand = (min(scores), ok)
                if (cand[1], cand[0]) > (best[1], best[0]):
                    best = cand
            return best
        if not self.thumbs:
            return 0.0, False
        best = max(_correlation(thumb, ref) for ref in self.thumbs)
        return best, best >= self.thumb_min


@dataclass
class Classification:
    name: str | None
    score: float
    scores: dict[str, float]
    forbidden: bool = False

    @property
    def known(self) -> bool:
        return self.name is not None


def reference_files(screens_dir: Path = SCREENS_DIR) -> dict[str, list[Path]]:
    """{ekran: [slike]} iz imena fajlova (`ime.png`, `ime__varijanta.png`)."""
    found: dict[str, list[Path]] = {}
    if not screens_dir.is_dir():
        return found
    for path in sorted(screens_dir.glob("*.png")):
        name = path.stem.split("__", 1)[0].strip().lower()
        if name and not name.startswith("unknown"):  # unknown* = primeri za proveru
            found.setdefault(name, []).append(path)
    return found


def load_rules_json(path: Path = RULES_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


class ScreenClassifier:
    def __init__(self, rules: dict | None = None, screens_dir: Path = SCREENS_DIR):
        self.config = load_rules_json() if rules is None else rules
        self.screens_dir = screens_dir
        self.rules: dict[str, ScreenRule] = {}
        self._build()

    def _build(self) -> None:
        files = reference_files(self.screens_dir)
        screens_cfg = self.config.get("screens", {})
        for name in sorted(set(files) | set(screens_cfg)):
            cfg = screens_cfg.get(name, {})
            paths = files.get(name, [])
            images = {p.name: _to_bgr(p) for p in paths}
            rule = ScreenRule(
                name=name,
                thumbs=[_thumb(img) for img in images.values()],
                thumb_min=float(cfg.get("thumb_min", DEFAULT_THUMB_MIN)),
                taps={k: (int(v[0]), int(v[1])) for k, v in cfg.get("taps", {}).items()
                      if not isinstance(v, dict)},
                forbidden=bool(cfg.get("forbidden", False)),
                note=str(cfg.get("note", "")),
            )
            def anchor(spec: dict) -> Anchor:
                ref_name = spec.get("ref") or (paths[0].name if paths else None)
                if ref_name not in images:
                    raise ValueError(f"Ekran '{name}': sidro trazi sliku {ref_name}, a nje nema u {self.screens_dir}")
                x, y, w, h = (int(v) for v in spec["box"])
                return Anchor(
                    box=(x, y, w, h),
                    template=np.ascontiguousarray(images[ref_name][y:y + h, x:x + w]),
                    min_score=float(spec.get("min", DEFAULT_ANCHOR_MIN)),
                    search=int(spec.get("search", DEFAULT_SEARCH)),
                )

            rule.anchors = [anchor(spec) for spec in cfg.get("anchors", [])]
            rule.alt_anchors = [[anchor(spec) for spec in group] for group in cfg.get("anchors_alt", [])]
            for tap_name, spec in cfg.get("taps", {}).items():
                if not isinstance(spec, dict):
                    continue
                ref_name = spec.get("ref") or (paths[0].name if paths else None)
                if ref_name not in images:
                    raise ValueError(f"Ekran '{name}': tap '{tap_name}' trazi sliku {ref_name}")
                x, y, w, h = (int(v) for v in spec["find"])
                rule.finds[tap_name] = Anchor(
                    box=(x, y, w, h),
                    template=np.ascontiguousarray(images[ref_name][y:y + h, x:x + w]),
                    min_score=float(spec.get("min", DEFAULT_ANCHOR_MIN)),
                    search=max(REFERENCE_SIZE),  # ceo ekran
                )
            self.rules[name] = rule

    @property
    def screen_names(self) -> list[str]:
        return sorted(self.rules)

    def has_tap(self, screen: str, tap: str) -> bool:
        rule = self.rules.get(screen)
        return rule is not None and (tap in rule.taps or tap in rule.finds)

    def tap_point(self, screen: str, tap: str, image=None) -> tuple[int, int] | None:
        """Fiksna tacka, ili centar dugmeta nadjenog na `image` (None ako ga nema)."""
        rule = self.rules.get(screen)
        if rule is None:
            return None
        if tap in rule.taps:
            return rule.taps[tap]
        anchor = rule.finds.get(tap)
        if anchor is None or image is None:
            return None
        found = anchor.locate(_to_bgr(image))
        if found is None:
            return None
        x, y = found
        return x + anchor.box[2] // 2, y + anchor.box[3] // 2

    def classify(self, image) -> Classification:
        bgr = _to_bgr(image)
        thumb = _thumb(bgr)
        scores: dict[str, float] = {}
        matched: list[tuple[float, str]] = []
        for name, rule in self.rules.items():
            score, ok = rule.score(bgr, thumb)
            scores[name] = round(score, 4)
            if ok:
                matched.append((score, name))
        if not matched:
            return Classification(None, max(scores.values(), default=0.0), scores)
        matched.sort(reverse=True)
        score, name = matched[0]
        return Classification(name, score, scores, forbidden=self.rules[name].forbidden)
