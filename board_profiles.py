import json
import os
import shutil
from pathlib import Path

from window_geometry import WindowRect


REGULAR_PROFILE = "regular"
SUPERSIZE_PROFILE = "supersize"
DEFAULT_PROFILE = REGULAR_PROFILE

BOARD_PROFILES = {
    REGULAR_PROFILE: {
        "config_file": "board_config.json",
        "boardSize": 7,
    },
    SUPERSIZE_PROFILE: {
        "config_file": "board_config_supersize.json",
        "boardSize": 8,
    },
}

REQUIRED_CONFIG_KEYS = ("left", "up", "width", "height", "squareSize")
DISPLAY_CALIBRATION_FILE = "display_calibration.json"
DISPLAY_CALIBRATION_VERSION = 1
LAYOUT_FULLSCREEN_LANDSCAPE = "fullscreen_landscape"
LAYOUT_PORTRAIT_WINDOW = "portrait_window"
CANONICAL_SQUARE_SIZE = {
    REGULAR_PROFILE: 84,
    SUPERSIZE_PROFILE: 74,
}


class BoardCalibrationError(ValueError):
    pass


def profile_for_board_size(board_size):
    """Calibration profile for a board of this size, or None if none fits.

    The memory path knows the board size for a fact (the engine reports it), so
    it can pick the profile instead of trusting a dropdown. None is a real
    answer, not a fallback: `super-sized` is 9x9 and has no geometry here, and
    clicking a 9x9 board through the 7x7 grid would hit the wrong cells.
    """
    try:
        wanted = int(board_size)
    except (TypeError, ValueError):
        return None
    for name, settings in BOARD_PROFILES.items():
        if settings["boardSize"] == wanted:
            return name
    return None


def calculate_board_config(top_left_center, bottom_right_center, board_size):
    if board_size < 2:
        raise ValueError("board_size must be at least 2")

    gap_count = board_size - 1
    square_size_x = (bottom_right_center[0] - top_left_center[0]) / gap_count
    square_size_y = (bottom_right_center[1] - top_left_center[1]) / gap_count
    square_size = round((square_size_x + square_size_y) / 2)

    return {
        "left": int(top_left_center[0] - square_size // 2),
        "up": int(top_left_center[1] - square_size // 2),
        "width": int(square_size * board_size),
        "height": int(square_size * board_size),
        "squareSize": int(square_size),
        "boardSize": int(board_size),
    }


def _window_rect(value):
    if isinstance(value, WindowRect):
        return value
    if isinstance(value, dict):
        return WindowRect(
            int(value["left"]),
            int(value["top"]),
            int(value["width"]),
            int(value["height"]),
        )
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return WindowRect(*(int(item) for item in value))
    raise BoardCalibrationError("BlueStacks prozor nema validnu geometriju")


def validate_board_calibration(
    top_left_center,
    bottom_right_center,
    board_size,
    window_rect=None,
):
    """Validate two tile centers before any existing config is overwritten."""

    if board_size < 2:
        raise BoardCalibrationError("Tabla mora imati najmanje 2 polja")
    x1, y1 = (int(value) for value in top_left_center)
    x2, y2 = (int(value) for value in bottom_right_center)
    if x2 <= x1 or y2 <= y1:
        raise BoardCalibrationError(
            "Donje desno polje mora biti desno i ispod gornjeg levog"
        )
    gaps = board_size - 1
    square_x = (x2 - x1) / gaps
    square_y = (y2 - y1) / gaps
    if min(square_x, square_y) < 20:
        raise BoardCalibrationError("Polja su premala; proveri izabrane tacke")
    mismatch = abs(square_x - square_y) / max(square_x, square_y)
    if mismatch > 0.10:
        raise BoardCalibrationError(
            "Razmak po sirini i visini se razlikuje vise od 10%; ponovi klikove"
        )

    config = calculate_board_config((x1, y1), (x2, y2), board_size)
    if window_rect is not None:
        rect = _window_rect(window_rect)
        if rect.width <= 0 or rect.height <= 0:
            raise BoardCalibrationError("BlueStacks prozor nema validnu velicinu")
        tolerance = max(2, config["squareSize"] // 5)
        if (
            config["left"] < rect.left - tolerance
            or config["up"] < rect.top - tolerance
            or config["left"] + config["width"] > rect.right + tolerance
            or config["up"] + config["height"] > rect.bottom + tolerance
        ):
            raise BoardCalibrationError(
                "Izabrana tabla nije unutar BlueStacks App Player prozora"
            )
    return config


def _display_calibration_path(base_dir="."):
    return Path(base_dir) / DISPLAY_CALIBRATION_FILE


def _read_display_payload(base_dir="."):
    path = _display_calibration_path(base_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != DISPLAY_CALIBRATION_VERSION:
        return None
    if not isinstance(payload.get("profiles"), dict):
        return None
    return payload


def has_relative_calibration(profile=DEFAULT_PROFILE, base_dir="."):
    payload = _read_display_payload(base_dir)
    return bool(payload and isinstance(payload["profiles"].get(profile), dict))


def display_layout_key(window_rect):
    """Classify the two BlueStacks arrangements which reflow game chrome."""

    rect = _window_rect(window_rect)
    return (
        LAYOUT_PORTRAIT_WINDOW
        if rect.height > rect.width
        else LAYOUT_FULLSCREEN_LANDSCAPE
    )


def _entry_layout_key(entry):
    explicit = entry.get("layout_key")
    if explicit in {LAYOUT_FULLSCREEN_LANDSCAPE, LAYOUT_PORTRAIT_WINDOW}:
        return explicit
    return display_layout_key(entry["reference_client"])


def _entry_variants(entry):
    variants = entry.get("variants")
    if isinstance(variants, list):
        return [item for item in variants if isinstance(item, dict)]
    # Version-1 files originally contained one profile directly. Treat that
    # entry as a single variant so existing fullscreen calibration is retained
    # when a portrait-window calibration is added.
    return [entry]


def _select_relative_variant(entry, window_rect):
    variants = _entry_variants(entry)
    if not variants:
        raise BoardCalibrationError("Sacuvani profil nema validnu kalibraciju")
    wanted = display_layout_key(window_rect)
    for variant in variants:
        try:
            if _entry_layout_key(variant) == wanted:
                return variant
        except (KeyError, TypeError, ValueError):
            continue
    if "variants" not in entry:
        # Preserve legacy version-1 behavior until the first multi-layout save.
        return variants[0]
    raise BoardCalibrationError(
        "Ovaj BlueStacks raspored jos nije kalibrisan; klikni Kalibrisi ekran"
    )


def _relative_profile(config, profile, window_rect):
    rect = _window_rect(window_rect)
    layout_key = display_layout_key(rect)
    board_size = int(config["boardSize"])
    center_x = config["left"] + config["width"] / 2.0
    center_y = config["up"] + config["height"] / 2.0
    return {
        "layout_key": layout_key,
        "board_size": board_size,
        "reference_client": rect.to_dict(),
        "reference_board_local": {
            "left": int(config["left"] - rect.left),
            "top": int(config["up"] - rect.top),
            "width": int(config["width"]),
            "height": int(config["height"]),
            "squareSize": int(config["squareSize"]),
        },
        "center_x_ratio": (center_x - rect.left) / rect.width,
        "center_y_ratio": (center_y - rect.top) / rect.height,
        # Match Masters stays portrait even when BlueStacks itself is fullscreen
        # on a landscape monitor.  The portrait viewport scales with client
        # height; using min(width, height) incorrectly halves the board when the
        # same app is shown in a narrow portrait BlueStacks window.
        "square_size_height_ratio": config["squareSize"] / rect.height,
        "square_size_ratio": config["squareSize"] / min(rect.width, rect.height),
        "canonical_square_size": CANONICAL_SQUARE_SIZE[profile],
        # BlueStacks reflows the bottom controls in a narrow portrait window.
        # Store the relation to the calibrated board instead of assuming the
        # fullscreen 0.44-cell gap at every layout and resolution.
        "perk_anchor": {
            "slot_1_x_from_board_left_ratio": 0.5,
            "slot_spacing_ratio": 1.0,
            "y_from_board_bottom_ratio": (
                0.31 if layout_key == LAYOUT_PORTRAIT_WINDOW else 0.44
            ),
        },
    }


def _resolve_relative_profile(entry, profile, window_rect):
    rect = _window_rect(window_rect)
    entry = _select_relative_variant(entry, rect)
    reference_client = _window_rect(entry["reference_client"])
    local = entry["reference_board_local"]
    board_size = int(entry.get("board_size", BOARD_PROFILES[profile]["boardSize"]))
    if board_size != BOARD_PROFILES[profile]["boardSize"]:
        raise BoardCalibrationError("Sacuvani profil ima pogresnu velicinu table")

    if rect.width == reference_client.width and rect.height == reference_client.height:
        # Same drawable size: preserve every calibrated pixel exactly and only
        # translate by the window movement.
        square_size = int(local["squareSize"])
        left = rect.left + int(local["left"])
        up = rect.top + int(local["top"])
    else:
        square_ratio = float(
            entry.get("square_size_height_ratio", entry["square_size_ratio"])
        )
        square_size = max(
            1,
            int(round(square_ratio * rect.height)),
        )
        board_pixels = square_size * board_size
        center_x = rect.left + float(entry["center_x_ratio"]) * rect.width
        center_y = rect.top + float(entry["center_y_ratio"]) * rect.height
        left = int(round(center_x - board_pixels / 2.0))
        up = int(round(center_y - board_pixels / 2.0))

    config = {
        "left": left,
        "up": up,
        "width": square_size * board_size,
        "height": square_size * board_size,
        "squareSize": square_size,
        "boardSize": board_size,
    }
    perk_anchor = entry.get("perk_anchor")
    if isinstance(perk_anchor, dict):
        slot_1_x = left + int(
            square_size * float(perk_anchor["slot_1_x_from_board_left_ratio"])
        )
        spacing = int(round(square_size * float(perk_anchor["slot_spacing_ratio"])))
        perk_y = up + config["height"] + int(
            round(square_size * float(perk_anchor["y_from_board_bottom_ratio"]))
        )
        config["perkSlotCenters"] = (
            (slot_1_x, perk_y),
            (slot_1_x + spacing, perk_y),
        )
    tolerance = max(2, square_size // 5)
    if (
        config["left"] < rect.left - tolerance
        or config["up"] < rect.top - tolerance
        or config["left"] + config["width"] > rect.right + tolerance
        or config["up"] + config["height"] > rect.bottom + tolerance
    ):
        raise BoardCalibrationError(
            "Preracunata tabla izlazi iz BlueStacks prozora; potrebna je nova kalibracija"
        )
    return config


def _atomic_write_json(path, payload):
    path = Path(path)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _restore_text(path, previous_text):
    path = Path(path)
    if previous_text is None:
        if path.exists():
            path.unlink()
        return
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.restore.tmp")
    try:
        temp_path.write_text(previous_text, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def save_board_calibration(
    profile,
    top_left_center,
    bottom_right_center,
    window_rect,
    base_dir=".",
):
    if profile not in BOARD_PROFILES:
        raise BoardCalibrationError(f"Nepoznat profil table: {profile}")
    settings = BOARD_PROFILES[profile]
    config = validate_board_calibration(
        top_left_center,
        bottom_right_center,
        settings["boardSize"],
        window_rect,
    )
    base_path = Path(base_dir)
    config_path = base_path / settings["config_file"]
    display_path = _display_calibration_path(base_path)
    payload = _read_display_payload(base_path) or {
        "version": DISPLAY_CALIBRATION_VERSION,
        "profiles": {},
    }
    new_variant = _relative_profile(config, profile, window_rect)
    previous_entry = payload["profiles"].get(profile)
    variants = []
    if isinstance(previous_entry, dict):
        variants = _entry_variants(previous_entry)
    new_layout = new_variant["layout_key"]
    preserved = []
    for variant in variants:
        try:
            if _entry_layout_key(variant) == new_layout:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        preserved.append(variant)
    payload["profiles"][profile] = {"variants": preserved + [new_variant]}

    old_config_text = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else None
    )
    old_display_text = (
        display_path.read_text(encoding="utf-8") if display_path.exists() else None
    )
    if config_path.exists():
        shutil.copy2(config_path, config_path.with_suffix(config_path.suffix + ".bak"))
    if display_path.exists():
        shutil.copy2(display_path, display_path.with_suffix(display_path.suffix + ".bak"))
    try:
        _atomic_write_json(config_path, config)
        _atomic_write_json(display_path, payload)
    except Exception:
        # The two files form one logical calibration.  If the second replace
        # fails (disk/permission issue), restore both previous versions so the
        # bot never starts from a half-updated pair.
        _restore_text(config_path, old_config_text)
        _restore_text(display_path, old_display_text)
        raise
    return _resolve_relative_profile(
        payload["profiles"][profile],
        profile,
        window_rect,
    )


def load_board_config(profile=DEFAULT_PROFILE, base_dir=".", window_rect=None):
    if profile not in BOARD_PROFILES:
        raise ValueError(f"Unknown board profile: {profile}")

    profile_settings = BOARD_PROFILES[profile]
    config_path = Path(base_dir) / profile_settings["config_file"]
    with config_path.open("r", encoding="utf-8") as config_file:
        raw_config = json.load(config_file)

    legacy_config = {key: int(raw_config[key]) for key in REQUIRED_CONFIG_KEYS}
    legacy_config["boardSize"] = int(
        raw_config.get("boardSize", profile_settings["boardSize"])
    )
    if window_rect is None:
        return legacy_config

    payload = _read_display_payload(base_dir)
    entry = payload["profiles"].get(profile) if payload else None
    if not isinstance(entry, dict):
        return legacy_config
    try:
        return _resolve_relative_profile(entry, profile, window_rect)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        if isinstance(exc, BoardCalibrationError):
            raise
        # A partial/corrupt new file must never break the proven legacy setup.
        return legacy_config


def display_scale_for_config(profile, square_size):
    if profile not in CANONICAL_SQUARE_SIZE:
        return 1.0
    return max(0.25, min(4.0, float(square_size) / CANONICAL_SQUARE_SIZE[profile]))
