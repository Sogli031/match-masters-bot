"""Extract Match Masters gameplay JSON from the UDP/5056 wire protocol.

The realtime game channel is not HTTPS.  Its UDP payloads contain a small
binary envelope followed by JSON encoded as UTF-16LE.  This tool can parse an
existing pcap or stream packets directly from a rooted Android device through
ADB/tcpdump.  Authentication material is redacted by default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path
from typing import BinaryIO, Iterator


SENSITIVE_KEY_PARTS = (
    "access_token",
    "accesstoken",
    "auth",
    "deviceid",
    "email",
    "firebase",
    "password",
    "refresh_token",
    "refreshtoken",
    "secret",
    "session",
    "userid",
    "user_id",
)


def _read_exact(stream: BinaryIO, size: int) -> bytes | None:
    data = stream.read(size)
    if not data:
        return None
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise EOFError("truncated pcap stream")
        data += chunk
    return data


def iter_pcap_packets(stream: BinaryIO) -> Iterator[tuple[float, int, bytes]]:
    header = _read_exact(stream, 24)
    if header is None:
        return
    magic = header[:4]
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
        b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
        b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    }
    try:
        endian, resolution = formats[magic]
    except KeyError as exc:
        raise ValueError("unsupported pcap magic") from exc
    link_type = struct.unpack(endian + "I", header[20:24])[0]

    while True:
        packet_header = _read_exact(stream, 16)
        if packet_header is None:
            return
        seconds, fraction, captured_len, _wire_len = struct.unpack(
            endian + "IIII", packet_header
        )
        packet = _read_exact(stream, captured_len)
        if packet is None:
            raise EOFError("missing pcap packet body")
        yield seconds + fraction / resolution, link_type, packet


def _ipv4_offset(link_type: int, packet: bytes) -> int | None:
    if link_type == 1:  # Ethernet
        if len(packet) < 14:
            return None
        ether_type = int.from_bytes(packet[12:14], "big")
        offset = 14
        while ether_type in (0x8100, 0x88A8) and len(packet) >= offset + 4:
            ether_type = int.from_bytes(packet[offset + 2 : offset + 4], "big")
            offset += 4
        return offset if ether_type == 0x0800 else None
    if link_type == 101:  # raw IP
        return 0
    if link_type == 113:  # Linux cooked capture v1
        return 16
    if link_type == 276:  # Linux cooked capture v2
        return 20
    return None


def extract_udp(packet: bytes, link_type: int) -> tuple[str, int, str, int, bytes] | None:
    ip_offset = _ipv4_offset(link_type, packet)
    if ip_offset is None or len(packet) < ip_offset + 28:
        return None
    first = packet[ip_offset]
    if first >> 4 != 4:
        return None
    ihl = (first & 0x0F) * 4
    if ihl < 20 or packet[ip_offset + 9] != 17:
        return None
    udp_offset = ip_offset + ihl
    if len(packet) < udp_offset + 8:
        return None
    source = ".".join(str(part) for part in packet[ip_offset + 12 : ip_offset + 16])
    destination = ".".join(str(part) for part in packet[ip_offset + 16 : ip_offset + 20])
    source_port, destination_port, udp_len = struct.unpack(
        "!HHH", packet[udp_offset : udp_offset + 6]
    )
    payload_end = min(len(packet), udp_offset + max(udp_len, 8))
    return source, source_port, destination, destination_port, packet[udp_offset + 8 : payload_end]


def extract_json(payload: bytes) -> object | None:
    """Return the first valid JSON value embedded in a gameplay payload."""
    markers = ((b'{\x00"\x00', "utf-16le", b"}\x00"), (b'{"', "utf-8", b"}"))
    for marker, encoding, end_marker in markers:
        start = payload.find(marker)
        if start < 0:
            continue
        end = payload.rfind(end_marker)
        if end < start:
            continue
        candidate = payload[start : end + len(end_marker)]
        try:
            return json.loads(candidate.decode(encoding))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None


def _decode_compressed_json(payload: bytes) -> object | None:
    gzip_start = payload.find(bytes.fromhex("1f8b08"))
    if gzip_start < 0:
        return None
    try:
        inflater = zlib.decompressobj(31)
        raw = inflater.decompress(payload[gzip_start:]) + inflater.flush()
    except zlib.error:
        return None
    encodings = ("utf-16le", "utf-8") if raw.count(b"\x00") > len(raw) // 4 else ("utf-8", "utf-16le")
    for encoding in encodings:
        try:
            return json.loads(raw.decode(encoding).rstrip("\x00"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    return None


def _summarize_server_json(value: object, include_identifiers: bool) -> tuple[str, object]:
    if include_identifiers or not isinstance(value, dict):
        return "server_state", sanitize(value, include_identifiers=include_identifiers)

    if "Players" in value and "Seed" in value:
        players = []
        for player in value.get("Players") or []:
            if not isinstance(player, dict):
                continue
            players.append(
                {
                    "AbilityType": player.get("AbilityType"),
                    "AbilityConfig": sanitize(player.get("AbilityConfig")),
                    "BoardAbilities": sanitize(player.get("BoardAbilities")),
                    "IsConnected": player.get("IsConnected"),
                    "TimeBank": player.get("TimeBank"),
                    "StakesMultiplier": player.get("StakesMultiplier"),
                    "Powerup": player.get("Powerup"),
                    "LimitedPerksCounts": sanitize(player.get("LimitedPerksCounts")),
                }
            )
        return "match_init", {
            "Players": players,
            "ShowSettings": sanitize(value.get("ShowSettings")),
            "SpecialPiecesModels": sanitize(value.get("SpecialPiecesModels")),
            "MatchType": value.get("MatchType"),
            "Seed": value.get("Seed"),
            "LastEventIndex": value.get("LastEventIndex"),
            "spawningEngineConfig": sanitize(value.get("spawningEngineConfig")),
            "engineFixes": sanitize(value.get("engineFixes")),
            "ConcederIndex": value.get("ConcederIndex"),
        }

    response = value.get("responseData")
    if isinstance(response, dict) and "matchIndex" in response:
        result_keys = (
            "coinsEarned",
            "trophiesEarned",
            "liveEventPointsEarned",
            "starsCollected",
            "winnerGetBoosters",
            "arenaProgressed",
            "lostBooster",
            "boostersLostAmount",
            "boosterShieldUsed",
            "boosterShieldsUsedAmount",
            "stakesMultiplier",
            "miniGameTokensEarned",
            "sceneBuildingTokensEarned",
            "matchIndex",
        )
        return "match_result", {
            key: sanitize(response.get(key)) for key in result_keys if key in response
        }

    return "server_state", {
        "topLevelKeys": list(value),
        "responseDataKeys": list(response) if isinstance(response, dict) else [],
    }


def _fragment_part(payload: bytes) -> tuple[tuple[bytes, int, int], int, int, bytes] | None:
    # Photon/ENet packet header (12 bytes), SendFragment command (32-byte header).
    if len(payload) < 44 or payload[12] != 8:
        return None
    command_len = int.from_bytes(payload[16:20], "big")
    start_sequence = int.from_bytes(payload[24:28], "big")
    fragment_count = int.from_bytes(payload[28:32], "big")
    fragment_number = int.from_bytes(payload[32:36], "big")
    total_length = int.from_bytes(payload[36:40], "big")
    fragment_offset = int.from_bytes(payload[40:44], "big")
    if not (1 <= fragment_count <= 4096 and fragment_number < fragment_count):
        return None
    end = min(len(payload), 12 + command_len)
    part = payload[44:end]
    if total_length <= 0 or fragment_offset + len(part) > total_length:
        return None
    key = (payload[8:12], start_sequence, total_length)
    return key, fragment_count, fragment_number, fragment_offset.to_bytes(4, "big") + part


def sanitize(value: object, include_identifiers: bool = False) -> object:
    if include_identifiers:
        return value
    if isinstance(value, dict):
        cleaned: dict[str, object] = {}
        for key, item in value.items():
            normalized = key.lower().replace("-", "").replace("_", "")
            if any(part.replace("_", "") in normalized for part in SENSITIVE_KEY_PARTS):
                cleaned[key] = "[REDACTED]"
            elif key.lower() == "gamestatehash" and isinstance(item, str):
                digest = hashlib.sha256(item.encode("utf-8")).hexdigest()[:16]
                cleaned[key] = f"sha256:{digest}"
            else:
                cleaned[key] = sanitize(item, include_identifiers=False)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item, include_identifiers=False) for item in value]
    return value


def events_from_pcap(
    stream: BinaryIO, *, include_identifiers: bool = False
) -> Iterator[dict[str, object]]:
    fragments: dict[
        tuple[bytes, int, int], dict[str, object]
    ] = {}
    for timestamp, link_type, packet in iter_pcap_packets(stream):
        udp = extract_udp(packet, link_type)
        if udp is None:
            continue
        source, source_port, destination, destination_port, payload = udp
        if source_port != 5056 and destination_port != 5056:
            continue
        if source_port == 5056:
            fragment = _fragment_part(payload)
            if fragment is not None:
                key, fragment_count, fragment_number, encoded_part = fragment
                group = fragments.setdefault(
                    key, {"count": fragment_count, "parts": {}}
                )
                parts = group["parts"]
                assert isinstance(parts, dict)
                parts[fragment_number] = encoded_part
                if len(parts) == fragment_count:
                    assembled = bytearray(key[2])
                    for stored in parts.values():
                        offset = int.from_bytes(stored[:4], "big")
                        data = stored[4:]
                        assembled[offset : offset + len(data)] = data
                    decoded = _decode_compressed_json(bytes(assembled))
                    if decoded is not None:
                        event_type, summarized = _summarize_server_json(
                            decoded, include_identifiers
                        )
                        yield {
                            "timestamp": dt.datetime.fromtimestamp(
                                timestamp, tz=dt.timezone.utc
                            ).isoformat(),
                            "direction": "server_to_client",
                            "server": source,
                            "payload_bytes": len(assembled),
                            "event_type": event_type,
                            "data": summarized,
                        }
                    del fragments[key]
        data = extract_json(payload)
        if data is None:
            continue
        yield {
            "timestamp": dt.datetime.fromtimestamp(
                timestamp, tz=dt.timezone.utc
            ).isoformat(),
            "direction": "server_to_client" if source_port == 5056 else "client_to_server",
            "server": source if source_port == 5056 else destination,
            "payload_bytes": len(payload),
            "event_type": "gameplay_action",
            "data": sanitize(data, include_identifiers=include_identifiers),
        }


def _open_live_capture(
    serial: str, adb: str, remote_pcap: str
) -> subprocess.Popen[bytes]:
    # Writing on-device avoids buffering in the ADB exec-out pipe.  The pcap is
    # periodically pulled and reparsed; already emitted packets are deduplicated.
    command = (
        f"rm -f {remote_pcap}; "
        f"tcpdump -i any -U -s 0 -w {remote_pcap} udp and port 5056"
    )
    return subprocess.Popen(
        [adb, "-s", serial, "shell", f"su -c '{command}'"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _event_key(event: dict[str, object]) -> str:
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _events_from_growing_pcap(
    path: Path, *, include_identifiers: bool
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    try:
        with path.open("rb") as stream:
            for event in events_from_pcap(
                stream, include_identifiers=include_identifiers
            ):
                events.append(event)
    except (EOFError, ValueError):
        # Pulling can catch tcpdump halfway through the newest packet.  Earlier
        # complete packets have already been yielded and are safe to use.
        pass
    return events


def _stop_remote_tcpdump(serial: str, adb: str) -> None:
    subprocess.run(
        [
            adb,
            "-s",
            serial,
            "shell",
            "su -c 'pkill -2 tcpdump 2>/dev/null || true'",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )


def _capture_live_file(
    serial: str,
    adb: str,
    output: Path | None,
    *,
    include_identifiers: bool,
    poll_seconds: float,
    remote_pcap: str,
) -> int:
    process = _open_live_capture(serial, adb, remote_pcap)
    destination = output.open("a", encoding="utf-8") if output else None
    seen: set[str] = set()
    count = 0
    print(f"capture_started remote={remote_pcap}", file=sys.stderr, flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix="matchmasters-udp-") as temp_dir:
            local_pcap = Path(temp_dir) / "capture.pcap"
            while process.poll() is None:
                pull = subprocess.run(
                    [adb, "-s", serial, "pull", remote_pcap, str(local_pcap)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if pull.returncode == 0 and local_pcap.exists():
                    for event in _events_from_growing_pcap(
                        local_pcap, include_identifiers=include_identifiers
                    ):
                        key = _event_key(event)
                        if key in seen:
                            continue
                        seen.add(key)
                        line = json.dumps(
                            event, ensure_ascii=False, separators=(",", ":")
                        )
                        print(line, flush=True)
                        if destination:
                            destination.write(line + "\n")
                            destination.flush()
                        count += 1
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        return 130
    finally:
        if destination:
            destination.close()
        _stop_remote_tcpdump(serial, adb)
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        print(f"capture_stopped events={count}", file=sys.stderr, flush=True)
    return process.returncode or 0


def _write_events(events: Iterator[dict[str, object]], output: Path | None) -> int:
    destination = output.open("a", encoding="utf-8") if output else None
    count = 0
    try:
        for event in events:
            line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
            print(line, flush=True)
            if destination:
                destination.write(line + "\n")
                destination.flush()
            count += 1
    finally:
        if destination:
            destination.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pcap", type=Path, help="parse an existing pcap")
    source.add_argument("--serial", help="stream from this rooted ADB device")
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--output", type=Path, help="append JSON events to this JSONL file")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument(
        "--remote-pcap",
        default="/sdcard/Download/mm_udp_live.pcap",
        help="temporary pcap path on the Android device",
    )
    parser.add_argument(
        "--include-identifiers",
        action="store_true",
        help="do not redact identifiers (unsafe for shared output)",
    )
    args = parser.parse_args()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.pcap:
        with args.pcap.open("rb") as stream:
            count = _write_events(
                events_from_pcap(stream, include_identifiers=args.include_identifiers),
                args.output,
            )
        print(f"parsed_events={count}", file=sys.stderr)
        return 0

    return _capture_live_file(
        args.serial,
        args.adb,
        args.output,
        include_identifiers=args.include_identifiers,
        poll_seconds=max(0.2, args.poll_seconds),
        remote_pcap=args.remote_pcap,
    )


if __name__ == "__main__":
    raise SystemExit(main())
