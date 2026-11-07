import datetime
import math
import os
import time
from dataclasses import replace

import cv2
import numpy as np
from PIL import Image, ImageEnhance

from board_profiles import (
    BoardCalibrationError,
    DEFAULT_PROFILE,
    display_scale_for_config,
    has_relative_calibration,
    load_board_config,
)
from capture import capture_debug_screenshot
from dataset_classes import PURPLE_GEM_CLASSES, decode_class, hot_color_class_details
from window_geometry import find_bluestacks_client_rect
import ml_recognition_runtime
from ml_recognition_runtime import (
    ML_RECOGNITION_FIRST,
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_ONLY,
    ML_RECOGNITION_SHADOW,
    RecognitionMlResult,
    normalize_ml_recognition_mode,
)
from move_strategy import (
    BLUE,
    BLOCKED,
    CHEST_MODE,
    COLOR_CRYSTALS_MODE,
    DISCO_BALL,
    FIREWORKS_MODE,
    FUNKY_TILES_MODE,
    GameMode,
    MixyMeowState,
    UfoState,
    UFO_MAX_EYES,
    BOUNTY_MODE,
    GREEN,
    GREEN_LEAF_MODE,
    HOT_COLOR_MODE,
    NONE_MODE,
    MULTIPLIER_MUSHROOMS_MODE,
    ORANGE,
    PURPLE,
    PURPLE_GEM_MODE,
    RED,
    RED_AND_BLUE_MODE,
    SPECIAL_BILLIE_DRONE,
    SPECIAL_ALL_ABOARD_BANDIT,
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
    SPECIAL_O_RAMA_MODE,
    SPECIAL_RED_BLUE_TILE,
    SPECIAL_SWEEP_SE_BROOM,
    SPECIAL_VERTICAL,
    SPECIAL_XTRA_MOVE_TILE,
    SPECIAL_ZANY_ZAPPER_1,
    SPECIAL_ZANY_ZAPPER_2,
    VERTICAL_RUSH_MODE,
    WHITE,
    YELLOW,
    make_purple_gem_special,
    make_vinnie_se_heart_special,
    normalize_game_mode,
)

runtime_initialized = False
last_hot_color_state = None
last_hot_color_auto_candidate = None
# (row, col) -> class name held back by the ANIMATION_PRONE_ML_CLASSES guard,
# waiting for a second scan to confirm it.
pending_transient_ml_cells = {}
_CONFIG_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
win = None
left = up = width = height = squareSize = 0
# Real layouts calibrate to ~70-90 px tiles; anything this small is a minimized
# or collapsed window, never a board that can be swiped.
MIN_PLAYABLE_SQUARE_SIZE = 16
top_left_x = top_left_y = 0
scale = 1.0
display_scale = 1.0
current_board_profile = DEFAULT_PROFILE
calibrated_perk_slot_centers = None
min_detect_range = 1
max_detect_range = 30
color_templates = []
special_templates = []
special_template_types = []
special_template_thresholds = []
special_template_colors = []
heart_templates = []
heart_template_masks = []
heart_template_colors = []
heart_template_thresholds = []
vinnie_se_heart_templates = []
vinnie_se_heart_template_masks = []
vinnie_se_heart_template_colors = []
vinnie_se_heart_template_specials = []
vinnie_se_heart_template_thresholds = []
knight_templates = []
knight_template_masks = []
knight_template_colors = []
knight_template_thresholds = []
cleo_bug_templates = []
cleo_bug_template_masks = []
cleo_bug_template_thresholds = []
billie_drone_templates = []
billie_drone_template_masks = []
billie_drone_template_thresholds = []
disco_ball_templates = []
disco_ball_template_masks = []
disco_ball_template_thresholds = []
all_aboard_bandit_templates = []
all_aboard_bandit_template_masks = []
all_aboard_bandit_template_colors = []
all_aboard_bandit_template_thresholds = []
joojoo_skull_templates = []
joojoo_skull_template_masks = []
joojoo_skull_template_thresholds = []
color_crystal_templates = []
color_crystal_template_masks = []
color_crystal_template_colors = []
color_crystal_template_thresholds = []
mushroom_templates = []
mushroom_template_masks = []
mushroom_template_colors = []
mushroom_template_thresholds = []
firework_mode_templates = []
firework_template_masks = []
firework_template_types = []
firework_template_thresholds = []
bounty = leaf = leaf_plus3 = purple_gem_4 = purple_gem_5 = red_blue = chest = chest2 = None

BOOSTER_ACTIVATE_TEMPLATE_PATHS = (
    os.path.join("Match-Masters", "Sprite", "blue-activate.png"),
    os.path.join("Match-Masters", "Sprite", "blue-activate-pushed.png"),
)
BOOSTER_ACTIVATE_WORD_CROP = (155, 48, 215, 88)
BOOSTER_ACTIVATE_THRESHOLD = 0.70
BOOSTER_ACTIVATE_LOWER_WORD_THRESHOLD = 0.75
BOOSTER_ACTIVATE_SCALE_RANGE = (0.56, 0.66)
BOOSTER_ACTIVATE_SCALE_STEPS = 21
BOOSTER_ACTIVATE_TEXT_MIN_WHITE_RATIO = 0.07
BOOSTER_ACTIVATE_TEXT_MIN_COL_RATIO = 0.45
BOOSTER_ACTIVATE_TEXT_MIN_SPAN_RATIO = 0.55
# Whiteness alone cannot tell the ACTIVATE word from a sparkle burst or a light
# streak sweeping over the charge pill -- both light up the same ratios.  The
# word always breaks into several letter-sized blobs sitting on one baseline, so
# require at least two components whose height falls in the glyph band.
BOOSTER_ACTIVATE_TEXT_MIN_GLYPHS = 2
BOOSTER_ACTIVATE_TEXT_GLYPH_MIN_AREA_RATIO = 0.0015
BOOSTER_ACTIVATE_TEXT_GLYPH_MIN_HEIGHT_RATIO = 0.30
BOOSTER_ACTIVATE_TEXT_GLYPH_MAX_HEIGHT_RATIO = 0.80
HEART_TRANSPARENT_ALPHA_THRESHOLD = 32
HEART_TRANSPARENT_MAX_PIECE_RATIO = 0.04
HEART_TRANSPARENT_COLOR_DISTANCE = 80.0
BILLIE_DRONE_TEMPLATE_THRESHOLD = 0.32
JOOJOO_SKULL_TEMPLATE_THRESHOLD = 0.36
JOOJOO_SKULL_MIN_LIGHT_RATIO = 0.18
JOOJOO_SKULL_COLOR_DISTANCE = 85.0
JOOJOO_SKULL_MIN_COLOR_PIXELS = 80

SPECIAL_PIECE_MODE_AUTO = "auto"
SPECIAL_PIECE_MODE_NONE = "none"
SPECIAL_PIECE_MODE_HEARTS = "hearts"
SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS = "vinnie_se_hearts"
SPECIAL_PIECE_MODE_KNIGHTS = "knights"
SPECIAL_PIECE_MODE_CLEO = "cleo"
SPECIAL_PIECE_MODE_BILLIE = "billie"
SPECIAL_PIECE_MODE_DISCO = "disco"
SPECIAL_PIECE_MODE_HIGH_VOLTAGE = "high_voltage"
SPECIAL_PIECE_MODE_ALL_ABOARD = "all_aboard"
SPECIAL_PIECE_MODE_JOOJOO = "joojoo"
SPECIAL_PIECE_MODE_MIXY_MEOW = "mixy_meow"
SPECIAL_PIECE_MODE_UFO = "ufo"
SPECIAL_PIECE_MODE_OPTIONS = (
    ("Booster: Nista", SPECIAL_PIECE_MODE_NONE),
    ("Booster: Auto", SPECIAL_PIECE_MODE_AUTO),
    ("Booster: Srca", SPECIAL_PIECE_MODE_HEARTS),
    ("Booster: Vinnie SE srca", SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS),
    ("Booster: Konji", SPECIAL_PIECE_MODE_KNIGHTS),
    ("Booster: Cleo", SPECIAL_PIECE_MODE_CLEO),
    ("Booster: Billie", SPECIAL_PIECE_MODE_BILLIE),
    ("Booster: Disco", SPECIAL_PIECE_MODE_DISCO),
    ("Booster: High Voltage", SPECIAL_PIECE_MODE_HIGH_VOLTAGE),
    ("Booster: All Aboard", SPECIAL_PIECE_MODE_ALL_ABOARD),
    ("Booster: Joo Joo", SPECIAL_PIECE_MODE_JOOJOO),
    ("Booster: Mixy Meow", SPECIAL_PIECE_MODE_MIXY_MEOW),
    ("Booster: UFO", SPECIAL_PIECE_MODE_UFO),
)
SPECIAL_PIECE_MODE_LABELS = {
    SPECIAL_PIECE_MODE_NONE: "Nista",
    SPECIAL_PIECE_MODE_AUTO: "Auto",
    SPECIAL_PIECE_MODE_HEARTS: "Srca",
    SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS: "Vinnie SE srca",
    SPECIAL_PIECE_MODE_KNIGHTS: "Konji",
    SPECIAL_PIECE_MODE_CLEO: "Cleo",
    SPECIAL_PIECE_MODE_BILLIE: "Billie",
    SPECIAL_PIECE_MODE_DISCO: "Disco",
    SPECIAL_PIECE_MODE_HIGH_VOLTAGE: "High Voltage",
    SPECIAL_PIECE_MODE_ALL_ABOARD: "All Aboard",
    SPECIAL_PIECE_MODE_JOOJOO: "Joo Joo",
    SPECIAL_PIECE_MODE_MIXY_MEOW: "Mixy Meow",
    SPECIAL_PIECE_MODE_UFO: "UFO",
}
special_piece_mode = SPECIAL_PIECE_MODE_AUTO
curr_mode = GameMode.FIREWORKS
last_funky_tile_cells: tuple[tuple[int, int], ...] = ()
last_jelly_zone_cells: tuple[tuple[int, int], ...] = ()
ml_recognition_mode = ML_RECOGNITION_OFF
COLOR_AGNOSTIC_SPECIAL_CLASSES = frozenset(
    {
        "disco_ball",
        "cleo_bug",
        "billie_drone",
        "mode_target",
        "chest_mode_target",
        "green_leaf_mode_target",
        "red_blue_mode_target",
        "red_blue_tile",
        "broom",
    }
    | set(PURPLE_GEM_CLASSES)
)
MODE_SPECIFIC_TARGET_CLASS_MODES = {
    "chest_mode_target": GameMode.CHEST,
    "green_leaf_mode_target": GameMode.GREEN_LEAF,
    "red_blue_mode_target": GameMode.RED_AND_BLUE,
    **{class_name: GameMode.PURPLE_GEM for class_name in PURPLE_GEM_CLASSES},
}
COLOR_AGNOSTIC_SPECIAL_MIN_CONFIDENCE = 0.9
# Classes that ride a BLOCKED board cell: they are the only specials with no
# colour of their own, which makes them the model's default answer for anything
# that is neither a tile nor empty. Debug/runs 2026-08-15 17-44-54 and 17-46-07
# show explosion bursts and motion-blurred falling pieces read as "lotus" /
# "billie_drone" at confidence 0.996-0.9999, and a phantom lotus rewrites the
# whole decision (the lotus gate left exactly one candidate in 17-46-07).
# Both are static board furniture in the real game, so require the same class at
# the same cell on two scans in a row. A held-back cell reads as unrecognized,
# which the manual retry loop and the auto stability gate already handle; a real
# lotus costs one extra scan (~100ms), an animation frame never repeats.
ANIMATION_PRONE_ML_CLASSES = frozenset({"lotus", "billie_drone"})
# The numbered +23/+24 Purple Gem overlay obscures the underlying tile more than
# the lower-value artwork.  A real end-game sample scored 0.3106 while all other
# 48 board cells were clean, so keep a narrowly mode/class-gated 0.30 floor.
PURPLE_GEM_MODE_TARGET_MIN_CONFIDENCE = 0.30
# The dataset only covers the printed values 5..22.  Late in a Purple Gem match
# the gems climb past that range, and the model then splits its probability over
# several numbered gem classes so no single class clears the floor above.  The
# printed number never reaches the board engine (every gem is just
# SPECIAL_MODE_TARGET), so a confident *family* total is enough to keep the gem
# on the board -- treat it as an unknown high-value gem instead of losing it.
PURPLE_GEM_FAMILY_FALLBACK_MIN_CONFIDENCE = 0.60
# Green Leaf targets are already disambiguated by the active game mode, and
# edge-clipped +3 leaves in the top board row score below the generic 0.90 floor
# even when the model correctly identifies them as mode_target.  Keep a guarded
# mode-specific floor instead of weakening disco/Cleo/other colorless specials.
GREEN_LEAF_MODE_TARGET_MIN_CONFIDENCE = 0.70
GAME_MODE_OPTIONS = (
    GameMode.FIREWORKS,
    GameMode.CHEST,
    GameMode.RED_AND_BLUE,
    GameMode.PURPLE_GEM,
    GameMode.GREEN_LEAF,
    GameMode.BOUNTY,
    GameMode.LASER,
    GameMode.VERTICAL_RUSH,
    GameMode.COLOR_CRUSH,
    GameMode.MULTIPLIER_MUSHROOMS,
    GameMode.SPECIAL_O_RAMA,
    GameMode.XTRA_MOVES,
    GameMode.INFINITE_MOVES,
    GameMode.ARCADE_MAN,
    GameMode.FLOOR_IS_LAVA,
    GameMode.FUNKY_TILES,
    GameMode.DRILLIN_DOWN,
    GameMode.CRAZY_COLUMNS,
    # ColumnManiaBoard (32): every column starts at x1 and a move raises the
    # multiplier of every column it cleared something in.
    GameMode.COLUMN_MANIA,
    # LightsUpBoard (37): matches in the lit column raise the score multiplier.
    GameMode.LIGHTS_UP,
    GameMode.MOVES_MULTIPLIER,
    GameMode.MULTIPLIER_MADNESS,
    # RainbowMultiplierBoard (35): two dealt colours raise the score multiplier.
    GameMode.COLOR_CLIMB,
    GameMode.HOT_COLOR,
    GameMode.ENERGIZED,
    # CandyWorldBoard (2): its candy tiles are two-colour (blue/red) pieces.
    GameMode.CANDY_WORLD,
    # DustvilleDuelBoard (4): three replenishing "wanted" tiles to collect.
    GameMode.DUSTVILLE_DUEL,
    # Board models read out of libil2cpp.so 2026-08-21. Frozen Feud simulates
    # its row clear; the other three carry the mode only so the board is read
    # and the mode stops reporting as unmapped (see MODE_WEIGHTS).
    GameMode.FROZEN_FEUD,
    GameMode.VEGAS_VIEWS,
    GameMode.BURIED_TREASURE,
    GameMode.ZANY_ZAPPERS,
    # Rule-flag modes: one MatchRulesModel field each, no board model.
    GameMode.BLOW_EM_UP,
    GameMode.LIGHTNING_STRIKE,
    GameMode.SHARED_ENERGY,
    GameMode.NONE,
)

# Funky markers are animated rainbow frames around board cells.  They are an
# overlay rather than a piece class (a heart can sit inside one), so detect the
# high-saturation, many-hued outer ring independently of base-piece recognition.
FUNKY_OUTER_BAND_RATIO = 22.0 / 84.0
FUNKY_BORDER_IGNORE_RATIO = 5.0 / 84.0
FUNKY_MIN_SATURATION = 120
FUNKY_MIN_VALUE = 100
FUNKY_MIN_RING_PIXELS_AT_84 = 2000
FUNKY_MIN_HUE_BINS = 10
FUNKY_MIN_PIXELS_PER_HUE_BIN_AT_84 = 8

# Some board animations draw a bright translucent beam over a complete row or
# column.  Its position changes, but it always lights the otherwise-dark outer
# band of most cells on the same axis.  Detect that geometry independently of
# tile classes, then give ML a second, tighter view of only the affected cells.
BOARD_LINE_EDGE_INNER_RATIO = 5.0 / 84.0
BOARD_LINE_EDGE_OUTER_RATIO = 18.0 / 84.0
BOARD_LINE_MIN_EDGE_VALUE = 150.0
BOARD_LINE_MIN_VALUE_DELTA = 45.0
BOARD_LINE_MIN_AXIS_COVERAGE = 0.70
BOARD_LINE_ML_INSET_RATIO = 8.0 / 84.0
BOARD_LINE_ML_CONTRAST = 1.25
BOARD_LINE_CLASS_CHANGE_MARGIN = 0.05


# The jelly area is a rainbow-outlined region that washes out the board
# background inside it (Debug 2026-08-14 23:27/23:28: cell-corner saturation
# drops from ~210 outside to 85-153 inside).  The absolute level depends on the
# board skin, so compare every cell against the board's own dominant background
# instead of a fixed threshold, and keep only one contiguous region -- explosion
# glare washes out scattered cells the same way.
JELLY_ZONE_CORNER_INSET = 2.0 / 84.0
JELLY_ZONE_CORNER_PATCH_RATIO = 10.0 / 84.0
JELLY_ZONE_MIN_SATURATION_DROP = 45.0
# The area's outline does not follow cell borders exactly, so a cell it only
# half covers washes out less than the core (175 against 89-159 with a 212
# baseline on the 23:50:57 frame). Grow the core over such cells instead of
# lowering the main threshold, which would start swallowing ordinary tiles.
JELLY_ZONE_GROW_SATURATION_DROP = 25.0
# Whether the outline separates two cells is decided by the longest neon *line*
# along their border, not by the share of neon pixels in the band. The stroke is
# only 4-5px wide and it does not sit on the cell border: on the 03-33-57 frame
# it runs 8-12px to the side of it, so a band tight enough to keep the neon share
# meaningful missed the stroke entirely (0.024) and the area swallowed the cell
# behind it. Sampling a wider band and asking how far a single line of neon runs
# is immune to that offset.
#
# Measured over 10 live regions: a border the outline runs along covers 0.56-0.98
# of its length, an ordinary interior border at most 0.50 (a tile's gloss stripe
# lies at a fixed offset from the border and covers half of it).
JELLY_ZONE_EDGE_BAND_RATIO = 14.0 / 84.0
JELLY_ZONE_EDGE_STROKE_COVERAGE = 0.55
JELLY_ZONE_EDGE_INSET_RATIO = 6.0 / 84.0
JELLY_ZONE_MIN_CELLS = 4
# Explosion glare washes out cell corners exactly like the jelly overlay does,
# so confirm the region by its rainbow outline. What separates the two is not
# how many neon pixels the border holds but whether they form one continuous
# stroke: the outline is a single curve running most of the way around, glare
# is scatter. Measured over 14 live regions (7x7 and 8x8) the longest connected
# neon run covers 0.49-1.15 of the region perimeter, while explosion glare
# reaches 0.25 and breaks into 69 specks instead of a dozen.
#
# The earlier neon-pixel *ratio* test could not do this. It read 0.23 on the
# 7x7 fixture it was tuned against but 0.08-0.14 on the 8x8 board -- a bigger
# region has proportionally more border the rounded outline cuts across, which
# dilutes the sample -- so SuperSize jelly areas were rejected outright and the
# bot played them as ordinary boards. Hue-bin coverage was no help either: real
# regions span 5-9 bins and the glare negative spans 6.
#
# The band is wide enough to catch the stroke where it bulges away from the
# cell edge it nominally follows.
JELLY_ZONE_BORDER_BAND = 9.0 / 84.0
JELLY_ZONE_BORDER_MIN_SATURATION = 150
JELLY_ZONE_BORDER_MIN_VALUE = 200
JELLY_ZONE_BORDER_MIN_STROKE_RATIO = 0.35
# Off-board edges carry no stroke, so they are left out of the perimeter (see
# _jelly_zone_border_is_rainbow). That lifts an edge-hugging glare patch's stroke
# ratio too -- the 7x7 glare negative goes from 0.25 to 0.39 -- so state the
# other half of the difference outright: glare scatters. Measured over the same
# frames, a real outline leaves 0.6-1.4 neon components per 100px of perimeter
# and glare 5.4-8.2.
JELLY_ZONE_BORDER_MAX_SPECK_DENSITY = 3.0 / 100.0
# The stroke is drawn over the tiles it passes, so ML sees artwork the training
# set never contained (Debug 2026-08-14 23:50:57: a plain orange gem read as
# yellow_knight at 0.925, the bot swapped for a match that did not exist and the
# game refused the move). Paint the overlay out and let ML look again.
JELLY_OVERLAY_BAND_RATIO = 9.0 / 84.0
JELLY_SPARKLE_MIN_VALUE = 230
JELLY_SPARKLE_MAX_SATURATION = 45
JELLY_SPARKLE_MIN_BLOB_AREA = 30
# A real XTRA tile draws white letters and frame rays: 9-11 white components per
# cell against 1-3 for a reward sparkle. Never paint over that, or a genuine
# extra-move tile would be cleaned away into a plain gem.
JELLY_SPARKLE_MAX_WHITE_COMPONENTS = 4
JELLY_OVERLAY_INPAINT_RADIUS = 3
# At jelly cells the cleaned image is the better evidence (the overlay that
# confused the model is gone), so a class change there does not need the beam
# pass's extra margin -- only its own confidence.
JELLY_CLASS_CHANGE_MIN_CONFIDENCE = 0.75
JELLY_BACKGROUND_MIN_SHIFT = 12
JELLY_BACKGROUND_TOLERANCE = 45
# A real XTRA tile is unmistakable in white: every one of the 54 labelled crops
# has 7-11 blobs (the letters plus the frame rays) against 1-3 for a gem with a
# reward sparkle. Overlays make the model report XTRA on plain gems at full
# confidence, so demote any XTRA read on a cell without that structure.
XTRA_TILE_MIN_WHITE_COMPONENTS = 5


def _cell_background_saturation(hsv, row: int, col: int, cell_size: int) -> float:
    """Median saturation of a cell's four corners (board background, not piece)."""
    inset = max(1, int(round(cell_size * JELLY_ZONE_CORNER_INSET)))
    patch = max(2, int(round(cell_size * JELLY_ZONE_CORNER_PATCH_RATIO)))
    top, left = row * cell_size, col * cell_size
    bottom, right = top + cell_size, left + cell_size
    corners = (
        hsv[top + inset:top + patch, left + inset:left + patch, 1],
        hsv[top + inset:top + patch, right - patch:right - inset, 1],
        hsv[bottom - patch:bottom - inset, left + inset:left + patch, 1],
        hsv[bottom - patch:bottom - inset, right - patch:right - inset, 1],
    )
    samples = np.concatenate([corner.reshape(-1) for corner in corners])
    if samples.size == 0:
        return 255.0
    return float(np.median(samples))


def _jelly_edge_stroke_coverage(hsv, cell, neighbour, cell_size: int) -> float:
    """How far the outline runs along the border between two cells.

    Returns the longest single line of neon parallel to the border, as a share of
    the border's length, so a stroke that runs beside the border rather than on
    it still counts in full.
    """
    band = max(1, int(round(cell_size * JELLY_ZONE_EDGE_BAND_RATIO)))
    inset = max(1, int(round(cell_size * JELLY_ZONE_EDGE_INSET_RATIO)))
    (row, col), (neighbour_row, neighbour_col) = cell, neighbour
    if row == neighbour_row:
        border_x = max(col, neighbour_col) * cell_size
        y0, y1 = row * cell_size + inset, (row + 1) * cell_size - inset
        x0, x1 = border_x - band, border_x + band
        along_axis = 0
    else:
        border_y = max(row, neighbour_row) * cell_size
        y0, y1 = border_y - band, border_y + band
        x0, x1 = col * cell_size + inset, (col + 1) * cell_size - inset
        along_axis = 1
    height, width = hsv.shape[:2]
    patch = hsv[max(0, y0):min(height, y1), max(0, x0):min(width, x1)]
    if patch.size == 0:
        return 1.0
    neon = (
        (patch[:, :, 1] > JELLY_ZONE_BORDER_MIN_SATURATION)
        & (patch[:, :, 2] > JELLY_ZONE_BORDER_MIN_VALUE)
    )
    return float(neon.mean(axis=along_axis).max())


def _grow_jelly_region(region, saturation, hsv, cell_size: int, grow_threshold: float):
    """Extend the core over neighbours the outline only partly covers.

    The outline itself decides: a neighbour separated from the area by the
    rainbow stroke stays outside no matter how dim it looks (board rows near the
    screen edge read dim on their own), while a neighbour with a clear border to
    the area is part of it.
    """
    grown = set(region)
    pending = list(grown)
    while pending:
        row, col = pending.pop()
        for row_step, col_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = (row + row_step, col + col_step)
            if not (
                0 <= neighbour[0] < board_length
                and 0 <= neighbour[1] < board_length
            ) or neighbour in grown:
                continue
            if saturation[neighbour[0]][neighbour[1]] >= grow_threshold:
                continue
            if (
                _jelly_edge_stroke_coverage(hsv, (row, col), neighbour, cell_size)
                >= JELLY_ZONE_EDGE_STROKE_COVERAGE
            ):
                continue
            grown.add(neighbour)
            pending.append(neighbour)
    return grown


def _cells_are_connected(cells) -> bool:
    """True when the cells form one 4-connected blob."""
    remaining = set(cells)
    if not remaining:
        return False
    stack = [next(iter(remaining))]
    seen = set()
    while stack:
        row, col = stack.pop()
        if (row, col) in seen:
            continue
        seen.add((row, col))
        for row_step, col_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = (row + row_step, col + col_step)
            if neighbour in remaining and neighbour not in seen:
                stack.append(neighbour)
    return len(seen) == len(remaining)


def _drop_cells_across_the_outline(cells, saturation, hsv, cell_size: int):
    """Remove cells the outline separates from the rest of the area.

    The wash-out alone cannot place a cell the outline cuts through: half of its
    corners dim like the inside (Debug 2026-08-15 03:33:27 read (4,4) at 122
    against a 170 baseline, well past the core threshold, with the outline
    running down its left border), so the area reached across the stroke and the
    simulation recoloured a tile the game leaves alone. Where the outline runs
    between two cells of the area, the one that is *less* washed out is the one
    outside it.
    """
    kept = set(cells)
    settled = set()
    while True:
        strongest = None
        for row, col in kept:
            for row_step, col_step in ((1, 0), (0, 1)):
                neighbour = (row + row_step, col + col_step)
                border = ((row, col), neighbour)
                if neighbour not in kept or border in settled:
                    continue
                coverage = _jelly_edge_stroke_coverage(
                    hsv, (row, col), neighbour, cell_size
                )
                if coverage < JELLY_ZONE_EDGE_STROKE_COVERAGE:
                    continue
                if strongest is None or coverage > strongest[0]:
                    strongest = (coverage, border)
        if strongest is None:
            return kept
        _coverage, border = strongest
        outside = max(border, key=lambda cell: saturation[cell[0]][cell[1]])
        remaining = kept - {outside}
        if len(remaining) < JELLY_ZONE_MIN_CELLS or not _cells_are_connected(remaining):
            settled.add(border)
            continue
        kept = remaining


def _fill_enclosed_cells(cells):
    """Add cells the region encloses.

    A bright piece can keep its own corners saturated even under the wash-out
    (a live frame lost (4,4) in the middle of its area), but a cell the jelly
    surrounds on every side is inside it.
    """
    region = set(cells)
    outside = set()
    stack = [
        (row, col)
        for row in range(board_length)
        for col in range(board_length)
        if (row in (0, board_length - 1) or col in (0, board_length - 1))
        and (row, col) not in region
    ]
    while stack:
        cell = stack.pop()
        if cell in outside:
            continue
        outside.add(cell)
        row, col = cell
        for row_step, col_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = (row + row_step, col + col_step)
            if (
                0 <= neighbour[0] < board_length
                and 0 <= neighbour[1] < board_length
                and neighbour not in region
                and neighbour not in outside
            ):
                stack.append(neighbour)
    return {
        (row, col)
        for row in range(board_length)
        for col in range(board_length)
        if (row, col) in region or (row, col) not in outside
    }


def _jelly_zone_border_is_rainbow(hsv, cells, cell_size: int) -> bool:
    """True when the region's outer edge is drawn with the rainbow outline."""
    band = max(1, int(round(cell_size * JELLY_ZONE_BORDER_BAND)))
    inside = set(cells)
    height, width = hsv.shape[:2]
    ring = np.zeros((height, width), dtype=np.uint8)
    perimeter = 0
    for row, col in cells:
        top, left = row * cell_size, col * cell_size
        edges = (
            ((-1, 0), (top - band, top + band, left, left + cell_size)),
            ((1, 0), (top + cell_size - band, top + cell_size + band, left, left + cell_size)),
            ((0, -1), (top, top + cell_size, left - band, left + band)),
            ((0, 1), (top, top + cell_size, left + cell_size - band, left + cell_size + band)),
        )
        for (row_step, col_step), (y0, y1, x0, x1) in edges:
            neighbour = (row + row_step, col + col_step)
            if neighbour in inside:
                continue
            ring[max(0, y0):min(height, y1), max(0, x0):min(width, x1)] = 1
            if not (
                0 <= neighbour[0] < board_length and 0 <= neighbour[1] < board_length
            ):
                # The outline is drawn outside the board crop there, so this edge
                # can never hold a stroke -- counting it only dilutes the test.
                # An area in the top-left corner scored 0.34 against a 0.35 bar
                # with half its perimeter off-board, and 0.68 without those edges
                # (Debug 2026-08-15 03:33:41/03:33:47/03:34:15: the same 3x3 area
                # went unseen on four frames in a row).
                continue
            perimeter += cell_size
    if perimeter <= 0:
        return False

    neon = (
        (hsv[:, :, 1] > JELLY_ZONE_BORDER_MIN_SATURATION)
        & (hsv[:, :, 2] > JELLY_ZONE_BORDER_MIN_VALUE)
        & (ring > 0)
    ).astype(np.uint8)
    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        neon, connectivity=8
    )
    longest_stroke = max(
        (int(stats[index, cv2.CC_STAT_AREA]) for index in range(1, component_count)),
        default=0,
    )
    if longest_stroke < JELLY_ZONE_BORDER_MIN_STROKE_RATIO * perimeter:
        return False
    speck_count = component_count - 1
    return speck_count <= JELLY_ZONE_BORDER_MAX_SPECK_DENSITY * perimeter


def detect_jelly_zone_cells(img_color) -> tuple[tuple[int, int], ...]:
    """Return the board cells inside the jelly area, if one is on screen."""
    if img_color is None:
        return ()
    rgb = np.asarray(img_color.convert("RGB") if hasattr(img_color, "convert") else img_color)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return ()

    cell_size = int(squareSize)
    if (
        cell_size <= 0
        or rgb.shape[0] < board_length * cell_size
        or rgb.shape[1] < board_length * cell_size
    ):
        return ()

    hsv = cv2.cvtColor(rgb[:, :, :3], cv2.COLOR_RGB2HSV)
    saturation = np.array(
        [
            [
                _cell_background_saturation(hsv, row, col, cell_size)
                for col in range(board_length)
            ]
            for row in range(board_length)
        ]
    )
    # The un-dimmed half of the board defines "normal" background saturation.
    baseline = float(np.median(saturation[saturation >= np.median(saturation)]))
    dimmed = (saturation < baseline - JELLY_ZONE_MIN_SATURATION_DROP).astype(np.uint8)
    if not dimmed.any():
        return ()

    region_count, labels = cv2.connectedComponents(dimmed, connectivity=4)
    largest = ()
    for label in range(1, region_count):
        cells = tuple(
            (int(row), int(col)) for row, col in zip(*np.where(labels == label))
        )
        if len(cells) > len(largest):
            largest = cells
    if len(largest) < JELLY_ZONE_MIN_CELLS:
        return ()
    grown = _grow_jelly_region(
        set(largest),
        saturation,
        hsv,
        cell_size,
        baseline - JELLY_ZONE_GROW_SATURATION_DROP,
    )
    trimmed = _drop_cells_across_the_outline(grown, saturation, hsv, cell_size)
    cells = tuple(sorted(_fill_enclosed_cells(trimmed)))
    if not _jelly_zone_border_is_rainbow(hsv, cells, cell_size):
        return ()
    return cells


def detect_funky_tile_cells(img_color) -> tuple[tuple[int, int], ...]:
    """Return zero-based board cells carrying the Funky rainbow frame."""
    if img_color is None:
        return ()
    rgb = np.asarray(img_color.convert("RGB") if hasattr(img_color, "convert") else img_color)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return ()

    cell_size = int(squareSize)
    required_height = board_length * cell_size
    required_width = board_length * cell_size
    if rgb.shape[0] < required_height or rgb.shape[1] < required_width:
        return ()

    outer_band = max(1, int(round(cell_size * FUNKY_OUTER_BAND_RATIO)))
    ignored_border = max(1, int(round(cell_size * FUNKY_BORDER_IGNORE_RATIO)))
    yy, xx = np.ogrid[:cell_size, :cell_size]
    outer_ring = (
        (xx < outer_band)
        | (xx >= cell_size - outer_band)
        | (yy < outer_band)
        | (yy >= cell_size - outer_band)
    )
    outer_ring &= ~(
        (xx < ignored_border)
        | (xx >= cell_size - ignored_border)
        | (yy < ignored_border)
        | (yy >= cell_size - ignored_border)
    )
    area_scale = (cell_size / 84.0) ** 2
    min_ring_pixels = max(1, int(round(FUNKY_MIN_RING_PIXELS_AT_84 * area_scale)))
    min_bin_pixels = max(3, int(round(FUNKY_MIN_PIXELS_PER_HUE_BIN_AT_84 * area_scale)))

    detected = []
    hue_edges = np.linspace(0, 180, 13)
    for row in range(board_length):
        for col in range(board_length):
            crop = rgb[
                row * cell_size : (row + 1) * cell_size,
                col * cell_size : (col + 1) * cell_size,
                :3,
            ]
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            vivid = (
                outer_ring
                & (hsv[:, :, 1] > FUNKY_MIN_SATURATION)
                & (hsv[:, :, 2] > FUNKY_MIN_VALUE)
            )
            if int(vivid.sum()) < min_ring_pixels:
                continue
            hue_counts = np.histogram(hsv[:, :, 0][vivid], bins=hue_edges)[0]
            if int((hue_counts >= min_bin_pixels).sum()) >= FUNKY_MIN_HUE_BINS:
                detected.append((row, col))
    return tuple(detected)


def detect_board_overlay_lines(img_color) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return complete board rows/columns covered by a bright animated beam."""
    if img_color is None:
        return (), ()
    rgb = np.asarray(img_color.convert("RGB") if hasattr(img_color, "convert") else img_color)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return (), ()

    cell_size = int(squareSize)
    if cell_size <= 0:
        return (), ()
    required_height = board_length * cell_size
    required_width = board_length * cell_size
    if rgb.shape[0] < required_height or rgb.shape[1] < required_width:
        return (), ()

    inner = max(1, int(round(cell_size * BOARD_LINE_EDGE_INNER_RATIO)))
    outer = max(inner + 1, int(round(cell_size * BOARD_LINE_EDGE_OUTER_RATIO)))
    yy, xx = np.ogrid[:cell_size, :cell_size]
    edge_ring = (
        (xx < outer)
        | (xx >= cell_size - outer)
        | (yy < outer)
        | (yy >= cell_size - outer)
    ) & ~(
        (xx < inner)
        | (xx >= cell_size - inner)
        | (yy < inner)
        | (yy >= cell_size - inner)
    )

    edge_values = np.zeros((board_length, board_length), dtype=np.float32)
    for row in range(board_length):
        for col in range(board_length):
            crop = rgb[
                row * cell_size : (row + 1) * cell_size,
                col * cell_size : (col + 1) * cell_size,
                :3,
            ]
            hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
            edge_values[row, col] = float(np.median(hsv[:, :, 2][edge_ring]))

    baseline = float(np.median(edge_values))
    bright_threshold = max(
        BOARD_LINE_MIN_EDGE_VALUE,
        baseline + BOARD_LINE_MIN_VALUE_DELTA,
    )
    min_axis_cells = max(2, int(math.ceil(board_length * BOARD_LINE_MIN_AXIS_COVERAGE)))

    rows = tuple(
        row
        for row in range(board_length)
        if int(np.count_nonzero(edge_values[row, :] >= bright_threshold)) >= min_axis_cells
    )
    columns = tuple(
        col
        for col in range(board_length)
        if int(np.count_nonzero(edge_values[:, col] >= bright_threshold)) >= min_axis_cells
    )
    return rows, columns


def board_overlay_line_cells(img_color) -> tuple[tuple[int, int], ...]:
    """Return every cell affected by a detected full-row/full-column beam."""
    rows, columns = detect_board_overlay_lines(img_color)
    cells = {
        (row, col)
        for row in range(board_length)
        for col in range(board_length)
        if row in rows or col in columns
    }
    return tuple(sorted(cells))


def prepare_board_image_without_overlay_lines(img_color, line_cells=None):
    """Create tighter ML crops for beam-covered cells while preserving the board."""
    cells = tuple(line_cells) if line_cells is not None else board_overlay_line_cells(img_color)
    if not cells:
        return img_color

    source = img_color.convert("RGB") if hasattr(img_color, "convert") else Image.fromarray(img_color)
    prepared = source.copy()
    cell_size = int(squareSize)
    inset = max(1, int(round(cell_size * BOARD_LINE_ML_INSET_RATIO)))
    if inset * 2 >= cell_size:
        return img_color

    for row, col in cells:
        left_px = col * cell_size
        top_px = row * cell_size
        crop = source.crop(
            (
                left_px + inset,
                top_px + inset,
                left_px + cell_size - inset,
                top_px + cell_size - inset,
            )
        )
        crop = crop.resize((cell_size, cell_size), Image.Resampling.BILINEAR)
        crop = ImageEnhance.Contrast(crop).enhance(BOARD_LINE_ML_CONTRAST)
        prepared.paste(crop, (left_px, top_px))
    return prepared

def jelly_zone_ml_cells(jelly_cells) -> tuple[tuple[int, int], ...]:
    """Cells whose artwork the jelly overlay can distort.

    The rainbow stroke straddles the border, so the neighbour outside the area
    is affected exactly as much as the cell inside it.
    """
    cells = {(int(row), int(col)) for row, col in jelly_cells or ()}
    if not cells:
        return ()
    affected = set(cells)
    for row, col in cells:
        for row_step, col_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = (row + row_step, col + col_step)
            if 0 <= neighbour[0] < board_length and 0 <= neighbour[1] < board_length:
                affected.add(neighbour)
    return tuple(sorted(affected))


def _white_component_count(cell_white) -> int:
    """Blobs of white inside one cell, ignoring specks."""
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        cell_white.astype(np.uint8),
        8,
    )
    return sum(
        1
        for index in range(1, count)
        if int(stats[index, cv2.CC_STAT_AREA]) >= JELLY_SPARKLE_MIN_BLOB_AREA
    )


def _jelly_overlay_mask(rgb, jelly_cells) -> np.ndarray:
    """Pixels of the rainbow stroke and of the white sparkles it travels with."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    height, width = hsv.shape[:2]
    cell_size = int(squareSize)
    band = max(1, int(round(cell_size * JELLY_OVERLAY_BAND_RATIO)))
    cells = {(int(row), int(col)) for row, col in jelly_cells}

    border = np.zeros((height, width), dtype=bool)
    for row, col in cells:
        top, left = row * cell_size, col * cell_size
        edges = (
            ((-1, 0), (top - band, top + band, left, left + cell_size)),
            ((1, 0), (top + cell_size - band, top + cell_size + band, left, left + cell_size)),
            ((0, -1), (top, top + cell_size, left - band, left + band)),
            ((0, 1), (top, top + cell_size, left + cell_size - band, left + cell_size + band)),
        )
        for (row_step, col_step), (y0, y1, x0, x1) in edges:
            if (row + row_step, col + col_step) in cells:
                continue
            border[max(0, y0):min(height, y1), max(0, x0):min(width, x1)] = True

    stroke = (
        border
        & (hsv[:, :, 1] > JELLY_ZONE_BORDER_MIN_SATURATION)
        & (hsv[:, :, 2] > JELLY_ZONE_BORDER_MIN_VALUE)
    )
    # The reward sparkles ride along the same overlay and cost the model just as
    # much: with only the stroke removed a live orange gem still read as
    # yellow_knight (0.43), with both removed it read orange_normal (1.00).
    white = (
        (hsv[:, :, 2] >= JELLY_SPARKLE_MIN_VALUE)
        & (hsv[:, :, 1] <= JELLY_SPARKLE_MAX_SATURATION)
    )
    sparkle = np.zeros((height, width), dtype=bool)
    for row, col in jelly_zone_ml_cells(cells):
        top, left = row * cell_size, col * cell_size
        cell_white = white[top:top + cell_size, left:left + cell_size]
        if _white_component_count(cell_white) > JELLY_SPARKLE_MAX_WHITE_COMPONENTS:
            continue
        sparkle[top:top + cell_size, left:left + cell_size] = cell_white
    mask = (stroke | sparkle).astype(np.uint8)
    return cv2.dilate(mask, np.ones((5, 5), np.uint8))


def prepare_board_image_without_jelly_overlay(img_color, jelly_cells):
    """Paint the jelly stroke and its sparkles out before the ML retry pass."""
    if not jelly_cells:
        return img_color
    source = (
        img_color.convert("RGB") if hasattr(img_color, "convert") else Image.fromarray(img_color)
    )
    rgb = np.asarray(source)
    cell_size = int(squareSize)
    if (
        cell_size <= 0
        or rgb.shape[0] < board_length * cell_size
        or rgb.shape[1] < board_length * cell_size
    ):
        return img_color
    mask = _jelly_overlay_mask(rgb, jelly_cells)
    if mask.any():
        repaired = cv2.inpaint(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
            mask,
            JELLY_OVERLAY_INPAINT_RADIUS,
            cv2.INPAINT_TELEA,
        )
        rgb = cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB)
    return Image.fromarray(_restore_jelly_cell_background(rgb, jelly_cells))


def _restore_jelly_cell_background(rgb, jelly_cells):
    """Put the washed-out cell background back to the board's normal tone.

    The lighter jelly background is what the model reads as an XTRA marker's
    frame: on live frames a plain yellow gem came back as yellow_xtra_move at
    0.99, and every phantom XTRA in the saved runs sat inside the area.
    """
    cell_size = int(squareSize)
    affected = set(jelly_zone_ml_cells(jelly_cells))
    if not affected:
        return rgb
    working = rgb.astype(np.int16).copy()
    outside = [
        _cell_background_color(working, row, col, cell_size)
        for row in range(board_length)
        for col in range(board_length)
        if (row, col) not in affected
    ]
    if not outside:
        return rgb
    target = np.median(np.stack(outside), axis=0)
    for row, col in affected:
        source = _cell_background_color(working, row, col, cell_size)
        if np.abs(source - target).max() < JELLY_BACKGROUND_MIN_SHIFT:
            continue
        top, left = row * cell_size, col * cell_size
        cell = working[top:top + cell_size, left:left + cell_size]
        background = np.abs(cell - source).max(axis=2) < JELLY_BACKGROUND_TOLERANCE
        cell[background] = np.clip(cell[background] + (target - source), 0, 255)
    return working.astype(np.uint8)


def _cell_background_color(rgb, row: int, col: int, cell_size: int):
    """Median colour of a cell's four corners (board background, not piece)."""
    inset = max(1, int(round(cell_size * JELLY_ZONE_CORNER_INSET)))
    patch = max(2, int(round(cell_size * JELLY_ZONE_CORNER_PATCH_RATIO)))
    top, left = row * cell_size, col * cell_size
    bottom, right = top + cell_size, left + cell_size
    corners = (
        rgb[top + inset:top + patch, left + inset:left + patch],
        rgb[top + inset:top + patch, right - patch:right - inset],
        rgb[bottom - patch:bottom - inset, left + inset:left + patch],
        rgb[bottom - patch:bottom - inset, right - patch:right - inset],
    )
    samples = np.concatenate([corner.reshape(-1, 3) for corner in corners])
    return np.median(samples, axis=0)


WHITE_COLOR = WHITE
CHEST_COLOR = 8

colors = [
    (0, 151, 224),
    (42, 214, 44),
    (255, 239, 16),
    (201, 106, 251),
    (251, 46, 76),
    (255, 138, 44),
    (250, 250, 250),
]
firework_color = [(0, 151, 224), (25, 187, 26), (255, 241, 91), (209, 110, 248), (251, 46, 76), (255, 104, 28)]
board_length = 7
color_acc = 10
pixel_color_detect_range = 60
special_color = 1
special_color_three_score = 2.5
three_score = 1

color_dict = {
    1: "blue",
    2: "green",
    3: "yellow",
    4: "purple",
    5: "red",
    6: "orange",
    WHITE_COLOR: "white",
    CHEST_COLOR: "chest",
}

SPECIAL_TEMPLATE_COLORS = ("blue", "green", "yellow", "purple", "red", "orange", "white")
COLOR_TEMPLATE_SPECS = (
    ("blue", 1),
    ("green", 2),
    ("yellow", 3),
    ("purple", 4),
    ("red", 5),
    ("orange", 6),
    ("white", WHITE_COLOR),
)
COLOR_NAME_TO_VALUE = dict(COLOR_TEMPLATE_SPECS)
HEART_TEMPLATE_SPECS = (
    ("blue", 1, 0.32),
    ("green", 2, 0.32),
    ("yellow", 3, 0.32),
    ("purple", 4, 0.30),
    ("red", 5, 0.32),
    ("orange", 6, 0.25, 0.80),
    ("white", WHITE_COLOR, 0.32),
)
KNIGHT_TEMPLATE_SPECS = (
    ("blue", 1, 0.09),
    ("green", 2, 0.08),
    ("yellow", 3, 0.095),
    ("purple", 4, 0.055),
    ("red", 5, 0.18),
    ("orange", 6, 0.14),
)
GENERAL_SPECIAL_SPECS = (
    ("row", SPECIAL_HORIZONTAL, 0.70, "assets/general/horizonal_purple_arrow.png", 0.8),
    ("column", SPECIAL_VERTICAL, 0.70, "assets/general/vertical_blue_arrow.png", 0.8),
    ("bomb", SPECIAL_BOMB, 0.70, "assets/general/green_bomb.png", 0.8),
    ("lightning", SPECIAL_LIGHTNING, 0.78, "assets/general/green_lightning.png", 0.8),
    ("crosshair", SPECIAL_CROSSHAIR, 0.80, "assets/general/crosshair.png", 1.0),
)
COLOR_CRYSTAL_TEMPLATE_SPECS = (
    ("green", 2, 0.30),
    ("yellow", 3, 0.34),
    ("purple", 4, 0.18),
    ("orange", 6, 0.30),
)
# The general (TM_CCOEFF_NORMED) special detector occasionally fires a false
# positive on a color-crystal tile. Those ccoeff scores are not comparable to
# the crystal's TM_SQDIFF_NORMED confidence, so the crystal cannot be gated
# against them by confidence. Instead it may override such a special only when
# the special barely cleared its own threshold (small margin = likely a false
# positive); a genuine special clears its threshold by a comfortable margin and
# is preserved. Candidate-based specials (knight, heart, ...) share the SQDIFF
# metric, so those are gated by confidence instead.
CRYSTAL_OVERRIDABLE_SPECIALS = frozenset(spec[1] for spec in GENERAL_SPECIAL_SPECS)
CRYSTAL_OVERRIDE_GENERAL_MARGIN = 0.05
MUSHROOM_TEMPLATE_SPECS = (
    ("green", 2, 0.28),
    ("yellow", 3, 0.28),
    ("purple", 4, 0.28),
    ("orange", 6, 0.28),
)
MUSHROOM_STEM_MIN_LIGHT_RATIO = 0.42
ALL_ABOARD_BANDIT_TEMPLATE_SPECS = (
    ("blue", 1, 0.18),
    ("green", 2, 0.18),
    ("yellow", 3, 0.18),
    ("purple", 4, 0.18),
    ("red", 5, 0.18),
    ("orange", 6, 0.18),
)
FIREWORK_TEMPLATE_SPECS = (
    ("live_purple_row_right.png", SPECIAL_FIREWORK_RIGHT, 0.08),
    ("live_orange_row_left.png", SPECIAL_FIREWORK_LEFT, 0.08),
    ("live_yellow_row_left.png", SPECIAL_FIREWORK_LEFT, 0.08),
    ("live_yellow_row_right.png", SPECIAL_FIREWORK_RIGHT, 0.08),
    ("live_orange_column_down.png", SPECIAL_FIREWORK_DOWN, 0.08),
    ("live_yellow_column_down.png", SPECIAL_FIREWORK_DOWN, 0.08),
    ("live_purple_column_down.png", SPECIAL_FIREWORK_DOWN, 0.08),
    ("left_firework.png", SPECIAL_FIREWORK_LEFT, 0.08),
    ("right_firework.png", SPECIAL_FIREWORK_RIGHT, 0.08),
    ("up_firework.png", SPECIAL_FIREWORK_UP, 0.08),
    ("down_firework.png", SPECIAL_FIREWORK_DOWN, 0.08),
)
VINNIE_SE_HEART_TEMPLATE_THRESHOLD = 0.32

def load_and_resize_template(path, fill_ratio=0.8, fit_to_tile=False):
    img = cv2.imread(path, 0) if os.path.isfile(path) else None
    if img is None:
        # Return a dummy 10x10 template so cv2.matchTemplate won't crash
        return np.zeros((10, 10), dtype=np.uint8)
    target_width = int(squareSize * fill_ratio)
    scale_base = max(img.shape[:2]) if fit_to_tile else img.shape[1]
    img_scale = target_width / scale_base
    return cv2.resize(img, (0, 0), fx=img_scale, fy=img_scale)

def load_and_resize_rgba_template(path, fill_ratio=0.88, fit_to_tile=True):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED) if os.path.isfile(path) else None
    if img is None:
        return None, None
    target_width = int(squareSize * fill_ratio)
    scale_base = max(img.shape[:2]) if fit_to_tile else img.shape[1]
    img_scale = target_width / scale_base
    resized = cv2.resize(img, (0, 0), fx=img_scale, fy=img_scale)
    if resized.ndim == 2:
        template = cv2.cvtColor(resized, cv2.COLOR_GRAY2RGB)
        mask = np.full(resized.shape, 255, dtype=np.uint8)
    elif resized.shape[2] == 4:
        template = cv2.cvtColor(resized[:, :, :3], cv2.COLOR_BGR2RGB)
        mask = resized[:, :, 3]
    else:
        template = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        mask = np.full(resized.shape[:2], 255, dtype=np.uint8)
    return template, mask

def load_booster_activate_word_template(path):
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED) if os.path.isfile(path) else None
    if img is None:
        return None
    x, y, width, height = BOOSTER_ACTIVATE_WORD_CROP
    return img[y:y + height, x:x + width, :3]

def booster_activation_region():
    x = int(left - squareSize * 0.18)
    y = int(up - squareSize * 2.05)
    return (
        max(0, x),
        max(0, y),
        max(1, int(squareSize * 2.75)),
        max(1, int(squareSize * 1.25)),
    )

def _as_bgr_image(image):
    if isinstance(image, Image.Image):
        return cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    return image

def _booster_search_window(result_shape):
    height, width = result_shape[:2]
    x1 = max(0, int(width * 0.60))
    x2 = width
    y1 = max(0, int(height * 0.25))
    y2 = min(height, int(height * 0.90))
    if x2 <= x1 or y2 <= y1:
        return 0, 0, width, height
    return x1, y1, x2, y2

def _best_booster_activate_match(image_gray, template_gray, template_name, threshold, match_type):
    best = {"active": False, "score": 0.0, "template": None, "scale": None, "location": None}
    # The activation artwork is screen UI, not a board tile.  Keep the exact
    # old range at the current display size (display_scale == 1), while a
    # portable calibration scales it on a smaller/larger screen.
    min_scale, max_scale = (
        BOOSTER_ACTIVATE_SCALE_RANGE[0] * display_scale,
        BOOSTER_ACTIVATE_SCALE_RANGE[1] * display_scale,
    )
    for scale_value in np.linspace(min_scale, max_scale, BOOSTER_ACTIVATE_SCALE_STEPS):
        template_width = max(1, int(round(template_gray.shape[1] * scale_value)))
        template_height = max(1, int(round(template_gray.shape[0] * scale_value)))
        if template_width > image_gray.shape[1] or template_height > image_gray.shape[0]:
            continue
        scaled_template = cv2.resize(
            template_gray,
            (template_width, template_height),
            interpolation=cv2.INTER_AREA,
        )
        result = cv2.matchTemplate(image_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
        x1, y1, x2, y2 = _booster_search_window(result.shape)
        constrained = result[y1:y2, x1:x2]
        if constrained.size == 0:
            continue
        _, score, _, location = cv2.minMaxLoc(constrained)
        if score > best["score"]:
            best = {
                "active": score >= threshold,
                "score": float(score),
                "template": template_name,
                "scale": float(scale_value),
                "location": (int(x1 + location[0]), int(y1 + location[1])),
                "template_size": (int(template_width), int(template_height)),
                "match_type": match_type,
            }
    return best

def _booster_activate_text_glyph_count(white_text):
    """Count letter-shaped blobs in the ACTIVATE text mask.

    Sparkles and diagonal light streaks produce one blob that is either far too
    small or spans the whole band height, while the word splits into several
    components of roughly letter height.
    """
    height, width = white_text.shape[:2]
    _count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        white_text.astype(np.uint8),
        8,
    )
    min_area = BOOSTER_ACTIVATE_TEXT_GLYPH_MIN_AREA_RATIO * height * width
    min_height = BOOSTER_ACTIVATE_TEXT_GLYPH_MIN_HEIGHT_RATIO * height
    max_height = BOOSTER_ACTIVATE_TEXT_GLYPH_MAX_HEIGHT_RATIO * height
    glyphs = 0
    for index in range(1, stats.shape[0]):
        blob_height = int(stats[index, cv2.CC_STAT_HEIGHT])
        blob_area = int(stats[index, cv2.CC_STAT_AREA])
        if blob_area >= min_area and min_height <= blob_height <= max_height:
            glyphs += 1
    return glyphs

def _booster_activate_text_band_match(image_bgr):
    height, width = image_bgr.shape[:2]
    x1 = int(width * 0.34)
    x2 = int(width * 0.98)
    y1 = int(height * 0.15)
    y2 = int(height * 0.82)
    roi = image_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return {"active": False, "score": 0.0, "template": "text-band", "scale": None, "location": None}

    b, g, r = cv2.split(roi.astype(np.int16))
    max_channel = np.maximum.reduce([r, g, b])
    min_channel = np.minimum.reduce([r, g, b])
    white_text = (r > 185) & (g > 185) & (b > 185) & ((max_channel - min_channel) < 55)
    white_count = int(np.count_nonzero(white_text))
    if white_count == 0:
        return {"active": False, "score": 0.0, "template": "text-band", "scale": None, "location": None}

    ys, xs = np.where(white_text)
    roi_width = roi.shape[1]
    roi_area = roi.shape[0] * roi_width
    white_ratio = white_count / roi_area
    col_ratio = np.count_nonzero(np.bincount(xs, minlength=roi_width) > 0) / roi_width
    span_ratio = (int(xs.max()) - int(xs.min()) + 1) / roi_width
    glyph_count = _booster_activate_text_glyph_count(white_text)
    active = (
        white_ratio >= BOOSTER_ACTIVATE_TEXT_MIN_WHITE_RATIO
        and col_ratio >= BOOSTER_ACTIVATE_TEXT_MIN_COL_RATIO
        and span_ratio >= BOOSTER_ACTIVATE_TEXT_MIN_SPAN_RATIO
        and glyph_count >= BOOSTER_ACTIVATE_TEXT_MIN_GLYPHS
    )
    score = min(
        1.0,
        0.40 * min(1.0, white_ratio / 0.11)
        + 0.35 * min(1.0, col_ratio / 0.60)
        + 0.25 * min(1.0, span_ratio / 0.70),
    )
    return {
        "active": bool(active),
        "score": float(score),
        "template": "text-band",
        "scale": None,
        "location": (int(x1 + xs.min()), int(y1 + ys.min())),
        "template_size": (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)),
        "match_type": "text_band",
        "glyph_count": int(glyph_count),
    }

def detect_booster_activate_in_image(image):
    image_bgr = _as_bgr_image(image)
    if image_bgr is None or image_bgr.size == 0:
        return {"active": False, "score": 0.0, "template": None, "scale": None, "location": None}

    image_gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    best = {"active": False, "score": 0.0, "template": None, "scale": None, "location": None}
    lower_word_best = best
    for template_path in BOOSTER_ACTIVATE_TEMPLATE_PATHS:
        template = load_booster_activate_word_template(template_path)
        if template is None:
            continue
        template_name = os.path.basename(template_path)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        full_match = _best_booster_activate_match(
            image_gray,
            template_gray,
            template_name,
            BOOSTER_ACTIVATE_THRESHOLD,
            "full_word",
        )
        if full_match["score"] > best["score"]:
            best = full_match
        lower_word = template_gray[template_gray.shape[0] // 3:, :]
        lower_match = _best_booster_activate_match(
            image_gray,
            lower_word,
            template_name,
            BOOSTER_ACTIVATE_LOWER_WORD_THRESHOLD,
            "lower_word",
        )
        if lower_match["score"] > lower_word_best["score"]:
            lower_word_best = lower_match
    if best["active"]:
        return best
    if lower_word_best["active"]:
        return lower_word_best
    text_band_match = _booster_activate_text_band_match(image_bgr)
    if text_band_match["active"]:
        return text_band_match
    return best if best["score"] >= lower_word_best["score"] else lower_word_best

def detect_booster_activate(screenshot_path=None):
    region = booster_activation_region()
    image = capture_debug_screenshot(screenshot_path, region=region)
    detection = detect_booster_activate_in_image(image)
    detection["region"] = region
    return detection

def special_template_paths(family, fallback_path):
    found_paths = []
    for color in SPECIAL_TEMPLATE_COLORS:
        for base_dir in (os.path.join("Match-Masters", "Sprite"), os.path.join("assets", "general")):
            path = os.path.join(base_dir, f"gem_{family}_{color}.png")
            if os.path.exists(path):
                found_paths.append(path)
                break
    return found_paths if found_paths else [fallback_path]

def special_template_color(path):
    filename = os.path.basename(path)
    for color_name, color_value in COLOR_NAME_TO_VALUE.items():
        if filename.endswith(f"_{color_name}.png"):
            return color_value
    return None

def general_special_threshold(family, color_value, default_threshold):
    if family == "bomb" and color_value == 1:
        return 0.50
    if family == "bomb" and color_value in {2, 3, 4, 5, 6}:
        return 0.65
    return default_threshold

def load_general_special_templates():
    templates = []
    template_types = []
    template_thresholds = []
    template_colors = []
    for family, special_type, threshold, fallback_path, fill_ratio in GENERAL_SPECIAL_SPECS:
        for path in special_template_paths(family, fallback_path):
            color_value = special_template_color(path)
            templates.append(load_and_resize_template(path, fill_ratio=fill_ratio, fit_to_tile=True))
            template_types.append(special_type)
            template_thresholds.append(general_special_threshold(family, color_value, threshold))
            template_colors.append(color_value)
    return templates, template_types, template_thresholds, template_colors

def load_heart_templates():
    templates = []
    masks = []
    template_colors = []
    template_thresholds = []
    for spec in HEART_TEMPLATE_SPECS:
        color_name, color_value, threshold = spec[:3]
        fill_ratio = spec[3] if len(spec) > 3 else 0.88
        path = os.path.join("assets", "general", f"gem_cupid_heart_{color_name}.png")
        template, mask = load_and_resize_rgba_template(path, fill_ratio=fill_ratio)
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_colors.append(color_value)
        template_thresholds.append(threshold)
    return templates, masks, template_colors, template_thresholds


def load_vinnie_se_heart_templates():
    templates = []
    masks = []
    template_colors = []
    template_specials = []
    template_thresholds = []
    color_specs = [spec for spec in COLOR_TEMPLATE_SPECS if spec[1] != WHITE_COLOR]
    for index, (first_name, first_value) in enumerate(color_specs):
        for second_name, second_value in color_specs[index + 1 :]:
            path = os.path.join(
                "assets",
                "general",
                f"vinnie_se_heart_{first_name}_{second_name}.png",
            )
            if not os.path.exists(path):
                continue
            template, mask = load_and_resize_rgba_template(path, fill_ratio=0.88)
            if template is None:
                continue
            templates.append(template)
            masks.append(mask)
            template_colors.append(first_value)
            template_specials.append(
                make_vinnie_se_heart_special(first_value, second_value)
            )
            template_thresholds.append(VINNIE_SE_HEART_TEMPLATE_THRESHOLD)
    return templates, masks, template_colors, template_specials, template_thresholds


def load_knight_templates():
    templates = []
    masks = []
    template_colors = []
    template_thresholds = []
    for color_name, color_value, threshold in KNIGHT_TEMPLATE_SPECS:
        path = os.path.join("assets", "general", f"charles_knight_{color_name}.png")
        template, mask = load_and_resize_rgba_template(path, fill_ratio=0.95)
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_colors.append(color_value)
        template_thresholds.append(threshold)
    return templates, masks, template_colors, template_thresholds

def load_cleo_bug_templates():
    template, mask = load_and_resize_rgba_template(
        os.path.join("assets", "general", "cleo_bug.png"),
        fill_ratio=1.0,
    )
    if template is None:
        return [], [], []
    return [template], [mask], [0.18]

def load_billie_drone_templates():
    template, mask = load_and_resize_rgba_template(
        os.path.join("assets", "general", "billie_drone.png"),
        fill_ratio=1.0,
    )
    if template is None:
        return [], [], []
    return [template], [mask], [BILLIE_DRONE_TEMPLATE_THRESHOLD]

def load_disco_ball_templates():
    template, mask = load_and_resize_rgba_template(
        os.path.join("assets", "general", "disco_ball.png"),
        fill_ratio=1.0,
    )
    if template is None:
        return [], [], []
    return [template], [mask], [0.18]

def load_all_aboard_bandit_templates():
    templates = []
    masks = []
    template_colors = []
    template_thresholds = []
    for color_name, color_value, threshold in ALL_ABOARD_BANDIT_TEMPLATE_SPECS:
        path = os.path.join("assets", "general", f"all_aboard_bandit_{color_name}.png")
        if not os.path.exists(path):
            continue
        template, mask = load_and_resize_rgba_template(path, fill_ratio=1.0)
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_colors.append(color_value)
        template_thresholds.append(threshold)
    return templates, masks, template_colors, template_thresholds

def load_joojoo_skull_templates():
    atlas_path = os.path.join("assets", "general", "joojoo-piece.png")
    atlas = (
        cv2.imread(atlas_path, cv2.IMREAD_UNCHANGED)
        if os.path.isfile(atlas_path)
        else None
    )
    if atlas is None:
        return [], [], []
    skull = atlas[134:193, 2:66]
    if skull.size == 0:
        return [], [], []
    target_width = int(squareSize * 0.75)
    scale_value = target_width / max(skull.shape[:2])
    resized = cv2.resize(skull, (0, 0), fx=scale_value, fy=scale_value)
    template = cv2.cvtColor(resized[:, :, :3], cv2.COLOR_BGR2RGB)
    mask = resized[:, :, 3]
    return [template], [mask], [JOOJOO_SKULL_TEMPLATE_THRESHOLD]

def load_color_crystal_templates():
    templates = []
    masks = []
    template_colors = []
    template_thresholds = []
    for color_name, color_value, threshold in COLOR_CRYSTAL_TEMPLATE_SPECS:
        template, mask = load_and_resize_rgba_template(
            os.path.join("assets", "modes", "color_crystals", f"color_crystal_{color_name}.png"),
            fill_ratio=0.95,
        )
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_colors.append(color_value)
        template_thresholds.append(threshold)
    return templates, masks, template_colors, template_thresholds

def load_mushroom_templates():
    templates = []
    masks = []
    template_colors = []
    template_thresholds = []
    for color_name, color_value, threshold in MUSHROOM_TEMPLATE_SPECS:
        template, mask = load_and_resize_rgba_template(
            os.path.join("assets", "modes", "multiplier_mushrooms", f"mushroom_{color_name}.png"),
            fill_ratio=0.95,
        )
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_colors.append(color_value)
        template_thresholds.append(threshold)
    return templates, masks, template_colors, template_thresholds

def load_firework_templates():
    templates = []
    masks = []
    template_types = []
    template_thresholds = []
    for filename, special_type, threshold in FIREWORK_TEMPLATE_SPECS:
        template, mask = load_and_resize_rgba_template(
            os.path.join("assets", "modes", "fireworks", filename),
            fill_ratio=1.0,
        )
        if template is None:
            continue
        templates.append(template)
        masks.append(mask)
        template_types.append(special_type)
        template_thresholds.append(threshold)
    return templates, masks, template_types, template_thresholds

def normalize_special_piece_mode(mode):
    if mode in {
        SPECIAL_PIECE_MODE_AUTO,
        SPECIAL_PIECE_MODE_NONE,
        SPECIAL_PIECE_MODE_HEARTS,
        SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS,
        SPECIAL_PIECE_MODE_KNIGHTS,
        SPECIAL_PIECE_MODE_CLEO,
        SPECIAL_PIECE_MODE_BILLIE,
        SPECIAL_PIECE_MODE_DISCO,
        SPECIAL_PIECE_MODE_HIGH_VOLTAGE,
        SPECIAL_PIECE_MODE_ALL_ABOARD,
        SPECIAL_PIECE_MODE_JOOJOO,
        SPECIAL_PIECE_MODE_MIXY_MEOW,
        SPECIAL_PIECE_MODE_UFO,
    }:
        return mode
    text = str(mode or "").strip().lower()
    if text in {"nista", "none", "nothing", "off", "bez", "bez boostera"}:
        return SPECIAL_PIECE_MODE_NONE
    if text in {"srca", "heart", "hearts"}:
        return SPECIAL_PIECE_MODE_HEARTS
    if text in {
        "vinnie se",
        "vinnie_se",
        "vinnie se srca",
        "vinnie_se_hearts",
        "se srca",
        "se hearts",
        "kindred hearts",
        "dvobojna srca",
    }:
        return SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS
    if text in {"konji", "konj", "knight", "knights"}:
        return SPECIAL_PIECE_MODE_KNIGHTS
    if text in {"cleo", "bug", "bugs", "buba", "bube"}:
        return SPECIAL_PIECE_MODE_CLEO
    if text in {"billie", "bili", "drone", "robot"}:
        return SPECIAL_PIECE_MODE_BILLIE
    if text in {"disco", "disko", "funky", "funky match", "broccoli", "brokoli"}:
        return SPECIAL_PIECE_MODE_DISCO
    if text in {"high voltage", "high_voltage", "voltage", "visoki napon"}:
        return SPECIAL_PIECE_MODE_HIGH_VOLTAGE
    if text in {"all aboard", "all_aboard", "aboard", "voz", "train"}:
        return SPECIAL_PIECE_MODE_ALL_ABOARD
    if text in {"joojoo", "joo joo", "joo-joo", "monkey", "majmun", "skull", "lobanja"}:
        return SPECIAL_PIECE_MODE_JOOJOO
    if text in {"mixy", "mixy meow", "mixy_meow", "meow", "kitty", "cat"}:
        return SPECIAL_PIECE_MODE_MIXY_MEOW
    if text in {"ufo", "ufo se", "ufo_se", "extractor", "ekstraktor", "oci", "oko"}:
        return SPECIAL_PIECE_MODE_UFO
    return SPECIAL_PIECE_MODE_AUTO

_templates_loaded_for_square_size = None


def ensure_templates_loaded(force=False):
    """Load the templates once per tile size; a repeat is a no-op."""
    global _templates_loaded_for_square_size
    if not force and _templates_loaded_for_square_size == squareSize:
        return
    load_templates()
    _templates_loaded_for_square_size = squareSize


def load_templates():
    global color_templates, special_templates, special_template_types, special_template_thresholds
    global special_template_colors
    global heart_templates, heart_template_masks, heart_template_colors, heart_template_thresholds
    global vinnie_se_heart_templates, vinnie_se_heart_template_masks
    global vinnie_se_heart_template_colors, vinnie_se_heart_template_specials
    global vinnie_se_heart_template_thresholds
    global knight_templates, knight_template_masks, knight_template_colors, knight_template_thresholds
    global cleo_bug_templates, cleo_bug_template_masks, cleo_bug_template_thresholds
    global billie_drone_templates, billie_drone_template_masks, billie_drone_template_thresholds
    global disco_ball_templates, disco_ball_template_masks, disco_ball_template_thresholds
    global all_aboard_bandit_templates, all_aboard_bandit_template_masks
    global all_aboard_bandit_template_colors, all_aboard_bandit_template_thresholds
    global joojoo_skull_templates, joojoo_skull_template_masks, joojoo_skull_template_thresholds
    global color_crystal_templates, color_crystal_template_masks, color_crystal_template_colors
    global color_crystal_template_thresholds
    global mushroom_templates, mushroom_template_masks, mushroom_template_colors, mushroom_template_thresholds
    global firework_mode_templates
    global firework_template_masks, firework_template_types, firework_template_thresholds
    global bounty, leaf, leaf_plus3, purple_gem_4, purple_gem_5, red_blue, chest, chest2

    # base colors templates:
    red = load_and_resize_template('assets/general/red.png')
    green = load_and_resize_template('assets/general/green.png')
    yellow = load_and_resize_template('assets/general/yellow.png')
    purple = load_and_resize_template('assets/general/purple.png')
    blue = load_and_resize_template('assets/general/blue.png')
    orange = load_and_resize_template('assets/general/orange.png')
    color_templates = [blue, green, yellow, purple, red, orange]

    # special templates:
    (
        special_templates,
        special_template_types,
        special_template_thresholds,
        special_template_colors,
    ) = load_general_special_templates()
    heart_templates, heart_template_masks, heart_template_colors, heart_template_thresholds = load_heart_templates()
    (
        vinnie_se_heart_templates,
        vinnie_se_heart_template_masks,
        vinnie_se_heart_template_colors,
        vinnie_se_heart_template_specials,
        vinnie_se_heart_template_thresholds,
    ) = load_vinnie_se_heart_templates()
    knight_templates, knight_template_masks, knight_template_colors, knight_template_thresholds = load_knight_templates()
    cleo_bug_templates, cleo_bug_template_masks, cleo_bug_template_thresholds = load_cleo_bug_templates()
    billie_drone_templates, billie_drone_template_masks, billie_drone_template_thresholds = load_billie_drone_templates()
    disco_ball_templates, disco_ball_template_masks, disco_ball_template_thresholds = load_disco_ball_templates()
    (
        all_aboard_bandit_templates,
        all_aboard_bandit_template_masks,
        all_aboard_bandit_template_colors,
        all_aboard_bandit_template_thresholds,
    ) = load_all_aboard_bandit_templates()
    (
        joojoo_skull_templates,
        joojoo_skull_template_masks,
        joojoo_skull_template_thresholds,
    ) = load_joojoo_skull_templates()
    (
        color_crystal_templates,
        color_crystal_template_masks,
        color_crystal_template_colors,
        color_crystal_template_thresholds,
    ) = load_color_crystal_templates()
    (
        mushroom_templates,
        mushroom_template_masks,
        mushroom_template_colors,
        mushroom_template_thresholds,
    ) = load_mushroom_templates()

    # modes templates:
    bounty = load_and_resize_template('assets/modes/bounty/bounty.png')
    leaf = load_and_resize_template('assets/modes/leafs/leaf.png')
    leaf_plus3 = load_and_resize_template('assets/modes/leafs/leaf_plus3.png', fill_ratio=1.0)
    purple_gem_4 = load_and_resize_template('assets/modes/purple_gem/purple_gem_4.png')
    purple_gem_5 = load_and_resize_template('assets/modes/purple_gem/purple_gem_5.png')
    red_blue = load_and_resize_template('assets/modes/red_blue/red_blue.png')
    chest = load_and_resize_template('assets/modes/chest/chest.png', fill_ratio=0.95)
    chest2 = load_and_resize_template('assets/modes/chest/chest2.png', fill_ratio=0.95)

    firework_mode_templates, firework_template_masks, firework_template_types, firework_template_thresholds = (
        load_firework_templates()
    )

def apply_board_profile(profile, *, allow_uncalibrated_layout=False):
    global left, up, width, height, squareSize, top_left_x, top_left_y, board_length
    global scale, display_scale, min_detect_range, max_detect_range, current_board_profile
    global calibrated_perk_slot_centers

    try:
        window_rect = None
        if has_relative_calibration(profile, _CONFIG_BASE_DIR):
            try:
                window_rect = find_bluestacks_client_rect()
            except RuntimeError as exc:
                # A saved relative profile is only safe when it can be anchored
                # to the real App Player window.  Do not silently click legacy
                # screen coordinates after the window disappears.
                raise RuntimeError(
                    "BlueStacks App Player nije dostupan za sacuvanu kalibraciju"
                ) from exc
        try:
            config = load_board_config(
                profile,
                base_dir=_CONFIG_BASE_DIR,
                window_rect=window_rect,
            )
        except BoardCalibrationError:
            if not allow_uncalibrated_layout:
                raise
            # Startup only: initialize templates and let the GUI open so the
            # user can reach "Kalibrisi ekran". Every real scan reapplies the
            # profile without this escape hatch and therefore remains blocked
            # until the current layout is calibrated.
            config = load_board_config(
                profile,
                base_dir=_CONFIG_BASE_DIR,
                window_rect=None,
            )
    except FileNotFoundError as exc:
        # Runs on every move from a worker thread: exit(1) raised SystemExit,
        # which `except Exception` there does not catch, so the thread died
        # without reporting and Auto hung on "racunam" for good.
        raise RuntimeError(f"Nema fajla kalibracije ekrana: {exc}") from exc

    if (
        not allow_uncalibrated_layout
        and int(config["squareSize"]) < MIN_PLAYABLE_SQUARE_SIZE
    ):
        # A minimized BlueStacks reports a ~160x28 client, which scales the
        # calibration to 2 px tiles: every swipe would land in one corner of
        # whatever is on screen. Checked before the globals change, so the
        # last good geometry stays in place until the window is back.
        raise RuntimeError(
            f"BlueStacks prozor je minimizovan ili premali "
            f"(polje {config['squareSize']} px) - ne igram dok se ne vrati"
        )
    left = config["left"]
    up = config["up"]
    width = config["width"]
    height = config["height"]
    squareSize = config["squareSize"]
    board_length = config["boardSize"]
    calibrated_perk_slot_centers = config.get("perkSlotCenters")

    top_left_x = left + squareSize // 2
    top_left_y = up + squareSize // 2

    # scale is calculated relative to the original expected squareSize of 88
    scale = squareSize / 88.0
    display_scale = display_scale_for_config(profile, squareSize)
    min_detect_range = max(1, int(2 * scale))  # min square size for check color in square
    max_detect_range = int(30 * scale)  # max square size for check color in square
    current_board_profile = profile
    # The production UI supports only ML-only recognition.  Do not load the
    # legacy board-template set in that mode; the trained ONNX model owns every
    # board cell, including mode targets.
    if normalize_ml_recognition_mode(ml_recognition_mode) != ML_RECOGNITION_ONLY:
        # The templates depend only on the tile size they are resized to. They
        # used to be re-read from disk (~100 PNGs) on every move; warm that is
        # ~20 ms, but on the first move of a match the emulator is loading the
        # level and the same reads queued behind its disk traffic for seconds
        # (setup_ms 3.4-5.3 s on match-opening runs, 2026-09-05..07).
        ensure_templates_loaded()

def square_color_detect(im, x, y, fireworks=False):
    include_white = normalize_game_mode(curr_mode) is GameMode.SPECIAL_O_RAMA
    curr_colors = color_palette(fireworks, include_white)
    for curr_range in range(min_detect_range, max_detect_range, 4):
        color_count = [0 for _ in curr_colors]
        curr_left = x - curr_range // 2
        curr_top = y - curr_range // 2
        for i in range(curr_range):
            for j in range(curr_range):
                pixel = im.getpixel((int(curr_left + i), int(curr_top + j)))
                curr_pixel = pixel_color_detect(pixel, fireworks, include_white)
                if curr_pixel != -1:
                    color_count[curr_pixel] += 1
        max_count = max(color_count)
        if max_count != 0:
                return color_count.index(max_count) + 1
    return 0

def detect_hot_color_state(image):
    def detect_regular_color(x, y):
        for curr_range in range(min_detect_range, max_detect_range, 4):
            color_count = [0 for _ in colors[:-1]]
            curr_left = x - curr_range // 2
            curr_top = y - curr_range // 2
            for i in range(curr_range):
                for j in range(curr_range):
                    pixel = image.getpixel((int(curr_left + i), int(curr_top + j)))
                    curr_pixel = pixel_color_detect(pixel, fireworks=False, include_white=False)
                    if curr_pixel != -1:
                        color_count[curr_pixel] += 1
            max_count = max(color_count)
            if max_count != 0:
                return color_count.index(max_count) + 1
        return 0

    current_x = left + 4 * squareSize
    next_x = current_x + squareSize // 2 + 12
    y = up + height + squareSize // 2
    return {
        "current": detect_regular_color(current_x, y),
        "next": detect_regular_color(next_x, y),
    }

# The suitcase is a UI popup anchored to the board *rectangle*, not to a cell:
# measured on live frames it sits at x 857-1062 -- centred on the board -- in
# both profiles, because SuperSize fits 8 cells into the same screen rectangle
# the regular board fills with 7 (592px against 588px). Sizing the crop in
# squareSize units therefore shrank it by 12% and pushed it 24px left on
# SuperSize (845-1011 against the regular 869-1058), cutting off the right-hand
# token of the code. The ratios below are the original regular-board constants
# divided by its 7 cells, so regular geometry is unchanged.
MIXY_CODE_REGION_LEFT_RATIO = 2.45 / 7.0
MIXY_CODE_REGION_TOP_RATIO = 1.15 / 7.0
MIXY_CODE_REGION_WIDTH_RATIO = 2.25 / 7.0
MIXY_CODE_REGION_HEIGHT_RATIO = 1.10 / 7.0
MIXY_REFERENCE_BOARD_WIDTH = 588.0


def _mixy_board_rect():
    """The board's screen size, falling back to the cell grid when uncalibrated."""
    grid = float((board_length or 7) * (squareSize or 84))
    return float(width or grid), float(height or grid)


def _mixy_scale_factor():
    """How much bigger the popup is drawn than on the reference 588px board."""
    board_width, _board_height = _mixy_board_rect()
    return max(0.5, board_width / MIXY_REFERENCE_BOARD_WIDTH)


def mixy_meow_code_region():
    """Screen area occupied by the Mixy suitcase above the board."""
    board_width, board_height = _mixy_board_rect()
    return (
        max(0, int(left + board_width * MIXY_CODE_REGION_LEFT_RATIO)),
        max(0, int(up - board_height * MIXY_CODE_REGION_TOP_RATIO)),
        max(1, int(board_width * MIXY_CODE_REGION_WIDTH_RATIO)),
        max(1, int(board_height * MIXY_CODE_REGION_HEIGHT_RATIO)),
    )


def _mixy_color_components(image):
    image_bgr = _as_bgr_image(image)
    if image_bgr is None or image_bgr.size == 0:
        return []
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    image_height, image_width = hsv.shape[:2]
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    # The purple piece is drawn as a pale lilac square (S~64, V~230), so a flat
    # S>=120 floor silently dropped every purple code token. Accept a washed-out
    # token only when it is also bright; the shape, area and "2-3 distinct
    # colors" guards below keep ordinary UI artwork out.
    saturated = ((saturation >= 120) & (value >= 100)) | (
        (saturation >= 50) & (value >= 190)
    )
    hue_ranges = (
        (RED, ((hue <= 8) | (hue >= 172))),
        (ORANGE, ((hue >= 9) & (hue <= 22))),
        (YELLOW, ((hue >= 23) & (hue <= 38))),
        (GREEN, ((hue >= 39) & (hue <= 82))),
        (BLUE, ((hue >= 83) & (hue <= 112))),
        (PURPLE, ((hue >= 125) & (hue <= 165))),
    )
    # The token is part of that popup, so it scales with the board rectangle too
    # -- not with the cell size, which SuperSize shrinks while the popup stays
    # the size it is on a regular board.
    scale_factor = _mixy_scale_factor()
    min_area = 300.0 * scale_factor * scale_factor
    max_area = 1700.0 * scale_factor * scale_factor
    min_side = 20.0 * scale_factor
    max_side = 58.0 * scale_factor
    # Pieces drawn with internal separator lines (the purple square) split into
    # thin horizontal slices, none of which reaches min_area on its own. Close
    # the mask so one token stays one component.
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (max(3, int(round(3 * scale_factor))), max(5, int(round(5 * scale_factor)))),
    )
    found = []
    for color, hue_mask in hue_ranges:
        mask = (hue_mask & saturated).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel)
        _, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        for stat, center in zip(stats[1:], centers[1:]):
            component_width = float(stat[cv2.CC_STAT_WIDTH])
            component_height = float(stat[cv2.CC_STAT_HEIGHT])
            area = float(stat[cv2.CC_STAT_AREA])
            aspect = component_width / max(1.0, component_height)
            if (
                min_area <= area <= max_area
                and min_side <= component_width <= max_side
                and min_side <= component_height <= max_side
                and 0.65 <= aspect <= 1.35
                and image_width * 0.15 <= float(center[0]) <= image_width * 0.85
                and image_height * 0.25 <= float(center[1]) <= image_height * 0.80
            ):
                found.append((color, float(center[0]), float(center[1]), area))
    return found


def detect_mixy_meow_code_state(image=None):
    region = mixy_meow_code_region()
    if image is None:
        image = capture_debug_screenshot(None, region=region, write_to_disk=False)
    else:
        image_width, image_height = image.size if isinstance(image, Image.Image) else (
            image.shape[1], image.shape[0]
        )
        x, y, region_width, region_height = region
        if (
            image_width > region_width * 1.5
            and image_height > region_height * 1.5
            and image_width >= x + region_width
            and image_height >= y + region_height
        ):
            if isinstance(image, Image.Image):
                image = image.crop((x, y, x + region_width, y + region_height))
            else:
                image = image[y:y + region_height, x:x + region_width]

    components = _mixy_color_components(image)
    # The popup always contains two or three large, round color tokens. Requiring
    # that pair is what keeps ordinary saturated UI artwork from activating Mixy.
    components.sort(key=lambda item: item[1])
    code_colors = tuple(dict.fromkeys(component[0] for component in components))
    active = 2 <= len(components) <= 3 and len(code_colors) == len(components)
    if not active:
        return MixyMeowState(
            active=False,
            code_colors=(),
            confidence=0.0,
            source="screen_color_tokens",
            reason=f"expected 2-3 Mixy color tokens, found {len(components)}",
        )

    mean_area = sum(component[3] for component in components) / len(components)
    expected_area = 950.0 * _mixy_scale_factor() ** 2
    area_quality = max(0.0, 1.0 - abs(mean_area - expected_area) / expected_area)
    confidence = min(0.99, 0.82 + 0.17 * area_quality)
    return MixyMeowState(
        active=True,
        code_colors=code_colors,
        confidence=confidence,
        source="screen_color_tokens",
        reason=f"detected {len(code_colors)} Mixy color tokens",
    )

# The module's casing: unsaturated grey, brighter than the rail behind it.
UFO_EYE_MAX_CASING_SATURATION = 70
UFO_EYE_MIN_CASING_VALUE = 110


def ufo_eye_region():
    """The rail strip above the board where the UFO eyes sit.

    Tall enough to hold a whole eye module including the few pixels it bobs up
    and down between animation frames, which means it reaches slightly into the
    first tile row. Tiles there are saturated, so they never survive the grey
    casing mask.
    """
    x = max(0, int(left - squareSize * 0.3))
    y = max(0, int(up - squareSize * 0.55))
    return (
        x,
        y,
        max(1, int(width + squareSize * 0.6)),
        max(1, int(up + squareSize * 0.12) - y),
    )


def _ufo_eye_components(image):
    """UFO eye modules found in the rail strip, left to right.

    Anchored on the module's grey metal casing, not on its green pupil. The
    pupil is only visible while the lens is open: at SuperSize scale the closed
    frame hides it completely, and even open it drifts about 10px vertically
    between frames, so keying on it lost live eyes both ways. The casing is a
    fixed ~0.5x0.5 cell square present in every frame; nothing else on the rail
    has that shape.
    """
    image_bgr = _as_bgr_image(image)
    if image_bgr is None or image_bgr.size == 0:
        return []
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    casing = (
        (saturation < UFO_EYE_MAX_CASING_SATURATION)
        & (value > UFO_EYE_MIN_CASING_VALUE)
    ).astype(np.uint8)
    # The lens splits the casing into a ring plus separate blades; close it so
    # one module stays one component.
    casing = cv2.morphologyEx(casing, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    scale_factor = max(0.5, float(squareSize or 84) / 84.0)
    # Gates in cell-84 units, measured across both board profiles.
    #
    # Area varies far more than the shape does, because the open lens is dark
    # and contributes nothing to the mask while the shut one adds its bright
    # blades: the same eye reads 589 open and 953-1046 closed on the 7x7 board.
    # A 600 floor tuned on the 8x8 board therefore threw away every open eye at
    # 7x7 -- eight of thirteen live frames -- so the floor is now well clear of
    # the smallest real casing and the shape gates do the work.
    #
    # Casing spans 46-49 units tall and 42-57 wide. Rail sparkles reach 53 tall
    # but 73 wide, so width is what rejects the closest negative.
    min_area = 450.0 * scale_factor * scale_factor
    min_width = 38.0 * scale_factor
    max_width = 64.0 * scale_factor
    min_height = 42.0 * scale_factor
    max_height = 54.0 * scale_factor
    found = []
    _, _, stats, centers = cv2.connectedComponentsWithStats(casing)
    for stat, center in zip(stats[1:], centers[1:]):
        if float(stat[cv2.CC_STAT_AREA]) < min_area:
            continue
        component_width = float(stat[cv2.CC_STAT_WIDTH])
        component_height = float(stat[cv2.CC_STAT_HEIGHT])
        if not min_width <= component_width <= max_width:
            continue
        if not min_height <= component_height <= max_height:
            continue
        found.append(
            (float(center[0]), float(stat[cv2.CC_STAT_AREA]), component_height)
        )
    found.sort(key=lambda item: item[0])
    # The closed lens leaves a smaller disc nested inside the casing; it fails
    # the size gate, but keep the merge in case a frame ever splits one module
    # into two accepted blobs.
    merged = []
    min_separation = 30.0 * scale_factor
    for component in found:
        if merged and component[0] - merged[-1][0] < min_separation:
            continue
        merged.append(component)
    return merged


def detect_ufo_eye_state(image=None):
    region = ufo_eye_region()
    if image is None:
        image = capture_debug_screenshot(None, region=region, write_to_disk=False)
    else:
        image_width, image_height = image.size if isinstance(image, Image.Image) else (
            image.shape[1], image.shape[0]
        )
        x, y, region_width, region_height = region
        if (
            image_width > region_width * 1.5
            and image_height > region_height * 1.5
            and image_width >= x + region_width
            and image_height >= y + region_height
        ):
            if isinstance(image, Image.Image):
                image = image.crop((x, y, x + region_width, y + region_height))
            else:
                image = image[y:y + region_height, x:x + region_width]

    components = _ufo_eye_components(image)
    eyes = len(components)
    if eyes <= 0 or eyes > UFO_MAX_EYES:
        return UfoState(
            eyes=0,
            confidence=0.0,
            source="screen_eye_modules",
            reason=f"expected 1-{UFO_MAX_EYES} UFO eyes, found {eyes}",
        )

    # Casing area measured 688-815 in cell-84 units across the live frames.
    expected_area = 750.0 * max(0.5, float(squareSize or 84) / 84.0) ** 2
    area_quality = min(
        max(
            0.0,
            1.0
            - abs(sum(item[1] for item in components) / eyes - expected_area)
            / expected_area,
        ),
        1.0,
    )
    confidence = min(0.99, 0.82 + 0.17 * area_quality)
    return UfoState(
        eyes=eyes,
        confidence=confidence,
        source="screen_eye_modules",
        reason=f"detected {eyes} UFO eye(s)",
    )


def color_palette(fireworks=False, include_white=False):
    if fireworks:
        return firework_color
    if include_white:
        return colors
    return colors[:-1]

def pixel_color_detect(pixel, fireworks=False, include_white=False):
    r = pixel[0]
    g = pixel[1]
    b = pixel[2]
    curr_colors = color_palette(fireworks, include_white)
    for i in range(len(curr_colors)):
        curr_color = curr_colors[i]
        if math.sqrt((curr_color[0] - r) ** 2 + (curr_color[1] - g) ** 2 + (curr_color[2] - b) ** 2) < pixel_color_detect_range:
            return i
    return -1

def _use_fireworks_palette_for_general_special(special_type):
    return special_type in {SPECIAL_LIGHTNING, SPECIAL_CROSSHAIR}

def create_board():
    return [[0 for i in range(board_length)] for j in range(board_length)]


def set_ml_recognition_mode(mode) -> str:
    global ml_recognition_mode
    ml_recognition_mode = normalize_ml_recognition_mode(mode)
    return ml_recognition_mode


def _is_mode_specific_baseline(special_value: int) -> bool:
    return special_value == SPECIAL_MODE_TARGET


def _is_color_agnostic_special_prediction(prediction) -> bool:
    return prediction.predicted_class in COLOR_AGNOSTIC_SPECIAL_CLASSES


# An extra-move star tile can legitimately appear on a neutral (mode=None)
# versus/showdown board: matching onto it grants an extra move regardless of any
# color objective. But the recognizer also occasionally hallucinates one during
# refill animations, and on a None board there is no game-mode context to
# corroborate it. So instead of rejecting every xtra prediction outright, trust
# it only when the model is highly confident; transient low-confidence false
# positives are still dropped. (The trained xtra classes validate at ~1.0, so
# genuine tiles clear this comfortably.)
XTRA_MOVE_NONE_MODE_CONFIDENCE_FLOOR = 0.9


def _is_xtra_move_out_of_mode_prediction(prediction, active_game_mode) -> bool:
    return (
        prediction.special_value == SPECIAL_XTRA_MOVE_TILE
        and normalize_game_mode(active_game_mode) is GameMode.NONE
        and prediction.confidence < XTRA_MOVE_NONE_MODE_CONFIDENCE_FLOOR
    )


def _accepted_prediction(prediction, reason: str):
    return replace(prediction, accepted=True, reason=reason)


def _rejected_prediction(prediction, reason: str):
    return replace(prediction, accepted=False, reason=reason)


ML_ONLY_COLOR_BOUND_SPECIAL_CONFIDENCE_FLOOR = 0.45
ML_ONLY_NORMAL_CONFIDENCE_FLOOR = 0.50
HOT_COLOR_NORMAL_CONFIDENCE_FLOOR = 0.45


def _can_ml_only_accept_below_class_threshold(prediction) -> bool:
    return (
        prediction.special_value != 0
        and not _is_color_agnostic_special_prediction(prediction)
        and prediction.confidence >= ML_ONLY_COLOR_BOUND_SPECIAL_CONFIDENCE_FLOOR
    )


def _mode_target_prediction_values(
    active_game_mode,
    fallback_board_value: int,
    fallback_special_value: int,
) -> tuple[int, int]:
    mode = normalize_game_mode(active_game_mode)
    if mode is GameMode.RED_AND_BLUE:
        return BLUE, SPECIAL_RED_BLUE_TILE
    board_value = {
        GameMode.PURPLE_GEM: PURPLE,
        GameMode.GREEN_LEAF: GREEN,
        GameMode.BOUNTY: ORANGE,
        GameMode.CHEST: CHEST_COLOR,
    }.get(mode, fallback_board_value)
    return board_value, fallback_special_value


def _resolve_prediction_values(
    prediction,
    active_game_mode,
    *,
    purple_family_fallback: bool = False,
) -> tuple[int, int]:
    if prediction.special_value != SPECIAL_MODE_TARGET:
        return prediction.board_value, prediction.special_value
    if (
        normalize_game_mode(active_game_mode) is GameMode.PURPLE_GEM
        and prediction.predicted_class in PURPLE_GEM_CLASSES
    ):
        value = (
            25
            if purple_family_fallback
            else int(prediction.predicted_class.rsplit("_", 1)[1])
        )
        return PURPLE, make_purple_gem_special(value)
    return _mode_target_prediction_values(
        active_game_mode,
        prediction.board_value,
        prediction.special_value,
    )


def _can_ml_only_accept_normal_below_class_threshold(prediction) -> bool:
    return (
        prediction.predicted_class.endswith("_normal")
        and prediction.special_value == 0
        and prediction.confidence >= ML_ONLY_NORMAL_CONFIDENCE_FLOOR
    )


def _can_hot_color_accept_normal_below_class_threshold(
    prediction,
    active_game_mode,
) -> bool:
    return (
        normalize_game_mode(active_game_mode) is HOT_COLOR_MODE
        and prediction.predicted_class.endswith("_normal")
        and prediction.special_value == 0
        and prediction.confidence >= HOT_COLOR_NORMAL_CONFIDENCE_FLOOR
    )


def _is_hot_color_prediction(prediction) -> bool:
    return hot_color_class_details(prediction.predicted_class) is not None


_HOT_COLOR_NORMAL_CLASSES = {
    GREEN: "green_normal",
    YELLOW: "yellow_normal",
    PURPLE: "purple_normal",
    ORANGE: "orange_normal",
}
HOT_COLOR_AUTO_MIN_TILES = 3
HOT_COLOR_AUTO_VALUE4_MIN_CONFIDENCE = 0.75
HOT_COLOR_AUTO_VALUE4_MIN_MARGIN = 0.04
HOT_COLOR_AUTO_VALUE4_COUNT_MIN_TILES = 5
HOT_COLOR_AUTO_VALUE4_COUNT_MIN_CONFIDENCE = 0.55
HOT_COLOR_AUTO_VALUE4_COUNT_MIN_LEAD = 3
HOT_COLOR_CONSENSUS_MIN_TILE_CONFIDENCE = 0.40
HOT_COLOR_INDIVIDUAL_MIN_CONFIDENCE = 0.98


def _hot_color_consensus(predictions, *, accepted_only: bool) -> dict | None:
    candidates: dict[tuple[int, int], list[float]] = {}
    for prediction in predictions:
        if accepted_only and not prediction.accepted:
            continue
        if not math.isfinite(prediction.confidence):
            continue
        details = hot_color_class_details(prediction.predicted_class)
        if details is None:
            continue
        candidates.setdefault(details, []).append(float(prediction.confidence))
    if not candidates:
        return None
    ranked = sorted(
        candidates.items(),
        # The numbered active tiles are visually decisive and normally sit near
        # 1.0 confidence. Plain tiles of other colors can weakly resemble their
        # numbered sibling, so group size must not outrank visual confidence.
        key=lambda item: (
            sum(item[1]) / len(item[1]),
            len(item[1]),
            sum(item[1]),
        ),
        reverse=True,
    )
    (color, value), confidences = ranked[0]
    selection = "confidence"
    color_tile_count = len(confidences)

    # Value 4 is the one Hot Color appearance that ordinary colored tiles most
    # often resemble.  A single false color can therefore have the highest
    # confidence, while the real active color owns most numbered tiles.  Let a
    # large, clearly count-dominant value-4 group win without weakening the
    # confidence-based rule for smaller/ambiguous groups.
    ranked_by_count = sorted(
        candidates.items(),
        key=lambda item: (
            len(item[1]),
            sum(item[1]) / len(item[1]),
        ),
        reverse=True,
    )
    (count_color, count_value), count_confidences = ranked_by_count[0]
    runner_up_count = (
        len(ranked_by_count[1][1]) if len(ranked_by_count) > 1 else 0
    )
    count_confidence = sum(count_confidences) / len(count_confidences)
    if (
        count_value == 4
        and len(count_confidences) >= HOT_COLOR_AUTO_VALUE4_COUNT_MIN_TILES
        and count_confidence >= HOT_COLOR_AUTO_VALUE4_COUNT_MIN_CONFIDENCE
        and len(count_confidences) - runner_up_count
        >= HOT_COLOR_AUTO_VALUE4_COUNT_MIN_LEAD
    ):
        color, value = count_color, count_value
        confidences = count_confidences
        color_tile_count = len(count_confidences)
        selection = "count_dominant_value_four"

    # Plain tiles are most often confused with the *_hot_color_4 sibling.
    # A coherent run of value 3/5 predictions is therefore stronger mode
    # evidence than an unrelated color's larger, weak value-4 group. Aggregate
    # 3/5 siblings by color first, then use the majority value for that color.
    non_four_by_color: dict[int, list[tuple[int, float]]] = {}
    for (candidate_color, candidate_value), values in candidates.items():
        if candidate_value == 4:
            continue
        non_four_by_color.setdefault(candidate_color, []).extend(
            (candidate_value, confidence) for confidence in values
        )
    if non_four_by_color:
        non_four_color, colored_values = max(
            non_four_by_color.items(),
            key=lambda item: (
                len(item[1]),
                sum(confidence for _value, confidence in item[1]) / len(item[1]),
            ),
        )
        if len(colored_values) >= HOT_COLOR_AUTO_MIN_TILES:
            values_by_number: dict[int, list[float]] = {}
            for candidate_value, confidence in colored_values:
                values_by_number.setdefault(candidate_value, []).append(confidence)
            value, confidences = max(
                values_by_number.items(),
                key=lambda item: (
                    len(item[1]),
                    sum(item[1]) / len(item[1]),
                ),
            )
            color = non_four_color
            color_tile_count = len(colored_values)
            selection = "numbered_value_group"

    runner_up_confidence = (
        max(
            (
                sum(values) / len(values)
                for details, values in ranked
                if details != (color, value)
            ),
            default=0.0,
        )
        if ranked
        else 0.0
    )
    runner_up_tile_count = max(
        (len(values) for details, values in candidates.items() if details != (color, value)),
        default=0,
    )
    return {
        "current": int(color),
        "value": int(value),
        "source": "ml_hot_color_tiles",
        "tile_count": len(confidences),
        "color_tile_count": color_tile_count,
        "confidence": sum(confidences) / len(confidences),
        "runner_up_confidence": runner_up_confidence,
        "runner_up_tile_count": runner_up_tile_count,
        "selection": selection,
        "conflicts": sum(len(values) for key, values in candidates.items() if key != (color, value)),
    }


def hot_color_auto_candidate_from_predictions(predictions) -> dict | None:
    """Return strong board evidence that Auto may use to select Hot Color."""
    state = _hot_color_consensus(predictions, accepted_only=False)
    if state is None:
        return None
    margin = float(state["confidence"]) - float(state["runner_up_confidence"])
    if state["selection"] in {
        "numbered_value_group",
        "count_dominant_value_four",
    }:
        if (
            int(state["color_tile_count"]) < HOT_COLOR_AUTO_MIN_TILES
            or float(state["confidence"]) < HOT_COLOR_CONSENSUS_MIN_TILE_CONFIDENCE
        ):
            return None
    elif (
        int(state["tile_count"]) < HOT_COLOR_AUTO_MIN_TILES
        or float(state["confidence"]) < HOT_COLOR_AUTO_VALUE4_MIN_CONFIDENCE
        or margin < HOT_COLOR_AUTO_VALUE4_MIN_MARGIN
    ):
        return None
    state["source"] = "ml_hot_color_auto_detection"
    state["confidence_margin"] = margin
    return state


def hot_color_state_from_predictions(predictions) -> dict | None:
    """Resolve the live Hot Color/value from accepted numbered tile classes."""
    state = _hot_color_consensus(predictions, accepted_only=True)
    if state is not None:
        state["demoted_conflicts"] = sum(
            prediction.reason == "hot_color_conflict_demoted_to_normal"
            for prediction in predictions
        )
    return state


def _record_hot_color_diag(_diag, applied_result, active_game_mode) -> None:
    global last_hot_color_state
    if normalize_game_mode(active_game_mode) is not HOT_COLOR_MODE:
        last_hot_color_state = None
        if _diag is not None:
            _diag["hot_color_state"] = None
        return
    last_hot_color_state = hot_color_state_from_predictions(
        applied_result.predictions
    )
    if _diag is not None:
        _diag["hot_color_state"] = last_hot_color_state


def _purple_gem_family_accepts(prediction, active_game_mode) -> bool:
    """Keep an out-of-range Purple Gem when only its number is uncertain.

    The top class must already be a gem class, so this never invents a target on
    a plain tile; it only rescues gems whose printed value the model has never
    been trained on (currently anything above ``purple_gem_22``).
    """
    if normalize_game_mode(active_game_mode) is not GameMode.PURPLE_GEM:
        return False
    if (
        prediction.predicted_class not in PURPLE_GEM_CLASSES
        and prediction.predicted_class != "mode_target"
    ):
        return False
    family_confidence = getattr(prediction, "mode_target_family_confidence", None)
    return (
        family_confidence is not None
        and math.isfinite(family_confidence)
        and family_confidence >= PURPLE_GEM_FAMILY_FALLBACK_MIN_CONFIDENCE
    )


def _color_agnostic_special_min_confidence(prediction, active_game_mode) -> float:
    if prediction.predicted_class in PURPLE_GEM_CLASSES:
        # Several numbered Purple Gem classes legitimately calibrate to a zero
        # threshold because confusing one number for another is harmless to
        # the board engine. Keep the proven live 0.30 floor so arbitrary weak
        # guesses still cannot become targets.
        return PURPLE_GEM_MODE_TARGET_MIN_CONFIDENCE
    if prediction.predicted_class in MODE_SPECIFIC_TARGET_CLASS_MODES:
        # The visual class itself identifies the target family. Its learned
        # class threshold remains authoritative; the mode gate below prevents
        # it from leaking into another game mode.
        return 0.0
    if prediction.predicted_class == "mode_target":
        mode = normalize_game_mode(active_game_mode)
        if mode is GameMode.PURPLE_GEM:
            return PURPLE_GEM_MODE_TARGET_MIN_CONFIDENCE
        if mode is GameMode.GREEN_LEAF:
            return GREEN_LEAF_MODE_TARGET_MIN_CONFIDENCE
    return COLOR_AGNOSTIC_SPECIAL_MIN_CONFIDENCE


def apply_ml_recognition_overlay(
    board,
    special_board,
    ml_result: RecognitionMlResult,
    active_game_mode=None,
):
    global last_hot_color_auto_candidate
    if not ml_result.available:
        return ml_result

    if ml_result.mode == ML_RECOGNITION_SHADOW:
        return replace(
            ml_result,
            predictions=[
                _rejected_prediction(prediction, "shadow_mode")
                for prediction in ml_result.predictions
            ],
        )

    if ml_result.mode not in {
        ML_RECOGNITION_HYBRID,
        ML_RECOGNITION_FIRST,
        ML_RECOGNITION_ONLY,
    }:
        return ml_result

    ml_primary = ml_result.mode in {ML_RECOGNITION_FIRST, ML_RECOGNITION_ONLY}
    last_hot_color_auto_candidate = hot_color_auto_candidate_from_predictions(
        ml_result.predictions
    )
    is_hot_color_mode = normalize_game_mode(active_game_mode) is HOT_COLOR_MODE
    hot_color_consensus = None
    if is_hot_color_mode:
        hot_color_consensus = _hot_color_consensus(
            ml_result.predictions,
            accepted_only=False,
        )
    active_hot_details = None
    if hot_color_consensus is not None:
        active_hot_details = (
            hot_color_consensus["current"],
            hot_color_consensus["value"],
        )
    hot_color_consensus_is_trusted = bool(
        hot_color_consensus is not None
        and int(hot_color_consensus.get("color_tile_count", 0))
        >= HOT_COLOR_AUTO_MIN_TILES
        and (
            hot_color_consensus.get("selection")
            in {"numbered_value_group", "count_dominant_value_four"}
            or float(hot_color_consensus.get("confidence", 0.0))
            >= HOT_COLOR_AUTO_VALUE4_MIN_CONFIDENCE
        )
    )
    # Rebuilt from scratch every scan: a cell that stops reading as one of these
    # classes drops out, so an animation frame can never bank a confirmation for
    # a later burst at the same cell.
    previous_transient_cells = dict(pending_transient_ml_cells)
    transient_cells = {}
    decisions = []
    for prediction in ml_result.predictions:
        current_board = board[prediction.row][prediction.col]
        current_special = special_board[prediction.row][prediction.col]
        if prediction.predicted_class == "empty":
            decisions.append(_rejected_prediction(prediction, "empty_rejected"))
            continue
        effective_threshold = prediction.threshold
        if (
            prediction.predicted_class == "mode_target"
            and normalize_game_mode(active_game_mode) is GameMode.PURPLE_GEM
        ):
            effective_threshold = min(
                effective_threshold, PURPLE_GEM_MODE_TARGET_MIN_CONFIDENCE
            )
        if not math.isfinite(prediction.confidence) or not math.isfinite(effective_threshold):
            decisions.append(_rejected_prediction(prediction, "non_finite_ml_score"))
            continue
        expected_target_mode = MODE_SPECIFIC_TARGET_CLASS_MODES.get(
            prediction.predicted_class
        )
        if (
            expected_target_mode is not None
            and normalize_game_mode(active_game_mode) is not expected_target_mode
        ):
            decisions.append(
                _rejected_prediction(prediction, "mode_target_class_out_of_mode")
            )
            continue
        hot_details = hot_color_class_details(prediction.predicted_class)
        demote_hot_prediction = hot_details is not None and (
            not is_hot_color_mode
            or (
                active_hot_details is not None
                and hot_details != active_hot_details
            )
        )
        if demote_hot_prediction:
            normal_class = _HOT_COLOR_NORMAL_CLASSES.get(hot_details[0])
            if normal_class is not None:
                normal_prediction = replace(
                    prediction,
                    predicted_class=normal_class,
                    special_value=0,
                )
                board[prediction.row][prediction.col] = normal_prediction.board_value
                special_board[prediction.row][prediction.col] = 0
                decisions.append(
                    _accepted_prediction(
                        normal_prediction,
                        (
                            "hot_color_conflict_demoted_to_normal"
                            if is_hot_color_mode
                            else "hot_color_out_of_mode_demoted_to_normal"
                        ),
                    )
                )
                continue
        consensus_accepts_hot_tile = bool(
            hot_color_consensus_is_trusted
            and hot_details == active_hot_details
            and prediction.confidence >= HOT_COLOR_CONSENSUS_MIN_TILE_CONFIDENCE
        )
        individual_accepts_hot_tile = bool(
            is_hot_color_mode
            and hot_details == active_hot_details
            and prediction.confidence >= HOT_COLOR_INDIVIDUAL_MIN_CONFIDENCE
        )
        if (
            prediction.threshold > 1.0
            and not consensus_accepts_hot_tile
            and not individual_accepts_hot_tile
        ):
            decisions.append(_rejected_prediction(prediction, "threshold_disabled"))
            continue
        if (
            _is_color_agnostic_special_prediction(prediction)
            and prediction.confidence
            < _color_agnostic_special_min_confidence(prediction, active_game_mode)
            and not _purple_gem_family_accepts(prediction, active_game_mode)
        ):
            decisions.append(
                _rejected_prediction(prediction, "color_agnostic_special_below_minimum")
            )
            continue
        if prediction.confidence < effective_threshold:
            if consensus_accepts_hot_tile:
                acceptance_reason = "hot_color_consensus"
            elif individual_accepts_hot_tile:
                acceptance_reason = "hot_color_individual_high_confidence"
            elif _can_hot_color_accept_normal_below_class_threshold(
                prediction,
                active_game_mode,
            ):
                acceptance_reason = "hot_color_normal_confidence_floor"
            elif (
                ml_result.mode == ML_RECOGNITION_ONLY
                and normalize_game_mode(active_game_mode) is not HOT_COLOR_MODE
                and prediction.predicted_class.endswith("_normal")
                and prediction.normal_color_family_confidence is not None
                and math.isfinite(prediction.normal_color_family_confidence)
                and prediction.normal_color_family_confidence
                >= ML_ONLY_NORMAL_CONFIDENCE_FLOOR
            ):
                acceptance_reason = "ml_only_normal_color_family"
            elif (
                ml_result.mode == ML_RECOGNITION_ONLY
                and _can_ml_only_accept_normal_below_class_threshold(prediction)
            ):
                acceptance_reason = "ml_only_normal_confidence_floor"
            elif (
                ml_result.mode == ML_RECOGNITION_ONLY
                and _can_ml_only_accept_below_class_threshold(prediction)
            ):
                acceptance_reason = "ml_only_confidence_floor"
            elif _purple_gem_family_accepts(prediction, active_game_mode):
                acceptance_reason = "purple_gem_family_confidence"
            else:
                decisions.append(_rejected_prediction(prediction, "confidence_below_threshold"))
                continue
        else:
            acceptance_reason = "confidence_pass"
        if (
            normalize_game_mode(active_game_mode) is GameMode.INFINITE_MOVES
            and prediction.special_value == SPECIAL_XTRA_MOVE_TILE
        ):
            # The shipped Infinite Moves rules disable extra moves. Animated
            # beams can still make a normal colored tile look like an XTRA tile
            # (the latest saved run did exactly that). Preserve a confidently
            # recognized base color, but never create/score a fake extra move.
            # Confidence gating above remains authoritative for obscured colors.
            prediction = replace(
                prediction,
                predicted_class=prediction.predicted_class.replace(
                    "_xtra_move", "_normal"
                ),
                special_value=0,
            )
            acceptance_reason = "infinite_moves_xtra_demoted_to_normal"
        if (
            not ml_primary
            and _is_mode_specific_baseline(current_special)
            and prediction.special_value == 0
        ):
            decisions.append(_rejected_prediction(prediction, "mode_specific_baseline"))
            continue
        if not ml_primary and current_special != 0:
            decisions.append(_rejected_prediction(prediction, "existing_special_protected"))
            continue
        if _is_xtra_move_out_of_mode_prediction(prediction, active_game_mode):
            decisions.append(_rejected_prediction(prediction, "xtra_move_out_of_mode"))
            continue
        if (
            not ml_primary
            and current_board != 0
            and prediction.special_value != 0
            and prediction.board_value != current_board
            and not _is_color_agnostic_special_prediction(prediction)
            and prediction.predicted_class != "lotus"
        ):
            decisions.append(_rejected_prediction(prediction, "special_color_mismatch"))
            continue

        cell_key = (prediction.row, prediction.col)
        if prediction.predicted_class in ANIMATION_PRONE_ML_CLASSES:
            # Carry the class forward either way: seen once it is still pending,
            # seen twice it stays trusted for as long as it keeps reading the
            # same, so a confirmed lotus does not flicker back to unrecognized.
            seen_before = (
                previous_transient_cells.get(cell_key) == prediction.predicted_class
            )
            transient_cells[cell_key] = prediction.predicted_class
            if not seen_before:
                decisions.append(
                    _rejected_prediction(prediction, "transient_awaiting_confirmation")
                )
                continue

        resolved_board_value, resolved_special_value = _resolve_prediction_values(
            prediction,
            active_game_mode,
            purple_family_fallback=(
                acceptance_reason == "purple_gem_family_confidence"
            ),
        )
        resolved_prediction = replace(
            prediction,
            board_value=resolved_board_value,
            special_value=resolved_special_value,
        )
        board[prediction.row][prediction.col] = resolved_prediction.board_value
        special_board[prediction.row][prediction.col] = resolved_prediction.special_value
        decisions.append(_accepted_prediction(resolved_prediction, acceptance_reason))

    pending_transient_ml_cells.clear()
    pending_transient_ml_cells.update(transient_cells)

    return replace(ml_result, predictions=decisions)


def _set_ml_diag_off(_diag, mode):
    if _diag is None:
        return
    _diag["ml_recognition_mode"] = mode
    _diag["ml_available"] = False
    _diag["ml_predictions"] = 0
    _diag["ml_accepted"] = 0
    _diag["ml_rejected"] = 0
    _diag["ml_fast_path"] = False


def _record_ml_diag(
    _diag,
    applied_result,
    template_board,
    template_special_board,
    board,
    special_board,
    fast_path=False,
    blocked=False,
    block_reason=None,
):
    if _diag is None:
        return

    accepted = sum(1 for prediction in applied_result.predictions if prediction.accepted)
    rejected = len(applied_result.predictions) - accepted
    _diag["ml_recognition_mode"] = applied_result.mode
    _diag["ml_available"] = applied_result.available
    _diag["ml_model_version"] = applied_result.model_version
    _diag["ml_inference_ms"] = applied_result.inference_ms
    _diag["ml_predictions"] = len(applied_result.predictions)
    _diag["ml_accepted"] = accepted
    _diag["ml_rejected"] = rejected
    _diag["ml_unavailable_reason"] = applied_result.load_error
    _diag["ml_fast_path"] = fast_path
    _diag["ml_primary_blocked"] = False
    payload = ml_recognition_runtime.build_ml_debug_payload(
        applied_result,
        template_board,
        template_special_board,
        board,
        special_board,
    )
    payload.setdefault("summary", {})["fast_path"] = fast_path
    payload["summary"]["blocked"] = False
    if fast_path:
        payload["summary"]["template_baseline"] = "skipped"
    if blocked:
        _diag["ml_primary_blocked"] = True
        if applied_result.mode == ML_RECOGNITION_ONLY:
            _diag["ml_only_blocked"] = True
        payload["summary"]["blocked"] = True
        payload["summary"]["block_reason"] = block_reason
    _diag["ml_debug_payload"] = payload


def _restore_board(target, source):
    target[:] = [row[:] for row in source]


def _ml_primary_failure_reason(applied_result, accepted, expected_cells, board):
    if not applied_result.available:
        return "ml_unavailable"
    if len(applied_result.predictions) != expected_cells:
        return "incomplete_ml_predictions"
    if accepted != expected_cells:
        return "incomplete_ml_board"
    if not check_fill(board):
        return "invalid_ml_board"
    return "unknown"


def _set_ml_primary_blocked_timings(_diag):
    if _diag is None:
        return
    _diag["non_ml_templates_ms"] = 0.0
    _diag.setdefault("mode_specific_ms", 0.0)
    _diag["color_fallback_ms"] = 0.0


def _predict_board_tiles_with_line_resilience(
    img_color,
    mode,
    _diag=None,
    jelly_cells=(),
):
    """Classify normally, then retry cells hidden by a beam or the jelly overlay."""
    rows, columns = detect_board_overlay_lines(img_color)
    line_cells = {
        (row, col)
        for row in range(board_length)
        for col in range(board_length)
        if row in rows or col in columns
    }
    jelly_ml_cells = set(jelly_zone_ml_cells(jelly_cells))
    retry_cells = line_cells | jelly_ml_cells
    if _diag is not None:
        _diag["overlay_line_rows"] = list(rows)
        _diag["overlay_line_columns"] = list(columns)
        _diag["overlay_line_cells"] = [list(cell) for cell in sorted(line_cells)]
        _diag["overlay_line_ml_second_pass"] = False
        _diag["overlay_line_corrected_predictions"] = 0
        _diag["jelly_overlay_ml_cells"] = [list(cell) for cell in sorted(jelly_ml_cells)]

    base_result = ml_recognition_runtime.predict_board_tiles(
        img_color,
        board_length,
        squareSize,
        mode,
    )
    if not base_result.available:
        return base_result
    if not retry_cells:
        return _with_structureless_xtra_demoted(img_color, base_result, _diag)

    prepared = img_color
    if jelly_ml_cells:
        prepared = prepare_board_image_without_jelly_overlay(prepared, jelly_cells)
    if line_cells:
        prepared = prepare_board_image_without_overlay_lines(prepared, line_cells)
    corrected_result = ml_recognition_runtime.predict_board_tiles(
        prepared,
        board_length,
        squareSize,
        mode,
    )
    if _diag is not None:
        _diag["overlay_line_ml_second_pass"] = True
    if not corrected_result.available:
        return _with_structureless_xtra_demoted(img_color, base_result, _diag)

    corrected_by_cell = {
        (prediction.row, prediction.col): prediction
        for prediction in corrected_result.predictions
    }
    merged_predictions = []
    corrected_count = 0
    for prediction in base_result.predictions:
        cell = (prediction.row, prediction.col)
        corrected = corrected_by_cell.get(cell)
        choose_corrected = False
        if cell in retry_cells and corrected is not None:
            if corrected.predicted_class == prediction.predicted_class:
                choose_corrected = corrected.confidence > prediction.confidence
            elif cell in jelly_ml_cells:
                # The overlay made the base read wrong at full confidence
                # (blue_xtra_move 0.99 over a plain star, live 2026-08-15), so
                # the beam pass's "beat the old score" rule would keep the
                # phantom for ever. Trust the cleaned read on its own merit.
                choose_corrected = (
                    corrected.confidence >= corrected.threshold
                    and corrected.confidence >= JELLY_CLASS_CHANGE_MIN_CONFIDENCE
                )
            else:
                choose_corrected = (
                    corrected.confidence >= corrected.threshold
                    and corrected.confidence
                    >= prediction.confidence + BOARD_LINE_CLASS_CHANGE_MARGIN
                )
        if choose_corrected:
            merged_predictions.append(corrected)
            corrected_count += 1
        else:
            merged_predictions.append(prediction)

    merged_predictions, demoted_count = _demote_structureless_xtra_moves(
        img_color,
        merged_predictions,
    )
    if _diag is not None:
        _diag["overlay_line_corrected_predictions"] = corrected_count
        _diag["structureless_xtra_demoted"] = demoted_count
    return replace(
        base_result,
        predictions=merged_predictions,
        inference_ms=base_result.inference_ms + corrected_result.inference_ms,
    )


def _with_structureless_xtra_demoted(img_color, result, _diag=None):
    predictions, demoted = _demote_structureless_xtra_moves(img_color, result.predictions)
    if _diag is not None:
        _diag["structureless_xtra_demoted"] = demoted
    if not demoted:
        return result
    return replace(result, predictions=predictions)


def _demote_structureless_xtra_moves(img_color, predictions):
    """Strip XTRA markers from cells that do not carry the XTRA banner.

    An XTRA tile is white letters plus frame rays: all 54 labelled crops show at
    least 7 white blobs, while a gem with a reward sparkle shows 1-3. Overlays
    (the jelly wash, sparkles) make the model report XTRA on ordinary gems at
    full confidence, and those phantom extras cost real turns.
    """
    rgb = np.asarray(
        img_color.convert("RGB") if hasattr(img_color, "convert") else img_color
    )
    cell_size = int(squareSize)
    if rgb.ndim != 3 or rgb.shape[0] < board_length * cell_size:
        return predictions, 0
    hsv = cv2.cvtColor(rgb[:, :, :3], cv2.COLOR_RGB2HSV)
    white = (
        (hsv[:, :, 2] >= JELLY_SPARKLE_MIN_VALUE)
        & (hsv[:, :, 1] <= JELLY_SPARKLE_MAX_SATURATION)
    )
    updated = []
    demoted = 0
    for prediction in predictions:
        if not prediction.predicted_class.endswith("_xtra_move"):
            updated.append(prediction)
            continue
        top, left = prediction.row * cell_size, prediction.col * cell_size
        components = _white_component_count(
            white[top:top + cell_size, left:left + cell_size]
        )
        if components >= XTRA_TILE_MIN_WHITE_COMPONENTS:
            updated.append(prediction)
            continue
        normal_class = prediction.predicted_class.replace("_xtra_move", "_normal")
        try:
            board_value, special_value = decode_class(normal_class)
        except Exception:
            updated.append(prediction)
            continue
        updated.append(
            replace(
                prediction,
                predicted_class=normal_class,
                board_value=board_value,
                special_value=special_value,
            )
        )
        demoted += 1
    return updated, demoted


def _try_ml_primary_fast_path(img_color, board, special_board, active_game_mode, _diag=None):
    mode = normalize_ml_recognition_mode(ml_recognition_mode)
    if mode not in {ML_RECOGNITION_FIRST, ML_RECOGNITION_ONLY}:
        return False

    template_board = [row[:] for row in board]
    template_special_board = [row[:] for row in special_board]
    ml_result = _predict_board_tiles_with_line_resilience(
        img_color,
        mode,
        _diag,
        jelly_cells=last_jelly_zone_cells,
    )
    applied_result = apply_ml_recognition_overlay(
        board,
        special_board,
        ml_result,
        active_game_mode,
    )
    mode_template_hits = 0
    _mode_board_value, mode_template_specs = mode_target_template_specs(active_game_mode)
    if mode != ML_RECOGNITION_ONLY and mode_template_specs:
        _t_mode = time.perf_counter()
        img_gray = cv2.cvtColor(np.array(img_color), cv2.COLOR_RGB2GRAY)
        mode_template_hits = apply_mode_target_templates(
            img_gray,
            board,
            special_board,
            active_game_mode,
        )
        mode_specific_ms = (time.perf_counter() - _t_mode) * 1000
    else:
        mode_specific_ms = 0.0
    if _diag is not None:
        _diag["mode_specific_ms"] = mode_specific_ms
        _diag["mode_template_hits"] = mode_template_hits
    accepted = sum(1 for prediction in applied_result.predictions if prediction.accepted)
    expected_cells = board_length * board_length
    if (
        not applied_result.available
        or len(applied_result.predictions) != expected_cells
        or not check_fill(board)
    ):
        block_reason = _ml_primary_failure_reason(
            applied_result,
            accepted,
            expected_cells,
            board,
        )
        _restore_board(board, template_board)
        _restore_board(special_board, template_special_board)
        if mode == ML_RECOGNITION_ONLY:
            _record_ml_diag(
                _diag,
                applied_result,
                template_board,
                template_special_board,
                board,
                special_board,
                fast_path=False,
                blocked=True,
                block_reason=block_reason,
            )
            _record_hot_color_diag(_diag, applied_result, active_game_mode)
            _set_ml_primary_blocked_timings(_diag)
            return True
        return False

    _record_ml_diag(
        _diag,
        applied_result,
        template_board,
        template_special_board,
        board,
        special_board,
        fast_path=True,
    )
    _record_hot_color_diag(_diag, applied_result, active_game_mode)
    if _diag is not None:
        _diag["non_ml_templates_ms"] = 0.0
        _diag.setdefault("mode_specific_ms", 0.0)
        _diag.setdefault("mode_template_hits", 0)
        _diag["color_fallback_ms"] = 0.0
    return True


def _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag=None):
    mode = normalize_ml_recognition_mode(ml_recognition_mode)
    if mode == ML_RECOGNITION_OFF:
        _set_ml_diag_off(_diag, mode)
        return board, special_board

    template_board = [row[:] for row in board]
    template_special_board = [row[:] for row in special_board]
    ml_result = _predict_board_tiles_with_line_resilience(
        img_color,
        mode,
        _diag,
        jelly_cells=last_jelly_zone_cells,
    )
    applied_result = apply_ml_recognition_overlay(
        board,
        special_board,
        ml_result,
        active_game_mode,
    )
    _record_ml_diag(
        _diag,
        applied_result,
        template_board,
        template_special_board,
        board,
        special_board,
        fast_path=False,
    )
    _record_hot_color_diag(_diag, applied_result, active_game_mode)

    return board, special_board


def get_board_locations(locations):
    board = create_board()
    for pt in zip(*locations[::-1]):
        i = (pt[1] + squareSize // 2) // squareSize
        j = (pt[0] + squareSize // 2) // squareSize
        board[i][j] = 1
    return board

def iter_template_match_cells(result, template, threshold):
    rows, cols = np.where(result >= threshold)
    for y, x in zip(rows, cols):
        i = int((y + template.shape[0] // 2) // squareSize)
        j = int((x + template.shape[1] // 2) // squareSize)
        if 0 <= i < board_length and 0 <= j < board_length:
            yield i, j, float(result[y][x])

def iter_template_match_cells_below(result, template, threshold):
    rows, cols = np.where(result <= threshold)
    for y, x in zip(rows, cols):
        i = int((y + template.shape[0] // 2) // squareSize)
        j = int((x + template.shape[1] // 2) // squareSize)
        if 0 <= i < board_length and 0 <= j < board_length:
            yield i, j, float(result[y][x])

def iter_template_match_cell_positions_below(result, template, threshold):
    rows, cols = np.where(result <= threshold)
    for y, x in zip(rows, cols):
        i = int((y + template.shape[0] // 2) // squareSize)
        j = int((x + template.shape[1] // 2) // squareSize)
        if 0 <= i < board_length and 0 <= j < board_length:
            yield i, j, float(result[y][x]), int(x), int(y)

def heart_candidate_has_clean_shape(img_rgb, template, mask, x, y):
    height, width = template.shape[:2]
    if y + height > img_rgb.shape[0] or x + width > img_rgb.shape[1]:
        return False

    transparent_region = mask < HEART_TRANSPARENT_ALPHA_THRESHOLD
    if not np.any(transparent_region):
        return True

    pixels = img_rgb[y:y + height, x:x + width][transparent_region].astype(np.float32)
    palette = np.array(colors[:-1], dtype=np.float32)
    distances = np.linalg.norm(pixels[:, None, :] - palette[None, :, :], axis=2)
    piece_like_ratio = float((distances.min(axis=1) < HEART_TRANSPARENT_COLOR_DISTANCE).mean())
    return piece_like_ratio <= HEART_TRANSPARENT_MAX_PIECE_RATIO

def heart_candidate_color(img_color, row, col, template_color):
    if img_color is None or template_color == WHITE_COLOR:
        return template_color

    x = col * squareSize + squareSize // 2
    y = row * squareSize + squareSize // 2
    detected_color = square_color_detect(img_color, x, y)
    if detected_color != template_color:
        return None
    return detected_color

def find_heart_candidates(img_rgb, img_color=None):
    if img_color is None:
        img_color = Image.fromarray(img_rgb.astype(np.uint8))

    candidates = {}
    for index, template in enumerate(heart_templates):
        mask = heart_template_masks[index]
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=mask,
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = heart_template_thresholds[index]
        for i, j, score, x, y in iter_template_match_cell_positions_below(res, template, threshold):
            if not heart_candidate_has_clean_shape(img_rgb, template, mask, x, y):
                continue
            color = heart_candidate_color(img_color, i, j, heart_template_colors[index])
            if color is None:
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, color)
    return candidates


def find_vinnie_se_heart_candidates(img_rgb, img_color=None):
    candidates = {}
    for index, template in enumerate(vinnie_se_heart_templates):
        mask = vinnie_se_heart_template_masks[index]
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=mask,
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = vinnie_se_heart_template_thresholds[index]
        for i, j, score, x, y in iter_template_match_cell_positions_below(res, template, threshold):
            if not heart_candidate_has_clean_shape(img_rgb, template, mask, x, y):
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (
                    score,
                    vinnie_se_heart_template_colors[index],
                    vinnie_se_heart_template_specials[index],
                )
    return candidates


def find_knight_candidates(img_rgb, img_color):
    candidates = {}
    for index, template in enumerate(knight_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=knight_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = knight_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            x = j * squareSize + squareSize // 2
            y = i * squareSize + squareSize // 2
            if square_color_detect(img_color, x, y) != knight_template_colors[index]:
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, knight_template_colors[index])
    return candidates

def find_cleo_bug_candidates(img_rgb):
    candidates = {}
    for index, template in enumerate(cleo_bug_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=cleo_bug_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = cleo_bug_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score < previous:
                candidates[(i, j)] = score
    return candidates

def find_billie_drone_candidates(img_rgb):
    candidates = {}
    target_cell = (board_length - 1, board_length // 2)
    for index, template in enumerate(billie_drone_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=billie_drone_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = billie_drone_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            if (i, j) != target_cell:
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous:
                candidates[(i, j)] = score
    return candidates

def find_disco_ball_candidates(img_rgb):
    candidates = {}
    for index, template in enumerate(disco_ball_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=disco_ball_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = disco_ball_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score < previous:
                candidates[(i, j)] = score
    return candidates

def find_all_aboard_bandit_candidates(img_rgb, img_color=None):
    if img_color is None:
        img_color = Image.fromarray(img_rgb.astype(np.uint8))

    candidates = {}
    for index, template in enumerate(all_aboard_bandit_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=all_aboard_bandit_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = all_aboard_bandit_template_thresholds[index]
        template_color = all_aboard_bandit_template_colors[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, template_color)
    return candidates

def joojoo_candidate_has_light_skull(img_rgb, row, col):
    y1 = row * squareSize + int(squareSize * 0.10)
    y2 = row * squareSize + int(squareSize * 0.70)
    x1 = col * squareSize + int(squareSize * 0.10)
    x2 = col * squareSize + int(squareSize * 0.90)
    roi = img_rgb[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    light_pixels = (
        (roi[:, :, 0] > 170)
        & (roi[:, :, 1] > 150)
        & (roi[:, :, 2] > 120)
    )
    return float(light_pixels.mean()) >= JOOJOO_SKULL_MIN_LIGHT_RATIO

def joojoo_candidate_color(img_rgb, img_color, row, col):
    y1 = row * squareSize + int(squareSize * 0.05)
    y2 = row * squareSize + int(squareSize * 0.95)
    x1 = col * squareSize + int(squareSize * 0.05)
    x2 = col * squareSize + int(squareSize * 0.95)
    roi = img_rgb[y1:y2, x1:x2]
    allowed_colors = (GREEN, YELLOW, PURPLE, ORANGE)
    if roi.size:
        palette = np.array([colors[color - 1] for color in allowed_colors], dtype=np.float32)
        pixels = roi.reshape(-1, 3).astype(np.float32)
        distances = np.linalg.norm(pixels[:, None, :] - palette[None, :, :], axis=2)
        nearest = distances.argmin(axis=1)
        close = distances.min(axis=1) < JOOJOO_SKULL_COLOR_DISTANCE
        if np.any(close):
            counts = np.bincount(nearest[close], minlength=len(allowed_colors))
            best_index = int(counts.argmax())
            if counts[best_index] >= JOOJOO_SKULL_MIN_COLOR_PIXELS:
                return allowed_colors[best_index]

    fallback = square_color_detect(
        img_color,
        col * squareSize + squareSize // 2,
        row * squareSize + squareSize // 2,
    )
    return fallback if fallback in allowed_colors else None

def find_joojoo_skull_candidates(img_rgb, img_color=None):
    if img_color is None:
        img_color = Image.fromarray(img_rgb.astype(np.uint8))

    candidates = {}
    for index, template in enumerate(joojoo_skull_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=joojoo_skull_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = joojoo_skull_template_thresholds[index]
        best_scores_by_cell = {}
        for i, j, score, _x, _y in iter_template_match_cell_positions_below(res, template, threshold):
            previous = best_scores_by_cell.get((i, j))
            if previous is None or score < previous:
                best_scores_by_cell[(i, j)] = score
        for (i, j), score in best_scores_by_cell.items():
            if not joojoo_candidate_has_light_skull(img_rgb, i, j):
                continue
            color = joojoo_candidate_color(img_rgb, img_color, i, j)
            if color is None:
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, color)
    return candidates

def find_color_crystal_candidates(img_rgb):
    candidates = {}
    for index, template in enumerate(color_crystal_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=color_crystal_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = color_crystal_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, color_crystal_template_colors[index])
    return candidates

def find_mushroom_candidates(img_rgb):
    candidates = {}
    for index, template in enumerate(mushroom_templates):
        res = cv2.matchTemplate(
            img_rgb,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=mushroom_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = mushroom_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            if not mushroom_candidate_has_bright_stem(img_rgb, i, j):
                continue
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, mushroom_template_colors[index])
    return candidates


def mushroom_candidate_has_bright_stem(img_rgb, row, col):
    y1 = row * squareSize + int(squareSize * 0.60)
    y2 = row * squareSize + int(squareSize * 0.95)
    x1 = col * squareSize + int(squareSize * 0.30)
    x2 = col * squareSize + int(squareSize * 0.70)
    roi = img_rgb[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    light_pixels = (
        (roi[:, :, 0] > 170)
        & (roi[:, :, 1] > 140)
        & (roi[:, :, 2] > 100)
    )
    return float(light_pixels.mean()) >= MUSHROOM_STEM_MIN_LIGHT_RATIO


def find_firework_candidates(img_rgb):
    candidates = {}
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    for index, template in enumerate(firework_mode_templates):
        template_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)
        res = cv2.matchTemplate(
            img_gray,
            template_gray,
            cv2.TM_SQDIFF_NORMED,
            mask=firework_template_masks[index],
        )
        res = np.nan_to_num(res, nan=1.0, posinf=1.0, neginf=1.0)
        threshold = firework_template_thresholds[index]
        for i, j, score in iter_template_match_cells_below(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score < previous[0]:
                candidates[(i, j)] = (score, firework_template_types[index])
    return candidates


def mode_target_template_specs(active_game_mode):
    mode = normalize_game_mode(active_game_mode)
    if mode is GameMode.CHEST:
        return CHEST_COLOR, ((chest, 0.8), (chest2, 0.8))
    if mode is GameMode.GREEN_LEAF:
        return GREEN, ((leaf_plus3, 0.85), (leaf, 0.8))
    return None, ()


def find_mode_target_candidates(img_gray, active_game_mode):
    board_value, specs = mode_target_template_specs(active_game_mode)
    candidates = {}
    for template, threshold in specs:
        if template is None or template.size == 0 or float(template.std()) == 0.0:
            continue
        res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
        for i, j, score in iter_template_match_cells(res, template, threshold):
            previous = candidates.get((i, j))
            if previous is None or score > previous:
                candidates[(i, j)] = score
    return board_value, candidates


def apply_mode_target_templates(img_gray, board, special_board, active_game_mode):
    board_value, candidates = find_mode_target_candidates(img_gray, active_game_mode)
    if board_value is None:
        return 0
    for i, j in candidates:
        board[i][j] = board_value
        special_board[i][j] = SPECIAL_MODE_TARGET
    return len(candidates)


def update_board_2(board, special_board, screenshot_path=None, write_screenshot=True, _diag=None):
    global last_funky_tile_cells, last_hot_color_state, last_hot_color_auto_candidate
    global last_jelly_zone_cells
    curr_time = str(datetime.datetime.now())[:19].replace(':', '_')  # DEBUG
    if screenshot_path is None and write_screenshot:
        screenshot_path = os.path.join("Debug", curr_time + ".png")
    _t = time.perf_counter()
    img_color = capture_debug_screenshot(
        screenshot_path if write_screenshot else None,
        region=(left, up, width, height),
        latest_key=screenshot_path,
        write_to_disk=write_screenshot,
    )  # DEBUG
    if _diag is not None:
        _diag["screenshot_ms"] = (time.perf_counter() - _t) * 1000
    active_game_mode = normalize_game_mode(curr_mode)
    last_hot_color_state = None
    last_hot_color_auto_candidate = None
    last_funky_tile_cells = (
        detect_funky_tile_cells(img_color)
        if active_game_mode is GameMode.FUNKY_TILES
        else ()
    )
    last_jelly_zone_cells = detect_jelly_zone_cells(img_color)
    if _diag is not None:
        _diag["funky_tile_cells"] = [list(cell) for cell in last_funky_tile_cells]
        _diag["jelly_zone_cells"] = [list(cell) for cell in last_jelly_zone_cells]
    if _try_ml_primary_fast_path(img_color, board, special_board, active_game_mode, _diag):
        return board, special_board

    img_rgb = np.array(img_color.convert("RGB"))
    img_gray = cv2.cvtColor(np.array(img_color), cv2.COLOR_RGB2GRAY)

    # Initialised here so the color-crystal detector and mode-specific branches
    # (MULTIPLIER_MUSHROOMS) can compare their template confidence with the
    # general special detectors.
    special_confidence = create_board()
    # How far each general (ccoeff) special scored above its detection threshold.
    # A small margin means the match barely passed and is likely a false positive
    # (e.g. a lightning/bomb hit on a color-crystal tile); the crystal detector
    # uses this to decide when it may override such a special.
    general_special_margin = [[None] * board_length for _ in range(board_length)]
    _t_non_ml = time.perf_counter()
    # We removed grayscale matchTemplate for base colors here because it confuses Red and Orange.
    # The board will be populated by the highly accurate RGB square_color_detect below.
    for index, template in enumerate(special_templates):
        res = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
        threshold = special_template_thresholds[index] if index < len(special_template_thresholds) else 0.75
        special_type = special_template_types[index] if index < len(special_template_types) else index + 1
        expected_color = (
            special_template_colors[index]
            if len(special_template_colors) == len(special_templates)
            else None
        )
        for i, j, score in iter_template_match_cells(res, template, threshold):
            if score <= special_confidence[i][j]:
                continue
            if board[i][j] == 0:
                x = j * squareSize + squareSize // 2
                y = i * squareSize + squareSize // 2
                board[i][j] = square_color_detect(
                    img_color,
                    x,
                    y,
                    _use_fireworks_palette_for_general_special(special_type),
                )
            if expected_color is not None and expected_color != WHITE_COLOR and board[i][j] != expected_color:
                continue
            special_board[i][j] = special_type
            special_confidence[i][j] = score
            general_special_margin[i][j] = score - threshold

    active_special_piece_mode = normalize_special_piece_mode(special_piece_mode)
    heart_candidates = {}
    vinnie_se_heart_candidates = {}
    knight_candidates = {}
    cleo_bug_candidates = {}
    billie_drone_candidates = {}
    disco_ball_candidates = {}
    all_aboard_bandit_candidates = {}
    joojoo_skull_candidates = {}

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_HEARTS}:
        heart_candidates = find_heart_candidates(img_rgb, img_color)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS}:
        vinnie_se_heart_candidates = find_vinnie_se_heart_candidates(img_rgb, img_color)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_KNIGHTS}:
        knight_candidates = find_knight_candidates(img_rgb, img_color)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_CLEO}:
        cleo_bug_candidates = find_cleo_bug_candidates(img_rgb)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_BILLIE}:
        billie_drone_candidates = find_billie_drone_candidates(img_rgb)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_DISCO}:
        disco_ball_candidates = find_disco_ball_candidates(img_rgb)
    if active_special_piece_mode == SPECIAL_PIECE_MODE_ALL_ABOARD:
        all_aboard_bandit_candidates = find_all_aboard_bandit_candidates(img_rgb, img_color)
    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_JOOJOO}:
        joojoo_skull_candidates = find_joojoo_skull_candidates(img_rgb, img_color)

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_HEARTS}:
        for (i, j), (score, color) in heart_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = color
            special_board[i][j] = SPECIAL_HEART
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS}:
        for (i, j), (score, color, special) in vinnie_se_heart_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = color
            special_board[i][j] = special
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_KNIGHTS}:
        for (i, j), (score, color) in knight_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = color
            special_board[i][j] = SPECIAL_KNIGHT
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_CLEO}:
        for (i, j), score in cleo_bug_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = 1
            special_board[i][j] = SPECIAL_CLEO_BUG
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_BILLIE}:
        for (i, j), score in billie_drone_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = BLOCKED
            special_board[i][j] = SPECIAL_BILLIE_DRONE
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_DISCO}:
        for (i, j), score in disco_ball_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = DISCO_BALL
            special_board[i][j] = SPECIAL_DISCO_BALL
            special_confidence[i][j] = confidence

    if active_special_piece_mode == SPECIAL_PIECE_MODE_ALL_ABOARD:
        for (i, j), (score, color) in all_aboard_bandit_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = color
            special_board[i][j] = SPECIAL_ALL_ABOARD_BANDIT
            special_confidence[i][j] = confidence

    if active_special_piece_mode in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_JOOJOO}:
        for (i, j), (score, color) in joojoo_skull_candidates.items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j]:
                continue
            board[i][j] = color
            special_board[i][j] = SPECIAL_JOOJOO_SKULL
            special_confidence[i][j] = confidence

    # Color crystals are detected in every game mode (not only when the
    # Color Crystals mode is selected). When a crystal is part of a match it
    # clears its whole color, so the bot should always recognise and use them.
    # A stray crystal match must not clobber a genuine special on the same cell,
    # so we only override an existing special when it is either a low-margin
    # general false positive or a less confident candidate special.
    for (i, j), (score, template_color) in find_color_crystal_candidates(img_rgb).items():
        confidence = 1.0 - score
        existing_special = special_board[i][j]
        if existing_special != 0:
            if existing_special in CRYSTAL_OVERRIDABLE_SPECIALS:
                margin = general_special_margin[i][j]
                if margin is not None and margin >= CRYSTAL_OVERRIDE_GENERAL_MARGIN:
                    # Confident general special: treat as genuine, keep it.
                    continue
            elif confidence <= special_confidence[i][j]:
                # Candidate special detected more confidently: keep it.
                continue
        x = j * squareSize + squareSize // 2
        y = i * squareSize + squareSize // 2
        color = square_color_detect(img_color, x, y) or template_color
        board[i][j] = color
        special_board[i][j] = SPECIAL_COLOR_CRYSTAL
        special_confidence[i][j] = max(special_confidence[i][j], confidence)

    if _diag is not None:
        _diag["non_ml_templates_ms"] = (time.perf_counter() - _t_non_ml) * 1000

    _t_mode = time.perf_counter()
    if active_game_mode is GameMode.NONE and check_fill(board):
        if _diag is not None:
            _diag.setdefault("mode_specific_ms", (time.perf_counter() - _t_mode) * 1000)
            _diag.setdefault("color_fallback_ms", 0.0)
        return _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag)

    if active_game_mode is GameMode.FIREWORKS:
        for (i, j), (_score, special_type) in find_firework_candidates(img_rgb).items():
            x = j * squareSize + squareSize // 2
            y = i * squareSize + squareSize // 2
            board[i][j] = square_color_detect(img_color, x, y, True)
            special_board[i][j] = special_type

    elif active_game_mode is GameMode.CHEST:
        apply_mode_target_templates(img_gray, board, special_board, active_game_mode)

    elif active_game_mode is GameMode.MULTIPLIER_MUSHROOMS:
        for (i, j), (score, template_color) in find_mushroom_candidates(img_rgb).items():
            confidence = 1.0 - score
            if confidence <= special_confidence[i][j] and special_board[i][j] != SPECIAL_JOOJOO_SKULL:
                continue
            x = j * squareSize + squareSize // 2
            y = i * squareSize + squareSize // 2
            color = square_color_detect(img_color, x, y) or template_color
            board[i][j] = color
            special_board[i][j] = SPECIAL_MUSHROOM
            special_confidence[i][j] = confidence

    elif active_game_mode is GameMode.RED_AND_BLUE:
        w, h = red_blue.shape[::-1]
        res = cv2.matchTemplate(img_gray, red_blue, cv2.TM_CCOEFF_NORMED)
        threshold = 0.8
        loc = np.where(res >= threshold)
        for pt in zip(*loc[::-1]):
            i = (pt[1] + squareSize // 2) // squareSize
            j = (pt[0] + squareSize // 2) // squareSize
            board[i][j] = 1

    elif active_game_mode is GameMode.PURPLE_GEM:
        w, h = purple_gem_4.shape[::-1]
        res = cv2.matchTemplate(img_gray, purple_gem_4, cv2.TM_CCOEFF_NORMED)
        threshold = 0.7
        loc = np.where(res >= threshold)
        for pt in zip(*loc[::-1]):
            i = (pt[1] + squareSize // 2) // squareSize
            j = (pt[0] + squareSize // 2) // squareSize
            board[i][j] = 4
            special_board[i][j] = 9

    elif active_game_mode is GameMode.GREEN_LEAF:
        apply_mode_target_templates(img_gray, board, special_board, active_game_mode)

    elif active_game_mode is GameMode.BOUNTY:
        w, h = bounty.shape[::-1]
        res = cv2.matchTemplate(img_gray, bounty, cv2.TM_CCOEFF_NORMED)
        threshold = 0.8
        loc = np.where(res >= threshold)
        for pt in zip(*loc[::-1]):
            i = (pt[1] + squareSize // 2) // squareSize
            j = (pt[0] + squareSize // 2) // squareSize
            board[i][j] = 6
            special_board[i][j] = 9

    if check_fill(board):
        if _diag is not None:
            _diag.setdefault("mode_specific_ms", (time.perf_counter() - _t_mode) * 1000)
            _diag.setdefault("color_fallback_ms", 0.0)
        return _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag)

    if _diag is not None:
        _diag.setdefault("mode_specific_ms", (time.perf_counter() - _t_mode) * 1000)
    _t = time.perf_counter()
    for i in range(board_length):
        for j in range(board_length):
            if board[i][j] == 0:
                board[i][j] = square_color_detect(img_color, j * squareSize + squareSize // 2, i * squareSize + squareSize // 2)
    if _diag is not None:
        _diag["color_fallback_ms"] = (time.perf_counter() - _t) * 1000

    return _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag)

def check_fill(board):
    for i in range(board_length):
        for j in range(board_length):
            if board[i][j] == 0:
                return False
    return True

def check_best_exchange(board, special_board):
    highest_score = 0
    highest_score_spot = (0, 0)
    highest_score_dir = "up"
    for i in range(board_length):
        for j in range(board_length):
            score_up, score_down, score_left, score_right = 0, 0, 0, 0
            
            # Helper to detect double special swap
            def is_double_special(r1, c1, r2, c2):
                return (0 < special_board[r1][c1] <= 4 or special_board[r1][c1] >= 10) and \
                       (0 < special_board[r2][c2] <= 4 or special_board[r2][c2] >= 10)

            if i > 0:
                if is_double_special(i, j, i - 1, j):
                    score_up = 50.0
                else:
                    boards = exchange_boards(board, special_board, i, j, "up")
                    score_up = check_board_score(boards[0], boards[1])
            if i < board_length - 1:
                if is_double_special(i, j, i + 1, j):
                    score_down = 50.0
                else:
                    boards = exchange_boards(board, special_board, i, j, "down")
                    score_down = check_board_score(boards[0], boards[1])
            if j > 0:
                if is_double_special(i, j, i, j - 1):
                    score_left = 50.0
                else:
                    boards = exchange_boards(board, special_board, i, j, "left")
                    score_left = check_board_score(boards[0], boards[1])
            if j < board_length - 1:
                if is_double_special(i, j, i, j + 1):
                    score_right = 50.0
                else:
                    boards = exchange_boards(board, special_board, i, j, "right")
                    score_right = check_board_score(boards[0], boards[1])
                    
            curr_high_score = max(score_up, score_down, score_left, score_right)
            if curr_high_score >= highest_score:
                highest_score, highest_score_dir = check_best_direction(score_up, score_down, score_left, score_right)
                highest_score_spot = (i, j)
    return (highest_score, highest_score_spot, highest_score_dir)

def exchange_boards(board, special_board, i, j, direction):
    if direction == "up":
        exchange_board = copy.deepcopy(board)
        temp = exchange_board[i][j]
        exchange_board[i][j] = exchange_board[i - 1][j]
        exchange_board[i - 1][j] = temp
        exchange_special_board = copy.deepcopy(special_board)
        temp = exchange_special_board[i][j]
        exchange_special_board[i][j] = exchange_special_board[i - 1][j]
        exchange_special_board[i - 1][j] = temp
    elif direction == "down":
        exchange_board = copy.deepcopy(board)
        temp = exchange_board[i][j]
        exchange_board[i][j] = exchange_board[i + 1][j]
        exchange_board[i + 1][j] = temp
        exchange_special_board = copy.deepcopy(special_board)
        temp = exchange_special_board[i][j]
        exchange_special_board[i][j] = exchange_special_board[i + 1][j]
        exchange_special_board[i + 1][j] = temp
    elif direction == "left":
        exchange_board = copy.deepcopy(board)
        temp = exchange_board[i][j]
        exchange_board[i][j] = exchange_board[i][j - 1]
        exchange_board[i][j - 1] = temp
        exchange_special_board = copy.deepcopy(special_board)
        temp = exchange_special_board[i][j]
        exchange_special_board[i][j] = exchange_special_board[i][j - 1]
        exchange_special_board[i][j - 1] = temp
    else:  # right
        exchange_board = copy.deepcopy(board)
        temp = exchange_board[i][j]
        exchange_board[i][j] = exchange_board[i][j + 1]
        exchange_board[i][j + 1] = temp
        exchange_special_board = copy.deepcopy(special_board)
        temp = exchange_special_board[i][j]
        exchange_special_board[i][j] = exchange_special_board[i][j + 1]
        exchange_special_board[i][j + 1] = temp
    return exchange_board, exchange_special_board

def check_best_direction(score_up, score_down, score_left, score_right):
    if score_up >= score_down and score_up >= score_left and score_up >= score_right:
        return score_up, "up"
    if score_down >= score_up and score_down >= score_left and score_down >= score_right:
        return score_down, "down"
    if score_left >= score_up and score_left >= score_down and score_left >= score_right:
        return score_left, "left"
    if score_right >= score_up and score_right >= score_down and score_right >= score_left:
        return score_right, "right"

def check_board_score(board, special_board):
    score = 0
    not_special = True
    match = False
    # horizonal:
    for i in range(board_length):
        for j in range(board_length - 2):
            if board[i][j] == board[i][j + 1] == board[i][j + 2] and board[i][j] != 0:
                match = True
                horizonal_special_score = is_special_horizonal(board, special_board, (i, j))
                if horizonal_special_score >= 5:
                    not_special = False
                    score += horizonal_special_score
                    explode_line(board, i, j, "horizonal")
                if horizonal_special_score < 5:
                    if board[i][j] == 1:
                        score += special_color_three_score
                    else:
                        score += three_score
                    explode_line(board, i, j, "horizonal")
    # vertical:
    for i in range(board_length - 2):
        for j in range(board_length):
            if board[i][j] == board[i + 1][j] == board[i + 2][j] and board[i][j] != 0:
                match = True
                vertical_special_score = is_special_vertical(board, special_board, (i, j))
                if vertical_special_score >= 5:
                    not_special = False
                    score += vertical_special_score
                    explode_line(board, i, j, "vertical")
                if vertical_special_score < 5:
                    if board[i][j] == 1:
                        score += special_color_three_score
                    else:
                        score += three_score
                    explode_line(board, i, j, "vertical")
    if not_special and match:
        board, special_board = drop_boards(board, special_board)
        score += check_board_score(board, special_board)
    return score

def is_special_horizonal(board, special_board, left_c):
    blue_bonus = board[left_c[0]][left_c[1]] == 1
    special_score = 0
    if 1 <= special_board[left_c[0]][left_c[1]] <= 4 or 1 <= special_board[left_c[0]][left_c[1] + 1] <= 4 or 1 <= \
            special_board[left_c[0]][left_c[1] + 2] <= 4:
        special_score += 5
    for j in range(left_c[1], left_c[1] + 3):
        if left_c[0] > 1:
            if board[left_c[0] - 2][j] == board[left_c[0] - 1][j] == board[left_c[0]][j]:
                return 200 + special_score if blue_bonus else 120 + special_score
        if 0 < left_c[0] < 6:
            if board[left_c[0] - 1][j] == board[left_c[0]][j] == board[left_c[0] + 1][j]:
                return 200 + special_score if blue_bonus else 120 + special_score
        if left_c[0] < 5:
            if board[left_c[0]][j] == board[left_c[0] + 1][j] == board[left_c[0] + 2][j]:
                return 200 + special_score if blue_bonus else 120 + special_score
    if 0 < left_c[1] < 4:
        if board[left_c[0]][left_c[1] - 1] == board[left_c[0]][left_c[1]] == board[left_c[0]][left_c[1] + 3]:
            return 300 + special_score if blue_bonus else 220 + special_score
    if left_c[1] > 0:
        if board[left_c[0]][left_c[1] - 1] == board[left_c[0]][left_c[1]]:
            return 150 + special_score if blue_bonus else 100 + special_score
    if left_c[1] + 3 <= 6:
        if board[left_c[0]][left_c[1]] == board[left_c[0]][left_c[1] + 3]:
            return 150 + special_score if blue_bonus else 100 + special_score
    return special_score

def is_special_vertical(board, special_board, top_c):
    blue_bonus = board[top_c[0]][top_c[1]] == 1
    special_score = 0
    if 0 < special_board[top_c[0]][top_c[1]] <= 3 or 0 < special_board[top_c[0] + 1][top_c[1]] <= 3 or 0 < special_board[top_c[0] + 2][top_c[1]] <= 3:
        special_score += 5
    for i in range(top_c[0], top_c[0] + 3):
        if top_c[1] > 1:
            if board[i][top_c[1] - 2] == board[i][top_c[1] - 1] == board[i][top_c[1]]:
                return 200 + special_score if blue_bonus else 120 + special_score
        if 0 < top_c[1] < 6:
            if board[i][top_c[1] - 1] == board[i][top_c[1]] == board[i][top_c[1] + 1]:
                return 200 + special_score if blue_bonus else 120 + special_score
        if top_c[1] < 5:
            if board[i][top_c[1]] == board[i][top_c[1] + 1] == board[i][top_c[1] + 2]:
                return 200 + special_score if blue_bonus else 120 + special_score
    if 0 < top_c[0] < 4:
        if board[top_c[0] - 1][top_c[1]] == board[top_c[0]][top_c[1]] == board[top_c[0] + 3][top_c[1]]:
            return 300 + special_score if blue_bonus else 220 + special_score
    if top_c[0] > 0:
        if board[top_c[0] - 1][top_c[1]] == board[top_c[0]][top_c[1]]:
            return 150 + special_score if blue_bonus else 100 + special_score
    if top_c[0] + 3 <= 6:
        if board[top_c[0]][top_c[1]] == board[top_c[0] + 3][top_c[1]]:
            return 150 + special_score if blue_bonus else 100 + special_score
    return special_score

def explode_line(board, i, j, direction):
    if direction == "horizonal":
        board[i][j] = 0
        board[i][j + 1] = 0
        board[i][j + 2] = 0
    if direction == "vertical":
        board[i][j] = 0
        board[i + 1][j] = 0
        board[i + 2][j] = 0

def drop_boards(board, special_board):
    board = np.rot90(board)
    board = board.tolist()
    for i in range(board_length):
        for j in range(board_length):
            if board[i][j] == 0:
                board[i].insert(0, board[i].pop(j))
                special_board[i].insert(0, special_board[i].pop(j))
    board = np.rot90(board, 3)
    board = board.tolist()
    return board, special_board
