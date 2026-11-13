import copy
import csv
import datetime
import contextlib
import json
import os
import random
import shutil
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import pyautogui
import cv2
import numpy as np
from PIL import Image, ImageDraw

import capture
import board_source
import learned_value
import move_telemetry
import strategy_lab.live as strategy_lab_live
from solo_challenge import SoloGoalState
import perk_detection
from perk_executor import PerkExecutionFrame, execute_perk_flow
import recognition
import screen_state_reader
from board_profiles import DEFAULT_PROFILE, REGULAR_PROFILE, SUPERSIZE_PROFILE
from board_source import BOARD_SOURCE_AUTO, BOARD_SOURCE_MEMORY, BOARD_SOURCE_ML
from window_geometry import find_bluestacks_window
from match_context import build_match_context
from capture import (
    AUTO_LATEST_BOARD_FILENAME,
    AUTO_MOTION_THRESHOLD,
    AUTO_VISUAL_HASH_MAX_DISTANCE,
    AUTO_VISUAL_HASH_SIZE,
    auto_core_motion_score,
    auto_motion_score,
    auto_visual_fingerprint,
    auto_visual_hash_distance,
    capture_debug_screenshot,
    flush_debug_screenshot_writes,
    load_auto_board_image,
)
from auto_plan import PlanningCancelled, planning_cancellation
from move_strategy import (
    BluePlan,
    BOOSTER_MAX_CHARGE,
    BoosterState,
    GameMode,
    Direction,
    LaserBeamTargetEvaluation,
    MoveCandidate,
    MoveEvaluation,
    MixyMeowState,
    UfoState,
    BOUNTY_INITIAL_TARGET_VALUE,
    BOUNTY_TARGET_VALUE_INCREASE,
    bounty_target_value_active,
    purple_gem_state,
    UFO_ALLOW_PICKING_BLUES,
    UFO_PREDICTED_EXTRA_GATE,
    ufo_abduction_active,
    UFO_ABDUCTION_EVENT,
    PerkAction,
    PerkDecisionContext,
    PerkObjective,
    STRATEGY_UNKNOWN,
    StrategyContext,
    TurnState,
    choose_dragon_move,
    choose_high_voltage_target,
    choose_laser_beam_target,
    choose_magic_wand_target,
    choose_woolly_workout_target,
    choose_perk_action,
    context_rejected_perk_action,
    color_crush_active,
    energized_charge_colors_active,
    charge_colors_active,
    sweep_paint_pvp_mode_active,
    mushroom_multipliers_active,
    normalize_energized_colors,
    ENERGIZED_COLOR_LABELS,
    matches_destroy_color_active,
    vertical_matches_destroy_color_active,
    all_specials_lightning_active,
    extra_moves_enabled_active,
    special_combo_score_multiplier_active,
    every_match_is_special_active,
    ability_temp_specials_active,
    both_colors_charge_energy_active,
    line_destruction_active,
    mode_charges_both_colors,
    mode_creates_only_lightning,
    ability_used_active,
    froggy_gather_region_active,
    hot_color_succession_for_mode,
    floor_lava_checked_columns,
    lights_up_state as lights_up_state_active,
    score_multiplier_state as score_multiplier_state_active,
    column_mania_state as column_mania_state_active,
    multiplier_colors_active,
    multiplier_growth_colors,
    color_climb_extra_before_booster,
    color_climb_mixy_code_moves,
    disco_swap_before_booster,
    funky_tile_cells,
    vegas_views_cells,
    jelly_zone_cells,
    COLOR_CRUSH_MODE,
    clamp_lookahead_depth,
    clamp_points_only_lookahead_depth,
    evaluate_blue_plan,
    effective_score_rally_values_for_mode,
    find_matches,
    game_mode_value,
    grid_to_lists,
    has_guaranteed_true_extra,
    is_extra_move_evaluation,
    LIVE_LOOKAHEAD_BEAM_WIDTH,
    LIVE_LOOKAHEAD_CANDIDATES,
    LIVE_LOOKAHEAD_DEPTH,
    MEASURED_MOVE_VALUE,
    SOLO_CHALLENGE_LOOKAHEAD_BEAM_WIDTH,
    SOLO_CHALLENGE_LOOKAHEAD_CANDIDATES,
    SOLO_CHALLENGE_LOOKAHEAD_DEPTH,
    best_extra_move_setup,
    blue_extra_move_before_lotus,
    blue_setup_extra_before_lotus,
    is_vinnie_se_heart_special,
    is_purple_gem_special,
    evaluation_matches_mixy_code,
    has_reliable_same_move_extra,
    normalize_game_mode,
    perk_effect_priority_key,
    perk_legality_reason,
    perk_value_priority_key,
    perk_activation_decision,
    oriented_swap_candidate,
    oriented_swipe,
    prioritize_ranked_moves,
    rank_froggy_lotus_moves,
    froggy_lotus_setup_choice,
    exact_froggy_lotus_choice,
    exact_blue_extra_before_lotus_check,
    rank_mixy_code_moves,
    rank_points_only_moves,
    rank_lowest_points_moves,
    jelly_conversion_tiles,
    rank_extra_move_moves,
    rank_moves,
    exact_refill_choice,
    exact_refill_active,
    JELLY_BLUE_SETUP_CANDIDATES,
    JELLY_DELAY_CANDIDATES,
    plan_visible_extra_sequence,
    rank_perk_actions,
    remove_cross_last_resort,
    should_reserve_last_perk,
    versus_perk_last_chance,
    VERSUS_PERK_MIN_TURN_SECONDS,
    compute_moves_left_in_match,
    compute_is_final_round,
    strategy_context_or_unknown,
    _time_bound_turn,
    solo_goal_priority_moves,
    solo_points_goal,
    solo_goal_progress,
    vinnie_se_heart_colors,
    purple_gem_value,
)
from ml_recognition_runtime import (
    ML_RECOGNITION_ONLY,
    ML_RECOGNITION_OFF,
    normalize_ml_recognition_mode,
)
from recognition import (
    BOUNTY_MODE,
    CHEST_COLOR,
    CHEST_MODE,
    COLOR_CRYSTALS_MODE,
    DISCO_BALL,
    FIREWORKS_MODE,
    GAME_MODE_OPTIONS,
    GREEN_LEAF_MODE,
    HOT_COLOR_MODE,
    MULTIPLIER_MUSHROOMS_MODE,
    NONE_MODE,
    PURPLE_GEM_MODE,
    RED_AND_BLUE_MODE,
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
    SPECIAL_O_RAMA_MODE,
    SPECIAL_PIECE_MODE_AUTO,
    SPECIAL_PIECE_MODE_BILLIE,
    SPECIAL_PIECE_MODE_CLEO,
    SPECIAL_PIECE_MODE_DISCO,
    SPECIAL_PIECE_MODE_HEARTS,
    SPECIAL_PIECE_MODE_HIGH_VOLTAGE,
    SPECIAL_PIECE_MODE_KNIGHTS,
    SPECIAL_PIECE_MODE_LABELS,
    SPECIAL_PIECE_MODE_MIXY_MEOW,
    SPECIAL_PIECE_MODE_UFO,
    SPECIAL_PIECE_MODE_NONE,
    SPECIAL_PIECE_MODE_OPTIONS,
    SPECIAL_ALL_ABOARD_BANDIT,
    SPECIAL_SWEEP_SE_BROOM,
    SPECIAL_VERTICAL,
    SPECIAL_XTRA_MOVE_TILE,
    SPECIAL_ZANY_ZAPPER_1,
    SPECIAL_ZANY_ZAPPER_2,
    VERTICAL_RUSH_MODE,
    WHITE_COLOR,
    apply_board_profile,
    check_fill,
    create_board,
    detect_booster_activate,
    detect_mixy_meow_code_state,
    detect_ufo_eye_state,
    detect_funky_tile_cells,
    detect_jelly_zone_cells,
    normalize_special_piece_mode,
    update_board_2,
)

# pyautogui sleeps PAUSE seconds after every call; its 0.1s default added
# ~400ms of dead time per move. Swipe duration and explicit delays still apply.
pyautogui.PAUSE = 0.01
# pyautogui.drag() interpolates the path in tween steps and sleeps between
# them. MINIMUM_DURATION clamps any duration< it up to itself (default 0.1s),
# and MINIMUM_SLEEP forces ~50ms gaps between move events. Both together turn
# a 0.14s swipe into a fragmented slow drag that BlueStacks reads as a hover
# below the gesture-velocity threshold instead of a flick. Zero them out so the
# drag duration we pass is actually honored and move events stream tightly.
pyautogui.MINIMUM_DURATION = 0
pyautogui.MINIMUM_SLEEP = 0
# Windows' default timer makes every time.sleep() round up to ~15.6ms. The
# swipe paths sleep in small slices (pyautogui's interpolated drag sleeps ~50
# times), which measured as ~1.06s per swipe on 2026-08-24 — the whole "swipe
# je spor" problem. 1ms timer resolution makes those slices real. Process-wide
# and reference-counted by Windows; harmless if it fails.
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

DEBUG_RUNS_DIR = os.path.join("Debug", "runs")
# Per-move debug runs are written under the *active* runs dir. It defaults to
# DEBUG_RUNS_DIR (flat, legacy layout) and is re-pointed at a per-game subfolder
# when the user clicks "Nova partija" (start_new_game_dir). Routing each game
# into its own folder lets calibration group moves by game without guessing
# boundaries from timestamps. Runtime is single-threaded, so a module global is
# safe here.
_active_runs_dir = DEBUG_RUNS_DIR
DEBUG_AUDIT_LOG = os.path.join("Debug", "debug_audit.csv")
SCORE_REGION_FILENAME = "score_region.png"
INTENT_FILENAME = "intent.txt"
INTENT_AUDIT_FILENAME = "intent_audit.md"
AFTER_BOARD_FILENAME = "after_board.png"
AFTER_SCORE_REGION_FILENAME = "after_score_region.png"
OBSERVED_DELTA_FILENAME = "observed_delta.json"
FINAL_OBSERVATION_FILENAME = "final_observation.json"
TERMINAL_BOARD_FILENAME = "terminal_board.png"
TERMINAL_SCORE_REGION_FILENAME = "terminal_score_region.png"
_runtime_tracked_score = None
# Per-component (value, consecutive_moves) for a live reading the floor keeps
# rejecting; see SCORE_FLOOR_OVERRULE_STREAK.
_runtime_score_rejection_streaks = {}
# Observed delta still waiting for a settled frame to record its after-meters.
_pending_observed_delta = None

# A single score crop must not be allowed to poison the monotonic tracker with
# an inserted/duplicated digit (for example 192 -> 8182).  The allowance grows
# with the already accumulated score so high-scoring modes are not constrained
# by a small fixed ceiling, while ordinary versus scores still reject jumps that
# cannot plausibly happen between adjacent observations.
SCORE_RECONCILE_MIN_COMPONENT_JUMP = 500
SCORE_RECONCILE_COMPONENT_JUMP_MULTIPLIER = 4
# Score reconciliation is component-wise throughout: each side is confirmed,
# overruled and maximised on its own. A solo game simply has no second one.
SCORE_COMPONENTS = ("our_score", "opponent_score")
# How many consecutive moves a rejected-but-agreed component has to repeat the
# same value before it overrules the stored floor. Two captures inside one move
# share the same animation frame and can repeat an artefact (51 -> 514), so
# agreement alone is not enough; holding across separate moves is. Three keeps
# the false-accept risk low while still recovering within a few moves.
SCORE_FLOOR_OVERRULE_STREAK = 3
# How many consecutive resolutions may agree on a value *below* the stored floor
# before the floor is treated as a leftover from an earlier match. Both live
# crops must confirm the component each time, so this is a much stronger signal
# than a single low read; three moves keeps a transient double-misread from
# clearing a legitimate floor.
SCORE_NEW_MATCH_DROP_STREAK = 3
FINAL_OBSERVATION_MAX_ATTEMPTS = 8
FINAL_OBSERVATION_DELAY_SECONDS = 0.6
FINAL_OBSERVATION_SCORE_MOTION_THRESHOLD = 0.75
ML_RECOGNITION_DEBUG_FILENAME = "ml_recognition.json"
# In-memory cache key for the last scanned board frame. Lets us save a debug
# run for an ML "only" recognition block even when Debug is toggled off (the
# frame is remembered here without being written to disk on every scan).
ML_BLOCK_LATEST_BOARD_KEY = "ml_block_latest_board.png"
STATE_READER_FILENAME = "state_reader.json"
STATE_IMAGE_FILENAME = "state.png"
STATE_BOOSTER_IMAGE_FILENAME = "state_booster.png"
STATE_MOVES_IMAGE_FILENAME = "state_moves.png"
STATE_ROUND_IMAGE_FILENAME = "state_round.png"
STATE_TURN_IMAGE_FILENAME = "state_turn.png"
SCORE_REGION_X_OFFSET_RATIO = 0.22
SCORE_REGION_Y_ABOVE_BOARD_RATIO = 0.62
SCORE_REGION_WIDTH_RATIO = 0.56
SCORE_REGION_HEIGHT_RATIO = 0.17
AUTO_SCAN_INTERVAL_MS = 25
AUTO_STABLE_REQUIRED_SCANS = 2
AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS = 3
# Scan count alone is not a time guarantee: chained Auto scans can complete in
# well under 25 ms and a cascade can look unchanged for two frames between
# animation phases.  Production Auto therefore also requires the same clean
# board signature to survive this short wall-clock window.  Scanning continues
# at full speed during the window; there is no fixed post-action sleep.
AUTO_MIN_STABLE_SECONDS = 0.14
AUTO_NO_MATCH_SETTLE_SECONDS = 0.18
AUTO_FORCE_SETTLE_SECONDS = 0.50
# Persistent cosmetic animation (bomb fuse, XTRA glow, twinkling star tiles)
# keeps motion/visual scores above threshold forever, so the normal stability
# gate never settles and auto stalls on "ceka animaciju". Escape hatch: once the
# *recognized* board signature has been identical this many scans in a row, treat
# the board as settled regardless of motion. Cascades change the signature every
# frame, so this only fires on a genuinely static board; it sits above the
# suspicious count so normal boards still play via the fast 2-scan path.
AUTO_SETTLED_SIGNATURE_FORCE_SCANS = 6
# Core-motion ceiling for the "dead still" fast path: when the suspicious gate
# would demand a third identical scan, two identical scans whose core motion is
# this low (well under AUTO_MOTION_THRESHOLD) already prove the board settled —
# real animation tails measure noticeably above this even between near-settled
# frames, while a static board with cosmetic overlays measures ~0.
AUTO_STILL_CORE_MOTION_MAX = 0.5
# "Match on board" gate: a settled board never shows an unresolved match — the
# game clears every line the moment it forms — so a fully recognized board that
# still contains one is mid-cascade and must not be played, even when motion
# and signature look calm between clear-animation frames. The inverse also
# holds: a fully recognized, match-free board whose signature repeats this many
# scans in a row is provably settled (falling pieces read as unrecognized cells
# or change the signature every frame), so auto can play through persistent
# cosmetic animation without waiting for the slower force-settle escape.
AUTO_NO_MATCH_SETTLE_SCANS = 3
AUTO_POST_MOVE_COOLDOWN_SECONDS = 0.12
AUTO_POST_BOOSTER_COOLDOWN_SECONDS = 0.0
# This only prevents spending a second perk immediately.  Normal Auto scanning
# and the next board move are no longer held behind a post-perk cooldown.
AUTO_POST_PERK_COOLDOWN_SECONDS = 0.50
AUTO_POST_PERK_MOVE_COOLDOWN_SECONDS = 0.0
AUTO_POST_PLAY_AGAIN_COOLDOWN_SECONDS = 1.5
AUTO_BOOSTER_STUCK_TICK_THRESHOLD = 3
AUTO_UNCHANGED_BOARD_REPLAY_TICK_THRESHOLD = 3
# Tick thresholds prevent one noisy frame from triggering recovery, while these
# wall-clock floors prevent the zero-cooldown scanner from reaching three ticks
# before the game has had time to start its accepted input animation.
AUTO_BOOSTER_STUCK_MIN_SECONDS = 0.60
AUTO_UNCHANGED_BOARD_REPLAY_MIN_SECONDS = 0.45
MANUAL_RECOGNITION_MAX_FRAMES = 3
MANUAL_RECOGNITION_MIN_AGREEING_FRAMES = 2
MANUAL_RECOGNITION_FRAME_DELAY_SECONDS = 0.10
# How often _wait_until_board_still re-grabs while waiting out an animation. A
# grab is ~6ms, so this polls roughly twice per grab's worth of work; tighter
# just burns CPU, looser gives back the latency the poll exists to save.
MANUAL_RECOGNITION_STILL_POLL_SECONDS = 0.012
MANUAL_RECOGNITION_RETRY_INTERVAL_MS = 25
# LIVE_LOOKAHEAD_* are imported from move_strategy (single source of truth so the
# engine benchmark guards the exact lookahead path used in-game).
SWIPE_DURATION_SECONDS = 0.03
# Swipe travel distance in pixels. 40 px sat right at the Android gesture
# threshold (~24-48dp depending on density), so a fragmented drag would slip
# under it and register as a tap-hold. 50 px gives margin without overshooting
# the neighbouring tile center.
SWIPE_DISTANCE_PX = 50
# Pre-press hold: brief pause after mouseDown before motion starts. Android's
# GestureDetector wants to see "press then drift" — simultaneous press+move
# can be classified as a tap or scroll-start instead of a fling. 5ms is the
# floor at which the press still registers ahead of the first move.
SWIPE_PRE_MOVE_HOLD_SECONDS = 0.003
# Post-move hold: pause at endpoint before mouseUp. BlueStacks computes fling
# velocity from the trailing move events; lifting instantly skews that math
# and the swipe gets registered as a slow drag (or ignored).
#
# 0.010 stood here while Windows' 15.6ms timer silently rounded every sleep up,
# so the real hold was ~15ms. Once timeBeginPeriod(1) made sleeps honest, the
# shortened hold dropped 5 of 7 swipes (2026-08-24 05:41). This is now the real
# number, not a value the timer was quietly correcting.
SWIPE_POST_MOVE_HOLD_SECONDS = 0.030
# How many move events the synthetic glide sends. Enough for BlueStacks to see
# a continuous drag; few enough that per-step overhead stays negligible.
SWIPE_SYNTHETIC_STEPS = 6

# Recorded-flick mode: when SWIPE_USE_PROFILE is True and SWIPE_PROFILE holds
# a SwipeRecording, swipe() replays the user's actual hand flick (rotated per
# direction) instead of the parameter-tuned synthetic path. The GUI populates
# these via a recorder + checkbox; falling back to the synthetic flick is
# automatic if either is unset, so existing setups keep working.
SWIPE_USE_PROFILE = False
SWIPE_PROFILE = None  # Optional[swipe_recorder.SwipeRecording]
# Timeline compression for profile replay: 2.0 plays the recorded flick in half
# its original time. 1.0 (the recording's own pace) is the default because the
# recording is a gesture BlueStacks demonstrably accepts -- the user made it by
# hand. Compressing it to ~55ms is what broke swipes on 2026-08-24; raise this
# only while watching the accepted/rejected ratio in the debug runs.
SWIPE_PROFILE_SPEED = 1.0

# Unit vectors per direction. swipe() multiplies by SWIPE_DISTANCE_PX so the
# travel distance stays tunable in one place.
_SWIPE_UNIT_DELTAS = {
    "left":  (-1, 0),
    "right": (1, 0),
    "up":    (0, -1),
    "down":  (0, 1),
}
CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS = 0.04
# adb_touch.AdbTouch while "Swipe kroz BlueStacks" is on, else None: the move's
# swipe is written into BlueStacks' touch device and the cursor never moves.
ADB_TOUCH = None
# Gap the game's targeting UI needs after the activation click before the
# target tile click registers. Must be self-sufficient: pyautogui.PAUSE (0.03)
# is too small to cover it, unlike the old 0.1 default this used to lean on.
#
# Boosters and perks raise the SAME in-game "pick a tile" prompt, so they get
# the same gap. Perks used to run on a shorter 0.25s of their own; the target
# click then landed before the prompt was interactive and the game swallowed
# it -- Mini Cleo/Hammer/Remove Cross activated but never selected a tile, and
# Teleport got at most one of its two picks. Targeted boosters never showed the
# bug precisely because they already waited 0.40s. Keep these tied together.
TARGET_PROMPT_DELAY_SECONDS = 0.40
HIGH_VOLTAGE_PROMPT_DELAY_SECONDS = TARGET_PROMPT_DELAY_SECONDS
PERK_SLOT_Y_OFFSET_RATIO = 0.44
PERK_SLOT_WIDTH_RATIO = 0.90
PERK_SLOT_HEIGHT_RATIO = 0.85
PARTY_PERK_SLOT_WIDTH_RATIO = 1.00
PARTY_PERK_SLOT_HEIGHT_RATIO = 0.93
# Template assets are 76x71 at the canonical 84px UI size.  Capturing exactly
# 76x71 gives matchTemplate no room to tolerate even a 1-2px calibration click
# difference.  An 8px canonical margin lets the template slide without lowering
# the acceptance threshold or making unrelated icons easier to accept.
PERK_SLOT_SEARCH_PADDING_RATIO = 8.0 / 84.0
# Perks UI is rendered at a fixed screen size matching the regular profile's
# cell size, regardless of the board profile. Using the current profile's
# squareSize (e.g. 74 in supersize) makes the capture region too small and
# off-center so template matching fails. Anchor perks to a reference size.
PERK_SLOT_REFERENCE_SQUARE_SIZE = 84
# Distance from the board's top edge to the perks UI center, measured per
# profile. Regular: 1042 - 417 = 625. Supersize: 1041 - 419 = 622.
PERK_SLOT_BOARD_TOP_Y_OFFSET = {
    REGULAR_PROFILE: 625,
    SUPERSIZE_PROFILE: 622,
}
# Supersize renders perk icons against a teal panel instead of the dark
# purple panel the templates were captured from. Same icon, different
# surround → template match drops to ~0.70 even for clear hits. Lower the
# acceptance threshold for supersize so real perks aren't rejected; the next
# non-matching template typically sits well below this gap.
PERK_SUPERSIZE_TEMPLATE_THRESHOLD = 0.68
PERK_PROMPT_DELAY_SECONDS = TARGET_PROMPT_DELAY_SECONDS
PERK_ANIMATION_DELAY_SECONDS = 0.35
PERK_VERIFY_DELAY_SECONDS = 0.15
BOOSTER_ACTION_NONE = "none"
# screen_state_read["score"]["source"] value used by the memory reader; it marks
# a score that came from PlayerModel.score instead of the on-screen digits.
SCORE_SOURCE_MEMORY = "memory"
BOOSTER_ACTION_HIGH_VOLTAGE = "high_voltage"
BOOSTER_ACTION_MAGIC_WAND = "magic_wand"
BOOSTER_ACTION_LASER_BEAM = "laser_beam"
BOOSTER_ACTION_DRAGON = "dragon"
BOOSTER_ACTION_WOOLLY_WORKOUT = "woolly_workout"
# The UFO has no activation of its own -- picking it only tells the bot to
# look for the eyes on the rail. Scanning for them on every turn of every
# other booster would cost a rail read the board never needs.
BOOSTER_ACTION_UFO = "ufo"
BOOSTER_ACTION_OPTIONS = (
    ("Bez posebne akcije", BOOSTER_ACTION_NONE),
    ("High Voltage", BOOSTER_ACTION_HIGH_VOLTAGE),
    ("Magic Wand", BOOSTER_ACTION_MAGIC_WAND),
    ("Laser Beam", BOOSTER_ACTION_LASER_BEAM),
    ("Dragon", BOOSTER_ACTION_DRAGON),
    ("Woolly Workout", BOOSTER_ACTION_WOOLLY_WORKOUT),
    ("UFO", BOOSTER_ACTION_UFO),
)
BOOSTER_ACTION_LABELS = {
    BOOSTER_ACTION_NONE: "Bez posebne akcije",
    BOOSTER_ACTION_HIGH_VOLTAGE: "High Voltage",
    BOOSTER_ACTION_MAGIC_WAND: "Magic Wand",
    BOOSTER_ACTION_LASER_BEAM: "Laser Beam",
    BOOSTER_ACTION_DRAGON: "Dragon",
    BOOSTER_ACTION_WOOLLY_WORKOUT: "Woolly Workout",
    BOOSTER_ACTION_UFO: "UFO",
}

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
    # ColumnManiaBoard (32): live per-column multipliers that a move raises.
    GameMode.COLUMN_MANIA,
    # LightsUpBoard (37): a lit column that raises the score multiplier.
    GameMode.LIGHTS_UP,
    # RainbowMultiplierBoard (35): two dealt colours raise the score multiplier.
    GameMode.COLOR_CLIMB,
    GameMode.HOT_COLOR,
    GameMode.ENERGIZED,
    # CandyWorldBoard (2): its candy tiles are two-colour (blue/red) pieces.
    GameMode.CANDY_WORLD,
    # DustvilleDuelBoard (4): three replenishing "wanted" tiles to collect.
    GameMode.DUSTVILLE_DUEL,
    # Rule-flag modes: one MatchRulesModel field each, no board model.
    # Board models read out of libil2cpp.so 2026-08-21. Frozen Feud simulates
    # its row clear; the other three carry the mode only so the board is read
    # and the mode stops reporting as unmapped (see MODE_WEIGHTS).
    GameMode.FROZEN_FEUD,
    GameMode.VEGAS_VIEWS,
    GameMode.BURIED_TREASURE,
    GameMode.ZANY_ZAPPERS,
    GameMode.BLOW_EM_UP,
    GameMode.LIGHTNING_STRIKE,
    GameMode.SHARED_ENERGY,
    GameMode.NONE,
)

# Persistent match-level state for The Floor Is Lava. Internal columns are
# zero-based; GUI/debug text presents them as 1..7.
_floor_lava_checked_columns: set[int] = set()
_bounty_target_value = BOUNTY_INITIAL_TARGET_VALUE


def reset_floor_lava_state() -> None:
    _floor_lava_checked_columns.clear()


def floor_lava_state() -> tuple[int, ...]:
    return tuple(sorted(_floor_lava_checked_columns))


def floor_lava_debug_state(memory_columns) -> dict | None:
    """What move.json records as the lava marks this decision was made on.

    Columns are 1-based like the predictions beside them. Call it before
    ``commit_floor_lava_evaluation``, or a "tally" state is already the
    prediction.
    """
    if recognition.curr_mode is not GameMode.FLOOR_IS_LAVA:
        return None
    if memory_columns is not None:
        columns, source = memory_columns, "memory"
    else:
        columns, source = floor_lava_state(), "tally"
    return {"columns": [int(col) + 1 for col in sorted(columns)], "source": source}


def commit_floor_lava_evaluation(evaluation: MoveEvaluation | None) -> None:
    if evaluation is None:
        return
    _floor_lava_checked_columns.clear()
    _floor_lava_checked_columns.update(evaluation.floor_lava_checked_columns_after)


def reset_bounty_state() -> None:
    global _bounty_target_value
    _bounty_target_value = BOUNTY_INITIAL_TARGET_VALUE


def bounty_state() -> int:
    return _bounty_target_value


def commit_bounty_evaluation(evaluation: MoveEvaluation | None) -> None:
    """Advance Bullseye's 5, 10, 15... reward after a collected target."""
    global _bounty_target_value
    if evaluation is None:
        return
    collected = max(0, int(round(evaluation.mode_targets)))
    _bounty_target_value += collected * BOUNTY_TARGET_VALUE_INCREASE

COLOR_DEBUG_LABELS = {
    1: "blue",
    2: "green",
    3: "yellow",
    4: "purple",
    5: "red",
    6: "orange",
    WHITE_COLOR: "white",
    CHEST_COLOR: "chest",
}
SPECIAL_DEBUG_LABELS = {
    SPECIAL_HORIZONTAL: "row",
    SPECIAL_VERTICAL: "column",
    SPECIAL_BOMB: "bomb",
    SPECIAL_LIGHTNING: "lightning",
    SPECIAL_CROSSHAIR: "crosshair",
    SPECIAL_MODE_TARGET: "mode",
    10: "created",
    SPECIAL_HEART: "heart",
    SPECIAL_KNIGHT: "knight",
    SPECIAL_CLEO_BUG: "cleo",
    SPECIAL_BILLIE_DRONE: "billie",
    SPECIAL_COLOR_CRYSTAL: "color-crystal",
    SPECIAL_DISCO_BALL: "disco",
    SPECIAL_MUSHROOM: "mushroom",
    SPECIAL_ALL_ABOARD_BANDIT: "all-aboard",
    SPECIAL_JOOJOO_SKULL: "joojoo",
    SPECIAL_FROGGY_LOTUS: "lotus",
    SPECIAL_FIREWORK_LEFT: "firework-left",
    SPECIAL_FIREWORK_RIGHT: "firework-right",
    SPECIAL_FIREWORK_UP: "firework-up",
    SPECIAL_FIREWORK_DOWN: "firework-down",
    SPECIAL_ZANY_ZAPPER_1: "zany-zapper-1",
    SPECIAL_ZANY_ZAPPER_2: "zany-zapper-2",
    SPECIAL_XTRA_MOVE_TILE: "xtra",
    SPECIAL_SWEEP_SE_BROOM: "broom",
}
AUDIT_LOG_FIELDS = (
    "closed_at",
    "previous_run",
    "after_run",
    "action",
    "mode",
    "profile",
    "selected_action",
    "allow_square_matches",
    "specials_explode_immediately",
    "color_crush",
    "energized_colors",
    "vertical_matches_destroy_color",
    "matches_destroy_color",
    "all_specials_lightning",
    "line_destruction",
    "include_future_value",
    "score_rally_values",
    "special_piece_mode",
    "selected_perks",
    "booster_active",
    "booster_score",
    "move_start",
    "move_target",
    "move_direction",
    "predicted_score",
    "predicted_reason",
    "high_voltage_target_cell",
    "high_voltage_target_color",
    "high_voltage_expected_cleared",
    "high_voltage_expected_blue",
    "high_voltage_expected_extra_moves",
    "high_voltage_expected_activated_specials",
    "high_voltage_explanation",
    "magic_wand_target_cell",
    "magic_wand_target_color",
    "magic_wand_expected_cleared",
    "magic_wand_expected_blue",
    "magic_wand_expected_extra_moves",
    "magic_wand_expected_activated_specials",
    "magic_wand_explanation",
    "laser_beam_target_cell",
    "laser_beam_target_color",
    "laser_beam_expected_cleared",
    "laser_beam_expected_blue",
    "laser_beam_expected_extra_moves",
    "laser_beam_expected_activated_specials",
    "laser_beam_explanation",
    "dragon_move_start",
    "dragon_move_target",
    "dragon_move_direction",
    "dragon_expected_cleared",
    "dragon_expected_blue",
    "dragon_expected_extra_moves",
    "dragon_expected_activated_specials",
    "dragon_explanation",
    "board_changed_cells",
    "special_changed_cells",
    "before_score_region",
    "after_score_region",
    "manual_note",
)

PERK_TARGET_NONE = "none"
PERK_TARGET_TILE = "tile"
PERK_TARGET_COLUMN = "column"
PERK_TARGET_TWO_TILES = "two_tiles"
PERK_DETERMINISTIC_TRUE = "true"
PERK_DETERMINISTIC_FALSE = "false"
PERK_DETERMINISTIC_PARTIAL = "partial"
PERK_NONE = "none"
PERK_UNKNOWN = perk_detection.PERK_UNKNOWN
PERK_STATUS_AVAILABLE = perk_detection.PERK_STATUS_AVAILABLE
PERK_STATUS_USED = perk_detection.PERK_STATUS_USED
PERK_STATUS_UNKNOWN = perk_detection.PERK_STATUS_UNKNOWN
PERK_HAMMER = "hammer"
PERK_SHUFFLE = "shuffle"
PERK_STAR_MAKER = "star_maker"
PERK_ENERGY_BOOST = "energy_boost"
PERK_TELEPORT = "teleport"
PERK_CHECKERBOARD = "checkerboard"
PERK_REMOVE_CROSS = "remove_cross"
PERK_MINI_CLEO = "mini_cleo"
PERK_MINI_COBRA = "mini_cobra"
PERK_MINI_MASTERMIND = "mini_mastermind"
PERK_MINI_WAND = "mini_wand"
PERK_CREATE_LIGHTNING = "create_lightning"

_booster_ready_latch = {
    "booster_action_mode": None,
    "detection": None,
    "miss_count": 0,
}
# The text-band heuristic fires on any wide white overlay (score popups, combo
# texts, glare), so a single such frame is not enough evidence that the booster
# is ready. Instead of deferring to the next turn (which wastes the current
# move on a normal swap when the booster IS ready), re-capture the button once
# after a short delay and only latch when the second look still sees it.
# Template word matches keep activating instantly -- their thresholds are
# specific enough, and delaying them cost real moves in play.
BOOSTER_TEXT_BAND_RETRY_DELAY_SECONDS = 0.35
# A latched ready state that keeps failing raw re-detection is more likely a
# stale false positive than a run of missed frames; expire it after this many
# consecutive misses instead of holding "Activate booster" forever.
BOOSTER_LATCH_MAX_CONSECUTIVE_MISSES = 2
# An accepted blue-meter read at or below this charge (meter scale 0..6) means
# the bar is clearly partial, so a weak activate detection on the same scan is
# a false positive. An active template word match outranks the meter: the
# pulsing ACTIVATE glow can wash the blue out of the meter crop, and vetoing on
# that frame made the bot miss genuinely full boosters.
BOOSTER_METER_VETO_MAX_CHARGE = 4
PERK_DETONATOR = "detonator"
PERK_BOMB_DELIVERY = "bomb_delivery"

runtime_initialized = False
win = None

@dataclass(frozen=True)
class PerkDefinition:
    key: str
    label: str
    target_type: str
    effect_type: str
    deterministic: str
    rescan_required: bool
    requires_next_move: bool = False


PERK_DEFINITIONS = {
    PERK_HAMMER: PerkDefinition(
        PERK_HAMMER,
        "Hammer",
        PERK_TARGET_TILE,
        "remove_tile",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_SHUFFLE: PerkDefinition(
        PERK_SHUFFLE,
        "Shuffle",
        PERK_TARGET_NONE,
        "shuffle_board",
        PERK_DETERMINISTIC_FALSE,
        True,
    ),
    PERK_STAR_MAKER: PerkDefinition(
        PERK_STAR_MAKER,
        "Star Maker",
        PERK_TARGET_NONE,
        "add_blue_stars",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_ENERGY_BOOST: PerkDefinition(
        PERK_ENERGY_BOOST,
        "Energy Boost",
        PERK_TARGET_NONE,
        "next_match_counts_as_blue",
        PERK_DETERMINISTIC_TRUE,
        False,
        requires_next_move=True,
    ),
    PERK_TELEPORT: PerkDefinition(
        PERK_TELEPORT,
        "Teleport",
        PERK_TARGET_TWO_TILES,
        "swap_two_tiles",
        PERK_DETERMINISTIC_TRUE,
        True,
    ),
    PERK_CHECKERBOARD: PerkDefinition(
        PERK_CHECKERBOARD,
        "Checkerboard",
        PERK_TARGET_NONE,
        "duplicate_random_colors_checkerboard",
        PERK_DETERMINISTIC_FALSE,
        True,
    ),
    PERK_REMOVE_CROSS: PerkDefinition(
        PERK_REMOVE_CROSS,
        "Remove Cross",
        PERK_TARGET_TILE,
        "remove_row_and_column",
        PERK_DETERMINISTIC_TRUE,
        True,
    ),
    PERK_MINI_CLEO: PerkDefinition(
        PERK_MINI_CLEO,
        "Mini Cleo",
        PERK_TARGET_TILE,
        "duplicate_selected_color",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_MINI_COBRA: PerkDefinition(
        PERK_MINI_COBRA,
        "Mini Cobra",
        PERK_TARGET_COLUMN,
        "clone_column",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_MINI_MASTERMIND: PerkDefinition(
        PERK_MINI_MASTERMIND,
        "Mini Mastermind",
        PERK_TARGET_NONE,
        "auto_rearrange_special_matches",
        PERK_DETERMINISTIC_FALSE,
        True,
    ),
    PERK_MINI_WAND: PerkDefinition(
        PERK_MINI_WAND,
        "Mini Wand",
        PERK_TARGET_NONE,
        "remove_random_color",
        PERK_DETERMINISTIC_FALSE,
        True,
    ),
    PERK_CREATE_LIGHTNING: PerkDefinition(
        PERK_CREATE_LIGHTNING,
        "Create Lightning",
        PERK_TARGET_NONE,
        "create_two_lightnings",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_DETONATOR: PerkDefinition(
        PERK_DETONATOR,
        "Detonator",
        PERK_TARGET_NONE,
        "detonate_all_specials",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
    PERK_BOMB_DELIVERY: PerkDefinition(
        PERK_BOMB_DELIVERY,
        "Bomb Delivery",
        PERK_TARGET_NONE,
        "center_bomb",
        PERK_DETERMINISTIC_PARTIAL,
        True,
    ),
}
PERK_OPTIONS = (
    ("None", PERK_NONE),
    *(
        (definition.label, definition.key)
        for definition in PERK_DEFINITIONS.values()
    ),
)


def auto_board_signature(board, special_board):
    return (
        tuple(tuple(row) for row in board),
        tuple(tuple(row) for row in special_board),
    )


AUTO_SETTLED_IGNORED_SPECIALS = frozenset({SPECIAL_XTRA_MOVE_TILE})


def _auto_settled_special_value(value):
    return 0 if value in AUTO_SETTLED_IGNORED_SPECIALS else value


def auto_settled_board_signature(board, special_board):
    return (
        tuple(tuple(row) for row in board),
        tuple(
            tuple(_auto_settled_special_value(value) for value in row)
            for row in special_board
        ),
    )


def _auto_settled_signature_from_signature(signature):
    if not (
        isinstance(signature, tuple)
        and len(signature) == 2
        and isinstance(signature[1], tuple)
    ):
        return signature
    return (
        signature[0],
        tuple(
            tuple(_auto_settled_special_value(value) for value in row)
            for row in signature[1]
        ),
    )


def board_has_unrecognized_cells(board):
    return any(0 in row for row in board)


def auto_board_has_unresolved_match(board, special_board, allow_square_matches=False):
    """True when the recognized board still shows a match the game will clear.

    Uses the same match semantics as the cascade simulator (colored specials
    match as their color, color-flexible tiles via special_board), so "would
    the game auto-resolve this" agrees with what the strategy simulates.
    Returns None for unknown boards (unrecognized cells): mid-fall cells read
    as 0 and the plain stability gate already blocks those frames.
    """
    if not board or board_has_unrecognized_cells(board):
        return None
    return bool(
        find_matches(
            board,
            allow_square_matches=allow_square_matches,
            special_board=special_board,
        )
    )

def board_scan_block_reason(board):
    if board_has_unrecognized_cells(board):
        return "unrecognized_cells"
    return None


def board_zero_count(board):
    return sum(1 for row in board for value in row if value == 0)


@dataclass(frozen=True)
class RecognitionFrameSample:
    index: int
    board: list[list[int]]
    special_board: list[list[int]]
    diag: dict
    zero_count: int
    block_reason: str | None
    image: object | None = None


def _wait_until_board_still(
    previous_image,
    max_seconds,
    *,
    board_size=None,
    poll_seconds=MANUAL_RECOGNITION_STILL_POLL_SECONDS,
):
    """Block until the board stops moving, or until max_seconds runs out.

    Replaces a flat sleep between "Cekaj anim." frames. The sleep existed so the
    next recognition could not land inside the same animation frame and repeat
    its artefact -- i.e. it was a guess at how long movement lasts. Watching the
    pixels answers that directly, using the same stillness bound the auto loop
    already settles on (AUTO_STILL_CORE_MOTION_MAX). A settled board returns
    after one poll; an animating one still waits the whole budget, so the
    "really wait for the animation" guarantee is unchanged. Returns the
    milliseconds actually spent, for the timing breakdown.
    """
    started = time.perf_counter()
    if max_seconds <= 0:
        return 0.0
    if previous_image is None:
        # Nothing to compare against: fall back to the flat wait rather than
        # skipping it, so a cache miss can never shorten the animation guard.
        time.sleep(max_seconds)
        return max_seconds * 1000
    region = (recognition.left, recognition.up, recognition.width, recognition.height)
    deadline = started + max_seconds
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        time.sleep(min(poll_seconds, remaining))
        current_image = capture.capture_debug_screenshot(
            output_path=None,
            region=region,
            write_to_disk=False,
        )
        if current_image is None:
            break
        core_motion = auto_core_motion_score(
            previous_image,
            current_image,
            board_size=board_size,
        )
        if float(core_motion) <= AUTO_STILL_CORE_MOTION_MAX:
            break
        previous_image = current_image
    return (time.perf_counter() - started) * 1000


def _copy_grid(grid):
    return [list(row) for row in grid]


def _recognition_sample_signature(sample: RecognitionFrameSample):
    return auto_board_signature(sample.board, sample.special_board)


def _select_majority_recognition_sample(samples):
    by_signature = {}
    for sample in samples:
        if sample.block_reason is not None:
            continue
        by_signature.setdefault(_recognition_sample_signature(sample), []).append(sample)

    winners = [
        same_signature_samples
        for same_signature_samples in by_signature.values()
        if len(same_signature_samples) >= MANUAL_RECOGNITION_MIN_AGREEING_FRAMES
    ]
    if not winners:
        return None

    winners.sort(key=lambda group: (len(group), group[-1].index), reverse=True)
    return winners[0][-1]


def _manual_recognition_unsafe_reason(samples):
    if any(sample.block_reason == "unrecognized_cells" for sample in samples):
        return "unrecognized_cells"
    return "unstable_frames"


def _frame_majority_payload(samples, selected_sample, unsafe_reason):
    if selected_sample is not None:
        decision = "accepted_majority"
        final_source = "majority"
    else:
        decision = "unsafe"
        final_source = "last_frame"
    return {
        "enabled": True,
        "frames_captured": len(samples),
        "frame_delay_ms": round(MANUAL_RECOGNITION_FRAME_DELAY_SECONDS * 1000),
        "min_agreeing_frames": MANUAL_RECOGNITION_MIN_AGREEING_FRAMES,
        "decision": decision,
        "unsafe_reason": unsafe_reason,
        "final_source": final_source,
        "selected_frame": selected_sample.index if selected_sample is not None else None,
    }


def _frame_majority_disabled_payload(frames_captured):
    return {
        "enabled": False,
        "frames_captured": frames_captured,
        "frame_delay_ms": 0,
        "min_agreeing_frames": 1,
        "decision": "disabled",
        "unsafe_reason": None,
        "final_source": "single_frame",
        "selected_frame": frames_captured if frames_captured else None,
    }


class AutoMoveStability:
    def __init__(
        self,
        required_scans=AUTO_STABLE_REQUIRED_SCANS,
        suspicious_required_scans=AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS,
        motion_threshold=AUTO_MOTION_THRESHOLD,
        hash_max_distance=AUTO_VISUAL_HASH_MAX_DISTANCE,
        force_settle_scans=AUTO_SETTLED_SIGNATURE_FORCE_SCANS,
        still_core_motion_max=AUTO_STILL_CORE_MOTION_MAX,
        no_match_settle_scans=AUTO_NO_MATCH_SETTLE_SCANS,
        min_stable_seconds=AUTO_MIN_STABLE_SECONDS,
        no_match_settle_seconds=AUTO_NO_MATCH_SETTLE_SECONDS,
        force_settle_seconds=AUTO_FORCE_SETTLE_SECONDS,
    ):
        self.base_required_scans = required_scans
        self.suspicious_required_scans = max(suspicious_required_scans, required_scans)
        self.required_scans = required_scans
        self.motion_threshold = motion_threshold
        self.hash_max_distance = hash_max_distance
        self.still_core_motion_max = still_core_motion_max
        # A match-free settle is deterministic game knowledge, so it may match
        # the suspicious count, but never undercut it: mid-animation misreads
        # still need the extra confirmation scan.
        self.no_match_settle_scans = max(
            no_match_settle_scans, self.suspicious_required_scans
        )
        self.min_stable_seconds = max(0.0, float(min_stable_seconds))
        self.no_match_settle_seconds = max(
            self.min_stable_seconds, float(no_match_settle_seconds)
        )
        self.force_settle_seconds = max(
            self.no_match_settle_seconds, float(force_settle_seconds)
        )
        # Keep the force-settle bound strictly above the suspicious count so it is
        # only ever a last-resort fallback, never the normal acceptance path.
        self.force_settle_scans = max(force_settle_scans, self.suspicious_required_scans + 1)
        self.reset()

    def reset(self):
        self.last_signature = None
        self.last_visual_hash = None
        self.last_hash_distance = None
        self.last_motion_score = 0.0
        self.last_core_motion_score = None
        self.stable_count = 0
        self.still_count = 0
        self.played_signature = None
        self.waiting_for_change = False
        self.wait_reason = None
        self.previous_image = None
        self.required_scans = self.base_required_scans
        self.suspicious_until_stable = False
        self.observed_signature = None
        self.observed_repeat_count = 0
        self.observed_signature_since = None
        self.observed_stable_seconds = 0.0

    def _note_observed_signature(self, signature, observed_at):
        if signature == self.observed_signature:
            self.observed_repeat_count += 1
        else:
            self.observed_signature = signature
            self.observed_repeat_count = 1
            self.observed_signature_since = observed_at
        if observed_at is None or self.observed_signature_since is None:
            self.observed_stable_seconds = 0.0
        else:
            self.observed_stable_seconds = max(
                0.0, float(observed_at) - float(self.observed_signature_since)
            )

    def _stable_for(self, seconds, observed_at):
        # Tests and non-GUI callers that do not provide a clock keep the legacy
        # scan-count contract.  The GUI always supplies monotonic time, which is
        # the production safety gate against ultra-fast inter-animation scans.
        if observed_at is None:
            return True
        return self.observed_stable_seconds + 1e-9 >= max(0.0, float(seconds))

    def _require_suspicious_stability(self):
        self.required_scans = self.suspicious_required_scans
        self.suspicious_until_stable = True

    def _clear_suspicious_stability_if_ready(self):
        if self.suspicious_until_stable:
            self.required_scans = self.base_required_scans
            self.suspicious_until_stable = False

    def _can_count_visual_animation(self, signature, core_motion_score):
        if self.last_signature is None or signature != self.last_signature:
            return False
        if self.waiting_for_change and signature == self.played_signature:
            return False
        if core_motion_score is None:
            return False
        return float(core_motion_score) <= self.motion_threshold

    def _count_stable_observation(self, signature, visual_hash, observed_at=None):
        if signature == self.last_signature:
            self.stable_count += 1
        else:
            self.last_signature = signature
            self.stable_count = 1
            self.still_count = 0
        self.last_visual_hash = visual_hash
        if (
            self.last_core_motion_score is not None
            and self.last_core_motion_score <= self.still_core_motion_max
            and self.last_motion_score <= self.motion_threshold
        ):
            self.still_count += 1
        else:
            self.still_count = 0

        self.wait_reason = "stable"
        if (
            self.stable_count >= self.required_scans
            and self._stable_for(self.min_stable_seconds, observed_at)
        ):
            self._clear_suspicious_stability_if_ready()
            return True
        if (
            self.required_scans > self.base_required_scans
            and self.stable_count >= self.base_required_scans
            and self.still_count >= self.base_required_scans
            and self._stable_for(self.min_stable_seconds, observed_at)
        ):
            # Dead-still fast path: the suspicious gate exists to catch
            # mid-animation misreads, but base-count identical scans with
            # near-zero core motion already prove the board settled.
            self._clear_suspicious_stability_if_ready()
            self.wait_reason = "stable_still"
            return True
        return False

    def observe(
        self,
        board,
        special_board,
        visual_hash=None,
        motion_score=0.0,
        core_motion_score=None,
        board_has_match=None,
        observed_at=None,
        authoritative=False,
        engine_move_ready=None,
    ):
        # authoritative=True means the board came straight out of the engine
        # (memory reader), not off pixels. Scan counts, motion scores and the
        # wall-clock floors all exist to guard against ML misreads mid-animation
        # -- an engine board cannot misread, so they are skipped. The two gates
        # that remain are engine truths: empty cells mean pieces are still
        # falling, and an unresolved match means the cascade is still running.
        self.wait_reason = None
        self.last_hash_distance = None
        self.last_motion_score = float(motion_score or 0.0)
        self.last_core_motion_score = (
            None if core_motion_score is None else float(core_motion_score)
        )

        if board_has_unrecognized_cells(board):
            self.last_signature = None
            self.last_visual_hash = None
            self.stable_count = 0
            self.still_count = 0
            self.observed_signature = None
            self.observed_repeat_count = 0
            self.observed_signature_since = None
            self.observed_stable_seconds = 0.0
            self.wait_reason = "unrecognized"
            self._require_suspicious_stability()
            return False

        signature = auto_settled_board_signature(board, special_board)
        if self.waiting_for_change and signature == self.played_signature:
            self.wait_reason = "change"
            return False

        if self.waiting_for_change and signature != self.played_signature:
            self._require_suspicious_stability()
            self.waiting_for_change = False
            self.played_signature = None
            self.last_signature = None
            self.last_visual_hash = None
            self.stable_count = 0
            self.still_count = 0
            self.observed_signature = None
            self.observed_repeat_count = 0
            self.observed_signature_since = None
            self.observed_stable_seconds = 0.0

        # Count consecutive identical recognized signatures independently of the
        # motion/visual resets below. A board that reads the same this many scans
        # in a row is settled even if cosmetic animation keeps motion high.
        self._note_observed_signature(signature, observed_at)

        if authoritative and engine_move_ready is False:
            # The engine's own GameState says it is not accepting a swipe yet
            # (move still processing / turn machinery running). This is the
            # ground truth the pixel gates only ever approximated, so wait on
            # it directly. None stays distinct: an agent without the state
            # block falls through to the full/no-match gates below.
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            self.stable_count = 0
            self.still_count = 0
            self.wait_reason = "engine_busy"
            return False

        if authoritative and board_has_match is not None:
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            if board_has_match:
                # Engine still resolving: the visible line pops on its own.
                self.stable_count = 0
                self.still_count = 0
                self.wait_reason = "match_pending"
                return False
            if self.observed_repeat_count < 2:
                # One more scan (~16ms) to confirm: the engine flips back to
                # MovePlaying while a previous special's destruction can still
                # be landing, so a single read can catch an intermediate board.
                # The 2026-08-24 05:03 session computed two moves on such
                # frames (predicted 31/19 cleared, observed 15/8). Two
                # identical consecutive reads prove the board stopped moving.
                self.stable_count = 0
                self.still_count = 0
                self.wait_reason = "memory_confirm"
                return False
            # Full, match-free and repeated straight from the engine: settled,
            # play now even while the pixel animation tails off.
            self.stable_count = max(self.stable_count, self.required_scans)
            self._clear_suspicious_stability_if_ready()
            self.wait_reason = "memory_settled"
            return True

        if board_has_match:
            # The game clears every match the moment it forms, so a board that
            # still shows one is mid-cascade: the visible line is about to pop
            # even if motion and signature look calm between clear frames.
            # Only a dead-still board that has repeated past the force-settle
            # bound escapes the veto — that is a persistent misread (phantom
            # match), not a cascade, and stalling on it would leave recovery
            # to the much slower watchdog.
            dead_still_misread = (
                self.observed_repeat_count >= self.force_settle_scans
                and self._stable_for(self.force_settle_seconds, observed_at)
                and self.last_core_motion_score is not None
                and self.last_core_motion_score <= self.still_core_motion_max
                and self.last_motion_score <= self.motion_threshold
            )
            if not dead_still_misread:
                self.last_signature = signature
                self.last_visual_hash = visual_hash
                self.stable_count = 0
                self.still_count = 0
                self.wait_reason = "match_pending"
                self._require_suspicious_stability()
                return False

        if (
            self.observed_repeat_count >= self.force_settle_scans
            and self._stable_for(self.force_settle_seconds, observed_at)
        ):
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            self.stable_count = max(self.stable_count, self.required_scans)
            self._clear_suspicious_stability_if_ready()
            self.wait_reason = "settled_signature"
            return True

        if (
            board_has_match is False
            and self.observed_repeat_count >= self.no_match_settle_scans
            and self._stable_for(self.no_match_settle_seconds, observed_at)
        ):
            # Fully recognized, match-free, and identical this many scans in a
            # row: the cascade is provably over (falling pieces read as
            # unrecognized cells or change the signature every frame), so
            # settle now instead of letting cosmetic animation keep resetting
            # the motion/hash gates until the force-settle escape.
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            self.stable_count = max(self.stable_count, self.required_scans)
            self._clear_suspicious_stability_if_ready()
            self.wait_reason = "settled_no_match"
            return True

        if self.last_motion_score > self.motion_threshold:
            if self._can_count_visual_animation(signature, self.last_core_motion_score):
                return self._count_stable_observation(
                    signature, visual_hash, observed_at
                )
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            self.stable_count = 0
            self.still_count = 0
            self.wait_reason = "motion"
            self._require_suspicious_stability()
            return False

        if (
            signature == self.last_signature
            and self.last_visual_hash is not None
            and visual_hash is not None
        ):
            self.last_hash_distance = auto_visual_hash_distance(self.last_visual_hash, visual_hash)
            if self.last_hash_distance is not None and self.last_hash_distance > self.hash_max_distance:
                if self._can_count_visual_animation(signature, self.last_core_motion_score):
                    return self._count_stable_observation(
                        signature, visual_hash, observed_at
                    )
                self.last_visual_hash = visual_hash
                self.stable_count = 0
                self.still_count = 0
                self.wait_reason = "visual"
                self._require_suspicious_stability()
                return False

        return self._count_stable_observation(signature, visual_hash, observed_at)

    def mark_played(self, signature=None):
        self.played_signature = (
            _auto_settled_signature_from_signature(signature)
            if signature is not None
            else self.last_signature
        )
        self.waiting_for_change = self.played_signature is not None
        self.last_signature = None
        self.last_visual_hash = None
        self.last_hash_distance = None
        self.stable_count = 0
        self.still_count = 0
        self.observed_signature = None
        self.observed_repeat_count = 0
        self.observed_signature_since = None
        self.observed_stable_seconds = 0.0
        if self.waiting_for_change:
            self._require_suspicious_stability()


@dataclass(frozen=True)
class PlayAgainDetection:
    active: bool
    score: float = 0.0
    region: tuple[int, int, int, int] | None = None
    click_point: tuple[int, int] | None = None
    reason: str = ""


def _play_again_search_region(image_width, image_height):
    x1 = max(0, int(round(image_width * 0.20)))
    x2 = min(image_width, int(round(image_width * 0.67)))
    y1 = max(0, int(round(image_height * 0.84)))
    y2 = min(image_height, int(round(image_height * 0.995)))
    return x1, y1, max(0, x2 - x1), max(0, y2 - y1)


def detect_play_again_button(image):
    if image is None:
        return PlayAgainDetection(False, reason="no_image")

    image = image.convert("RGB")
    image_width, image_height = image.size
    x, y, width, height = _play_again_search_region(image_width, image_height)
    if width <= 0 or height <= 0:
        return PlayAgainDetection(False, region=(x, y, width, height), reason="empty_region")

    crop = image.crop((x, y, x + width, y + height)).convert("HSV")
    hsv = np.asarray(crop, dtype=np.uint8)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    vivid = (saturation >= 55) & (value >= 90)
    red_or_orange = (hue <= 60) | (hue >= 240)
    blue = (hue >= 132) & (hue <= 170)
    mask = (vivid & (red_or_orange | blue)).astype(np.uint8)

    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask,
        connectivity=8,
    )
    if component_count <= 1:
        return PlayAgainDetection(False, region=(x, y, width, height), reason="no_component")

    best_index = max(
        range(1, component_count),
        key=lambda index: stats[index, cv2.CC_STAT_AREA],
    )
    component_x = int(stats[best_index, cv2.CC_STAT_LEFT])
    component_y = int(stats[best_index, cv2.CC_STAT_TOP])
    component_width = int(stats[best_index, cv2.CC_STAT_WIDTH])
    component_height = int(stats[best_index, cv2.CC_STAT_HEIGHT])
    component_area = int(stats[best_index, cv2.CC_STAT_AREA])
    region_area = max(1, width * height)
    score = component_area / region_area

    button_like = (
        score >= 0.16
        and component_width >= width * 0.55
        and component_height >= height * 0.35
    )
    if not button_like:
        return PlayAgainDetection(
            False,
            score=score,
            region=(x, y, width, height),
            reason="component_too_small",
        )

    click_x = x + component_x + component_width // 2
    click_y = y + component_y + component_height // 2
    return PlayAgainDetection(
        True,
        score=score,
        region=(x, y, width, height),
        click_point=(int(click_x), int(click_y)),
        reason="button_shape",
    )


def click_play_again_button(
    detection,
    return_position=None,
    return_delay=None,
):
    # Sentinel-resolve so a live edit of CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS
    # (e.g. from the GUI tuning panel) takes effect on the next call. A bare
    # default arg captures the value at def-time and ignores later updates.
    if return_delay is None:
        return_delay = CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS
    if not getattr(detection, "active", False) or detection.click_point is None:
        return False

    if return_position is None:
        return_position = pyautogui.position()

    click_x = recognition.left + int(detection.click_point[0])
    click_y = recognition.up + int(detection.click_point[1])
    game_click(click_x, click_y)
    time.sleep(return_delay)
    pyautogui.moveTo(return_position[0], return_position[1])
    return True


@contextlib.contextmanager
def _multiplier_states_active(
    column_mania_multipliers,
    score_multiplier,
    remaining_moves,
    multiplier_colors=None,
    match_seconds_left=None,
):
    """Column Mania's per-column ramp and the player's own score multiplier.

    Entered as one block because the `with` in `compute_move` is already at
    CPython's limit of 20 statically nested blocks -- one more entry there is a
    SyntaxError, not a style question. Both price a multiplier point by what is
    left to spend it on, so they take the same move count. Color Climb's dealt
    colour pair rides along for the same reason.
    """
    with column_mania_state_active(column_mania_multipliers, remaining_moves):
        with score_multiplier_state_active(
            score_multiplier, remaining_moves, match_seconds_left
        ):
            with multiplier_colors_active(multiplier_colors):
                yield


# Timed race (Showdown / Party / Master League), meter full, and the CLOCK --
# not the counter -- ends this turn (move_strategy._time_bound_turn): the
# booster goes before extras, as with the "Booster odmah" toggle. An extra
# only feeds a counter the clock will never let us exhaust (TIME_BOUND_TURNS),
# while every second spent in front of a full meter is charge burned and a
# fire that may not come at all. Measured over Debug/runs 2026-11-04..11-10
# (figures from the 2026-11-10 analysis): 913 race moves played on a full
# meter (752 of them extras) burned 1631 of 7482 collected blue (22%); half
# the activations had at least one full-meter move before them (mean 1.07);
# 7 of 11 races ended on 7/7. The toggle's own exceptions stay: a strong extra
# (_valuable_extra_before_immediate_booster), the Color Climb dealt-colour
# extra, jelly / Cleo / Brocco gates, and every lotus, Mixy and Color Climb
# gate that already precedes the booster decision. Versus and the true Solo
# Challenge are untouched (their turns end on the counter).
TIME_BOUND_BOOSTER_FIRST = True
TIME_BOUND_BOOSTER_GATE = "booster_time_bound_gate"


def time_bound_booster_first(turn_state, strategy_context) -> bool:
    """Whether a full meter fires before extras because the clock ends the turn."""
    if not TIME_BOUND_BOOSTER_FIRST:
        return False
    context = strategy_context_or_unknown(strategy_context)
    if not context.is_solo_6 or context.is_solo_challenge:
        return False
    return _time_bound_turn(turn_state, context)


def select_booster_action_with_gate(
    ranked_moves,
    booster_active,
    booster_immediate=False,
    turn_state=None,
    strategy_context=None,
    jelly_zone_pending=False,
    multiplier_extra_colors=(),
    disco_before_booster=None,
):
    if (strategy_context_or_unknown(strategy_context).is_solo_challenge
            and ranked_moves and getattr(ranked_moves[0], "decision_gate", "")
            in {"solo_target_finish_gate", "solo_target_refill_gate", "jelly_stage_cross_gate"}):
        return "move", ranked_moves[0], ranked_moves[0].decision_gate
    if booster_active:
        # Armed UFO eyes never hold a ready booster (player, 2026-09-15): only
        # a guaranteed extra does, below. The old `ufo_pending_eye_gate` played
        # plain moves on a full meter while eyes were armed -- and on
        # 2026-09-15 03:54:06 it ended a match with the booster unused, on an
        # eye that had already fired.
        # Color Climb: a sure extra that makes a combo in one of the player's
        # multiplier colours -- by its own match or by a sure cascade, whatever
        # colour the extra itself is (player, 2026-10-08) -- keeps the turn
        # *and* raises the multiplier, and the engine's own hook skips the
        # raise on a move that spent the booster. So even with "booster
        # immediately" on, that extra goes first and the booster fires on the
        # move it buys. Other extras keep the immediate toggle's behaviour.
        if multiplier_extra_colors:
            with multiplier_colors_active(multiplier_extra_colors):
                climb_extra = color_climb_extra_before_booster(
                    ranked_moves, GameMode.COLOR_CLIMB
                )
            if climb_extra is not None:
                return "move", climb_extra, "multiplier_color_extra_before_booster_gate"
        # Jelly SE: activation repaints a fresh zone, so while the current
        # zone still has a move that converts it, that move goes first --
        # firing over it throws the conversion away (measured 2026-08-26
        # 03:38:17: activation with 14 jelly cells pending). One converting
        # move consumes the zone, so the very next decision activates.
        # Applies in immediate mode too; with no converting move available
        # the activation proceeds as before. Keyed on the conversion event,
        # not on `jelly_converted_tiles` (the SURVIVING tiles): a conversion
        # whose blob clears itself in cascade 2 -- the usual one -- has zero
        # survivors and never passed here.
        if jelly_zone_pending:
            for evaluation in ranked_moves:
                if (
                    jelly_conversion_tiles(evaluation) > 0
                    and getattr(evaluation, "disco_moves", 0) <= 0
                ):
                    return "move", evaluation, "jelly_before_booster_gate"
        # Cleo swaps never block a ready booster (the booster adds Cleos, it
        # does not destroy them) -- except the ones the Cleo tier flagged: a
        # special partner, a mushroom at 80%, or the most valuable colour
        # (player, 2026-09-15; move_strategy._cleo_goes_before_booster).
        for evaluation in ranked_moves:
            if getattr(evaluation, "cleo_before_booster", False):
                return "move", evaluation, "cleo_before_booster_gate"
        # A ready booster is spent as soon as it is not blocked by a direct
        # extra: it is never banked for a future versus round. (The old
        # "save on the last move of a non-final round" gate was removed.)
        # Brocco balls outside Solo Challenge (player, 2026-10-08): every ball
        # is thrown before the booster fires -- the swap is free and buys
        # points. A strong extra still went first (forced-extra path above
        # the gate), so the order is extras, balls, booster.
        if booster_immediate and disco_before_booster is not None:
            return "move", disco_before_booster, "disco_before_booster_gate"
        if booster_immediate:
            return "activate_booster", None, "booster_immediate_toggle_gate"
        # A GUARANTEED extra may hold a ready booster: direct (match-4+/square
        # by the swap itself) or a cascade whose match uses only tiles already
        # on the board (has_guaranteed_true_extra rejects anything behind a
        # random-refill boundary or an unstable special). Firing first would
        # rearrange the board and throw the guaranteed extra away — measured
        # 2026-08-27 21:03:39: final move, deterministic orange-four cascade
        # extra discarded by activating over it. Refill-dependent cascade
        # promises still do not block: activation is free, so firing wins.
        for evaluation in ranked_moves:
            if (
                has_guaranteed_true_extra(evaluation)
                and max(
                    getattr(evaluation, "extra_moves", 0),
                    getattr(evaluation, "direct_extra_moves", 0),
                )
                > 0
                and getattr(evaluation, "disco_moves", 0) <= 0
            ):
                return "move", evaluation, "booster_blocked_by_true_extra_gate"
        for evaluation in ranked_moves:
            if (
                getattr(evaluation, "direct_extra_moves", 0) > 0
                and getattr(evaluation, "disco_moves", 0) <= 0
            ):
                return "move", evaluation, "booster_blocked_by_direct_extra_gate"
        if disco_before_booster is not None:
            return "move", disco_before_booster, "disco_before_booster_gate"
        return "activate_booster", None, "booster_after_extra_spend_gate"
    if ranked_moves:
        gate = getattr(ranked_moves[0], "decision_gate", "unknown")
        if gate == "unknown":
            gate = "score_gate"
        return "move", ranked_moves[0], gate
    return "none", None, "no_action_gate"


def _color_climb_extra_colors() -> frozenset[int]:
    """The multiplier colours an ordinary extra should be played in first.

    Only Color Climb asks for this (the user's rule for the "booster
    immediately" toggle); Multiplier Madness keeps its existing gates. Reads
    the pair the memory path supplied for this move, so outside the mode or
    without a memory reading it is empty and the gate is inert.
    """
    if recognition.curr_mode is not GameMode.COLOR_CLIMB:
        return frozenset()
    return multiplier_growth_colors(GameMode.COLOR_CLIMB)


# Minimum flat-score margin by which a laser cross must beat the best normal move
# before the bot spends the booster. 0.0 means "fire if at least as good"; raise
# it to make the bot hoard the booster unless the cross is clearly better.
LASER_FIRE_SCORE_MARGIN = 0.0


def should_fire_laser_over_move(laser_target, normal_baseline, booster_immediate):
    """Decide whether firing the laser now beats just playing the best move.

    Both scores are on the same flat scale (instant + special + blue + mode +
    extra + potential), so they compare directly. When immediate activation is
    toggled the user wants to fire regardless; if there is no normal move to fall
    back to, firing is the only option.
    """
    if laser_target is None:
        return False
    if booster_immediate:
        return True
    if normal_baseline is None:
        return True
    return laser_target.score >= normal_baseline.score + LASER_FIRE_SCORE_MARGIN


def fallback_from_targetless_booster(normal_baseline, booster_action_mode):
    """Play the best legal move when a targeted booster has no valid target."""
    gate = f"{booster_action_mode}_no_target_fallback"
    if normal_baseline is not None:
        return "move", normal_baseline, gate
    return "none", None, gate


# Whether the manual Extra-move button may fall back to a Mixy code move whose
# only extra is the engine's refund. Off since 2026-09-13: the refund misses
# roughly one credited match in five (133 of 168 landed in the 2026-08-25 -
# 2026-08-28 snapshots, and 02:42:41 on 2026-09-13 is a credited match that
# still cost the move), and the button's whole contract is "an extra or
# nothing". A code move that earns its own match-4 on the converted board is
# unaffected -- that one keeps the turn whatever the refund does.
MIXY_REFUND_ONLY_EXTRA_FALLBACK = False


def _prefer_refund_proof_mixy_extra(
    mixy_ranked, count_code_refund, score_rally_values=None
):
    """Among Mixy code candidates, prefer one whose extra survives the refund.

    The engine's refund is not unconditional even for a credited first hit on
    a fresh code: 2026-08-27 21:30:41 the green code move was credited (the
    SourceColors/TargetColor transient fired, conversion included) yet no
    re-deal followed and the moves counter stayed one short for 49 s. A
    candidate whose swap ALSO earns its own extra on the converted board
    (match-4/cross -- direct_extra_moves above the refund credit) keeps the
    Extra-move promise even when the refund does not land, so it wins over a
    higher-scoring refund-only candidate.

    Score Rally is the exception (player, 2026-09-15: green at 5 "gives by
    far the most points"): a higher-ranked code move in a colour the board
    pays MORE for is not given up for a refund-proof one in a cheaper colour
    -- the points gap dwarfs the one-in-five refund miss. Equal rates keep the
    refund-proof preference exactly as before.
    """
    refund_credit = 1.0 if count_code_refund else 0.0

    def rate(evaluation) -> float:
        color = getattr(evaluation, "mixy_code_color", None)
        if not score_rally_values or color is None:
            return 1.0
        return float(score_rally_values.get(int(color), 1.0))

    for index, evaluation in enumerate(mixy_ranked):
        refund_proof = getattr(evaluation, "direct_extra_moves", 0) > refund_credit
        if (not refund_proof and isinstance(evaluation, MoveEvaluation)
                and evaluation.extra_moves > refund_credit):
            own_extra = replace(evaluation,
                extra_moves=max(0.0, evaluation.extra_moves - refund_credit),
                direct_extra_moves=max(0.0, evaluation.direct_extra_moves - refund_credit))
            refund_proof = has_guaranteed_true_extra(own_extra)
        if refund_proof:
            for richer in mixy_ranked[:index]:
                if rate(richer) > rate(evaluation):
                    return richer
            return evaluation
    return mixy_ranked[0] if mixy_ranked else None


# How much plain evaluated score a code move may give up before it stops being
# worth forcing. The code move is played ahead of the ordinary ranking on the
# grounds that it keeps the turn, so it costs nothing -- but the refund lands
# in only ~82% of credited matches (133 of 168 in the 2026-08-25 - 2026-08-28
# snapshots), and a refund-only code move that is also far weaker than the best
# plain move is a straight loss when the refund misses. Sized above the flat
# MIXY_CODE_MATCH_BONUS-free gap of an ordinary code three-match so normal play
# is untouched: over 70 recorded code boards this only steps aside on the
# handful where the plain best more than doubles the code move.
MIXY_CODE_FORCE_SCORE_MARGIN = 30.0


def _mixy_code_move_worth_forcing(candidate, prioritized_moves, count_code_refund):
    """Whether this code move may still preempt the ordinary ranking.

    A candidate that earns its own extra on the converted board (a match-4 or
    cross beyond the refund credit) keeps the turn whatever the refund does,
    so it is always worth forcing. A refund-only candidate is compared on the
    plain scale instead -- its score minus the categorical code bonus, which
    exists to order code moves against each other and not against the rest of
    the board.
    """
    if candidate is None:
        return False
    refund_credit = 1.0 if count_code_refund else 0.0
    if getattr(candidate, "direct_extra_moves", 0.0) > refund_credit:
        return True
    if not prioritized_moves or prioritized_moves[0] is candidate:
        return True
    code_value = float(getattr(candidate, "score", 0.0)) - float(
        getattr(candidate, "mixy_code_bonus", 0.0) or 0.0
    )
    return (
        float(getattr(prioritized_moves[0], "score", 0.0))
        <= code_value + MIXY_CODE_FORCE_SCORE_MARGIN
    )


def _forced_extra_move_candidate(ranked_moves, direct_only=False, strategy_context=None):
    # direct_only: with a ready booster only swap-earned extras count; cascade
    # promises must not preempt activation (see select_booster_action_with_gate).
    #
    # Solo Challenge: a Brocco ball that keeps the turn and leads the ranking
    # with a charge plan already beat every extra there by booster charge
    # (_solo_charge_plan_order over the extra tier). Forcing the first plain
    # extra behind it threw that order away: 2026-11-11 19:10:14 (ball 3 now,
    # plan 4 -> plain extra 0 now, plan 4), 19:11:52 (last move, ball 7/7 ->
    # plain extra 5), 19:15:25 (ball 3 now, plan 7 -> plain extra plan 3).
    top = ranked_moves[0] if ranked_moves else None
    if (
        not direct_only
        and top is not None
        and strategy_context_or_unknown(strategy_context).is_solo_challenge
        and getattr(top, "disco_moves", 0) > 0
        and getattr(top, "solo_blue_plan_charge", None) is not None
        and has_reliable_same_move_extra(top)
    ):
        return None
    for evaluation in ranked_moves:
        if getattr(evaluation, "disco_moves", 0) > 0:
            continue
        if direct_only:
            if getattr(evaluation, "direct_extra_moves", 0) > 0:
                return evaluation
            continue
        if has_guaranteed_true_extra(evaluation) or getattr(evaluation, "direct_extra_moves", 0) > 0:
            return evaluation
    return None


# --- Booster odmah: only a STRONG extra delays the activation ----------------
# An extra that precedes the immediate activation must earn the delay. What
# counts as earning it: the swap activates an existing special (a lightning, a
# bomb), collects a multiplier mushroom, raises the score multiplier (a
# multiplier-colour match), or collects a Purple Gem target -- or, failing all
# of those, is simply worth real points on its own.
#
# The points floor is what separates a "strong" plain extra from the bare
# match-4 this rule exists to skip. Measured over the 286 recorded
# `booster_immediate_valuable_extra_gate` decisions:
#
#   extra kind                              n     median instant   median cells
#   activates special / mushroom / target  190              12             12
#   plain                                   96               4              4
#
# The plain group is almost entirely the minimum match: median 4 points off 4
# cells, p75 8. The floor is MEASURED_MOVE_VALUE -- an extra worth less than an
# average move is not worth delaying the booster for -- which keeps the handful
# of plain extras that are actually big (the group tops out at 31) and drops the
# rest.
#
# This narrows the 2026-08-28 solo_6 widening, deliberately and with its cost
# understood. That change let ANY direct extra precede the activation in solo_6,
# because over the 08:00-09:34 runs 28 of 88 immediate activations skipped a
# plain direct extra and 11 of those activations repainted it off the board,
# costing a full turn out of six. Waiting itself is still free (the meter stays
# full across the extra: 09-23-19 -> 09-23-25 and 09-26-11 -> 09-26-13, both 7/7
# before and after). So the trade is explicit: weak extras may again be lost to
# the activation, and that is accepted -- a 4-point match-4 is not worth the
# board churn. Strong extras still go first, in solo_6 and everywhere else.
# Party/Showdown (``booster_rush``) were always narrow and are unchanged.
IMMEDIATE_BOOSTER_STRONG_EXTRA_ONLY = True
IMMEDIATE_BOOSTER_PLAIN_EXTRA_MIN_INSTANT = MEASURED_MOVE_VALUE


def _is_last_move_of_turn(turn_state) -> bool:
    remaining = getattr(turn_state, "remaining_moves", None)
    return remaining is not None and remaining <= 1


def _is_strong_extra_before_immediate_booster(evaluation, mode, turn_state=None) -> bool:
    """Whether this extra is worth delaying ``Booster odmah`` for.

    On the last move of the turn every extra is strong: its points floor
    measures the match, but what the extra buys there is the only move left.
    2026-09-15 06:31:13 (Color Crush, 1 move left, meter 7/7): a red L extra
    worth 5 instant points was judged weak, the activation repainted it away
    and the turn ended one move short -- the move it would have bought scored
    256. The activation stays free after the extra (the meter stays full).
    """
    if _is_last_move_of_turn(turn_state):
        return True
    if getattr(evaluation, "activated_specials", 0) > 0:
        return True
    if getattr(evaluation, "multiplier_mushrooms", 0) > 0:
        return True
    # A multiplier-colour extra (purple in Multiplier Madness, a dealt colour in
    # Color Climb) raises the score multiplier by one and keeps the turn, so the
    # activation that follows -- and everything after it -- is paid at the
    # higher rate, for free. Its own points say nothing about that: a purple
    # match-4 is 4 instant points. 2026-09-18 23:50:03 (Multiplier Madness,
    # Froggy, meter 7/7): such an extra was judged weak and the activation's
    # board churn went first, with two lotus collects behind it.
    if getattr(evaluation, "multiplier_madness_points", 0) > 0:
        return True
    if mode is GameMode.PURPLE_GEM and getattr(evaluation, "mode_targets", 0) > 0:
        return True
    if not IMMEDIATE_BOOSTER_STRONG_EXTRA_ONLY:
        return True
    return (
        float(getattr(evaluation, "instant_score", 0.0))
        >= IMMEDIATE_BOOSTER_PLAIN_EXTRA_MIN_INSTANT
    )


def _valuable_extra_before_immediate_booster(
    ranked_moves, mode, strategy_context=None, turn_state=None
):
    """Return an extra that is worth spending before the immediate activation.

    ``Booster odmah`` must not idle behind an ordinary match-4/square, so only a
    strong extra precedes the activation -- see
    IMMEDIATE_BOOSTER_STRONG_EXTRA_ONLY for what strong means and what the
    narrowing costs. The activation is free afterwards, so no turn is lost.

    solo_6 keeps its own ordering within the strong ones, because there the turn
    is the scarce resource: a guaranteed cascade extra first, then any direct
    one. Party/Showdown (``booster_rush``) fall through to the single pass.
    """
    mode = normalize_game_mode(mode)
    context = strategy_context_or_unknown(strategy_context)

    def usable(evaluation):
        if getattr(evaluation, "disco_moves", 0) > 0:
            return False
        return _is_strong_extra_before_immediate_booster(evaluation, mode, turn_state)

    if context.is_solo_6 and not context.is_solo_booster_rush:
        for evaluation in ranked_moves:
            if not usable(evaluation):
                continue
            if (
                has_guaranteed_true_extra(evaluation)
                and max(
                    getattr(evaluation, "extra_moves", 0),
                    getattr(evaluation, "direct_extra_moves", 0),
                )
                > 0
            ):
                return evaluation
        for evaluation in ranked_moves:
            if not usable(evaluation):
                continue
            if getattr(evaluation, "direct_extra_moves", 0) > 0:
                return evaluation
        return None
    for evaluation in ranked_moves:
        if not usable(evaluation):
            continue
        if getattr(evaluation, "direct_extra_moves", 0) <= 0:
            continue
        return evaluation
    return None


# --- Froggy Fu + Checkerboard: save the perk for the last activation ----------
# The player's rule (2026-09-19). Checkerboard repaints the whole board into two
# colours, so about half of it becomes one colour -- and a lotus collects every
# tile of the colour matched next to it. Thrown with fresh lotuses standing, a
# collect takes ~24 tiles instead of ~9 (two dozen yellows at the lotus rate),
# which is worth far more than anything the perk does on its own. So with Froggy
# Fu the perk is not spent "whenever":
#
#   * when the match clock reaches FROGGY_CHECKERBOARD_ARM_SECONDS the rule arms;
#   * the NEXT booster activation after that -- whenever it comes -- throws
#     Checkerboard as soon as its lotuses are on the board, before the lotus move.
#
# A lotus that was already standing when the rule armed does not count: it is
# the leftover of an earlier activation (usually a single one), and the player
# asked for the next activation. If none comes the perk goes unused; that is
# accepted. The activation is recognised by what it does to the board -- the
# lotus count going UP -- so it does not matter whether the bot or the player
# pressed the booster.
#
# Timed solo only. That is where `time_left_seconds` is the MATCH clock (~105 s,
# one activation cycle is ~15 s: 00:07:15 activate -> 00:07:20 / 00:07:27 the
# two collects). In versus the same field is the turn clock, and the true Solo
# Challenge is limited by moves, not time -- the rule would strand the perk
# there, so both keep the ordinary perk policy.
FROGGY_CHECKERBOARD_ARM_SECONDS = 20.0
# The clock only runs down inside a match; a jump up by more than this is a new
# match, and whatever the tracker remembered belongs to the old one.
FROGGY_CHECKERBOARD_NEW_MATCH_JUMP_SECONDS = 5.0


def _froggy_lotus_count(special_board) -> int:
    return sum(
        1
        for row in (special_board if special_board is not None else ())
        for value in row
        if value == SPECIAL_FROGGY_LOTUS
    )


class FroggyCheckerboardTracker:
    """Remembers, across decisions, whether an armed activation has happened."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last_lotuses = None
        self.last_time_left = None
        self.pending = False

    def observe(self, special_board, turn_state) -> bool:
        """Feed one decision's board and clock; True while the throw is due."""
        time_left = getattr(turn_state, "time_left_seconds", None)
        if time_left is None:
            self.reset()
            return False
        time_left = float(time_left)
        if (
            self.last_time_left is not None
            and time_left
            > self.last_time_left + FROGGY_CHECKERBOARD_NEW_MATCH_JUMP_SECONDS
        ):
            self.reset()
        lotuses = _froggy_lotus_count(special_board)
        if (
            time_left <= FROGGY_CHECKERBOARD_ARM_SECONDS
            and self.last_lotuses is not None
            and lotuses > self.last_lotuses
        ):
            self.pending = True
        if lotuses <= 0:
            self.pending = False
        self.last_lotuses = lotuses
        self.last_time_left = time_left
        return self.pending


_FROGGY_CHECKERBOARD_TRACKER = FroggyCheckerboardTracker()


def froggy_checkerboard_policy_applies(
    selected_perks, froggy_booster, turn_state, strategy_context
) -> bool:
    """Whether Checkerboard is being held back for the last activation.

    While this holds the ordinary perk path never sees the perk: that path
    judges a perk by the charge it banks, and would happily spend the repaint on
    filling the meter -- the opposite of keeping it for the lotuses.
    """
    if not froggy_booster or PERK_CHECKERBOARD not in tuple(selected_perks or ()):
        return False
    context = strategy_context_or_unknown(strategy_context)
    if not context.is_solo_6 or context.is_solo_challenge:
        return False
    return getattr(turn_state, "time_left_seconds", None) is not None

def _extra_move_decision_gate(evaluation):
    gate = getattr(evaluation, "decision_gate", "unknown")
    if gate != "unknown":
        return gate
    if has_guaranteed_true_extra(evaluation):
        return "true_extra_gate"
    if getattr(evaluation, "direct_extra_moves", 0) > 0:
        return "direct_extra_gate"
    return "score_gate"


def normalize_booster_action_mode(value):
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    if text in {"high voltage", "voltage", "visoki napon"}:
        return BOOSTER_ACTION_HIGH_VOLTAGE
    if text in {"magic wand", "wand", "magic", "carobni stapic", "magicni stapic"}:
        return BOOSTER_ACTION_MAGIC_WAND
    if text in {"laser beam", "laser", "laserbeam"}:
        return BOOSTER_ACTION_LASER_BEAM
    if text in {"dragon", "the dragon", "lil dragon", "lildragon"}:
        return BOOSTER_ACTION_DRAGON
    if text in {
        "woolly workout",
        "woolly",
        "wolly workout",
        "wolly",
        "willy workout",
        "willy",
    }:
        return BOOSTER_ACTION_WOOLLY_WORKOUT
    if text in {"ufo", "ufo se", "extractor", "ekstraktor", "oci", "oko"}:
        return BOOSTER_ACTION_UFO
    if text in {
        "",
        "none",
        "nista",
        "nothing",
        "off",
        "bez",
        "bez boostera",
        "bez posebne akcije",
        "plain",
        "activate",
    }:
        return BOOSTER_ACTION_NONE
    return BOOSTER_ACTION_NONE

def clear_booster_ready_latch():
    _booster_ready_latch["booster_action_mode"] = None
    _booster_ready_latch["detection"] = None
    _booster_ready_latch["miss_count"] = 0


# Where the ACTIVATE template was last actually seen, keyed by the region it
# was seen in. The word pulses: Debug/runs 2026-08-23_15-38-18..22 read it at
# 0.919 -> 0.0 -> 0.0 -> 0.963 over four consecutive frames (~1s apart) while
# memory held the meter at 7/7 throughout. A click that memory has already
# authorised therefore may not depend on the template landing on a visible
# frame -- the last seen position is where the button still is. Keying by the
# full region tuple makes the cache self-invalidating on any geometry or
# calibration change, since the region is derived from the live board anchors.
_last_booster_activate_location = {
    "region": None,
    "location": None,
    "template_size": None,
}


def _remember_booster_activate_location(detection):
    if not detection.get("active"):
        return
    location = detection.get("location")
    template_size = detection.get("template_size")
    region = detection.get("region")
    if location and template_size and region:
        _last_booster_activate_location["region"] = tuple(region)
        _last_booster_activate_location["location"] = tuple(location)
        _last_booster_activate_location["template_size"] = tuple(template_size)


# Where the booster panel's caption sits inside booster_activation_region(),
# as a fraction of that region. The panel shows "n/7" there while charging and
# the ACTIVATE word when full; the icon takes the panel's left third, so the
# caption's centre is the one point that is on the button in both states.
# Measured on the 1920x1080 fullscreen layout 2026-09-18 (board left 664, up
# 418, square 84 -> region 649,246 231x105; caption centre at 781,301).
BOOSTER_ACTIVATE_FIXED_POINT = (0.57, 0.52)


def _memory_booster_click_detection(active):
    """The booster "detection" when memory decides: no screenshot, fixed point.

    Shaped like detect_booster_activate's answer so click_booster_activate and
    the debug record need no second code path.
    """
    region = recognition.booster_activation_region()
    return {
        "active": bool(active),
        "score": 0.0,
        "template": None,
        "latched": False,
        "source": "memory",
        "raw_active": None,
        "region": tuple(region),
        "location": (
            int(region[2] * BOOSTER_ACTIVATE_FIXED_POINT[0]),
            int(region[3] * BOOSTER_ACTIVATE_FIXED_POINT[1]),
        ),
        "template_size": (0, 0),
        "location_source": "fixed_point",
    }


# The code-match refund (+1 move, see rank_mixy_code_moves) does not hold in
# every match: measured 2026-08-26, Chest Mode 02:44 lost the turn on two
# refund-only code matches (three+three kinds) while Special O'Rama kept it
# even on a plain three. Same shape as the deferral watch: promise it until
# the game demonstrably breaks it once, then stop counting it for the rest of
# the match so the ranking cannot keep preferring weak moves for a phantom
# extra.
_mixy_refund_watch = {
    "pending_moves": None,
    "promised_at": 0.0,
    "burned": False,
    "unresolved": False,
    # The dealt code at the last decision, the one a refund was promised on,
    # and the one a broken refund convicted. A convicted code is dead -- no
    # conversion and no refund come from it -- until the engine deals another
    # (see _mixy_code_dead_after_burn), which is how a code use whose
    # transient the GUI's poll missed stops being replayed as a phantom.
    "current_code": None,
    "promised_code": None,
    "dead_code": None,
}

# The engine credits the refund (and shape extras) only after the match and
# conversion animations settle: measured 2026-08-26 02:57-02:58, every read
# taken <=3 s after a code move showed the counter one short, every read
# taken >=8 s showed it restored (02:58:02 shows the +1 landing seconds after
# the move). A verdict taken inside that window is a race, not evidence.
MIXY_REFUND_VERDICT_SECONDS = 8.0


def reset_mixy_refund_watch():
    _mixy_refund_watch["pending_moves"] = None
    _mixy_refund_watch["promised_at"] = 0.0
    _mixy_refund_watch["burned"] = False
    _mixy_refund_watch["unresolved"] = False
    _mixy_refund_watch["current_code"] = None
    _mixy_refund_watch["promised_code"] = None
    _mixy_refund_watch["dead_code"] = None


def _note_mixy_current_code(mixy_meow_state):
    """Remember the dealt code this decision ranked on."""
    colors = getattr(mixy_meow_state, "code_colors", None) or ()
    _mixy_refund_watch["current_code"] = tuple(int(c) for c in colors) or None


def _note_mixy_refund_promised(remaining_moves):
    try:
        _mixy_refund_watch["pending_moves"] = int(remaining_moves)
        _mixy_refund_watch["promised_at"] = time.monotonic()
        _mixy_refund_watch["promised_code"] = _mixy_refund_watch["current_code"]
    except (TypeError, ValueError):
        _mixy_refund_watch["pending_moves"] = None
        _mixy_refund_watch["promised_code"] = None


# Gates whose extra may be swapped for the opening move of a better run of
# extras (plan_visible_extra_sequence). Special gates -- Mixy, Color Climb,
# lotus, booster and perk choices -- keep their own pick.
VISIBLE_EXTRA_PLAN_GATES = frozenset({"true_extra_gate", "same_move_extra_gate", "score_gate"})


def _mixy_code_live(mixy_code_active, mixy_meow_state) -> bool:
    """Whether a Mixy Meow code is dealt and still has uses this activation."""
    return bool(mixy_code_active and mixy_meow_state is not None
                and not mixy_meow_state.code_exhausted)


def _mixy_code_dead_after_burn(mixy_meow_state) -> bool:
    """Whether the dealt code is the one a broken refund already convicted.

    A code that promised a refund and gave none is spent in the engine's
    eyes -- the GUI's use counter simply never saw the transient -- so
    matching it again converts nothing and refunds nothing. The verdict
    holds exactly as long as `activeColors` stays that list: the engine only
    re-deals on activation or on a credited match, and either one makes the
    next code a fresh question.
    """
    dead = _mixy_refund_watch["dead_code"]
    if dead is None:
        return False
    colors = getattr(mixy_meow_state, "code_colors", None) or ()
    current = tuple(int(c) for c in colors) or None
    if current != dead:
        _mixy_refund_watch["dead_code"] = None
        return False
    return True


def _mixy_refund_burned(remaining_moves):
    """Call once per decision: True after a code refund provably failed.

    Convicts only on settled evidence: the counter exactly one below the
    promise AND the animation window long past. A counter back at (or above)
    the promise clears the case -- the refund landed, however late. A counter
    more than one below means other moves were spent meanwhile, so the
    comparison proves nothing. An early one-short read keeps the case open
    for the next decision instead of convicting a race.

    At auto-play cadence (~5 s per decision) the elapsed check alone can
    never convict: each new promise restarts the clock before the 8 s window
    closes, so a chain of broken refunds sails through unconvicted (measured
    2026-08-27 20:57:10-20:57:26: three code moves each promised a refund,
    each read one-short 5 s later, none convicted). Hence the `unresolved`
    carry-over: a second consecutive one-short reading means the earlier
    promise has had two decision cycles (>8 s of real time) to bounce the
    counter back and never did -- that chain is settled evidence.
    """
    pending = _mixy_refund_watch["pending_moves"]
    if pending is None:
        return _mixy_refund_watch["burned"]
    try:
        current = int(remaining_moves)
    except (TypeError, ValueError):
        current = None
    if current is None or current < pending - 1:
        _mixy_refund_watch["pending_moves"] = None
        _mixy_refund_watch["unresolved"] = False
        return _mixy_refund_watch["burned"]
    if current >= pending:
        _mixy_refund_watch["pending_moves"] = None
        _mixy_refund_watch["unresolved"] = False
        return _mixy_refund_watch["burned"]
    elapsed = time.monotonic() - _mixy_refund_watch["promised_at"]
    if elapsed >= MIXY_REFUND_VERDICT_SECONDS or _mixy_refund_watch["unresolved"]:
        _mixy_refund_watch["pending_moves"] = None
        _mixy_refund_watch["unresolved"] = False
        _mixy_refund_watch["burned"] = True
        # The code that broke the promise is dead until it re-deals.
        _mixy_refund_watch["dead_code"] = _mixy_refund_watch["promised_code"]
    else:
        _mixy_refund_watch["unresolved"] = True
    return _mixy_refund_watch["burned"]


def reset_mixy_deferral_watch():
    """Match change: drop the Mixy refund verdict.

    The deferral watch this was named after went unused once "Booster odmah"
    started winning over a pending code (it and its helpers were removed
    2026-09-22); the name stays because the GUI's match-change wiring calls it.
    """
    reset_mixy_refund_watch()


# The Mixy suitcase is only drawn for a few seconds at a time, but the code it
# shows stays pending until a match completes it. Without a latch the bot sees
# the code on roughly one scan in four and plays the other turns blind.
MIXY_CODE_LATCH_SECONDS = 90.0
_mixy_code_latch = {"state": None, "time": 0.0}


def clear_mixy_code_latch():
    _mixy_code_latch["state"] = None
    _mixy_code_latch["time"] = 0.0


def remember_mixy_code(state):
    _mixy_code_latch["state"] = state
    _mixy_code_latch["time"] = time.monotonic()


def latched_mixy_code():
    """The last reliably read code, while it can still be pending."""
    state = _mixy_code_latch["state"]
    if state is None:
        return None
    if time.monotonic() - _mixy_code_latch["time"] > MIXY_CODE_LATCH_SECONDS:
        clear_mixy_code_latch()
        return None
    return state


def release_mixy_code_latch_for_move(evaluation):
    """Drop the latch once a played swipe matches one of the code colors.

    Matching a code color is exactly what completes a Mixy code: the game then
    hands out a different one. Holding the old code past that point would make
    the next turns simulate a conversion that cannot happen.
    """
    state = _mixy_code_latch["state"]
    if state is None or evaluation is None:
        return False
    if not evaluation_matches_mixy_code(evaluation, state.code_colors):
        return False
    clear_mixy_code_latch()
    return True

def digit_reader_confirms_no_activate(screen_state_read):
    if not screen_state_read:
        return False
    booster_field = screen_state_read.get("booster_charge")
    if not isinstance(booster_field, dict):
        return False
    if not booster_field.get("accepted"):
        return False
    if booster_field.get("source") != "auto_booster_text":
        return False
    # A full "X/X" frame can flash right before the button flips to ACTIVATE;
    # only a genuinely partial fraction proves the booster is not ready.
    value = booster_field.get("value")
    maximum = booster_field.get("maximum", BOOSTER_MAX_CHARGE)
    if not isinstance(maximum, (int, float)) or maximum <= 0:
        maximum = BOOSTER_MAX_CHARGE
    if isinstance(value, (int, float)) and value >= maximum:
        return False
    return True

def memory_reader_booster_ready(screen_state_read):
    """The engine's own booster-ready flag, or None when memory has no answer.

    Memory outranks every screen heuristic here: `resolved.booster_ready` comes
    from the game's own state, while the ACTIVATE template, the digit reader and
    the meter reader all exist because the screen path has nothing better. On
    2026-08-17 03:51:30 the template scored 0.70 on a genuinely ready booster,
    the run played a move with no extra move instead of activating, and memory
    had the meter at 7/7 the whole time.
    """
    if not isinstance(screen_state_read, dict):
        return None
    resolved = screen_state_read.get("resolved")
    if not isinstance(resolved, dict):
        return None
    sources = resolved.get("sources")
    if not isinstance(sources, dict) or sources.get("booster_ready") != "memory":
        return None
    ready = resolved.get("booster_ready")
    return None if ready is None else bool(ready)


def meter_reader_confirms_partial_charge(screen_state_read):
    if not screen_state_read:
        return False
    booster_field = screen_state_read.get("booster_charge")
    if not isinstance(booster_field, dict):
        return False
    if not booster_field.get("accepted"):
        return False
    if booster_field.get("source") != "auto_meter":
        return False
    value = booster_field.get("value")
    return isinstance(value, (int, float)) and value <= BOOSTER_METER_VETO_MAX_CHARGE

def _booster_detection_is_strong(detection):
    # Template word matches (full/lower word) are specific enough to trust on a
    # single frame; only the text-band whiteness heuristic needs confirmation.
    if not detection.get("active"):
        return False
    return detection.get("match_type") != "text_band"

def apply_booster_ready_latch(detection, booster_action_mode):
    current = dict(detection or {"active": False, "score": 0.0})
    normalized_mode = normalize_booster_action_mode(booster_action_mode)
    latched_mode = _booster_ready_latch["booster_action_mode"]
    if latched_mode is not None and latched_mode != normalized_mode:
        clear_booster_ready_latch()

    if current.get("active"):
        current["latched"] = False
        _booster_ready_latch["booster_action_mode"] = normalized_mode
        _booster_ready_latch["detection"] = dict(current)
        _booster_ready_latch["miss_count"] = 0
        return current

    latched_detection = _booster_ready_latch["detection"]
    if latched_detection is not None:
        _booster_ready_latch["miss_count"] += 1
        if _booster_ready_latch["miss_count"] > BOOSTER_LATCH_MAX_CONSECUTIVE_MISSES:
            clear_booster_ready_latch()
            current["latched"] = False
            current["latch_expired"] = True
            return current
        result = dict(latched_detection)
        result["active"] = True
        result["latched"] = True
        result["raw_active"] = bool(current.get("active", False))
        result["raw_score"] = current.get("score", 0.0)
        return result

    current["latched"] = False
    return current

def select_extra_move_action(ranked_moves):
    # Spend the earned extra only on a move that passes the centralized
    # same-swipe reliability predicate. Direct match-4+/square and deterministic
    # natural cascades qualify; random-refill and unstable-special predictions do
    # not. The one sanctioned exception is the UFO fallback the ranking itself
    # produced (rank_extra_move_moves): an extra predicted behind an unambiguous
    # abduction, marked with its own gate. If nothing qualifies, do nothing and
    # report it.
    for evaluation in ranked_moves:
        if (
            is_extra_move_evaluation(evaluation)
            or getattr(evaluation, "decision_gate", None) == UFO_PREDICTED_EXTRA_GATE
        ):
            return "move", evaluation
    return "none", None


# ε-greedy exploration: with probability ε, play a non-greedy move from the top-k
# of the ranked list instead of the argmax. This turns the otherwise observational
# logs into off-policy data (we see outcomes of moves the greedy policy skipped),
# and is the data-generating half of the strategy search. Configured via env so a
# session can toggle it without code/GUI changes; keep ε=0 during CEM fitness
# evaluation (we want each weight-set's true greedy performance).
_EXPLORE_RNG = random.Random()


def _explore_epsilon():
    try:
        return max(0.0, min(1.0, float(os.environ.get("MM_EXPLORE_EPSILON", "0"))))
    except (TypeError, ValueError):
        return 0.0


def _explore_topk():
    try:
        return max(2, int(os.environ.get("MM_EXPLORE_TOPK", "3")))
    except (TypeError, ValueError):
        return 3


def maybe_explore_move(best_evaluation, selection_candidates, *, epsilon=None, top_k=None, rng=None):
    """Possibly swap the greedy move for a random top-k alternative.

    Only fires on a pure greedy pick (``best_evaluation`` is the #0 ranked move),
    so deliberate overrides (forced-extra, froggy, mixy, perks) are never
    randomized. Returns ``(evaluation_to_play, info)`` where ``info`` records the
    epsilon, whether we explored, the chosen rank and the selection propensity
    (for off-policy / inverse-propensity learning).
    """
    eps = _explore_epsilon() if epsilon is None else max(0.0, min(1.0, float(epsilon)))
    info = {"epsilon": eps, "explored": False, "chosen_rank": 0, "propensity": 1.0}
    if eps <= 0 or best_evaluation is None or not selection_candidates:
        return best_evaluation, info
    if selection_candidates[0] is not best_evaluation:
        return best_evaluation, info  # not a pure greedy pick; leave it
    k = _explore_topk() if top_k is None else max(2, int(top_k))
    pool = selection_candidates[:k]
    if len(pool) < 2:
        return best_evaluation, info
    info["pool_size"] = len(pool)
    chooser = rng or _EXPLORE_RNG
    if chooser.random() < eps:
        rank = chooser.randrange(1, len(pool))  # never re-pick the greedy #0
        info["explored"] = True
        info["chosen_rank"] = rank
        info["propensity"] = eps / (len(pool) - 1)
        return pool[rank], info
    info["propensity"] = 1.0 - eps
    return best_evaluation, info

def click_booster_activate(
    detection,
    return_position=None,
    return_delay=None,
    restore_cursor=True,
):
    if return_delay is None:
        return_delay = CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS
    if return_position is None:
        return_position = pyautogui.position()

    region = detection.get("region") or recognition.booster_activation_region()
    location = detection.get("location")
    template_size = detection.get("template_size")
    if location and template_size:
        x = region[0] + location[0] + template_size[0] // 2
        y = region[1] + location[1] + template_size[1] // 2
    else:
        x = region[0] + region[2] // 2
        y = region[1] + region[3] // 2
    game_click(x, y)
    time.sleep(return_delay)
    if restore_cursor:
        pyautogui.moveTo(return_position[0], return_position[1])


def revalidate_booster_activation_before_click(screen_state_read=None):
    """Pre-click gate: memory decides when it can, the template otherwise.

    Selection and perk/strategy ranking happen after the first screenshot, so
    this runs on the frame immediately before input. When memory answers
    (`resolved.booster_ready` sourced "memory") it is the engine's own flag and
    the template has no veto: Debug/runs 2026-08-23_15-38-18..22 show the
    pulsing ACTIVATE word scoring 0.919 -> 0.0 -> 0.0 -> 0.963 across four
    consecutive decisions while memory held 7/7 + booster_ready the whole
    time, and the old template requirement here burned three "Booster: nije
    spreman" cycles (~5s) before the flicker happened to line up. The template
    is still asked once -- but only for precise click coordinates, never for
    permission; when it misses, the last seen location (or the search-window
    centre) supplies them.

    Without a memory answer the original screen-only contract holds: no fresh
    raw template hit on this exact frame, no click, and never a stale latch.
    """
    memory_ready = memory_reader_booster_ready(screen_state_read)
    if memory_ready is False:
        clear_booster_ready_latch()
        return None
    if memory_ready:
        # Memory path: no frame is grabbed at all. The click goes to the fixed
        # caption point of the booster panel (BOOSTER_ACTIVATE_FIXED_POINT).
        clear_booster_ready_latch()
        return _memory_booster_click_detection(True)

    # Screen path (no memory answer): the original contract.
    fresh = detect_booster_activate(None)
    _remember_booster_activate_location(fresh)
    if not fresh.get("active"):
        clear_booster_ready_latch()
        return None
    confirmed = dict(fresh)
    confirmed["latched"] = False
    return confirmed

def activate_high_voltage_booster(
    detection,
    target_cell,
    return_position=None,
    prompt_delay=HIGH_VOLTAGE_PROMPT_DELAY_SECONDS,
    return_delay=None,
):
    if return_delay is None:
        return_delay = CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS
    if return_position is None:
        return_position = pyautogui.position()

    click_booster_activate(
        detection,
        return_position=return_position,
        return_delay=prompt_delay,
        restore_cursor=False,
    )
    target_x, target_y = board_cell_center(target_cell)
    game_click(target_x, target_y)
    time.sleep(return_delay)
    pyautogui.moveTo(return_position[0], return_position[1])


def activate_magic_wand_booster(
    detection,
    target_cell,
    return_position=None,
    prompt_delay=HIGH_VOLTAGE_PROMPT_DELAY_SECONDS,
    return_delay=None,
):
    activate_high_voltage_booster(
        detection,
        target_cell,
        return_position=return_position,
        prompt_delay=prompt_delay,
        return_delay=return_delay,
    )


def activate_laser_beam_booster(
    detection,
    target_cell,
    return_position=None,
    prompt_delay=HIGH_VOLTAGE_PROMPT_DELAY_SECONDS,
    return_delay=None,
):
    activate_high_voltage_booster(
        detection,
        target_cell,
        return_position=return_position,
        prompt_delay=prompt_delay,
        return_delay=return_delay,
    )


def activate_woolly_workout_booster(
    detection,
    target_cell,
    return_position=None,
    prompt_delay=HIGH_VOLTAGE_PROMPT_DELAY_SECONDS,
    return_delay=None,
):
    activate_high_voltage_booster(
        detection,
        target_cell,
        return_position=return_position,
        prompt_delay=prompt_delay,
        return_delay=return_delay,
    )


def initialize_runtime():
    global runtime_initialized, win

    if runtime_initialized:
        return

    try:
        win = find_bluestacks_window()
    except RuntimeError:
        exit(1)
    # SW_RESTORE also un-maximizes some BlueStacks builds.  Only restore a truly
    # minimized player; otherwise preserve the user's fullscreen/window layout.
    if bool(getattr(win, "isMinimized", False)):
        win.restore()

    if not Path(__file__).resolve().with_name("board_config.json").exists():
        exit(1)

    # The GUI exposes ML-only as the single supported recognition mode.  Set it
    # before applying the profile so startup never loads legacy board templates.
    recognition.set_ml_recognition_mode(ML_RECOGNITION_ONLY)
    recognition.apply_board_profile(
        DEFAULT_PROFILE,
        allow_uncalibrated_layout=True,
    )

    runtime_initialized = True

def get_active_runs_dir():
    """Folder new per-move debug runs are written into (a game folder or root)."""
    return _active_runs_dir


def set_active_runs_dir(path):
    global _active_runs_dir
    _active_runs_dir = os.fspath(path)
    return _active_runs_dir


def _slugify_game_label(label):
    if not label:
        return ""
    # Keep folder names filesystem-safe: letters/digits/dash/underscore only.
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(label).strip())
    return cleaned.strip("_")[:40]


def start_new_game_dir(base_dir=DEBUG_RUNS_DIR, label=None):
    """Create a fresh per-game folder and route later debug runs into it.

    Lets the user mark a game boundary explicitly ("Nova partija") so calibration
    never pairs the last move of one game with the first of the next. Returns the
    new folder path; drops a ``game.json`` marker with the start time and label.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    slug = _slugify_game_label(label)
    name = f"game_{timestamp}" + (f"_{slug}" if slug else "")
    base_path = Path(base_dir)
    game_path = base_path / name
    suffix = 1
    while game_path.exists():
        game_path = base_path / f"{name}_{suffix}"
        suffix += 1
    game_path.mkdir(parents=True, exist_ok=False)
    marker = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "label": label or "",
    }
    (game_path / "game.json").write_text(json.dumps(marker, indent=2), encoding="utf-8")
    set_active_runs_dir(game_path)
    reset_runtime_score_tracking()
    # A move from the last match must not be closed with this one's meters: the
    # score restarts, and the delta would be a large negative that every reader
    # then has to recognise and throw away.
    move_telemetry.reset()
    return game_path


# The last two run dirs this process created, so find_previous_debug_run can
# link consecutive moves without re-listing the whole runs folder (853+ dirs =
# ~150ms per move on Windows). Single-threaded runtime, so globals are safe.
_last_created_debug_run_dir = None
_previous_created_debug_run_dir = None
# The slow path of find_previous_debug_run looks at this many of the newest
# run folders, and never links a move older than this to the current one.
PREVIOUS_RUN_SCAN_LIMIT = 50
PREVIOUS_RUN_MAX_AGE_SECONDS = 600.0


def _debug_json_default(value):
    """json default for debug records: numpy scalars/arrays, then plain text.

    numpy 2's ``numpy.bool`` is reported as "bool" and json refuses it; a
    perk record holding one aborted the move after the perk was spent
    (Color Crystals Versus, 2026-11-10 02:23:15).
    """
    item = getattr(value, "item", None)
    if callable(item) and getattr(value, "shape", None) == ():
        return item()
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _safe_debug_write(writer, *args, **kwargs):
    """Run a debug writer without letting it cost the move.

    The memory GUI always records, and these writes sit between the decision
    and the swipe: one value json cannot serialise (a numpy scalar, a new
    evaluation field) aborted the move while the turn clock kept running. The
    record is lost instead, with its traceback on the console.
    """
    try:
        return writer(*args, **kwargs)
    except Exception:
        import traceback

        print(f"[debug] {getattr(writer, '__name__', writer)} nije upisan:", flush=True)
        traceback.print_exc()
        return None


def create_debug_run_dir(base_dir=None):
    global _last_created_debug_run_dir, _previous_created_debug_run_dir
    base_path = Path(base_dir if base_dir is not None else get_active_runs_dir())
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
    run_path = base_path / timestamp
    suffix = 1
    while run_path.exists():
        run_path = base_path / f"{timestamp}_{suffix}"
        suffix += 1
    run_path.mkdir(parents=True, exist_ok=False)
    _previous_created_debug_run_dir = _last_created_debug_run_dir
    _last_created_debug_run_dir = run_path
    return run_path

def last_created_debug_run_dir():
    """The run folder this process created most recently, or None."""
    return _last_created_debug_run_dir


def score_region_from_board():
    board_width = max(1, recognition.width)
    region_x = int(round(recognition.left + board_width * SCORE_REGION_X_OFFSET_RATIO))
    region_y = int(round(recognition.up - board_width * SCORE_REGION_Y_ABOVE_BOARD_RATIO))
    region_width = max(1, int(round(board_width * SCORE_REGION_WIDTH_RATIO)))
    region_height = max(1, int(round(board_width * SCORE_REGION_HEIGHT_RATIO)))
    return max(0, region_x), max(0, region_y), region_width, region_height

def capture_score_region(output_path, region=None):
    output_path = Path(output_path)
    capture_region = region or score_region_from_board()
    capture_debug_screenshot(output_path, region=capture_region)
    return output_path

def find_previous_debug_run(current_run_dir, base_dir=None):
    # Default to the current run's own folder so previous-move linkage stays
    # scoped to the active game -- the first move of a new game folder then has
    # no predecessor and starts a clean observed-delta chain.
    base_path = Path(base_dir) if base_dir is not None else Path(current_run_dir).parent
    if not base_path.exists():
        return None
    current_path = Path(current_run_dir).resolve()
    # Fast path: the run created immediately before this one is the previous
    # move whenever it lives in the same game folder, recorded a move and was
    # not already closed by a terminal observation — the exact conditions the
    # full scan below checks. Anything off (new game folder, restart, closed
    # run) falls through to the scan, so behaviour is unchanged, only cheaper.
    cached = _previous_created_debug_run_dir
    if (
        _last_created_debug_run_dir is not None
        and Path(_last_created_debug_run_dir).resolve() == current_path
        and cached is not None
        and cached.parent == Path(current_run_dir).parent
        and (cached / "move.json").exists()
        and not (cached / OBSERVED_DELTA_FILENAME).exists()
    ):
        return cached
    # Run folders are named by their creation time, so only the newest few
    # names can hold the previous move. Stat-ing every folder cost seconds once
    # Debug/runs passed 3,000 of them, and on the first move after a launch
    # it happily linked a run from an earlier session (or day) as "previous".
    try:
        names = sorted(os.listdir(base_path), reverse=True)[:PREVIOUS_RUN_SCAN_LIMIT]
    except OSError:
        return None
    oldest_allowed = time.time() - PREVIOUS_RUN_MAX_AGE_SECONDS
    candidates = []
    for name in names:
        run_path = base_path / name
        if not run_path.is_dir():
            continue
        if run_path.resolve() == current_path:
            continue
        if not (run_path / "move.json").exists():
            continue
        # A terminal post-action capture can close the final move without
        # creating a following run. Do not close that same move again when an
        # unexpected extra produces another scan.
        if (run_path / OBSERVED_DELTA_FILENAME).exists():
            continue
        try:
            if run_path.stat().st_mtime < oldest_allowed:
                continue
        except OSError:
            continue
        candidates.append(run_path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))

def _grid_changes(before_grid, after_grid):
    changes = []
    row_count = max(len(before_grid or []), len(after_grid or []))
    for row in range(row_count):
        before_row = before_grid[row] if row < len(before_grid or []) else []
        after_row = after_grid[row] if row < len(after_grid or []) else []
        col_count = max(len(before_row), len(after_row))
        for col in range(col_count):
            before_value = before_row[col] if col < len(before_row) else None
            after_value = after_row[col] if col < len(after_row) else None
            if before_value == after_value:
                continue
            changes.append({
                "cell": [row, col],
                "before": before_value,
                "after": after_value,
            })
    return changes

def _compact_json(value):
    if value in (None, ""):
        return ""
    return json.dumps(value, separators=(",", ":"))

def _append_audit_log(row, audit_log_path=DEBUG_AUDIT_LOG):
    audit_path = Path(audit_log_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not audit_path.exists()
    with audit_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_LOG_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in AUDIT_LOG_FIELDS})


def _score_read_payload_from_path(path):
    try:
        with Image.open(path) as image:
            score_read = screen_state_reader.read_score_region(image)
    except Exception as exc:
        return {
            "our_score": None,
            "opponent_score": None,
            "score_deficit": None,
            "confidence": 0.0,
            "accepted": False,
            "source": "read_error",
            "reason": type(exc).__name__,
        }
    return score_read.to_debug_payload()

def write_observed_delta_report(
    previous_run_dir,
    after_run_dir,
    after_board_path,
    after_score_region_path,
    after_board,
    after_special_board,
    after_score_region=None,
    audit_log_path=DEBUG_AUDIT_LOG,
):
    previous_path = Path(previous_run_dir)
    after_path = Path(after_run_dir)
    previous_move_path = previous_path / "move.json"
    if not previous_move_path.exists():
        return None

    # Debug history may be truncated by an interrupted write or shutdown.
    # Missing audit data must never prevent the next game action.
    try:
        previous_move = json.loads(previous_move_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(previous_move, dict):
        return None
    before_board = previous_move.get("board") or []
    before_special_board = previous_move.get("special_board") or []
    board_changes = _grid_changes(before_board, after_board)
    special_changes = _grid_changes(before_special_board, after_special_board)

    after_board_copy = previous_path / AFTER_BOARD_FILENAME
    after_score_copy = previous_path / AFTER_SCORE_REGION_FILENAME
    # A memory-sourced score comes from PlayerModel.score, so the score crop is
    # never captured and there is nothing to copy; the score delta then simply
    # reports itself as unreadable instead of crashing the whole move.
    if after_board_path is not None:
        shutil.copy2(after_board_path, after_board_copy)
    if after_score_region_path is not None:
        shutil.copy2(after_score_region_path, after_score_copy)

    after_score_payload = (
        {"path": AFTER_SCORE_REGION_FILENAME}
        if after_score_region_path is not None
        else {"path": None}
    )
    if after_score_region is not None:
        after_score_payload["region"] = list(after_score_region)

    best_move = previous_move.get("best_move") or {}
    high_voltage_target = previous_move.get("high_voltage_target") or {}
    magic_wand_target = previous_move.get("magic_wand_target") or {}
    laser_beam_target = previous_move.get("laser_beam_target") or {}
    woolly_workout_target = previous_move.get("woolly_workout_target") or {}
    dragon_move = previous_move.get("dragon_move") or {}
    booster_detection = previous_move.get("booster_detection") or {}
    predicted_score = best_move.get(
        "score",
        high_voltage_target.get(
            "score",
            magic_wand_target.get(
                "score",
                laser_beam_target.get(
                    "score",
                    woolly_workout_target.get("score", dragon_move.get("score", "")),
                ),
            ),
        ),
    )
    predicted_reason = (
        best_move.get("reason")
        or high_voltage_target.get("explanation")
        or magic_wand_target.get("explanation")
        or laser_beam_target.get("explanation")
        or woolly_workout_target.get("explanation")
        or dragon_move.get("explanation", "")
    )
    before_score_read = _score_read_payload_from_path(
        previous_path / SCORE_REGION_FILENAME
    )
    after_score_read = _score_read_payload_from_path(after_score_region_path)
    score_readable = bool(
        before_score_read.get("accepted") and after_score_read.get("accepted")
    )
    our_points_gained = None
    opponent_points_gained = None
    if score_readable:
        our_points_gained = (
            int(after_score_read["our_score"])
            - int(before_score_read["our_score"])
        )
        opponent_points_gained = (
            int(after_score_read["opponent_score"])
            - int(before_score_read["opponent_score"])
        )
    score_confirmed = bool(
        score_readable
        and our_points_gained is not None
        and our_points_gained >= 0
        and opponent_points_gained == 0
    )
    score_delta = {
        "confirmed": score_confirmed,
        "readable": score_readable,
        "before": before_score_read,
        "after": after_score_read,
        "our_points_gained": our_points_gained,
        "opponent_points_gained": opponent_points_gained,
    }
    calibration_sample = None
    if score_confirmed and previous_move.get("selected_action") == "move":
        calibration_sample = {
            "score_before": before_score_read.get("our_score"),
            "score_after": after_score_read.get("our_score"),
            "actual_points": our_points_gained,
            "predicted_utility_score": predicted_score,
            "cleared_cells": best_move.get("cleared_cells"),
            "activated_specials": best_move.get("activated_specials"),
            "cascade_count": best_move.get("cascade_count"),
            "blue_cells": best_move.get("blue_cells"),
            "booster_active": bool(booster_detection.get("active", False)),
            "active_booster": previous_move.get("active_booster", "default"),
        }

    payload = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "previous_run": previous_path.name,
        "after_run": after_path.name,
        "previous_move": {
            "action": previous_move.get("action"),
            "mode": previous_move.get("mode"),
            "profile": previous_move.get("profile"),
            "selected_action": previous_move.get("selected_action"),
            "allow_square_matches": previous_move.get("allow_square_matches"),
            "specials_explode_immediately": previous_move.get("specials_explode_immediately"),
            "color_crush": previous_move.get("color_crush"),
            "energized_colors": previous_move.get("energized_colors"),
            "vertical_matches_destroy_color": previous_move.get("vertical_matches_destroy_color"),
            "matches_destroy_color": previous_move.get("matches_destroy_color"),
            "include_future_value": previous_move.get("include_future_value"),
            "score_rally_values": previous_move.get("score_rally_values"),
            "special_piece_mode": previous_move.get("special_piece_mode"),
            "selected_perks": previous_move.get("selected_perks"),
            "booster_detection": booster_detection or None,
            "best_move": best_move or None,
            "high_voltage_target": high_voltage_target or None,
            "magic_wand_target": magic_wand_target or None,
            "laser_beam_target": laser_beam_target or None,
            "woolly_workout_target": woolly_workout_target or None,
            "dragon_move": dragon_move or None,
        },
        "score_regions": {
            "before": previous_move.get("score_region"),
            "after": after_score_payload,
        },
        "score_delta": score_delta,
        "calibration_sample": calibration_sample,
        "board_before": before_board,
        "board_after": after_board,
        "special_board_before": before_special_board,
        "special_board_after": after_special_board,
        "board_delta": {
            "changed_count": len(board_changes),
            "changed_cells": board_changes,
        },
        "special_delta": {
            "changed_count": len(special_changes),
            "changed_cells": special_changes,
        },
        "manual_note": "",
    }

    delta_path = previous_path / OBSERVED_DELTA_FILENAME
    delta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _append_audit_log(
        {
            "closed_at": payload["created_at"],
            "previous_run": previous_path.name,
            "after_run": after_path.name,
            "action": previous_move.get("action"),
            "mode": previous_move.get("mode"),
            "profile": previous_move.get("profile"),
            "selected_action": previous_move.get("selected_action"),
            "allow_square_matches": previous_move.get("allow_square_matches"),
            "specials_explode_immediately": previous_move.get("specials_explode_immediately"),
            "color_crush": previous_move.get("color_crush"),
            "energized_colors": _compact_json(previous_move.get("energized_colors")),
            "vertical_matches_destroy_color": previous_move.get("vertical_matches_destroy_color"),
            "matches_destroy_color": previous_move.get("matches_destroy_color"),
            "include_future_value": previous_move.get("include_future_value"),
            "score_rally_values": _compact_json(previous_move.get("score_rally_values")),
            "special_piece_mode": previous_move.get("special_piece_mode", ""),
            "selected_perks": _compact_json(previous_move.get("selected_perks")),
            "booster_active": booster_detection.get("active", ""),
            "booster_score": booster_detection.get("score", ""),
            "move_start": _compact_json(best_move.get("start")),
            "move_target": _compact_json(best_move.get("target")),
            "move_direction": best_move.get("direction", ""),
            "predicted_score": predicted_score,
            "predicted_reason": predicted_reason,
            "high_voltage_target_cell": _compact_json(high_voltage_target.get("target_cell")),
            "high_voltage_target_color": high_voltage_target.get("target_color", ""),
            "high_voltage_expected_cleared": high_voltage_target.get("cleared_cells", ""),
            "high_voltage_expected_blue": high_voltage_target.get("blue_cells", ""),
            "high_voltage_expected_extra_moves": high_voltage_target.get("extra_moves", ""),
            "high_voltage_expected_activated_specials": high_voltage_target.get("activated_specials", ""),
            "high_voltage_explanation": high_voltage_target.get("explanation", ""),
            "magic_wand_target_cell": _compact_json(magic_wand_target.get("target_cell")),
            "magic_wand_target_color": magic_wand_target.get("target_color", ""),
            "magic_wand_expected_cleared": magic_wand_target.get("cleared_cells", ""),
            "magic_wand_expected_blue": magic_wand_target.get("blue_cells", ""),
            "magic_wand_expected_extra_moves": magic_wand_target.get("extra_moves", ""),
            "magic_wand_expected_activated_specials": magic_wand_target.get("activated_specials", ""),
            "magic_wand_explanation": magic_wand_target.get("explanation", ""),
            "laser_beam_target_cell": _compact_json(laser_beam_target.get("target_cell")),
            "laser_beam_target_color": laser_beam_target.get("target_color", ""),
            "laser_beam_expected_cleared": laser_beam_target.get("cleared_cells", ""),
            "laser_beam_expected_blue": laser_beam_target.get("blue_cells", ""),
            "laser_beam_expected_extra_moves": laser_beam_target.get("extra_moves", ""),
            "laser_beam_expected_activated_specials": laser_beam_target.get("activated_specials", ""),
            "laser_beam_explanation": laser_beam_target.get("explanation", ""),
            "dragon_move_start": _compact_json(dragon_move.get("start")),
            "dragon_move_target": _compact_json(dragon_move.get("target")),
            "dragon_move_direction": dragon_move.get("direction", ""),
            "dragon_expected_cleared": dragon_move.get("cleared_cells", ""),
            "dragon_expected_blue": dragon_move.get("blue_cells", ""),
            "dragon_expected_extra_moves": dragon_move.get("extra_moves", ""),
            "dragon_expected_activated_specials": dragon_move.get("activated_specials", ""),
            "dragon_explanation": dragon_move.get("explanation", ""),
            "board_changed_cells": len(board_changes),
            "special_changed_cells": len(special_changes),
            "before_score_region": SCORE_REGION_FILENAME if previous_move.get("score_region") else "",
            "after_score_region": AFTER_SCORE_REGION_FILENAME,
            "manual_note": "",
        },
        audit_log_path=audit_log_path,
    )
    return delta_path


def capture_final_debug_observation(
    debug_run_dir,
    *,
    score_region=None,
    max_attempts=FINAL_OBSERVATION_MAX_ATTEMPTS,
    delay_seconds=FINAL_OBSERVATION_DELAY_SECONDS,
    score_motion_threshold=FINAL_OBSERVATION_SCORE_MOTION_THRESHOLD,
    audit_log_path=DEBUG_AUDIT_LOG,
):
    """Close a likely terminal move even when no next auto scan will exist.

    Two matching recognized boards plus a settled score crop confirm the
    post-action state. If the match-end screen replaces the board, the last
    frame/score are still kept in ``final_observation.json`` instead of silently
    losing the final outcome.
    """
    run_path = Path(debug_run_dir)
    board_path = run_path / TERMINAL_BOARD_FILENAME
    score_path = run_path / TERMINAL_SCORE_REGION_FILENAME
    previous_signature = None
    previous_score_image = None
    last_board = None
    last_special_board = None
    board_valid = False
    settled = False
    score_motion = None
    attempts = 0

    for attempt in range(max(1, int(max_attempts))):
        if delay_seconds > 0:
            time.sleep(delay_seconds)
        attempts = attempt + 1
        board = create_board()
        special_board = create_board()
        diag = {}
        board, special_board = update_board_2(
            board,
            special_board,
            screenshot_path=board_path,
            write_screenshot=True,
            _diag=diag,
        )
        capture_score_region(score_path, score_region)
        flush_debug_screenshot_writes(board_path)
        flush_debug_screenshot_writes(score_path)

        current_score_image = None
        try:
            with Image.open(score_path) as image:
                current_score_image = image.convert("RGB").copy()
        except (FileNotFoundError, OSError):
            current_score_image = None
        score_motion = (
            auto_motion_score(previous_score_image, current_score_image)
            if previous_score_image is not None and current_score_image is not None
            else None
        )
        signature = auto_board_signature(board, special_board)
        board_valid = board_scan_block_reason(board) is None
        last_board = _copy_grid(board)
        last_special_board = _copy_grid(special_board)
        settled = bool(
            board_valid
            and previous_signature == signature
            and score_motion is not None
            and score_motion <= score_motion_threshold
        )
        previous_signature = signature if board_valid else None
        previous_score_image = current_score_image
        if settled:
            break

    observed_delta_path = None
    if board_valid and last_board is not None and last_special_board is not None:
        observed_delta_path = write_observed_delta_report(
            run_path,
            run_path / "terminal_observation",
            board_path,
            score_path,
            last_board,
            last_special_board,
            after_score_region=score_region,
            audit_log_path=audit_log_path,
        )

    payload = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "settled": settled,
        "board_valid": board_valid,
        "attempts": attempts,
        "score_motion": None if score_motion is None else round(score_motion, 3),
        "score_motion_threshold": float(score_motion_threshold),
        "terminal_board": TERMINAL_BOARD_FILENAME if board_path.exists() else None,
        "terminal_score_region": (
            TERMINAL_SCORE_REGION_FILENAME if score_path.exists() else None
        ),
        "observed_delta": (
            observed_delta_path.name if observed_delta_path is not None else None
        ),
    }
    (run_path / FINAL_OBSERVATION_FILENAME).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def _should_capture_final_debug_observation(
    debug_enabled,
    debug_run_dir,
    turn_state,
    best_evaluation,
):
    return bool(
        debug_enabled
        and debug_run_dir is not None
        and best_evaluation is not None
        and turn_state is not None
        and getattr(turn_state, "is_final_round", False)
        and turn_state.remaining_moves is not None
        and turn_state.remaining_moves <= 1
        and not has_guaranteed_true_extra(best_evaluation)
    )

def debug_cell_label(color, special):
    color_label = COLOR_DEBUG_LABELS.get(color, str(color) if color else "empty")
    if special == 0:
        return color_label
    if special in {SPECIAL_CLEO_BUG, SPECIAL_SWEEP_SE_BROOM}:
        return SPECIAL_DEBUG_LABELS[special]
    if is_vinnie_se_heart_special(special):
        first_color, second_color = vinnie_se_heart_colors(special)
        special_label = (
            "vinnie-se-"
            f"{COLOR_DEBUG_LABELS.get(first_color, first_color)}-"
            f"{COLOR_DEBUG_LABELS.get(second_color, second_color)}"
        )
    elif is_purple_gem_special(special):
        special_label = f"purple-gem-{purple_gem_value(special)}"
    else:
        special_label = SPECIAL_DEBUG_LABELS.get(special, f"special-{special}")
    return f"{color_label}/{special_label}"

def summarize_move_intent(evaluation):
    if evaluation is None:
        return None
    events = list(getattr(evaluation, "intent_events", []) or [])
    return {
        "event_count": len(events),
        "cleared_cells": float(getattr(evaluation, "cleared_cells", 0.0)),
        "blue_cells": float(getattr(evaluation, "blue_cells", 0.0)),
        "activated_specials": float(getattr(evaluation, "activated_specials", 0.0)),
        "cascade_count": float(getattr(evaluation, "cascade_count", 0.0)),
        "has_chain": any(
            event.get("type") == "special_effect" and event.get("activated_specials")
            for event in events
        ),
        "has_uncertain_boundary": any(
            event.get("type") == "uncertain_refill_boundary"
            for event in events
        ),
    }

def serialize_move_evaluation(evaluation):
    if evaluation is None:
        return None
    # The orientation the move would actually be swiped with, so Debug shows the
    # tile that gets dragged rather than the candidate generator's fixed end.
    candidate = oriented_swap_candidate(evaluation)
    payload = {
        "start": list(candidate.start),
        "target": list(candidate.target),
        "direction": candidate.direction.value,
        "score": evaluation.score,
        "instant_score": evaluation.instant_score,
        "exact_refill": getattr(evaluation, "exact_refill", False),
        "approximate_refill": getattr(evaluation, "approximate_refill", False),
        "special_bonus": evaluation.special_bonus,
        "created_special_value": getattr(evaluation, "created_special_value", 0.0),
        "created_special_values": list(
            getattr(evaluation, "created_special_values", []) or []
        ),
        "blue_bonus": evaluation.blue_bonus,
        "mode_bonus": evaluation.mode_bonus,
        "multiplier_madness_points": evaluation.multiplier_madness_points,
        "multiplier_madness_setup_bonus": evaluation.multiplier_madness_setup_bonus,
        "floor_lava_destroyed_columns": [
            col + 1 for col in evaluation.floor_lava_destroyed_columns
        ],
        "floor_lava_checked_columns_after": [
            col + 1 for col in evaluation.floor_lava_checked_columns_after
        ],
        "extra_move_bonus": evaluation.extra_move_bonus,
        "disco_move_bonus": evaluation.disco_move_bonus,
        "blue_cells": evaluation.blue_cells,
        "solo_blue_plan_charge": getattr(evaluation, "solo_blue_plan_charge", None),
        "intent_events": list(getattr(evaluation, "intent_events", []) or []),
        "intent_summary": summarize_move_intent(evaluation),
        "cleared_cells": evaluation.cleared_cells,
        "activated_specials": evaluation.activated_specials,
        "predictable_special_activated": evaluation.predictable_special_activated,
        "extra_moves": evaluation.extra_moves,
        "direct_extra_moves": evaluation.direct_extra_moves,
        "ufo_predicted_extra_moves": getattr(
            evaluation, "ufo_predicted_extra_moves", 0.0
        ),
        "disco_moves": evaluation.disco_moves,
        "cascade_count": evaluation.cascade_count,
        "mode_targets": evaluation.mode_targets,
        "chest_drops": evaluation.chest_drops,
        "multiplier_mushrooms": evaluation.multiplier_mushrooms,
        "board_potential": evaluation.board_potential,
        "lookahead_bonus": evaluation.lookahead_bonus,
        "extra_chain_bonus": evaluation.extra_chain_bonus,
        "extra_setup_bonus": evaluation.extra_setup_bonus,
        "verified_extra_setup_bonus": evaluation.verified_extra_setup_bonus,
        "cleared_color_counts": {
            int(color): float(count)
            for color, count in evaluation.cleared_color_counts.items()
        },
        "booster_fill_bonus": getattr(evaluation, "booster_fill_bonus", 0.0),
        "blue_waste_penalty": getattr(evaluation, "blue_waste_penalty", 0.0),
        "phase": getattr(evaluation, "phase", "unknown"),
        "phase_adjusted_mode_bonus": getattr(
            evaluation,
            "phase_adjusted_mode_bonus",
            evaluation.mode_bonus,
        ),
        "score_strategy": getattr(evaluation, "score_strategy", "normal"),
        "score_strategy_adjustment": getattr(
            evaluation,
            "score_strategy_adjustment",
            0.0,
        ),
        "mixy_code_color": getattr(evaluation, "mixy_code_color", None),
        "mixy_code_bonus": getattr(evaluation, "mixy_code_bonus", 0.0),
        "mixy_converted_tiles": getattr(evaluation, "mixy_converted_tiles", 0),
        # The jelly repaint's priced remainder: tiles that survive this move's
        # own cascades (the consumed ones are ordinary cleared cells). Written
        # so a jelly audit can check the pricing instead of falling back to
        # intent events, like the lotus fields below.
        "jelly_converted_tiles": getattr(evaluation, "jelly_converted_tiles", 0.0),
        "jelly_converted_color": getattr(evaluation, "jelly_converted_color", None),
        "jelly_charge_cells": getattr(evaluation, "jelly_charge_cells", 0.0),
        "jelly_setup_bonus": getattr(evaluation, "jelly_setup_bonus", 0.0),
        "froggy_lotus_color": getattr(evaluation, "froggy_lotus_color", None),
        "froggy_lotus_collected": getattr(evaluation, "froggy_lotus_collected", 0),
        "froggy_lotus_bonus": getattr(evaluation, "froggy_lotus_bonus", 0.0),
        # What the lotus collect actually banks on the meter. Without these two
        # the lotus charge model cannot be checked at all: the 2026-08-21 and
        # 2026-08-23 matches both read as "charge underpredicted on lotus moves"
        # purely because the fields were never written, so every audit fell back
        # to `blue_cells` -- which by design does not include the gathered
        # cluster.
        "froggy_lotus_charge_cells": getattr(
            evaluation, "froggy_lotus_charge_cells", 0.0
        ),
        "froggy_lotus_charge_value": getattr(
            evaluation, "froggy_lotus_charge_value", 0.0
        ),
        "destroyed_extra_candidates": getattr(
            evaluation,
            "destroyed_extra_candidates",
            0,
        ),
        "preserved_extra_candidates": getattr(
            evaluation,
            "preserved_extra_candidates",
            0,
        ),
        "extra_preservation_penalty": getattr(
            evaluation,
            "extra_preservation_penalty",
            0.0,
        ),
        "decision_gate": getattr(evaluation, "decision_gate", "unknown"),
        # Heuristicki prioritet po kome je rangirano (pre reziduala) i poslednji
        # rezidual naucenog modela za ovaj kandidat (0.0 bez modela).
        "priority_score": learned_value.last_priorities.get(
            learned_value.candidate_key(evaluation)
        ),
        "learned_residual": learned_value.last_residuals.get(
            learned_value.candidate_key(evaluation), 0.0
        ),
        "applied_learned_residual": learned_value.last_applied_residuals.get(
            learned_value.candidate_key(evaluation), 0.0
        ),
        "setup_value": getattr(evaluation, "setup_value", 0.0),
        "direct_match_cells": getattr(evaluation, "direct_match_cells", 0.0),
        "direct_blue_cells": getattr(evaluation, "direct_blue_cells", 0.0),
        "direct_effect_cells": getattr(evaluation, "direct_effect_cells", 0.0),
        "direct_effect_blue_cells": getattr(
            evaluation,
            "direct_effect_blue_cells",
            0.0,
        ),
        "effect_source_counts": dict(
            getattr(evaluation, "effect_source_counts", {}) or {}
        ),
        "reason": describe_move_reason(evaluation),
        "explanation": evaluation.explanation,
        # False kad potez sam nije napravio match (special+special, disko,
        # lobanja, booster/perk): expected_cascades tada pocinje od prve
        # kaskade pada. tools/rebuild_evaluation.py vraca polje u evaluaciju,
        # pa replay snimka vidi isto sto i ziva igra (2026-09-20).
        "has_direct_match_layer": bool(
            getattr(evaluation, "has_direct_match_layer", True)
        ),
        "expected_cascades": serialize_expected_cascades(evaluation),
    }
    if evaluation.cleo_scenario_count:
        payload["cleo"] = {
            "scenario_count": evaluation.cleo_scenario_count,
            "extra_move_scenarios": evaluation.cleo_extra_move_scenarios,
            "extra_move_probability": evaluation.cleo_extra_move_probability,
            "average_score": evaluation.cleo_average_score,
            "worst_score": evaluation.cleo_worst_score,
            "best_score": evaluation.cleo_best_score,
            "risk_score": evaluation.cleo_risk_score,
            "risk_adjustment": evaluation.cleo_risk_adjustment,
            "blue_cells_by_scenario": list(evaluation.cleo_blue_cells_by_scenario),
            "scenario_weights": list(evaluation.cleo_scenario_weights),
            # Per-scenario source colour + score: lets calibrate_from_audit
            # compare the colour distribution the bot assumed against the colour
            # the game actually rolled, and re-fit CLEO_EXTRA_MOVE_CHANCE.
            "scenario_colors": list(evaluation.cleo_scenario_colors),
            "scenario_scores": list(evaluation.cleo_scenario_scores),
            # Per-colour predicted extras, same order as scenario_colors: the
            # observed delta's cleo_check compares the rolled colour's entry
            # with what the move counter did.
            "scenario_extra_moves": list(
                getattr(evaluation, "cleo_scenario_extra_moves", ()) or ()
            ),
            "blue_potential": evaluation.blue_potential,
        }
    return payload

def _serialize_perk_target(target):
    if isinstance(target, tuple):
        return [_serialize_perk_target(part) for part in target]
    if isinstance(target, list):
        return [_serialize_perk_target(part) for part in target]
    return target

def serialize_perk_action(action):
    if action is None:
        return None
    return {
        "perk": action.perk_key,
        "slot_number": getattr(action, "slot_number", None),
        "target": _serialize_perk_target(action.target),
        "score": action.score,
        "gross_score": action.gross_score,
        "threshold": action.threshold,
        "baseline_score": action.baseline_score,
        "reason": action.reason,
        "explanation": action.explanation,
        "selection_policy": "objective_horizon_net_gain",
        "objective": getattr(getattr(action, "objective", None), "value", getattr(action, "objective", "best_move")),
        "legal": getattr(action, "legal", True),
        "legal_reason": getattr(action, "legal_reason", "legal"),
        "immediate_points": getattr(action, "immediate_points", 0.0),
        "next_move_value": getattr(action, "next_move_value", 0.0),
        "horizon_value": getattr(action, "horizon_value", 0.0),
        "mode_value": getattr(action, "mode_value", 0.0),
        "booster_value": getattr(action, "booster_value", 0.0),
        "expected_value": getattr(action, "expected_value", 0.0),
        "lower_quartile": getattr(action, "lower_quartile", 0.0),
        "confidence": getattr(action, "confidence", 1.0),
        "net_gain": getattr(action, "net_gain", 0.0),
        "goal_finish": getattr(action, "goal_finish", False),
        "effect_source": getattr(getattr(action, "effect_source", None), "value", "perk"),
        "planned_perks": list(getattr(action, "planned_perks", ())),
        "effect": {
            "booster_charge_cells": getattr(action, "booster_charge_cells", 0.0),
            "blue_cells": getattr(action, "blue_cells", 0.0),
            "cleared_cells": getattr(action, "cleared_cells", 0.0),
            "activated_specials": getattr(action, "activated_specials", 0.0),
            "extra_moves": getattr(action, "extra_moves", 0.0),
            "mode_targets": getattr(action, "mode_targets", 0.0),
        },
        "follow_up": serialize_move_evaluation(action.follow_up),
    }

def serialize_blue_plan(blue_plan):
    if blue_plan is None:
        return None
    return {
        "best_now": blue_plan.best_now,
        "best_within_two": blue_plan.best_within_two,
        "can_fill_now": blue_plan.can_fill_now,
        "can_fill_within_two": blue_plan.can_fill_within_two,
        "explanation": blue_plan.explanation,
    }

def resolve_mixy_meow_state(request, recognition, mixy_meow_state):
    """Read the Mixy suitcase above the board unless the caller already did."""
    if mixy_meow_state is not None:
        return mixy_meow_state
    if recognition.special_piece_mode not in {
        SPECIAL_PIECE_MODE_AUTO,
        SPECIAL_PIECE_MODE_MIXY_MEOW,
    }:
        return None
    try:
        # Auto-state already captures the full screen in the common GUI path.
        # Reuse it so Mixy detection does not add another screenshot.
        if request.screen_state_image is not None:
            detected = detect_mixy_meow_code_state(request.screen_state_image)
        else:
            detected = detect_mixy_meow_code_state()
    except Exception as exc:
        # Mixy is an optional popup. A transient screenshot failure must not
        # abort an otherwise valid move.
        return MixyMeowState(
            active=False,
            code_colors=(),
            confidence=0.0,
            source="screen_color_tokens",
            reason=f"Mixy detection failed: {type(exc).__name__}",
        )

    if detected.is_reliable:
        remember_mixy_code(detected)
        return detected

    # The suitcase hides between turns while its code stays pending, so an
    # empty read is not proof that Mixy is off. Reuse the last read code until
    # a match completes it or the latch ages out.
    latched = latched_mixy_code()
    if latched is None:
        return detected
    return replace(
        latched,
        source="screen_color_tokens_latched",
        reason=f"latched code ({latched.reason}); this scan: {detected.reason}",
    )


def resolve_ufo_state(request, recognition, ufo_state, booster_action_mode):
    """Count the UFO eyes on the rail unless the caller already did.

    Only when the user has actually picked the UFO. Unlike Mixy -- whose
    suitcase is a large popup that costs one cheap crop to rule out -- deciding
    there is no eye means masking and labelling the whole rail strip, and that
    is pure waste on every turn of every other booster.
    """
    if ufo_state is not None:
        return ufo_state
    if (
        booster_action_mode != BOOSTER_ACTION_UFO
        and recognition.special_piece_mode != SPECIAL_PIECE_MODE_UFO
    ):
        return None
    try:
        # Reuse the full-screen auto-state capture, like Mixy does, so counting
        # the eyes costs no extra screenshot.
        if request.screen_state_image is not None:
            return detect_ufo_eye_state(request.screen_state_image)
        return detect_ufo_eye_state()
    except Exception as exc:
        # The UFO is optional scenery. A transient screenshot failure must not
        # abort an otherwise valid move -- it only means no abduction is
        # modelled this turn.
        return UfoState(
            eyes=0,
            confidence=0.0,
            source="screen_eye_modules",
            reason=f"UFO detection failed: {type(exc).__name__}",
        )


def serialize_ufo_state(ufo_state: UfoState | None):
    if ufo_state is None:
        return None
    return {
        "eyes": int(ufo_state.eyes),
        "confidence": float(ufo_state.confidence),
        "source": ufo_state.source,
        "reason": ufo_state.reason,
        "applied": bool(ufo_state.is_reliable),
        "allow_blues": bool(ufo_state.allow_blues),
        "ability_type": ufo_state.ability_type,
        "engine_eyes": getattr(ufo_state, "engine_eyes", None),
    }


def serialize_mixy_meow_state(
    mixy_state: MixyMeowState | None,
    selected_evaluation=None,
):
    if mixy_state is None:
        return None
    selected_color = None
    candidate_color = getattr(selected_evaluation, "mixy_code_color", None)
    if mixy_state.active and candidate_color in mixy_state.code_colors:
        selected_color = candidate_color
    return {
        "active": bool(mixy_state.active),
        "code_colors": list(mixy_state.code_colors),
        "spent_colors": list(getattr(mixy_state, "spent_colors", ())),
        "uses_this_activation": int(getattr(mixy_state, "uses_this_activation", 0)),
        "max_uses": int(getattr(mixy_state, "max_uses", 0)),
        "exhausted": bool(getattr(mixy_state, "code_exhausted", False)),
        # MixyMeow.UsesLeft straight from the engine on the manual dump this
        # move ran on; None when the agent did not read it (plain poll, older
        # agent build).
        "engine_uses_left": getattr(mixy_state, "engine_uses_left", None),
        "confidence": float(mixy_state.confidence),
        "source": mixy_state.source,
        "reason": mixy_state.reason,
        "selected_color": selected_color,
        "fallback": bool(mixy_state.active and selected_color is None),
    }

def serialize_expected_cascades(evaluation):
    cascades = []
    # Brojevi prate intent_events: efekat samog poteza je kaskada 1, pa kod
    # poteza bez sopstvenog matcha lista pocinje od kaskade 2 (do 2026-09-20
    # pisalo je 1, npr. 2026-09-20_19-33-55_870: match event kaskada 2, ovde 1).
    first_cascade = 1 if getattr(evaluation, "has_direct_match_layer", True) else 2
    for cascade_index, matches in enumerate(
        getattr(evaluation, "cascade_matches", []) or [], start=first_cascade
    ):
        cascades.append({
            "cascade": cascade_index,
            "matches": [
                {
                    "color": match.color,
                    "kind": match.kind,
                    "cells": [list(cell) for cell in sorted(match.cells)],
                    "tile_count": len(match.cells),
                }
                for match in matches
            ],
        })
    return cascades

def serialize_high_voltage_evaluation(evaluation):
    if evaluation is None:
        return None
    return {
        "target_cell": list(evaluation.target_cell),
        "target_color": evaluation.target_color,
        "score": evaluation.score,
        "instant_score": evaluation.instant_score,
        "special_bonus": evaluation.special_bonus,
        "blue_bonus": evaluation.blue_bonus,
        "mode_bonus": evaluation.mode_bonus,
        "extra_move_bonus": evaluation.extra_move_bonus,
        "cleared_cells": evaluation.cleared_cells,
        "blue_cells": evaluation.blue_cells,
        "activated_specials": evaluation.activated_specials,
        "extra_moves": evaluation.extra_moves,
        "cascade_count": evaluation.cascade_count,
        "mode_targets": evaluation.mode_targets,
        "chest_drops": evaluation.chest_drops,
        "multiplier_mushrooms": evaluation.multiplier_mushrooms,
        "board_potential": evaluation.board_potential,
        "next_move_score": evaluation.next_move_score,
        "next_move_bonus": evaluation.next_move_bonus,
        # blue_cells above is charge earned, which is always 0 for a blast; this
        # is every blue cell the activation takes off the board.
        "wasted_blue_cells": getattr(evaluation, "wasted_blue_cells", 0.0),
        "blue_service": getattr(evaluation, "blue_service", 0.0),
        "exact_refill": getattr(evaluation, "exact_refill", False),
        "approximate_refill": getattr(evaluation, "approximate_refill", False),
        "explanation": evaluation.explanation,
    }


def serialize_magic_wand_evaluation(evaluation):
    return serialize_high_voltage_evaluation(evaluation)


def serialize_laser_beam_evaluation(evaluation):
    return serialize_high_voltage_evaluation(evaluation)


def serialize_woolly_workout_evaluation(evaluation):
    payload = serialize_high_voltage_evaluation(evaluation)
    if payload is not None:
        payload["converted_cells"] = evaluation.converted_cells
    return payload


def _screen_state_field_debug_image(field_payload, filename, source_image, run_path):
    if not field_payload or source_image is None:
        return None
    region = field_payload.get("region")
    if not isinstance(region, list) or len(region) != 4:
        return None
    x, y, width, height = (int(value) for value in region)
    if width <= 0 or height <= 0:
        return None
    image_width, image_height = source_image.size
    if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
        return None

    crop_path = run_path / filename
    source_image.crop((x, y, x + width, y + height)).save(crop_path)
    return {
        "path": filename,
        "value": field_payload.get("value"),
        "source": field_payload.get("source"),
        "confidence": field_payload.get("confidence"),
        "accepted": field_payload.get("accepted"),
        "region": region,
    }

def _screen_state_resolved_sources(screen_state_read):
    if screen_state_read is None:
        return {}
    return screen_state_read.get("resolved", {}).get("sources", {}) or {}

def _resolved_state_source(value, screen_state_read, field_name):
    if value is None:
        return "unknown"
    return _screen_state_resolved_sources(screen_state_read).get(field_name) or "manual"


def resolved_score_state(screen_state_read):
    if not isinstance(screen_state_read, dict):
        return {
            "our_score": None,
            "opponent_score": None,
            "score_deficit": None,
            "confidence": None,
            "source": "unknown",
        }
    resolved = screen_state_read.get("resolved") or {}
    score = screen_state_read.get("score") or {}
    if not score.get("accepted"):
        return {
            "our_score": None,
            "opponent_score": None,
            "score_deficit": None,
            "confidence": score.get("confidence"),
            "source": "unknown",
        }
    return {
        "our_score": resolved.get("our_score", score.get("our_score")),
        "opponent_score": resolved.get("opponent_score", score.get("opponent_score")),
        "score_deficit": resolved.get("score_deficit", score.get("score_deficit")),
        "confidence": score.get("confidence"),
        "source": score.get("source", "auto_score_digits"),
    }


def _prep_score_region(screen_state_read):
    """The crop the prep read actually used, so the fresh read can match it.

    Recorded even when the read itself failed (the Party pill is regularly
    hidden behind the combo banner), which is exactly when the fresh read must
    not silently fall back to the versus header region.
    """
    if not isinstance(screen_state_read, dict):
        return None
    region = (screen_state_read.get("score") or {}).get("region")
    if not isinstance(region, (list, tuple)) or len(region) != 4:
        return None
    try:
        return tuple(int(value) for value in region)
    except (TypeError, ValueError):
        return None


def reconcile_screen_state_score(
    screen_state_read,
    fresh_score_read,
    tracked_score_read=None,
    rejection_streaks=None,
):
    """Resolve prep, later runtime and last-known cumulative score reads.

    Auto prep intentionally runs just before the board is declared stable. The
    board can already be still while the cumulative score is still counting up,
    so prep may contain a real but stale intermediate value (for example 98
    while the runtime crop already shows 101). Scores never decrease within one
    game, therefore the component-wise maximum is a safe temporal resolution.
    A tracked value also acts as a floor when score effects hide both live crops.
    """
    payload = copy.deepcopy(screen_state_read) if isinstance(screen_state_read, dict) else {}
    raw_score = payload.get("score") or {}
    if hasattr(fresh_score_read, "to_debug_payload"):
        fresh_score = fresh_score_read.to_debug_payload()
    elif isinstance(fresh_score_read, dict):
        fresh_score = copy.deepcopy(fresh_score_read)
    else:
        fresh_score = {}
    tracked_score = (
        copy.deepcopy(tracked_score_read)
        if isinstance(tracked_score_read, dict)
        else {}
    )

    payload["score_prep"] = copy.deepcopy(raw_score) if raw_score else None
    payload["score_fresh"] = copy.deepcopy(fresh_score) if fresh_score else None
    payload["score_tracked"] = copy.deepcopy(tracked_score) if tracked_score else None

    candidate_scores = [
        (name, score)
        for name, score in (
            ("prep", raw_score),
            ("fresh", fresh_score),
            ("tracked", tracked_score),
        )
        if score.get("accepted") and score.get("our_score") is not None
    ]
    score_rejections = []

    # Solo Challenge has no opponent, so its reads carry our_score alone. Every
    # comparison below is component-wise, so a missing component is simply a
    # component that is not compared -- that keeps the monotonic floor and the
    # outlier checks working on the one score a solo game does have.
    def score_pair(score):
        # Either component can legitimately be absent: solo has no opponent, and
        # an overruled component is masked out below.
        return tuple(
            None if score.get(label) is None else int(score[label])
            for label in SCORE_COMPONENTS
        )

    def component_outlier(candidate, reference, label):
        index = SCORE_COMPONENTS.index(label)
        current = score_pair(candidate)[index]
        previous = score_pair(reference)[index]
        if current is None or previous is None:
            return None
        jump = current - previous
        allowed = max(
            SCORE_RECONCILE_MIN_COMPONENT_JUMP,
            abs(previous) * SCORE_RECONCILE_COMPONENT_JUMP_MULTIPLIER,
        )
        previous_digits = str(abs(previous))
        current_digits = str(abs(current))
        probable_inserted_digit = bool(
            previous >= 10
            and jump >= 100
            and len(current_digits) > len(previous_digits)
            and (
                current_digits.startswith(previous_digits)
                or current_digits.endswith(previous_digits)
            )
        )
        if probable_inserted_digit:
            return jump, allowed, "probable_inserted_score_digit"
        if jump > allowed:
            return jump, allowed, "implausible_component_jump"
        return None

    def implausible_increase(candidate, reference):
        for label in SCORE_COMPONENTS:
            outlier = component_outlier(candidate, reference, label)
            if outlier is not None:
                jump, allowed, kind = outlier
                return label, jump, allowed, kind
        return None

    rejected_names = set()
    current_by_name = {
        name: score
        for name, score in candidate_scores
        if name in {"prep", "fresh"}
    }
    prep_current = current_by_name.get("prep")
    fresh_current = current_by_name.get("fresh")
    # Agreement is judged per component, not on the pair as a whole. The
    # 2026-08-10 21:44 versus game is why: the tracker held a poisoned
    # opponent=2, and the two current reads agreed exactly on the true
    # opponent=3290 while disagreeing on our own score (4 vs 9). Demanding
    # whole-pair agreement threw away the one component that was confirmed, so
    # the correct 3290 stayed rejected for the rest of the match and the bot
    # played as if it were winning.
    confirmed_components = set()
    if prep_current is not None and fresh_current is not None:
        prep_values = score_pair(prep_current)
        fresh_values = score_pair(fresh_current)
        for index, label in enumerate(SCORE_COMPONENTS):
            if prep_values[index] is not None and prep_values[index] == fresh_values[index]:
                confirmed_components.add(label)

    # Recover from a tracker poisoned by an older bad read. Two independent
    # current captures that agree exactly can overrule an implausibly larger
    # historical value; one crop alone cannot lower the monotonic floor. Only
    # the confirmed component is dropped -- the rest of the tracked read still
    # acts as a floor.
    masked_tracked_components = set()
    if tracked_score and fresh_current is not None:
        for label in confirmed_components:
            outlier = component_outlier(tracked_score, fresh_current, label)
            if outlier is None:
                continue
            jump, allowed, _kind = outlier
            masked_tracked_components.add(label)
            score_rejections.append(
                {
                    "name": "tracked",
                    "reason": "tracked_outlier_against_confirmed_current_component",
                    "field": label,
                    "jump": jump,
                    "allowed_jump": allowed,
                    "score": list(score_pair(tracked_score)),
                    "reference": list(score_pair(fresh_current)),
                }
            )
    # The mirror case, and the one the outlier check above cannot see: a
    # *lower* value that both live crops agree on, move after move, means the
    # floor belongs to an earlier match. A score never falls inside one game,
    # and reset_runtime_score_tracking only runs when the user remembers to
    # press "Nova partija". Debug/runs 2026-08-15 rode a 1976 from a previous
    # versus game through a whole party match whose real total was 1599 -- a
    # 377 gap, nowhere near the 4x jump the outlier check needs. Unlike the
    # upward streak below this counts consecutive resolutions rather than a
    # repeated value, because a live score rises every move.
    if isinstance(rejection_streaks, dict) and tracked_score and fresh_current is not None:
        for label in SCORE_COMPONENTS:
            key = ("below_floor", label)
            index = SCORE_COMPONENTS.index(label)
            value = score_pair(fresh_current)[index]
            floor = score_pair(tracked_score)[index]
            if (
                label in confirmed_components
                and floor is not None
                and value is not None
                and value < floor
            ):
                count = rejection_streaks.get(key, (None, 0))[1] + 1
            else:
                count = 0
            rejection_streaks[key] = (None, count)
            if count >= SCORE_NEW_MATCH_DROP_STREAK:
                masked_tracked_components.add(label)
                score_rejections.append(
                    {
                        "name": "tracked",
                        "reason": "floor_from_previous_match",
                        "field": label,
                        "value": value,
                        "consecutive_reads": count,
                        "reference": list(score_pair(tracked_score)),
                    }
                )
    if masked_tracked_components and all(
        label in masked_tracked_components or tracked_score.get(label) is None
        for label in SCORE_COMPONENTS
    ):
        rejected_names.add("tracked")

    # Components whose live value has survived enough consecutive moves that the
    # stored floor, not the reading, is what must be wrong. An animation
    # artefact repeats within one move; it does not hold the same value across
    # several. See SCORE_FLOOR_OVERRULE_STREAK.
    overruled_floor_components = set()
    if isinstance(rejection_streaks, dict):
        for label in SCORE_COMPONENTS:
            if label not in confirmed_components:
                continue
            index = SCORE_COMPONENTS.index(label)
            value = score_pair(fresh_current)[index]
            floor = score_pair(tracked_score)[index] if tracked_score else None
            previous_value, count = rejection_streaks.get(label, (None, 0))
            # Only ever upward. A score does not fall inside a game, so a
            # persistent value *below* the floor is a misread, and overruling
            # downwards would leave the floor stuck low while every genuinely
            # rising read got rejected as an implausible jump.
            if (
                floor is not None
                and value is not None
                and value > floor
                and component_outlier(fresh_current, tracked_score, label)
            ):
                count = count + 1 if previous_value == value else 1
            else:
                value, count = None, 0
            rejection_streaks[label] = (value, count)
            if count >= SCORE_FLOOR_OVERRULE_STREAK:
                overruled_floor_components.add(label)
                score_rejections.append(
                    {
                        "name": "tracked",
                        "reason": "floor_overruled_by_persistent_current_reads",
                        "field": label,
                        "value": value,
                        "consecutive_reads": count,
                        "reference": list(score_pair(tracked_score)),
                    }
                )

    tracked_reference = None
    if tracked_score and "tracked" not in rejected_names:
        tracked_reference = copy.deepcopy(tracked_score)
        for label in masked_tracked_components:
            tracked_reference[label] = None
        # Substitute the masked copy everywhere, not just as a comparison
        # reference: a component overruled as poisoned must not come back
        # through the component-wise maximum below either.
        candidate_scores = [
            (name, tracked_reference if name == "tracked" else score)
            for name, score in candidate_scores
        ]
    if tracked_reference is not None:
        for name, score in candidate_scores:
            if name not in {"prep", "fresh"}:
                continue
            outlier = None
            for label in SCORE_COMPONENTS:
                # A value that keeps coming back move after move is not an
                # animation artefact -- the floor itself is wrong. Without this
                # escape a tracker poisoned *low* is self-sealing: the correct
                # value looks like an implausible jump up from the bad floor and
                # is rejected forever (Debug 2026-08-10 21:44: opponent stuck at
                # 2 for the whole match while the live reads said 3290, so the
                # bot played as if it were winning by 1787).
                if label in overruled_floor_components:
                    continue
                component = component_outlier(score, tracked_reference, label)
                if component is not None:
                    outlier = (label,) + component
                    break
            if outlier is None:
                continue
            field, jump, allowed, outlier_kind = outlier
            rejected_names.add(name)
            score_rejections.append(
                {
                    "name": name,
                    "reason": (
                        "probable_inserted_digit_from_tracked_score"
                        if outlier_kind == "probable_inserted_score_digit"
                        else "implausible_increase_from_tracked_score"
                    ),
                    "field": field,
                    "jump": jump,
                    "allowed_jump": allowed,
                    "score": list(score_pair(score)),
                    "reference": list(score_pair(tracked_reference)),
                }
            )

    payload["score_rejections"] = score_rejections
    accepted_scores = [
        (name, score)
        for name, score in candidate_scores
        if name not in rejected_names
    ]
    if not accepted_scores:
        return payload

    our_values = [
        int(score["our_score"])
        for _name, score in accepted_scores
        if score.get("our_score") is not None
    ]
    if not our_values:
        return payload
    our_score = max(our_values)
    opponent_values = [
        int(score["opponent_score"])
        for _name, score in accepted_scores
        if score.get("opponent_score") is not None
    ]
    opponent_score = max(opponent_values) if opponent_values else None
    confidence = min(
        float(score.get("confidence", 0.0)) for _name, score in accepted_scores
    )
    current_scores = [score for name, score in accepted_scores if name in {"prep", "fresh"}]
    effective_score = copy.deepcopy(
        current_scores[-1] if current_scores else accepted_scores[-1][1]
    )
    effective_score.update(
        {
            "our_score": our_score,
            "opponent_score": opponent_score,
            "score_deficit": (
                None if opponent_score is None else opponent_score - our_score
            ),
            "confidence": confidence,
            "accepted": True,
            "source": (
                "auto_score_digits_tracked_fallback"
                if not current_scores
                else "auto_score_digits_reconciled"
            ),
            "reason": (
                f"prep={raw_score.get('our_score')}-{raw_score.get('opponent_score')}; "
                f"fresh={fresh_score.get('our_score')}-{fresh_score.get('opponent_score')}; "
                f"tracked={tracked_score.get('our_score')}-{tracked_score.get('opponent_score')}; "
                f"resolved={our_score}-{opponent_score}; "
                f"rejected={','.join(sorted(rejected_names)) or 'none'}"
            ),
        }
    )

    payload["score"] = effective_score
    resolved = payload.setdefault("resolved", {})
    resolved["our_score"] = effective_score.get("our_score")
    resolved["opponent_score"] = effective_score.get("opponent_score")
    resolved["score_deficit"] = effective_score.get("score_deficit")
    resolved.setdefault("sources", {})["score"] = effective_score.get("source", "unknown")
    return payload


def reset_runtime_score_tracking():
    global _runtime_tracked_score
    _runtime_tracked_score = None
    _runtime_score_rejection_streaks.clear()
    move_telemetry.reset()


def reconcile_and_track_screen_state_score(screen_state_read, fresh_score_read):
    global _runtime_tracked_score
    payload = reconcile_screen_state_score(
        screen_state_read,
        fresh_score_read,
        tracked_score_read=_runtime_tracked_score,
        rejection_streaks=_runtime_score_rejection_streaks,
    )
    effective_score = payload.get("score") or {}
    if effective_score.get("accepted"):
        _runtime_tracked_score = copy.deepcopy(effective_score)
    return payload


def auto_score_changed_after_stable_prep(screen_state_read, fresh_score_read):
    """True when the pre-play crop proves a confirmed prep score was premature."""
    if not isinstance(screen_state_read, dict):
        return False
    stability = screen_state_read.get("score_stability") or {}
    if stability.get("enabled") is False:
        return False
    if not stability.get("stable"):
        return False
    samples = stability.get("samples") or []
    if not samples or not getattr(fresh_score_read, "accepted", False):
        return False
    confirmed = samples[-1]
    if not isinstance(confirmed, (list, tuple)) or len(confirmed) != 2:
        return False
    fresh = (fresh_score_read.our_score, fresh_score_read.opponent_score)
    return fresh != (confirmed[0], confirmed[1])

def resolved_booster_maximum(booster_maximum=None, screen_state_read=None):
    if isinstance(screen_state_read, dict):
        resolved = screen_state_read.get("resolved") or {}
        resolved_maximum = resolved.get("booster_maximum")
        # Memory-sourced maximum is PlayerModel.energyToAbility itself and
        # outranks every screen read. This used to peek at `resolved` directly,
        # bypassing `sources` -- the one mechanism every other field uses -- so
        # it is folded into the same gate here (2026-08-23).
        if (
            _screen_state_resolved_sources(screen_state_read).get("booster_maximum")
            == SCORE_SOURCE_MEMORY
            and isinstance(resolved_maximum, (int, float))
            and resolved_maximum > 0
        ):
            return int(resolved_maximum)
        booster_field = screen_state_read.get("booster_charge") or {}
        field_maximum = booster_field.get("maximum")
        if (
            booster_field.get("accepted")
            and isinstance(field_maximum, (int, float))
            and field_maximum > 0
        ):
            return int(field_maximum)
    if isinstance(booster_maximum, (int, float)) and booster_maximum > 0:
        return int(booster_maximum)
    if isinstance(screen_state_read, dict):
        resolved = screen_state_read.get("resolved") or {}
        resolved_maximum = resolved.get("booster_maximum")
        if isinstance(resolved_maximum, (int, float)) and resolved_maximum > 0:
            return int(resolved_maximum)
    return BOOSTER_MAX_CHARGE


def resolve_strategy_states(
    booster_charge,
    remaining_moves,
    screen_state_read=None,
    total_rounds=None,
    current_round=None,
    booster_maximum=None,
    turn_time_left=None,
    seconds_per_move=None,
    turns_left_in_match=None,
    opponent_booster=None,
    opponent_charge_colors=(),
    opponent_next_turn_moves=None,
    opponent_score_multiplier=None,
):
    maximum = resolved_booster_maximum(booster_maximum, screen_state_read)
    try:
        # The engine's match-wide turn counter, read on our turn, counts this
        # turn too: 1 means nobody plays after us.
        opponent_turn_follows = int(turns_left_in_match) > 1
    except (TypeError, ValueError):
        opponent_turn_follows = None
    return (
        BoosterState(
            current=booster_charge,
            maximum=maximum,
            source=_resolved_state_source(
                booster_charge,
                screen_state_read,
                "booster_charge",
            ),
        ),
        TurnState(
            remaining_moves=remaining_moves,
            source=_resolved_state_source(
                remaining_moves,
                screen_state_read,
                "remaining_moves",
            ),
            moves_left_in_match=compute_moves_left_in_match(
                remaining_moves, total_rounds, current_round
            ),
            is_final_round=compute_is_final_round(total_rounds, current_round),
            current_round=current_round,
            total_rounds=total_rounds,
            time_left_seconds=turn_time_left,
            seconds_per_move=seconds_per_move,
            opponent_turn_follows=opponent_turn_follows,
            opponent_booster=opponent_booster,
            opponent_charge_colors=opponent_charge_colors,
            opponent_next_turn_moves=opponent_next_turn_moves,
            opponent_score_multiplier=opponent_score_multiplier,
        ),
    )

def effective_booster_state_for_detection(booster_state, booster_detection):
    # A memory-sourced BoosterState is PlayerModel.energy read out of the game
    # and may not be rounded up to "full" by a visual ACTIVATE hit. The bump
    # below exists for the screen path, whose meter read can lag behind the
    # button; memory cannot lag itself, and overwriting it would let a stray
    # template match (or the memory-authorised detection itself) fake a full
    # meter into the charge economy (2026-08-23 sweep).
    if booster_state is not None and booster_state.source == SCORE_SOURCE_MEMORY:
        return booster_state
    if booster_detection and booster_detection.get("active"):
        maximum = (
            booster_state.maximum
            if booster_state is not None and booster_state.maximum > 0
            else BOOSTER_MAX_CHARGE
        )
        return BoosterState(
            current=maximum,
            maximum=maximum,
            source="booster_detection",
        )
    return booster_state

def _board_region_screenshot():
    """One grab of the board region, or None if geometry is not configured yet.

    Used by the memory path, which has the pieces but not the overlays drawn on
    top of them (jelly area, Funky markers).
    """
    region = (
        int(recognition.left),
        int(recognition.up),
        int(recognition.width),
        int(recognition.height),
    )
    if region[2] <= 0 or region[3] <= 0:
        return None
    try:
        return capture.capture_debug_screenshot(None, region=region, write_to_disk=False)
    except Exception:
        # A missing screen is not a reason to lose the move: the detectors are
        # given None and report nothing, exactly as before.
        return None


def resolve_booster_activation_detection(
    booster_debug_path,
    *,
    force_no_booster=False,
    screen_state_read=None,
    booster_action_mode=BOOSTER_ACTION_NONE,
):
    if force_no_booster:
        clear_booster_ready_latch()
        return {
            "active": False,
            "score": 0.0,
            "latched": False,
            "suppressed": True,
        }

    memory_ready = memory_reader_booster_ready(screen_state_read)
    if memory_ready is not None:
        # The engine settled it, and nothing on screen is consulted: not for
        # permission and, since 2026-09-18, not for the click point either (the
        # ACTIVATE template is not even shipped on every install, so the click
        # was already landing on a fallback point). The latch is a screen-path
        # device and has nothing left to do here.
        clear_booster_ready_latch()
        return _memory_booster_click_detection(memory_ready)

    booster_detection = detect_booster_activate(booster_debug_path)
    # Screen path only. Any positive sighting feeds the click-location cache.
    _remember_booster_activate_location(booster_detection)
    if digit_reader_confirms_no_activate(screen_state_read):
        clear_booster_ready_latch()
        raw_active = bool(booster_detection.get("active", False))
        raw_score = float(booster_detection.get("score", 0.0))
        return {
            "active": False,
            "score": raw_score,
            "latched": False,
            "suppressed_by_digit_reader": True,
            "raw_active": raw_active,
        }
    if meter_reader_confirms_partial_charge(screen_state_read) and not (
        _booster_detection_is_strong(booster_detection)
    ):
        clear_booster_ready_latch()
        return {
            "active": False,
            "score": float(booster_detection.get("score", 0.0)),
            "latched": False,
            "suppressed_by_meter_reader": True,
            "raw_active": bool(booster_detection.get("active", False)),
        }

    if booster_detection.get("active"):
        already_latched = _booster_ready_latch["detection"] is not None
        if not already_latched and not _booster_detection_is_strong(booster_detection):
            # Single text-band frame: look again after a short pause. A ready
            # booster is still there and activates this same turn; a floating
            # score popup / glare frame is gone and no move is wasted either way.
            time.sleep(BOOSTER_TEXT_BAND_RETRY_DELAY_SECONDS)
            retry_detection = detect_booster_activate(booster_debug_path)
            if retry_detection.get("active"):
                confirmed = dict(retry_detection)
                confirmed["confirmed_by_retry"] = True
                return apply_booster_ready_latch(confirmed, booster_action_mode)
            pending = dict(booster_detection)
            pending["active"] = False
            pending["latched"] = False
            pending["pending_confirmation"] = True
            return pending

    return apply_booster_ready_latch(
        booster_detection,
        booster_action_mode,
    )

INTENT_SPECIAL_LABELS = {
    "bomb": "Bomb",
    "bomb_bomb": "Bomb+Bomb",
    "horizontal": "Horizontal",
    "vertical": "Vertical",
    "firework_left": "Firework left",
    "firework_right": "Firework right",
    "firework_up": "Firework up",
    "firework_down": "Firework down",
    "lightning": "Lightning",
    "crosshair": "Crosshair",
    "heart": "Heart",
    "vinnie_se_heart": "Vinnie SE heart",
    "knight": "Knight",
    "created_special": "Created special",
    "color_crystal": "Color crystal",
    "disco": "Disco",
}


def _format_intent_cell(cell):
    if not isinstance(cell, (list, tuple)) or len(cell) != 2:
        return "(?,?)"
    return f"({cell[0]},{cell[1]})"


def _format_intent_cells(cells):
    if not isinstance(cells, (list, tuple)) or not cells:
        return "(no cells)"
    return ", ".join(_format_intent_cell(cell) for cell in cells)


def _format_intent_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def _intent_special_label(name):
    return INTENT_SPECIAL_LABELS.get(name, str(name).replace("_", " ").title())


def _intent_match_kind_label(kind):
    return str(kind).replace("_", " ").title()


def _intent_color_label(color):
    return COLOR_DEBUG_LABELS.get(color, str(color))


def _intent_grid_symbol(value) -> str:
    if not value:
        return "."
    label = COLOR_DEBUG_LABELS.get(value)
    if not label:
        return "?"
    # Blue and purple both start with a distinct letter except b/p clash with
    # nothing else here, so the first letter is unambiguous across the six
    # playable colours (b/g/y/p/r/o).
    return label[0]


def _format_intent_board_grid(board, highlight_cells=None) -> list[str]:
    """ASCII dump of a modelled board; highlighted cells are upper-cased.

    Used to show exactly how the Sweep SE broom is predicted to rearrange the
    board, so the prediction can be compared against the real screenshot.
    """
    highlight = {tuple(cell) for cell in (highlight_cells or [])}
    lines = ["    " + " ".join(str(col) for col in range(len(board[0])))] if board else []
    for row_index, row in enumerate(board):
        cells = []
        for col_index, value in enumerate(row):
            symbol = _intent_grid_symbol(value)
            if (row_index, col_index) in highlight:
                symbol = symbol.upper()
            cells.append(symbol)
        lines.append(f"  {row_index} " + " ".join(cells))
    return lines


def _render_intent_expected_total(payload: dict | None) -> str:
    if not payload:
        return (
            "Expected total: "
            "N/A cleared cells, N/A blue cells, "
            "N/A activated specials, N/A cascades."
        )
    def total_value(field):
        value = payload.get(field)
        if value is None:
            return "N/A"
        return _format_intent_number(value)

    return (
        "Expected total: "
        f"{total_value('cleared_cells')} cleared cells, "
        f"{total_value('blue_cells')} blue cells, "
        f"{total_value('activated_specials')} activated specials, "
        f"{total_value('cascade_count')} cascades."
    )


def render_move_intent_text(move_payload: dict) -> str:
    selected_action = move_payload.get("selected_action")
    lines = [f"Selected action: {selected_action}"]
    best_move = move_payload.get("best_move") or {}
    planned_move = best_move
    reason = best_move.get("reason", "") if best_move else ""
    perk_only_plan = None

    if selected_action == "activate_perk":
        perk_action = move_payload.get("selected_perk_action") or {}
        lines.append(f"Perk: {perk_action.get('perk', 'unknown')}")
        follow_up = perk_action.get("follow_up")
        planned_move = follow_up or {}
        if follow_up:
            reason = (
                perk_action.get("reason")
                or perk_action.get("explanation")
                or planned_move.get("reason", "")
            )
        else:
            reason = (
                perk_action.get("reason")
                or perk_action.get("explanation")
                or f"Activate perk {perk_action.get('perk', 'unknown')}."
            )
            score = (
                "N/A"
                if perk_action.get("score") is None
                else _format_intent_number(perk_action.get("score"))
            )
            gross_score = (
                "N/A"
                if perk_action.get("gross_score") is None
                else _format_intent_number(perk_action.get("gross_score"))
            )
            perk_only_plan = f"{reason} Score {score}, gross score {gross_score}."
    elif selected_action == "activate_booster":
        high_voltage_target = move_payload.get("high_voltage_target") or {}
        magic_wand_target = move_payload.get("magic_wand_target") or {}
        laser_beam_target = move_payload.get("laser_beam_target") or {}
        woolly_workout_target = move_payload.get("woolly_workout_target") or {}
        dragon_move = move_payload.get("dragon_move") or {}
        if high_voltage_target:
            lines.append(
                f"High Voltage target: {_format_intent_cell(high_voltage_target.get('target_cell'))}"
            )
            planned_move = high_voltage_target
            reason = high_voltage_target.get("explanation") or "Activate booster target."
        elif magic_wand_target:
            lines.append(
                f"Magic Wand target: {_format_intent_cell(magic_wand_target.get('target_cell'))}"
            )
            planned_move = magic_wand_target
            reason = magic_wand_target.get("explanation") or "Activate booster target."
        elif laser_beam_target:
            lines.append(
                f"Laser Beam target: {_format_intent_cell(laser_beam_target.get('target_cell'))}"
            )
            planned_move = laser_beam_target
            reason = laser_beam_target.get("explanation") or "Activate booster target."
        elif woolly_workout_target:
            lines.append(
                "Woolly Workout target: "
                f"{_format_intent_cell(woolly_workout_target.get('target_cell'))}"
            )
            planned_move = woolly_workout_target
            reason = woolly_workout_target.get("explanation") or "Activate booster target."
        elif dragon_move:
            lines.append(
                "Dragon move: "
                f"{_format_intent_cell(dragon_move.get('start'))} -> "
                f"{_format_intent_cell(dragon_move.get('target'))}"
            )
            planned_move = dragon_move
            reason = dragon_move.get("explanation") or "Activate Dragon move."
        elif not planned_move:
            reason = "Activate booster."
    elif not planned_move:
        reason = "No move details available."

    if planned_move and planned_move.get("start") is not None and planned_move.get("target") is not None:
        start = _format_intent_cell(planned_move.get("start"))
        target = _format_intent_cell(planned_move.get("target"))
        direction = planned_move.get("direction")
        lines.append(f"Move: {start} -> {target} {direction}")

    lines.append("Plan:")
    plan_lines = []
    for event in planned_move.get("intent_events") or []:
        event_type = event.get("type")
        if event_type == "special_effect":
            special_name = event.get("special")
            special_label = _intent_special_label(special_name)
            cell = _format_intent_cell(event.get("cell"))
            cleared = _format_intent_number(event.get("cleared_cells"))
            blue = _format_intent_number(event.get("blue_cells"))

            if special_name == "bomb":
                plan_lines.append(
                    f"- {special_label} explodes from {cell}, clears {cleared} cells, including {blue} blue cells."
                )
            elif special_name == "bomb_bomb":
                plan_lines.append(
                    f"- {special_label} explodes from target {cell}, clears {cleared} cells, including {blue} blue cells."
                )
            elif special_name == "vertical":
                plan_lines.append(f"- {special_label} clears {cleared} cells, including {blue} blue cells.")
            else:
                plan_lines.append(
                    f"- {special_label} clears {cleared} cells from {cell}, including {blue} blue cells."
                )

            for activated_cell in event.get("activated_specials") or []:
                plan_lines.append(
                    f"- {special_label} activates special at {_format_intent_cell(activated_cell)}."
                )
        elif event_type == "sweep_se_activation":
            plan_lines.append(
                "- Broom sweeps "
                f"{_intent_color_label(event.get('color'))} "
                f"{event.get('direction')} from {_format_intent_cell(event.get('cell'))}, "
                f"packing {len(event.get('swept_cells') or [])} tiles against the edge."
            )
            setup_bonus = event.get("setup_bonus") or 0.0
            if setup_bonus:
                plan_lines.append(
                    "- Board left behind is worth "
                    f"{_format_intent_number(setup_bonus)} next turn "
                    f"({_format_intent_number(event.get('setup_pairs'))} adjacent pairs, "
                    f"{_format_intent_number(event.get('setup_blue_tiles'))} packed blue, "
                    f"plus ~{_format_intent_number(event.get('setup_recolour_tiles'))} "
                    "recoloured tiles the sim does not create)."
                )
            packed_board = event.get("packed_board")
            if packed_board:
                plan_lines.append("- Predicted board right after the sweep (SWEPT tiles upper-case):")
                plan_lines.extend(
                    f"  {line}"
                    for line in _format_intent_board_grid(
                        packed_board, event.get("swept_cells")
                    )
                )
        elif event_type == "ufo_abduction":
            colors = event.get("colors") or []
            plan_lines.append(
                "- UFO abducts every ordinary "
                + " and ".join(_intent_color_label(color) for color in colors)
                + f" tile on cascade {_format_intent_number(event.get('cascade'))}."
            )
        elif event_type == "uncertain_refill_boundary":
            plan_lines.append("- Later refill-dependent cascades are not counted as known intent.")
        elif event_type == "measured_charge_expectation":
            source = event.get("source")
            if source == "knight":
                plan_lines.append(
                    "- Knight chain is expected to charge about "
                    f"{_format_intent_number(event.get('blue_cells'))} more than its "
                    f"modelled cells ({_format_intent_number(event.get('activations'))} "
                    "activations, measured)."
                )
            else:
                plan_lines.append(
                    f"- {_intent_color_label(event.get('color'))} jelly conversion is "
                    "expected to charge about "
                    f"{_format_intent_number(event.get('blue_cells'))} (measured)."
                )
        elif event_type == "froggy_lotus_collect":
            plan_lines.append(
                "- Froggy lotus collects "
                f"{_format_intent_number(event.get('collected'))} "
                f"{_intent_color_label(event.get('color'))} pieces at "
                f"{_format_intent_number(event.get('value'))}"
                f"x each."
            )
        elif event_type == "xtra_move_collect":
            plan_lines.append(
                "- XTRA marker grants "
                f"{_format_intent_number(event.get('extra_moves'))} extra move "
                f"from {_format_intent_cells(event.get('cells') or [])}."
            )
        elif event_type == "match":
            cells = event.get("cells") or []
            tile_count = event.get("tile_count", len(cells))
            tile_label = "tile" if _format_intent_number(tile_count) == "1" else "tiles"
            plan_lines.append(
                "- "
                f"Cascade {_format_intent_number(event.get('cascade'))}: "
                f"{_intent_match_kind_label(event.get('kind'))} "
                f"{_intent_color_label(event.get('color'))} match clears "
                f"{_format_intent_number(tile_count)} {tile_label} at {_format_intent_cells(cells)}."
            )

    if not plan_lines:
        if planned_move:
            if selected_action == "activate_booster" and (
                move_payload.get("high_voltage_target") or move_payload.get("magic_wand_target")
                or move_payload.get("woolly_workout_target")
            ):
                plan_lines.append(f"- {reason}")
            else:
                plan_lines.append("- No detailed intent events were recorded; using score summary only.")
        elif perk_only_plan:
            plan_lines.append(f"- {perk_only_plan}")
        else:
            plan_lines.append("- No move details available.")
    lines.extend(plan_lines)

    lines.append("Why selected:")
    lines.append(str(reason))
    lines.append(_render_intent_expected_total(planned_move))
    return "\n".join(lines) + "\n"


def _intent_audit_path(run_path: Path) -> Path:
    if run_path.parent.name == "runs":
        return run_path.parent.parent / INTENT_AUDIT_FILENAME
    return run_path.parent / INTENT_AUDIT_FILENAME


def _intent_audit_totals(payload: dict | None) -> str:
    if not payload:
        return (
            "N/A cleared cells, N/A blue cells, "
            "N/A activated specials, N/A cascades"
        )
    return (
        f"{_format_intent_number(payload.get('cleared_cells'))} cleared cells, "
        f"{_format_intent_number(payload.get('blue_cells'))} blue cells, "
        f"{_format_intent_number(payload.get('activated_specials'))} activated specials, "
        f"{_format_intent_number(payload.get('cascade_count'))} cascades"
    )


def _intent_audit_reason_and_totals(move_payload: dict) -> tuple[str, str]:
    selected_action = move_payload.get("selected_action")
    if selected_action == "move":
        best_move = move_payload.get("best_move") or {}
        if not best_move:
            return "No move details available.", _intent_audit_totals(None)
        return (
            best_move.get("reason") or best_move.get("explanation") or "Move selected.",
            _intent_audit_totals(best_move),
        )

    if selected_action == "activate_perk":
        perk_action = move_payload.get("selected_perk_action") or {}
        follow_up = perk_action.get("follow_up")
        reason = (
            perk_action.get("reason")
            or perk_action.get("explanation")
            or f"Activate perk {perk_action.get('perk', 'unknown')}."
        )
        if follow_up:
            return reason, _intent_audit_totals(follow_up)
        score = _format_intent_number(perk_action.get("score"))
        gross_score = _format_intent_number(perk_action.get("gross_score"))
        return (
            f"{reason} Score {score}, gross score {gross_score}.",
            _intent_audit_totals(None),
        )

    if selected_action == "activate_booster":
        high_voltage_target = move_payload.get("high_voltage_target") or {}
        if high_voltage_target:
            return (
                high_voltage_target.get("explanation") or "Activate booster target.",
                _intent_audit_totals(high_voltage_target),
            )
        magic_wand_target = move_payload.get("magic_wand_target") or {}
        if magic_wand_target:
            return (
                magic_wand_target.get("explanation") or "Activate booster target.",
                _intent_audit_totals(magic_wand_target),
            )
        laser_beam_target = move_payload.get("laser_beam_target") or {}
        if laser_beam_target:
            return (
                laser_beam_target.get("explanation") or "Activate booster target.",
                _intent_audit_totals(laser_beam_target),
            )
        woolly_workout_target = move_payload.get("woolly_workout_target") or {}
        if woolly_workout_target:
            return (
                woolly_workout_target.get("explanation") or "Activate booster target.",
                _intent_audit_totals(woolly_workout_target),
            )
        dragon_move = move_payload.get("dragon_move") or {}
        if dragon_move:
            return (
                dragon_move.get("explanation") or "Activate Dragon move.",
                _intent_audit_totals(dragon_move),
            )
        return "Activate booster.", _intent_audit_totals(None)

    return "No move selected.", _intent_audit_totals(None)


def _render_intent_audit_entry(run_path: Path, move_payload: dict) -> str:
    if run_path.parent.name == "runs":
        detail_path = Path("runs") / run_path.name / INTENT_FILENAME
    else:
        detail_path = Path(run_path.name) / INTENT_FILENAME

    reason, expected_total = _intent_audit_reason_and_totals(move_payload)
    return (
        f"## {run_path.name}\n"
        f"- Selected action: {move_payload.get('selected_action')}\n"
        f"- Reason: {reason}\n"
        f"- Expected total: {expected_total}\n"
        f"- Detail: {detail_path.as_posix()}\n\n"
    )


def write_intent_debug_files(run_path: Path, move_payload: dict) -> None:
    run_path = Path(run_path)
    intent_text = render_move_intent_text(move_payload)
    (run_path / INTENT_FILENAME).write_text(intent_text, encoding="utf-8")

    audit_path = _intent_audit_path(run_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as audit_file:
        audit_file.write(_render_intent_audit_entry(run_path, move_payload))


def describe_move_reason(evaluation):
    reasons = []
    if getattr(evaluation, "froggy_lotus_bonus", 0.0) > 0:
        reasons.append("aktivira Froggy lotus i skuplja ciljnu boju")
    if has_guaranteed_true_extra(evaluation):
        reasons.append("daje extra move")
    if evaluation.disco_moves > 0:
        reasons.append("ne trosi normalan potez")
    if evaluation.special_bonus > 0:
        reasons.append("pravi ili aktivira specijal")
    if evaluation.cascade_count > 1:
        reasons.append("pokrece kaskadu")
    elif evaluation.instant_score >= 8:
        reasons.append("cisti dosta polja")
    if evaluation.blue_bonus > 0:
        reasons.append("skuplja plave")
    if evaluation.mode_bonus > 0:
        reasons.append("dobar je za izabrani mod")
    if evaluation.lookahead_bonus > 0:
        reasons.append("postavlja jak sledeci potez")

    if not reasons:
        return "Odigrao sam ovo jer je najbolji od legalnih poteza po trenutnoj tabli."
    if len(reasons) == 1:
        return f"Odigrao sam ovo jer {reasons[0]}."
    return f"Odigrao sam ovo jer {', '.join(reasons[:-1])} i {reasons[-1]}."

def write_recognized_overlay(
    board_image_path,
    output_path,
    board,
    special_board,
    best_evaluation=None,
    ml_cells=None,
    funky_cells=None,
    jelly_cells=None,
):
    image = Image.open(board_image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    ml_by_pos = {}
    for cell in ml_cells or []:
        ml_by_pos[(cell.get("row"), cell.get("col"))] = cell
    funky_positions = {tuple(cell) for cell in (funky_cells or ())}
    jelly_positions = {tuple(cell) for cell in (jelly_cells or ())}
    for row, values in enumerate(board):
        for col, color in enumerate(values):
            x = col * recognition.squareSize
            y = row * recognition.squareSize
            unrecognized = color == 0 and special_board[row][col] == 0
            ml_cell = ml_by_pos.get((row, col)) if unrecognized else None
            if unrecognized:
                # In ML "only" mode one rejected cell discards the whole ML
                # board, so every cell reads 0 here. Show the per-cell ML
                # guess anyway: red = the cell that actually got rejected,
                # orange = ML knew it but the board was thrown away.
                label = "???"
                if ml_cell is not None:
                    label = (
                        f"{ml_cell.get('ml_class', '?')}\n"
                        f"{float(ml_cell.get('confidence', 0.0)):.2f}"
                        f"/{float(ml_cell.get('threshold', 0.0)):.2f}"
                    )
                rejected = ml_cell is None or not ml_cell.get("accepted")
                outline = (255, 0, 0) if rejected else (255, 165, 0)
                outline_width = 3 if rejected else 2
                fill = (200, 0, 0) if rejected else (120, 70, 0)
                box_bottom = y + 17 if ml_cell is None else y + 30
            else:
                label = debug_cell_label(color, special_board[row][col])
                outline = (255, 255, 0)
                outline_width = 1
                fill = (0, 0, 0)
                box_bottom = y + 17
            if (row, col) in jelly_positions:
                label = f"{label}\nJELLY"
                outline = (255, 0, 255)
                outline_width = 3
                box_bottom = max(box_bottom, y + 30)
            if (row, col) in funky_positions:
                label = f"{label}\nFUNKY"
                outline = (0, 255, 255)
                outline_width = 4
                box_bottom = max(box_bottom, y + 30)
            draw.rectangle((x, y, x + recognition.squareSize - 1, y + recognition.squareSize - 1), outline=outline, width=outline_width)
            text_box = (x + 2, y + 2, x + min(recognition.squareSize - 2, 76), box_bottom)
            draw.rectangle(text_box, fill=fill)
            draw.text((x + 4, y + 4), label, fill=(255, 255, 255))

    if best_evaluation is not None:
        best_candidate = oriented_swap_candidate(best_evaluation)
        start_row, start_col = best_candidate.start
        target_row, target_col = best_candidate.target
        sx = start_col * recognition.squareSize
        sy = start_row * recognition.squareSize
        tx = target_col * recognition.squareSize
        ty = target_row * recognition.squareSize
        draw.rectangle((sx, sy, sx + recognition.squareSize - 1, sy + recognition.squareSize - 1), outline=(0, 255, 0), width=4)
        draw.rectangle((tx, ty, tx + recognition.squareSize - 1, ty + recognition.squareSize - 1), outline=(255, 80, 80), width=4)
        draw.line(
            (
                sx + recognition.squareSize // 2,
                sy + recognition.squareSize // 2,
                tx + recognition.squareSize // 2,
                ty + recognition.squareSize // 2,
            ),
            fill=(0, 255, 0),
            width=3,
        )

    image.save(output_path)

def write_move_debug_report(
    run_dir,
    source_board_image_path,
    board,
    special_board,
    best_evaluation,
    ranked_candidates,
    mode,
    profile,
    allow_square_matches,
    score_rally_values,
    special_piece_mode=SPECIAL_PIECE_MODE_AUTO,
    booster_action_mode=BOOSTER_ACTION_NONE,
    specials_explode_immediately=False,
    color_crush=False,
    energized_colors=(),
    engine_charge_colors=None,
    mushroom_multipliers=False,
    vertical_matches_destroy_color=False,
    matches_destroy_color=False,
    all_specials_lightning=False,
    every_match_is_special=False,
    line_destruction=(False, False),
    include_future_value=True,
    action="best_move",
    selected_action="move",
    booster_detection=None,
    high_voltage_target=None,
    magic_wand_target=None,
    laser_beam_target=None,
    woolly_workout_target=None,
    dragon_move=None,
    mixy_meow_state=None,
    ufo_state=None,
    selected_perks=None,
    detected_perk_slots=None,
    selected_perk_action=None,
    perk_candidates=None,
    best_rejected_perk=None,
    perk_slot_reasons=None,
    perk_last_chance=None,
    perk_slot_status=None,
    score_region_path=None,
    score_region=None,
    previous_run=None,
    observed_delta_path=None,
    booster_charge=None,
    booster_maximum=None,
    remaining_moves=None,
    total_rounds=None,
    current_round=None,
    round_source=None,
    blue_plan=None,
    screen_state_read=None,
    screen_state_image=None,
    top_candidates=20,
    full_ranked_candidates=None,
    exploration=None,
    booster_state=None,
    turn_state=None,
    strategy_context=None,
    decision_gate="unknown",
    play_enabled=True,
    ml_recognition_payload=None,
    funky_cells=None,
    jelly_cells=None,
    jelly_state=None,
    hot_color_state=None,
    color_climb_state=None,
    floor_lava_state=None,
):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    # `source_board_image_path` is None when the caller asked for a JSON-only run
    # (RunRequest.debug_images_enabled false). Everything below this point is the
    # record of *what the bot decided*, which is what move auditing and score
    # calibration read; the two board images only show what it saw, and cost
    # ~625 KB of the ~660 KB a full run folder takes.
    if source_board_image_path is not None:
        source_path = Path(source_board_image_path)
        flush_debug_screenshot_writes(source_path)
        board_path = run_path / "board.png"
        if source_path.resolve() != board_path.resolve():
            shutil.copy2(source_path, board_path)

        recognized_path = run_path / "recognized.png"
        ml_cells = None
        if isinstance(ml_recognition_payload, dict):
            ml_cells = ml_recognition_payload.get("cells")
        write_recognized_overlay(
            board_path,
            recognized_path,
            board,
            special_board,
            best_evaluation,
            ml_cells=ml_cells,
            funky_cells=funky_cells,
            jelly_cells=jelly_cells,
        )

    score_region_payload = None
    if score_region_path is not None:
        source_score_path = Path(score_region_path)
        flush_debug_screenshot_writes(source_score_path)
        score_path = run_path / SCORE_REGION_FILENAME
        if source_score_path.resolve() != score_path.resolve():
            shutil.copy2(source_score_path, score_path)
        score_region_payload = {"path": SCORE_REGION_FILENAME}
        if score_region is not None:
            score_region_payload["region"] = list(score_region)

    screen_state_image_payload = None
    if screen_state_image is not None:
        state_image_path = run_path / STATE_IMAGE_FILENAME
        screen_state_image.save(state_image_path)
        screen_state_image_payload = {"path": STATE_IMAGE_FILENAME}

    screen_state_payload = None
    screen_state_debug_payload = None
    if screen_state_read is not None:
        screen_state_debug_payload = copy.deepcopy(screen_state_read)
        debug_images = {}
        booster_image = _screen_state_field_debug_image(
            screen_state_debug_payload.get("booster_charge"),
            STATE_BOOSTER_IMAGE_FILENAME,
            screen_state_image,
            run_path,
        )
        if booster_image is not None:
            debug_images["booster_charge"] = booster_image
        moves_image = _screen_state_field_debug_image(
            screen_state_debug_payload.get("remaining_moves"),
            STATE_MOVES_IMAGE_FILENAME,
            screen_state_image,
            run_path,
        )
        if moves_image is not None:
            debug_images["remaining_moves"] = moves_image
        round_image = _screen_state_field_debug_image(
            screen_state_debug_payload.get("current_round"),
            STATE_ROUND_IMAGE_FILENAME,
            screen_state_image,
            run_path,
        )
        if round_image is not None:
            debug_images["current_round"] = round_image
        turn_image = _screen_state_field_debug_image(
            screen_state_debug_payload.get("turn_owner"),
            STATE_TURN_IMAGE_FILENAME,
            screen_state_image,
            run_path,
        )
        if turn_image is not None:
            debug_images["turn_owner"] = turn_image
        if debug_images:
            screen_state_debug_payload["debug_images"] = debug_images

        screen_state_path = run_path / STATE_READER_FILENAME
        screen_state_path.write_text(
            json.dumps(screen_state_debug_payload, indent=2),
            encoding="utf-8",
        )
        screen_state_payload = {
            "path": STATE_READER_FILENAME,
            "resolved": screen_state_debug_payload.get("resolved"),
            "booster_charge": screen_state_debug_payload.get("booster_charge"),
            "remaining_moves": screen_state_debug_payload.get("remaining_moves"),
            "current_round": screen_state_debug_payload.get("current_round"),
            "turn_owner": screen_state_debug_payload.get("turn_owner"),
            "score": screen_state_debug_payload.get("score"),
            "score_stability": screen_state_debug_payload.get("score_stability"),
            "debug_images": screen_state_debug_payload.get("debug_images"),
        }

    if booster_state is None or turn_state is None:
        resolved_booster_state, resolved_turn_state = resolve_strategy_states(
            booster_charge,
            remaining_moves,
            screen_state_read,
            total_rounds=total_rounds,
            current_round=current_round,
            booster_maximum=booster_maximum,
        )
        booster_state = booster_state or resolved_booster_state
        turn_state = turn_state or resolved_turn_state

    strategy_context = strategy_context_or_unknown(strategy_context)
    match_context = build_match_context(
        strategy_mode=strategy_context.mode,
        game_mode=game_mode_value(mode),
        booster="default",
        booster_action_mode=normalize_booster_action_mode(booster_action_mode),
        remaining_moves=turn_state.remaining_moves,
        moves_left_in_match=turn_state.moves_left_in_match,
        current_round=current_round,
        total_rounds=total_rounds,
        our_score=getattr(strategy_context, "our_score", None),
        opponent_score=getattr(strategy_context, "opponent_score", None),
        score_deficit=getattr(strategy_context, "score_deficit", None),
        score_confidence=getattr(strategy_context, "score_confidence", None),
    )
    if (
        best_evaluation is not None
        and getattr(best_evaluation, "decision_gate", "unknown") == "unknown"
    ):
        original_best_evaluation = best_evaluation
        best_evaluation = replace(best_evaluation, decision_gate=decision_gate)
        ranked_candidates = [
            best_evaluation if evaluation is original_best_evaluation else evaluation
            for evaluation in ranked_candidates
        ]

    move_payload = {
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "ranking_provenance": learned_value.ranking_provenance(),
        "ranking_context": {
            "booster_state": asdict(booster_state),
            "turn_state": asdict(turn_state),
            "strategy_context": asdict(strategy_context),
        },
        "action": action,
        "mode": game_mode_value(mode),
        "profile": profile,
        "special_piece_mode": normalize_special_piece_mode(special_piece_mode),
        "booster_action_mode": normalize_booster_action_mode(booster_action_mode),
        "allow_square_matches": allow_square_matches,
        "specials_explode_immediately": specials_explode_immediately,
        "color_crush": color_crush,
        "energized_colors": list(energized_colors or ()),
        "engine_charge_colors": (
            None if engine_charge_colors is None else list(engine_charge_colors)
        ),
        "mushroom_multipliers": bool(mushroom_multipliers),
        "vertical_matches_destroy_color": vertical_matches_destroy_color,
        "matches_destroy_color": bool(matches_destroy_color),
        "all_specials_lightning": bool(all_specials_lightning),
        "every_match_is_special": bool(every_match_is_special),
        "line_destruction": list(line_destruction or (False, False)),
        "include_future_value": include_future_value,
        "score_rally_values": score_rally_values,
        "hot_color_state": hot_color_state,
        # Color Climb: the dealt pair the scorer played with (bot colour codes)
        # and the live multiplier, so a match can be audited afterwards.
        "color_climb_state": color_climb_state,
        # The Floor Is Lava: the marked columns the scorer played with
        # (1-based, like floor_lava_checked_columns_after) and where they came
        # from -- "memory" is ColumnsEruptionDictionary, "tally" the bot's own
        # bookkeeping. Until 2026-09-20 only the prediction was stored, so
        # "did that move mark what we said" could not be answered from a run.
        "floor_lava_state": floor_lava_state,
        "selected_action": selected_action,
        "play_enabled": play_enabled,
        "intent_file": INTENT_FILENAME,
        "decision_gate": decision_gate,
        "exploration": exploration,
        "booster_detection": booster_detection,
        "booster_state": {
            "current": booster_state.current,
            "maximum": booster_state.maximum,
            "source": booster_state.source,
        },
        "turn_state": {
            "remaining_moves": turn_state.remaining_moves,
            "moves_left_in_match": turn_state.moves_left_in_match,
            "source": turn_state.source,
            "time_left_seconds": turn_state.time_left_seconds,
            "seconds_per_move": turn_state.seconds_per_move,
            "is_final_round": turn_state.is_final_round,
            "opponent_turn_follows": turn_state.opponent_turn_follows,
        },
        "round_state": {
            "current": current_round,
            "total": total_rounds,
            "source": round_source,
        },
        "strategy_context": {
            "mode": strategy_context.mode,
            # The two flags that switch every blue-hoarding policy on or off
            # (disco / high-voltage / lotus-sweep-jelly blue-first, and the
            # points-first override that scopes them). Without them in the log
            # a "why did it not chase blue?" question cannot be answered from
            # the run at all -- the mode alone reads the same whether the
            # policy was active or not.
            "booster_rush": strategy_context.booster_rush,
            "solo_challenge": strategy_context.solo_challenge,
            "solo_goal": asdict(strategy_context.solo_goal) if strategy_context.solo_goal else None,
            "is_solo_booster_rush": strategy_context.is_solo_booster_rush,
            "is_solo_challenge": strategy_context.is_solo_challenge,
        },
        "active_booster": "default",
        "match_context": match_context.to_payload(),
        "score_state": {
            "our_score": match_context.our_score,
            "opponent_score": match_context.opponent_score,
            "score_deficit": match_context.score_deficit,
            "confidence": match_context.score_confidence,
            "strategy": match_context.score_strategy,
            "expected_safe_points": match_context.expected_safe_points,
        },
        "blue_plan": serialize_blue_plan(blue_plan),
        "high_voltage_target": serialize_high_voltage_evaluation(high_voltage_target),
        "magic_wand_target": serialize_magic_wand_evaluation(magic_wand_target),
        "laser_beam_target": serialize_laser_beam_evaluation(laser_beam_target),
        "woolly_workout_target": serialize_woolly_workout_evaluation(
            woolly_workout_target
        ),
        "dragon_move": serialize_move_evaluation(dragon_move),
        "mixy_meow": serialize_mixy_meow_state(mixy_meow_state, best_evaluation),
        "ufo": serialize_ufo_state(ufo_state),
        "selected_perks": list(selected_perks or (PERK_NONE, PERK_NONE)),
        "detected_perk_slots": [
            serialize_perk_slot_detection(detection)
            for detection in (detected_perk_slots or [])
        ],
        "perk_slot_status": [dict(entry) for entry in (perk_slot_status or ())],
        "perk_slot_reasons": [dict(entry) for entry in (perk_slot_reasons or ())],
        "perk_last_chance": perk_last_chance,
        "selected_perk_action": serialize_perk_action(selected_perk_action),
        "best_rejected_perk": serialize_perk_action(best_rejected_perk)
        if best_rejected_perk is not None
        else (
            serialize_perk_action((perk_candidates or [None])[0])
            if selected_perk_action is None and perk_candidates
            else None
        ),
        "perk_candidates": [
            serialize_perk_action(action)
            for action in (perk_candidates or [])[:top_candidates]
        ],
        "score_region": score_region_payload,
        "screen_state_read": screen_state_payload,
        "screen_state_image": screen_state_image_payload,
        "previous_run": Path(previous_run).name if previous_run else None,
        "observed_delta_for_previous_run": (
            {
                "run": Path(previous_run).name,
                "path": Path(observed_delta_path).name,
            }
            if previous_run and observed_delta_path
            else None
        ),
        "board": grid_to_lists(board),
        "special_board": grid_to_lists(special_board),
        "funky_tile_cells": [list(cell) for cell in sorted(funky_cells or ())],
        "jelly_zone_cells": [list(cell) for cell in sorted(jelly_cells or ())],
        # Where those cells came from. With Debug on the memory path records the
        # engine's own answer next to the host's parse of it, plus the raw
        # dictionary they were read out of -- so a wrong zone can be traced to
        # the read, the parse or the mapping without replaying the match.
        "jelly_state": jelly_state,
        "best_move": serialize_move_evaluation(best_evaluation),
        "will_play": (
            play_enabled
            and selected_action == "move"
            and best_evaluation is not None
        ),
        "will_activate_booster": play_enabled and selected_action == "activate_booster",
        "will_activate_perk": play_enabled and selected_action == "activate_perk",
        "will_click_high_voltage_target": play_enabled and high_voltage_target is not None,
        "will_click_magic_wand_target": play_enabled and magic_wand_target is not None,
        "will_click_laser_beam_target": play_enabled and laser_beam_target is not None,
        "will_click_woolly_workout_target": (
            play_enabled and woolly_workout_target is not None
        ),
        "will_play_dragon_move": play_enabled and dragon_move is not None,
    }
    candidates_payload = [
        serialize_move_evaluation(evaluation)
        for evaluation in ranked_candidates[:top_candidates]
    ]

    (run_path / "move.json").write_text(
        json.dumps(move_payload, indent=2, default=_debug_json_default),
        encoding="utf-8",
    )
    (run_path / "candidates.json").write_text(
        json.dumps(candidates_payload, indent=2, default=_debug_json_default),
        encoding="utf-8",
    )
    # On extra-move turns the candidate list above is filtered to extra-granting
    # moves only. When the caller also supplies the full ranked move list, log it
    # separately so offline learning can compare the played extra move against the
    # best plain move it never considered. Absent (None) on normal turns, where
    # candidates.json already holds the full ranking.
    if full_ranked_candidates is not None:
        full_candidates_payload = [
            serialize_move_evaluation(evaluation)
            for evaluation in full_ranked_candidates[:max(top_candidates, 40)]
        ]
        (run_path / "candidates_all.json").write_text(
            json.dumps(full_candidates_payload, indent=2),
            encoding="utf-8",
        )
    try:
        write_intent_debug_files(run_path, move_payload)
    except Exception as exc:
        try:
            (run_path / INTENT_FILENAME).write_text(
                f"Intent debug unavailable: {exc}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    # The previous run's delta was written before this run had read the meters,
    # so close it out now that they are known. The two quantities settle at
    # different moments, so they are closed on different frames:
    #
    # * booster charge accumulates continuously, so the tightest window is best
    #   -- the first frame whose board is stable. Waiting longer lets a booster
    #   activation or a later move land inside the window.
    # * the move counter needs the extra-move dot, which arrives a beat late.
    #   Debug 2026-08-10 22:52 reads 9 -> 8 -> 9 across a move, a booster
    #   activation and the next move; the middle frame was not "settling" (the
    #   board was stable, only the dots were not) yet reported a delivered extra
    #   as missing. It is final only once the next move is being decided.
    global _pending_observed_delta
    if observed_delta_path:
        _pending_observed_delta = Path(observed_delta_path)
    settled = not str(decision_gate).startswith("recognition_blocked:")
    move_decision = settled and selected_action == "move"
    if _pending_observed_delta is not None and screen_state_debug_payload is not None:
        try:
            close_observed_delta_state(
                _pending_observed_delta,
                screen_state_debug_payload,
                settled=settled,
                move_decision=move_decision,
                after_floor_lava_state=floor_lava_state,
            )
        except Exception as exc:
            print("Observed delta state close failed:", exc)
        if move_decision:
            _pending_observed_delta = None
    return run_path


def close_observed_delta_state(
    observed_delta_path,
    after_state,
    settled=True,
    move_decision=True,
    after_floor_lava_state=None,
):
    """Fill in an observed delta's after-meters once this run has read them.

    The delta is written during recognition, before the booster/move meters of
    the new frame exist, so it used to record only the board. Answering "did
    that move charge the booster" or "did it really keep the turn" then meant
    pairing consecutive state_reader.json files by hand. With both ends stored,
    one file per move carries the whole before/after picture.

    ``settled`` is False for a frame captured while the board is still moving;
    its meters are written anyway (better than nothing when no settled frame
    follows) but marked provisional. ``move_decision`` marks the later frame on
    which the next move is chosen, which is the only point where the move
    counter can be trusted -- so the turn verdict is filled in then, without
    disturbing the booster reading already taken from the tighter window.
    """
    delta_path = Path(observed_delta_path)
    if not delta_path.exists():
        return
    payload = json.loads(delta_path.read_text(encoding="utf-8"))
    before_state = _run_resolved_state(delta_path.parent)
    after_resolved = (after_state or {}).get("resolved") or {}
    existing = payload.get("state_delta") or {}

    def gained(before, after, field):
        first, second = before.get(field), after.get(field)
        if first is None or second is None:
            return None
        return int(second) - int(first)

    # Keep the earliest settled reading of the booster: waiting longer lets an
    # activation or another move land inside the window.
    if existing.get("after_settled"):
        booster_after = existing.get("after") or {}
        booster_gained = existing.get("booster_charge_gained")
        after_settled = True
    else:
        booster_after = after_resolved
        raw = gained(before_state, after_resolved, "booster_charge")
        # Negative means the booster fired between the two reads, so the gain is
        # unknowable rather than zero.
        booster_gained = None if raw is not None and raw < 0 else raw
        after_settled = bool(settled)

    if move_decision:
        moves_gained = gained(before_state, after_resolved, "remaining_moves")
        kept = _kept_the_turn(before_state, after_resolved, moves_gained)
        turn_after = after_resolved
    else:
        moves_gained = existing.get("remaining_moves_gained")
        kept = existing.get("kept_the_turn")
        turn_after = existing.get("turn_after") or {}

    payload["state_delta"] = {
        "before": before_state,
        "after": booster_after,
        "booster_charge_gained": booster_gained,
        "after_settled": after_settled,
        # The turn verdict comes from a later frame than the booster reading, so
        # its own after-state is kept beside it rather than overwriting.
        "turn_after": turn_after,
        # Raw difference, not a bool: the counter also refills on a new round.
        "remaining_moves_gained": moves_gained,
        "kept_the_turn": kept,
        "turn_measured": bool(move_decision or existing.get("turn_measured")),
    }

    _fill_memory_score_delta(payload, delta_path.parent, after_state)

    best_move = (payload.get("previous_move") or {}).get("best_move") or {}
    if best_move:
        predicted_extra = max(
            float(best_move.get("extra_moves") or 0.0),
            float(best_move.get("direct_extra_moves") or 0.0),
        )
        # The meter cannot take more than it has room for: a move that clears
        # nine blue into a 3/7 booster charges 4, and comparing the raw nine
        # against that reads as a model error when the model was exactly right.
        # Three of the 24 recorded disco activations were only this.
        predicted_charge = best_move.get("blue_cells")
        try:
            room = float(before_state.get("booster_maximum")) - float(
                before_state.get("booster_charge")
            )
        except (AttributeError, TypeError, ValueError):
            room = None
        if predicted_charge is not None and room is not None and room >= 0:
            predicted_charge = min(float(predicted_charge), room)
        # A booster that fired between the two reads leaves a negative raw
        # delta, which `booster_charge_gained` reports as None. That is not a
        # failed prediction and must not be audited as one: firing needs a full
        # meter, so the move earned at least the room that was left. Two of the
        # 2026-08-23 disco moves read as "unmeasured" this way, and their trace
        # frames showed both predictions had been exactly right (4->7 on a
        # predicted 3, and 5->5 on a predicted 0, spent a move later).
        charge_spent_between = (
            payload["state_delta"]["booster_charge_gained"] is None
            and before_state is not None
            and after_state is not None
        )
        payload["prediction_check"] = {
            "predicted_blue_cells": best_move.get("blue_cells"),
            # What the meter can actually take of it -- this is the number the
            # observed gain has to match.
            "predicted_booster_charge_gained": predicted_charge,
            # True when the meter was spent inside the measuring window, so the
            # observed gain is a floor (`observed_charge_at_least`), not a value.
            "charge_spent_between": charge_spent_between,
            "observed_charge_at_least": room if charge_spent_between else None,
            "observed_booster_charge_gained": payload["state_delta"][
                "booster_charge_gained"
            ],
            "predicted_extra_moves": predicted_extra,
            "observed_kept_the_turn": payload["state_delta"]["kept_the_turn"],
            "predicted_cleared_cells": best_move.get("cleared_cells"),
            "observed_changed_cells": (payload.get("board_delta") or {}).get(
                "changed_count"
            ),
        }
        cleo_check = _cleo_prediction_check(payload, best_move)
        if cleo_check is not None:
            payload["cleo_check"] = cleo_check
    if move_decision:
        lava_check = _floor_lava_prediction_check(
            delta_path.parent, best_move, after_floor_lava_state
        )
        if lava_check is not None:
            payload["floor_lava_check"] = lava_check
    delta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _floor_lava_prediction_check(previous_run_path, best_move, after_state):
    """Predicted lava marks against the engine's, once the next move is decided.

    Only a "memory" after-state is evidence: the tally is the bot's own
    prediction carried forward and always agrees with itself. Written for the
    open question of 2026-09-20 -- whether a swap that matches nothing (disco,
    special+special, skull) marks its own column -- which the runs of that day
    could not answer because the live marks were never stored.
    """
    if not isinstance(after_state, dict):
        return None
    try:
        previous_move = json.loads(
            (Path(previous_run_path) / "move.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    before_state = previous_move.get("floor_lava_state")
    if not isinstance(before_state, dict):
        return None
    best_move = best_move or {}
    observed = sorted(int(col) for col in after_state.get("columns") or ())
    check = {
        "before_columns": before_state.get("columns"),
        "before_source": before_state.get("source"),
        "selected_action": previous_move.get("selected_action"),
        "has_direct_match_layer": best_move.get("has_direct_match_layer"),
        "observed_columns_after": observed,
        "observed_source": after_state.get("source"),
        "predicted_columns_after": None,
        "predicted_destroyed_columns": None,
        "matches_prediction": None,
    }
    # Booster/perk targets carry no lava prediction; the before/after pair is
    # still worth having, the verdict is not.
    if previous_move.get("selected_action") == "move" and best_move:
        predicted = sorted(
            int(col) for col in best_move.get("floor_lava_checked_columns_after") or ()
        )
        check["predicted_columns_after"] = predicted
        check["predicted_destroyed_columns"] = list(
            best_move.get("floor_lava_destroyed_columns") or ()
        )
        if after_state.get("source") == "memory":
            check["matches_prediction"] = predicted == observed
            check["unpredicted_marks"] = sorted(set(observed) - set(predicted))
            check["missing_marks"] = sorted(set(predicted) - set(observed))
    return check


# An unchanged move counter is trustworthy at once, but a *dropped* one read
# this soon after the move can still be restored by a late extra-move credit
# (memory_gui._report_broken_promise, measured 2026-08-26).
CLEO_CHECK_LOST_TURN_MIN_GAP_SECONDS = 8.0
# The clone colour is read off the boards as the colour that lost the most
# tiles; below this many it cannot be told from ordinary clearing.
CLEO_CHECK_MIN_COLOUR_DROP = 3


def _run_name_seconds(name):
    try:
        stamp, millis = str(name).rsplit("_", 1)
        return (
            datetime.datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S").timestamp()
            + int(millis) / 1000.0
        )
    except (TypeError, ValueError):
        return None


def _cleo_prediction_check(payload, best_move):
    """Did the Cleo simulation predict what the game did? None for other moves.

    Reads the clone colour the game picked off the before/after boards, looks up
    the extra the simulation predicted for exactly that colour, and compares it
    with the move counter. Verdict: "pogodio", "promasio" or "nepoznato" (with
    the reason), so a whole session can be counted with tools/cleo_audit.py.
    """
    cleo = best_move.get("cleo") or {}
    colors = [int(color) for color in cleo.get("scenario_colors") or []]
    before = payload.get("board_before")
    after = payload.get("board_after")
    special_before = payload.get("special_board_before")
    start, target = best_move.get("start"), best_move.get("target")
    if not colors or not before or not after or not special_before or not start or not target:
        return None
    cleo_code = SPECIAL_CLEO_BUG
    if special_before[start[0]][start[1]] == cleo_code:
        drags_cleo, partner = True, target
    elif special_before[target[0]][target[1]] == cleo_code:
        drags_cleo, partner = False, start
    else:
        return None
    partner_color = int(before[partner[0]][partner[1]])

    def counts(board):
        tally = {}
        for row in board:
            for value in row:
                tally[int(value)] = tally.get(int(value), 0) + 1
        return tally

    count_before, count_after = counts(before), counts(after)
    drops = sorted(
        ((count_before.get(color, 0) - count_after.get(color, 0), color) for color in colors),
        reverse=True,
    )
    top_drop, actual_color = drops[0] if drops else (0, None)
    runner_up = drops[1][0] if len(drops) > 1 else 0
    colour_sure = top_drop >= CLEO_CHECK_MIN_COLOUR_DROP and top_drop > runner_up

    extras = cleo.get("scenario_extra_moves")
    predicted_extra = None
    if actual_color is not None and extras and len(extras) == len(colors):
        predicted_extra = float(extras[colors.index(actual_color)]) >= 1.0

    state_delta = payload.get("state_delta") or {}
    kept = state_delta.get("kept_the_turn")
    gap = None
    first, second = _run_name_seconds(payload.get("previous_run")), _run_name_seconds(
        payload.get("after_run")
    )
    if first is not None and second is not None:
        gap = round(second - first, 1)
    turn_sure = kept is True or (
        kept is False and gap is not None and gap >= CLEO_CHECK_LOST_TURN_MIN_GAP_SECONDS
    )

    if not state_delta.get("turn_measured"):
        verdict, reason = "nepoznato", "potez jos nije izmeren"
    elif kept is None:
        verdict, reason = "nepoznato", "brojac poteza nije citljiv"
    elif not colour_sure:
        verdict, reason = "nepoznato", "boja se ne vidi sa table"
    elif predicted_extra is None:
        verdict, reason = "nepoznato", "nema predvidjanja po boji (stari zapis)"
    else:
        verdict = "pogodio" if predicted_extra == kept else "promasio"
        reason = (
            ""
            if predicted_extra == kept
            else "predvideo extra, igra nije dala"
            if predicted_extra
            else "nije predvideo extra, igra ga je dala"
        )
        if not turn_sure:
            # A counter that dropped this soon can still be restored.
            verdict = f"verovatno {verdict}"
            reason = "; ".join(
                part for part in (reason, f"brojac pao posle {gap}s") if part
            )
    return {
        "drags_cleo": drags_cleo,
        "partner_color": partner_color,
        "predicted_probability": cleo.get("extra_move_probability"),
        "predicted_extra_by_color": (
            {str(color): float(extra) for color, extra in zip(colors, extras)}
            if extras and len(extras) == len(colors)
            else None
        ),
        "actual_color": actual_color if colour_sure else None,
        "actual_color_guess": actual_color,
        "colour_drops": {str(color): drop for drop, color in drops},
        "predicted_extra_for_actual_color": predicted_extra,
        "observed_kept_the_turn": kept,
        "seconds_to_next_decision": gap,
        "verdict": verdict,
        "reason": reason,
    }


def _memory_score_payload(state_payload):
    """A run's score block, but only when it came from memory (exact, no OCR)."""
    score = (state_payload or {}).get("score") or {}
    if score.get("source") != SCORE_SOURCE_MEMORY or not score.get("accepted"):
        return None
    if score.get("our_score") is None:
        return None
    return dict(score)


def _fill_memory_score_delta(payload, previous_run_dir, after_state):
    """Close the score delta from the memory reader when no crop was captured.

    The crop path is the only source write_observed_delta_report has, and the
    memory board source never captures one -- so every memory-played move wrote
    `readable: false` and no calibration sample, while PlayerModel.score had the
    exact before/after all along. Solo has no opponent, so the confirmation rule
    drops the "opponent gained nothing" half rather than failing on a null.
    """
    existing = payload.get("score_delta") or {}
    if existing.get("readable"):
        return
    before_state = _run_state_payload(previous_run_dir)
    before_score = _memory_score_payload(before_state)
    after_score = _memory_score_payload(after_state)
    if before_score is None or after_score is None:
        return

    our_gained = int(after_score["our_score"]) - int(before_score["our_score"])
    opponent_gained = None
    if (
        before_score.get("opponent_score") is not None
        and after_score.get("opponent_score") is not None
    ):
        opponent_gained = int(after_score["opponent_score"]) - int(
            before_score["opponent_score"]
        )
    confirmed = our_gained >= 0 and opponent_gained in (None, 0)
    payload["score_delta"] = {
        "confirmed": confirmed,
        "readable": True,
        "before": before_score,
        "after": after_score,
        "our_points_gained": our_gained,
        "opponent_points_gained": opponent_gained,
    }

    previous_move = payload.get("previous_move") or {}
    if not confirmed or previous_move.get("selected_action") != "move":
        return
    best_move = previous_move.get("best_move") or {}
    booster_detection = previous_move.get("booster_detection") or {}
    payload["calibration_sample"] = {
        "score_before": before_score.get("our_score"),
        "score_after": after_score.get("our_score"),
        "actual_points": our_gained,
        "predicted_utility_score": best_move.get("score", ""),
        "cleared_cells": best_move.get("cleared_cells"),
        "activated_specials": best_move.get("activated_specials"),
        "cascade_count": best_move.get("cascade_count"),
        "blue_cells": best_move.get("blue_cells"),
        "booster_active": bool(booster_detection.get("active", False)),
        "active_booster": previous_move.get("active_booster", "default"),
    }


def _kept_the_turn(before_state, after_state, moves_gained):
    """Whether this one move kept the turn, or None when it cannot be told.

    The move counter answers this only when the two reads bracket exactly one
    move. In a versus match it counts moves left in the current turn, refills
    between turns, and the pair of reads can straddle the opponent -- the
    2026-08-10 22:19 game shows 3->1 drops, which no single move can produce.
    Reporting False there invented five "false extra move" alarms that were
    only a stale window, so anything outside a clean one-move step says None.
    """
    if moves_gained is None or moves_gained > 0:
        return None
    if moves_gained < -1:
        return None
    before_round = before_state.get("current_round")
    after_round = after_state.get("current_round")
    # Only a *known* change of round disqualifies. An unreadable round is
    # common on the settling frame the after-state comes from, and a refill
    # would already have shown up as the counter going up.
    if before_round is not None and after_round is not None and before_round != after_round:
        return None
    if before_state.get("turn_owner") != "us" or after_state.get("turn_owner") != "us":
        return None
    return moves_gained == 0


def _run_state_payload(run_path):
    state_path = Path(run_path) / STATE_READER_FILENAME
    if not state_path.exists():
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_resolved_state(run_path):
    return _run_state_payload(run_path).get("resolved") or {}

def swipe(direction):
    """Human-style flick: press, brief settle, glide to endpoint, brief hold, lift.

    Replaces pyautogui.drag() because drag fires mouseUp the instant the last
    interpolated move event ships, which BlueStacks' GestureDetector frequently
    misclassifies as a tap-hold instead of a fling. Splitting the press/move/
    release with explicit pre- and post-move holds mirrors what a hand on the
    mouse produces and crosses the Android fling-velocity threshold reliably.

    If a recorded profile is loaded and enabled, the user's real hand flick is
    replayed instead — same press/move/release shape but with the velocity
    curve BlueStacks already accepts when the user plays manually.
    """
    if SWIPE_USE_PROFILE and SWIPE_PROFILE is not None:
        import swipe_recorder  # local import keeps cold-start dependency lazy
        # Diagnostic wrappers: attribute replay wall time to the individual
        # input calls (the 2026-08-24 session lost ~1s per move somewhere in
        # the play path). Overhead is a perf_counter pair per call.
        steps = {"down_ms": 0.0, "moves_ms": 0.0, "sleep_ms": 0.0, "up_ms": 0.0, "move_calls": 0}

        def _timed(fn, key, count_key=None):
            def wrapped(*args, **kwargs):
                started = time.perf_counter()
                result = fn(*args, **kwargs)
                steps[key] += (time.perf_counter() - started) * 1000.0
                if count_key is not None:
                    steps[count_key] += 1
                return result
            return wrapped

        swipe_recorder.play_recording(
            SWIPE_PROFILE,
            direction,
            scale_factor=getattr(recognition, "display_scale", 1.0),
            speed_factor=SWIPE_PROFILE_SPEED,
            post_hold_seconds=SWIPE_POST_MOVE_HOLD_SECONDS,
            mouse_down=_timed(pyautogui.mouseDown, "down_ms"),
            move_to=_timed(pyautogui.moveTo, "moves_ms", "move_calls"),
            mouse_up=_timed(pyautogui.mouseUp, "up_ms"),
            sleep=_timed(time.sleep, "sleep_ms"),
            perf_counter=time.perf_counter,
        )
        steps["profile_used"] = 1.0
        _last_play_step_timings.update(steps)
        return

    delta = _SWIPE_UNIT_DELTAS.get(direction)
    if delta is None:
        return
    scaled_distance = max(
        1,
        int(round(SWIPE_DISTANCE_PX * getattr(recognition, "display_scale", 1.0))),
    )
    dx = delta[0] * scaled_distance
    dy = delta[1] * scaled_distance
    start_x, start_y = pyautogui.position()
    pyautogui.mouseDown(button='left', _pause=False)
    time.sleep(SWIPE_PRE_MOVE_HOLD_SECONDS)
    # Own glide instead of pyautogui.moveTo(duration=...): pyautogui splits the
    # drag into ~one step per pixel and sleeps between all of them, which under
    # the default Windows timer measured ~1s per swipe. A handful of steps
    # paced against a perf_counter deadline keeps the same duration with move
    # events tight enough for the fling classifier.
    glide_started = time.perf_counter()
    for step in range(1, SWIPE_SYNTHETIC_STEPS + 1):
        fraction = step / SWIPE_SYNTHETIC_STEPS
        wait = glide_started + SWIPE_DURATION_SECONDS * fraction - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
        pyautogui.moveTo(
            start_x + int(round(dx * fraction)),
            start_y + int(round(dy * fraction)),
            duration=0,
            _pause=False,
        )
    time.sleep(SWIPE_POST_MOVE_HOLD_SECONDS)
    pyautogui.mouseUp(button='left', _pause=False)
    _last_play_step_timings["profile_used"] = 0.0

def board_cell_center(cell):
    row, col = cell
    return (
        recognition.top_left_x + recognition.squareSize * col,
        recognition.top_left_y + recognition.squareSize * row,
    )

def perk_slot_center(slot_number):
    if slot_number not in (1, 2):
        raise ValueError("Perk slot must be 1 or 2")
    calibrated_centers = getattr(recognition, "calibrated_perk_slot_centers", None)
    if calibrated_centers and len(calibrated_centers) >= slot_number:
        center = calibrated_centers[slot_number - 1]
        return int(center[0]), int(center[1])
    profile = getattr(recognition, "current_board_profile", None)
    if profile == SUPERSIZE_PROFILE:
        ui_scale = getattr(recognition, "display_scale", 1.0)
        ref_size = max(1, int(round(PERK_SLOT_REFERENCE_SQUARE_SIZE * ui_scale)))
        # Supersize board.left=664 but the perks UI slot 1 sits at screen
        # X=705 (matching regular profile's top_left_x). Using ref_size//2=42
        # gives 706, which is 1px right of the icon center and drops the
        # template match below threshold. Trim by 1 to land on the icon.
        slot_1_x = recognition.left + ref_size // 2 - 1
        return (
            slot_1_x + ref_size * (slot_number - 1),
            recognition.up
            + int(round(PERK_SLOT_BOARD_TOP_Y_OFFSET[SUPERSIZE_PROFILE] * ui_scale)),
        )
    return (
        recognition.top_left_x + recognition.squareSize * (slot_number - 1),
        recognition.up + recognition.height + int(round(recognition.squareSize * PERK_SLOT_Y_OFFSET_RATIO)),
    )

def perk_slot_capture_size(*, party=False):
    profile = getattr(recognition, "current_board_profile", None)
    width_ratio = PARTY_PERK_SLOT_WIDTH_RATIO if party else PERK_SLOT_WIDTH_RATIO
    height_ratio = PARTY_PERK_SLOT_HEIGHT_RATIO if party else PERK_SLOT_HEIGHT_RATIO
    if profile == SUPERSIZE_PROFILE:
        ref_size = max(
            1,
            int(
                round(
                    PERK_SLOT_REFERENCE_SQUARE_SIZE
                    * getattr(recognition, "display_scale", 1.0)
                )
            ),
        )
    else:
        ref_size = recognition.squareSize
    return (
        max(1, int(round(ref_size * width_ratio))),
        max(1, int(round(ref_size * height_ratio))),
    )


def perk_slot_search_size(*, party=False):
    width, height = perk_slot_capture_size(party=party)
    profile = getattr(recognition, "current_board_profile", None)
    if profile == SUPERSIZE_PROFILE:
        reference_size = (
            PERK_SLOT_REFERENCE_SQUARE_SIZE
            * getattr(recognition, "display_scale", 1.0)
        )
    else:
        reference_size = recognition.squareSize
    padding = max(
        2,
        int(round(reference_size * PERK_SLOT_SEARCH_PADDING_RATIO)),
    )
    return width + 2 * padding, height + 2 * padding


def normalize_perk_detection_capture(image, local_centers, slot_size, ui_scale):
    """Upscale/downscale a portable UI crop back to canonical template pixels."""

    resolved_scale = max(0.25, min(4.0, float(ui_scale or 1.0)))
    if abs(resolved_scale - 1.0) < 0.01:
        return image, tuple(local_centers), tuple(slot_size)
    target_size = (
        max(1, int(round(image.width / resolved_scale))),
        max(1, int(round(image.height / resolved_scale))),
    )
    normalized_image = image.resize(target_size, Image.Resampling.BILINEAR)
    normalized_centers = tuple(
        (center_x / resolved_scale, center_y / resolved_scale)
        for center_x, center_y in local_centers
    )
    normalized_slot_size = (
        max(1, int(round(slot_size[0] / resolved_scale))),
        max(1, int(round(slot_size[1] / resolved_scale))),
    )
    return normalized_image, normalized_centers, normalized_slot_size


def detect_current_perk_slots(screenshot_path=None, *, party=False):
    slot_centers = (perk_slot_center(1), perk_slot_center(2))
    # Search in a slightly larger crop so template matching can recover from a
    # small manual calibration offset. Click coordinates stay unchanged.
    slot_size = perk_slot_search_size(party=party)
    region = perk_detection.perk_slots_capture_region(slot_centers, slot_size)
    image = capture_debug_screenshot(screenshot_path, region=region)
    local_centers = perk_detection.centers_relative_to_region(slot_centers, region)
    image, local_centers, slot_size = normalize_perk_detection_capture(
        image,
        local_centers,
        slot_size,
        getattr(recognition, "display_scale", 1.0),
    )
    profile = getattr(recognition, "current_board_profile", None)
    threshold = (
        PERK_SUPERSIZE_TEMPLATE_THRESHOLD
        if profile == SUPERSIZE_PROFILE
        else perk_detection.PERK_TEMPLATE_THRESHOLD
    )
    return perk_detection.detect_perk_slots(
        image,
        local_centers,
        slot_size,
        threshold=threshold,
    )

def serialize_perk_slot_detection(detection):
    if detection is None:
        return None
    if hasattr(detection, "to_debug_payload"):
        return detection.to_debug_payload()
    return {
        "slot": getattr(detection, "slot_number", None),
        "perk": getattr(detection, "perk_key", PERK_UNKNOWN),
        "status": getattr(detection, "status", PERK_STATUS_UNKNOWN),
        "score": round(float(getattr(detection, "score", 0.0)), 4),
        "template": getattr(detection, "template_name", None),
    }

def _is_board_cell(value):
    return (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(isinstance(part, int) for part in value)
    )

def _require_board_cell(value, field_name):
    if not _is_board_cell(value):
        raise ValueError(f"{field_name} must be a board cell tuple")
    row, col = value
    return row, col

def _perk_target_click_points(definition, target):
    if definition.target_type == PERK_TARGET_NONE:
        return []
    if definition.target_type == PERK_TARGET_TILE:
        return [board_cell_center(_require_board_cell(target, "target"))]
    if definition.target_type == PERK_TARGET_COLUMN:
        if not isinstance(target, int):
            raise ValueError("column target must be an integer column index")
        if target < 0 or target >= recognition.board_length:
            raise ValueError("column target is outside the board")
        return [board_cell_center((recognition.board_length // 2, target))]
    if definition.target_type == PERK_TARGET_TWO_TILES:
        if (
            not isinstance(target, (tuple, list))
            or len(target) != 2
            or not _is_board_cell(target[0])
            or not _is_board_cell(target[1])
        ):
            raise ValueError("two tile targets are required")
        return [board_cell_center(target[0]), board_cell_center(target[1])]
    raise ValueError(f"Unsupported perk target type: {definition.target_type}")

def activate_perk_action(
    perk_key,
    slot_number,
    target=None,
    return_position=None,
    prompt_delay=PERK_PROMPT_DELAY_SECONDS,
    animation_delay=PERK_ANIMATION_DELAY_SECONDS,
):
    if perk_key in (None, PERK_NONE):
        return False
    if perk_key not in PERK_DEFINITIONS:
        raise ValueError(f"Unknown perk: {perk_key}")

    definition = PERK_DEFINITIONS[perk_key]
    perk_x, perk_y = perk_slot_center(slot_number)
    target_points = _perk_target_click_points(definition, target)

    if return_position is None:
        return_position = pyautogui.position()

    game_click(perk_x, perk_y)
    if target_points:
        time.sleep(prompt_delay)
        for index, (target_x, target_y) in enumerate(target_points):
            game_click(target_x, target_y)
            if index < len(target_points) - 1:
                time.sleep(prompt_delay)
    time.sleep(animation_delay)
    pyautogui.moveTo(return_position[0], return_position[1])
    return True

def find_selected_perk_slot(selected_perks, perk_key):
    for index, selected in enumerate(selected_perks, start=1):
        if selected == perk_key:
            return index
    return None

def _bind_perk_action_slot(action, slot_number):
    dataclass_fields = getattr(action, "__dataclass_fields__", {})
    if "slot_number" in dataclass_fields:
        return replace(action, slot_number=slot_number)
    bound_action = copy.copy(action)
    setattr(bound_action, "slot_number", slot_number)
    return bound_action

def rank_selected_perk_actions(board, special_board, selected_perks, **ranking_options):
    # A caller may rank only one forced slot while still exposing the other
    # equipped perk to combo planning (for example Create Lightning ->
    # Detonator).  Ordinary Auto calls do not pass an override and keep the
    # historical behaviour of deriving the complete set from selected_perks.
    ranking_options.setdefault(
        "all_available_perks",
        tuple(perk for perk in selected_perks if perk in PERK_DEFINITIONS),
    )
    actions = []
    for slot_number, perk_key in enumerate(selected_perks, start=1):
        if perk_key in (None, PERK_NONE) or perk_key not in PERK_DEFINITIONS:
            continue
        slot_actions = rank_perk_actions(
            board,
            special_board,
            [perk_key],
            **ranking_options,
        )
        actions.extend(
            _bind_perk_action_slot(action, slot_number)
            for action in slot_actions
        )
    if not ranking_options.get("force_use") and not ranking_options.get("last_chance"):
        kept = remove_cross_last_resort(actions)
        diagnostics = ranking_options.get("diagnostics")
        if len(kept) != len(actions) and diagnostics is not None:
            diagnostics.setdefault(PERK_REMOVE_CROSS, "remove_cross_last_resort")
        actions = kept
    return sorted(
        actions,
        key=lambda item: perk_value_priority_key(
            item,
            ranking_options.get("decision_context"),
            ranking_options.get("mode", "None"),
            ranking_options.get("score_rally_values"),
        ),
        reverse=True,
    )


PERK_HANDOVER_AUDIT_LOG = os.path.join("Debug", "perk_handover_audit.jsonl")


def final_handover_perk_audit(
    *,
    turn_state,
    strategy_context,
    played_evaluation,
    selected_perks,
    perk_slot_status=None,
    perk_slot_reasons=None,
):
    """The perks still unused as the swipe hands over the last versus turn.

    None unless this swipe ends our final versus turn: final round, one move
    left and no guaranteed same-move extra. "Confirmed available" is the
    source's own slot view when it has one (memory: equipped and not spent),
    else the request's selected_perks.
    """
    context = strategy_context_or_unknown(strategy_context)
    if not context.is_versus_2 or turn_state is None or not turn_state.is_final_round:
        return None
    if turn_state.remaining_moves is None or turn_state.remaining_moves > 1:
        return None
    if played_evaluation is not None and has_reliable_same_move_extra(played_evaluation):
        return None
    reasons = {
        int(entry.get("slot")): entry.get("reason")
        for entry in (perk_slot_reasons or ())
        if isinstance(entry, dict) and entry.get("slot") is not None
    }
    slots = []
    if perk_slot_status:
        for entry in perk_slot_status:
            if not isinstance(entry, dict) or entry.get("slot") is None:
                continue
            slot_number = int(entry["slot"])
            slots.append({
                "slot": slot_number,
                "perk": entry.get("perk"),
                "available": bool(entry.get("available")),
                "source": entry.get("source") or "memory",
                "source_reason": entry.get("reason"),
                "decision_reason": reasons.get(slot_number),
            })
    else:
        for slot_number, perk_key in enumerate(selected_perks or (), start=1):
            slots.append({
                "slot": slot_number,
                "perk": perk_key,
                "available": perk_key in PERK_DEFINITIONS,
                "source": "selected_perks",
                "source_reason": None,
                "decision_reason": reasons.get(slot_number),
            })
    unused = [slot for slot in slots if slot["available"]]
    return {
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "time_left_seconds": turn_state.time_left_seconds,
        "current_round": turn_state.current_round,
        "total_rounds": turn_state.total_rounds,
        "unused_confirmed": len(unused),
        "slots": slots,
    }


def record_final_handover_perk_audit(
    *,
    mode=None,
    debug_run_dir=None,
    log_path=None,
    **audit_kwargs,
):
    """Append the final-handover perk audit (see final_handover_perk_audit).

    One line per swipe that hands over the last versus turn, so
    tools/perk_handover_report.py can count how often a confirmed available
    perk was left unused.
    """
    audit = final_handover_perk_audit(**audit_kwargs)
    if audit is None:
        return None
    audit["mode"] = getattr(mode, "value", None) or str(mode)
    if debug_run_dir is not None:
        audit["run"] = Path(debug_run_dir).name
        (Path(debug_run_dir) / "perk_handover_audit.json").write_text(
            json.dumps(audit, indent=2), encoding="utf-8"
        )
    path = Path(log_path or PERK_HANDOVER_AUDIT_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit) + "\n")
    return audit


@dataclass
class AutoPerkDecision:
    """Generation and activation of one Auto perk decision, kept apart.

    ``candidates`` are the legal targets the ranking produced; the activation
    gate and the reserve then decide. ``slot_reasons`` says per slot why no
    perk was chosen (or "selected"), for the debug record.
    """

    selected: object | None = None
    gate: str | None = None
    best_rejected: object | None = None
    candidates: list = field(default_factory=list)
    slot_reasons: list = field(default_factory=list)
    last_chance: bool = False
    last_chance_reason: str = ""

    def as_debug(self) -> dict:
        def describe(action):
            if action is None:
                return None
            follow_up = getattr(action, "follow_up", None)
            return {
                "perk": action.perk_key,
                "slot_number": getattr(action, "slot_number", None),
                "target": action.target,
                "net_gain": round(float(action.net_gain), 3),
                "horizon_value": round(float(action.horizon_value), 3),
                "reason": action.reason,
                "follow_up": (
                    [list(follow_up.candidate.start), list(follow_up.candidate.target)]
                    if follow_up is not None else None
                ),
            }

        return {
            "action": "activate_perk" if self.selected is not None else "move",
            "gate": self.gate,
            "selected": describe(self.selected),
            "best_rejected": describe(self.best_rejected),
            "candidate_count": len(self.candidates),
            "last_chance": {"active": self.last_chance, "reason": self.last_chance_reason},
            "slot_reasons": list(self.slot_reasons),
        }


def _drop_floor_lava_effect_losses(candidates, normal_baseline, mode, diagnostics=None):
    """Floor Is Lava: keep a perk off a swipe whose eruption it would cost.

    The charge scale prices the erupted column's blue but not its points, and
    on the last versus handover points are what is left. A target whose
    follow-up erupts fewer columns than the swipe it replaces stays only when
    its own points plus the follow-up's make up for the swipe's points.
    """
    if normalize_game_mode(mode) is not GameMode.FLOOR_IS_LAVA or normal_baseline is None:
        return candidates
    baseline_erupted = len(getattr(normal_baseline, "floor_lava_destroyed_columns", ()) or ())
    if baseline_erupted == 0:
        return candidates

    def points(evaluation):
        if evaluation is None:
            return 0.0
        return max(0.0, float(evaluation.instant_score)) + max(0.0, float(evaluation.mode_bonus))

    baseline_points = points(normal_baseline)
    kept = []
    for action in candidates:
        follow_up = getattr(action, "follow_up", None)
        erupted = len(getattr(follow_up, "floor_lava_destroyed_columns", ()) or ())
        perk_points = (
            max(0.0, float(action.immediate_points))
            + max(0.0, float(action.mode_value))
            + points(follow_up)
        )
        if (erupted < baseline_erupted and perk_points < baseline_points
                and not getattr(action, "goal_finish", False)):
            continue
        kept.append(action)
    if diagnostics is not None:
        for action in candidates:
            if action not in kept and not any(
                other.perk_key == action.perk_key for other in kept
            ):
                diagnostics.setdefault(action.perk_key, "floor_lava_effect_lost")
    return kept


def _perk_slot_reason_entry(slot_number, perk_key, reason, slot_status=None):
    entry = {"slot": slot_number, "perk": perk_key, "reason": reason}
    if slot_status:
        entry["source_status"] = slot_status
    return entry


def solo_perk_last_chance(turn, normal_baseline=None):
    """(active, reason): the Solo Challenge's last swipe, after which a perk is wasted.

    A reliable same-move extra keeps the match going, so the window waits for
    the swipe that really ends it, as on the final versus round.
    """
    if turn is None or turn.remaining_moves is None:
        return False, "remaining_moves_unknown"
    if normal_baseline is not None and has_reliable_same_move_extra(normal_baseline):
        return False, "direct_guaranteed_extra"
    if int(turn.remaining_moves) <= 1:
        return True, "last_move"
    return False, f"moves_left={int(turn.remaining_moves)}"


def decide_auto_perk(
    board,
    special_board,
    selected_perks,
    *,
    normal_baseline,
    decision_context,
    strategy_context,
    perk_slot_status=None,
    blocked_reason=None,
    teleport_exact_pair=None,
    **ranking_options,
):
    """Rank the selected perk slots and decide whether one fires now.

    Solo Challenge (offline, 152 recorded boards, 2026-11-09): the Teleport
    goes on the first move it can, on ``teleport_exact_pair`` when the exact
    refill chose one; on the last move every unused perk goes.

    ``perk_slot_status`` is the source's own per-slot view (memory GUI), so a
    slot the request masked to PERK_NONE still reports why. ``blocked_reason``
    is set when the caller's gates kept the ranking from running at all.
    """
    turn = decision_context.turn
    valid = [perk for perk in selected_perks if perk in PERK_DEFINITIONS]
    last_chance, last_chance_reason = versus_perk_last_chance(
        turn, strategy_context, len(valid), normal_baseline
    )
    solo = strategy_context_or_unknown(strategy_context).is_solo_challenge
    goal = solo_points_goal(strategy_context, ranking_options.get("mode", "None"))
    goal_active = goal is not None and not goal.complete
    if goal_active:
        decision_context = replace(decision_context, objective=PerkObjective.SOLO_GOAL, blue_plan=None)
    if solo and not last_chance:
        last_chance, last_chance_reason = solo_perk_last_chance(turn, normal_baseline)
    last_move = last_chance and last_chance_reason == "last_move"
    ready_booster = bool(ranking_options.get("booster_active"))
    if goal_active and last_move and ready_booster:
        ranking_options["booster_active"] = False
    decision = AutoPerkDecision(
        last_chance=last_chance, last_chance_reason=last_chance_reason
    )
    status_by_slot = {
        int(entry.get("slot")): entry
        for entry in (perk_slot_status or ())
        if isinstance(entry, dict) and entry.get("slot") is not None
    }
    time_left = turn.time_left_seconds if turn is not None else None
    low_time = (
        last_chance
        and time_left is not None
        and float(time_left) <= VERSUS_PERK_MIN_TURN_SECONDS
    )
    diagnostics: dict[str, str] = {}
    if valid and blocked_reason is None and not low_time:
        decision.candidates = rank_selected_perk_actions(
            board,
            special_board,
            selected_perks,
            normal_baseline=normal_baseline,
            decision_context=decision_context,
            strategy_context=strategy_context,
            last_chance=last_chance,
            diagnostics=diagnostics,
            **ranking_options,
        )
    if last_chance and decision.candidates:
        decision.candidates = _drop_floor_lava_effect_losses(
            decision.candidates,
            normal_baseline,
            ranking_options.get("mode", "None"),
            diagnostics,
        )
    if goal_active and ready_booster:
        decision.candidates = [item for item in decision.candidates if item.goal_finish]
    rejection_reason = None
    if decision.candidates:
        best = decision.candidates[0]
        should_activate, _margin, gate = perk_activation_decision(
            best,
            normal_baseline,
            decision_context,
            strategy_context,
            last_chance=last_chance,
            last_move=last_move,
        )
        reserve = should_reserve_last_perk(
            valid, best, decision_context, strategy_context, last_chance=last_chance
        )
        if last_chance and len(valid) > 1 and not (goal_active and best.goal_finish):
            # A perk that plays the swipe itself (Energy Boost) ends the turn
            # when it fires on the last move, so the other unused perk goes
            # first if it is worth firing at all. Decided by the perk's own
            # definition, never by slot order.
            def plays_swipe(action):
                definition = PERK_DEFINITIONS.get(action.perk_key)
                return bool(definition and definition.requires_next_move)

            slot_bests = {}
            for action in decision.candidates:
                slot_bests.setdefault(getattr(action, "slot_number", None), action)
            for action in sorted(slot_bests.values(), key=plays_swipe):
                fires, _action_margin, action_gate = perk_activation_decision(
                    action,
                    normal_baseline,
                    decision_context,
                    strategy_context,
                    last_chance=last_chance,
                    last_move=last_move,
                )
                if fires:
                    if action is not best:
                        action_gate = f"{action_gate}+swipe_perk_last"
                    best, should_activate, gate, reserve = action, True, action_gate, False
                    break
        if should_activate and not reserve:
            decision.selected = best
            decision.gate = gate
        elif reserve:
            rejection_reason = "reserved_for_later"
            decision.best_rejected = replace(
                best,
                defer_until_later=True,
                reason="Cuvam poslednji slabiji perk za jaci kasniji prozor.",
                explanation=f"{best.explanation}, perk_reserved_for_later=1",
            )
        else:
            baseline_value = float(best.horizon_value) - float(best.net_gain)
            rejection_reason = (
                f"swipe_first: perk+nastavak={float(best.horizon_value):.1f} "
                f"< swipe={baseline_value:.1f} ({gate})"
            )
            decision.best_rejected = replace(
                best,
                reason=(
                    "Obican swipe ostaje prvi izbor: perk i nastavak "
                    f"{float(best.horizon_value):.1f} protiv {baseline_value:.1f} "
                    "bez perka."
                    if last_chance
                    else "Perk se cuva jer ne popravlja konzervativni horizont."
                ),
                explanation=f"{best.explanation}, activation_gate={gate}",
            )
    if solo and not goal_active and decision.candidates and (
            decision.selected is None or decision.selected.perk_key != PERK_TELEPORT):
        teleport = next((action for action in decision.candidates
                         if action.perk_key == PERK_TELEPORT and action.legal), None)
        if teleport is not None:
            if teleport_exact_pair is not None:
                first, second = teleport_exact_pair
                teleport = replace(
                    teleport, target=[list(first), list(second)],
                    reason="Solo: Teleport odmah, par iz tacnog plana do kraja meca.",
                    explanation=f"{teleport.explanation}, solo_teleport_exact_pair=1")
            else:
                teleport = replace(
                    teleport, reason="Solo: Teleport odmah (istrazivanje: prvi potez je najbolji).",
                    explanation=f"{teleport.explanation}, solo_teleport_first=1")
            decision.selected, decision.gate = teleport, "solo_teleport_first_gate"
            decision.best_rejected = None
            rejection_reason = None
    for slot_number, perk_key in enumerate(selected_perks, start=1):
        slot_status = status_by_slot.get(slot_number)
        if perk_key not in PERK_DEFINITIONS:
            source_reason = (slot_status or {}).get("reason")
            reason = (
                f"slot_unavailable:{source_reason}" if source_reason else "slot_unavailable"
            )
            decision.slot_reasons.append(
                _perk_slot_reason_entry(
                    slot_number,
                    (slot_status or {}).get("perk") or perk_key,
                    reason,
                    slot_status,
                )
            )
            continue
        if decision.selected is not None and getattr(
            decision.selected, "slot_number", None
        ) == slot_number:
            reason = "selected"
        elif blocked_reason is not None:
            reason = blocked_reason
        elif low_time:
            reason = f"low_turn_time:{float(time_left):.1f}s"
        elif any(
            getattr(action, "slot_number", None) == slot_number
            for action in decision.candidates
        ):
            if decision.selected is not None:
                reason = "other_slot_first"
            else:
                reason = rejection_reason or "not_best"
        else:
            reason = diagnostics.get(perk_key, "no_candidate")
        decision.slot_reasons.append(
            _perk_slot_reason_entry(slot_number, perk_key, reason, slot_status)
        )
    return decision

def _froggy_checkerboard_action(
    board,
    special_board,
    selected_perks,
    normal_baseline,
    booster_state,
    turn_state,
    strategy_context,
    **ranking_options,
):
    """The Checkerboard activation for `froggy_checkerboard_gate`, or None.

    Forced the same way a manual perk click is: the decision to throw it was
    made by the tracker (fresh lotuses from an activation after the clock
    armed), not by the ranking, which prices the repaint without knowing a
    lotus will collect it.
    """
    forced_selected_perks = tuple(
        perk_key if perk_key == PERK_CHECKERBOARD else PERK_NONE
        for perk_key in selected_perks
    )
    if PERK_CHECKERBOARD not in forced_selected_perks:
        return None
    decision_context = PerkDecisionContext(
        booster=booster_state,
        turn=turn_state,
        blue_plan=None,
        objective=PerkObjective.BEST_MOVE,
    )
    actions = rank_selected_perk_actions(
        board,
        special_board,
        forced_selected_perks,
        normal_baseline=normal_baseline,
        decision_context=decision_context,
        booster_active=False,
        strategy_context=strategy_context,
        force_use=True,
        all_available_perks=tuple(
            perk_key for perk_key in selected_perks if perk_key in PERK_DEFINITIONS
        ),
        **ranking_options,
    )
    if not actions:
        return None
    return replace(
        actions[0],
        reason=(
            "Checkerboard posle aktivacije boostera u poslednjih 20 s: pola table "
            "postaje jedna boja i lotus je celu pokupi."
        ),
        explanation=f"{actions[0].explanation}, froggy_checkerboard_armed_activation=1",
    )


def resolve_perk_action_slot(action, selected_perks):
    slot_number = getattr(action, "slot_number", None)
    if slot_number is not None:
        if (
            isinstance(slot_number, int)
            and 1 <= slot_number <= len(selected_perks)
            and selected_perks[slot_number - 1] == action.perk_key
        ):
            return slot_number
        return None
    return find_selected_perk_slot(selected_perks, action.perk_key)

def _capture_perk_execution_frame(
    slot_number,
    screenshot_path=None,
    board_provider=None,
    suppress_memory_perk_used=False,
):
    if board_provider is not None:
        # Memory path: the agent hands over the exact board in milliseconds.
        # Screen scanning here cost ~1 s per verification frame and up to eight
        # of them run per perk, which is where the perk "hang" came from. The
        # slot strip is skipped for the same reason -- a changed board already
        # confirms the effect. The provider may return a third element: the
        # engine's own PlayerModel.isBoardAbilityUsedThisMove. Without it every
        # memory frame reported "unknown" and Energy Boost -- whose success
        # test is board_changed AND perk_used -- could never verify from
        # memory: run 2026-08-21 17-06-38 had the swipe landing on all eight
        # attempts and still reported effect_not_confirmed, because the slot
        # strip is the only other source of "used" and it never shows an armed
        # Energy Boost as spent.
        board = special_board = None
        perk_used = None
        try:
            frame = board_provider()
            if frame is not None:
                if len(frame) >= 3:
                    board, special_board, perk_used = frame[0], frame[1], frame[2]
                else:
                    board, special_board = frame
        except Exception:
            board = special_board = None
            perk_used = None
        board_valid = bool(board) and board_scan_block_reason(board) is None
        return PerkExecutionFrame(
            signature=(
                auto_board_signature(board, special_board) if board_valid else None
            ),
            perk_status=(
                PERK_STATUS_USED
                if perk_used and not suppress_memory_perk_used
                else PERK_STATUS_UNKNOWN
            ),
            board_valid=board_valid,
            board=board,
            special_board=special_board,
        )
    board = create_board()
    special_board = create_board()
    try:
        board, special_board = update_board_2(
            board,
            special_board,
            screenshot_path=screenshot_path,
            write_screenshot=bool(screenshot_path),
        )
        board_valid = board_scan_block_reason(board) is None
    except Exception:
        board_valid = False
    perk_status = PERK_STATUS_UNKNOWN
    try:
        detections = detect_current_perk_slots(party=getattr(recognition, "party", False))
        if 1 <= slot_number <= len(detections):
            perk_status = detections[slot_number - 1].status
    except Exception:
        pass
    return PerkExecutionFrame(
        signature=auto_board_signature(board, special_board) if board_valid else None,
        perk_status=perk_status,
        board_valid=board_valid,
        board=board,
        special_board=special_board,
    )


def _write_perk_execution_debug(debug_run_dir, action, result):
    if debug_run_dir is None:
        return
    path = Path(debug_run_dir) / "perk_execution.json"
    path.write_text(
        json.dumps(
            {
                "perk": action.perk_key,
                "slot": getattr(action, "slot_number", None),
                "target": _serialize_perk_target(action.target),
                "expected": serialize_perk_action(action),
                "success": result.success,
                "reason": result.reason,
                "retried": result.retried,
                "board_changed": result.board_changed,
                "follow_up_recalculated": result.follow_up_recalculated,
                "stages": result.stages,
            },
            indent=2,
            default=_debug_json_default,
        ),
        encoding="utf-8",
    )


def execute_verified_perk_action(
    action,
    selected_perks,
    *,
    before_board,
    before_special_board,
    return_position=None,
    debug_run_dir=None,
    mode="None",
    allow_square_matches=False,
    score_rally_values=None,
    explode_created_specials_immediately=False,
    board_frame_provider=None,
    rules_context=None,
    strategy_context=None,
    turn_state=None,
):
    slot = resolve_perk_action_slot(action, selected_perks)
    if slot is None:
        return False
    definition = PERK_DEFINITIONS[action.perk_key]
    target_points = _perk_target_click_points(definition, action.target)
    if return_position is None:
        return_position = pyautogui.position()
    before_frame = PerkExecutionFrame(
        signature=auto_board_signature(before_board, before_special_board),
        perk_status=PERK_STATUS_AVAILABLE,
        board_valid=True,
        board=before_board,
        special_board=before_special_board,
    )
    verify_path = (
        str(Path(debug_run_dir) / "perk_verify_board.png")
        if debug_run_dir is not None
        else None
    )

    # Memory's "a perk was consumed this move" flag may already be raised
    # before this click, when an earlier perk was spent in the same move (both
    # perk slots can legally be played in one turn). Raised beforehand it can
    # no longer distinguish this perk from the previous one, so one probe here
    # decides: if it is already up, it is masked for the whole transaction and
    # verification falls back to the board change, exactly as before the flag
    # existed (2026-08-23).
    suppress_memory_perk_used = False
    if board_frame_provider is not None:
        probe = _capture_perk_execution_frame(
            slot, None, board_provider=board_frame_provider
        )
        suppress_memory_perk_used = probe.perk_status == PERK_STATUS_USED

    def recalculate_follow_up(frame):
        if frame.board is None or frame.special_board is None or not frame.board_valid:
            return None
        # Runs after the caller's rules block has closed, so the match's rules
        # are re-entered here (rules_context); without them the re-plan
        # treated e.g. Color Crush red as an ordinary colour.
        with (rules_context() if rules_context is not None else contextlib.nullcontext()):
            candidates = rank_moves(
                frame.board,
                frame.special_board,
                mode=mode,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                lookahead_candidates=0,
                include_future_value=False,
                explode_created_specials_immediately=explode_created_specials_immediately,
                strategy_context=strategy_context,
            )
            goal = solo_points_goal(strategy_context, mode)
            if goal is not None and not goal.complete:
                candidates = prioritize_ranked_moves(
                    candidates, mode, allow_square_matches, score_rally_values,
                    explode_created_specials_immediately, turn_state=turn_state,
                    strategy_context=strategy_context,
                )
        return candidates[0] if candidates else None

    def play_follow_up(follow_up):
        follow_up_start, follow_up_direction = oriented_swipe(follow_up)
        return play_best_move_with_cursor_restore(
            follow_up_start,
            follow_up_direction,
            follow_up.score,
            return_position=return_position,
        )

    perk_x, perk_y = perk_slot_center(slot)
    result = execute_perk_flow(
        perk_key=action.perk_key,
        slot_number=slot,
        target_points=target_points,
        before_frame=before_frame,
        click_activate=lambda: game_click(perk_x, perk_y),
        click_target=lambda point: game_click(point[0], point[1]),
        capture_frame=lambda: _capture_perk_execution_frame(
            slot,
            verify_path,
            board_provider=board_frame_provider,
            suppress_memory_perk_used=suppress_memory_perk_used,
        ),
        requires_next_move=definition.requires_next_move,
        follow_up=getattr(action, "follow_up", None),
        play_follow_up=play_follow_up,
        recalculate_follow_up=recalculate_follow_up,
        sleep=time.sleep,
        prompt_delay=PERK_PROMPT_DELAY_SECONDS,
        verify_delay=PERK_VERIFY_DELAY_SECONDS,
    )
    pyautogui.moveTo(return_position[0], return_position[1])
    _safe_debug_write(_write_perk_execution_debug, debug_run_dir, action, result)
    return result.success


def write_ml_recognition_debug_payload(run_dir, payload):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / ML_RECOGNITION_DEBUG_FILENAME).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


# Step timings of the most recent play_best_move_with_cursor_restore call, so
# timings.json can attribute the execute time to the actual input calls.
# Single-threaded play path; overwritten on every call.
_last_play_step_timings = {}


def refill_input_detail(selected_action, best_evaluation=None, perk_action=None,
                        booster_mode=None) -> dict:
    """What the bot is about to play, JSON-safe, for refill-miss records.

    The refill monitor only had two resting boards per miss; on a long
    cascade the closest simulated swap is a guess and the miss cannot be
    traced. With the bot's own swipe (or perk and its target) the exact move
    can be replayed. Moves played by hand carry no detail.
    """
    detail = {"action": selected_action}
    try:
        if selected_action == "move" and best_evaluation is not None:
            candidate = oriented_swap_candidate(best_evaluation)
            detail.update(start=[int(v) for v in candidate.start],
                          target=[int(v) for v in candidate.target],
                          direction=Direction(candidate.direction).value)
        elif selected_action == "activate_perk" and perk_action is not None:
            detail["perk"] = perk_action.perk_key
            detail["perk_target"] = json.loads(json.dumps(perk_action.target, default=str))
            follow = getattr(perk_action, "follow_up", None)
            if follow is not None:
                candidate = oriented_swap_candidate(follow)
                detail["follow_up"] = {"start": [int(v) for v in candidate.start],
                                       "target": [int(v) for v in candidate.target]}
        elif selected_action == "activate_booster":
            detail["booster_mode"] = str(booster_mode)
    except Exception as exc:  # A record without the detail beats a failed move.
        detail["error"] = f"{type(exc).__name__}: {exc}"
    return detail


def exact_refill_skip_reason(selected_action, request, *, lotus=False, mixy=False) -> str:
    """Why this move's choice did not ask the exact refill, in the panel's words."""
    if selected_action == "activate_booster":
        return "ovaj potez je booster"
    if selected_action == "activate_perk":
        return "ovaj potez je perk"
    if selected_action != "move":
        return f"ovaj potez nije obican swipe ({selected_action})"
    if request.points_only:
        return "Least Points: igra se samo na poene"
    if request.solo_cross_only:
        return "igra se samo krst"
    if lotus:
        return "Froggy lotus na tabli: dopuna ne racuna vrednost lotusa"
    if mixy:
        return "Mixy kod je aktivan: dopuna ga ne zna"
    return "potez je izabran pre provere dopune"


def game_click(x, y):
    """A click in the game: a BlueStacks tap while ADB_TOUCH is on, else the mouse.

    Mixed, the swipe went in as touch and the perk/booster clicks as the mouse:
    the perk was selected but its board target never landed (2026-11-07 20:15,
    remove_cross effect_not_confirmed; every target click before the adb swipe
    had worked). One input path for the whole move.
    """
    if ADB_TOUCH is not None:
        import adb_touch
        try:
            ADB_TOUCH.tap_screen((x, y))
            return
        except adb_touch.TouchUnavailable as exc:
            print(f"adb tap: {exc}; klik misem")
        except adb_touch.TouchUncertain as exc:
            print(f"adb tap nepotvrdjen: {exc}")
            return
    pyautogui.click(x, y)


def _adb_touch_swipe(start, direction) -> bool:
    """The swipe through BlueStacks' touch device. False: play it with the mouse.

    Only a swipe that was never sent falls back to the mouse; one sent but not
    confirmed is reported as played, since a second swipe could move twice.
    """
    import adb_touch

    delta = _SWIPE_UNIT_DELTAS.get(direction)
    if delta is None:
        return False
    distance = max(1, int(round(SWIPE_DISTANCE_PX * getattr(recognition, "display_scale", 1.0))))
    end = (start[0] + delta[0] * distance, start[1] + delta[1] * distance)
    started = time.perf_counter()
    try:
        ADB_TOUCH.swipe_screen(start, end)
    except adb_touch.TouchUnavailable as exc:
        print(f"adb swipe: {exc}; swipe misem")
        _last_play_step_timings["adb_fallback"] = 1.0
        return False
    except adb_touch.TouchUncertain as exc:
        print(f"adb swipe nepotvrdjen: {exc}")
        _last_play_step_timings["adb_uncertain"] = 1.0
    _last_play_step_timings["swipe_ms"] = (time.perf_counter() - started) * 1000.0
    _last_play_step_timings["adb_touch"] = 1.0
    return True


def play_best_move_with_cursor_restore(
    start_cell,
    direction,
    score,
    return_position=None,
    return_delay=None,
):
    if return_delay is None:
        return_delay = CURSOR_RETURN_AFTER_SWIPE_DELAY_SECONDS

    # ``score`` is contextual utility, not a legality signal. Opponent handover
    # risk, charge waste and other strategic penalties may make the best (or
    # only) legal move negative. Refusing that swipe forfeits the move to the
    # timer, which is always worse than playing the selected legal candidate.

    _last_play_step_timings.clear()
    target_x, target_y = board_cell_center(start_cell)
    if ADB_TOUCH is not None and _adb_touch_swipe((target_x, target_y), direction):
        return True
    if return_position is None:
        return_position = pyautogui.position()
    _t = time.perf_counter()
    pyautogui.moveTo(target_x, target_y)
    _last_play_step_timings["move_to_cell_ms"] = (time.perf_counter() - _t) * 1000.0
    _t = time.perf_counter()
    swipe(direction)
    _last_play_step_timings["swipe_ms"] = (time.perf_counter() - _t) * 1000.0
    _t = time.perf_counter()
    time.sleep(return_delay)
    pyautogui.moveTo(return_position[0], return_position[1])
    _last_play_step_timings["cursor_return_ms"] = (time.perf_counter() - _t) * 1000.0
    return True

@dataclass(frozen=True)
class CheckBestMoveRequest:
    mode: GameMode
    special_piece_mode: str
    selected_profile: str
    allow_square_matches: bool
    specials_explode_immediately: bool
    score_rally_values: dict[int, float] | None
    selected_perks: tuple[str, str]
    # None: read the cursor right before the first click (see the execute phase).
    cursor_return_position: tuple[int, int] | None
    booster_action_mode: str = BOOSTER_ACTION_NONE
    booster_charge: int | None = None
    booster_maximum: int | None = None
    remaining_moves: int | None = None
    # Multi-round carry-over (versus) modes: total rounds in the match and the
    # current round (1-based). None for single-round modes (Showdown/Party).
    total_rounds: int | None = None
    current_round: int | None = None
    # Where current_round came from: "auto_round_tracking" (GUI advances it on
    # the versus dot refill) or "manual" (user-set spinbox). Audit-only.
    round_source: str = "manual"
    strategy_mode: str = STRATEGY_UNKNOWN
    include_future_value: bool = False
    action: str = "highest_points"
    display_label: str = "Most Points"
    extra_move_only: bool = False
    # Dedicated manual objective: maximize points while assigning zero value to
    # booster charge. It always chooses a board swipe; booster/perk gates do not
    # override the result.
    points_only: bool = False
    # "Najmanje poena": burn a move for the fewest points. Rides on the
    # points_only path (no booster, no perk, no Mixy code, no extra hunt) with
    # the ranking turned upside down and turn-keeping extras pushed last.
    # Only meaningful together with points_only=True.
    worst_move: bool = False
    # Solo Challenge "Predji zastavicu" button: play only a move sure to reach the
    # next flag, or nothing. solo_cross_report hears whether one exists on this board.
    solo_cross_only: bool = False
    solo_cross_report: object = None
    # Manual GUI action: immediately use the currently detected perk from this
    # exact slot, while still scanning the board to choose any required target.
    forced_perk_slot: int | None = None
    # Square Match Solo with the exact engine refill (square_solo_live): the
    # swap the full-game planner chose, as ((row, col), (row, col)). It is put
    # first in the ranking; booster/perk gates still run as usual.
    engine_plan_move: tuple | None = None
    pre_scanned_board: list[list[int]] | None = None
    pre_scanned_special_board: list[list[int]] | None = None
    pre_scanned_board_path: object | None = None
    lookahead_candidates: int | None = None
    lookahead_depth: int = 2
    lookahead_beam_width: int | None = LIVE_LOOKAHEAD_BEAM_WIDTH
    auto_signature: object | None = None
    debug_enabled: bool = True
    # Split off from `debug_enabled` so a match can always be recorded while the
    # expensive half stays opt-in. The JSON a run needs to audit move choice and
    # score weights (move/candidates/observed_delta/intent/state/timings) is ~34
    # KB; the images that go with it (board, recognized overlay, booster crop,
    # score crop) are ~650 KB -- twenty times the folder for evidence that only
    # matters when recognition itself is in question. False keeps the JSON and
    # drops the pixels.
    debug_images_enabled: bool = True
    activate_booster_immediately: bool = False
    # Solo (Party/Showdown) booster-rush weights charge progress among moves
    # after guaranteed extras have been taken. Ignored in versus.
    showdown_booster_rush: bool = True
    # True Solo Challenge (alone on the board with a relaxed/no turn clock), as
    # opposed to Showdown/Party/Master-League solo boards that share the solo_6
    # strategy mode but race a clock. Gates blue-hoarding policies such as
    # SOLO_DISCO_BLUE_FIRST; see StrategyContext.is_solo_challenge.
    solo_challenge: bool = False
    solo_goal_state: dict | None = None
    # GameLogic.IsSingleplayerBoard from memory. Color Crush wipes red on a solo
    # board but not on a versus one (see move_strategy.COLOR_CRUSH_INERT_COLORS).
    # None when unknown: the strategy context's solo_6 decides.
    single_player_board: bool | None = None
    # Turn clock: seconds left and the measured wall time per move, so the
    # ranking can tell a time-bound turn (Showdown/Party/Master League) from a
    # move-bound one. See TIME_BOUND_TURNS in move_strategy.
    turn_time_left: float | None = None
    seconds_per_move: float | None = None
    # GameLogic's match-wide turns left (this turn included); None = unknown.
    turns_left_in_match: int | None = None
    opponent_booster: BoosterState | None = None
    opponent_charge_colors: tuple[int, ...] = ()
    opponent_next_turn_moves: int | None = None
    color_crush: bool = False
    # Energized: the two colors (besides blue) that fill the booster meter.
    energized_colors: tuple[int, ...] = ()
    # Engine truth for which colors charge the booster this match, read from
    # MatchRulesModel via the memory reader. None = unknown (blue default).
    # When set it replaces blue+energized outright, including "no blue".
    engine_charge_colors: tuple[int, ...] | None = None
    # Energy one tile of each charging colour adds, on the BOOSTER_MAX_CHARGE
    # scale (booster_charge/maximum are scaled the same way by the GUI). None:
    # every charging tile counts one.
    engine_charge_weights: dict | None = None
    # Multiplier mushrooms: score a cleared mushroom by the number printed on
    # its cap (green +1 .. yellow +4) instead of counting it as one.
    mushroom_multipliers: bool = False
    vertical_matches_destroy_color: bool = False
    # Mutation Lab "Matches explode color" (type 25): the same whole-colour
    # wipe with the vertical condition dropped. A separate mutation from
    # vertical_matches_destroy_color, and the catalogue blocks the two against
    # each other, so they are separate switches rather than one with a mode.
    matches_destroy_color: bool = False
    # MatchRulesModel.allSpecialsLightning: every special a match creates is a
    # Lightning, whatever shape made it.
    all_specials_lightning: bool = False
    # MatchRulesModel.extraMoveEnabled; False = no 4+ match returns a move.
    # None (screen path) keeps extras on.
    extra_move_enabled: bool | None = None
    extra_move_bonus_time: float = 0.0
    # MatchRulesModel.specialComboScoreMultiplier: cells a special's blast (or
    # a merge swap) destroys score this many times. None/1 = plain scoring.
    special_combo_score_multiplier: int | None = None
    # MatchRulesModel.everyMatchIsSpecial is independent of the named board
    # mode and may be active at the same time (for example in Candy World).
    every_match_is_special: bool = False
    # (row, col) of the booster's temporary specials on the played board
    # (SlotModel.status & 1); move_strategy.ability_temp_specials_active.
    ability_temp_special_cells: tuple = ()
    # MatchRulesModel.destroyRowOnHorizontalMatch / .destroyColumnOnVerticalMatch
    # as (rows, columns). Arcade Man is the ruleset with both on; the pair is
    # kept separate so a profile that sweeps only one axis is expressible.
    line_destruction: tuple[bool, bool] = (False, False)
    screen_state_read: dict | None = None
    screen_state_image: object | None = None
    mixy_meow_state: MixyMeowState | None = None
    ufo_state: UfoState | None = None
    detected_perk_slots: object | None = None
    # The source's own per-slot perk view, independent of selected_perks:
    # ({"slot": 1, "perk": key, "available": bool, "reason": str}, ...). The
    # memory GUI fills it so a slot masked to PERK_NONE (spent, low clock,
    # unconfirmed previous perk) still reports why in the debug record.
    perk_slot_status: tuple | None = None
    # Callable returning a fresh ``(board, special_board)`` without touching the
    # screen. Only the memory path can supply one; perk verification uses it
    # instead of re-scanning pixels between clicks.
    board_frame_provider: object | None = None
    # Callable returning a *current* screen_state_read (memory path only), for
    # the pre-click booster check. screen_state_read above is the state the
    # plan was built from, and a plan can wait a long time for its board.
    fresh_screen_state_provider: object | None = None
    board_source: str = BOARD_SOURCE_ML
    ml_recognition_mode: str = ML_RECOGNITION_OFF
    force_no_booster: bool = False
    # Near the low-clock cutoff, spend a ready booster before other actions.
    # In Versus a selected guaranteed extra still goes first.
    booster_clock_deadline: bool = False
    hot_color_state: dict | None = None
    # The Floor Is Lava: the columns the engine already counts as matched once,
    # straight out of FloorIsLavaBoard.ColumnsEruptionDictionary. The memory
    # path knows this exactly, so it beats the bot's own move-by-move tally;
    # None means "no memory reading", i.e. keep using the tracked state.
    floor_lava_columns: tuple[int, ...] | None = None
    # Lights Up: LightsUpBoard.CurrentActiveColumn plus the player's current
    # ScoreMultiplier, as {"column": int, "multiplier": int}. Memory-only; None
    # leaves the mode scoring like a plain board rather than guessing a column.
    lights_up_state: dict | None = None
    # Column Mania: the live per-column CellModel.scoreMultiplier values as
    # {"multipliers": [int, ...]}. Memory-only; None leaves the mode scoring
    # like a plain board rather than guessing a ramp.
    column_mania_state: dict | None = None
    # The two PlayerModel.scoreMultiplier boards (Moves Multiplier 34,
    # Multiplier Madness 22): the player's live multiplier as
    # {"multiplier": int}. Memory-only; None scores a multiplier point at its
    # opening-move price, which is what a board at x1 is worth anyway.
    score_multiplier_state: dict | None = None
    # Color Climb (RainbowMultiplierBoard 35): the player's two multiplier
    # colours as {"colors": (int, int), "multiplier": int}, bot colour codes.
    # Memory-only; None scores the mode like a plain board rather than guessing
    # which pair the board dealt.
    color_climb_state: dict | None = None
    # PlayerModel.isAbilityUsedThisMove (plus the free-move board abilities):
    # nine board models return from their hook without applying the mode's own
    # rule when this move already spent an ability, so Floor Is Lava marks no
    # column and Vertical Rush moves no multiplier. Only the memory path can
    # know it; the screen path leaves it False, which is the old behaviour.
    # Froggy Fu's gather region as (radius, uses_chebyshev), off the booster's
    # own tuning params. None keeps the old whole-board lotus count.
    froggy_gather_region: tuple[int, bool] | None = None
    ability_used_this_move: bool = False
    # The booster half of ability_used_this_move alone. The UFO SE eye fill
    # reads only PlayerModel.isAbilityUsedThisMove, not the free-move perks.
    # None = same as ability_used_this_move (screen path, old callers).
    booster_used_this_move: bool | None = None
    # MatchRulesModel.pvpMode. The Sweep SE broom repaints a different number of
    # tiles per mode (Solo none at all), and only the memory path knows which
    # mode is running; None keeps the PvP default.
    sweep_paint_pvp_mode: int | None = None
    # The jelly's infected area straight out of BoardModel.extraData, as
    # ((row, col), ...). The overlay has no slot of its own, so the screen path
    # has to infer it from washed-out saturation; when memory names the cells
    # outright that guess -- and the board grab it needs -- is skipped. None
    # means "not read", which keeps the detector.
    jelly_zone_cells: tuple[tuple[int, int], ...] | None = None
    # Funky Tiles cells from CellModel.cellType (memory reader). None = the
    # snapshot did not carry the grid; on a memory board that reads as "none".
    funky_tile_cells: tuple[tuple[int, int], ...] | None = None
    # Vegas Views from memory: {"cells": [(row, col), ...], "multiplier": int}.
    # None = not read, and the mode then scores like a plain board.
    vegas_views_state: dict | None = None
    # The evidence behind those cells (engine points, resolved keys, the raw
    # extraData). Debug-only bookkeeping: nothing reads it, it is written to
    # move.json so a jelly match can be checked after the fact.
    jelly_debug: dict | None = None
    allow_perk_activation: bool = True
    manual_recognition_stability_enabled: bool = True
    play_enabled: bool = True
    refill_input_started: object | None = None
    # Memory Auto may plan during animation. Both callbacks are GUI-validated
    # thread-safe gates; no clicks or committed Debug records precede the wait.
    wait_for_board: object | None = None
    claim_execution: object | None = None
    planning_is_cancelled: object | None = None
    # Fast refill (outside the Solo Challenge): the move was ranked without the
    # exact refill, during the animation. Called once the board is ready, it
    # returns an ExactRefillSession for the settled board (or None), and only
    # the top FAST_EXACT_REFILL_TOP moves are checked with it.
    late_exact_refill: object | None = None
    # Called with a short reason when this move's choice skips the exact
    # refill (booster, perk, lotus, Least Points...), so the panel can say why.
    exact_refill_skip: object | None = None
    # Solo Challenge with the exact refill: the Teleport pair whose exact line
    # to the end of the match scores best (square_solo_live.teleport_exact_pair),
    # as ((r, c), (r, c)), or None for the bot's own pick.
    teleport_exact_pair: tuple | None = None


# Fast refill: how many of the bot's own top moves the settled board re-checks,
# and the most the next-board setup search may add.
FAST_EXACT_REFILL_TOP = 5
FAST_EXACT_REFILL_SETUP_SECONDS = 0.3
# Showdown / Party: with this much of the clock left the settled board checks
# every move, not just the top five. On 541 recorded solo positions that is
# +3 ms median (+16 ms p90) and picks another move in 32 (a run of extras,
# Dustville charge, a setup, blue the top five missed); only a long run of
# extras (Score Market) took up to 1.3 s, so near the end it stays at five.
FAST_EXACT_REFILL_ALL_MIN_SECONDS = 10.0


def fast_exact_refill_count(candidates: int, time_left_seconds) -> int:
    """How many of the bot's own moves the settled board checks exactly."""
    if time_left_seconds is None or time_left_seconds >= FAST_EXACT_REFILL_ALL_MIN_SECONDS:
        return candidates
    return min(candidates, FAST_EXACT_REFILL_TOP)

@dataclass(frozen=True)
class CheckBestMoveResult:
    best_move_text: str
    score_text: str
    clear_used_perk_key: str | None = None
    clear_used_perk_slot: int | None = None
    # Slot clicked this request whether or not its use was confirmed. With
    # clear_used_perk_slot None the caller must not start another perk until
    # the engine confirms the spend or the turn changes.
    perk_attempted_slot: int | None = None
    auto_signature: object | None = None
    booster_attempt: bool = False
    # How many colours the played move expects the UFO eyes to abduct. The
    # caller keeps the eye ledger (the engine only reports an activation for a
    # single frame), and both eyes can fire inside one move, so it has to be
    # told what was spent rather than assume one per move.
    ufo_abductions: int = 0
    waiting_for_board: bool = False
    # True only when this result actually sent a board swipe. Perks such as
    # Shuffle and most booster activations change the board without ending our
    # turn, so Auto must keep the already-confirmed "our turn" latch.
    turn_consumed: bool = True
    planning_cancelled: bool = False


def count_ufo_abductions(evaluation) -> int:
    """Colours the simulated move hands to the UFO eyes."""
    total = 0
    for event in getattr(evaluation, "intent_events", None) or ():
        if event.get("type") == UFO_ABDUCTION_EVENT:
            total += len(event.get("colors") or ())
    return total


def _recognition_attempt_summary(diag: dict) -> dict:
    summary = {}
    for key, value in diag.items():
        if key == "ml_debug_payload":
            continue
        if isinstance(value, bool) or value is None or isinstance(value, str):
            summary[key] = value
        elif isinstance(value, (int, float)):
            summary[key] = round(value, 1)
        else:
            summary[key] = value
    return summary


def _is_ml_only_recognition_block(ml_mode, ml_debug_payload) -> bool:
    """True when ML 'only' mode threw the whole board away (no template
    fallback), so the failure leaves no other trace to inspect."""
    if normalize_ml_recognition_mode(ml_mode) != ML_RECOGNITION_ONLY:
        return False
    if not isinstance(ml_debug_payload, dict):
        return False
    return bool(ml_debug_payload.get("summary", {}).get("blocked"))


def _resolve_ml_block_board_image(request):
    """Best available in-memory copy of the frame that failed ML recognition."""
    if request.pre_scanned_board_path is not None:
        image = capture.get_latest_debug_screenshot(request.pre_scanned_board_path)
        if image is not None:
            return image
    return capture.get_latest_debug_screenshot(ML_BLOCK_LATEST_BOARD_KEY)


def promote_engine_plan_move(evaluations, planned):
    """Put the planner's swap first; unchanged when it is not among them.

    A swap is the same move from either end, so the cell pair is compared
    without order.
    """
    wanted = {tuple(planned[0]), tuple(planned[1])}
    for index, evaluation in enumerate(evaluations):
        candidate = evaluation.candidate
        if {tuple(candidate.start), tuple(candidate.target)} == wanted:
            return [evaluation] + evaluations[:index] + evaluations[index + 1:]
    return evaluations


def run_free_swap_request(request: CheckBestMoveRequest, swap, note: str = "") -> CheckBestMoveResult:
    """Swap Freely: swipe one free (non-matching) swap; no move is spent.

    The board was already planned by free_swap.plan_free_swaps, so nothing is
    evaluated here: wait for the board like a normal move, swipe, and report
    that the turn goes on (turn_consumed=False keeps Auto on our turn).
    """
    from free_swap import swap_direction

    if request.wait_for_board is not None:
        if not request.wait_for_board():
            return CheckBestMoveResult(
                best_move_text="Auto: board changed, recomputing",
                score_text="", turn_consumed=False, planning_cancelled=True,
            )
        if request.claim_execution is None or not request.claim_execution():
            return CheckBestMoveResult(
                best_move_text="Auto: recomputing new board", score_text="",
                turn_consumed=False, planning_cancelled=True,
            )
    apply_board_profile(request.selected_profile)
    start, target = tuple(swap[0]), tuple(swap[1])
    direction = swap_direction(start, target)
    return_position = request.cursor_return_position
    if return_position is None:
        return_position = tuple(pyautogui.position())
    play_best_move_with_cursor_restore(start, direction, 0.0, return_position=return_position)
    return CheckBestMoveResult(
        best_move_text=f"Slobodna zamena: {start} {direction.value}",
        score_text=note or "Score: bez poteza",
        auto_signature=request.auto_signature,
        turn_consumed=False,
    )


def run_check_best_move_request(request: CheckBestMoveRequest) -> CheckBestMoveResult:
    previous_ml_recognition_mode = recognition.ml_recognition_mode
    recognition.set_ml_recognition_mode(request.ml_recognition_mode)
    try:
        with planning_cancellation(request.planning_is_cancelled):
            return _run_check_best_move_request(request)
    except PlanningCancelled:
        return CheckBestMoveResult(
            best_move_text="Auto: racunam novu tablu", score_text="",
            turn_consumed=False, planning_cancelled=True,
        )
    finally:
        recognition.set_ml_recognition_mode(previous_ml_recognition_mode)


def _run_check_best_move_request(request: CheckBestMoveRequest) -> CheckBestMoveResult:
    learned_value.begin_decision()
    if (request.pre_scanned_board is None) != (request.pre_scanned_special_board is None):
        raise ValueError("pre_scanned_board and pre_scanned_special_board must be provided together")

    phase_start = time.perf_counter()
    recognition_ms = 0.0
    compute_ms = 0.0
    debug_ms = 0.0
    planning_wait_ms = 0.0
    _recognition_breakdown = {}
    _t_setup = time.perf_counter()

    cursor_return_position = request.cursor_return_position
    recognition.curr_mode = normalize_game_mode(request.mode)
    if recognition.curr_mode is GameMode.INFINITE_MOVES:
        # Infinite Moves is timed rather than move-limited. Never let a stale
        # GUI spin-box or a generic dot read turn it into a "final move" and cap
        # lookahead/booster decisions. Keep the raw screen-state payload only as
        # diagnostics; strategy deliberately receives an unbounded horizon.
        request = replace(
            request,
            remaining_moves=None,
            total_rounds=None,
            current_round=None,
            round_source="infinite_moves",
        )
    recognition.special_piece_mode = normalize_special_piece_mode(request.special_piece_mode)
    selected_profile = request.selected_profile
    allow_square_matches = request.allow_square_matches
    specials_explode_immediately = request.specials_explode_immediately
    color_crush = request.color_crush or recognition.curr_mode is COLOR_CRUSH_MODE
    # The Energized colors are a match-level modifier the GUI supplies; they are
    # honoured whenever they are set, and are the whole point of the mode entry.
    energized_colors = normalize_energized_colors(request.energized_colors)
    vertical_matches_destroy_color = request.vertical_matches_destroy_color
    matches_destroy_color = request.matches_destroy_color
    # Either source turns a rule on: the mode entry the user picked in the GUI,
    # or the engine's own rules flag the memory reader supplies.
    all_specials_lightning = bool(
        request.all_specials_lightning
    ) or mode_creates_only_lightning(recognition.curr_mode)
    every_match_is_special = bool(request.every_match_is_special)
    both_colors_charge_energy = mode_charges_both_colors(recognition.curr_mode)
    line_destruction = tuple(request.line_destruction or (False, False))
    score_rally_values = effective_score_rally_values_for_mode(
        recognition.curr_mode,
        request.score_rally_values,
        request.hot_color_state,
    )
    selected_perks = request.selected_perks
    booster_action_mode = normalize_booster_action_mode(request.booster_action_mode)
    _t_profile = time.perf_counter()
    apply_board_profile(selected_profile)
    # Split out so a slow first move of a match can be blamed precisely: this
    # is the window lookup, the calibration file and the template cache.
    _recognition_breakdown["profile_ms"] = round((time.perf_counter() - _t_profile) * 1000, 1)
    deferred_debug = request.wait_for_board is not None
    debug_enabled = request.debug_enabled and not deferred_debug
    debug_images_enabled = debug_enabled and request.debug_images_enabled
    debug_run_dir = create_debug_run_dir() if debug_enabled else None
    previous_debug_run = find_previous_debug_run(debug_run_dir) if debug_enabled else None
    debug_board_path = debug_run_dir / "board.png" if debug_images_enabled else None
    versus_score_region = score_region_from_board()
    # Mirror whatever crop the prep read resolved to. Party and Solo Challenge
    # keep our total in a pill of their own, and the versus header region then
    # lands on the "You / avatar / # rank" strip instead -- Debug/runs
    # 2026-08-15 17:44-17:46 read the party rank "# 6" as a score of 7 on every
    # move while prep had our real 1599. Because prep and fresh then never
    # agreed, the reconciler's recovery path could not overrule a tracked score
    # left over from an *earlier* match, and all 23 moves resolved to a frozen
    # 1976 -- which put the bot in "ahead" for a match it was losing.
    prep_score_region = _prep_score_region(request.screen_state_read)
    live_score_region = prep_score_region or versus_score_region
    fresh_score_is_solo_pill = (
        prep_score_region is not None and prep_score_region != versus_score_region
    )
    debug_score_region = live_score_region if debug_images_enabled else None
    _recognition_breakdown["setup_ms"] = round((time.perf_counter() - _t_setup) * 1000, 1)
    _t_score = time.perf_counter()
    debug_score_path = None
    fresh_score_image = None
    score_changed_after_prep = False
    # A memory-sourced score is exact: it comes from PlayerModel.score, not from
    # digits on screen. Re-reading the pixels could only replace a correct value
    # with a misread, so the whole OCR/reconcile path is skipped for it.
    score_state_is_from_memory = (
        isinstance(request.screen_state_read, dict)
        and (request.screen_state_read.get("score") or {}).get("source") == SCORE_SOURCE_MEMORY
    )
    if score_state_is_from_memory:
        pass
    elif debug_images_enabled:
        debug_score_path = capture_score_region(
            debug_run_dir / SCORE_REGION_FILENAME,
            debug_score_region,
        )
        if debug_score_path is not None:
            fresh_score_image = capture.get_latest_debug_screenshot(debug_score_path)
    elif request.screen_state_read is not None:
        fresh_score_image = capture_debug_screenshot(
            output_path=None,
            region=live_score_region,
            write_to_disk=False,
        )

    if request.screen_state_read is not None and not score_state_is_from_memory:
        fresh_score_read = (
            screen_state_reader.read_solo_score_region(fresh_score_image)
            if fresh_score_is_solo_pill
            else screen_state_reader.read_score_region(fresh_score_image)
        )
        score_changed_after_prep = bool(
            request.auto_signature is not None
            and auto_score_changed_after_stable_prep(
                request.screen_state_read,
                fresh_score_read,
            )
        )
        request = replace(
            request,
            screen_state_read=reconcile_and_track_screen_state_score(
                request.screen_state_read,
                fresh_score_read,
            ),
        )
    _recognition_breakdown["score_capture_ms"] = round((time.perf_counter() - _t_score) * 1000, 1)

    _ml_debug_payload = None
    _funky_tile_cells: tuple[tuple[int, int], ...] = ()
    _jelly_zone_cells: tuple[tuple[int, int], ...] = ()
    _hot_color_state = copy.deepcopy(request.hot_color_state)
    unsafe_reason = None
    # When Debug is off we still want the last scanned frame in memory so an ML
    # "only" block can be saved on demand. Pass a stable cache key (no disk
    # write) instead of the None screenshot_path the off-path used before.
    recognition_board_cache_path = debug_board_path or ML_BLOCK_LATEST_BOARD_KEY

    selected_board_source = board_source.normalize_board_source(request.board_source)
    if request.pre_scanned_board is None and selected_board_source != BOARD_SOURCE_ML:
        try:
            memory_result = board_source.load_memory_board_snapshot()
        except board_source.MemoryBoardUnavailable as exc:
            if selected_board_source == BOARD_SOURCE_MEMORY:
                raise
            _recognition_breakdown["board_source"] = {
                "selected": BOARD_SOURCE_AUTO,
                "used": BOARD_SOURCE_ML,
                "fallback_reason": str(exc),
            }
        else:
            request = replace(
                request,
                pre_scanned_board=memory_result.board,
                pre_scanned_special_board=memory_result.special_board,
            )
            _recognition_breakdown["board_source"] = {
                "selected": selected_board_source,
                "used": BOARD_SOURCE_MEMORY,
                "warnings": list(memory_result.warnings),
            }
    elif request.pre_scanned_board is None:
        _recognition_breakdown["board_source"] = {
            "selected": BOARD_SOURCE_ML,
            "used": BOARD_SOURCE_ML,
        }

    if request.pre_scanned_board is not None:
        game_board = copy.deepcopy(request.pre_scanned_board)
        special_game_board = copy.deepcopy(request.pre_scanned_special_board)
        source_board_path = (
            Path(request.pre_scanned_board_path)
            if request.pre_scanned_board_path is not None
            else None
        )
        cached_image = (
            capture.get_latest_debug_screenshot(source_board_path)
            if source_board_path is not None
            else None
        )
        if cached_image is None and source_board_path is not None:
            try:
                with Image.open(source_board_path) as source_image:
                    cached_image = source_image.convert("RGB")
            except (FileNotFoundError, OSError):
                cached_image = None
        # Memory names the infected cells exactly (JellySE keeps them in
        # BoardModel.extraData), so the pixel detector -- and, when nothing else
        # on this path needs a picture, the board grab itself -- is skipped.
        # On a memory board the jelly zone comes from memory or not at all: a
        # request that does not name it means "no zone", never "go and look at
        # the pixels" (2026-09-18: the saturation detector painted a six-cell
        # zone over a perk effect in a match with no jelly and held the booster).
        _memory_jelly_cells = request.jelly_zone_cells or ()
        # The only thing left on this path that wants a picture is the debug
        # record ("Debug zapis"); no detector runs on a memory board.
        needs_picture = debug_images_enabled
        if cached_image is None and needs_picture:
            cached_image = _board_region_screenshot()
        # Funky Tiles: the marked cells are CellModel.cellType == Funky in the
        # engine, sent by the agent as `cell_types` (2026-09-18). A request that
        # does not carry them means "none known", never "look at the pixels".
        _funky_tile_cells = tuple(
            (int(row), int(col)) for row, col in (request.funky_tile_cells or ())
        )
        _jelly_zone_cells = tuple(
            (int(row), int(col)) for row, col in _memory_jelly_cells
        )
        if debug_images_enabled:
            debug_board_path.parent.mkdir(parents=True, exist_ok=True)
            if cached_image is not None:
                capture.remember_debug_screenshot(debug_board_path, cached_image)
                cached_image.save(debug_board_path)
            elif source_board_path is not None and source_board_path.exists():
                if source_board_path.resolve() != debug_board_path.resolve():
                    shutil.copy2(source_board_path, debug_board_path)
            else:
                capture_debug_screenshot(
                    debug_board_path,
                    region=(recognition.left, recognition.up, recognition.width, recognition.height),
                )
    elif request.manual_recognition_stability_enabled:
        _attempts_diag = []
        _retry_sleep_ms = 0.0
        _frame_samples = []
        selected_sample = None
        for attempt in range(MANUAL_RECOGNITION_MAX_FRAMES):
            game_board = create_board()
            special_game_board = create_board()
            _attempt_diag = {}
            game_board, special_game_board = update_board_2(
                game_board,
                special_game_board,
                screenshot_path=recognition_board_cache_path,
                write_screenshot=debug_images_enabled,
                _diag=_attempt_diag,
            )
            frame_sample = RecognitionFrameSample(
                index=attempt + 1,
                board=_copy_grid(game_board),
                special_board=_copy_grid(special_game_board),
                diag=dict(_attempt_diag),
                zero_count=board_zero_count(game_board),
                block_reason=board_scan_block_reason(game_board),
                image=capture.get_latest_debug_screenshot(
                    recognition_board_cache_path
                ),
            )
            attempt_summary = _recognition_attempt_summary(_attempt_diag)
            attempt_summary["index"] = frame_sample.index
            attempt_summary["zero_count"] = frame_sample.zero_count
            attempt_summary["block_reason"] = frame_sample.block_reason
            _attempts_diag.append(attempt_summary)
            _frame_samples.append(frame_sample)

            selected_sample = _select_majority_recognition_sample(_frame_samples)
            if selected_sample is not None:
                break

            if attempt < MANUAL_RECOGNITION_MAX_FRAMES - 1:
                # The flat sleep is a proxy for "let the animation move on" so
                # the next frame cannot repeat this frame's artefact. Poll for
                # that condition instead of assuming it takes 100ms: a settled
                # board clears in ~15ms, an animating one still waits the full
                # budget. Screen grabs are ~6ms, recognition is ~29ms, so
                # polling grabs is far cheaper than polling frames.
                _retry_sleep_ms += _wait_until_board_still(
                    frame_sample.image,
                    MANUAL_RECOGNITION_FRAME_DELAY_SECONDS,
                    board_size=len(frame_sample.board) or None,
                )

        selected_sample = _select_majority_recognition_sample(_frame_samples)
        unsafe_reason = None
        if selected_sample is not None:
            game_board = _copy_grid(selected_sample.board)
            special_game_board = _copy_grid(selected_sample.special_board)
            _ml_debug_payload = selected_sample.diag.get("ml_debug_payload")
            final_recognition_diag = selected_sample.diag
        else:
            last_sample = _frame_samples[-1]
            game_board = _copy_grid(last_sample.board)
            special_game_board = _copy_grid(last_sample.special_board)
            _ml_debug_payload = last_sample.diag.get("ml_debug_payload")
            final_recognition_diag = last_sample.diag
            unsafe_reason = _manual_recognition_unsafe_reason(_frame_samples)
        _funky_tile_cells = tuple(
            tuple(cell) for cell in final_recognition_diag.get("funky_tile_cells", ())
        )
        _jelly_zone_cells = tuple(
            tuple(cell) for cell in final_recognition_diag.get("jelly_zone_cells", ())
        )
        if recognition.curr_mode is HOT_COLOR_MODE:
            _hot_color_state = copy.deepcopy(
                final_recognition_diag.get("hot_color_state")
            )

        _recognition_breakdown["retry_count"] = len(_attempts_diag)
        _recognition_breakdown["retry_sleep_ms"] = round(_retry_sleep_ms, 1)
        _recognition_breakdown["attempts"] = _attempts_diag
        _recognition_breakdown["frame_majority"] = _frame_majority_payload(
            _frame_samples,
            selected_sample,
            unsafe_reason,
        )
    else:
        max_retries = 3
        _attempts_diag = []
        _retry_sleep_ms = 0.0
        for attempt in range(max_retries):
            game_board = create_board()
            special_game_board = create_board()
            _attempt_diag = {}
            game_board, special_game_board = update_board_2(
                game_board,
                special_game_board,
                screenshot_path=recognition_board_cache_path,
                write_screenshot=debug_images_enabled,
                _diag=_attempt_diag,
            )
            attempt_summary = _recognition_attempt_summary(_attempt_diag)
            attempt_summary["index"] = attempt + 1
            attempt_summary["zero_count"] = board_zero_count(game_board)
            attempt_summary["block_reason"] = board_scan_block_reason(game_board)
            _attempts_diag.append(attempt_summary)
            _ml_debug_payload = _attempt_diag.get("ml_debug_payload")

            if not board_has_unrecognized_cells(game_board):
                break

            if attempt < max_retries - 1:
                time.sleep(MANUAL_RECOGNITION_FRAME_DELAY_SECONDS)
                _retry_sleep_ms += MANUAL_RECOGNITION_FRAME_DELAY_SECONDS * 1000

        _funky_tile_cells = tuple(
            tuple(cell) for cell in _attempt_diag.get("funky_tile_cells", ())
        )
        _jelly_zone_cells = tuple(
            tuple(cell) for cell in _attempt_diag.get("jelly_zone_cells", ())
        )
        if recognition.curr_mode is HOT_COLOR_MODE:
            _hot_color_state = copy.deepcopy(_attempt_diag.get("hot_color_state"))

        _recognition_breakdown["retry_count"] = len(_attempts_diag)
        _recognition_breakdown["retry_sleep_ms"] = round(_retry_sleep_ms, 1)
        _recognition_breakdown["attempts"] = _attempts_diag
        _recognition_breakdown["frame_majority"] = _frame_majority_disabled_payload(
            len(_attempts_diag)
        )
    score_rally_values = effective_score_rally_values_for_mode(
        recognition.curr_mode,
        request.score_rally_values,
        _hot_color_state,
    )
    _recognition_block_reason = unsafe_reason
    if _recognition_block_reason is None:
        _recognition_block_reason = board_scan_block_reason(game_board)
    state_stability = (
        request.screen_state_read.get("state_stability")
        if isinstance(request.screen_state_read, dict)
        else None
    )
    if (
        _recognition_block_reason is None
        and request.manual_recognition_stability_enabled
        and isinstance(state_stability, dict)
        and state_stability.get("enabled") is True
        and state_stability.get("stable") is not True
    ):
        _recognition_block_reason = "state_settling"
    if _recognition_block_reason is None and score_changed_after_prep:
        _recognition_block_reason = "score_settling"
    if _recognition_block_reason is not None:
        _recognition_breakdown["blocked_reason"] = _recognition_block_reason

    recognition_ms = (time.perf_counter() - phase_start) * 1000.0

    observed_delta_path = None
    debug_phase_start = time.perf_counter()
    if previous_debug_run is not None and not score_changed_after_prep:
        flush_debug_screenshot_writes(debug_board_path)
        flush_debug_screenshot_writes(debug_score_path)
        observed_delta_path = write_observed_delta_report(
            previous_debug_run,
            debug_run_dir,
            debug_board_path,
            debug_score_path,
            game_board,
            special_game_board,
            after_score_region=debug_score_region,
        )
    debug_ms += (time.perf_counter() - debug_phase_start) * 1000.0

    if _recognition_block_reason is not None:
        # Save the blocked board even mid-play: with ML "only" there is no
        # template fallback, so recognized.png (unrecognized cells drawn in
        # red) + ml_recognition.json are the only trace of WHAT failed.
        block_debug_dir = debug_run_dir if (debug_enabled and debug_run_dir is not None) else None
        block_board_path = debug_board_path
        block_score_path = debug_score_path
        block_score_region = debug_score_region
        block_previous_run = previous_debug_run
        block_observed_delta_path = observed_delta_path
        # ML "only" discarded the whole board, so the picture is the evidence --
        # this is the one place a JSON-only run still has to write an image.
        # Two ways to get here: debug off entirely (mint a one-off run from the
        # cached frame), or the record is on with images off (the run exists,
        # only the board image is missing).
        if (
            block_debug_dir is None or block_board_path is None
        ) and _is_ml_only_recognition_block(
            request.ml_recognition_mode, _ml_debug_payload
        ):
            fallback_image = _resolve_ml_block_board_image(request)
            if fallback_image is not None:
                if block_debug_dir is None:
                    block_debug_dir = create_debug_run_dir()
                    block_score_path = None
                    block_score_region = None
                    block_previous_run = None
                    block_observed_delta_path = None
                block_debug_dir.mkdir(parents=True, exist_ok=True)
                block_board_path = block_debug_dir / "board.png"
                fallback_image.save(block_board_path)

        if block_debug_dir is not None and not score_changed_after_prep:
            debug_phase_start = time.perf_counter()
            booster_state, turn_state = resolve_strategy_states(
                request.booster_charge,
                request.remaining_moves,
                request.screen_state_read,
                total_rounds=request.total_rounds,
                current_round=request.current_round,
                booster_maximum=request.booster_maximum,
            )
            write_move_debug_report(
                block_debug_dir,
                block_board_path,
                game_board,
                special_game_board,
                None,
                [],
                mode=recognition.curr_mode,
                profile=selected_profile,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                special_piece_mode=recognition.special_piece_mode,
                booster_action_mode=booster_action_mode,
                specials_explode_immediately=specials_explode_immediately,
                color_crush=color_crush,
                energized_colors=energized_colors,
                engine_charge_colors=request.engine_charge_colors,
                mushroom_multipliers=request.mushroom_multipliers,
                vertical_matches_destroy_color=vertical_matches_destroy_color,
                matches_destroy_color=matches_destroy_color,
                all_specials_lightning=all_specials_lightning,
                every_match_is_special=every_match_is_special,
                line_destruction=line_destruction,
                include_future_value=request.include_future_value,
                action=request.action,
                selected_action="none",
                score_region_path=block_score_path,
                score_region=block_score_region,
                previous_run=block_previous_run,
                observed_delta_path=block_observed_delta_path,
                booster_charge=request.booster_charge,
                booster_maximum=request.booster_maximum,
                remaining_moves=request.remaining_moves,
                total_rounds=request.total_rounds,
                current_round=request.current_round,
                round_source=request.round_source,
                screen_state_read=request.screen_state_read,
                screen_state_image=request.screen_state_image,
                booster_state=booster_state,
                turn_state=turn_state,
                strategy_context=strategy_context_or_unknown(request.strategy_mode),
                decision_gate=f"recognition_blocked:{_recognition_block_reason}",
                play_enabled=request.play_enabled,
                ml_recognition_payload=_ml_debug_payload,
                funky_cells=_funky_tile_cells,
                jelly_cells=_jelly_zone_cells,
                jelly_state=request.jelly_debug,
                hot_color_state=_hot_color_state,
                color_climb_state=request.color_climb_state,
                floor_lava_state=floor_lava_debug_state(request.floor_lava_columns),
            )
            if _ml_debug_payload is not None:
                write_ml_recognition_debug_payload(block_debug_dir, _ml_debug_payload)
            debug_ms += (time.perf_counter() - debug_phase_start) * 1000.0
        execute_phase_start = time.perf_counter()
        execute_ms = (time.perf_counter() - execute_phase_start) * 1000.0
        total_ms = recognition_ms + compute_ms + debug_ms + execute_ms + planning_wait_ms
        if debug_enabled and debug_run_dir is not None:
            (debug_run_dir / "timings.json").write_text(
                json.dumps(
                    {
                        "recognition_ms": round(recognition_ms, 1),
                        "compute_ms": round(compute_ms, 1),
                        "debug_ms": round(debug_ms, 1),
                        "execute_ms": round(execute_ms, 1),
                        "total_ms": round(total_ms, 1),
                        "recognition_breakdown": _recognition_breakdown,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return CheckBestMoveResult(
            best_move_text=(
                (
                    f"{request.display_label}: waiting for score"
                    if _recognition_block_reason == "score_settling"
                    else (
                        f"{request.display_label}: waiting for state"
                        if _recognition_block_reason == "state_settling"
                        else f"{request.display_label}: waiting for board"
                    )
                )
                if request.play_enabled
                else f"{request.display_label}: saved"
            ),
            score_text="Score: 0" if request.play_enabled else "Score: debug",
            auto_signature=request.auto_signature,
            waiting_for_board=request.play_enabled,
            turn_consumed=False,
        )

    booster_detection = None
    high_voltage_target = None
    magic_wand_target = None
    laser_beam_target = None
    woolly_workout_target = None
    dragon_move = None
    mixy_meow_state = request.mixy_meow_state
    perk_candidates = []
    selected_perk_action = None
    best_rejected_perk = None
    perk_slot_reasons = []
    perk_last_chance_info = None
    manual_perk_failure_reason = None
    decision_context = None
    decision_gate = "unknown"
    # Full ranked move list, captured only on extra-move turns (where
    # selection_candidates is filtered to extra moves) for offline learning.
    full_ranked_candidates = None
    # What to tell the user when the Extra-move button finds no extra to play.
    extra_move_hint = None
    # ε-greedy exploration record for this decision (None until the generic move
    # gate runs; stays None for perk/booster/forced/froggy/mixy decisions).
    exploration_info = None
    booster_state, turn_state = resolve_strategy_states(
        request.booster_charge,
        request.remaining_moves,
        request.screen_state_read,
        total_rounds=request.total_rounds,
        current_round=request.current_round,
        booster_maximum=request.booster_maximum,
        turn_time_left=request.turn_time_left,
        seconds_per_move=request.seconds_per_move,
        turns_left_in_match=request.turns_left_in_match,
        opponent_booster=request.opponent_booster,
        opponent_charge_colors=request.opponent_charge_colors,
        opponent_next_turn_moves=request.opponent_next_turn_moves,
        opponent_score_multiplier=(request.score_multiplier_state or {}).get("opponent_multiplier"),
    )
    strategy_context = strategy_context_or_unknown(request.strategy_mode)
    # Ordinary strategy stops at the current turn. The explicit maximum-points
    # action may use the configured match horizon so a later round is not valued
    # as if the match ended at the current round boundary.
    if request.points_only:
        effective_lookahead_depth = clamp_points_only_lookahead_depth(
            request.lookahead_depth, turn_state
        )
    else:
        effective_lookahead_depth = clamp_lookahead_depth(
            request.lookahead_depth, turn_state
        )
    score_state = resolved_score_state(request.screen_state_read)
    runtime_match_context = build_match_context(
        strategy_mode=strategy_context.mode,
        game_mode=game_mode_value(recognition.curr_mode),
        booster="default",
        booster_action_mode=booster_action_mode,
        remaining_moves=turn_state.remaining_moves,
        moves_left_in_match=turn_state.moves_left_in_match,
        current_round=request.current_round,
        total_rounds=request.total_rounds,
        our_score=score_state["our_score"],
        opponent_score=score_state["opponent_score"],
        score_deficit=score_state["score_deficit"],
        score_confidence=score_state["confidence"],
    )
    strategy_context = replace(
        strategy_context,
        booster_rush=bool(request.showdown_booster_rush),
        solo_challenge=bool(request.solo_challenge),
        solo_goal=(SoloGoalState.from_payload(request.solo_goal_state)
                   if request.solo_challenge else None),
        score_strategy=runtime_match_context.score_strategy,
        our_score=runtime_match_context.our_score,
        opponent_score=runtime_match_context.opponent_score,
        score_deficit=runtime_match_context.score_deficit,
        expected_safe_points=runtime_match_context.expected_safe_points,
        score_confidence=runtime_match_context.score_confidence,
    )
    # Solo Challenge: the last moves search as deep as the others. A move that
    # truly has no next move still gets no future value (_phase_future_factor).
    if strategy_context.is_solo_challenge:
        effective_lookahead_depth = request.lookahead_depth
    goal = solo_points_goal(strategy_context, recognition.curr_mode)
    # The UFO abducts a whole colour off the board on the coming move, so every
    # ranking path has to simulate against that outcome -- an extra move, the
    # blue it charges and the board it leaves behind are all decided after the
    # abduction, not before it. Resolved once here rather than per gate.
    ufo_state = resolve_ufo_state(
        request, recognition, request.ufo_state, booster_action_mode
    )
    ufo_eyes = ufo_state.eyes if (ufo_state is not None and ufo_state.is_reliable) else 0
    ufo_allow_blues = (
        ufo_state.allow_blues if ufo_state is not None else UFO_ALLOW_PICKING_BLUES
    )
    booster_activation_ready = False
    compute_phase_start = time.perf_counter()
    def mode_rules():
        """This match's rules as one context, enterable more than once.

        It used to be a single inline `with (...)`, so the follow-up a perk
        re-plans after the board changed (execute_verified_perk_action, well
        after that block closed) ran with every rule off: Color Crush, charge
        colours, UFO, Lights Up, Column Mania, jelly/funky cells, hot colour,
        bounty, Floor Is Lava. An ExitStack also sidesteps CPython's static
        block nesting limit this stack was sitting at.
        """
        stack = contextlib.ExitStack()
        for manager in (
            ufo_abduction_active(ufo_eyes, ufo_allow_blues),
            color_crush_active(
                color_crush,
                single_player=(
                    strategy_context.is_solo_6
                    if request.single_player_board is None
                    else request.single_player_board
                ),
            ),
            # Energized picks plus the engine's own charge table (memory
            # reader); the engine table, when present, replaces the
            # blue+Energized model -- see engine_charge_colors_active.
            charge_colors_active(energized_colors, request.engine_charge_colors,
                                 request.engine_charge_weights),
            mushroom_multipliers_active(request.mushroom_multipliers),
            vertical_matches_destroy_color_active(vertical_matches_destroy_color),
            matches_destroy_color_active(matches_destroy_color),
            all_specials_lightning_active(all_specials_lightning),
            extra_moves_enabled_active(request.extra_move_enabled, request.extra_move_bonus_time),
            special_combo_score_multiplier_active(
                request.special_combo_score_multiplier or 1
            ),
            every_match_is_special_active(every_match_is_special),
            ability_temp_specials_active(
                game_board, special_game_board, request.ability_temp_special_cells
            ),
            both_colors_charge_energy_active(both_colors_charge_energy),
            line_destruction_active(*line_destruction),
            floor_lava_checked_columns(
                request.floor_lava_columns
                if request.floor_lava_columns is not None
                else floor_lava_state()
            ),
            ability_used_active(
                request.ability_used_this_move,
                booster_used=request.booster_used_this_move,
            ),
            sweep_paint_pvp_mode_active(request.sweep_paint_pvp_mode),
            # Lights Up prices a multiplier point by what is left to spend it
            # on, so the move count travels with the column and the multiplier.
            lights_up_state_active(
                (request.lights_up_state or {}).get("column"),
                (request.lights_up_state or {}).get("multiplier", 1),
                request.remaining_moves,
            ),
            # Column Mania prices a raised column the same way, so it also
            # needs to know how many moves are left to clear that column again.
            _multiplier_states_active(
                (request.column_mania_state or {}).get("multipliers"),
                (request.score_multiplier_state or {}).get("multiplier", 1),
                request.remaining_moves,
                (request.color_climb_state or {}).get("colors"),
                # Only the timed solo race: there `time_left_seconds` is the
                # match clock, which is what prices a multiplier point. In
                # versus it is the turn clock and the Solo Challenge is
                # limited by moves.
                match_seconds_left=(
                    turn_state.time_left_seconds
                    if strategy_context.is_solo_6
                    and not strategy_context.is_solo_challenge
                    else None
                ),
            ),
            froggy_gather_region_active(
                *(request.froggy_gather_region or (None, True))
            ),
            # Hot Color rotates its colour in onMoveEnd, so every lookahead ply
            # past this move is scored with a different one. The board model
            # names the next colour outright; two moves out it is a fresh
            # random roll and gets no hot-colour bonus at all.
            hot_color_succession_for_mode(recognition.curr_mode, _hot_color_state),
            bounty_target_value_active(bounty_state()),
            # A collected gem respawns one higher, so its price depends on how
            # many collections are still to come.
            purple_gem_state(
                special_game_board
                if recognition.curr_mode is PURPLE_GEM_MODE
                else None,
                request.remaining_moves,
            ),
            funky_tile_cells(_funky_tile_cells),
            vegas_views_cells(
                (request.vegas_views_state or {}).get("cells") or (),
                (request.vegas_views_state or {}).get("multiplier", 1),
            ),
            jelly_zone_cells(_jelly_zone_cells),
        ):
            try:
                stack.enter_context(manager)
            except BaseException:
                # As the inline `with` did: what was entered is left again.
                stack.close()
                raise
        return stack

    with mode_rules():
        if request.extra_move_only:
            if request.activate_booster_immediately:
                booster_debug_path = debug_run_dir / "booster.png" if debug_images_enabled else None
                booster_detection = resolve_booster_activation_detection(
                    booster_debug_path,
                    force_no_booster=request.force_no_booster,
                    screen_state_read=request.screen_state_read,
                    booster_action_mode=booster_action_mode,
                )
                booster_state = effective_booster_state_for_detection(
                    booster_state,
                    booster_detection,
                )
                booster_activation_ready = bool(
                    booster_detection["active"]
                )
            # Mixy converts every other code color into the matched one before
            # the swap resolves, so rank on the converted board. A ready
            # booster (only detected here with "Booster odmah" on) goes before
            # any pending code: activation re-deals a fresh code immediately
            # (measured 2026-08-26, see the main-path mixy guard), so nothing
            # is lost by activating first.
            mixy_meow_state = resolve_mixy_meow_state(
                request, recognition, mixy_meow_state
            )
            mixy_ranked = []
            # As the main branch does: the refund watch pins a failed refund on
            # the code this decision ranked on, so it must know that code.
            if mixy_meow_state is not None and mixy_meow_state.is_reliable:
                _note_mixy_current_code(mixy_meow_state)
            count_code_refund = not _mixy_refund_burned(turn_state.remaining_moves)
            if mixy_meow_state is not None and mixy_meow_state.is_reliable:
                mixy_ranked = rank_mixy_code_moves(
                    game_board,
                    special_game_board,
                    mixy_meow_state,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    lookahead_candidates=request.lookahead_candidates,
                    lookahead_depth=effective_lookahead_depth,
                    lookahead_beam_width=request.lookahead_beam_width,
                    explode_created_specials_immediately=specials_explode_immediately,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                    count_code_refund=count_code_refund,
                )
            # The Extra-move button keeps its word: a Mixy code candidate may
            # preempt the plain extra hunt only while it actually promises a
            # reliable extra. With the refund credit convicted off
            # (count_code_refund False) a code move promises nothing, and
            # playing it here burned the user's last move on a non-extra
            # (2026-08-27 21:37:58: extra=0 candidate via the old
            # mixy_before_booster_gate) -- such a board falls through to the
            # ordinary extra ranking instead.
            mixy_extra_pick = None
            mixy_pick_refund_proof = False
            if mixy_ranked:
                refund_proof = _prefer_refund_proof_mixy_extra(
                    mixy_ranked, count_code_refund
                )
                if refund_proof is not None and has_reliable_same_move_extra(
                    refund_proof
                ):
                    mixy_extra_pick = refund_proof
                    mixy_pick_refund_proof = (
                        getattr(refund_proof, "direct_extra_moves", 0)
                        > (1.0 if count_code_refund else 0.0)
                    )
            booster_now = booster_detection is not None and booster_activation_ready
            if booster_now:
                # A targeted booster needs its cell here as well: the target
                # block below belongs to the main branch, so this press used to
                # reach the click with the target still None and die on
                # `.target_cell` (AttributeError). No target -> the button
                # falls back to its extra hunt, as if the meter were not full.
                # Dragon keeps its own fallback after both branches.
                target_kwargs = dict(
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if booster_action_mode == BOOSTER_ACTION_HIGH_VOLTAGE:
                    high_voltage_target = choose_high_voltage_target(
                        game_board, special_game_board, **target_kwargs,
                        strategy_context=strategy_context,
                        turn_state=turn_state,
                    )
                    booster_now = high_voltage_target is not None
                elif booster_action_mode == BOOSTER_ACTION_MAGIC_WAND:
                    magic_wand_target = choose_magic_wand_target(
                        game_board, special_game_board, **target_kwargs,
                    )
                    booster_now = magic_wand_target is not None
                elif booster_action_mode == BOOSTER_ACTION_LASER_BEAM:
                    laser_beam_target = choose_laser_beam_target(
                        game_board, special_game_board, **target_kwargs,
                        booster_state=booster_state,
                    )
                    booster_now = laser_beam_target is not None
                elif booster_action_mode == BOOSTER_ACTION_WOOLLY_WORKOUT:
                    woolly_workout_target = choose_woolly_workout_target(
                        game_board, special_game_board, **target_kwargs,
                    )
                    booster_now = woolly_workout_target is not None
            if booster_now and mixy_extra_pick is not None:
                # Player rule (2026-09-26): a code move that keeps the turn goes
                # before the ready booster; only a code move with no extra lets
                # the booster fire first.
                ranked_moves = mixy_ranked
                selection_candidates = mixy_ranked
                selected_action = "move"
                best_evaluation = mixy_extra_pick
                decision_gate = "mixy_extra_move_gate"
            elif booster_now:
                # "Booster odmah" wins over a code move with no extra: the code
                # re-deals right after activation, so activating loses nothing.
                selection_candidates = []
                selected_action = "activate_booster"
                best_evaluation = None
                decision_gate = "booster_immediate_toggle_gate"
            elif mixy_extra_pick is not None and mixy_pick_refund_proof:
                ranked_moves = mixy_ranked
                selection_candidates = mixy_ranked
                selected_action = "move"
                best_evaluation = mixy_extra_pick
                decision_gate = "mixy_extra_move_gate"
            else:
                ranked_moves = rank_extra_move_moves(
                    game_board,
                    special_game_board,
                    recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    lookahead_candidates=request.lookahead_candidates,
                    include_future_value=request.include_future_value,
                    lookahead_depth=effective_lookahead_depth,
                    lookahead_beam_width=request.lookahead_beam_width,
                    explode_created_specials_immediately=specials_explode_immediately,
                    # Solo disco never blue: the button must not spend a blue
                    # disco swap either (SOLO_DISCO_NEVER_BLUE).
                    strategy_context=strategy_context,
                )
                selection_candidates = ranked_moves
                selected_action, best_evaluation = select_extra_move_action(
                    selection_candidates
                )
                # A refund-only Mixy promise is ~but not fully~ reliable (the
                # 2026-08-28 02:49:20 press played one and the refund never
                # landed while the plain extra hunt was never even ranked), so
                # a GENUINE board extra now outranks it. It used to be the
                # fallback when the board offered no real extra -- and that
                # fallback kept costing the last move: 2026-09-13 02:42:41 the
                # code match was credited (converted, re-dealt, meter filled)
                # and the counter still went 6 -> 5. The button promises an
                # extra or nothing, so the refund alone no longer qualifies
                # (MIXY_REFUND_ONLY_EXTRA_FALLBACK); the code move is named in
                # the hint instead, for the user to take knowingly.
                if (
                    best_evaluation is None
                    and mixy_extra_pick is not None
                    and MIXY_REFUND_ONLY_EXTRA_FALLBACK
                ):
                    ranked_moves = mixy_ranked
                    selection_candidates = mixy_ranked
                    selected_action = "move"
                    best_evaluation = mixy_extra_pick
                    decision_gate = "mixy_extra_move_gate"
                elif best_evaluation is None and mixy_extra_pick is not None:
                    decision_gate = "no_action_gate"
                    start, direction = oriented_swipe(mixy_extra_pick)
                    extra_move_hint = (
                        f"no guaranteed extra; Mixy code {tuple(start)} {direction} "
                        f"(color {getattr(mixy_extra_pick, 'mixy_code_color', '?')}) "
                        "relies on an uncertain refund -- not playing"
                    )
                elif best_evaluation is None:
                    decision_gate = "no_action_gate"
                    # Nothing on this board grants an extra, and the button will
                    # not play a plain move in its place -- that promise is the
                    # whole point of the gate. It can still end the press with
                    # something to act on: rank the plain moves once and name the
                    # best one that leaves an extra for the next move. Read-only;
                    # the caller reports it and plays nothing.
                    if full_ranked_candidates is None:
                        full_ranked_candidates = rank_moves(
                            game_board,
                            special_game_board,
                            recognition.curr_mode,
                            allow_square_matches=allow_square_matches,
                            score_rally_values=score_rally_values,
                            lookahead_candidates=request.lookahead_candidates,
                            include_future_value=request.include_future_value,
                            lookahead_depth=effective_lookahead_depth,
                            lookahead_beam_width=request.lookahead_beam_width,
                            explode_created_specials_immediately=specials_explode_immediately,
                            strategy_context=strategy_context,
                        )
                    setup = best_extra_move_setup(
                        full_ranked_candidates,
                        recognition.curr_mode,
                        allow_square_matches,
                        score_rally_values,
                        specials_explode_immediately,
                    )
                    # The label already says "Extra move", so the hint does not
                    # repeat the word.
                    if setup is not None:
                        setup_move, _next_extra = setup
                        start, direction = oriented_swipe(setup_move)
                        extra_move_hint = (
                            f"none (but {tuple(start)} {direction} sets one up "
                            "for the next move)"
                        )
                    elif full_ranked_candidates:
                        best_plain = full_ranked_candidates[0]
                        start, direction = oriented_swipe(best_plain)
                        extra_move_hint = (
                            f"none and no setup (best ordinary move {tuple(start)} "
                            f"{direction}, score {best_plain.score:.0f})"
                        )
                    else:
                        extra_move_hint = "none (no legal moves on the board)"
                else:
                    decision_gate = getattr(best_evaluation, "decision_gate", "unknown")
                    if decision_gate == "unknown":
                        decision_gate = "same_move_extra_gate"
                # The selected list holds only extra-granting moves, so the
                # logged candidates omit plain alternatives. Also rank the full
                # move set so offline learning can measure what the extra-move
                # gate skipped. This is a second whole rank_moves pass, so it
                # rides the images/deep flag rather than the always-on record --
                # every move would otherwise pay for it now that the record no
                # longer switches off. The empty-extra branch above may already
                # have paid for it to build its hint -- reuse that pass.
                if debug_images_enabled and full_ranked_candidates is None:
                    full_ranked_candidates = rank_moves(
                        game_board,
                        special_game_board,
                        recognition.curr_mode,
                        allow_square_matches=allow_square_matches,
                        score_rally_values=score_rally_values,
                        lookahead_candidates=request.lookahead_candidates,
                        include_future_value=request.include_future_value,
                        lookahead_depth=effective_lookahead_depth,
                        lookahead_beam_width=request.lookahead_beam_width,
                        explode_created_specials_immediately=specials_explode_immediately,
                        strategy_context=strategy_context,
                    )
        else:
            if request.points_only and request.worst_move:
                ranked_moves = rank_lowest_points_moves(
                    game_board,
                    special_game_board,
                    recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    lookahead_candidates=request.lookahead_candidates,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
            elif request.points_only:
                ranked_moves = rank_points_only_moves(
                    game_board,
                    special_game_board,
                    recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    lookahead_candidates=request.lookahead_candidates,
                    include_future_value=request.include_future_value,
                    lookahead_depth=effective_lookahead_depth,
                    lookahead_beam_width=request.lookahead_beam_width,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
            else:
                ranked_moves = rank_moves(
                    game_board,
                    special_game_board,
                    recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    lookahead_candidates=request.lookahead_candidates,
                    include_future_value=request.include_future_value,
                    lookahead_depth=effective_lookahead_depth,
                    lookahead_beam_width=request.lookahead_beam_width,
                    explode_created_specials_immediately=specials_explode_immediately,
                    strategy_context=strategy_context,
                    turn_state=turn_state,
                )
            booster_debug_path = debug_run_dir / "booster.png" if debug_images_enabled else None
            booster_detection = resolve_booster_activation_detection(
                booster_debug_path,
                force_no_booster=request.force_no_booster,
                screen_state_read=request.screen_state_read,
                booster_action_mode=booster_action_mode,
            )
            booster_state = effective_booster_state_for_detection(
                booster_state,
                booster_detection,
            )
            booster_activation_ready = bool(
                booster_detection["active"]
            )
            if not request.points_only:
                mixy_meow_state = resolve_mixy_meow_state(
                    request, recognition, mixy_meow_state
                )
            mixy_code_active = bool(
                not request.points_only
                and recognition.special_piece_mode
                in {SPECIAL_PIECE_MODE_AUTO, SPECIAL_PIECE_MODE_MIXY_MEOW}
                and mixy_meow_state is not None
                and mixy_meow_state.is_reliable
            )
            prioritized_moves = (
                ranked_moves
                if request.points_only
                else prioritize_ranked_moves(
                    ranked_moves,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    explode_created_specials_immediately=specials_explode_immediately,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                )
            )
            if (request.engine_plan_move is not None and not request.points_only
                    and (goal is None or goal.complete)):
                prioritized_moves = promote_engine_plan_move(
                    prioritized_moves, request.engine_plan_move
                )
            froggy_lotus_moves = (
                []
                if request.points_only
                else rank_froggy_lotus_moves(
                    ranked_moves,
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    score_rally_values=score_rally_values,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                    specials_auto_explode=specials_explode_immediately,
                )
            )
            # A free blue extra that leaves the lotus standing is banked before
            # the collect fires (see POINT_RACE_BLUE_EXTRA_BEFORE_LOTUS); in the
            # true Solo Challenge only when it out-charges every collect
            # (SOLO_EXTRA_BEFORE_LOTUS). None whenever the policy does not
            # apply, which leaves the lotus gate exactly as it was.
            blue_extra_before_lotus = blue_extra_move_before_lotus(
                ranked_moves,
                froggy_lotus_moves,
                special_game_board,
                mode=recognition.curr_mode,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                explode_created_specials_immediately=specials_explode_immediately,
                booster_state=booster_state,
                turn_state=turn_state,
                strategy_context=strategy_context,
            )
            # An extra elsewhere whose settled board puts blue next to the lotus
            # goes first too (player, 2026-11-07): the next move then fires the
            # lotus on blue. True Solo Challenge only.
            blue_setup_before_lotus = None
            if blue_extra_before_lotus is None:
                blue_setup_before_lotus = blue_setup_extra_before_lotus(
                    ranked_moves,
                    froggy_lotus_moves,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    explode_created_specials_immediately=specials_explode_immediately,
                    booster_state=booster_state,
                    strategy_context=strategy_context,
                )
            # Froggy Fu with Checkerboard equipped: the perk waits for the first
            # activation after the clock arms it (FROGGY_CHECKERBOARD_ARM_SECONDS).
            # Observed on every decision, perk or not, so the lotus count the
            # next one is compared with is never stale.
            froggy_checkerboard_due = _FROGGY_CHECKERBOARD_TRACKER.observe(
                special_game_board, turn_state
            )
            froggy_checkerboard_policy = (
                not request.points_only
                and froggy_checkerboard_policy_applies(
                    selected_perks,
                    request.froggy_gather_region is not None
                    or _froggy_lotus_count(special_game_board) > 0,
                    turn_state,
                    strategy_context,
                )
            )
            forced_extra_move = None
            immediate_booster_extra = None
            mixy_candidates = []
            mixy_ranked = []
            mixy_extra_move = None
            # Color Climb: a Mixy code move that matches one of our dealt
            # colours. Played ahead of the booster and the extra hunt (the
            # user's rule for the mode); None everywhere else.
            color_climb_mixy_move = None
            mixy_extra_refund_proof = False
            # Left True until the code path actually runs: _mixy_refund_burned
            # is a once-per-decision verdict and must not be spent on a
            # decision that has no code move to rank.
            mixy_count_code_refund = True
            dragon_activates_before_extra = bool(
                booster_activation_ready
                and booster_action_mode == BOOSTER_ACTION_DRAGON
            )
            # The toggle, or a full meter in a turn the clock ends
            # (TIME_BOUND_BOOSTER_FIRST): either way the booster goes first.
            booster_time_bound_first = bool(
                booster_activation_ready
                and not request.activate_booster_immediately
                and time_bound_booster_first(turn_state, strategy_context)
            )
            booster_first = bool(
                request.activate_booster_immediately or booster_time_bound_first
            )
            forced_manual_perk = request.forced_perk_slot in (1, 2)
            if mixy_code_active and not forced_manual_perk:
                _note_mixy_current_code(mixy_meow_state)
                mixy_count_code_refund = not _mixy_refund_burned(
                    turn_state.remaining_moves
                )
                if _mixy_code_dead_after_burn(mixy_meow_state):
                    # One proven broken refund on this exact code: the engine
                    # has spent it, whatever the GUI's use counter says. Rank
                    # it as exhausted so no code move is offered until the
                    # list re-deals (rank_mixy_code_moves returns nothing for
                    # an exhausted code).
                    cap = int(getattr(mixy_meow_state, "max_uses", 0) or 0) or 2
                    mixy_meow_state = replace(
                        mixy_meow_state,
                        uses_this_activation=max(
                            cap, int(getattr(mixy_meow_state, "uses_this_activation", 0) or 0)
                        ),
                        max_uses=cap,
                        reason=(
                            f"{mixy_meow_state.reason}; kod proglasen mrtvim posle "
                            "neispunjenog refund-a (isti activeColors)"
                        ),
                    )
                # Rank the code moves before the booster/extra decision. Mixy
                # converts before the swap resolves, so an extra earned on this
                # turn is only visible on the converted board.
                mixy_ranked = rank_mixy_code_moves(
                    game_board,
                    special_game_board,
                    mixy_meow_state,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    lookahead_candidates=request.lookahead_candidates,
                    lookahead_depth=effective_lookahead_depth,
                    lookahead_beam_width=request.lookahead_beam_width,
                    explode_created_specials_immediately=specials_explode_immediately,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                    count_code_refund=mixy_count_code_refund,
                )
                color_climb_mixy_move = next(
                    (
                        evaluation
                        for evaluation in color_climb_mixy_code_moves(
                            mixy_ranked, recognition.curr_mode
                        )
                    ),
                    None,
                )
                # The refund credit alone satisfies has_reliable_same_move_extra
                # (rank_mixy_code_moves writes it straight into
                # direct_extra_moves), so picking the first "reliable extra"
                # here promoted every code move to a guaranteed one. Use the
                # same refund-proof preference the Extra-move button already
                # uses: a code move whose swap earns its own extra keeps the
                # turn outright and may still preempt the ordinary hunt, while
                # a refund-only one waits for that hunt to come up empty (see
                # the fallback below).
                mixy_extra_move = _prefer_refund_proof_mixy_extra(
                    mixy_ranked, mixy_count_code_refund, score_rally_values
                )
                if mixy_extra_move is not None and not has_reliable_same_move_extra(
                    mixy_extra_move
                ):
                    mixy_extra_move = None
                mixy_extra_refund_proof = mixy_extra_move is not None and (
                    getattr(mixy_extra_move, "direct_extra_moves", 0.0)
                    > (1.0 if mixy_count_code_refund else 0.0)
                )
            if request.points_only:
                forced_extra_move = None
            elif forced_manual_perk:
                forced_extra_move = None
            elif (
                mixy_extra_move is not None
                and mixy_extra_refund_proof
                and not booster_activation_ready
            ):
                # The code move keeps the turn, so it costs nothing to play it
                # first while the meter is still charging -- but only a
                # refund-proof one keeps it for certain. A refund-only code
                # move now waits below, behind the ordinary extra hunt.
                #
                # A READY booster is the exception: the code re-deals itself
                # after every code match AND right after activation (measured
                # 2026-08-26 00:50:27->:30 and 00:51:30->:33: activation, phase
                # 0, fresh activeColors two seconds later), so there is always
                # another code move -- letting it precede activation starved
                # the booster for 48s at 7/7 (00:51:13-00:52:01) while plain
                # moves played out. Activation loses only the current colours,
                # not the code slot, so it goes first.
                forced_extra_move = mixy_extra_move
                mixy_candidates = mixy_ranked
            elif mixy_extra_move is not None and booster_activation_ready:
                # Player rule (2026-09-26): with a Mixy code move on the board
                # the ready booster waits -- unless that code move earns no
                # extra. The extra keeps the turn, so the booster still fires
                # on the very next decision.
                forced_extra_move = mixy_extra_move
                mixy_candidates = mixy_ranked
            elif dragon_activates_before_extra:
                # Dragon enhances the swipe that follows activation. Playing a
                # direct extra first would spend the same scoring opportunity
                # without Dragon's rays; let choose_dragon_move evaluate that
                # extra (and every alternative) with the booster effect instead.
                forced_extra_move = None
            elif booster_activation_ready and booster_first:
                immediate_booster_extra = _valuable_extra_before_immediate_booster(
                    prioritized_moves,
                    recognition.curr_mode,
                    strategy_context=strategy_context,
                    turn_state=turn_state,
                )
                forced_extra_move = immediate_booster_extra
            else:
                forced_extra_move = _forced_extra_move_candidate(
                    prioritized_moves,
                    direct_only=booster_activation_ready,
                    strategy_context=strategy_context,
                )
                # No guaranteed board extra: consider a refund-only code move
                # only when its value justifies the less reliable refund.
                if (
                    forced_extra_move is None
                    and mixy_extra_move is not None
                    and not booster_activation_ready
                    and _mixy_code_move_worth_forcing(
                        mixy_extra_move, prioritized_moves, mixy_count_code_refund
                    )
                ):
                    forced_extra_move = mixy_extra_move
                    mixy_candidates = mixy_ranked
            disco_before_booster = (
                disco_swap_before_booster(
                    ranked_moves,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    booster_state=booster_state,
                    strategy_context=strategy_context,
                    turn_state=turn_state,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if booster_activation_ready and not request.points_only
                else None
            )
            solo_goal_moves = solo_goal_priority_moves(
                ranked_moves, recognition.curr_mode, booster_state, turn_state,
                score_rally_values, strategy_context,
            ) if not request.points_only else []
            if request.solo_cross_report is not None and not request.points_only:
                request.solo_cross_report(bool(solo_goal_moves))
            if request.solo_cross_only:
                selection_candidates = solo_goal_moves
                selected_action = "move" if solo_goal_moves else "none"
                best_evaluation = solo_goal_moves[0] if solo_goal_moves else None
                decision_gate = (
                    best_evaluation.decision_gate if best_evaluation else "solo_target_no_move_gate"
                )
            elif request.points_only:
                selection_candidates = ranked_moves
                selected_action = "move" if ranked_moves else "none"
                best_evaluation = ranked_moves[0] if ranked_moves else None
                decision_gate = (
                    ("worst_move_gate" if request.worst_move else "points_only_gate")
                    if best_evaluation
                    else "no_action_gate"
                )
            elif not forced_manual_perk and goal is not None and goal.complete and not goal.continue_after_last:
                selection_candidates = []
                selected_action = "none"
                best_evaluation = None
                decision_gate = "solo_target_complete_gate"
            elif (not forced_manual_perk and prioritized_moves
                  and prioritized_moves[0].decision_gate in {
                      "solo_target_finish_gate", "solo_target_refill_gate", "jelly_stage_cross_gate",
                  }):
                selection_candidates = prioritized_moves
                selected_action = "move"
                best_evaluation = prioritized_moves[0]
                decision_gate = best_evaluation.decision_gate
            elif forced_manual_perk:
                selection_candidates = prioritized_moves
                manual_baseline = prioritized_moves[0] if prioritized_moves else None
                forced_slot = int(request.forced_perk_slot)
                forced_perk_key = selected_perks[forced_slot - 1]
                if forced_perk_key in PERK_DEFINITIONS:
                    blue_plan = evaluate_blue_plan(
                        game_board,
                        special_game_board,
                        booster_state,
                        mode=recognition.curr_mode,
                        allow_square_matches=allow_square_matches,
                        score_rally_values=score_rally_values,
                        explode_created_specials_immediately=specials_explode_immediately,
                    )
                    decision_context = PerkDecisionContext(
                        booster=booster_state,
                        turn=turn_state,
                        blue_plan=blue_plan,
                        # The click forces activation, not a weaker ranking
                        # objective.  Targets and follow-ups must use the same
                        # BEST_MOVE horizon, booster value, and conservative
                        # random-outcome estimate as Auto.
                        objective=PerkObjective.BEST_MOVE,
                    )
                    forced_selected_perks = tuple(
                        forced_perk_key if index == forced_slot else PERK_NONE
                        for index in (1, 2)
                    )
                    perk_candidates = rank_selected_perk_actions(
                        game_board,
                        special_game_board,
                        forced_selected_perks,
                        normal_baseline=manual_baseline,
                        decision_context=decision_context,
                        mode=recognition.curr_mode,
                        allow_square_matches=allow_square_matches,
                        score_rally_values=score_rally_values,
                        include_future_value=request.include_future_value,
                        booster_active=False,
                        explode_created_specials_immediately=specials_explode_immediately,
                        strategy_context=strategy_context,
                        force_use=True,
                        # Only the clicked slot may activate, but the other
                        # equipped perk remains relevant to combo planning.
                        all_available_perks=tuple(
                            perk_key
                            for perk_key in selected_perks
                            if perk_key in PERK_DEFINITIONS
                        ),
                    )
                if perk_candidates:
                    selected_perk_action = perk_candidates[0]
                    selected_action = "activate_perk"
                    best_evaluation = manual_baseline
                    decision_gate = "manual_perk_slot_gate"
                else:
                    manual_perk_failure_reason = perk_legality_reason(
                        forced_perk_key,
                        game_board,
                        special_game_board,
                        manual_baseline,
                    ) or "Nije pronadjena legalna meta za izabrani perk."
                    baseline_value = (
                        float(manual_baseline.score)
                        if manual_baseline is not None
                        else 0.0
                    )
                    best_rejected_perk = PerkAction(
                        perk_key=forced_perk_key,
                        target=None,
                        score=baseline_value,
                        gross_score=baseline_value,
                        threshold=0.0,
                        baseline_score=baseline_value,
                        reason=manual_perk_failure_reason,
                        explanation="manual_force_mechanical_illegality",
                        legal=False,
                        legal_reason=manual_perk_failure_reason,
                        objective=PerkObjective.MANUAL_FORCE,
                    )
                    selected_action = "none"
                    best_evaluation = None
                    decision_gate = "manual_perk_no_target_gate"
            elif (
                request.booster_clock_deadline
                and booster_activation_ready
                and not (strategy_context.is_versus_2 and forced_extra_move is not None)
            ):
                # Player, 2026-10-08: 31 of 263 races (9/25-10/8) ended with the
                # meter full because extras -- ~2.5 s of clock each, up to ~5-7 s
                # -- kept going first until the clock fell under the 8 s
                # low-clock rule (2026-09-29 19:36: full at 22.4 s, five extras,
                # too late at 8.0 s). In Versus the extra keeps a paid move;
                # let it go first (2026-11-11 18:17:56, 13.47 s left).
                selection_candidates = prioritized_moves
                selected_action = "activate_booster"
                best_evaluation = None
                decision_gate = "booster_clock_deadline_gate"
            elif (
                froggy_checkerboard_policy
                and request.allow_perk_activation
                and not booster_detection["active"]
                and froggy_checkerboard_due
                and (
                    froggy_checkerboard_action := _froggy_checkerboard_action(
                        game_board,
                        special_game_board,
                        selected_perks,
                        prioritized_moves[0] if prioritized_moves else None,
                        booster_state,
                        turn_state,
                        strategy_context,
                        mode=recognition.curr_mode,
                        allow_square_matches=allow_square_matches,
                        score_rally_values=score_rally_values,
                        include_future_value=request.include_future_value,
                        explode_created_specials_immediately=specials_explode_immediately,
                    )
                )
                is not None
            ):
                # Ahead of the lotus move and of the blue extra before it: the
                # repaint is what makes the collect big, and it wipes any extra
                # standing on the board anyway.
                selection_candidates = prioritized_moves
                perk_candidates = [froggy_checkerboard_action]
                selected_perk_action = froggy_checkerboard_action
                selected_action = "activate_perk"
                best_evaluation = prioritized_moves[0] if prioritized_moves else None
                decision_gate = "froggy_checkerboard_gate"
            elif (
                color_climb_extra := (
                    color_climb_extra_before_booster(
                        prioritized_moves,
                        recognition.curr_mode,
                        lotus_moves=froggy_lotus_moves,
                        special_board=special_game_board,
                        allow_square_matches=allow_square_matches,
                        score_rally_values=score_rally_values,
                        explode_created_specials_immediately=specials_explode_immediately,
                    )
                    if (
                        froggy_lotus_moves
                        or booster_activation_ready
                        or color_climb_mixy_move is not None
                    )
                    else None
                )
            ) is not None:
                # Color Climb (player, 2026-10-08): with a booster to spend --
                # a lotus, a ready meter or a dealt-colour Mixy code -- a sure
                # extra that makes a dealt-colour combo (its own match or a
                # sure cascade, any colour of extra) goes first. It keeps the
                # turn and raises the multiplier; the booster waits one move.
                selection_candidates = prioritized_moves
                selected_action = "move"
                best_evaluation = color_climb_extra
                decision_gate = "color_climb_extra_before_booster_gate"
            elif blue_extra_before_lotus is not None:
                # The lotus keeps: it is a piece on the board, not an offer that
                # expires, and this move was checked to leave it standing.
                selection_candidates = prioritized_moves
                selected_action = "move"
                best_evaluation = blue_extra_before_lotus
                decision_gate = "blue_extra_before_lotus_gate"
            elif blue_setup_before_lotus is not None:
                selection_candidates = prioritized_moves
                selected_action = "move"
                best_evaluation = blue_setup_before_lotus
                decision_gate = "blue_setup_extra_before_lotus_gate"
            elif froggy_lotus_moves:
                selection_candidates = froggy_lotus_moves
                selected_action = "move"
                best_evaluation = froggy_lotus_moves[0]
                decision_gate = getattr(best_evaluation, "decision_gate", "froggy_lotus_gate")
            elif color_climb_mixy_move is not None:
                # Color Climb: a code match in a dealt colour repaints the board
                # into that colour *and* raises the multiplier, so it goes
                # before the booster (ready or not) and before the ordinary
                # extra hunt. The lotus above keeps precedence: it is a piece
                # on the board and its dealt-colour collect is tiered first in
                # rank_froggy_lotus_moves.
                selection_candidates = mixy_ranked
                selected_action = "move"
                best_evaluation = color_climb_mixy_move
                decision_gate = "color_climb_mixy_code_gate"
            elif forced_extra_move is not None:
                if forced_extra_move is mixy_extra_move:
                    selection_candidates = mixy_ranked
                    decision_gate = "mixy_extra_move_gate"
                else:
                    selection_candidates = prioritized_moves
                    decision_gate = (
                        "booster_immediate_valuable_extra_gate"
                        if immediate_booster_extra is not None
                        else _extra_move_decision_gate(forced_extra_move)
                    )
                selected_action = "move"
                best_evaluation = forced_extra_move
            elif mixy_code_active:
                mixy_candidates = mixy_ranked
                # A playable pending Mixy code goes before an unready booster.
                # Once the meter is full the ordinary booster path decides
                # instead: activation re-deals a fresh code immediately, so a
                # pending code is never a reason to postpone it (see the
                # mixy_extra_move guard above for the measurement).
                # ... and only while it is not handing back a far better plain
                # move for the code bonus. The bonus orders code moves against
                # each other; nothing here ever compared them with the rest of
                # the board, so a 6-point code three-match could preempt a
                # 37-point move on the strength of a refund that misses about
                # one time in five.
                if (
                    mixy_candidates
                    and not booster_activation_ready
                    and _mixy_code_move_worth_forcing(
                        mixy_candidates[0], prioritized_moves, mixy_count_code_refund
                    )
                ):
                    selection_candidates = mixy_candidates
                    selected_action = "move"
                    best_evaluation = mixy_candidates[0]
                    decision_gate = getattr(
                        best_evaluation, "decision_gate", "unknown"
                    )
                    if decision_gate == "unknown":
                        decision_gate = "score_gate"
                else:
                    # A readable popup does not guarantee that its code can be
                    # matched on this board (and a ready booster outranks any
                    # pending code). Use the ordinary booster/exploration path
                    # and let perks be considered too.
                    selection_candidates = prioritized_moves
                    selected_action, best_evaluation, decision_gate = select_booster_action_with_gate(
                        selection_candidates,
                        booster_detection["active"],
                        booster_first
                        or dragon_activates_before_extra,
                        turn_state=turn_state,
                        strategy_context=strategy_context,
                        jelly_zone_pending=bool(_jelly_zone_cells),
                        multiplier_extra_colors=_color_climb_extra_colors(),
                        disco_before_booster=disco_before_booster,
                    )
                    if dragon_activates_before_extra and selected_action == "activate_booster":
                        decision_gate = "dragon_before_extra_gate"
                    elif (booster_time_bound_first
                          and decision_gate == "booster_immediate_toggle_gate"):
                        decision_gate = TIME_BOUND_BOOSTER_GATE
                    if selected_action == "move":
                        best_evaluation, exploration_info = maybe_explore_move(
                            best_evaluation, selection_candidates
                        )
                        if exploration_info.get("explored"):
                            decision_gate = "exploration_gate"
            else:
                selection_candidates = prioritized_moves
                selected_action, best_evaluation, decision_gate = select_booster_action_with_gate(
                    selection_candidates,
                    booster_detection["active"],
                    booster_first
                    or dragon_activates_before_extra,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                    jelly_zone_pending=bool(_jelly_zone_cells),
                    multiplier_extra_colors=_color_climb_extra_colors(),
                    disco_before_booster=disco_before_booster,
                )
                if dragon_activates_before_extra and selected_action == "activate_booster":
                    decision_gate = "dragon_before_extra_gate"
                elif (booster_time_bound_first
                      and decision_gate == "booster_immediate_toggle_gate"):
                    decision_gate = TIME_BOUND_BOOSTER_GATE
                # ε-greedy exploration only on the generic greedy move pick.
                if selected_action == "move":
                    best_evaluation, exploration_info = maybe_explore_move(
                        best_evaluation, selection_candidates
                    )
                    if exploration_info.get("explored"):
                        decision_gate = "exploration_gate"
            normal_baseline = best_evaluation
            if normal_baseline is None:
                normal_baseline = prioritized_moves[0] if prioritized_moves else None
            # Checkerboard held back for the final lotuses is invisible to the
            # ordinary perk policy: it is neither ranked nor counted as the
            # "last perk" to reserve.
            auto_selected_perks = selected_perks
            if froggy_checkerboard_policy:
                auto_selected_perks = tuple(
                    PERK_NONE if perk_key == PERK_CHECKERBOARD else perk_key
                    for perk_key in selected_perks
                )
            valid_selected_perks = [
                perk_key
                for perk_key in auto_selected_perks
                if perk_key in PERK_DEFINITIONS
            ]
            has_selected_perk = bool(valid_selected_perks)
            # Use-it-or-lose-it window: on the last move of a solo showdown
            # (or the final versus round) an unused perk simply expires. The
            # ranking layer already handles this (_final_showdown_perk_pressure
            # halves thresholds and adds no-target fallbacks for star_maker &
            # co.) -- but with the Mixy code read from memory, mixy_candidates
            # is non-empty on virtually every decision of a Mixy match, and the
            # mixy blocker below kept the ranking from ever running: in the
            # 2026-08-23 17:01 match star_maker was considered once, rejected,
            # and then never looked at again before the match ended. In this
            # window the mixy/forced-extra blockers therefore step aside.
            versus_last_chance, _versus_last_chance_reason = versus_perk_last_chance(
                turn_state,
                strategy_context,
                len(valid_selected_perks),
                normal_baseline,
            )
            perk_last_chance = bool(
                (
                    turn_state.remaining_moves is not None
                    and turn_state.remaining_moves <= 1
                    and (
                        strategy_context.is_solo_6
                        or (strategy_context.is_versus_2 and turn_state.is_final_round)
                    )
                )
                or versus_last_chance
            )
            perk_blocked_reason = None
            if not has_selected_perk:
                perk_blocked_reason = "no_available_slot"
            elif forced_manual_perk:
                perk_blocked_reason = "manual_perk_forced"
            elif decision_gate in {
                "froggy_checkerboard_gate", "solo_target_finish_gate", "solo_target_refill_gate",
                "solo_target_no_move_gate", "solo_target_complete_gate", "jelly_stage_cross_gate",
            }:
                perk_blocked_reason = f"gate:{decision_gate}"
            elif not request.allow_perk_activation:
                perk_blocked_reason = "perk_activation_disabled"
            elif booster_detection["active"] and not (
                goal is not None and not goal.complete and turn_state.remaining_moves == 1
                and not (normal_baseline and has_reliable_same_move_extra(normal_baseline))
            ):
                perk_blocked_reason = "booster_active"
            elif mixy_candidates and not perk_last_chance:
                perk_blocked_reason = "mixy_code_move"
            elif froggy_lotus_moves:
                perk_blocked_reason = "froggy_lotus_move"
            elif not (
                forced_extra_move is None
                # Energy Boost enhances the already-forced extra swipe; it does
                # not replace or endanger it. Other perks remain blocked here.
                or PERK_ENERGY_BOOST in valid_selected_perks
                or perk_last_chance
            ):
                perk_blocked_reason = "forced_extra_move"
            elif exploration_info is not None and exploration_info.get("explored"):
                perk_blocked_reason = "exploration"
            blue_plan = (
                evaluate_blue_plan(
                    game_board,
                    special_game_board,
                    booster_state,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if perk_blocked_reason is None and (goal is None or goal.complete)
                else None
            )
            decision_context = PerkDecisionContext(
                booster=booster_state,
                turn=turn_state,
                blue_plan=blue_plan,
                # A perk is judged by the meter alone -- the charge it
                # banks plus the blue of the move it sets up -- never by
                # points, and with no exception: a perk is a free resource
                # and the booster is what it is for. Points-only used to
                # override this on a final versus round; that override is
                # gone by explicit decision.
                objective=PerkObjective.MAX_BLUE,
            )
            # Generation (legal targets per slot) and the activation decision
            # (is the perk worth more than keeping it) live in
            # decide_auto_perk, which also records per slot why no perk went.
            auto_perk_decision = decide_auto_perk(
                game_board,
                special_game_board,
                auto_selected_perks,
                normal_baseline=normal_baseline,
                decision_context=decision_context,
                strategy_context=strategy_context,
                perk_slot_status=request.perk_slot_status,
                blocked_reason=perk_blocked_reason,
                teleport_exact_pair=request.teleport_exact_pair,
                mode=recognition.curr_mode,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                include_future_value=request.include_future_value,
                booster_active=booster_detection["active"],
                explode_created_specials_immediately=specials_explode_immediately,
            )
            perk_slot_reasons = auto_perk_decision.slot_reasons
            perk_last_chance_info = {
                "active": auto_perk_decision.last_chance,
                "reason": auto_perk_decision.last_chance_reason,
            }
            if perk_blocked_reason is None:
                perk_candidates = auto_perk_decision.candidates
                best_rejected_perk = auto_perk_decision.best_rejected
                if auto_perk_decision.selected is not None:
                    selected_perk_action = auto_perk_decision.selected
                    selected_action = "activate_perk"
                    decision_gate = auto_perk_decision.gate
                if selected_perk_action is None and not perk_candidates:
                    def rejected_perk(perk_key):
                        contextual = context_rejected_perk_action(
                            perk_key,
                            normal_baseline,
                            decision_context,
                            strategy_context=strategy_context,
                        )
                        if contextual is not None:
                            return contextual
                        illegality = perk_legality_reason(
                            perk_key,
                            game_board,
                            special_game_board,
                            normal_baseline,
                        )
                        if illegality is None:
                            return None
                        baseline_value = (
                            float(normal_baseline.score)
                            if normal_baseline is not None
                            else 0.0
                        )
                        return PerkAction(
                            perk_key=perk_key,
                            target=None,
                            score=baseline_value,
                            gross_score=baseline_value,
                            threshold=0.0,
                            baseline_score=baseline_value,
                            reason=illegality,
                            explanation="mechanical_illegality",
                            legal=False,
                            legal_reason=illegality,
                            objective=decision_context.objective,
                        )

                    rejected_perks = (
                        rejected_perk(perk_key)
                        for perk_key in valid_selected_perks
                    )
                    best_rejected_perk = next(
                        (rejection for rejection in rejected_perks if rejection is not None),
                        None,
                    )
            if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_HIGH_VOLTAGE:
                high_voltage_target = choose_high_voltage_target(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                    strategy_context=strategy_context,
                    turn_state=turn_state,
                )
                if high_voltage_target is None:
                    selected_action, best_evaluation, decision_gate = (
                        fallback_from_targetless_booster(
                            normal_baseline, booster_action_mode
                        )
                    )
            if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_MAGIC_WAND:
                magic_wand_target = choose_magic_wand_target(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if magic_wand_target is None:
                    selected_action, best_evaluation, decision_gate = (
                        fallback_from_targetless_booster(
                            normal_baseline, booster_action_mode
                        )
                    )
            if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_LASER_BEAM:
                laser_beam_target = choose_laser_beam_target(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                    booster_state=booster_state,
                )
                if laser_beam_target is None:
                    selected_action, best_evaluation, decision_gate = (
                        fallback_from_targetless_booster(
                            normal_baseline, booster_action_mode
                        )
                    )
                elif not should_fire_laser_over_move(
                    laser_beam_target,
                    normal_baseline,
                    request.activate_booster_immediately,
                ):
                    # A stronger normal move exists; keep the booster charged and
                    # play the move instead of spending the laser on a weak cross.
                    selected_action = "move"
                    best_evaluation = normal_baseline
                    decision_gate = "laser_value_below_move_gate"
                    laser_beam_target = None
            if (
                selected_action == "activate_booster"
                and booster_action_mode == BOOSTER_ACTION_WOOLLY_WORKOUT
            ):
                woolly_workout_target = choose_woolly_workout_target(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                )
                if woolly_workout_target is None:
                    selected_action, best_evaluation, decision_gate = (
                        fallback_from_targetless_booster(
                            normal_baseline, booster_action_mode
                        )
                    )
            if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_DRAGON:
                dragon_move = choose_dragon_move(
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    include_future_value=request.include_future_value,
                    explode_created_specials_immediately=specials_explode_immediately,
                    strategy_context=strategy_context,
                )
                if dragon_move is None:
                    selected_action, best_evaluation, decision_gate = (
                        fallback_from_targetless_booster(
                            normal_baseline, booster_action_mode
                        )
                    )
                elif (goal is not None and not goal.complete and turn_state.remaining_moves == 1
                      and normal_baseline is not None and not has_reliable_same_move_extra(dragon_move)
                      and (has_reliable_same_move_extra(normal_baseline)
                           or solo_goal_progress(dragon_move, recognition.curr_mode, goal)
                           <= solo_goal_progress(normal_baseline, recognition.curr_mode, goal))):
                    # Dragon includes a swipe. A ready free activation would
                    # leave the normal move available, so this check is specific to Dragon.
                    selected_action = "move"
                    best_evaluation = normal_baseline
                    decision_gate = "solo_dragon_progress_below_move_gate"

        if selected_action == "activate_booster" and booster_action_mode == BOOSTER_ACTION_DRAGON and dragon_move is None:
            dragon_move = choose_dragon_move(
                game_board,
                special_game_board,
                mode=recognition.curr_mode,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                include_future_value=request.include_future_value,
                explode_created_specials_immediately=specials_explode_immediately,
            )
            if dragon_move is None:
                selected_action = "none"

    compute_ms = (time.perf_counter() - compute_phase_start) * 1000.0

    planning_wait_ms = 0.0
    if request.wait_for_board is not None:
        wait_start = time.perf_counter()
        if not request.wait_for_board():
            return CheckBestMoveResult(
                best_move_text="Auto: board changed, recomputing",
                score_text="", turn_consumed=False, planning_cancelled=True,
            )
        planning_wait_ms = (time.perf_counter() - wait_start) * 1000.0
        if request.claim_execution is None or not request.claim_execution():
            return CheckBestMoveResult(
                best_move_text="Auto: recomputing new board", score_text="",
                turn_consumed=False, planning_cancelled=True,
            )
        # A held plan may have been computed before BlueStacks left or re-entered
        # fullscreen. The board in memory is the same, so the plan is still good,
        # but its screen geometry is not: the first swipe landed on old coordinates.
        apply_board_profile(selected_profile)
        debug_enabled = request.debug_enabled
        debug_images_enabled = debug_enabled and request.debug_images_enabled
        debug_run_dir = create_debug_run_dir() if debug_enabled else None
        previous_debug_run = find_previous_debug_run(debug_run_dir) if debug_enabled else None
        debug_board_path = debug_run_dir / "board.png" if debug_images_enabled else None
        debug_score_region = live_score_region if debug_images_enabled else None
        if debug_images_enabled:
            capture_debug_screenshot(
                debug_board_path,
                region=(recognition.left, recognition.up, recognition.width, recognition.height),
            )
            debug_score_path = capture_score_region(
                debug_run_dir / SCORE_REGION_FILENAME, debug_score_region,
            )
        if previous_debug_run is not None:
            flush_debug_screenshot_writes(debug_board_path)
            flush_debug_screenshot_writes(debug_score_path)
            observed_delta_path = write_observed_delta_report(
                previous_debug_run, debug_run_dir, debug_board_path, debug_score_path,
                game_board, special_game_board, after_score_region=debug_score_region,
            )

    # Where the cursor goes back to is read HERE, after the plan has waited for
    # the board and been claimed, unless the caller pinned it. Read when the
    # computation started, it pointed wherever the mouse was when a speculative
    # plan began -- seconds before the click that armed it -- so the cursor
    # jumped back to that stale spot instead of the button that was clicked.
    # Resolved once, so a booster click followed by its swipe (Dragon) still
    # returns to the user's position rather than to the booster button.
    if cursor_return_position is None:
        cursor_return_position = tuple(pyautogui.position())

    # Strategy Lab is the last policy choice, after native strategic gates and
    # after the board/claim checks. Native execution and confirmation stay below.
    strategy_lab_label, strategy_lab_token = "", None
    protected_goal = decision_gate in {
        "solo_target_finish_gate", "solo_target_refill_gate", "solo_target_complete_gate", "jelly_stage_cross_gate",
    }
    try:
        if not protected_goal and (goal is None or goal.complete):
            best_evaluation, strategy_lab_label, strategy_lab_token = strategy_lab_live.runtime_select(
                request=request, mode=recognition.curr_mode, context=strategy_context,
                board=game_board, special_board=special_game_board,
                evaluations=locals().get("ranked_moves", selection_candidates),
                baseline=best_evaluation, selected_action=selected_action,
                booster_detection=booster_detection, selected_perks=selected_perks,
                ufo_state=ufo_state, mixy_state=mixy_meow_state,
                flags=dict(allow_square_matches=allow_square_matches,
                    specials_explode_immediately=specials_explode_immediately,
                    color_crush=color_crush, energized_colors=energized_colors,
                    engine_charge_colors=request.engine_charge_colors,
                    mushroom_multipliers=request.mushroom_multipliers,
                    vertical_matches_destroy_color=vertical_matches_destroy_color,
                    matches_destroy_color=matches_destroy_color,
                    all_specials_lightning=all_specials_lightning,
                    every_match_is_special=every_match_is_special,
                    line_destruction=line_destruction,
                    single_player_board=(strategy_context.is_solo_6 if request.single_player_board is None else request.single_player_board)),
            )
        if strategy_lab_token and strategy_lab_live.settings().get("mode") == "active":
            decision_gate = "strategy_lab_profile_or_explicit_fallback"
    except Exception as exc:
        strategy_lab_label = "[Lab fallback: " + str(exc)[:100] + "] "

    # Square Match Solo exact-refill plan (square_solo_live): the planner saw
    # the real refills to the last move, so its swap wins over every swap
    # heuristic above. Booster and perk decisions are left alone.
    if (not protected_goal and (goal is None or goal.complete)
            and request.engine_plan_move is not None and selected_action == "move"
            and not request.points_only and not request.solo_cross_only):
        planned = promote_engine_plan_move(
            list(locals().get("ranked_moves") or locals().get("selection_candidates") or []),
            request.engine_plan_move,
        )
        if planned and {tuple(planned[0].candidate.start), tuple(planned[0].candidate.target)} == {
                tuple(request.engine_plan_move[0]), tuple(request.engine_plan_move[1])}:
            best_evaluation = planned[0]
            decision_gate = "engine_plan_gate"
            strategy_lab_label = "[tacna dopuna] " + strategy_lab_label
    # The lotus collect with the drop known: the gather and the cascades after
    # it re-simulated on the exact refill, ranked by the same lotus rule.
    elif (not protected_goal and selected_action == "move" and not request.points_only
            and not request.solo_cross_only and request.late_exact_refill is not None
            and decision_gate == "froggy_lotus_gate" and locals().get("froggy_lotus_moves")):
        try:
            late_session = request.late_exact_refill()
        except Exception as exc:  # The plain pick stays; never lose the move.
            late_session = None
            print(f"fast refill: late session failed: {type(exc).__name__}: {exc}")
        if late_session is not None:
            with mode_rules(), exact_refill_active(late_session):
                lotus_pick = exact_froggy_lotus_choice(
                    froggy_lotus_moves,
                    game_board,
                    special_game_board,
                    allow_square_matches=allow_square_matches,
                    mode=recognition.curr_mode,
                    explode_created_specials_immediately=specials_explode_immediately,
                    score_rally_values=score_rally_values,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                )
            if lotus_pick is not None:
                best_evaluation = lotus_pick[0]
                strategy_lab_label = f"[dopuna: {lotus_pick[1]}] " + strategy_lab_label
            elif request.exact_refill_skip is not None:
                request.exact_refill_skip("Froggy lotus: potez izlazi iz tacne dopune")
    # A blue extra played before the lotus (blue_extra_move_before_lotus_gate):
    # with the drop known, keep it only if it really keeps the turn and leaves
    # the lotus standing; otherwise collect the lotus now.
    elif (not protected_goal and selected_action == "move" and not request.points_only
            and not request.solo_cross_only and request.late_exact_refill is not None
            and decision_gate == "blue_extra_before_lotus_gate" and locals().get("froggy_lotus_moves")):
        try:
            late_session = request.late_exact_refill()
        except Exception as exc:  # The plain pick stays; never lose the move.
            late_session = None
            print(f"fast refill: late session failed: {type(exc).__name__}: {exc}")
        if late_session is not None:
            with mode_rules(), exact_refill_active(late_session):
                checked = exact_blue_extra_before_lotus_check(
                    best_evaluation,
                    froggy_lotus_moves,
                    game_board,
                    special_game_board,
                    allow_square_matches=allow_square_matches,
                    mode=recognition.curr_mode,
                    explode_created_specials_immediately=specials_explode_immediately,
                    score_rally_values=score_rally_values,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                )
            if checked is not None:
                if checked[0] is not best_evaluation:
                    decision_gate = "froggy_lotus_gate"
                    selection_candidates = froggy_lotus_moves
                best_evaluation = checked[0]
                strategy_lab_label = f"[dopuna: {checked[1]}] " + strategy_lab_label
            elif request.exact_refill_skip is not None:
                request.exact_refill_skip("extra pre lotusa: potez izlazi iz tacne dopune")
    # The ordinary move with the drop known (Solo Challenge): a known extra, the
    # booster's blue or a setup outranks the swap heuristics above. Booster and
    # perk decisions stay; so does a lotus, whose value this does not price.
    # So does a live Mixy Meow code: the re-simulation here does not know the
    # code, so it played a 3-blue match over code moves the bot scored 151-192
    # and spent the code by accident on other moves (2026-11-07 05:35-05:37).
    elif (not protected_goal and selected_action == "move" and not request.points_only and not request.solo_cross_only
            # A lotus that no move fires is not this move's value: the drop may
            # bring the match that fires it next (froggy_lotus_setup_choice).
            and (not any(SPECIAL_FROGGY_LOTUS in row for row in special_game_board)
                 or not locals().get("froggy_lotus_moves"))
            and not _mixy_code_live(locals().get("mixy_code_active"), mixy_meow_state)
            and (goal is None or goal.complete or (
                not booster_activation_ready and decision_gate in VISIBLE_EXTRA_PLAN_GATES
            ))
            and (not strategy_context.is_versus_2
                 or (request.late_exact_refill is not None and not request.extra_move_only and (
                     decision_gate == "score_gate"
                     or (decision_gate == "true_extra_gate" and not booster_activation_ready))))):
        exact_candidates = list(locals().get("prioritized_moves") or locals().get("ranked_moves") or [])
        if strategy_context.is_versus_2:
            # The ordinary ranking already used any session available up front.
            # For a late session, start with the same undecorated evaluations.
            raw_moves = {(item.candidate.start, item.candidate.target): item
                         for item in ranked_moves}
            exact_candidates = [
                raw_moves.get((item.candidate.start, item.candidate.target), item)
                for item in exact_candidates
            ]
        late_session, exact_setup = None, {}
        if request.late_exact_refill is not None:
            try:
                late_session = request.late_exact_refill()
            except Exception as exc:  # The plain pick stays; never lose the move.
                print(f"fast refill: late session failed: {type(exc).__name__}: {exc}")
            checked = fast_exact_refill_count(
                len(exact_candidates), getattr(turn_state, "time_left_seconds", None))
            top = exact_candidates[:checked]
            if _jelly_zone_cells:
                # The jelly plan needs swaps outside the zone that keep the turn,
                # which the conversion tier ranks below every conversion.
                top += [e for e in exact_candidates[checked:]
                        if jelly_conversion_tiles(e) <= 0 and getattr(e, "extra_moves", 0) > 0
                        ][:JELLY_DELAY_CANDIDATES]
                # The blue jelly setup also weighs paid swaps that leave the zone alone.
                top += [e for e in exact_candidates[checked:]
                        if jelly_conversion_tiles(e) <= 0 and not any(e is t for t in top)
                        ][:JELLY_BLUE_SETUP_CANDIDATES]
            exact_candidates = top
            exact_setup = {"setup_seconds": FAST_EXACT_REFILL_SETUP_SECONDS}
        # The match's rules again: UFO eyes and the rest change what a swap clears.
        with mode_rules(), (exact_refill_active(late_session) if late_session is not None
                            else contextlib.nullcontext()):
            exact_pick = exact_refill_choice(
                exact_candidates,
                game_board,
                special_game_board,
                allow_square_matches=allow_square_matches,
                mode=recognition.curr_mode,
                explode_created_specials_immediately=specials_explode_immediately,
                score_rally_values=score_rally_values,
                solo_goal=(strategy_context.solo_goal
                           if strategy_context.is_solo_challenge else None),
                booster_state=booster_state,
                turn_state=turn_state,
                strategy_context=strategy_context,
                include_future_value=request.include_future_value,
                **exact_setup,
            )
            if any(SPECIAL_FROGGY_LOTUS in row for row in special_game_board):
                lotus_setup = froggy_lotus_setup_choice(
                    exact_candidates,
                    game_board,
                    special_game_board,
                    allow_square_matches=allow_square_matches,
                    mode=recognition.curr_mode,
                    explode_created_specials_immediately=specials_explode_immediately,
                    score_rally_values=score_rally_values,
                    booster_state=booster_state,
                    turn_state=turn_state,
                    strategy_context=strategy_context,
                )
                if lotus_setup is not None:
                    exact_pick = lotus_setup
        if exact_pick is not None:
            best_evaluation = exact_pick[0]
            decision_gate = "exact_refill_priority"
            strategy_lab_label = f"[dopuna: {exact_pick[1]}] " + strategy_lab_label
        elif (best_evaluation is not None and decision_gate in VISIBLE_EXTRA_PLAN_GATES
                and getattr(best_evaluation, "solo_blue_plan_charge", None) is None
                and has_reliable_same_move_extra(best_evaluation)):
            # Refill off (Solo Challenge): plan the run of extras on the tiles
            # already on the board (player, 2026-11-07: "i kad nije dopuna").
            with mode_rules():
                planned = plan_visible_extra_sequence(
                    list(locals().get("prioritized_moves") or locals().get("ranked_moves") or []),
                    game_board,
                    special_game_board,
                    mode=recognition.curr_mode,
                    allow_square_matches=allow_square_matches,
                    score_rally_values=score_rally_values,
                    explode_created_specials_immediately=specials_explode_immediately,
                    strategy_context=strategy_context,
                    turn_state=turn_state,
                    booster_state=booster_state,
                )
            if planned is not None:
                best_evaluation = planned
                decision_gate = "visible_extra_plan_gate"
                strategy_lab_label = "[niz extra poteza] " + strategy_lab_label
    elif (selected_action == "activate_booster" and request.late_exact_refill is not None
          and (high_voltage_target is not None or magic_wand_target is not None)):
        try:
            late_session = request.late_exact_refill()
        except Exception as exc:
            late_session = None
            print(f"fast refill: late session failed: {type(exc).__name__}: {exc}")
        if late_session is not None:
            target_kwargs = dict(
                mode=recognition.curr_mode,
                allow_square_matches=allow_square_matches,
                score_rally_values=score_rally_values,
                include_future_value=request.include_future_value,
                explode_created_specials_immediately=specials_explode_immediately,
            )
            with mode_rules(), exact_refill_active(late_session):
                if high_voltage_target is not None:
                    high_voltage_target = choose_high_voltage_target(
                        game_board, special_game_board, **target_kwargs,
                        strategy_context=strategy_context, turn_state=turn_state,
                    ) or high_voltage_target
                else:
                    magic_wand_target = choose_magic_wand_target(
                        game_board, special_game_board, **target_kwargs,
                    ) or magic_wand_target
    elif request.exact_refill_skip is not None:
        mixy_move = (selected_action == "move"
                     and _mixy_code_live(locals().get("mixy_code_active"), mixy_meow_state))
        if ((selected_action in ("activate_booster", "activate_perk") or mixy_move)
                and request.late_exact_refill is not None):
            # A live Mixy code keeps its own pick, but its swipe (the code use
            # and re-deal, engine_mixy) is still checked: Color Climb
            # 2026-11-12 02:44-02:45, every code move was "preskocen".
            # Not for the choice: the resting read hands the board before the
            # booster/perk to the refill check (capture_resting), so the move
            # before it is checked too. Color Climb 2026-11-12 01:21-01:23:
            # 6 of 16 checkable moves were "preskocen" behind a booster.
            try:
                request.late_exact_refill()
            except Exception as exc:  # Never cost the booster.
                print(f"fast refill: board read before {selected_action} failed: "
                      f"{type(exc).__name__}: {exc}")
        request.exact_refill_skip(exact_refill_skip_reason(
            selected_action, request,
            lotus=any(SPECIAL_FROGGY_LOTUS in row for row in special_game_board),
            mixy=_mixy_code_live(locals().get("mixy_code_active"), mixy_meow_state)))

    debug_phase_start = time.perf_counter()
    if debug_enabled:
        _safe_debug_write(
            write_move_debug_report,
            debug_run_dir,
            debug_board_path,
            game_board,
            special_game_board,
            best_evaluation,
            selection_candidates,
            mode=recognition.curr_mode,
            profile=selected_profile,
            allow_square_matches=allow_square_matches,
            score_rally_values=score_rally_values,
            special_piece_mode=recognition.special_piece_mode,
            booster_action_mode=booster_action_mode,
            specials_explode_immediately=specials_explode_immediately,
            color_crush=color_crush,
            energized_colors=energized_colors,
            engine_charge_colors=request.engine_charge_colors,
            mushroom_multipliers=request.mushroom_multipliers,
            vertical_matches_destroy_color=vertical_matches_destroy_color,
            matches_destroy_color=matches_destroy_color,
            all_specials_lightning=all_specials_lightning,
            every_match_is_special=every_match_is_special,
            line_destruction=line_destruction,
            include_future_value=request.include_future_value,
            action=request.action,
            selected_action=selected_action,
            booster_detection=booster_detection,
            high_voltage_target=high_voltage_target,
            magic_wand_target=magic_wand_target,
            laser_beam_target=laser_beam_target,
            woolly_workout_target=woolly_workout_target,
            dragon_move=dragon_move,
            mixy_meow_state=mixy_meow_state,
            ufo_state=ufo_state,
            selected_perks=selected_perks,
            detected_perk_slots=request.detected_perk_slots,
            selected_perk_action=selected_perk_action,
            perk_candidates=perk_candidates,
            best_rejected_perk=best_rejected_perk,
            perk_slot_reasons=perk_slot_reasons,
            perk_last_chance=perk_last_chance_info,
            perk_slot_status=request.perk_slot_status,
            score_region_path=debug_score_path,
            score_region=debug_score_region,
            previous_run=previous_debug_run,
            observed_delta_path=observed_delta_path,
            booster_charge=request.booster_charge,
            booster_maximum=request.booster_maximum,
            remaining_moves=request.remaining_moves,
            total_rounds=request.total_rounds,
            current_round=request.current_round,
            round_source=request.round_source,
            blue_plan=decision_context.blue_plan if decision_context is not None else None,
            screen_state_read=request.screen_state_read,
            screen_state_image=request.screen_state_image,
            full_ranked_candidates=full_ranked_candidates,
            exploration=exploration_info,
            booster_state=booster_state,
            turn_state=turn_state,
            strategy_context=strategy_context,
            decision_gate=decision_gate,
            play_enabled=request.play_enabled,
            funky_cells=_funky_tile_cells,
            jelly_cells=_jelly_zone_cells,
            jelly_state=request.jelly_debug,
            hot_color_state=_hot_color_state,
            color_climb_state=request.color_climb_state,
            floor_lava_state=floor_lava_debug_state(request.floor_lava_columns),
        )
        if _ml_debug_payload is not None:
            _safe_debug_write(
                write_ml_recognition_debug_payload, debug_run_dir, _ml_debug_payload
            )
    # Outside the Debug guard on purpose. The weights that arbitrate points
    # against booster charge are calibrated from played moves, and a full Debug
    # run is far too heavy to leave on -- so the handful of numbers that
    # calibration actually reads are appended to one JSONL file on every move,
    # images and directories not involved. See move_telemetry.
    move_telemetry.record(
        screen_state_read=request.screen_state_read,
        evaluation=best_evaluation,
        strategy_mode=strategy_context,
        game_mode=recognition.curr_mode,
        selected_action=selected_action,
        decision_gate=decision_gate,
    )
    debug_ms += (time.perf_counter() - debug_phase_start) * 1000.0
    execute_phase_start = time.perf_counter()
    # Per-step timings inside the execute phase, keyed by step name. Filled by
    # the action branches below so timings.json can say WHERE execute time went
    # (the 2026-08-24 session measured a constant ~1.1s here with no obvious
    # sleeps on the plain-move path).
    _execute_breakdown = {}

    def log_phase_timings():
        execute_ms = (time.perf_counter() - execute_phase_start) * 1000.0
        total_ms = recognition_ms + compute_ms + debug_ms + execute_ms + planning_wait_ms
        if debug_enabled and debug_run_dir is not None:
            (debug_run_dir / "timings.json").write_text(
                json.dumps(
                    {
                        "recognition_ms": round(recognition_ms, 1),
                        "compute_ms": round(compute_ms, 1),
                        "debug_ms": round(debug_ms, 1),
                        "execute_ms": round(execute_ms, 1),
                        "planning_wait_ms": round(planning_wait_ms, 1),
                        "total_ms": round(total_ms, 1),
                        "recognition_breakdown": _recognition_breakdown,
                        "execute_breakdown": {
                            key: round(value, 1)
                            for key, value in _execute_breakdown.items()
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    if not request.play_enabled:
        # record() opened an entry for an action that is not being played;
        # closing it with the next move's meters would credit this decision
        # with whatever the next one does.
        move_telemetry.reset()
        log_phase_timings()
        return CheckBestMoveResult(
            best_move_text=f"{request.display_label}: saved",
            score_text="Score: debug",
            auto_signature=request.auto_signature,
            turn_consumed=False,
        )

    if request.refill_input_started is not None and selected_action != "none":
        request.refill_input_started(selected_action, refill_input_detail(
            selected_action, best_evaluation, selected_perk_action, booster_action_mode))

    if selected_action == "activate_perk":
        definition = PERK_DEFINITIONS.get(selected_perk_action.perk_key)
        perk_label = definition.label if definition else selected_perk_action.perk_key
        selected_perk_slot = resolve_perk_action_slot(selected_perk_action, selected_perks)
        played = execute_verified_perk_action(
            selected_perk_action,
            selected_perks,
            before_board=game_board,
            before_special_board=special_game_board,
            return_position=cursor_return_position,
            debug_run_dir=debug_run_dir if debug_enabled else None,
            mode=recognition.curr_mode,
            allow_square_matches=allow_square_matches,
            score_rally_values=score_rally_values,
            explode_created_specials_immediately=specials_explode_immediately,
            board_frame_provider=request.board_frame_provider,
            rules_context=mode_rules,
            strategy_context=strategy_context,
            turn_state=turn_state,
        )
        if not played:
            move_telemetry.reset()
        log_phase_timings()
        return CheckBestMoveResult(
            best_move_text=f"Perk: {perk_label}",
            score_text="Prioritet: efekat perka",
            clear_used_perk_key=selected_perk_action.perk_key if played else None,
            clear_used_perk_slot=selected_perk_slot if played else None,
            perk_attempted_slot=selected_perk_slot,
            auto_signature=request.auto_signature,
            # The verified perk executor already waited for the effect, stable
            # post-action frames and a rescan. Marking this as a recognition
            # wait would make the GUI schedule the same request again and could
            # play an unintended next move while it displays "skeniram".
            waiting_for_board=False,
            turn_consumed=bool(played and definition.requires_next_move),
        )

    if selected_action == "activate_booster":
        # Re-checked on the state as it is now, not the one the plan was built
        # from: a plan built just before the previous activation registered
        # would otherwise press the booster a second time.
        click_state = request.screen_state_read
        if request.fresh_screen_state_provider is not None:
            try:
                current_state = request.fresh_screen_state_provider()
            except Exception:
                current_state = None
            if current_state is not None:
                click_state = current_state
        fresh_booster_detection = revalidate_booster_activation_before_click(
            click_state
        )
        if fresh_booster_detection is None:
            move_telemetry.reset()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text="Booster: nije spreman",
                score_text="Score: waiting for state",
                auto_signature=request.auto_signature,
                waiting_for_board=True,
                turn_consumed=False,
            )
        booster_detection = fresh_booster_detection
        if booster_action_mode == BOOSTER_ACTION_HIGH_VOLTAGE:
            activate_high_voltage_booster(
                booster_detection,
                high_voltage_target.target_cell,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=f"High Voltage: {high_voltage_target.target_cell}",
                score_text="Score: " + str(round(high_voltage_target.score, 2)),
                auto_signature=request.auto_signature,
                booster_attempt=True,
                turn_consumed=False,
            )
        if booster_action_mode == BOOSTER_ACTION_MAGIC_WAND:
            activate_magic_wand_booster(
                booster_detection,
                magic_wand_target.target_cell,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=f"Magic Wand: {magic_wand_target.target_cell}",
                score_text="Score: " + str(round(magic_wand_target.score, 2)),
                auto_signature=request.auto_signature,
                booster_attempt=True,
                turn_consumed=False,
            )
        if booster_action_mode == BOOSTER_ACTION_LASER_BEAM:
            activate_laser_beam_booster(
                booster_detection,
                laser_beam_target.target_cell,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=f"Laser Beam: {laser_beam_target.target_cell}",
                score_text="Score: " + str(round(laser_beam_target.score, 2)),
                auto_signature=request.auto_signature,
                booster_attempt=True,
                turn_consumed=False,
            )
        if booster_action_mode == BOOSTER_ACTION_WOOLLY_WORKOUT:
            activate_woolly_workout_booster(
                booster_detection,
                woolly_workout_target.target_cell,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=f"Woolly Workout: {woolly_workout_target.target_cell}",
                score_text="Score: " + str(round(woolly_workout_target.score, 2)),
                auto_signature=request.auto_signature,
                booster_attempt=True,
                turn_consumed=False,
            )
        if booster_action_mode == BOOSTER_ACTION_DRAGON:
            click_booster_activate(
                booster_detection,
                return_position=cursor_return_position,
                return_delay=HIGH_VOLTAGE_PROMPT_DELAY_SECONDS,
                restore_cursor=False,
            )
            dragon_start, dragon_direction = oriented_swipe(dragon_move)
            play_best_move_with_cursor_restore(
                dragon_start,
                dragon_direction,
                dragon_move.score,
                return_position=cursor_return_position,
            )
            clear_booster_ready_latch()
            log_phase_timings()
            return CheckBestMoveResult(
                best_move_text=(
                    f"Dragon: {dragon_start}, "
                    f"{dragon_direction}"
                ),
                score_text="Score: " + str(round(dragon_move.score, 2)),
                auto_signature=request.auto_signature,
                booster_attempt=True,
            )
        click_booster_activate(
            booster_detection,
            return_position=cursor_return_position,
        )
        clear_booster_ready_latch()
        log_phase_timings()
        return CheckBestMoveResult(
            best_move_text="Booster: activate",
            score_text="Score: booster",
            auto_signature=request.auto_signature,
            booster_attempt=True,
            turn_consumed=False,
        )

    if best_evaluation is None:
        log_phase_timings()
        return CheckBestMoveResult(
            best_move_text=(
                f"Perk {request.forced_perk_slot}: unavailable"
                + (
                    f" ({manual_perk_failure_reason})"
                    if manual_perk_failure_reason
                    else ""
                )
                if request.forced_perk_slot in (1, 2)
                else f"{request.display_label}: {extra_move_hint or 'none'}"
            ),
            score_text="Score: 0",
            auto_signature=request.auto_signature,
            turn_consumed=False,
        )

    # Swipe the tile the move was chosen for, not whichever end the candidate
    # generator happened to put first -- the game credits the match to the tile
    # you drag (see `oriented_swipe`).
    swipe_start, swipe_direction = oriented_swipe(best_evaluation)
    best_move = (best_evaluation.score, swipe_start, swipe_direction)

    _t_step = time.perf_counter()
    move_played = play_best_move_with_cursor_restore(
        best_move[1],
        best_move[2],
        best_move[0],
        return_position=cursor_return_position,
    )
    try:
        strategy_lab_live.record_execution(
            strategy_lab_token, move_played, request.fresh_screen_state_provider
        )
    except Exception:
        pass  # A diagnostic write must never change a sent native action.
    _execute_breakdown["play_ms"] = (time.perf_counter() - _t_step) * 1000.0
    _execute_breakdown.update(_last_play_step_timings)
    _t_step = time.perf_counter()
    if move_played:
        release_mixy_code_latch_for_move(best_evaluation)
    if (
        move_played
        and getattr(best_evaluation, "mixy_code_color", None) is not None
        and not _mixy_refund_watch["burned"]
        and turn_state.remaining_moves is not None
        # Only a refund-only promise can convict the refund: with a real
        # match-4 in the same swipe a lost turn blames the cascade prediction,
        # not the code credit.
        and max(
            getattr(best_evaluation, "extra_moves", 0.0),
            getattr(best_evaluation, "direct_extra_moves", 0.0),
        )
        <= 1.0
    ):
        _note_mixy_refund_promised(turn_state.remaining_moves)
    if (
        move_played
        and recognition.curr_mode is GameMode.FLOOR_IS_LAVA
        and request.floor_lava_columns is None
    ):
        # With the engine's own counter in hand there is nothing to carry over:
        # the next snapshot states the marks instead of predicting them.
        commit_floor_lava_evaluation(best_evaluation)
    if move_played and recognition.curr_mode is GameMode.BOUNTY:
        commit_bounty_evaluation(best_evaluation)
    if move_played:
        try:
            record_final_handover_perk_audit(
                turn_state=turn_state,
                strategy_context=strategy_context,
                played_evaluation=best_evaluation,
                selected_perks=selected_perks,
                perk_slot_status=request.perk_slot_status,
                perk_slot_reasons=perk_slot_reasons,
                mode=recognition.curr_mode,
                debug_run_dir=debug_run_dir if debug_enabled else None,
            )
        except Exception:
            # The audit is measurement only; it must never fail a sent move.
            pass
    # With a memory-sourced score the terminal OCR observation has nothing to
    # add: PlayerModel.score is exact and _fill_memory_score_delta closes the
    # delta without a crop. Skipping it also frees the ~1.2s it blocked the
    # auto loop for after nearly every Solo Challenge move.
    if (
        move_played
        and not score_state_is_from_memory
        and _should_capture_final_debug_observation(
            debug_enabled,
            debug_run_dir,
            turn_state,
            best_evaluation,
        )
    ):
        try:
            capture_final_debug_observation(
                debug_run_dir,
                score_region=debug_score_region,
            )
        except Exception:
            # Final diagnostics must never turn a successfully sent move into
            # a gameplay failure.
            pass
    _execute_breakdown["post_play_ms"] = (time.perf_counter() - _t_step) * 1000.0
    log_phase_timings()
    return CheckBestMoveResult(
        best_move_text=f"{strategy_lab_label}{request.display_label}: {best_move[1]}, {best_move[2]}",
        score_text="Score: " + str(round(best_move[0], 2)),
        auto_signature=request.auto_signature,
        ufo_abductions=count_ufo_abductions(best_evaluation) if move_played else 0,
    )
