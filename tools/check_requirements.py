"""Check -- and optionally repair -- the pinned dependencies of a project.

``python_for_windows.bat`` already knows how to install Python itself when it is
missing. This is the same idea one level up: it answers "are the libraries
there, and are they the pinned versions?" and, with ``--install``, makes them so.

Presence and versions are read from installed package metadata, which is fast
enough to run on every launch. The slower ``--verify-imports`` pass actually
imports each package and is meant to run *after* a repair, to prove the fix
took (a half-written opencv or PyQt5 installs cleanly but fails to import).

Usage::

    python tools/check_requirements.py requirements.txt
    python tools/check_requirements.py requirements.txt --install
    python tools/check_requirements.py requirements.txt --verify-imports

Exit code 0 means every requirement is satisfied; 1 means something is missing,
mismatched or broken -- and under ``--install``, that pip could not fix it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

# Redosled je bitan: prvo se skida ono sto ostali paketi koriste kao osnovu.
REQUIREMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*"
    r"(?P<spec>(?:[<>=!~]=?\s*[^,;\s]+\s*,?\s*)*)$"
)


def canonical(name: str) -> str:
    """PEP 503 ime paketa: 'opencv-python', 'Opencv_Python' i 'opencv.python' su isto."""
    return re.sub(r"[-_.]+", "-", name).lower()


def version_key(version: str) -> tuple[int, ...]:
    """Gruba zamena za packaging.version kad ga nema -- dovoljna za '4.13.0.92'."""
    return tuple(int(part) for part in re.findall(r"\d+", version)) or (0,)


def compare_versions(have: str, want: str) -> int:
    """-1 ako je instalirana starija, 1 ako je novija, 0 ako su iste."""
    try:
        from packaging.version import Version

        left, right = Version(have), Version(want)
    except Exception:
        left, right = version_key(have), version_key(want)

    if left < right:
        return -1
    return 1 if left > right else 0


class Requirement:
    """Jedan red iz requirements fajla, sveden na ono sto nam treba."""

    def __init__(self, raw: str, name: str, pinned: str | None) -> None:
        self.raw = raw
        self.name = name
        self.pinned = pinned

    def __repr__(self) -> str:  # pragma: no cover - samo za debug
        return f"Requirement({self.raw!r})"


def parse_requirements(path: Path) -> list[Requirement]:
    """Cita requirements fajl. Podrzava i ugnjezdene '-r drugi.txt' redove."""
    requirements: list[Requirement] = []
    seen: set[str] = set()

    # utf-8-sig: bez toga BOM zalepljen na prvi red pojede prvi paket u fajlu.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue

        # '-r requirements-runtime.txt' -- ubaci i njegov sadrzaj.
        include = re.match(r"^-r\s+(.+)$", line)
        if include:
            nested = (path.parent / include.group(1).strip()).resolve()
            if nested.exists():
                for nested_req in parse_requirements(nested):
                    if canonical(nested_req.name) not in seen:
                        seen.add(canonical(nested_req.name))
                        requirements.append(nested_req)
            continue

        if line.startswith("-"):
            continue  # ostale pip opcije nas se ne ticu

        line = line.split(";", 1)[0].strip()  # environment marker
        match = REQUIREMENT_RE.match(line)
        if not match:
            continue

        name = match.group("name")
        if canonical(name) in seen:
            continue

        spec = (match.group("spec") or "").strip().rstrip(",")
        pin = re.match(r"^==\s*([^,\s]+)$", spec)
        seen.add(canonical(name))
        requirements.append(Requirement(line, name, pin.group(1) if pin else None))

    return requirements


def installed_versions() -> dict[str, str]:
    """Mapa kanonsko-ime -> instalirana verzija, procitana iz metapodataka."""
    versions: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            versions[canonical(name)] = dist.version or ""
    return versions


def top_level_modules(name: str) -> list[str]:
    """Moduli koje paket zapravo instalira (iz top_level.txt), za import test."""
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return []

    text = dist.read_text("top_level.txt") or ""
    modules = [line.strip() for line in text.splitlines() if line.strip()]
    if modules:
        return modules
    return [canonical(name).replace("-", "_")]


def check(requirements: list[Requirement]) -> list[tuple[Requirement, str, str]]:
    """Vraca listu problema: (requirement, razlog, opis za korisnika)."""
    versions = installed_versions()
    problems: list[tuple[Requirement, str, str]] = []

    for req in requirements:
        have = versions.get(canonical(req.name))

        if have is None:
            pin = f" ({req.pinned})" if req.pinned else ""
            problems.append((req, "missing", f"{req.name}: nije instaliran{pin}"))
            continue

        if not req.pinned or have == req.pinned:
            continue

        # Projekat je testiran na zakucanoj verziji, pa je i vracanje unazad
        # ispravan ishod -- zato se smer kaze naglas pre nego sto se bilo sta dira.
        direction = "DOWNGRADE" if compare_versions(have, req.pinned) > 0 else "UPGRADE"
        problems.append(
            (
                req,
                direction.lower(),
                f"{req.name}: instaliran {have}, projekat trazi {req.pinned}"
                f"  ->  {direction}",
            )
        )

    return problems


def check_imports(requirements: list[Requirement]) -> list[str]:
    """Stvarno uvozi pakete -- hvata instalacije koje 'postoje' ali su polomljene."""
    broken: list[str] = []

    for req in requirements:
        for module in top_level_modules(req.name):
            if module.startswith("_") or module in {"tests", "test"}:
                continue
            try:
                __import__(module)
            except Exception as error:  # DLL-ovi umeju da puknu na razne nacine
                broken.append(f"{req.name}: 'import {module}' puca ({error})")
                break

    return broken


def pip_install(specs: list[str]) -> bool:
    """Instalira/popravlja samo problematicne pakete, ne ceo requirements fajl."""
    try:
        import pip  # noqa: F401
    except ImportError:
        print("pip nije dostupan, pokusavam ensurepip...", flush=True)
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False)

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        *specs,
    ]
    print("Pokrecem: " + " ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", help="putanja do requirements .txt fajla")
    parser.add_argument(
        "--install",
        action="store_true",
        help="instaliraj/popravi ono sto fali umesto samo prijave",
    )
    parser.add_argument(
        "--verify-imports",
        action="store_true",
        help="posle provere verzija stvarno uvezi pakete (sporije)",
    )
    args = parser.parse_args(argv)

    path = Path(args.requirements).resolve()
    if not path.exists():
        print(f"GRESKA: nema requirements fajla: {path}")
        return 1

    requirements = parse_requirements(path)
    if not requirements:
        print(f"Upozorenje: {path.name} nema nijedan paket.")
        return 0

    problems = check(requirements)

    if problems:
        print(f"Biblioteke ne odgovaraju projektu ({path.name}):")
        for _req, _reason, message in problems:
            print(f"  - {message}")

        counts = {"missing": 0, "downgrade": 0, "upgrade": 0}
        for _req, reason, _message in problems:
            counts[reason] = counts.get(reason, 0) + 1
        summary = [
            f"{counts['missing']} za instalaciju",
            f"{counts['downgrade']} za vracanje na stariju verziju",
            f"{counts['upgrade']} za novu verziju",
        ]
        print("\nUkupno: " + ", ".join(part for part in summary if not part.startswith("0 ")))

        if not args.install:
            return 1

        print()
        if not pip_install([req.raw for req, _reason, _message in problems]):
            print("GRESKA: pip nije uspeo da instalira sve sto treba.")
            return 1

        problems = check(requirements)
        if problems:
            print("GRESKA: i posle instalacije nesto i dalje ne valja:")
            for _req, _reason, message in problems:
                print(f"  - {message}")
            return 1

        print("Biblioteke su instalirane.")

    if args.verify_imports:
        broken = check_imports(requirements)
        if broken:
            print("Instalirane su, ali se ne ucitavaju:")
            for message in broken:
                print(f"  - {message}")
            return 1

    if not problems:
        print(f"Sve biblioteke iz {path.name} su na mestu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
