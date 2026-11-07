"""Receive read-only Match Masters 7x7 board snapshots from Frida/IL2CPP."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    import frida
except ImportError:  # pragma: no cover - exercised by the CLI error path
    frida = None

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import board_source
from move_strategy import (
    BLOCKED,
    BLUE,
    CHEST,
    DISCO_BALL,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    WHITE,
    YELLOW,
)


DEFAULT_SERIAL = "127.0.0.1:5555"
FORBIDDEN_SERIALS = frozenset({"127.0.0.1:5695", "emulator-5554"})
# How soon an online serial that failed the Pie64 identity check is checked
# again during discovery (see `discover_serial`).
DISCOVERY_REPROBE_SECONDS = 3.0
DEFAULT_PACKAGE = "com.funtomic.matchmasters"
DEFAULT_AGENT = Path(__file__).with_name("matchmasters_board_dump.js")
DEFAULT_OUTPUT = PROJECT_ROOT / "Debug" / "memory_board" / "board_snapshots.jsonl"
DEFAULT_LATEST = PROJECT_ROOT / "Debug" / "memory_board" / "latest.json"
# Where the GUI records the matches the agent saw end for good, per game
# process ({"pid": ..., "keys": [...]}; memory_gui.remember_dead_logic). The
# CLI only reads it; the GUI owns it.
DEAD_LOGICS_PATH = PROJECT_ROOT / "Debug" / "memory_board" / "dead_logics.json"
DEAD_LOGICS_MAX = 32
# CLI loop: how long to back off after `game_pid` fails (adb "device offline",
# a timeout), doubling per failure up to the cap.
PID_POLL_BACKOFF_BASE = 1.0
PID_POLL_BACKOFF_MAX = 10.0
FRIDA_SERVER_PATH = "/data/local/tmp/frida-server"
FRIDA_PORT = 27042

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ReaderError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    timeout: float = 15.0,
    check: bool = False,
    text: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=check,
            creationflags=_CREATE_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise ReaderError(f"Komanda nije pronadjena: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ReaderError(f"Komanda je istekla: {' '.join(args[:4])}") from exc


def _adb_candidates() -> list[Path]:
    """Places adb realistically ends up in on this machine, best first."""
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "Android" / "Sdk" / "platform-tools" / "adb.exe",
        # APK Builder drops platform-tools here when Android Studio is absent.
        local / "APKBuilder" / "platform-tools" / "adb.exe",
    ]
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "platform-tools" / "adb.exe")
    # Last resort: BlueStacks ships its own adb (v36). On a fresh Windows
    # install nothing else exists, and it drove the whole 2026-09-12 setup
    # (push, forward, shell) without issue.
    candidates.append(Path(r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"))
    return candidates


def find_adb() -> str:
    """Locate adb, on PATH or in the usual platform-tools folders.

    ``shutil.which`` on its own was too strict: a platform-tools install that
    never touched PATH is still perfectly usable, and that is the normal state
    of things when Android Studio was never run. Anything found off PATH is
    put *on* PATH, so child processes and later lookups agree on one adb.
    """
    adb = shutil.which("adb")
    if adb:
        return adb

    for candidate in _adb_candidates():
        if not candidate.is_file():
            continue
        folder = str(candidate.parent)
        path = os.environ.get("PATH", "")
        if folder not in path.split(os.pathsep):
            os.environ["PATH"] = folder + os.pathsep + path
        return str(candidate)

    searched = "\n  ".join(str(candidate) for candidate in _adb_candidates())
    raise ReaderError(
        "adb nije pronadjen -- ni na PATH-u, ni na poznatim lokacijama:\n  " + searched
    )


def _ensure_adb_server(adb: str) -> None:
    """Start the adb daemon without letting it hold our pipes open.

    The daemon the first command spawns inherits whatever stdout/stderr it was
    given, so a captured `adb connect` waits for a *daemon* that never exits and
    hits the timeout even though the connect itself succeeded. Handing the
    start-server call the null device keeps that fork off our pipes.
    """
    try:
        subprocess.run(
            [adb, "start-server"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25.0,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        # Not fatal: `adb devices` below starts the daemon too, and reports the
        # real problem if adb is broken.
        pass


def _adb_connect(adb: str, serial: str) -> None:
    """Nudge adb towards a port; failure and slowness are both acceptable.

    Connecting only *adds* a transport -- the `adb devices` listing is what
    discovery actually reads -- so a refused or hung connect must not end the
    search. On 2026-08-17 a 10s timeout on the default port aborted the whole
    attach while the instance was reachable the entire time.
    """
    try:
        _run([adb, "connect", serial], timeout=10.0)
    except ReaderError:
        pass


def parse_adb_devices(output: str) -> dict[str, str]:
    devices: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        devices[parts[0]] = parts[1]
    return devices


def _instance_identity(adb: str, serial: str) -> tuple[str, str, bool] | None:
    """(android release, cpu abi, game installed) for a serial, or None."""
    return _instance_identity_or_reason(adb, serial)[0]


def _instance_identity_or_reason(
    adb: str, serial: str
) -> tuple[tuple[str, str, bool] | None, str]:
    """The identity, or None with what went wrong (for the final error)."""
    try:
        release = adb_shell(adb, serial, "getprop ro.build.version.release", timeout=8.0)
        abi = adb_shell(adb, serial, "getprop ro.product.cpu.abi", timeout=8.0)
        packages = adb_shell(
            adb, serial, f"pm list packages {DEFAULT_PACKAGE}", timeout=10.0
        )
    except ReaderError as exc:
        return None, str(exc)
    return (release.strip(), abi.strip(), DEFAULT_PACKAGE in packages), ""


def _pie64_check(adb: str, serial: str) -> tuple[bool, str]:
    """`is_pie64_instance` plus why not, so a failed discovery can say it."""
    identity, reason = _instance_identity_or_reason(adb, serial)
    if identity is None:
        return False, reason or "adb shell nije odgovorio"
    release, abi, has_game = identity
    if not release.startswith("9") or "64" not in abi:
        return False, f"Android {release or '?'} / {abi or '?'} nije Pie64"
    if not has_game:
        return False, "igra nije (jos) vidljiva u pm list packages"
    return True, ""


def is_pie64_instance(adb: str, serial: str) -> bool:
    """Whether this serial is the Pie64 instance the reader is built for.

    Identity, not port number: BlueStacks hands each running instance the next
    free port (5555, 5556, ...), so a restart or a second instance moves the
    game to a port the reader never asked for -- which is exactly what happened
    on 2026-08-17, with a dead transport left holding 5555 as "offline". The
    rail this replaces existed to keep the reader off the *wrong* instance, and
    that is still enforced here: Android 9, 64-bit, with the game installed.
    """
    identity = _instance_identity(adb, serial)
    if identity is None:
        return False
    release, abi, has_game = identity
    return release.startswith("9") and "64" in abi and has_game


def bluestacks_conf_serials() -> list[str]:
    """Loopback serials for every instance BlueStacks lists in its own conf.

    BlueStacks records the port it handed each instance in
    `bst.instance.<name>.status.adb_port`, and that is the only place the real
    number appears: a second instance lands far from the default (Pie64_2 came
    up on 5575, then 5576, then 5577 across reboots), so knocking on the
    default port's immediate neighbours never reaches it. Missing conf or
    unreadable file is not an error -- discovery falls back to probing.
    """
    conf = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    conf = conf / "BlueStacks_nxt" / "bluestacks.conf"
    try:
        text = conf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    serials: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if not key.startswith("bst.instance.") or not key.endswith(".status.adb_port"):
            continue
        port = value.strip().strip('"')
        if port.isdigit():
            serial = f"127.0.0.1:{port}"
            if serial not in serials:
                serials.append(serial)
    return serials


def _candidate_serials(devices: dict[str, str]) -> list[str]:
    """Online loopback serials worth probing, the default port first."""
    candidates = [
        serial
        for serial, state in devices.items()
        if state == "device"
        and serial not in FORBIDDEN_SERIALS
        and serial.startswith("127.0.0.1:")
    ]
    candidates.sort(key=lambda serial: (serial != DEFAULT_SERIAL, serial))
    return candidates


def discover_serial(
    adb: str, requested: str | None = None, *, timeout: float = 45.0
) -> str:
    """The Pie64 instance's serial, whatever port BlueStacks put it on.

    An explicit `requested` serial is honoured (it is how the caller pins one
    instance), but it still has to pass the identity check.
    """
    if requested and requested in FORBIDDEN_SERIALS:
        raise ReaderError(f"Zabranjena/pogresna instanca: {requested}")

    # The default port first: connecting is what turns a listening BlueStacks
    # instance into an adb device in the first place.
    _ensure_adb_server(adb)
    known = [requested or DEFAULT_SERIAL, DEFAULT_SERIAL, *bluestacks_conf_serials()]
    for serial in dict.fromkeys(known):
        if serial not in FORBIDDEN_SERIALS:
            _adb_connect(adb, serial)
    deadline = time.monotonic() + timeout
    last_devices: dict[str, str] = {}
    # serial -> when it may be probed again. A failed identity check is retried
    # rather than written off: the check is three adb shell calls, and one of
    # them timing out or `pm list` answering empty while the instance is still
    # settling used to mark a perfectly good 127.0.0.1:5555 as "not Pie64" for
    # the rest of the 45 s -- the attach then failed with the device listed
    # as online in its own error, and the next attempt went straight through.
    next_probe: dict[str, float] = {}
    probe_reasons: dict[str, str] = {}
    while time.monotonic() < deadline:
        completed = _run([adb, "devices"], timeout=10.0)
        last_devices = parse_adb_devices(completed.stdout or "")
        if requested:
            if last_devices.get(requested) == "device":
                if is_pie64_instance(adb, requested):
                    return requested
                raise ReaderError(
                    f"{requested} nije Pie64 instanca sa igrom; ne kacim se na nju"
                )
        else:
            now = time.monotonic()
            for serial in _candidate_serials(last_devices):
                if now < next_probe.get(serial, 0.0):
                    continue
                ok, reason = _pie64_check(adb, serial)
                if ok:
                    return serial
                probe_reasons[serial] = reason
                next_probe[serial] = time.monotonic() + DISCOVERY_REPROBE_SECONDS
            # A port BlueStacks opened but adb has never been told about shows
            # up nowhere in `adb devices`, so knock on the neighbours of the
            # default port once the known ones are exhausted.
            if not next_probe:
                base_host, _, base_port = DEFAULT_SERIAL.rpartition(":")
                for offset in range(1, 5):
                    _adb_connect(adb, f"{base_host}:{int(base_port) + offset}")
        online_wrong = [
            value for value in FORBIDDEN_SERIALS if last_devices.get(value) == "device"
        ]
        if online_wrong and not _candidate_serials(last_devices):
            raise ReaderError(
                "Aktivna je pogresna instanca "
                + ", ".join(sorted(online_wrong))
                + "; pokreni Pie64 (BlueStacks) instancu sa igrom"
            )
        time.sleep(1.0)
    why = "; ".join(f"{serial}: {reason}" for serial, reason in probe_reasons.items())
    raise ReaderError(
        "Pie64 instanca sa igrom nije postala dostupna; "
        f"adb={last_devices or 'nema uredjaja'}"
        + (f"; provera: {why}" if why else "")
    )


def adb_shell(adb: str, serial: str, command: str, *, timeout: float = 15.0) -> str:
    completed = _run([adb, "-s", serial, "shell", command], timeout=timeout)
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode != 0:
        raise ReaderError(f"ADB shell greska ({completed.returncode}): {output}")
    return output


def ensure_frida_server(adb: str, serial: str) -> None:
    if frida is None:
        raise ReaderError("Python paket frida nije instaliran")
    # A missing binary exits 127, which `adb_shell` would surface as a bare
    # "ADB shell greska (127)" -- useless on a freshly prepared instance, where
    # a not-yet-copied frida-server is the likeliest reason to be here at all.
    try:
        remote_version = adb_shell(
            adb,
            serial,
            f"su -c '{FRIDA_SERVER_PATH} --version 2>/dev/null'",
        ).splitlines()
    except ReaderError:
        remote_version = []
    if not remote_version:
        raise ReaderError(
            f"Nema izvrsnog {FRIDA_SERVER_PATH} na {serial}; "
            f"kopiraj frida-server {frida.__version__} (android-x86_64) tamo"
        )
    remote_version_value = remote_version[-1].strip()
    if remote_version_value != frida.__version__:
        raise ReaderError(
            f"Frida verzije se ne poklapaju: host={frida.__version__}, "
            f"server={remote_version_value}"
        )

    processes = adb_shell(adb, serial, "su -c 'pidof frida-server || true'")
    if not processes.strip():
        adb_shell(
            adb,
            serial,
            "su -c 'chmod 755 /data/local/tmp/frida-server; "
            "nohup /data/local/tmp/frida-server "
            ">/data/local/tmp/frida-server.log 2>&1 &'",
        )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if adb_shell(adb, serial, "su -c 'pidof frida-server || true'").strip():
                break
            time.sleep(0.25)
        else:
            log = adb_shell(
                adb,
                serial,
                "su -c 'tail -n 20 /data/local/tmp/frida-server.log 2>/dev/null || true'",
            )
            raise ReaderError(f"frida-server se nije pokrenuo: {log}")

    forwarded = _run(
        [adb, "-s", serial, "forward", f"tcp:{FRIDA_PORT}", f"tcp:{FRIDA_PORT}"],
        timeout=10.0,
    )
    if forwarded.returncode != 0:
        raise ReaderError((forwarded.stderr or forwarded.stdout or "adb forward failed").strip())


def restart_frida_server(adb: str, serial: str, *, timeout: float = 8.0) -> str:
    """Kill frida-server and bring it back up, returning the new PID.

    This is the cheap half of recovery: it drops every session the server was
    holding, which is what a GUI killed mid-attach leaves behind.
    """
    adb_shell(adb, serial, "su -c 'pkill -9 frida-server || true'")
    time.sleep(1.5)
    adb_shell(
        adb,
        serial,
        "su -c 'chmod 755 /data/local/tmp/frida-server; "
        "nohup /data/local/tmp/frida-server "
        ">/data/local/tmp/frida-server.log 2>&1 &'",
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = adb_shell(adb, serial, "su -c 'pidof frida-server || true'").strip()
        if pid:
            _run([adb, "-s", serial, "forward", f"tcp:{FRIDA_PORT}", f"tcp:{FRIDA_PORT}"], timeout=10.0)
            return pid
        time.sleep(0.25)
    log = adb_shell(
        adb,
        serial,
        "su -c 'tail -n 20 /data/local/tmp/frida-server.log 2>/dev/null || true'",
    )
    raise ReaderError(f"frida-server se nije podigao: {log}")


def restart_game(adb: str, serial: str, package: str, *, timeout: float = 60.0) -> int:
    """Force-stop the game and start it again, returning the new PID.

    The expensive half of recovery, and the one that usually removes the need
    to restart BlueStacks itself: a process still holding a stale agent, or one
    frida left with suspended threads, is fixed by a new process -- the whole
    emulator does not have to go.
    """
    adb_shell(adb, serial, f"am force-stop {package}", timeout=20.0)
    time.sleep(1.0)
    adb_shell(
        adb,
        serial,
        f"monkey -p {package} -c android.intent.category.LAUNCHER 1",
        timeout=30.0,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pid = game_pid(adb, serial, package)
        if pid is not None:
            return pid
        time.sleep(1.0)
    raise ReaderError(f"{package} se nije pokrenuo za {timeout:.0f}s")


def diagnose(adb: str, serial: str, package: str) -> dict[str, Any]:
    """What the device looks like right now, in the terms an attach cares about.

    Used to turn "the reader is being weird again, restart everything" into a
    specific statement about which piece is wrong.
    """
    report: dict[str, Any] = {"serial": serial}
    try:
        report["frida_pid"] = adb_shell(
            adb, serial, "su -c 'pidof frida-server || true'"
        ).strip() or None
    except ReaderError as exc:
        report["frida_pid"] = None
        report["frida_error"] = str(exc)
    try:
        report["game_pid"] = game_pid(adb, serial, package)
    except ReaderError as exc:
        report["game_pid"] = None
        report["game_error"] = str(exc)
    if report.get("game_pid") is not None:
        try:
            verify_namespace_cleaned(adb, serial, int(report["game_pid"]))
            report["namespace"] = "ok"
        except Exception as exc:
            report["namespace"] = str(exc)
    return report


def game_pid(adb: str, serial: str, package: str) -> int | None:
    output = adb_shell(adb, serial, f"pidof {package} || true")
    values = [value for value in output.split() if value.isdigit()]
    return int(values[0]) if values else None


def namespace_status(adb: str, serial: str) -> str:
    return adb_shell(
        adb,
        serial,
        "su -c 'tail -n 10 /data/local/tmp/matchmasters_namespace_hide.log "
        "2>/dev/null || true'",
    )


def verify_namespace_cleaned(adb: str, serial: str, pid: int) -> None:
    deadline = time.monotonic() + 12.0
    last = ""
    expected = f"pid={pid} namespace_cleaned=yes"
    while time.monotonic() < deadline:
        last = namespace_status(adb, serial)
        if expected in last:
            return
        time.sleep(0.5)
    raise ReaderError(
        f"Namespace zastita nije potvrdjena za PID {pid}; poslednji log:\n{last}"
    )


_ALLOWED_STATE_KEYS = {
    "game_state",
    "is_active",
    "is_singleplayer_board",
    "moves",
    "moves_made_this_turn",
    "chain_reaction",
    "current_turn",
    "turns",
    "turns_total",
    "current_round",
    "rounds",
    "rounds_total",
    "accumulated_move_score",
    "accumulated_turn_score",
    "remaining_time",
    "timer_paused",
    "current_player_index",
    "opponent_index",
    "energy_charging_colors",
    "opponent_energy_charging_colors",
}

# Player name is intentionally absent: the snapshot must never carry account
# identifiers, only the numbers the bot plays on.
_ALLOWED_PLAYER_KEYS = {
    "index",
    "score",
    "turn_score",
    "max_round_score",
    "rounds_won",
    "energy",
    "energy_to_ability",
    "energy_full",
    "energy_colors",
    "booster_activations_left",
    "score_multiplier",
    "health",
    "slot_type",
    "bonus_tiles_collected",
    # Mutation Lab: which mutations this player has picked and how long they
    # last. The agent already narrows the PlayerModel sweep to mutation-named
    # fields, so no identifier reaches this allowlist to begin with.
    "mutation_fields",
    "special_ability_type",
    "special_ability_name",
    "special_ability_description",
    "special_ability_params",
    # Read-only scalar sweep of the live SpecialAbility instance. The UFO's own
    # counters live here (PassiveActivates / ColorsPicked / MoveColorsTarget),
    # which is the only way to see how many eyes are still armed -- the model
    # field activeSpecialAbilityType reads 49 for a single animation frame.
    # The agent already narrows this to readable scalars and int collections.
    "special_ability_fields",
    "active_special_ability_type",
    # Whether this move already spent an ability. Nine board models skip their
    # own rule when it did (docs/game_mode_logic_from_code.md).
    "is_ability_used_this_move",
    "is_board_ability_used_this_move",
    "board_ability_used_this_move",
    "active_board_ability",
    "is_my_turn",
    "has_played_this_turn",
    "player_type",
}

_ALLOWED_RULES_KEYS = {
    "id",
    "title",
    "board_model_name",
    "pvp_mode",
    "rumble_type",
    "board_size",
    "colors_count",
    "moves_per_turn",
    "additional_moves",
    "turns_per_game",
    "time_per_turn",
    "is_timer",
    "extra_move_enabled",
    "energy_mult",
    "special_combo_score_multiplier",
    "both_colors_charge_energy",
    "explosion_on_match",
    "destroy_row_on_horizontal_match",
    "destroy_column_on_vertical_match",
    "vertical_match_increase_multiplier",
    "vertical_match_destroy_color",
    "specials_auto_explode",
    "all_specials_lightning",
    "every_match_is_special",
    "match_creates_special_chance",
    "bigger_bomb_area",
    "ability_locked",
    "reshuffle_every_turn",
    "solo_refill_mode",
    "solo_targets",
    "rumble_players_amount",
    "is_square_match",
    # SlotColor -> energy, decoded by the agent. board_source reads them to know
    # which colours charge the booster (multiplier-mushrooms charges a non-blue
    # one); they were dropped here until 2026-09-22, so it always assumed blue.
    "color_combo_energy",
    "color_energy_override",
    # The agent's sweep of every MatchRulesModel field, under its engine name.
    # Allow-listing individual rules is exactly what made a rule like
    # everyMatchIsSpecial invisible until someone thought to name it; this one
    # key carries the rest, so a mode's rules can be read without a code change.
    "engine_fields",
}


_ALLOWED_BOARD_ABILITY_KEYS = {"type", "name", "index"}


_ALLOWED_ABILITY_ENGINE_KEYS = {
    # UFOBeamSE getters: the eyes armed right now, straight from the engine.
    "remaining_hud_eyes",
    "colors_to_pick",
    "colors_picked",
    "passive_activates",
    # MixyMeow getters.
    "uses_left",
    "passive_uses_since_activate",
    "activates",
}


def _safe_ability_engine(raw: Any) -> dict[str, int | float | None] | None:
    """The getter counters the agent reads on a manual dump, numbers only.

    Missing from `_ALLOWED_PLAYER_KEYS` until 2026-09-15, so every manual dump
    lost them here and the UFO eye count and Mixy's UsesLeft were only ever
    inferred: 342 manual dumps with UFO SE / Mixy in that day's recording, not
    one carrying the key, and a match lost with a full booster held back by an
    eye that had already fired.
    """
    if not isinstance(raw, dict):
        return None
    return {
        key: value
        for key, value in raw.items()
        if key in _ALLOWED_ABILITY_ENGINE_KEYS
        and (value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)))
    }


def _safe_player(raw: dict[str, Any]) -> dict[str, Any]:
    player = {key: raw[key] for key in _ALLOWED_PLAYER_KEYS if key in raw}
    if "ufo_colors_exploded_this_move" in raw:
        colors = raw["ufo_colors_exploded_this_move"]
        player["ufo_colors_exploded_this_move"] = (
            [color for color in colors[:16]
             if isinstance(color, int) and not isinstance(color, bool) and 0 <= color <= 255]
            if isinstance(colors, list) else None
        )
    if "special_ability_engine" in raw:
        player["special_ability_engine"] = _safe_ability_engine(
            raw["special_ability_engine"]
        )
    abilities = raw.get("board_abilities")
    if isinstance(abilities, list):
        player["board_abilities"] = [
            {key: ability[key] for key in _ALLOWED_BOARD_ABILITY_KEYS if key in ability}
            for ability in abilities
            if isinstance(ability, dict)
        ]
    return player


def _safe_state(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    state = {key: raw[key] for key in _ALLOWED_STATE_KEYS if key in raw}
    players = raw.get("players")
    if isinstance(players, list):
        state["players"] = [
            _safe_player(player) for player in players if isinstance(player, dict)
        ]
    rules = raw.get("rules")
    if isinstance(rules, dict):
        state["rules"] = {key: rules[key] for key in _ALLOWED_RULES_KEYS if key in rules}
    return state


def _safe_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    allowed_snapshot_keys = {
        "schema_version",
        "type",
        "captured_at",
        "reason",
        "stable",
        "rows",
        "columns",
        "game_logic",
        "board_object",
        # The game build and the live enum tables read at attach. board_source
        # checks the tables against its hardcoded numbers -- an update that
        # inserts an enum member mid-run shifts every later value while keeping
        # them all "known", which no per-slot warning can catch.
        "game_version",
        "enums",
        "signature",
        "state_signature",
        "state_error",
        "slots",
        # Whatever the active board model keeps on itself. Mode state that is
        # not on the pieces lives here -- Column Mania's per-column multipliers
        # are the case that made it necessary. No account data on this object.
        "board_fields",
        # The board's `*Directions` tables, i.e. the blast shapes as [x, y]
        # offsets. Compiled constants, so one snapshot settles them for good.
        "board_directions",
        # CellModel grids: `cell_types` [row][col] carries the Funky Tiles cells
        # and `cell_multipliers` Column Mania's per-column multiplier. The agent
        # sent both, board_source reads both, and until 2026-09-22 they were
        # dropped right here, so those two modes never saw their own state.
        "cell_types",
        "cell_multipliers",
        # Mutation Lab state off GameLogic. The player-level sweep only ever
        # produced `mutationLabTargetInd`, so the picked mutation lives here or
        # nowhere the reader can see.
        "mutation_fields",
        # The mutations actually in force, one dict each. Several of their types
        # are rules the simulator already implements, so this is the field that
        # turns Mutation Lab from unreadable into partly playable.
        "active_mutations",
        # BoardModel.extraData as plain strings. JellySE has no field for its
        # infected area -- it keeps the cells, the target colour, the phase and
        # the uses left in this dictionary, under keys the engine formats per
        # ability type and player index. Board state only; no account data.
        "board_extra_data",
        # How that dictionary read (layout, per-entry errors): the evidence for
        # the extraData that reads as {} in every recording. Diagnostic only.
        "board_extra_data_diag",
        # The JellySE instance itself: which of those keys this match uses, and
        # on a manual dump the points as the engine's own deserialiser returns
        # them, which is the ground truth the host parser is checked against.
        "jelly",
        # Froggy Fu's own live state. `attraction_moves` is the recorded gather
        # -- one entry per swap the pull performed -- which is the only source
        # for the board the pull leaves behind: the animation plays those steps
        # out one at a time, so no captured frame shows the settled result.
        "froggy",
    }
    allowed_slot_keys = {
        "x", "y", "row", "col", "color", "color2", "value",
        "originalValue", "holdValue", "relatedPlayerIndex", "status",
        "score", "scoreModifierOrigin", "scoreModifierBonus", "energy",
        "hitPoints", "origin", "damageable", "autoDestruct", "canBeMatched",
        "movable", "createdFromCombo", "skipDestroyTillMoveEnds",
        "activateOnHitpointReduced", "isLiveEventPiece",
    }
    snapshot = {key: raw[key] for key in allowed_snapshot_keys if key in raw}
    if isinstance(snapshot.get("slots"), list):
        snapshot["slots"] = [
            {key: slot[key] for key in allowed_slot_keys if key in slot}
            for slot in snapshot["slots"]
            if isinstance(slot, dict)
        ]
    state = _safe_state(raw.get("state"))
    if state is not None:
        snapshot["state"] = state
    return snapshot


def enrich_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    snapshot = _safe_snapshot(raw)
    board, special_board, warnings = board_source.adapt_memory_snapshot_payload(snapshot)
    snapshot["board"] = board
    snapshot["special_board"] = special_board
    snapshot["warnings"] = list(warnings)
    snapshot["host_received_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return snapshot


# The snapshot log grew to 2.66 GB (2026-09-07): ~56 KB per snapshot, ~10 per
# second in a match, appended forever. latest.json is what the bot runs on;
# the log is only for later analysis, so it is rolled over by size and the
# rolled files can simply be deleted.
JSONL_ROTATE_BYTES = 200 * 1024 * 1024
# Rotated files kept next to the live log; older ones are deleted on rotation.
# Rotation alone only moved the growth sideways: 200 MB per rotated file, and
# nothing ever removed one.
JSONL_ROTATED_KEEP = 3


def _rotated_jsonl_pattern(path: Path) -> "re.Pattern[str]":
    """`<stem>.<YYYYMMDD_HHMMSS><suffix>`: exactly what rotation names a file."""
    return re.compile(
        re.escape(path.stem) + r"\.\d{8}_\d{6}" + re.escape(path.suffix) + r"\Z"
    )


def prune_rotated_jsonl(path: Path, keep: int = JSONL_ROTATED_KEEP) -> list[Path]:
    """Delete all but the newest `keep` rotated copies of `path`; never raises.

    Only files in `path`'s own folder whose name is exactly a rotation name
    (`board_snapshots.20260919_043455.jsonl`) are candidates -- the live log,
    latest.json and anything else are never touched. Newest by the stamp in
    the name, which is also the rotation order. Returns what was deleted.
    """
    pattern = _rotated_jsonl_pattern(path)
    try:
        rotated = sorted(
            entry
            for entry in path.parent.iterdir()
            if pattern.match(entry.name) and entry.is_file()
        )
    except OSError:
        return []
    keep = max(0, int(keep))
    stale = rotated[: len(rotated) - keep] if len(rotated) > keep else []
    deleted: list[Path] = []
    for entry in stale:
        try:
            entry.unlink()
            deleted.append(entry)
        except OSError:
            # Open in an analysis tool, say: the next rotation tries again.
            continue
    return deleted


def rotate_jsonl_if_large(path: Path, limit: int = JSONL_ROTATE_BYTES) -> Path | None:
    """Rename `path` aside once it exceeds `limit` bytes; return the new name.

    After a rotation only the newest JSONL_ROTATED_KEEP rotated files stay.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size < limit:
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    rotated = path.with_name(f"{path.stem}.{stamp}{path.suffix}")
    try:
        os.replace(path, rotated)
    except OSError:
        return None
    prune_rotated_jsonl(path, JSONL_ROTATED_KEEP)
    return rotated


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_jsonl_if_large(path)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def write_latest(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


_COLOR_LABELS = {
    0: "?",
    BLOCKED: "#",
    BLUE: "B",
    GREEN: "G",
    YELLOW: "Y",
    PURPLE: "P",
    RED: "R",
    ORANGE: "O",
    WHITE: "W",
    CHEST: "C",
    DISCO_BALL: "*",
}


def format_board(snapshot: dict[str, Any]) -> str:
    board = snapshot["board"]
    special = snapshot["special_board"]
    rows = []
    for row_index, row in enumerate(board):
        cells = []
        for col_index, value in enumerate(row):
            color = _COLOR_LABELS.get(int(value), "?")
            special_value = int(special[row_index][col_index])
            cells.append(f"{color}{special_value:02d}" if special_value else f" {color} ")
        rows.append(f"{row_index}: " + " ".join(cells))
    return "\n".join(rows)


_GAME_STATE_LABELS = {
    -1: "Initializing",
    -2: "StartingGame",
    -3: "WaitingToStartTurn",
    -4: "TurnPlaying",
    -5: "MovePlaying",
    -6: "MoveProcessing",
    -7: "MoveEnd",
    -8: "EndingTurn",
    -9: "WaitingForTurnTime",
    2: "Player1Win",
    3: "Player2Win",
    4: "Player1TechnicalWin",
    5: "Player2TechnicalWin",
    6: "Player1ConcedeWin",
    7: "Player2ConcedeWin",
}


def format_state(snapshot: dict[str, Any]) -> str:
    state = snapshot.get("state")
    if not isinstance(state, dict):
        error = snapshot.get("state_error")
        return f"stanje: nedostupno ({error})" if error else "stanje: nedostupno"

    raw_state = state.get("game_state")
    label = _GAME_STATE_LABELS.get(raw_state, raw_state)
    lines = [
        f"stanje={label} potezi={state.get('moves')} "
        f"(odigrano u potezu {state.get('moves_made_this_turn')}) "
        f"kaskada={state.get('chain_reaction')}",
        f"runda={state.get('current_round')}/{state.get('rounds_total')} "
        f"tura={state.get('current_turn')}/{state.get('turns_total')} "
        f"na potezu igrac {state.get('current_player_index')} "
        f"punjenje boje={state.get('energy_charging_colors')}",
    ]
    for player in state.get("players", []):
        lines.append(
            f"  igrac {player.get('index')}: skor={player.get('score')} "
            f"(tura {player.get('turn_score')}) buster="
            f"{player.get('energy')}/{player.get('energy_to_ability')} "
            f"pun={player.get('energy_full')} mult={player.get('score_multiplier')} "
            f"runde={player.get('rounds_won')} moj_potez={player.get('is_my_turn')}"
        )
    rules = state.get("rules")
    if isinstance(rules, dict):
        lines.append(
            f"  pravila: id={rules.get('id')} potezi/tura={rules.get('moves_per_turn')} "
            f"tura/partija={rules.get('turns_per_game')} extra={rules.get('extra_move_enabled')} "
            f"boje={rules.get('colors_count')} energy_mult={rules.get('energy_mult')} "
            f"special_mult={rules.get('special_combo_score_multiplier')}"
        )
    return "\n".join(lines)


def capture_screenshot(adb: str, serial: str, path: Path) -> None:
    completed = _run(
        [adb, "-s", serial, "exec-out", "screencap", "-p"],
        timeout=20.0,
        text=False,
    )
    if completed.returncode != 0 or not completed.stdout:
        stderr = completed.stderr.decode(errors="replace") if completed.stderr else ""
        raise ReaderError(f"Screenshot nije uspeo: {stderr}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(completed.stdout)


class BoardReader:
    def __init__(self, output: Path, latest: Path, *, quiet: bool = False):
        self.output = output
        self.latest = latest
        self.quiet = quiet
        self.ready_event = threading.Event()
        self.snapshot_event = threading.Event()
        self.detached_event = threading.Event()
        self.last_snapshot: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.metadata: dict[str, Any] | None = None
        # The agent idles until a match starts and says so; nothing before that
        # message is a board worth playing on.
        self.match_active = False
        self.match_event = threading.Event()
        self.last_match_reason: str | None = None
        # Freeze watchdog inputs. Any payload counts as proof of life; the
        # heartbeat is what makes silence meaningful, because a settled board
        # sends nothing. An older agent never sends one, and then the watchdog
        # stays out of it rather than reporting every quiet board.
        self.last_message_at: float | None = None
        self.last_heartbeat: dict[str, Any] | None = None
        self.last_heartbeat_at: float | None = None
        self.last_choose: dict[str, Any] | None = None
        # The last snapshot-file write failure per path (None once it works
        # again), so a full disk is reported once, not ten times a second.
        self.write_errors: dict[str, str | None] = {}
        # Which Frida session is current. Bumped on every attach and before a
        # session is torn down, so a "detached" signal that the OLD session
        # delivers late cannot mark the new one as gone.
        self.session_id = 0
        # GameLogic/board keys of matches the agent reported as over for good
        # (match_state dead=True), for handing back to a re-attached agent in
        # the same game process (see `merge_dead_logics`).
        self.dead_logic_keys: list[str] = []
        self._lock = threading.Lock()

    def new_session(self) -> int:
        """Retire the current session id and return a fresh one."""
        with self._lock:
            self.session_id += 1
            return self.session_id

    def detached_handler(self, session_id: int):
        """A `session.on("detached")` callback bound to one session id.

        The signal of a session that is no longer the current one (a late
        detach from the session just replaced, or from one torn down after a
        failed attach) is ignored; the current one goes to `on_detached`.
        """

        def handler(reason: Any, crash: Any = None) -> None:
            if session_id != self.session_id:
                return
            self.on_detached(reason, crash)

        return handler

    def remember_dead_logic(self, key: str) -> None:
        """Record one final end's logic key (newest last, bounded)."""
        if not key:
            return
        if key in self.dead_logic_keys:
            self.dead_logic_keys.remove(key)
        self.dead_logic_keys.append(key)
        del self.dead_logic_keys[:-DEAD_LOGICS_MAX]

    def _write_record(self, writer: Any, path: Path, record: dict[str, Any]) -> bool:
        """One snapshot file write; a failure is logged (once per new error)."""
        key = str(path)
        try:
            writer(path, record)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if self.write_errors.get(key) != message:
                print(
                    f"Upis snapshot-a nije uspeo ({path}): {message}",
                    file=sys.stderr,
                    flush=True,
                )
            self.write_errors[key] = message
            return False
        self.write_errors[key] = None
        return True

    def on_match_state(self, active: bool, reason: str, payload: dict[str, Any]) -> None:
        """Hook for hosts that want the match gate; the base reader only logs."""

    def on_notice(self, message: str) -> None:
        """Agent-side note worth showing the user; the base reader only prints."""

    def on_choose(self, payload: dict[str, Any]) -> None:
        """A heap walk (stop-the-world) started or finished in the game."""

    def on_detached(self, reason: str, crash: Any = None) -> None:
        self.match_active = False
        self.match_event.clear()
        self.last_error = f"Frida session detached: {reason}"
        self.detached_event.set()

    def on_message(self, message: dict[str, Any], data: bytes | None) -> None:
        if message.get("type") == "error":
            description = message.get("description") or message.get("stack") or str(message)
            self.last_error = description
            print(f"[FRIDA ERROR] {description}", file=sys.stderr, flush=True)
            return
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return
        payload_type = payload.get("type")
        self.last_message_at = time.monotonic()
        if payload_type == "heartbeat":
            self.last_heartbeat = payload
            self.last_heartbeat_at = self.last_message_at
            return
        if payload_type == "choose":
            self.last_choose = payload
            self.on_choose(payload)
            return
        if payload_type == "ready":
            if not self.quiet:
                print(
                    f"Frida agent spreman: app={payload.get('application')} "
                    f"Unity={payload.get('unity')}",
                    flush=True,
                )
            self.ready_event.set()
            return
        if payload_type == "match_state":
            self.match_active = bool(payload.get("active"))
            self.last_match_reason = str(payload.get("reason") or "")
            if not self.match_active and payload.get("dead") and payload.get("logic_key"):
                self.remember_dead_logic(str(payload["logic_key"]))
            if self.match_active:
                self.match_event.set()
            else:
                self.match_event.clear()
            self.on_match_state(self.match_active, self.last_match_reason, payload)
            if not self.quiet:
                label = "PARTIJA POCELA" if self.match_active else "partija gotova"
                print(
                    f"{label} ({self.last_match_reason}), "
                    f"GameCount={payload.get('game_count')}",
                    flush=True,
                )
            return
        if payload_type in ("match_pending", "match_pending_failed"):
            # Why a match did or did not open. Routed like an error rather than
            # dropped: silence here is exactly what "it did not pick up the
            # match" looked like from the outside.
            detail = ", ".join(
                f"{key}={value}"
                for key, value in payload.items()
                if key != "type"
            )
            message = (
                f"partija u najavi: {detail}"
                if payload_type == "match_pending"
                else f"partija nije otvorena: {detail}"
            )
            self.on_notice(message)
            if not self.quiet:
                print(message, flush=True)
            return
        if payload_type == "metadata":
            self.metadata = payload
            mismatches = [
                name
                for name, check in payload.get("offsets", {}).items()
                if isinstance(check, dict) and check.get("matches") is False
            ]
            if mismatches:
                print(
                    "Upozorenje: metadata offset odstupa: " + ", ".join(mismatches),
                    file=sys.stderr,
                    flush=True,
                )
            return
        if payload_type == "error":
            self.last_error = str(payload.get("message") or payload)
            print(
                f"[AGENT {payload.get('stage', 'error')}] {self.last_error}",
                file=sys.stderr,
                flush=True,
            )
            return
        if payload_type != "board_snapshot" or not isinstance(payload.get("snapshot"), dict):
            return
        try:
            snapshot = enrich_snapshot(payload["snapshot"])
        except Exception as exc:
            self.last_error = f"Snapshot odbijen: {exc}"
            print(self.last_error, file=sys.stderr, flush=True)
            return
        record = {"type": "board_snapshot", "snapshot": snapshot}
        with self._lock:
            # The bot plays on last_snapshot, not on the files: a full disk or
            # a log held open by an analysis tool used to raise out of here
            # before the snapshot was stored, and the board was simply lost.
            self.last_snapshot = snapshot
            self.snapshot_event.set()
            self._write_record(append_jsonl, self.output, record)
            self._write_record(write_latest, self.latest, record)
        if not self.quiet:
            print(
                f"\nSnapshot {snapshot.get('signature')} reason={snapshot.get('reason')} "
                f"stable={snapshot.get('stable')}",
                flush=True,
            )
            print(format_board(snapshot), flush=True)
            print(format_state(snapshot), flush=True)
            if snapshot.get("warnings"):
                print("Upozorenja: " + ", ".join(snapshot["warnings"]), flush=True)


def _export_call(exports: Any, names: tuple[str, ...], *args: Any) -> Any:
    for name in names:
        try:
            function = getattr(exports, name)
        except AttributeError:
            continue
        return function(*args)
    raise ReaderError(f"Frida RPC export nije pronadjen: {names}")


def load_recorded_dead_logics(path: Path = DEAD_LOGICS_PATH) -> tuple[int, list[str]] | None:
    """(pid, keys) from the GUI's dead_logics.json, or None; never raises."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pid = int(data.get("pid"))
        keys = [str(key) for key in data.get("keys") or [] if key]
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return (pid, keys) if keys else None


def merge_dead_logics(
    pid: int | None,
    session_keys: list[str] | tuple[str, ...],
    recorded: tuple[int, list[str]] | None = None,
) -> tuple[int, list[str]] | None:
    """The `dead_logics` to hand `attach_reader` for game process `pid`.

    `session_keys` are the ends this CLI saw itself in that process;
    `recorded` is the GUI's file, used only when it is for the same pid.
    Oldest first, no duplicates, the newest DEAD_LOGICS_MAX kept. None when
    there is nothing to hand over. `attach_reader` still ignores the result
    if the process it attaches to turns out to be a different one.
    """
    if pid is None:
        return None
    keys: list[str] = []
    if recorded is not None and recorded[0] == pid:
        keys.extend(str(key) for key in recorded[1] if key)
    for key in session_keys:
        if not key:
            continue
        if key in keys:
            keys.remove(key)
        keys.append(str(key))
    keys = keys[-DEAD_LOGICS_MAX:]
    return (int(pid), keys) if keys else None


def pid_poll_backoff(failures: int) -> float:
    """Seconds to wait after `failures` consecutive `game_pid` errors."""
    if failures <= 0:
        return 0.0
    return min(PID_POLL_BACKOFF_MAX, PID_POLL_BACKOFF_BASE * (2 ** min(failures - 1, 16)))


def _close_frida(script: Any, session: Any) -> None:
    """Unload the agent and drop the session, each step best-effort."""
    if script is not None:
        try:
            script.unload()
        except Exception:
            pass
    if session is not None:
        try:
            session.detach()
        except Exception:
            pass


def attach_reader(
    adb: str,
    serial: str,
    package: str,
    agent_path: Path,
    receiver: BoardReader,
    *,
    spawn: bool,
    poll_seconds: float,
    include_state: bool = True,
    stable_samples: int = 3,
    idle_seconds: float = 1.0,
    quiet_seconds: float = 0.0,
    ctor_hook: bool = True,
    dead_logics: tuple[int, list[str]] | None = None,
) -> tuple[Any, Any, Any, int]:
    """Attach the agent to the running game and start it polling.

    ``dead_logics`` is ``(pid, keys)``: GameLogic/board keys of matches the
    host saw end in that game process. Handed to the agent before it starts
    polling, so a fresh agent does not take the last match's leftover logic
    for a running one; ignored when the process is a different one.
    """
    if frida is None:
        raise ReaderError("Python paket frida nije instaliran")
    if not agent_path.exists():
        raise ReaderError(
            f"Frida agent nije pronadjen: {agent_path}; pokreni tools/build_board_agent.ps1"
        )
    device = frida.get_device_manager().add_remote_device(f"127.0.0.1:{FRIDA_PORT}")
    pid = game_pid(adb, serial, package)
    spawned = False
    if pid is None:
        if not spawn:
            raise ReaderError(
                f"Proces {package} nije pokrenut; pokreni igru ili dodaj --spawn"
            )
        pid = int(device.spawn([package]))
        spawned = True
    verify_namespace_cleaned(adb, serial, pid)
    # Pie64 itself is x86_64, but this split APK contains ARM64 Unity/IL2CPP
    # libraries and BlueStacks runs them through its native bridge. Attaching
    # to the default native realm only exposes x64 bootstrap modules; the
    # emulated realm is the real ARM64 game process containing libil2cpp.so.
    session = device.attach(pid, realm="emulated")
    # Tagged with this attach's session id: a late "detached" from a session
    # already replaced must not flag this one (see BoardReader.new_session).
    session.on("detached", receiver.detached_handler(receiver.new_session()))
    script = None
    try:
        script = session.create_script(agent_path.read_text(encoding="utf-8"))
        script.on("message", receiver.on_message)
        script.load()
        if spawned:
            device.resume(pid)
        if not receiver.ready_event.wait(20.0):
            raise ReaderError(
                receiver.last_error or "Frida agent nije poslao ready u roku od 20s"
            )
        if dead_logics is not None and dead_logics[0] == pid and dead_logics[1]:
            try:
                _export_call(
                    script.exports_sync, ("mark_dead", "markDead"), list(dead_logics[1])
                )
            except ReaderError:
                # An older agent build without the export: nothing to hand over.
                pass
        # The agent polls board-only until this call; game-state reading is
        # enabled explicitly so it can be switched off if a state read ever
        # misbehaves.
        _export_call(
            script.exports_sync,
            ("configure",),
            max(100, int(round(poll_seconds * 1000))),
            # How many identical polls count as "settled". A caller that checks
            # the engine's own move phase does not need the agent to prove it
            # by repetition, and every extra sample costs a full poll interval.
            int(stable_samples),
            bool(include_state),
            # Between matches the agent only reads the static match counter,
            # which costs nothing, so this interval buys responsiveness for
            # free: it is how late a new match can be noticed, not how much
            # work is done.
            max(200, int(round(idle_seconds * 1000))),
            # Optional inactivity backstop. Disabled by default: a player may
            # leave a live board unchanged while thinking or taking a break.
            max(0, int(round(quiet_seconds * 1000))),
            # Hook GameLogic's constructor so the agent is told which object
            # to read instead of searching the heap for it. An optimisation
            # with a fallback, and a switch, because this game is ARM64 under
            # BlueStacks' native bridge -- the reason hooking was avoided in
            # the first place.
            bool(ctor_hook),
        )
    except BaseException:
        # A half-made attach must not leave an agent running in the game (a
        # second one arrives with the retry) or a session nobody closes. Our
        # own teardown's "detached" is retired first so it is not reported as
        # the game going away.
        receiver.new_session()
        _close_frida(script, session)
        raise
    return device, session, script, pid


def set_trace(script: Any, enabled: bool, poll_ms: int | None = None) -> Any:
    """Turn the agent's debug trace on/off.

    With it on the agent also pushes the *unsettled* frames between two stable
    boards, which is the only way to see what a special or a booster actually
    did: the settled board arrives after the refill has already covered the
    cleared cells.
    """
    return _export_call(
        script.exports_sync,
        ("set_trace", "settrace"),
        bool(enabled),
        None if poll_ms is None else max(20, int(poll_ms)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serial",
        default=None,
        help="Pinuj instancu; bez ovoga se Pie64 trazi po identitetu (port se menja)",
    )
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--latest", type=Path, default=DEFAULT_LATEST)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--once", action="store_true", help="Rucni dump i izlaz")
    parser.add_argument("--manual-dump", action="store_true", help="Odmah posalji RPC dump")
    parser.add_argument("--spawn", action="store_true", help="Spawnuj igru ako nije pokrenuta")
    parser.add_argument("--screenshot", type=Path, help="Sacuvaj isti live ekran")
    parser.add_argument(
        "--no-state",
        action="store_true",
        help="Citaj samo tablu, bez stanja partije (potezi/skor/buster)",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    device = session = script = None
    try:
        adb = find_adb()
        serial = discover_serial(adb, args.serial)
        ensure_frida_server(adb, serial)
        receiver = BoardReader(args.output, args.latest, quiet=args.quiet)
        # Matches the GUI saw end in the running game process: the fresh agent
        # must not take their leftover logic for a live match. attach_reader
        # ignores them if the game turns out to be a different process.
        recorded = load_recorded_dead_logics()
        device, session, script, pid = attach_reader(
            adb,
            serial,
            args.package,
            args.agent,
            receiver,
            spawn=args.spawn,
            poll_seconds=args.poll_seconds,
            include_state=not args.no_state,
            dead_logics=recorded,
        )
        if not args.quiet:
            print(f"Attach uspesan: {args.package} PID={pid} serial={serial}", flush=True)
        if args.once or args.manual_dump:
            receiver.snapshot_event.clear()
            _export_call(script.exports_sync, ("dump_board", "dumpboard"))
        if args.once:
            if not receiver.snapshot_event.wait(15.0):
                raise ReaderError(receiver.last_error or "Nije primljen board snapshot")
            if args.screenshot:
                capture_screenshot(adb, serial, args.screenshot)
                if not args.quiet:
                    print(f"Screenshot: {args.screenshot}", flush=True)
            return 0

        if not args.quiet:
            print("Reader radi; Ctrl+C za izlaz.", flush=True)
        pid_failures = 0
        while True:
            try:
                current_pid = game_pid(adb, serial, args.package)
            except ReaderError as exc:
                # adb hiccups ("device offline", a timed-out shell) are not a
                # reason to end the reader: back off and ask again, and nudge
                # the transport back once it keeps failing.
                pid_failures += 1
                delay = pid_poll_backoff(pid_failures)
                if not args.quiet:
                    print(
                        f"adb ne odgovara ({exc}); ponovo za {delay:.0f}s",
                        file=sys.stderr,
                        flush=True,
                    )
                if pid_failures >= 3:
                    _adb_connect(adb, serial)
                time.sleep(delay)
                continue
            pid_failures = 0
            needs_reattach = receiver.detached_event.is_set() or (
                current_pid is not None and current_pid != pid
            )
            if needs_reattach:
                if not args.quiet:
                    print(
                        f"Proces igre je promenjen ({pid} -> {current_pid}); ponovo se kacim...",
                        flush=True,
                    )
                # Retire the old session first: its own "detached" (from the
                # teardown below, or late from the game) must not flag the new
                # session as gone and start this whole dance again.
                receiver.new_session()
                _close_frida(script, session)
                script = session = device = None
                receiver.ready_event.clear()
                receiver.detached_event.clear()
                # Same process (the session dropped, the game did not): the
                # ends seen so far still apply. A new process starts clean.
                if current_pid is not None and current_pid != pid:
                    receiver.dead_logic_keys.clear()
                dead_logics = merge_dead_logics(
                    current_pid if current_pid is not None else pid,
                    receiver.dead_logic_keys,
                    load_recorded_dead_logics(),
                )
                deadline = time.monotonic() + 60.0
                while time.monotonic() < deadline:
                    try:
                        device, session, script, pid = attach_reader(
                            adb,
                            serial,
                            args.package,
                            args.agent,
                            receiver,
                            spawn=False,
                            poll_seconds=args.poll_seconds,
                            include_state=not args.no_state,
                            dead_logics=dead_logics,
                        )
                        break
                    except Exception as exc:
                        receiver.last_error = str(exc)
                        time.sleep(1.0)
                else:
                    raise ReaderError(
                        "Reader nije uspeo ponovo da se zakaci u roku od 60s: "
                        + str(receiver.last_error)
                    )
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"GRESKA: {exc}", file=sys.stderr, flush=True)
        return 2
    finally:
        if script is not None:
            try:
                script.unload()
            except Exception:
                pass
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
