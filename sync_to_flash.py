# -*- coding: utf-8 -*-
"""Kopira ceo "memory gui" folder na fles -- bez ijednog izuzetka.

Podrazumevano odrediste je ``<fles>:\\memory gui``, gde se fles sam nalazi:
uzima se izmenjivi drajv sa najvise slobodnog prostora koji moze da primi ceo
folder. Slovo fleša se menja (E: pa D:), a Rufus boot particija istog fleša
ima 0 slobodno, pa fiksno slovo nije bezbedno. Rucno: ``--dest D:\\nesto``.

Skripta radi kao mirror: kopira sve nove/izmenjene fajlove, a visak na flesu
nudi za brisanje. Izvorni folder na C disku nikada ne menja.

Razlika u odnosu na sync iz velikog bot foldera: tamo se Debug, tests i test
fajlovi namerno preskacu jer bi paket bio ogroman. Ovde se NE preskace nista --
Debug logovi, snapshotovi, __pycache__, node_modules, sve ide. Folder je mali
(~13 MB), a Debug je ovde deo posla.

Primeri::

    python sync_to_flash.py             # pregled pa potvrda
    python sync_to_flash.py --list      # samo pregled
    python sync_to_flash.py --no-delete # samo dodaj/prepisi
    python sync_to_flash.py -y          # bez obicne potvrde
    python sync_to_flash.py --dest F:\\MemoryGUI

Ako je za brisanje vise od 50 fajlova, cak i uz -y mora rucno da se ukuca
OBRISI. To je zastita od pogresnog odredista. Sa --force-delete i to pitanje
se preskace (koristi BAT, koji salje -y --force-delete).
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import sys


SOURCE = Path(__file__).resolve().parent
DEST_FOLDER_NAME = "memory gui"
MTIME_TOLERANCE = 2.0
DELETE_CONFIRM_LIMIT = 50
PREVIEW_LIMIT = 80
PRESERVED_DEST_PREFIXES = (".lan_control/",)


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value):,} {unit}"
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"


def normalized_rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def source_file_map(source: Path) -> dict[str, Path]:
    """Vrati rel_path -> source Path za SVAKI fajl u folderu, bez izuzetaka."""
    selected: dict[str, Path] = {}
    for path in source.rglob("*"):
        if path.is_file():
            selected[normalized_rel(path, source)] = path
    return selected


def validate_source(source: Path, selected: dict[str, Path]) -> None:
    """Markeri su fajlovi bez kojih memorijski GUI ne postoji."""
    markers = (
        "memory_gui.py",
        "runtime.py",
        "move_strategy.py",
        "board_source.py",
        "tools/matchmasters_board_reader.py",
        "tools/matchmasters_board_dump.js",
    )
    missing_markers = [name for name in markers if not (source / name).is_file()]
    missing_selected = [name for name in markers if name not in selected]
    if missing_markers or missing_selected:
        print("\nGRESKA: Izvor nije kompletan 'memory gui' folder.")
        if missing_markers:
            print("Nedostaju markeri:", ", ".join(missing_markers))
        if missing_selected:
            print("Markeri su greskom iskljuceni:", ", ".join(missing_selected))
        print("Nista nije dirano.")
        raise SystemExit(1)


def removable_drives() -> list[tuple[Path, int]]:
    """Removable drives Windows currently sees, as (root, free bytes).

    Only DRIVE_REMOVABLE counts: fixed disks and DVDs are never a flash
    stick, and a Rufus boot partition (tiny, zero free) is filtered out by
    the caller through the free-space requirement.
    """
    import ctypes
    import string

    drives: list[tuple[Path, int]] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(root) != 2:  # DRIVE_REMOVABLE
            continue
        try:
            free = shutil.disk_usage(root).free
        except OSError:
            continue
        drives.append((Path(root), free))
    return drives


def pick_destination(needed_bytes: int) -> Path:
    """The removable drive with the most free space that fits the folder.

    Flash letters change between reboots and USB ports (E: one day, D: the
    next), so a hardcoded default silently targets the wrong stick or a boot
    partition with zero free space. Pass --dest to override.
    """
    drives = removable_drives()
    if not drives:
        raise SystemExit("GRESKA: Nijedan fles (izmenjivi drajv) nije prikljucen.")
    fitting = [(root, free) for root, free in drives if free >= needed_bytes]
    if not fitting:
        listing = ", ".join(f"{root} ({human(free)} slobodno)" for root, free in drives)
        raise SystemExit(
            f"GRESKA: Nijedan fles nema {human(needed_bytes)} slobodno: {listing}"
        )
    fitting.sort(key=lambda item: item[1], reverse=True)
    return fitting[0][0] / DEST_FOLDER_NAME


def validate_destination(source: Path, dest: Path) -> None:
    source_abs = os.path.normcase(os.path.abspath(source))
    dest_abs = os.path.normcase(os.path.abspath(dest))
    if dest_abs == source_abs:
        raise SystemExit("GRESKA: Izvor i odrediste su isti. Nista nije dirano.")

    drive, tail = os.path.splitdrive(dest_abs)
    if not drive or not os.path.isdir(drive + os.sep):
        raise SystemExit(
            f"GRESKA: Drajv odredista nije dostupan: {drive or dest}. "
            "Da li je fles ukljucen?"
        )
    if tail.strip("\\/") == "":
        raise SystemExit("GRESKA: Odrediste ne sme biti koren drajva.")


def sha1(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def files_differ(source: Path, dest: Path) -> bool:
    source_stat = source.stat()
    dest_stat = dest.stat()
    if source_stat.st_size != dest_stat.st_size:
        return True
    if abs(source_stat.st_mtime - dest_stat.st_mtime) <= MTIME_TOLERANCE:
        return False
    return sha1(source) != sha1(dest)


def scan(selected: dict[str, Path], dest: Path):
    changed: list[tuple[str, str, int]] = []
    to_delete: list[tuple[str, int]] = []

    for rel, source_path in selected.items():
        dest_path = dest / Path(rel)
        try:
            if not dest_path.is_file():
                changed.append((rel, "NOV", source_path.stat().st_size))
            elif files_differ(source_path, dest_path):
                changed.append((rel, "IZMENJEN", source_path.stat().st_size))
        except (OSError, PermissionError) as exc:
            print(f"  ! Preskocen zbog greske citanja: {rel} ({exc})")

    if dest.is_dir():
        for path in dest.rglob("*"):
            if not path.is_file():
                continue
            rel = normalized_rel(path, dest)
            if rel.startswith(PRESERVED_DEST_PREFIXES):
                continue
            if rel not in selected:
                try:
                    size = path.stat().st_size
                except OSError:
                    size = 0
                to_delete.append((rel, size))

    changed.sort(key=lambda item: item[0].lower())
    to_delete.sort(key=lambda item: item[0].lower())
    return changed, to_delete


def group_summary(items: list[tuple], *, path_index: int = 0) -> list[tuple[str, int, int]]:
    groups: dict[str, list[int]] = {}
    for item in items:
        rel = item[path_index]
        top = rel.split("/", 1)[0]
        size = int(item[-1])
        values = groups.setdefault(top, [0, 0])
        values[0] += 1
        values[1] += size
    return sorted(
        ((name, count_size[0], count_size[1]) for name, count_size in groups.items()),
        key=lambda row: (-row[2], row[0].lower()),
    )


def print_items(title: str, items: list[tuple], *, verbose: bool) -> None:
    if not items:
        return
    print(f"\n{title} ({len(items)}):")
    limit = len(items) if verbose else min(len(items), PREVIEW_LIMIT)
    for item in items[:limit]:
        if len(item) == 3:
            rel, status, size = item
            print(f"  {status:<9} {human(size):>11}  {rel}")
        else:
            rel, size = item
            print(f"  {'BRISI':<9} {human(size):>11}  {rel}")
    if limit < len(items):
        print(f"  ... jos {len(items) - limit} fajlova (koristi --verbose za pun spisak)")

    if len(items) > PREVIEW_LIMIT:
        print("\n  Pregled po glavnom folderu:")
        for name, count, size in group_summary(items):
            print(f"    {name:<48} {count:>6} fajl.  {human(size):>11}")


def remove_empty_dirs(dest: Path) -> int:
    removed = 0
    if not dest.is_dir():
        return removed
    directories = sorted(
        (path for path in dest.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
                removed += 1
        except OSError:
            pass
    return removed


def mirror_empty_dirs(source: Path, dest: Path) -> int:
    """Prazan folder nema fajl koji bi ga povukao, a ovde je deo strukture
    (Debug\\memory_board pre prve partije). Zato se pravi rucno."""
    created = 0
    for path in source.rglob("*"):
        if not path.is_dir() or any(path.iterdir()):
            continue
        target = dest / path.relative_to(source)
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
                created += 1
            except OSError:
                pass
    return created


def do_sync(
    source: Path,
    selected: dict[str, Path],
    dest: Path,
    changed: list[tuple[str, str, int]],
    to_delete: list[tuple[str, int]],
) -> bool:
    copied = copy_failed = deleted = delete_failed = 0
    dest.mkdir(parents=True, exist_ok=True)

    for rel, _status, _size in changed:
        source_path = selected[rel]
        dest_path = dest / Path(rel)
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            copied += 1
            print(f"  OK         {rel}")
        except Exception as exc:
            copy_failed += 1
            print(f"  GRESKA     {rel} ({exc})")

    for rel, _size in to_delete:
        dest_path = dest / Path(rel)
        try:
            dest_path.unlink()
            deleted += 1
            if len(to_delete) <= PREVIEW_LIMIT:
                print(f"  OBRISAN    {rel}")
        except Exception as exc:
            delete_failed += 1
            print(f"  GRESKA bri {rel} ({exc})")

    removed_dirs = remove_empty_dirs(dest) if to_delete else 0
    created_dirs = mirror_empty_dirs(source, dest)
    print("\nRezultat:")
    print(f"  Kopirano: {copied}; neuspesno: {copy_failed}")
    print(f"  Obrisano: {deleted}; neuspesno: {delete_failed}; praznih foldera: {removed_dirs}")
    if created_dirs:
        print(f"  Napravljeno praznih foldera na odredistu: {created_dirs}")
    return copy_failed == 0 and delete_failed == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror Match Masters Bot foldera bez Debug foldera i testova."
    )
    parser.add_argument("-y", "--yes", action="store_true", help="sync bez obicne potvrde")
    parser.add_argument(
        "--force-delete",
        action="store_true",
        help="dozvoli veliko brisanje bez kucanja OBRISI",
    )
    parser.add_argument("--list", action="store_true", help="samo prikazi razlike")
    parser.add_argument("--no-delete", action="store_true", help="ne brisi visak sa flesa")
    parser.add_argument("--verbose", action="store_true", help="prikazi svaki fajl")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help=f"odrediste (default: <fles>:\\{DEST_FOLDER_NAME}, fles se sam nalazi)",
    )
    args = parser.parse_args()

    source = SOURCE
    selected = source_file_map(source)
    validate_source(source, selected)
    total_source_size = sum(path.stat().st_size for path in selected.values())
    dest = args.dest if args.dest is not None else pick_destination(total_source_size)
    validate_destination(source, dest)
    print("=" * 72)
    print(" MEMORY GUI -> SYNC (ceo folder, bez izuzetaka)")
    print("=" * 72)
    print(f" Izvor:       {source}")
    print(f" Odrediste:   {dest}")
    print(f" Za sync:     {len(selected)} fajlova, {human(total_source_size)}")
    print(" Iskljuceno:  nista -- ide i Debug, i __pycache__, i node_modules")
    print("=" * 72)
    print("\nPoredim fajlove...")

    changed, to_delete = scan(selected, dest)
    if args.no_delete:
        to_delete = []

    if not changed and not to_delete:
        print("\nSve je vec sinhronizovano. Nema razlika.")
        mirror_empty_dirs(source, dest)
        return 0

    print_items("ZA KOPIRANJE", changed, verbose=args.verbose)
    print_items("ZA BRISANJE SA ODREDISTA", to_delete, verbose=args.verbose)
    print(f"\nUkupno kopiranje: {len(changed)} fajlova, {human(sum(x[2] for x in changed))}")
    print(f"Ukupno brisanje:  {len(to_delete)} fajlova, {human(sum(x[1] for x in to_delete))}")

    if args.list:
        print("\n[--list] Samo pregled; nista nije promenjeno.")
        return 0

    if len(to_delete) > DELETE_CONFIRM_LIMIT:
        print(
            f"\nUPOZORENJE: {len(to_delete)} fajlova je za brisanje sa odredista."
        )
        if args.force_delete:
            print("[--force-delete] Brisanje se izvrsava bez pitanja.")
        else:
            answer = input("Ukucaj OBRISI da dozvolis ciscenje, ili Enter da ga preskocis: ").strip()
            if answer != "OBRISI":
                print("Brisanje je preskoceno; radi se samo kopiranje.")
                to_delete = []

    if not args.yes:
        answer = input("\nPokreni kopiranje na odrediste? [d/da/y = da]: ").strip().lower()
        if answer not in {"d", "da", "y", "yes"}:
            print("Otkazano. Nista nije promenjeno.")
            return 0
    else:
        print("\n[-y] Pokrecem bez obicne potvrde...")

    print()
    return 0 if do_sync(source, selected, dest, changed, to_delete) else 1


if __name__ == "__main__":
    raise SystemExit(main())
