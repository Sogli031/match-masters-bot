"""Offline provera pravila Autopilota na slikama -- bez ADB-a, bez klikova, bez API-ja.

    python tools/autopilot_check_screens.py            # sve referentne slike
    python tools/autopilot_check_screens.py D:/slike   # i slike iz foldera (ime = ocekivani ekran)

Svaka slika `<ekran>[__varijanta].png` mora da bude prepoznata kao <ekran>;
slika cije ime pocinje sa `unknown` mora da ostane neprepoznata.
Ispisuje i da li svaki ekran iz toka ima koordinate tapa koje mu trebaju.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autopilot import DEFAULT_FLOW  # noqa: E402
from autopilot_screens import SCREENS_DIR, ScreenClassifier  # noqa: E402


def check(folders: list[Path]) -> int:
    classifier = ScreenClassifier()
    failures = 0
    for folder in folders:
        for path in sorted(folder.glob("*.png")):
            expected = path.stem.split("__", 1)[0].lower()
            cls = classifier.classify(path)
            want_unknown = expected.startswith("unknown")
            ok = (cls.name is None) if want_unknown else (cls.name == expected)
            failures += 0 if ok else 1
            top = sorted(cls.scores.items(), key=lambda kv: -kv[1])[:3]
            print(f"{'OK ' if ok else 'GRESKA'} {path.name:32s} -> {cls.name or 'nepoznat':14s} "
                  + "  ".join(f"{n}={s:.2f}" for n, s in top))
    flow = dict(DEFAULT_FLOW)
    flow.update(classifier.config.get("flow", {}))
    for screen, step in flow.items():
        if "tap" not in step:
            continue
        if not classifier.has_tap(screen, step["tap"]):
            print(f"NEDOSTAJE tap '{step['tap']}' za ekran '{screen}'")
    print(f"\n{failures} gresaka")
    return 1 if failures else 0


if __name__ == "__main__":
    extra = [Path(p) for p in sys.argv[1:]]
    raise SystemExit(check([SCREENS_DIR, *extra]))
