"""Capture one settled match to a portable, locally registered simulator package."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.dump_il2cpp_symbols import SymbolCollector, attach, DEFAULT_AGENT
from tools.matchmasters_board_reader import find_adb, discover_serial, ensure_frida_server, DEFAULT_PACKAGE
from simulator_capture import prepare_input, load_capture


def conflicting_readers():
    if os.name != "nt":
        raise RuntimeError("Preflight trenutno podrzava Windows; provera paralelnih readera nije dostupna")
    result = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\\.exe$' -or $_.Name -eq 'MatchMastersBot.exe' } | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
        capture_output=True, text=True, check=True)
    records = json.loads(result.stdout or "[]")
    if isinstance(records, dict):
        records = [records]
    names = ("memory_gui", "matchmasters_board_reader", "dump_il2cpp_symbols",
             "dump_engine_config", "capture_match")
    return [r["ProcessId"] for r in records if r["ProcessId"] != os.getpid()
            and (r.get("Name") == "MatchMastersBot.exe"
                 or any(name in (r.get("CommandLine") or "") for name in names))]


def save_package(profile, runtime, output):
    output.mkdir(parents=True, exist_ok=False)
    def write(name, payload):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write("profile.json", {"captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                           "runtime": runtime, **profile})
    prepared = prepare_input(profile)
    write("simulator_input.json", prepared)
    write("resolved_overrides.json", prepared["resolved_overrides"])
    issues = profile.get("issues", [])
    blockers = []
    for name in ("id", "pvpMode", "colorsCount", "boardSize"):
        if profile["rules"].get(name) is None:
            blockers.append("rules." + name)
    if prepared["local_player_index"] is None:
        blockers.append("local player identity")
    manifest = {"schema_version": 1, "rules_id": prepared["rules_id"],
                "capture_complete": not issues and not blockers,
                "unresolved": issues, "missing_required": blockers,
                "full_simulation_ready": False,
                "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                          for name in ("profile.json", "simulator_input.json", "resolved_overrides.json")},
                "agent_sha256": hashlib.sha256(DEFAULT_AGENT.read_bytes()).hexdigest()}
    write("manifest.json", manifest)
    (output / "README.txt").write_text(
        f"Rules: {prepared['rules_id']}\nUnresolved reads: {len(issues)}\n"
        "Load locally: python tools/capture_match.py --inspect PATH_TO_THIS_FOLDER\n"
        "Captured data is not certification that every mode is implemented.\n", encoding="utf-8")
    load_capture(output)  # verify portable input before registering it
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(output.iterdir()):
            package.write(path, path.name)
    registry = ROOT / "data/simulator_profiles"
    registry.mkdir(parents=True, exist_ok=True)
    reference = registry / (output.name + "_" + manifest["files"]["profile.json"][:12] + ".json")
    reference.write_text(json.dumps({"package": str(output.resolve()),
        "rules_id": prepared["rules_id"], "capture_complete": manifest["capture_complete"],
        "profile_sha256": manifest["files"]["profile.json"]}, indent=2), encoding="utf-8")
    return manifest, archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--inspect", type=Path, help="Read/verify saved package; no game connection")
    args = parser.parse_args(argv)
    if args.inspect:
        package = load_capture(args.inspect)
        print(json.dumps({"manifest": package["manifest"], "input": package["simulator_input"]}, ensure_ascii=False, indent=2))
        return 0
    conflicts = conflicting_readers()
    if conflicts:
        raise RuntimeError(f"Zatvori Memory GUI/reader ili drugi dumper pre capture-a. PID: {conflicts}")
    lock = ROOT / "Debug/match_capture.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"Capture lock postoji: {lock}; proveri da drugi capture nije aktivan") from None
    os.close(descriptor)
    session = script = None
    try:
        adb = find_adb()
        serial = discover_serial(adb, args.serial)
        ensure_frida_server(adb, serial)
        collector = SymbolCollector()
        print("Jednokratno citam partiju; ne povlaci poteze...", flush=True)
        _, session, script = attach(adb, serial, DEFAULT_PACKAGE, DEFAULT_AGENT, collector)
        profile = script.exports_sync.capture_match_profile()
        time.sleep(0.25)
        verification = script.exports_sync.capture_match_profile()
        for section in ("state", "rng", "rules", "players", "spawning"):
            if profile[section] != verification[section]:
                raise RuntimeError(f"Partija nije mirovala tokom dva citanja: {section}; probaj ponovo bez poteza")
        if profile["board"]["slots"] != verification["board"]["slots"]:
            raise RuntimeError("Tabla se promenila tokom citanja; sacekaj da se smiri")
        profile["consistency"] = {"repeated_reads_equal": True, "interval_seconds": 0.25,
                                  "checked": ["state", "rng", "rules", "players", "spawning", "board.slots"]}
        # Detach before filesystem/adaptation work; no poll or managed calls.
        script.unload()
        script = None
        session.detach()
        session = None
        output = args.out or ROOT / "Debug/match_captures" / dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        manifest, archive = save_package(profile, collector.meta, output)
        print(f"Mod: {manifest['rules_id']}\nFolder: {output}\nZIP: {archive}\n"
              f"Nerazresenih citanja: {len(manifest['unresolved'])}\nAgent odvojen; mozes da igras.", flush=True)
        return 0 if manifest["capture_complete"] else 2
    finally:
        try:
            if script is not None:
                script.unload()
        finally:
            if session is not None:
                session.detach()
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"GRESKA: {error}", file=sys.stderr)
        raise SystemExit(1)
