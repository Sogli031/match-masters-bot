"""Canonical class taxonomy for the recognition dataset."""

from move_strategy import (
    BLOCKED,
    BLUE,
    CHEST,
    DISCO_BALL,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    SPECIAL_ALL_ABOARD_BANDIT,
    SPECIAL_BILLIE_DRONE,
    SPECIAL_BOMB,
    SPECIAL_CLEO_BUG,
    SPECIAL_COLOR_CRYSTAL,
    SPECIAL_CROSSHAIR,
    SPECIAL_DISCO_BALL,
    SPECIAL_FIREWORK_DOWN,
    SPECIAL_FIREWORK_LEFT,
    SPECIAL_FIREWORK_RIGHT,
    SPECIAL_FIREWORK_UP,
    SPECIAL_FROGGY_LOTUS,
    SPECIAL_HEART,
    SPECIAL_HORIZONTAL,
    SPECIAL_JOOJOO_SKULL,
    SPECIAL_KNIGHT,
    SPECIAL_LIGHTNING,
    SPECIAL_MODE_TARGET,
    SPECIAL_MUSHROOM,
    SPECIAL_RED_BLUE_TILE,
    SPECIAL_SPRAY_SE,
    SPECIAL_SWEEP_SE_BROOM,
    SPECIAL_VERTICAL,
    SPECIAL_XTRA_MOVE_TILE,
    SPECIAL_ZANY_ZAPPER_1,
    SPECIAL_ZANY_ZAPPER_2,
    VINNIE_SE_HEART_COLOR_PAIRS,
    WHITE,
    YELLOW,
    GameMode,
    is_purple_gem_special,
    is_vinnie_se_heart_special,
    make_vinnie_se_heart_special,
    normalize_game_mode,
    purple_gem_value,
    vinnie_se_heart_colors,
)

_COLOR_NAMES = {
    BLUE: "blue",
    GREEN: "green",
    YELLOW: "yellow",
    PURPLE: "purple",
    RED: "red",
    ORANGE: "orange",
    WHITE: "white",
}

_COLOR_AGNOSTIC_SPECIALS = {
    SPECIAL_DISCO_BALL: "disco_ball",
    SPECIAL_CLEO_BUG: "cleo_bug",
    SPECIAL_BILLIE_DRONE: "billie_drone",
    SPECIAL_FROGGY_LOTUS: "lotus",
    SPECIAL_RED_BLUE_TILE: "red_blue_mode_target",
    SPECIAL_SWEEP_SE_BROOM: "broom",
    SPECIAL_SPRAY_SE: "spray_se",
}

MODE_SPECIFIC_TARGET_CLASSES = {
    GameMode.CHEST: "chest_mode_target",
    GameMode.RED_AND_BLUE: "red_blue_mode_target",
    GameMode.GREEN_LEAF: "green_leaf_mode_target",
}

_COLOR_BOUND_SUFFIXES = {
    0: "normal",
    SPECIAL_HORIZONTAL: "horizontal",
    SPECIAL_VERTICAL: "vertical",
    SPECIAL_BOMB: "bomb",
    SPECIAL_LIGHTNING: "lightning",
    SPECIAL_CROSSHAIR: "crosshair",
    SPECIAL_HEART: "heart",
    SPECIAL_KNIGHT: "knight",
    SPECIAL_MUSHROOM: "mushroom",
    SPECIAL_COLOR_CRYSTAL: "color_crystal",
    SPECIAL_FIREWORK_LEFT: "firework_left",
    SPECIAL_FIREWORK_RIGHT: "firework_right",
    SPECIAL_FIREWORK_UP: "firework_up",
    SPECIAL_FIREWORK_DOWN: "firework_down",
    SPECIAL_ZANY_ZAPPER_1: "zany_zapper_1",
    SPECIAL_ZANY_ZAPPER_2: "zany_zapper_2",
    SPECIAL_ALL_ABOARD_BANDIT: "all_aboard_bandit",
    SPECIAL_JOOJOO_SKULL: "joojoo_skull",
    SPECIAL_XTRA_MOVE_TILE: "xtra_move",
}

_NAME_TO_COLOR = {name: code for code, name in _COLOR_NAMES.items()}
_SUFFIX_TO_SPECIAL = {suffix: code for code, suffix in _COLOR_BOUND_SUFFIXES.items()}
_VINNIE_SE_HEART_SUFFIX = "_vinnie_se_heart"
COIN_CLASSES = {
    f"{color_name}_coin": (color_code, 0)
    for color_code, color_name in _COLOR_NAMES.items()
    if color_code != WHITE
}
PURPLE_GEM_VALUES = tuple(range(5, 23))
PURPLE_GEM_CLASSES = {
    f"purple_gem_{value}": (PURPLE, SPECIAL_MODE_TARGET)
    for value in PURPLE_GEM_VALUES
}
HOT_COLOR_VALUES = (3, 4, 5)
HOT_COLOR_COLORS = (GREEN, YELLOW, PURPLE, ORANGE)
HOT_COLOR_CLASSES = {
    f"{_COLOR_NAMES[color]}_hot_color_{value}": (color, 0)
    for color in HOT_COLOR_COLORS
    for value in HOT_COLOR_VALUES
}
RETIRED_DATASET_CLASSES = frozenset({"blocked", "empty", "red_blue_tile"})
_CLASS_TO_COLOR_SPECIAL = {
    "disco_ball": (DISCO_BALL, SPECIAL_DISCO_BALL),
    "cleo_bug": (DISCO_BALL, SPECIAL_CLEO_BUG),
    "billie_drone": (BLOCKED, SPECIAL_BILLIE_DRONE),
    "chest_mode_target": (CHEST, SPECIAL_MODE_TARGET),
    "green_leaf_mode_target": (GREEN, SPECIAL_MODE_TARGET),
    "red_blue_mode_target": (BLUE, SPECIAL_RED_BLUE_TILE),
    "lotus": (BLOCKED, SPECIAL_FROGGY_LOTUS),
    "broom": (DISCO_BALL, SPECIAL_SWEEP_SE_BROOM),
    "spray_se": (DISCO_BALL, SPECIAL_SPRAY_SE),
    # Coins are visually distinct recognition classes, but deliberately decode
    # to a plain colored tile. They have no special gameplay effect.
    **COIN_CLASSES,
    **PURPLE_GEM_CLASSES,
    **HOT_COLOR_CLASSES,
}


def _vinnie_se_heart_class_name(first_color: int, second_color: int) -> str:
    return (
        f"{_COLOR_NAMES[first_color]}_{_COLOR_NAMES[second_color]}"
        f"{_VINNIE_SE_HEART_SUFFIX}"
    )


def _build_all_classes() -> frozenset:
    classes = set()
    classes.update(_COLOR_AGNOSTIC_SPECIALS.values())
    classes.add("lotus")
    classes.update(COIN_CLASSES)
    classes.update(PURPLE_GEM_CLASSES)
    classes.update(HOT_COLOR_CLASSES)
    classes.update(MODE_SPECIFIC_TARGET_CLASSES.values())
    for color_name in _COLOR_NAMES.values():
        for suffix in _COLOR_BOUND_SUFFIXES.values():
            classes.add(f"{color_name}_{suffix}")
    for first_color, second_color in VINNIE_SE_HEART_COLOR_PAIRS:
        classes.add(_vinnie_se_heart_class_name(first_color, second_color))
    return frozenset(classes)


ALL_CLASSES = _build_all_classes()


def mode_target_class_for_game_mode(game_mode: GameMode | str | None) -> str:
    """Return a visual target class when the active mode disambiguates it."""
    mode = normalize_game_mode(game_mode)
    class_name = MODE_SPECIFIC_TARGET_CLASSES.get(mode)
    if class_name is None:
        raise ValueError(f"No unnumbered mode-target class for game mode: {mode.value}")
    return class_name


def classify(
    color: int,
    special: int,
    game_mode: GameMode | str | None = None,
) -> str:
    """Map a move.json color/special pair to a canonical dataset class."""
    if special == SPECIAL_FROGGY_LOTUS:
        return "lotus"
    if is_retired_dataset_cell(color, special):
        raise ValueError(f"Retired dataset cell: color={color} special={special}")
    if is_vinnie_se_heart_special(special):
        return _vinnie_se_heart_class_name(*vinnie_se_heart_colors(special))
    if is_purple_gem_special(special):
        value = purple_gem_value(special)
        class_name = f"purple_gem_{value}"
        if class_name not in PURPLE_GEM_CLASSES:
            raise ValueError(f"Untrainable Purple Gem value: {value}")
        return class_name
    if special == SPECIAL_MODE_TARGET:
        return mode_target_class_for_game_mode(game_mode)
    if special in _COLOR_AGNOSTIC_SPECIALS:
        return _COLOR_AGNOSTIC_SPECIALS[special]

    suffix = _COLOR_BOUND_SUFFIXES.get(special)
    if suffix is None:
        raise ValueError(f"Unknown special code: {special}")

    color_name = _COLOR_NAMES.get(color)
    if color_name is None:
        raise ValueError(f"Unknown color code: {color}")
    return f"{color_name}_{suffix}"


def decode_class(class_name: str) -> tuple[int, int]:
    """Map a canonical dataset class back to runtime board/special values."""
    # Compatibility for ONNX metadata produced before mode targets were split.
    if class_name == "mode_target":
        return BLUE, SPECIAL_MODE_TARGET
    if class_name == "red_blue_tile":
        return BLUE, SPECIAL_RED_BLUE_TILE
    if class_name in RETIRED_DATASET_CLASSES:
        raise ValueError(f"Retired dataset class: {class_name}")
    if class_name in _CLASS_TO_COLOR_SPECIAL:
        return _CLASS_TO_COLOR_SPECIAL[class_name]

    if class_name.endswith(_VINNIE_SE_HEART_SUFFIX):
        color_part = class_name[: -len(_VINNIE_SE_HEART_SUFFIX)]
        color_names = color_part.split("_")
        if len(color_names) != 2:
            raise ValueError(f"Unknown dataset class: {class_name}")
        try:
            first_color = _NAME_TO_COLOR[color_names[0]]
            second_color = _NAME_TO_COLOR[color_names[1]]
            return first_color, make_vinnie_se_heart_special(first_color, second_color)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Unknown dataset class: {class_name}") from exc

    for color_name, color_code in _NAME_TO_COLOR.items():
        prefix = f"{color_name}_"
        if not class_name.startswith(prefix):
            continue
        suffix = class_name[len(prefix) :]
        special = _SUFFIX_TO_SPECIAL.get(suffix)
        if special is None:
            break
        return color_code, special

    raise ValueError(f"Unknown dataset class: {class_name}")


def hot_color_class_details(class_name: str) -> tuple[int, int] | None:
    """Return (color, points) for a Hot Color recognition class."""
    decoded = HOT_COLOR_CLASSES.get(class_name)
    if decoded is None:
        return None
    try:
        value = int(class_name.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return None
    return decoded[0], value


def is_retired_dataset_cell(color: int, special: int) -> bool:
    """Return True for old non-trainable board cells that should not become crops."""
    return (color == 0 and special == 0) or (color == BLOCKED and special == 0)
