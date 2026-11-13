"""Memory-only Match Masters cockpit.

A deliberately small sibling of :mod:`gui`: the board, the score, the moves and
the booster meter all come from the read-only Frida/IL2CPP snapshot, so nothing
here scans pixels or reads text off the screen. Move selection and the swipe
itself are the very same ``runtime.run_check_best_move_request`` the main GUI
uses -- only the input differs.

Run it with:  python memory_gui.py
"""

from __future__ import annotations

import copy
import functools
from collections import deque
import json
import re
from dataclasses import replace
from datetime import datetime
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import pyautogui
from PyQt5 import QtCore, QtGui, QtWidgets

import board_profiles
import board_source
from solo_challenge import SoloGoalState, goal_from_snapshot
import matchmasters_launcher
import recognition
import runtime
import swipe_recorder
from gui_state_panel import MemoryStatePanel
from gui_theme import apply_theme
from auto_plan import AutoPlan, plan_key_difference, snapshot_plan_key
from board_profiles import (
    BOARD_PROFILES,
    BoardCalibrationError,
    save_board_calibration,
    validate_board_calibration,
)
from board_source import BOARD_SOURCE_MEMORY
import free_swap
import square_solo_live
from square_solo_live import LiveSquareSolo
from refill_monitor import RefillMonitorClient, RefillTally
from simulator_capture import (
    MUTATION_DESTROY_COLUMN_ON_VERTICAL_MATCH,
    MUTATION_DESTROY_ROW_ON_HORIZONTAL_MATCH,
    MUTATION_MATCHES_CREATE_SPECIALS,
    MUTATION_MATCHES_DESTROY_COLOR,
    MUTATION_SPECIALS_AUTO_EXPLODE,
    MUTATION_VERTICAL_MATCH_DESTROY_COLOR,
    active_mutation_types,
)
from research_recorder import ResearchRecorder
from ml_recognition_runtime import ML_RECOGNITION_ONLY
from move_strategy import (
    BLOCKED,
    BLUE,
    BoosterState,
    ENERGIZED_COLOR_LABELS,
    cleo_odds_active,
    exact_refill_active,
    CHEST,
    FREE_MOVE_BOARD_ABILITIES,
    froggy_gather_config_from_params,
    DISCO_BALL,
    EMPTY,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    SPECIAL_CLEO_BUG,
    SPECIAL_MUSHROOM,
    WHITE,
    cleo_swipe_odds,
    YELLOW,
    STRATEGY_SOLO_6,
    STRATEGY_VERSUS_2,
    GameMode,
    MixyMeowState,
    UFO_ALLOW_PICKING_BLUES,
    UFO_COLORS_BY_ACTIVATION,
    UFO_MAX_COLORS_PER_MOVE,
    UFO_MAX_EYES,
    UFO_MAX_PASSIVE_ACTIVATES,
    UfoState,
    normalize_energized_colors,
)
from runtime import (
    BOOSTER_ACTION_NONE,
    BOOSTER_ACTION_UFO,
    BOOSTER_ACTION_OPTIONS,
    BOOSTER_MAX_CHARGE,
    SCORE_SOURCE_MEMORY,
    CheckBestMoveRequest,
    run_check_best_move_request,
)
from tools import matchmasters_board_reader as reader
from window_geometry import client_rect_for_window, find_bluestacks_window

PROJECT_ROOT = Path(__file__).resolve().parent

# Where a match whose ruleset the bot does not know gets recorded. One folder
# per rules id, holding the raw snapshots: that is exactly the evidence needed
# to work out what the mode does (see docs/game_mode_rules.md), and it can only
# be collected while the match is actually being played.
UNMAPPED_MODE_DIR = PROJECT_ROOT / "Debug" / "unmapped_modes"
# Enough to cover a whole turn's worth of board states without filling the disk
# if the mode is played for an hour.
UNMAPPED_MODE_MAX_SNAPSHOTS = 60

# Per-run recording of the memory frames an action produces (Debug only). The
# settled board hides the effect; these frames hold the board mid-cascade,
# where the cleared cells are still empty.
MEMORY_FRAMES_FILENAME = "memory_frames.jsonl"
# Faster than the 250 ms play poll so a single clear is not missed between two
# frames. 100 ms was still too coarse for the events that matter most: a Froggy
# lotus gathers its blob, destroys it and leaves a special inside one animation,
# and across eight recorded lotus moves that moment landed between two polls in
# seven of them. Trace mode is a read-only observer and only runs with Debug on,
# so the cost of going faster is disk, not risk -- one frame is ~23 KB.
TRACE_POLL_MS = 30

# GameState values worth acting on; see Match3Engine.GameState.
GAME_STATE_MOVE_PLAYING = -5
# The board is final the moment the match starts (-2) and does not change
# while the game waits for the first turn (-3), so planning starts there
# too; the turn-phase gates below still decide *when* the move is played.
GAME_STATES_CAN_PREPARE = frozenset((-2, -3, -4, -5, -6, -7))
# Start-up, match start and waiting for the turn: the turn countdown is not
# running yet, and the engine's remaining_time reads 0 there.
GAME_STATES_CLOCK_NOT_STARTED = frozenset((-1, -2, -3))

# How long a pressed move button stays a standing request. Pressed before the
# game accepts a move it is played the moment the game does; a game that does
# not get there within this window was not the one the click was meant for,
# and the request is dropped instead of spinning forever.
REQUESTED_ACTION_TIMEOUT_SECONDS = 10.0
BOARD_RECORD_WAIT_SECONDS = 3.0
# Fast refill (Versus, Showdown, Party): moves past the played one the exact
# refill follows when re-checking the top moves. Solo Challenge keeps the default.
FAST_REFILL_FOLLOWED_PLIES = 2
# Default for modes other than the timed Rumble / Showdown / Party races.
FULL_EXACT_REFILL_EVERYWHERE = True
VERSUS_REFILL_FOLLOWED_PLIES = 3


# How long the late exact refill gives the planned board to be called stable.
LATE_REFILL_SETTLE_SECONDS = 0.6
# exact_refill_session reasons for a board read while the game still resolved.
UNSETTLED_REFILL_REASONS = ("tabla jos nije mirna", "igra jos razresava potez")


def _same_planned_board(latest, planned) -> bool:
    """The settled snapshot is the board a fast plan was computed on."""
    return (latest.get("board") == planned.get("board")
            and latest.get("special_board") == planned.get("special_board")
            and (latest.get("state") or {}).get("moves") == (planned.get("state") or {}).get("moves"))
GAME_STATE_LABELS = {
    -1: "Starting",
    -2: "Match start",
    -3: "Waiting for turn",
    -4: "Turn in progress",
    -5: "Move",
    -6: "Processing move",
    -7: "End of move",
    -8: "End of turn",
    -9: "Waiting for turn time",
    2: "Player 1 wins",
    3: "Player 2 wins",
    4: "Technical win 1",
    5: "Technical win 2",
    6: "Forfeit - player 1 wins",
    7: "Forfeit - player 2 wins",
}

# MatchRulesModel.id as the engine reports it, mapped onto our strategy modes.
# Ids carry league suffixes ("color-crystals-master-league"), so matching is by
# prefix. An unlisted id plays as GameMode.NONE and says so in the UI.
#
# Two sources of truth, no guessing:
#   * the shipped `Match-Masters/TextAsset/Constants` `general.matchRules` table,
#     which lists each rules id together with its `boardModelName`;
#   * the live `ShowSettings.matchRules` payloads captured on 2026-08-15, which
#     show that a league match reports `<stageId>-master-league` and that the
#     engine names each arena's board model after the arena itself
#     (`plunder-pirates-master-league` -> boardModelName 8 = PlunderPiratesBoard,
#     `dustville-duel-master-league` -> 4 = DustvilleDuelBoard).
#
# Arenas whose board model the bot does not implement (cloud-city, frozen-feud,
# vegas-views, buried-treasure, stock-market, rocket-riot, anti-gravity, ...)
# are deliberately absent: playing them as GameMode.NONE is honest, mapping them
# onto a lookalike mode is not.
# See docs/game_mode_rules.md for the full table and the open questions.
# LightsUpBoard's own board model number, used to recognise a Lights Up arena
# whose ruleset id has never been captured.
LIGHTS_UP_BOARD_MODEL = 37
COLUMN_MANIA_BOARD_MODEL = 32

# Solo exact plans: read spawn weights + engine RNG from memory before each
# move and let the exact-refill planner pick the swap (square_solo_live).
SQUARE_SOLO_EXACT_PLAN = False
# Off since 2026-11-10: the planner plays swaps only, with the booster meter at
# 0 and no perks, so once the last Solo Challenge target was passed it took
# over and threw away charge (10:37:14 an 18-point swap over the bot's 150.9
# blue/special pick) while spending its 6 s budget on every move (10-15 s per
# move instead of ~5). The bot's own ranking keeps the exact refill.
COLOR_CRUSH_SOLO_EXACT_PLAN = False
RAINBOW_EXACT_PLAN = True

RULES_ID_TO_MODE = {
    # --- board-model modes, keyed by the arena the engine names them after ---
    # Captured live 2026-08-21: id "arcade-man", title "Arcade Man",
    # boardModelName 27 = MatchLineBoard. Both line-destruction rule flags are
    # *false* on the ruleset -- the sweep lives in the board model -- so nothing
    # but the id maps this mode (Debug/unmapped_modes/arcade-man).
    "arcade-man": GameMode.ARCADE_MAN,            # MatchLineBoard (27)
    "bulls-eye": GameMode.BOUNTY,                 # BullseyeBoard
    # Captured live 2026-08-17: id "candy-world-master-league", boardModelName 2,
    # three SlotValue 16 candy tiles on the board (Debug/unmapped_modes).
    "candy-world": GameMode.CANDY_WORLD,          # CandyWorldBoard (2)
    "bullseye-bash": GameMode.BOUNTY,             # BullseyeBoard
    "color-crystals": GameMode.COLOR_CRYSTALS,    # ColorBombBoard
    # Captured live 2026-08-21: id "color-crush", title "Color Crush",
    # boardModelName 28 = ColorCrushBoard. The capture also shows the rule
    # itself: the move at 09:14:20 wiped all 8 green tiles off the board for
    # 16 points (2 per cell) instead of the 3 a plain match clears
    # (Debug/unmapped_modes/color-crush).
    "color-crush": GameMode.COLOR_CRUSH,          # ColorCrushBoard (28)
    "crazy-columns": GameMode.CRAZY_COLUMNS,      # CrazyColumnsBoard
    # Mapped 2026-08-22 from 60 captured frames plus the compiled hooks:
    # unlike Crazy Columns' fixed ramp, every column starts at x1 and
    # onMoveEnd raises the ones the move cleared something in.
    "column-mania": GameMode.COLUMN_MANIA,        # ColumnManiaBoard (32)
    "crystal-cave": GameMode.PURPLE_GEM,          # CrystalCaveBoard
    # Mapped 2026-08-23 from the compiled hooks plus 1285 recorded snapshots.
    # Both are built out of PlayerModel.scoreMultiplier; the difference is how
    # it is earned -- per move played, or per destroyed purple combo.
    "moves-multiplier": GameMode.MOVES_MULTIPLIER,        # (34)
    "multiplier-madness": GameMode.MULTIPLIER_MADNESS,    # (22)
    # Captured live 2026-08-25 (Debug/unmapped_modes/color-climb, 420 frames):
    # id "color-climb", boardModelName 35, board field `availableColors`. Two
    # dealt colours per player raise PlayerModel.scoreMultiplier, decoded from
    # libil2cpp.so 2026-09-13 (see docs/game_mode_rules.md).
    "color-climb": GameMode.COLOR_CLIMB,                  # RainbowMultiplierBoard (35)
    "drill-down": GameMode.DRILLIN_DOWN,          # DigDownBoard
    # Captured live 2026-08-19: id "dustville-duel-master-league",
    # boardModelName 4, three replenishing "wanted" tiles as SlotValue 16.
    "dustville-duel": GameMode.DUSTVILLE_DUEL,    # DustvilleDuelBoard (4)
    "drillin-down": GameMode.DRILLIN_DOWN,        # DigDownBoard
    "extra-moves": GameMode.XTRA_MOVES,           # ExtraMovesBoard
    # Captured live 2026-08-19: id "the-floor-is-lava", boardModelName 36, and
    # a board object whose only state is ColumnsEruptionDictionary /
    # distinctXValues / resetGroundOnTurnEnd -- the per-column match counter the
    # in-game description states as "match twice on the same column to destroy
    # it".
    "the-floor-is-lava": GameMode.FLOOR_IS_LAVA,  # FloorIsLavaBoard (36)
    "fireworks-festival": GameMode.FIREWORKS,     # FireworksFestivalBoard
    "funky-tiles": GameMode.FUNKY_TILES,          # FunkyTilesBoard
    "hot-color": GameMode.HOT_COLOR,              # HotColorBoard
    "jungle-rumble": GameMode.GREEN_LEAF,         # JungleRumbleBoard
    "laser-matches": GameMode.LASER,              # LightsabersBoard (18)
    # Captured live 2026-08-21: id "lights-up", boardModelName 37, board fields
    # CurrentActiveColumn / RandomColumnChange. Every combo that touches the
    # lit column is +1 to PlayerControl.ScoreMultiplier, which multiplies
    # everything scored afterwards (see docs/game_mode_rules.md).
    "lights-up": GameMode.LIGHTS_UP,             # LightsUpBoard (37)
    # Captured live 2026-08-19: id "mighty-mushrooms", boardModelName 30, the
    # same SlotValue 19 mushrooms as board 29 -- confirmed to be the same mode
    # in a different arena. `is_square_match` comes from the rules by itself.
    "mighty-mushrooms": GameMode.MULTIPLIER_MUSHROOMS,      # MightyMushroomsBoard (30)
    # Captured live 2026-08-17: id "multiplier-mushrooms", boardModelName 29.
    "multiplier-mushrooms": GameMode.MULTIPLIER_MUSHROOMS,  # MultiplierMushroomsBoard (29)
    "plunder-pirates": GameMode.CHEST,            # PlunderPiratesBoard
    # --- rule-flag modes: one MatchRulesModel field, no board model ---
    "blow-em-up": GameMode.BLOW_EM_UP,            # specialsAutoExplode
    "energy": GameMode.SHARED_ENERGY,             # bothColorsChargeEnergy
    "shared-energy": GameMode.SHARED_ENERGY,      # bothColorsChargeEnergy
    "infinite-moves": GameMode.INFINITE_MOVES,    # reduceMoveOnValidSwap=false
    "lightning-strike": GameMode.LIGHTNING_STRIKE,  # allSpecialsLightning
}

# BoardModelName -> GameMode, straight from the enum dumped out of the live
# IL2CPP metadata (data/il2cpp_symbols.json, 2026-08-21). This is the stronger
# of the two identifiers: `MatchRulesModel.boardModelName` is a number the
# engine sets itself, while the ruleset id is a string that has to be captured
# once per arena before RULES_ID_TO_MODE can carry it. Consulted only when the
# id says nothing, so a hand-mapped id still wins.
#
# Absent on purpose: 1 (BoardModel) and 11 (RainbowBoard) have no class of their
# own in the metadata -- they *are* the plain board -- so "no special rules" is
# the correct answer for them, not "unmapped". The board models the bot has no
# strategy for are listed in docs/game_mode_logic_from_code.md.
BOARD_MODEL_TO_MODE = {
    2: GameMode.CANDY_WORLD,            # CandyWorldBoard
    3: GameMode.PURPLE_GEM,             # CrystalCaveBoard
    4: GameMode.DUSTVILLE_DUEL,         # DustvilleDuelBoard
    6: GameMode.FROZEN_FEUD,            # FrozenFeudBoard
    7: GameMode.GREEN_LEAF,             # JungleRumbleBoard
    8: GameMode.CHEST,                  # PlunderPiratesBoard
    9: GameMode.FIREWORKS,              # FireworksFestivalBoard
    10: GameMode.VEGAS_VIEWS,           # VegasViewsBoard
    12: GameMode.FUNKY_TILES,           # FunkyTilesBoard
    13: GameMode.BOUNTY,                # BullseyeBoard
    14: GameMode.XTRA_MOVES,            # ExtraMovesBoard
    15: GameMode.BURIED_TREASURE,       # BuriedTreasureBoard
    16: GameMode.COLOR_CRYSTALS,        # ColorBombBoard
    17: GameMode.DRILLIN_DOWN,          # DigDownBoard
    18: GameMode.LASER,                 # LightsabersBoard
    19: GameMode.CRAZY_COLUMNS,         # CrazyColumnsBoard
    21: GameMode.HOT_COLOR,             # HotColorBoard
    23: GameMode.VERTICAL_RUSH,         # VerticalRushBoard
    26: GameMode.ENERGIZED,             # EnergizedBoard
    27: GameMode.ARCADE_MAN,            # MatchLineBoard
    28: GameMode.COLOR_CRUSH,           # ColorCrushBoard
    29: GameMode.MULTIPLIER_MUSHROOMS,  # MultiplierMushroomsBoard
    30: GameMode.MULTIPLIER_MUSHROOMS,  # MightyMushroomsBoard -- same mushrooms
    22: GameMode.MULTIPLIER_MADNESS,    # MultiplierMadnessBoard
    COLUMN_MANIA_BOARD_MODEL: GameMode.COLUMN_MANIA,  # ColumnManiaBoard (32)
    34: GameMode.MOVES_MULTIPLIER,      # EveryMoveIncreaseScoreMultiplierBoard
    35: GameMode.COLOR_CLIMB,           # RainbowMultiplierBoard
    33: GameMode.ZANY_ZAPPERS,          # ZanyZappersBoard
    36: GameMode.FLOOR_IS_LAVA,         # FloorIsLavaBoard
    LIGHTS_UP_BOARD_MODEL: GameMode.LIGHTS_UP,  # LightsUpBoard (37)
}

# Rules ids that need no strategy of their own: their whole content is board
# geometry, colour count, timing or per-colour points, all of which the memory
# snapshot already carries (board size and blocked cells come from the cells,
# per-colour points from SlotModel.score via the score legend). They play as
# GameMode.NONE on purpose, and the UI says "bez posebnih pravila" rather than
# "nemapiran" so an unknown id still stands out.
# MatchRulesModel flags that *are* a mode on their own. Only consulted for a
# ruleset id the table above does not cover: a board model is the stronger
# statement, and the mode entry can only carry one of the two.
RULE_FLAG_TO_MODE = (
    # "Every match creates a special piece" -- Special O'Rama.
    ("every_match_is_special", GameMode.SPECIAL_O_RAMA),
    ("everyMatchIsSpecial", GameMode.SPECIAL_O_RAMA),
)

# True in essentially every match, so listing them says nothing about the mode.
# Measured on a live Funky Tiles match 2026-08-17, where the full sweep reports
# 137 fields: without this the "what is on" line is mostly timer plumbing.
RULE_FLAGS_NOT_WORTH_REPORTING = frozenset({
    "is_timer", "isTimer",
    "pauseTimerForAnimations",
    "pauseTimerForBoosters",
    "conditionalTimeBonus",
    "soloContinueAfterLastTarget",
    "soloOverflowPastTarget",
    # Reported by RULE_FLAGS_NOTABLE_WHEN_OFF when they matter, i.e. when off.
    "reduce_move_on_valid_swap", "reduceMoveOnValidSwap",
    "extra_move_enabled", "extraMoveEnabled",
})

# The mirror image: rules whose *off* state is the thing worth knowing, because
# on is the default everywhere. Reported as "!name" so the line says what the
# match actually does, not only what it adds.
RULE_FLAGS_NOTABLE_WHEN_OFF = (
    # false = a valid swap does not spend a move (Infinite Moves).
    ("reduce_move_on_valid_swap", "reduceMoveOnValidSwap"),
    # false = a match-4+ grants no extra move at all.
    ("extra_move_enabled", "extraMoveEnabled"),
)

# Match3Engine.MutationLabMutationType, recovered from the shipped
# global-metadata string table, whose enum member names are stored in
# declaration order. Three live values anchor the numbering (a 2026-08-19
# Mutation Lab match): 5 while purple was the boosted colour and the score
# legend read purple 3, 17 for the pick the player described as "destroy two
# colours this move", and 30 for Vertical Matches Destroy Color.
#
# Only the members the simulator can act on are listed. One member between
# DestroyColors and VerticalMatchDestroyColor has no name in that run of the
# string table -- almost certainly `Painter`, whose name is stored elsewhere
# because the table de-duplicates -- so numbers above 28 rest on the type-30
# anchor rather than on counting, and nothing below is derived by counting past
# it. See docs/mutation_lab.md.
#
# 2026-08-20 correction. A Mutation Lab match whose four permanent picks read
# "3 specials every turn", "Yellow matches charge booster", "Horizontal match
# explodes row" and "2 Multiplier Mushrooms every turn" reported types
# [10, 1, 22, 10]. The two 10s are the two AddSpecials picks -- a mushroom is
# a board special like any other, so it needs no type of its own -- and 1 is
# the yellow charge. That leaves 22 for the horizontal pick, with no vertical
# mutation on offer anywhere in the match, so 22 is DestroyRowOnHorizontalMatch
# and the string-table numbering is one too low from somewhere below 21 upward.
# The vertical twin therefore has no defensible number and is left unset: a
# vertical pick was left unrouted until one was seen live -- which happened the
# same evening at 23:10:01: type 23 arrived and the engine's own
# `destroyColumnOnVerticalMatch` flipped true in the same frame, so the pair is
# 22/23. Both halves are now engine-confirmed rather than counted.
#
# The shift is local, not global. Type 16 (BoosterCostAddition) and type 31
# (EveryMatchTempIncreaseMultiplier) both sit exactly where the string table
# puts them, confirmed live -- 16 by energyToAbility dropping 7->3 for the
# round, 31 by its ThisRound/baseWeight-8/trophies-3800 triple matching one
# single pvp catalogue entry. So only the 21..29 window is off by one, and
# VerticalMatchDestroyColor keeps its own live anchor at 30.
MUTATION_COLOR_CHARGES_ENERGY = 1
MUTATION_COLOR_POINTS_INCREASE = 5
MUTATION_ADD_SPECIALS = 10
# "Matches explode color": the same whole-colour wipe as 30 with the vertical
# condition dropped -- a separate mutation, and the catalogue blocks the two
# against each other. Confirmed live 2026-08-19 23:23: picked as a permanent
# mutation with config.color None, after which whole colours started vanishing
# from the board (14 and 16 tiles at once), and no rules field mirrors it -- so
# this routing is the only thing that tells the simulator about it.

# Serbian colour names, shared by the score legend and the mutation readout.
COLOR_NAMES = {
    GREEN: "zelena",
    YELLOW: "zuta",
    PURPLE: "ljubicasta",
    ORANGE: "narandzasta",
    BLUE: "plava",
    RED: "crvena",
}

# Names for the "Mutacije" readout, so a wrong pin shows up as a mismatch
# against the game's own wording instead of hiding inside the simulation.
# Deliberately incomplete: 17-21 and 24-29 are the stretch the 2026-08-20
# correction puts in doubt, so they print as "tip N (?)" rather than as a guess.
#
# One more data point for that stretch, from a solo Mutation Lab 2026-08-22
# (Debug/unmapped_modes/mutation-lab-solo-mode, 60 frames): type 19 ran with
# config.color 4 (purple), durationType 0 (Instant) and isRepeatable true.
# Walking data/mutation_lab_catalogue.json in declaration order puts Painter at
# 19 and ConvertToSpecial at 20, but the catalogue ships Painter in blue only,
# while ConvertToSpecial has a purple variant (convert-purple-to-bombs) that is
# also Instant and repeatable -- so either the two are swapped in the enum or
# the colour is not the piece colour. Two candidates is still a guess, so 19
# stays unnamed until a run shows what it does to the board.
MUTATION_TYPE_NAMES = {
    1: "boja puni buster",
    2: "kombo boje puni buster",
    3: "mec boje pravi specijal",
    4: "mec boje rusi liniju",
    5: "boja vredi vise poena",
    6: "specijali odmah eksplodiraju",
    7: "svaki mec pravi specijal",
    8: "vece bombe",
    9: "perkovi dopunjeni",
    10: "dodaj specijale (i pecurke)",
    11: "dodaj poene",
    12: "vise bombi",
    13: "vise plavih",
    14: "extra-move plocice",
    15: "broj boja",
    # 2026-08-19 23:03: this pick dropped energyToAbility 7 -> 3 for both
    # players and put it back when the round ended, which is exactly
    # BoosterCostAddition -- so the string table is right here, and only the
    # 21/22 pair is known to be off.
    16: "jeftiniji buster",
    22: "horizontalni mec rusi red",
    23: "vertikalni mec rusi kolonu",
    # 24, 25, 27-29 are derived from the reconciled numbering below, not seen
    # live yet; none of them is routed, so a wrong name here only misprints the
    # readout. 26 is live-confirmed ("purple matches increase multiplier",
    # config.color 7 = purple).
    24: "next move x10",
    25: "svaki mec rusi boju",
    26: "mec boje dize mnozilac",
    27: "puni buster",
    28: "vertikalni mec dize mnozilac",
    29: "unisti boje",
    30: "vertikalni mec rusi boju",
    # Confirmed on screen ("all matches increase multiplier") and in memory:
    # while it was live, PlayerModel.scoreMultiplier climbed one per match and
    # reset to 0 when the round ended. Unrouted -- the simulator has no
    # multiplier term -- but it mildly favours multi-match moves, which the
    # cascade scoring already prefers.
    31: "svaki mec dize mnozilac (nepodrzano)",
}

RULES_ID_NO_STRATEGY_CHANGE = frozenset({
    "academy-room",
    "best-turn-wins",     # winByBestRound -- scoring objective, see docs
    "blitz",              # timePerTurn only
    # 180 live frames 2026-08-18/19: the board seeds and replenishes ordinary
    # Bombs (SlotValue 6, no combo, no owning player) and carries nothing else
    # of its own -- `biggerBombArea` is false, so they are the 3x3 blast the
    # simulator already resolves. Reading the board is the whole support needed.
    "bombs-away",
    "classic",
    "five-colors",        # colorsCount 5
    "hammer-time",        # boardAbilities only
    "ice-cream",          # colorScoreOverride
    "match-and-hatch",    # the egg is the hatch animation, not a piece (see docs)
    "mini-master",        # boardSize 6
    # 60 live frames 2026-08-19: no board piece of its own at all, every
    # non-plain slot is a player-created special. Its content is the global
    # PlayerModel.scoreMultiplier climbing 1..7, which scales every move's
    # points equally and so cannot reorder them, plus `isSquareMatch`, which
    # the rules already switch on by themselves.
    "multiplier-madness",
    "rainbow",            # colorScoreOverride
    # 180 live frames 2026-08-22, boardModelName 20 (`StockMarketBoard`) -- the
    # same board as "stock-market" below under a second arena id, which is why
    # that entry alone did not cover it. `board_fields` names the whole
    # mechanic: `newScoreOverrides` (Dictionary<SlotColor,int>) rewritten every
    # move, capped by `MAX_SCORE` / `ENERGY_COLORS_MAX_SCORE`. The bot is
    # reactively correct because the score legend is read live each move; what
    # is missing is planning ahead for the *next* rewrite, which is unknowable
    # from a settled board anyway. `specialsAutoExplode` was on in 60 of the
    # frames and reaches the simulator straight from the rules (see the
    # `specials_explode_immediately` wiring), so it needs no mode entry either.
    "score-market",
    "shuffle",            # reshuffleEveryTurn
    "spotlight-stars",
    # 234 live frames 2026-08-22: `isSquareMatch` is the only flag it turns on
    # and the rules carry it by themselves, board model 0 (the plain board).
    "square-match",
    "stock-market",       # colorScoreOverride + ScoreLegend indicator
    "super-sized",        # boardSize 9 + colorsCount 7
    "teleport",           # boardAbilities only
    "three-moves",        # movesPerTurn 3
    "tribal-trouble",
    "win-by-rounds",      # winByRounds -- scoring objective, see docs
    "yin-yang",           # customCells
})

# Rulesets whose rules are real and are handled, but not through the mode entry.
# They must not be filed under "bez posebnih pravila" (that would claim they
# change nothing) and must not be recorded as unmapped either: the label says
# where their rules actually come from.
#
# Matched by prefix, same as the set above, so "mutation-lab-pvp-mode" and
# "mutation-lab-solo-mode" (240 live frames 2026-08-22) are both covered.
RULES_ID_HANDLED_OUTSIDE_MODE = {
    # Every rule of a Mutation Lab match is a picked mutation, read live from
    # GameLogic.mutationsActivatedList and routed into the simulator one type at
    # a time (see MUTATION_TYPE_NAMES and _refresh_mutations). The ruleset id
    # itself carries nothing beyond `isMutationLab`.
    "mutation-lab": "mutacije",
}


# PlayerClientControl.PlayerType
PLAYER_TYPE_LOCAL = 0

# Match3Engine.PVPMode / RumbleType
PVP_MODE_PVP = 0
PVP_MODE_SOLO = 1
PVP_MODE_RUMBLE = 2
RUMBLE_TYPE_LABELS = {0: "None", 1: "Classic", 2: "Showdown", 3: "Party"}
# Party draws a wider perk strip, which the slot template matcher has to know.
RUMBLE_TYPE_PARTY = 3
# How long a perk-verification frame waits for the agent's dump. Short on
# purpose: a missed frame only costs one poll of the verification loop.
PERK_FRAME_TIMEOUT_SECONDS = 0.4
# Below this much turn time left, the bot uses no perk and no booster of any
# kind; on the last round it also plays the highest-points move only, with no
# setup for later (earlier rounds keep the normal ranking, see `_play`). A perk or a targeted
# booster is a multi-click transaction (activate -> target -> verify) and the
# timer running out mid-transaction spends the resource for nothing; a one-click
# booster fires, but its effect plays out into a turn that is already over, so
# the next turn starts with an empty meter instead of a full one (player's
# rule, 2026-09-15; it replaces the older "1-klik buster sme" exception, which
# had one recorded win -- hot-color 2026-08-24 04:15 UTC, 1024:1025 -- against
# every turn that opened without the booster). Raised 5 -> 8 s on the
# player's word (2026-09-15): at 5 s the booster was still being thrown
# away right before the buzzer.
LOW_TURN_TIME_SECONDS = 8.0
# Last round of a timed solo race: from this much clock down, a ready booster
# goes before any extra or lotus (player, 2026-10-08). The margin over
# LOW_TURN_TIME_SECONDS is one extra's clock cost at p90 (Showdown 5.3 s,
# measured 9/25-10/8), so the last extra still leaves the booster on time.
# Before this, 31 of 263 races ended with a full meter that extras had pushed
# past the low-clock cut-off. Re-checked 2026-11-10 against the new per-move
# measurement below: a plain move's p90 is 5.4 s, so 8 + 5.4 = 13.4 s still
# fits under 14 s -- the value stays.
BOOSTER_CLOCK_DEADLINE_SECONDS = 14.0
# Measured clock cost of one move in a timed solo race (Showdown / Party /
# Master League: strategy_context.mode == "solo_6", solo_challenge False).
# Re-measured 2026-11-10 over Debug/runs 2026-11-04..11-10: the drop of
# ranking_context.turn_state.time_left_seconds between consecutive decisions
# of the same turn, 2431 plain moves: p25 1.5 s, median 2.6 s, p75 4.1 s, p90
# 5.4 s, mean 2.96 s (median per day 1.8-3.0 s). Booster/perk activations are
# counted apart -- 771 of them, median 6.5 s, mean 6.7 s -- see
# move_strategy.TIME_BOUND_ACTIVATION_SECONDS. The mean is what a clock budget
# adds up, so 3.0. (The old 6.5 s was the 2026-08-25 median 5 s / mean 6.7 s
# with activations mixed in and before the faster dumps.)
TIME_BOUND_SECONDS_PER_MOVE = 3.0
# Versus keeps the old per-move value on purpose: the race measurement above
# does not apply to it. Its clock drops only 0.56 s (median, 1335 moves; mean
# 0.65 s) between decisions over the same runs -- it does not seem to run
# through the animations -- so 6.5 caps versus horizons far harder than the
# clock does. Changing it changes the versus charge horizon and fire chances
# (VERSUS_FIRE_CHANCE_* were measured under it), which is a separate decision.
VERSUS_SECONDS_PER_MOVE = 6.5
# Extra moves can still be earned, so the plan key watches the clock a little
# before it could actually run short.
CLOCK_KEY_MOVE_MARGIN = 10
# There is no lower bound on playing: a turn that runs out unplayed is a turn
# thrown away, while a swipe the clock cuts through at worst costs nothing more
# than the turn already lost. So the last second is played like any other --
# only the perk and the booster stay off (see LOW_TURN_TIME_SECONDS), because
# those are multi-click transactions that a cut-off turn spends for nothing.
# How stale the snapshot may be before its countdown is refused and a fresh
# dump is asked for. The agent only resends when the state *changes*, and
# during our own turn nothing changes while the bot thinks, so without this the
# remaining time would quietly age by whole seconds before anyone read it.
#
# It was 0.4 s, which in every timed mode meant a manual dump back-to-back for
# the whole turn: 73 % of all recorded snapshots were those dumps, each one
# running engine code inside the game while it animates -- and the three
# recorded mid-match freezes (2026-09-07/12/14) all hit timed matches under
# that load. The age is subtracted from the engine's countdown anyway (see
# turn_time_left), so a 3 s old reading still gives the right time left; the
# only thing it can miss is a pause that started in those 3 s.
TIMED_TURN_SNAPSHOT_MAX_AGE_SECONDS = 3.0
# "No turn has reported this yet". A plain None would collide with the turn key
# itself, which is None until the first snapshot lands, and swallow the first
# message of the session.
NOTHING_LOGGED_YET = object()
# Auto polls this often. The engine gates below are cheap dictionary reads, so
# the interval is only about how soon a settled board is noticed.
AUTO_TICK_INTERVAL_MS = 50
# Candidates/depth/beam, fixed by the kind of match. On 2476 recorded solo
# decisions (2026-11-04) 6/2/3 and 12/3/4 chose the same move 99% of the time at
# 50 against 127 ms, and the 25 that differed showed no measurable gain, so every
# match on a clock uses the light search. Only Solo Challenge has time for more:
# on 364 recorded solo positions (2026-11-09) 20/3/6 picked the same move as
# 20/4/6 in 99.2% at 444 against 1738 ms (median), with the exact refill
# following 3 moves either way; depth 2 dropped to ~94%.
FAST_LOOKAHEAD_PARAMS = (6, 2, 3)
VERSUS_LOOKAHEAD_PARAMS = (6, 3, 3)
SOLO_LOOKAHEAD_PARAMS = (20, 3, 6)


# Swipe/auto tuning the user sets in the Tajming group. Its own file: the
# main GUI's gui_state.json belongs to the other app and is not read here.
TIMING_SETTINGS_PATH = Path(__file__).resolve().with_name("memory_gui_timing.json")
# How long auto may sit without playing before it says why. Every gate below is
# a silent `return` -- correct one tick at a time, and indistinguishable from a
# dead loop over minutes. The turn clock does not stop for us, so a stall has to
# be visible while it is happening, not reconstructed from Debug afterwards.
AUTO_STALL_LOG_SECONDS = 8.0
# A dump the agent has not answered in this long is worth saying out loud: the
# reader is attached and the board looks fine, so nothing else would hint that
# the game stopped answering.
SLOW_DUMP_WARN_SECONDS = 2.0
# Freeze watchdog. The agent sends a heartbeat every second during a match, so
# this much silence means the agent -- and almost certainly the game with it --
# is stuck. Each incident goes to FREEZE_LOG_PATH with what led up to it,
# because the log panel dies with the window and a freeze usually ends in a
# restart.
FREEZE_SILENCE_SECONDS = 3.0
FREEZE_WATCH_INTERVAL_MS = 1000
FREEZE_LOG_PATH = PROJECT_ROOT / "Debug" / "freeze_watch.log"
FREEZE_LOG_CONTEXT_LINES = 30
# A heap walk this slow is logged even outside a freeze: it froze the game for
# that long by itself.
FREEZE_LOG_SLOW_CHOOSE_MS = 100
FREEZE_LOG_MAX_BYTES = 2_000_000
_freeze_log_lock = threading.Lock()


def append_freeze_log(lines) -> None:
    """Append lines to the freeze log, stamped with local time; never raises.

    Called from the Qt thread and from Frida's message thread alike.
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        with _freeze_log_lock:
            FREEZE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            # Rolled once like the GUI log (it only ever grew, ~205 KB by
            # 2026-09-22); the previous file stays as .log.1 for freeze hunts.
            try:
                if FREEZE_LOG_PATH.stat().st_size > FREEZE_LOG_MAX_BYTES:
                    FREEZE_LOG_PATH.replace(FREEZE_LOG_PATH.with_suffix(".log.1"))
            except OSError:
                pass
            with FREEZE_LOG_PATH.open("a", encoding="utf-8") as handle:
                for line in lines:
                    handle.write(f"{stamp}  {line}\n")
    except OSError:
        pass


# The panel log, on disk. The panel dies with the window and the silent
# launcher's stdout file only ever holds what Python itself printed, so a
# reader that got stuck an hour ago left no trace of *why* (2026-09-15: three
# restarts in one morning, nothing to read afterwards). Every _log line goes
# here too, stamped with the date; rotated once so it cannot grow forever.
GUI_LOG_PATH = PROJECT_ROOT / "Debug" / "memory_gui.log"
GUI_LOG_MAX_BYTES = 2_000_000
_gui_log_lock = threading.Lock()


def append_gui_log(message: str) -> None:
    """Append one panel-log line to GUI_LOG_PATH; never raises."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _gui_log_lock:
            GUI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            try:
                if GUI_LOG_PATH.stat().st_size > GUI_LOG_MAX_BYTES:
                    GUI_LOG_PATH.replace(GUI_LOG_PATH.with_suffix(".log.1"))
            except OSError:
                pass
            with GUI_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp}  {message}\n")
    except OSError:
        pass


# Matches the agent saw end for good, per game process: the engine leaves the
# finished GameLogic on the heap looking playable, and a freshly attached agent
# has no memory of the end -- so every GUI restart picked the previous Solo
# Challenge's board up as a running match (2026-09-15 09:06). The keys go back
# to the agent on attach (markDead) as long as the game process is the same.
DEAD_LOGICS_PATH = PROJECT_ROOT / "Debug" / "memory_board" / "dead_logics.json"
DEAD_LOGICS_MAX = 32


def load_dead_logics() -> tuple[int, list[str]] | None:
    """(pid, keys) recorded by remember_dead_logic, or None."""
    try:
        data = json.loads(DEAD_LOGICS_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid"))
        keys = [str(key) for key in data.get("keys") or [] if key]
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return (pid, keys) if keys else None


def remember_dead_logic(pid: int, key: str) -> None:
    """Record one ended match's logic key for this game process; never raises."""
    current = load_dead_logics()
    keys = list(current[1]) if current is not None and current[0] == pid else []
    if key in keys:
        keys.remove(key)
    keys.append(key)
    keys = keys[-DEAD_LOGICS_MAX:]
    try:
        DEAD_LOGICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEAD_LOGICS_PATH.write_text(
            json.dumps({"pid": int(pid), "keys": keys}), encoding="utf-8"
        )
    except OSError:
        pass


# Between matches the agent heartbeats every 5 s (HEARTBEAT_IDLE_MS in the
# agent), so this much silence means it is stuck -- typically inside a heap
# walk the game never came back from, in the lobby where the freeze watchdog
# above is deliberately quiet. A stuck agent never reports the next match, and
# until now the only way out was to restart the GUI and the game by hand. The
# GUI can do the first half itself: drop the session and attach again, which
# also runs the frida-server / game restarts that _attach_with_recovery knows.
IDLE_AGENT_SILENCE_SECONDS = 45.0
# One recovery per this long: a second one on top of an attach still in
# progress would only add a second stuck thread.
IDLE_AGENT_RECOVERY_MIN_INTERVAL_SECONDS = 300.0
# Attach the reader as soon as the window is up, without waiting for a match.
# Measured on 2026-08-21: an idle agent reads only the static match counter,
# which costs 0 ms, while the old always-on poll paid ~37 ms per heap walk plus
# ~114 ms per snapshot every 100 ms -- in the lobby, for nothing. Attaching by
# hand also cost the first seconds of every match.
AUTO_ATTACH_ON_START = True
# The bot is often started before the game is. A failed attach is therefore the
# normal first state, not an error to sit in, so it is retried until it takes --
# and stopped for good the moment the reader is detached by hand.
READER_RETRY_SECONDS = 5.0
# An attach that has not finished in this long is stuck, not slow. Frida's own
# calls (device.attach, script.load) have no timeout, so a game left holding a
# previous agent can hang the worker with no way to interrupt it -- the button
# must not stay on "Kacim..." forever with no explanation.
#
# Generous because a failed attach is not simply reported any more: it restarts
# frida-server, and then the game itself, before giving up -- and a game restart
# alone can take a minute. See _attach_with_recovery.
ATTACH_WATCHDOG_SECONDS = 180.0
# How late a starting match may be noticed. Free to lower, but not free to
# lower far: it is the idle tick, and the tick itself is what costs nothing.
READER_IDLE_SECONDS = 0.5
# An unchanged board can be a deliberate pause. Keep the match attached until
# the engine reports an end or the user explicitly closes it (0 disables timeout).
READER_QUIET_SECONDS = 0.0
# Hook GameLogic's constructor instead of searching the heap for it. It saves
# the ~37 ms `gc.choose` per resolve and it does install on BlueStacks -- but
# with it on, matches stopped being picked up (2026-08-21), and the heap walk
# it replaces costs once per match, not once per poll. So: off by default,
# because the ~37 ms it saves is worth nothing next to a match that never
# starts. Flip to True only together with the diagnosis of what it broke.
READER_CTOR_HOOK = False
# A move that has been "running" this long is not running any more. Reported,
# not cancelled: the swipe may still be in flight, and a second one on top of it
# is worse than a late one.
MOVE_STUCK_WARN_SECONDS = 20.0

# Pause after a failed move computation, doubling per identical repeat
# (0.5, 1, 2, 4, 5, 5 ... s). Short enough that a transient error costs well
# under a second of turn clock, long enough that a persistent one cannot flood
# the log at tick rate.
MOVE_ERROR_FIRST_BACKOFF = 0.5
MOVE_ERROR_MAX_BACKOFF = 5.0

# A registered swipe changes the board's slots signature within about a second
# of the drag (the swap alone is enough; cascades only add to it). A board still
# identical this long after the move finished means the game never accepted the
# swipe -- measured 2026-08-24 06:37: the last move's drag was swallowed, the
# "tabla se nije promenila od proslog poteza" gate blocked with no way out, and
# the match clock expired with four moves left. After this long the auto loop
# clears the played-signature latch and plans again: the board is unchanged, so
# the replay costs nothing but the drag it re-sends.
SWIPE_RETRY_SECONDS = 3.0

# Match3Engine.BoardAbilityType -> ime perka u engine-u.
BOARD_ABILITY_NAMES = {
    0: "None", 1: "Hammer", 2: "Shuffler", 3: "Teleport", 4: "DoubleScore",
    5: "StarMaker", 6: "AnyMove", 7: "SwapRedBlue", 8: "ConvertToRow",
    9: "FreeMove", 10: "ExplodeSpecials", 11: "AutoMatch", 12: "ExplodeColumn",
    13: "ExplodePickedColor", 14: "ExplodeRandomColor", 15: "RandomMatches",
    16: "ExplodeBomb", 17: "CreateLightning", 18: "CrossAttack",
    19: "MiniCobra", 20: "MiniCleo", 21: "MiniWoolly", 22: "AnyMatchEnergy",
    23: "Zebra", 24: "VoidPull", 25: "ColorClone",
}

# Only the perks whose engine name matches ours beyond doubt. Used as a
# fallback; the primary match is by name, see PERK_LABEL_TO_KEY.
BOARD_ABILITY_TO_PERK = {
    1: "hammer",
    2: "shuffle",
    3: "teleport",
    5: "star_maker",
    17: "create_lightning",
    19: "mini_cobra",
    20: "mini_cleo",
}


def _normalized_label(value: object) -> str:
    return "".join(character for character in str(value or "").lower() if character.isalnum())


# BoardAbilityModel.name is the perk's in-game name ("Energy Boost", "Remove
# Cross"), i.e. exactly the label the bot's own perk list uses. Matching on that
# beats guessing from the enum, which only covered half of them.
PERK_LABEL_TO_KEY = {
    _normalized_label(definition.label): key
    for key, definition in runtime.PERK_DEFINITIONS.items()
    if getattr(definition, "label", None)
}

# Same trick for boosters: SpecialAbilityModel.name carries the in-game name.
BOOSTER_LABEL_TO_ACTION = {
    _normalized_label(label): value
    for label, value in BOOSTER_ACTION_OPTIONS
    if value != BOOSTER_ACTION_NONE
}
# One booster's option label is not its in-game name. The eye booster is called
# "UFO SE" in game; the bot's option is labelled "UFO", which matched the OTHER
# booster ("UFO", type 19) by name and left the SE to be recognised only by its
# ability number. Corrected here rather than by renaming the shared option,
# which also names the dropdown in gui.py.
del BOOSTER_LABEL_TO_ACTION[_normalized_label("UFO")]
BOOSTER_LABEL_TO_ACTION[_normalized_label("UFO SE")] = BOOSTER_ACTION_UFO

# Match3Engine.SpecialAbilityType -> ime bustera kako ga engine zove.
SPECIAL_ABILITY_NAMES = {
    0: "None", 1: "Hammer", 2: "DoubleScore", 3: "Magic", 4: "ExplodeSpecials",
    5: "Nuke", 6: "SpecialDelivery", 8: "CrossAttack", 9: "Teleport",
    10: "Grind", 11: "TransformSwap", 12: "DualRockets", 13: "SmallBoom",
    14: "CreateSpecials", 15: "Painter", 16: "AutoMatcher", 17: "RubberDucky",
    18: "B52Bomber", 19: "UFOBeam", 20: "MemoryGame", 21: "BlazingBoard",
    22: "BalloonBlast", 23: "TapTime", 24: "Infection", 25: "Lightsabers",
    26: "AllAboard", 27: "DoctorColor", 28: "CrazyClovers",
    29: "RainbowExplosion", 30: "ReplayExplosions", 31: "JeevesBot",
    32: "QueenCobra", 33: "ElMagneto", 34: "MrAppleberry", 35: "WoollyWorkout",
    36: "FoxyRoxy", 37: "ColonelMcQuack", 38: "Cupid", 39: "SweepIt",
    40: "MonkeyJoojoo", 41: "BillieBoom", 42: "ColorBombs", 43: "Paintbrushes",
    44: "BroccoBoogie", 45: "DoctorColorSE", 46: "AllAboardSE", 47: "CupidSE",
    48: "ElMagnetoSE", 49: "UFOBeamSE", 50: "SpecialDeliverySE", 51: "Zebra",
    52: "FoxyRoxySE", 53: "CleoCadabra", 54: "CheckmateCharles", 55: "Beehive",
    56: "YinYang", 57: "StarMeteors", 58: "MagicBeans", 59: "MixyMeow",
    60: "JellySE", 61: "SweepItSE", 62: "CrossAttackSE", 63: "FroggyFu",
}

# SpecialAbilityType -> our booster action, taken from the shipped
# `Match-Masters/TextAsset/Constants` ability table, which pairs each engine
# type with its in-game title: Lightsabers/ReplayExplosions are "High Voltage",
# Magic is "Magic Wand", CrossAttack is "Laser Beam", BlazingBoard is "Lil
# Dragon", UFOBeam is "UFO". Used as a fallback when the live
# SpecialAbilityModel.name is missing; see BOOSTER_LABEL_TO_ACTION.
#
# SE variants place a piece on the board instead of firing directly, so they are
# left out on purpose -- except UFOBeamSE, which still takes colours off it.
#
# UFOBeam (19, in-game "UFO") is deliberately NOT here. It is a different
# booster from UFOBeamSE (49, "UFO SE"), and the "ufo" action means one thing
# only: the eye/abduction ledger. The shipped ability table (data/
# ability_config.json) settles it --
#
#   19 "UFO"     additional_params: allowPickingBlues, allowPickingSpecials
#   49 "UFO SE"  additional_params: + colorsToPickByActivation "2,2,1",
#                maxPassiveActivates 2, specialPieceScoreValue, and the whole
#                chanceFor*EyeColor table; plus a powerup that re-deals
#                colorsToPickByActivation as "3,2"
#
# The plain UFO has no colorsToPickByActivation, no maxPassiveActivates and no
# eye-colour table, because it has no eyes -- it fires directly. Mapped to "ufo"
# it inherited the SE ledger anyway: `_eyes_for_next_activation` fell through to
# the SE defaults and armed 2 phantom eyes on every activation, which then
# blocked the next booster activation (`ufo_pending_eye_gate`) and let the
# Extra-move button play a predicted extra behind an abduction that cannot
# happen (UFO_PREDICTED_EXTRA_GATE). With 19 out of the map it resolves to no
# targeting policy, like every other direct-fire booster, and is simply
# activated without aiming.
ABILITY_TO_BOOSTER_ACTION = {
    3: "magic_wand",       # Magic          -> Magic Wand
    8: "laser_beam",       # CrossAttack    -> Laser Beam
    21: "dragon",          # BlazingBoard   -> Lil Dragon
    25: "high_voltage",    # Lightsabers    -> High Voltage
    30: "high_voltage",    # ReplayExplosions -> High Voltage
    35: "woolly_workout",  # WoollyWorkout
    49: "ufo",             # UFOBeamSE      -> the eye/abduction booster
}

# SpecialAbilityType of the one UFO that has eyes. Pinned by board_source's
# CRITICAL_ENUM_MEMBERS ("UFOBeamSE"), so a game update that shifts it stops the
# bot instead of silently arming the ledger for whatever landed on 49.
UFO_SE_ABILITY_TYPE = 49


class UfoAbductionTracker:
    """How many UFO SE eyes are armed right now, from the engine's own numbers.

    The rail count on screen was measured 0/12 against the engine, and
    ``activeSpecialAbilityType`` only reads 49 in the single frame the
    activation animation runs in -- the 2026-08-19 17:21-17:28 session
    activated the UFO four times and every decision that followed still saw a
    0 there, so the abduction was never once modelled.

    What the engine does hand over is the booster's own tuning, on
    ``SpecialAbility.Config.additionalParams``::

        allowPickingBlues      False
        allowPickingSpecials   False
        specialPieceScoreValue 4
        maxPassiveActivates    2
        colorsToPickByActivation "2,2,1"

    So the eye count is not something to read off the screen at all: the first
    activation of a match arms 2 colours, the second 2, the third 1, and the
    eyes fire passively on at most ``maxPassiveActivates`` of the moves that
    follow. This tracker keeps that ledger from the snapshot stream.
    """

    # The shipped defaults live in move_strategy next to the simulator that
    # uses them; keeping a second copy here only invited the two to drift.
    DEFAULT_COLORS_TO_PICK = UFO_COLORS_BY_ACTIVATION
    DEFAULT_MAX_PASSIVE_ACTIVATES = UFO_MAX_PASSIVE_ACTIVATES
    # How long armed eyes may survive without the engine's move clock moving at
    # all. They are meant to last two moves; well past that the ledger is stuck,
    # and a stuck ledger blocks every booster activation for the rest of the
    # match. Generous, because a legitimately slow turn must not clear them.
    EYE_MAX_ARMED_SECONDS = 90.0
    # Two activation edges closer than this are one activation (the meter
    # needs at least a move to refill).
    ACTIVATION_DEDUPE_SECONDS = 3.0
    DEFAULT_ALLOW_PICKING_BLUES = UFO_ALLOW_PICKING_BLUES

    def __init__(self):
        self.reset("init")

    def reset(self, reason: str = ""):
        self.eyes = 0
        self.activations = 0
        self.passive_activates_left = 0
        self.reason = reason or "nema aktivacije"
        self._last_energy = None
        self._last_full = False
        self._last_score = None
        # The engine's own move clock, and the abduction count the simulator
        # expects the next move to spend. See `observe`.
        self._last_move_clock = None
        self._last_passive = False
        self._last_activation_at = None
        self._pending_abductions = None
        self._armed_at = None
        self._colors_to_pick = self.DEFAULT_COLORS_TO_PICK
        self._max_passive = self.DEFAULT_MAX_PASSIVE_ACTIVATES
        self._allow_blues = self.DEFAULT_ALLOW_PICKING_BLUES
        # `colorsToPickByActivation` is indexed by the activations *this
        # turn* (UFOBeamSE.CalculateColorsToPick reads
        # SpecialAbility.ActivatesThisTurn), so the activation count restarts
        # with the turn. Party/Solo have one turn per match; versus several.
        self._turn_key = None
        # What the engine itself last said (manual dumps from an agent build
        # that runs the UFOBeamSE getters), for the record.
        self.engine_eyes = None
        # Whether `eyes` is still the engine's own number (set by a manual
        # dump, cleared by anything the ledger infers afterwards).
        self.eyes_from_engine = False

    @staticmethod
    def _bool(value, fallback: bool) -> bool:
        """Parse a param that arrives as text.

        The board agent stringifies every param value, so `allowPickingBlues`
        comes over as the *string* "False" -- and `bool("False")` is True, which
        would invert the flag and let an eye take blue.
        """
        if value is None:
            return fallback
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no", ""}:
            return False
        return fallback

    @staticmethod
    def _int_list(text, fallback):
        if text is None:
            return fallback
        values = []
        for part in str(text).replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                values.append(max(0, int(float(part))))
            except ValueError:
                return fallback
        return tuple(values) or fallback

    def _read_params(self, me):
        params = (me or {}).get("special_ability_params") or {}
        self._colors_to_pick = self._int_list(
            params.get("colorsToPickByActivation"), self.DEFAULT_COLORS_TO_PICK
        )
        max_passive = params.get("maxPassiveActivates")
        try:
            self._max_passive = max(1, int(float(max_passive)))
        except (TypeError, ValueError):
            self._max_passive = self.DEFAULT_MAX_PASSIVE_ACTIVATES
        self._allow_blues = self._bool(
            params.get("allowPickingBlues"), self.DEFAULT_ALLOW_PICKING_BLUES
        )

    def _eyes_for_next_activation(self) -> int:
        """Eyes this activation arms, never more than the two the game shows.

        The eye count comes from the live booster, not from a number typed in
        here, so an event variant of the UFO would be followed automatically --
        but two is the ceiling of the ordinary UFO SE and the simulator clamps
        there anyway (``ufo_abduction_active``), so the ledger clamps too
        instead of logging an eye that can never fire.
        """
        table = self._colors_to_pick or self.DEFAULT_COLORS_TO_PICK
        # `activations` is already incremented for the activation being armed,
        # so the first one reads entry 0.
        index = min(max(0, self.activations - 1), len(table) - 1)
        return max(0, min(UFO_MAX_EYES, int(table[index])))

    @staticmethod
    def booster_is_ufo(me) -> bool:
        """Whether the equipped booster is UFO *SE* -- the one with eyes.

        Keyed on the engine's ability type, not on the "ufo" booster action:
        the action is a targeting policy that a mapping change could hand to
        another booster, while the ledger models one specific booster's tuning.
        The plain UFO (19) is a different booster and has no eyes at all; see
        ABILITY_TO_BOOSTER_ACTION for the shipped params that separate them.
        """
        ability = (me or {}).get("special_ability_type")
        try:
            return int(ability) == UFO_SE_ABILITY_TYPE
        except (TypeError, ValueError):
            return False

    def observe(self, state, me) -> None:
        """Fold one memory snapshot into the ledger."""
        if not self.booster_is_ufo(me):
            if self.eyes or self.activations:
                self.reset("booster nije UFO SE")
            return
        self._read_params(me)
        score = me.get("score")
        # A fresh match: the score starts over and the eyes do not carry.
        if (
            isinstance(score, (int, float))
            and isinstance(self._last_score, (int, float))
            and score < self._last_score
        ):
            self.reset("new match")
            self._read_params(me)
        if isinstance(score, (int, float)):
            self._last_score = score
        turn_key = None
        if isinstance(state, dict):
            turn_key = (state.get("turns"), state.get("current_round"))
        if turn_key != self._turn_key:
            if self._turn_key is not None and self.activations:
                self.reason = f"nova tura: brojac aktivacija resetovan (bilo {self.activations})"
            self._turn_key = turn_key
            self.activations = 0

        energy = me.get("energy")
        maximum = me.get("energy_to_ability")
        full_now = me.get("energy_full")
        if full_now is None:
            full_now = (
                isinstance(energy, (int, float))
                and isinstance(maximum, (int, float))
                and maximum > 0
                and energy >= maximum
            )
        # Same SE-only test as `booster_is_ufo`, on the ability that is firing
        # rather than the one equipped.
        active = self.booster_is_ufo(
            {"special_ability_type": me.get("active_special_ability_type")}
        )
        # The charge dropping from full to nothing is the activation, and it is
        # the durable half of the signal: `activeSpecialAbilityType` is only
        # live for the frame the animation plays in, which polling usually
        # misses entirely.
        drained = (
            isinstance(energy, (int, float))
            and energy == 0
            and bool(self._last_full)
        )
        # Both readings can land on consecutive frames for the SAME activation
        # (2026-09-12 22:19:14.485 `activeSpecialAbilityType` 49 with the
        # meter still full, 22:19:14.838 the meter at 0), and counting it twice
        # both re-arms the eyes and advances the per-activation index, so the
        # next real activation reads the wrong entry. One activation cannot
        # follow another inside the animation, so a second edge this soon is
        # the same one.
        if (active or drained) and (
            self._last_activation_at is None
            or time.monotonic() - self._last_activation_at > self.ACTIVATION_DEDUPE_SECONDS
        ):
            self._last_activation_at = time.monotonic()
            self.on_activation(
                "puna energija -> 0" if drained else "activeSpecialAbilityType"
            )
        if isinstance(energy, (int, float)):
            self._last_energy = energy
        self._last_full = bool(full_now)

        # An eye is spent when it FIRES, which the engine shows directly:
        # `UFOBeamSE.isRunningAsPassive` is true for the 2-6 s the abduction
        # animation runs (rising edge = one AfterDestroyWithPassiveAbility,
        # which pulls every colour the eyes locked on that destroy -- see
        # `_spend_one_move`). The ledger used to spend an eye on every change of
        # the engine's move clock instead, and one swipe moves that clock in
        # two steps (moves_made_this_turn first, moves a second later), so two
        # eyes went for one move: replaying 2026-09-12 21:50 - 22:20, 14 of the
        # 18 real fires happened while the ledger said no eye was armed. A move
        # on which no eye fires (nothing pickable) leaves the eye armed in the
        # engine too, so the clock has no business here at all.
        passive = bool((me.get("special_ability_fields") or {}).get("isRunningAsPassive"))
        if passive and not self._last_passive and self.eyes > 0:
            self._spend_one_move("oko pucalo")
        self._last_passive = passive
        clock = self._move_clock(state)
        if clock is not None:
            self._last_move_clock = clock

        # Backstop for a clock that never moves: eyes live for at most a couple
        # of moves, so a ledger still armed this long after the activation is
        # stale, and holding it costs a free booster activation every turn.
        if (
            self.eyes > 0
            and self._armed_at is not None
            and time.monotonic() - self._armed_at > self.EYE_MAX_ARMED_SECONDS
        ):
            self.eyes = 0
            self.passive_activates_left = 0
            self._armed_at = None
            self.eyes_from_engine = False
            self.reason = "oci istekle (zaglavljena knjiga)"

        # The engine's own count, when the snapshot carries it, overrules the
        # ledger in both directions.
        self._sync_from_engine(me.get("special_ability_engine"))

    @staticmethod
    def _engine_int(engine, key) -> int | None:
        raw = engine.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return int(raw)

    def _sync_from_engine(self, engine) -> None:
        """Take the eye count from UFOBeamSE's own getters when present.

        `special_ability_engine` arrives on manual dumps from an agent build
        that calls the getters (the GUI asks for a dump before every move).
        `RemainingHudEyes` is what the game draws on the rail; failing that,
        `colorsToPick - ColorsPicked` is the same number one step earlier in
        the engine (decoded from libil2cpp.so 2026-09-13: `Use` sets the first
        and zeroes the second, `AfterDestroyWithPassiveAbility` raises the
        second and `PassiveActivates` once per eye fired, and stops once
        `PassiveActivates` reaches `maxPassiveActivates`). The ledger's
        inference stays in charge between dumps and on older agents.
        """
        if not isinstance(engine, dict):
            return
        eyes = self._engine_int(engine, "remaining_hud_eyes")
        to_pick = self._engine_int(engine, "colors_to_pick")
        picked = self._engine_int(engine, "colors_picked")
        if eyes is None and to_pick is not None and picked is not None:
            eyes = max(0, to_pick - picked)
        if eyes is None:
            return
        # Before the booster's first Use the engine holds a placeholder, not an
        # eye count: remaining_hud_eyes = colors_to_pick = 9 (Debug/memory_board
        # snapshots 2026-09-26 and 2026-09-29, every UFO SE match start). Real
        # values are 0..UFO_MAX_EYES. Clamping the 9 down to 2 armed two
        # phantom eyes from the first move, and plans paid for abductions that
        # never fired (planned 100, scored 4). Nothing is armed until a Use.
        if eyes > UFO_MAX_EYES:
            if self.activations > 0:
                return
            eyes = 0
        fired = self._engine_int(engine, "passive_activates")
        passive_left = None
        if fired is not None and self._max_passive:
            passive_left = max(0, self._max_passive - fired)
            if passive_left <= 0:
                eyes = 0
        eyes = max(0, min(UFO_MAX_EYES, eyes))
        self.engine_eyes = eyes
        self.eyes_from_engine = True
        if eyes != self.eyes:
            self.reason = f"engine: {eyes} oka (bilo {self.eyes} po knjizi)"
            self.eyes = eyes
            self._armed_at = time.monotonic() if eyes > 0 else None
            self._pending_abductions = None
        if passive_left is not None:
            self.passive_activates_left = passive_left
        elif eyes > 0 and self.passive_activates_left <= 0:
            self.passive_activates_left = self._max_passive

    @staticmethod
    def _move_clock(state) -> tuple | None:
        """Whatever changes in the snapshot when a move has been played.

        Read from the engine rather than counted by us. The ledger used to
        advance only when the GUI reported one of our own turn-consuming moves,
        which silently missed extra moves (they consume no turn), swipes whose
        result was not measured, and any move played while a booster attempt was
        in flight -- and a missed advance leaves the eyes armed forever, which
        blocks a ready booster for the rest of the match
        (`ufo_pending_eye_gate`).
        """
        if not isinstance(state, dict):
            return None
        clock = (
            state.get("current_turn"),
            state.get("moves"),
            state.get("moves_made_this_turn"),
        )
        return None if all(value is None for value in clock) else clock

    @staticmethod
    def _is_our_turn(state, me) -> bool:
        """Only our own moves burn eyes, so the opponent's must not move the clock."""
        if not isinstance(state, dict):
            return True
        current = state.get("current_player_index")
        mine = (me or {}).get("index")
        if current is None or mine is None:
            return True
        return current == mine

    def _spend_one_move(self, reason: str) -> None:
        """The abduction animation started: the eyes that fired are gone.

        One passive run takes every colour the eyes locked on the direct
        destroy, so it spends as many eyes as the played move's simulation
        locked (`on_move_played`). Without that number -- a perk's wipe, a
        swipe the GUI never scored -- all armed eyes go: the 2026-09-13
        01:37:42 run under an Energy Boost perk took two colours at once, and
        keeping a phantom eye afterwards held a full booster for two of the six
        moves, while an eye spent too early only costs the rare second pull.
        """
        if self._pending_abductions is None:
            spent = self.eyes
        else:
            spent = min(
                max(1, int(self._pending_abductions)),
                UFO_MAX_COLORS_PER_MOVE,
            )
        self._pending_abductions = None
        self.eyes_from_engine = False
        self.eyes = max(0, self.eyes - spent)
        self.passive_activates_left -= 1
        if self.passive_activates_left <= 0:
            self.eyes = 0
        if self.eyes <= 0:
            self.eyes = 0
            self._armed_at = None
            self.reason = f"oci potrosene ({reason})"

    def on_activation(self, source: str = "") -> int:
        self.activations += 1
        self.eyes_from_engine = False
        self.eyes = self._eyes_for_next_activation()
        self.passive_activates_left = self._max_passive
        self._armed_at = time.monotonic()
        self._pending_abductions = None
        self.reason = (
            f"{self.activations}. aktivacija: {self.eyes} oka"
            + (f" ({source})" if source else "")
        )
        return self.eyes

    def on_move_played(self, abductions: int = 0) -> None:
        """One of our moves is behind us, so the eyes that fired are gone.

        ``abductions`` is how many colours the simulation of the played move
        expected the eyes to take: one per distinct pickable colour the swap
        itself matched, up to every armed eye
        (``move_strategy.UFO_MAX_COLORS_PER_MOVE``); an eye that found no
        colour waits for the next move. It is read rather than assumed, so a
        move where no colour the eye can take was matched leaves the eye armed
        instead of silently burning it.
        """
        if self.eyes <= 0:
            return
        # Recorded, not applied. The eye is spent when the engine's move clock
        # says the move actually happened (see `observe`), so a move the GUI
        # never reports -- an extra move, an unmeasured swipe -- still burns it.
        self._pending_abductions = max(1, int(abductions or 0))

    def state(self, me) -> UfoState:
        ability = (me or {}).get("special_ability_type")
        try:
            ability = int(ability)
        except (TypeError, ValueError):
            ability = None
        if not self.booster_is_ufo(me):
            return UfoState(
                eyes=0,
                confidence=1.0,
                source="memory",
                reason=f"booster nije UFO SE (specialAbilityType={ability})",
                ability_type=ability,
            )
        return UfoState(
            eyes=int(self.eyes),
            confidence=1.0,
            source="memory",
            reason=self.reason,
            allow_blues=bool(self._allow_blues),
            ability_type=ability,
            engine_eyes=self.engine_eyes,
        )


CELL_COLORS = {
    EMPTY: ("#20232b", "#6b7280", "."),
    BLOCKED: ("#2b2b2b", "#9ca3af", "#"),
    BLUE: ("#2563eb", "#ffffff", "B"),
    GREEN: ("#16a34a", "#ffffff", "G"),
    YELLOW: ("#eab308", "#1f2937", "Y"),
    PURPLE: ("#9333ea", "#ffffff", "P"),
    RED: ("#dc2626", "#ffffff", "R"),
    ORANGE: ("#ea580c", "#ffffff", "O"),
    WHITE: ("#e5e7eb", "#1f2937", "W"),
    CHEST: ("#78350f", "#ffffff", "C"),
    DISCO_BALL: ("#0f172a", "#f9a8d4", "*"),
}


def guarded_slot(method):
    """Keep one bad snapshot from taking the whole window down.

    PyQt5 aborts the process when an exception escapes a slot or a timer
    callback, so an oddly shaped snapshot reaching any helper under
    _on_snapshot / _auto_tick / _on_move_done ended the GUI mid-match. The
    error is logged instead (the same message at most once per 10 s, since
    the tick repeats it every 25-50 ms). Test doubles that are not a real
    window still get the exception, so a broken stub cannot pass silently.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:
            if not isinstance(self, QtWidgets.QWidget):
                raise
            traceback.print_exc()
            frames = traceback.extract_tb(exc.__traceback__)
            where = (
                f" [{Path(frames[-1].filename).name}:{frames[-1].lineno}]"
                if frames else ""
            )
            text = f"{method.__name__}: {type(exc).__name__}: {exc}{where}"
            now = time.monotonic()
            last = getattr(self, "_slot_error_logged", {})
            if now - last.get(text, -1e9) >= 10.0:
                last[text] = now
                self._slot_error_logged = last
                try:
                    self._log(f"GUI error (skipping): {text}")
                except Exception:
                    pass
            return None
    return wrapper


class ReaderSignals(QtCore.QObject):
    snapshot = QtCore.pyqtSignal(object)
    status = QtCore.pyqtSignal(str)
    stopped = QtCore.pyqtSignal(str)
    attached = QtCore.pyqtSignal(int)
    # The agent idles between matches and says when one starts or ends, so the
    # reader can stay attached from launch instead of being attached by hand
    # once a match is already running.
    match_state = QtCore.pyqtSignal(bool, str, object)
    # Frida dropped the session (game crash, frida-server restart, adb loss).
    # Carries the receiver so a late signal from a session this GUI already
    # replaced cannot tear down the new one.
    detached = QtCore.pyqtSignal(object, str)
    # One answer from the refill check process (refill_monitor).
    refill = QtCore.pyqtSignal(object)
    # The attach worker found the BlueStacks adb serial (for the touch swipe).
    adb_device = QtCore.pyqtSignal()


class GuiBoardReader(reader.BoardReader):
    """Reader that also pushes every snapshot into the Qt event loop."""

    def __init__(self, output: Path, latest: Path, signals: ReaderSignals):
        super().__init__(output, latest, quiet=True)
        self._signals = signals

    def on_message(self, message, data):
        super().on_message(message, data)
        if isinstance(message, dict) and message.get("type") == "error":
            # A script-level error (the agent threw outside its own try) is
            # the kind of thing that precedes "the reader stopped reacting";
            # the base reader only prints it, and the silent launcher's
            # stdout file is not where anyone looks. Into the GUI log.
            self._signals.status.emit(f"frida error: {self.last_error}")
            return
        payload = message.get("payload") if isinstance(message, dict) else None
        payload_type = payload.get("type") if isinstance(payload, dict) else None
        if payload_type == "error":
            # The agent's own complaints: a resolve that switched instance, a
            # poll that failed, every candidate claiming to be a simulation.
            self._signals.status.emit(
                f"agent ({payload.get('stage', 'error')}): {payload.get('message')}"
            )
            return
        if payload_type != "board_snapshot":
            # Not a board: re-emitting the last snapshot here would stamp it
            # as just received and hide a stale board -- and right after
            # match_state(False) it put the finished match's board straight
            # back on the panel the clear had just emptied.
            return
        snapshot = self.last_snapshot
        if snapshot is not None:
            self._signals.snapshot.emit(copy.deepcopy(snapshot))

    def on_detached(self, reason, crash=None):
        super().on_detached(reason, crash)
        self._signals.detached.emit(self, str(reason))

    def on_match_state(self, active, reason, payload):
        self._signals.match_state.emit(
            bool(active), str(reason), dict(payload) if isinstance(payload, dict) else {}
        )

    def on_notice(self, message):
        self._signals.status.emit(str(message))
        # Only match_pending / match_pending_failed come this way, and a
        # start that was missed leaves no other trace on disk: the freeze
        # watchdog is silent outside a match and the GUI log is not a file.
        append_freeze_log([f"reader: {message}"])

    def on_choose(self, payload):
        # Every walk stops the game's world. During a match there should be at
        # most a handful; each one is logged so a freeze can be matched to it.
        # Outside a match only the slow ones, or the lobby would fill the file.
        ms = payload.get("ms")
        slow = isinstance(ms, (int, float)) and ms >= FREEZE_LOG_SLOW_CHOOSE_MS
        if payload.get("phase") != "end" or not (payload.get("match_active") or slow):
            return
        append_freeze_log([
            f"heap walk: {payload.get('why')} {ms} ms, "
            f"instanci={payload.get('instances')}, ukupno={payload.get('count')}, "
            f"partija={payload.get('match_active')}"
            + (f", greska={payload.get('error')}" if payload.get("error") else "")
        ])


class MoveSignals(QtCore.QObject):
    done = QtCore.pyqtSignal(object, str)
    # The worker finished the search and is now holding the move (waiting for
    # the board, or for a click). Carries the AutoPlan it belongs to.
    computed = QtCore.pyqtSignal(object)
    # The worker just read the Cleo values for the board it is computing.
    cleo_values = QtCore.pyqtSignal()
    # The search found whether a move sure to reach the next flag exists on a board.
    solo_cross = QtCore.pyqtSignal(object, bool)


class LauncherSignals(QtCore.QObject):
    progress = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(object)


class _SwipeRecorderWorker(QtCore.QObject):
    """Runs swipe_recorder.record_swipe() off the GUI thread.

    The recorder busy-waits on GetAsyncKeyState until the user completes a
    drag, which would freeze the Qt event loop if it ran here. Emits the
    recording, or None when nothing usable was captured.
    """

    finished = QtCore.pyqtSignal(object)

    @QtCore.pyqtSlot()
    def run(self):
        try:
            recording = swipe_recorder.record_swipe()
        except Exception:
            recording = None
        self.finished.emit(recording)


class MemoryWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Match Masters")
        self.menuBar().addAction("Strategy Lab", lambda: subprocess.Popen(
            [sys.executable, "-m", "strategy_lab", "gui"], cwd=PROJECT_ROOT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ))
        self.resize(360, 900)
        # 360 of content plus room for the vertical scrollbar.
        self.setMinimumWidth(372)
        self.setMaximumWidth(520)

        self._reader_signals = ReaderSignals()
        self._reader_signals.snapshot.connect(self._on_snapshot)
        self._reader_signals.snapshot.connect(self._watch_research_board)
        self._reader_signals.refill.connect(self._on_refill_answer)
        self._reader_signals.adb_device.connect(self._apply_adb_swipe)
        self._reader_signals.status.connect(self._on_reader_status_signal)
        self._reader_signals.stopped.connect(self._on_reader_stopped)
        self._reader_signals.attached.connect(self._on_reader_attached)
        self._reader_signals.match_state.connect(self._on_match_state)
        self._reader_signals.detached.connect(self._on_reader_detached)
        # Keeps retrying the attach until it succeeds; cleared by a manual
        # detach so "Prekini citac" means stop, not "stop for five seconds".
        self._reader_auto_retry = AUTO_ATTACH_ON_START
        self._last_attach_error = None
        self._attach_attempt = 0
        # When the current attach attempt started, for the hang watchdog.
        self._attach_started_at = None
        # Whether a match is running, as the engine reports it. Attaching is no
        # longer the same thing as having a board to play.
        self._match_active = False
        # Autopilot pins the reader to its instance (Pie64_2); None keeps the
        # old discovery that picks any Pie64-like instance.
        self._pinned_serial = None
        self._move_signals = MoveSignals()
        self._move_signals.done.connect(self._on_move_done)
        self._move_signals.solo_cross.connect(self._on_solo_cross)
        self._move_signals.computed.connect(self._on_plan_computed)
        self._move_signals.cleo_values.connect(self._redraw_cleo_odds)
        # The move button the user last pressed and that has not been played
        # yet. A click is a standing request: pressed too early (cascade,
        # opponent's turn, board not settled) it is kept and played the moment
        # the game allows a move, exactly like Auto does. Cleared by the move
        # that fulfils it, by an error, by the end of the match, by Auto taking
        # over, or by REQUESTED_ACTION_TIMEOUT_SECONDS passing.
        self._requested_action = None
        self._requested_at = 0.0
        self._launcher_signals = LauncherSignals()
        self._launcher_signals.progress.connect(self._log)
        self._launcher_signals.done.connect(self._on_launch_done)

        self._reader = None
        self._reader_script = None
        # Square Match Solo: exact refill + full-game plan (square_solo_live).
        self._square_live = LiveSquareSolo()
        self._exact_reader = LiveSquareSolo()   # profile cache for the ordinary ranking
        # Swap Freely (anySwapValid + reduceMoveOnMatchOnly): free swaps first.
        self._free_swap_guard = free_swap.FreeSwapGuard()
        self._cleo_profile = (None, None)       # (special board, its memory profile)
        self._cleo_render_args = None           # last (snapshot, rules) the panel drew
        self._research = ResearchRecorder()
        self._research_on = False
        self._research_busy = False
        self._research_signature = None
        self._research_done_signature = None
        self._record_wait_signature = None
        self._record_wait_started = 0.0
        self._refill_on = True
        self._refill_input = (0, None)
        self._refill_monitor = RefillMonitorClient(self._reader_signals.refill.emit)
        self._refill_tally = RefillTally()
        self._research.on_capture = self._on_board_captured
        self._reader_session = None
        self._reader_thread = None
        self._snapshot = None
        self._snapshot_received_at = None
        self._move_running = False
        # Back-off after a failed move computation (see _note_move_failure).
        self._move_error_count = 0
        self._move_error_text = None
        self._move_retry_not_before = 0.0
        self._auto_plan = None
        self._last_played_signature = None
        # When the signature above was recorded, for the failed-swipe retry.
        self._last_played_at = None
        self._calibration_overlay = None
        self._score_legend = None
        self._ufo_tracker = UfoAbductionTracker()
        # None = nothing read yet, so the first snapshot of a match sets the
        # baseline instead of logging a jump from nowhere.
        self._score_multiplier_reported = None
        # Color Climb: the dealt colour pair, logged once per match (it never
        # changes after onGameStart) and again only if the read disagrees.
        self._color_climb_reported: tuple | None = None
        self._warned_board_size = None
        # Follows the live board: the engine's board size picks the calibration
        # profile, so Supersize needs no dropdown here (there is none).
        self._board_profile = board_profiles.DEFAULT_PROFILE
        self._warned_uncalibrated: set[str] = set()
        self._unmapped_warned: set[str] = set()
        self._ruleset_logged: set[str] = set()
        self._unmapped_saved: dict[str, int] = {}
        self._unmapped_signatures: set[tuple[str, object]] = set()
        # Lava columns whose engine counter was last seen above one; kept so
        # the log says it once instead of on every poll.
        self._floor_lava_reported: list[int] = []
        self._jelly_zone_reported: list = []
        # The jelly zone across snapshots that do not carry it: the agent's
        # engine-decoded read lands only on manual dumps, so the last read is
        # held for the polls in between -- until memory says the zone is gone,
        # the match ends, or the read goes stale (board_source.JellyZoneTracker).
        self._jelly_zone_tracker = board_source.JellyZoneTracker()
        self._hot_color_reported: dict | None = None
        self._froggy_region_reported: tuple | None = None
        self._lights_up_reported: int | None = None
        self._lights_up_multiplier_reported: int | None = None
        # The lit column the last started action was planned on, and after our
        # swap that same column until the game moves it (it is going dark).
        self._lights_up_play_column: int | None = None
        self._lights_up_stale_column: int | None = None
        self._column_mania_reported: tuple[int, ...] | None = None
        # Match/turn boundary tracking, so per-match strategy state resets
        # itself here the way the GUI buttons do it in the screen path.
        self._last_board_object = None
        self._last_moves_made = None
        # Kept alive: a non-modal QMessageBox is garbage-collected the moment
        # the last reference goes, and it must not be modal -- a modal dialog
        # would freeze the auto-play loop mid-match.
        self._unmapped_box = None
        self._perk_keys = ()
        self._perk_types: tuple[int | None, ...] = ()
        # Perk slots already spent this match. The engine keeps a used ability
        # in BoardAbilities, so "used" has to be tracked here (and cross-checked
        # against the on-screen slot strip before every activation).
        self._used_perk_slots: set[int] = set()
        # Who marked each spent slot ("engine" / "bot"), for the debug record.
        self._used_perk_slot_sources: dict[int, str] = {}
        # (slot, turn key) of a perk clicked whose spend was not confirmed. No
        # other perk starts in that turn until memory confirms the spend: a
        # second click on an armed perk is not a second perk.
        self._perk_pending_confirmation: tuple[int, object] | None = None
        # Last Mixy code already announced in the log, so the line appears on
        # change instead of on every snapshot.
        self._mixy_code_reported: tuple[int, ...] | None = None
        # Raw engine `activeColors` the spent-set below belongs to, and the raw
        # colours already matched on that code (seen as SourceColors/TargetColor
        # transients). A repeat match of a spent colour is dead in-game until
        # the code re-deals -- see _track_mixy_code_spend.
        self._mixy_spent_code: tuple | None = None
        self._mixy_spent_colors: set[int] = set()
        # Disarmed after a re-deal until the old match transient is seen
        # cleared once; a transient read while disarmed belongs to the
        # previous code and must not spend a fresh colour.
        self._mixy_spend_armed: bool = True
        # Code matches credited since the current booster activation, against
        # the engine's own `maxUsesByActivation` cap. This is what actually
        # ends a code -- see _track_mixy_code_spend.
        self._mixy_uses_this_activation: int = 0
        self._mixy_max_uses: int = 0
        # Previous frame's phase and charge, to spot the activation edge.
        self._mixy_prev_phase: int | None = None
        self._mixy_prev_energy: int | None = None
        self._mixy_transient_live: bool = False
        # The dealt code on the previous frame, when the last use was counted
        # and when the booster was last activated -- a re-deal that follows
        # neither is a code use whose transient the poll missed (see
        # _track_mixy_activation_uses).
        self._mixy_prev_code: tuple | None = None
        self._mixy_last_use_at: float = 0.0
        self._mixy_activated_at: float = 0.0
        # Activations seen this turn: `maxUsesByActivation` and
        # `colorsToPickByActivation` are indexed by it (Party Color Climb reads
        # [2, 1] / [3, 2]: two uses on the first activation, one afterwards).
        self._mixy_activation_count: int = 0
        self._mixy_turn_key: tuple | None = None
        # Turn clock: the engine exposes the per-turn budget but not the live
        # countdown, so the turn's start is timed here and the rest inferred.
        self._turn_started_at = None
        self._turn_clock_key = None
        self._low_time_logged_for = NOTHING_LOGGED_YET
        self._opponent_turn_logged_for = NOTHING_LOGGED_YET
        # Reentrancy guard for the snapshot-driven auto dispatch.
        self._auto_dispatching = False
        # One board request at a time, and never on this thread: see
        # _request_dump for why the RPC cannot be allowed to block here.
        self._dump_lock = threading.Lock()
        self._dump_inflight = False
        self._dump_started_at = None
        # Freeze watchdog: the open incident (None while the agent talks) and
        # the last log lines, which the incident record carries along.
        self._freeze_incident = None
        self._recent_log = deque(maxlen=FREEZE_LOG_CONTEXT_LINES)
        # When the lobby watchdog last re-attached a silent agent.
        self._idle_recovery_at = None
        # PID of the game process the reader is attached to (dead_logics.json
        # is only meaningful for that process).
        self._reader_pid = None
        append_gui_log("=== Memory GUI started")
        # Auto stall watchdog: when auto last got somewhere, and what it last
        # complained about.
        self._auto_progress_at = None
        self._auto_stall_reason = None
        self._auto_stall_logged_at = 0.0
        self._move_stuck_logged = False
        self._booster_action = BOOSTER_ACTION_NONE
        # Debug frame recording: buffer between actions, sink while one is live.
        self._frames_since_action = []
        self._frame_sink = None
        self._action_started_at = 0.0

        self._build_ui()

        self._auto_timer = QtCore.QTimer(self)
        self._auto_timer.setInterval(AUTO_TICK_INTERVAL_MS)
        self._auto_timer.timeout.connect(self._auto_tick)
        self._auto_timer.timeout.connect(self._watch_research_board)
        self._auto_timer.start()

        self._freeze_timer = QtCore.QTimer(self)
        self._freeze_timer.setInterval(FREEZE_WATCH_INTERVAL_MS)
        self._freeze_timer.timeout.connect(self._freeze_watch_tick)
        self._freeze_timer.start()

        # Tuning is applied once the timer exists, because the tick interval is
        # one of the values it drives. A recording persisted by an earlier
        # session survives restarts; the saved values decide whether it is
        # actually replayed.
        self._swipe_record_thread = None
        self._swipe_record_worker = None
        runtime.SWIPE_PROFILE = swipe_recorder.load_profile()
        self._refresh_swipe_profile_status()
        self._load_timing_settings()
        self._apply_timing()

        # Attaching while the lobby is up used to be the thing that froze the
        # game, so it was done by hand once a match had started -- which cost
        # the first seconds of every match. The agent now idles for free until
        # a match begins, so the reader attaches itself here, once, and stays
        # for every match after it.
        if AUTO_ATTACH_ON_START:
            QtCore.QTimer.singleShot(0, self._reader_clicked)
        # Started remotely with MEMORY_GUI_AUTOSTART=1 (nobody at the PC to
        # click): Use Perks on, and Auto armed as soon as the reader allows it.
        if __import__("os").environ.get("MEMORY_GUI_AUTOSTART") == "1":
            self.PerksCheck.setChecked(True)
            if __import__("os").environ.get("MEMORY_GUI_RECORD") == "1":
                self.ResearchCheck.setChecked(True)
            self._autostart_timer = QtCore.QTimer(self)
            self._autostart_timer.setInterval(1000)
            self._autostart_timer.timeout.connect(self._autostart_tick)
            self._autostart_timer.start()

    def _autostart_tick(self):
        if self.AutoButton.isEnabled() and not self.AutoButton.isChecked():
            self.AutoButton.setChecked(True)
        if self.AutoButton.isChecked():
            self._log("Autostart: Use Perks i Auto ukljuceni")
            self._autostart_timer.stop()

    # ---------------------------------------------------------------- UI ---

    def _build_ui(self):
        central = QtWidgets.QWidget()
        central.setObjectName("Central")
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(9)

        def section(text):
            label = QtWidgets.QLabel(text.upper())
            label.setObjectName("SectionLabel")
            return label

        # Header: what this window is, and whether the reader is connected --
        # the one thing worth knowing at a glance.
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(0)
        app_title = QtWidgets.QLabel("Match Masters")
        app_title.setObjectName("AppTitle")
        app_subtitle = QtWidgets.QLabel("Toolkit")
        app_subtitle.setObjectName("AppSubtitle")
        titles.addWidget(app_title)
        titles.addWidget(app_subtitle)
        header.addLayout(titles, 1)
        self.ConnPill = QtWidgets.QLabel()
        self.ConnPill.setObjectName("ConnPillIdle")
        header.addWidget(self.ConnPill, 0, QtCore.Qt.AlignVCenter)
        layout.addLayout(header)

        self.LaunchButton = QtWidgets.QPushButton("Launch Game")
        self.LaunchButton.clicked.connect(self._launch_clicked)
        self.ReaderButton = QtWidgets.QPushButton("Attach Reader")
        self.ReaderButton.clicked.connect(self._reader_clicked)
        self.EndMatchButton = QtWidgets.QPushButton("Forfeit")
        self.EndMatchButton.setToolTip(
            "Manual match end, same path as a real end: agent closes the "
            "match and marks it as finished (won't come back after restart), "
            "panel clears, auto stops, reader waits for the next match."
        )
        self.EndMatchButton.clicked.connect(self._end_match_clicked)
        self.RestartFridaButton = QtWidgets.QPushButton("Restart Frida")
        self.RestartFridaButton.setToolTip(
            "When the game crashes with an attached session, frida-server stays "
            "in a bad state and claims libil2cpp.so is not loaded. This kills "
            "and restarts it on the device."
        )
        self.RestartFridaButton.clicked.connect(self._restart_frida_clicked)
        self.CalibrateButton = QtWidgets.QPushButton("Calibrate")
        self.CalibrateButton.setToolTip(
            "Memory tells WHAT is on the board, but swipe needs to know WHERE "
            "a cell is on screen. Without calibration for this BlueStacks layout "
            "every move fails with BoardCalibrationError."
        )
        self.CalibrateButton.clicked.connect(self._calibrate_clicked)
        # Two columns instead of one wide row: the window has to sit next to
        # BlueStacks, not on top of it.
        top = QtWidgets.QGridLayout()
        # Calibration and Predaja are the visible ones, one under the other in
        # the left column; the rest stay constructed (hidden) because the
        # reader/launch code still drives their text and enabled state.
        for index, button in enumerate(
            (
                self.CalibrateButton,
                self.LaunchButton,
                self.EndMatchButton,
                self.ReaderButton,
                self.RestartFridaButton,
            )
        ):
            top.addWidget(button, index // 2, index % 2)
            if button not in (self.CalibrateButton, self.EndMatchButton):
                button.hide()
        # Calibrate and Forfeit sit side by side: the hidden buttons above
        # fill the grid cells in between, so the row is rebuilt here.
        for button in (self.CalibrateButton, self.EndMatchButton):
            top.removeWidget(button)
        top.addWidget(self.CalibrateButton, 0, 0)
        top.addWidget(self.EndMatchButton, 0, 1)
        top.setHorizontalSpacing(8)
        self.CalibrateButton.setObjectName("GhostButton")
        self.EndMatchButton.setObjectName("DangerButton")
        layout.addLayout(top)
        layout.addWidget(section("Match"))

        # Stanje iz memorije: panel sam odlucuje koji redovi postoje za mod
        # koji se igra (gui_state_panel.MemoryStatePanel). Imena labela su
        # ostala ista, pa svaki postojeci setText poziv radi nepromenjen.
        self.StatePanel = MemoryStatePanel()
        self.StateLabel = self.StatePanel.StateLabel
        self.ScoreLabel = self.StatePanel.ScoreLabel
        self.MovesLabel = self.StatePanel.MovesLabel
        self.BoosterLabel = self.StatePanel.BoosterLabel
        self.ModeLabel = self.StatePanel.ModeLabel
        self.PerksLabel = self.StatePanel.PerksLabel
        self.MutationsLabel = self.StatePanel.MutationsLabel
        self.TurnLabel = self.StatePanel.TurnLabel
        self.FreshLabel = self.StatePanel.FreshLabel
        self.LegendLabel = self.StatePanel.LegendLabel
        self.BoosterNameLabel = self.StatePanel.BoosterNameLabel
        self.UfoEyesLabel = self.StatePanel.UfoEyesLabel
        layout.addWidget(self.StatePanel)

        board_box = QtWidgets.QGroupBox("Board")
        board_layout = QtWidgets.QGridLayout(board_box)
        board_layout.setSpacing(3)
        self._cells = []
        # Built for the biggest board the reader supports; _render_board hides
        # the outer row/column on a 7x7 match instead of rebuilding the grid.
        self._board_grid_size = max(board_source.SUPPORTED_MEMORY_BOARD_SIZES)
        for row in range(self._board_grid_size):
            row_cells = []
            for col in range(self._board_grid_size):
                cell = QtWidgets.QLabel(" ")
                cell.setAlignment(QtCore.Qt.AlignCenter)
                cell.setFixedSize(36, 36)
                cell.setFont(QtGui.QFont("Consolas", 9, QtGui.QFont.Bold))
                cell.setStyleSheet(
                    "background:#20232b;color:#6b7280;border-radius:8px;"
                )
                board_layout.addWidget(cell, row, col)
                row_cells.append(cell)
            self._cells.append(row_cells)
        self.CalcLabel = QtWidgets.QLabel("Computing: -")
        self.CalcLabel.setWordWrap(True)
        self.CalcLabel.setToolTip(
            "What the move planner is doing: the move is computed as soon as "
            "a new board arrives, even when Auto is off. The button then just "
            "plays the ready move (or waits for computation to finish)."
        )
        board_layout.addWidget(
            self.CalcLabel, self._board_grid_size, 0, 1, self._board_grid_size
        )
        layout.addWidget(board_box)
        # Shown only while a Cleo is on the board: per swipe, the chance the
        # random clone colour makes a 4+ match and keeps the turn.
        self.CleoGroup = QtWidgets.QGroupBox("Cleo - Extra Move Odds")
        cleo_layout = QtWidgets.QVBoxLayout(self.CleoGroup)
        self.CleoOddsLabel = QtWidgets.QLabel()
        self.CleoOddsLabel.setTextFormat(QtCore.Qt.RichText)
        self.CleoOddsLabel.setWordWrap(True)
        self.CleoOddsLabel.setToolTip(
            "For each piece around Cleo: the extra-move chance when swiping "
            "Cleo onto the piece and when swiping the piece onto Cleo (the "
            "source cell stays empty). Percentage = chance the game's own "
            "colour search ends on a colour that keeps the turn; colored "
            "squares are those colors. Colours are not equally likely: the "
            "game prefers a 4+ match near the clone amount, unless the extra "
            "is prevented (its chance depends on the match type and on how "
            "many figures were used this turn)."
        )
        cleo_layout.addWidget(self.CleoOddsLabel)
        # Did the simulation match the game on the last played Cleo swap
        # (runtime._cleo_prediction_check), plus this session's tally.
        self.CleoVerdictLabel = QtWidgets.QLabel()
        self.CleoVerdictLabel.setTextFormat(QtCore.Qt.RichText)
        self.CleoVerdictLabel.setWordWrap(True)
        self.CleoVerdictLabel.setStyleSheet("color:#9ca3af;")
        self.CleoVerdictLabel.hide()
        cleo_layout.addWidget(self.CleoVerdictLabel)
        layout.addWidget(self.CleoGroup)
        self.CleoGroup.hide()
        self._cleo_odds_key = None
        self._cleo_tally = {}
        self._cleo_checked_runs = set()
        # Board preview hidden; _render_board keeps updating the cells, which
        # stay invisible while their parent box is hidden.
        board_box.hide()

        # Everything below the board is stacked in a narrow two-column grid so
        # the window can live beside BlueStacks instead of covering it.
        settings_card = QtWidgets.QFrame()
        settings_card.setObjectName("Card")
        settings_layout = QtWidgets.QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(12, 10, 12, 10)
        settings_layout.setSpacing(8)
        options = QtWidgets.QGridLayout()
        options.setContentsMargins(0, 0, 0, 0)
        options.setVerticalSpacing(3)
        options.setColumnStretch(1, 1)

        # Booster (ime + punjenje) je sada u MemoryStatePanel.
        self.BoosterImmediateCheck = QtWidgets.QCheckBox("Booster Immediately")
        self.BoosterImmediateCheck.setToolTip(
            "Off by default: keep safe extra moves before activating a ready booster. "
            "Turn on to activate sooner when time is short."
        )
        options.addWidget(self.BoosterImmediateCheck, 4, 0, 1, 2)
        # Off by default: with the rush on, blue is weighted up and the extra
        # tier stops short-circuiting the ranking, so a turn-preserving extra
        # can lose to a charge move. Solo/Party/Showdown only -- versus ignores
        # it, because there a kept turn is worth more than meter progress.
        self.BlueRushCheck = QtWidgets.QCheckBox("Juri plave")
        self.BlueRushCheck.setChecked(True)
        self.BlueRushCheck.setVisible(False)
        # Perks are spent to fill the booster, not to farm points: the ranking
        # behind this is charge-first (see perk_effect_priority_key), so the
        # toggle only decides whether the bot may spend them at all.
        self.PerksCheck = QtWidgets.QCheckBox("Use Perks")
        self.PerksCheck.setToolTip(
            "Bot spends perks when they help charge the booster (blue, extra "
            "move, specials). Off: perks are only read from memory."
        )
        options.addWidget(self.PerksCheck, 8, 0, 1, 2)
        # The swipe as touch events inside BlueStacks (adb_touch) instead of
        # the mouse: the cursor stays where it is and the window may be covered.
        self.AdbSwipeCheck = QtWidgets.QCheckBox("Swipe kroz BlueStacks")
        self.AdbSwipeCheck.setToolTip(
            "Ukljuceno: potez se salje kao dodir direktno u BlueStacks preko adb-a, "
            "mis se ne pomera. Ako adb ne moze, potez ide misem."
        )
        self.AdbSwipeCheck.setChecked(True)
        self.AdbSwipeCheck.toggled.connect(lambda _checked: self._apply_adb_swipe())
        options.addWidget(self.AdbSwipeCheck, 9, 0, 1, 2)
        # Research recording: the settled board and the full memory profile go
        # to Debug/research (research_recorder; analyze with
        # tools/analyze_research.py). Does not change which move is played.
        self.ResearchCheck = QtWidgets.QCheckBox("Snimaj svaki potez")
        self.ResearchCheck.setToolTip(
            "Ukljuceno: svaka mirna tabla ide u Debug/research, bez obzira ko je "
            "odigrao potez (Auto, dugme ili rukom). Iskljuceno: nista se ne snima."
        )
        self.ResearchCheck.toggled.connect(self._on_research_toggled)
        # Legenda skora je sada u MemoryStatePanel (red se sam sakriva
        # kad mod nema posebnu legendu).
        self.DebugCheck = QtWidgets.QCheckBox("Debug zapis")
        self.DebugCheck.setChecked(False)
        self.DebugCheck.toggled.connect(lambda _checked: self._apply_trace_mode())
        self.DebugCheck.setVisible(False)
        settings_layout.addLayout(options)

        # Swipe/auto tuning. Keep it expanded on every launch so the active
        # gesture settings are visible immediately.
        self.TimingGroup = QtWidgets.QGroupBox("Timing")
        self.TimingGroup.setCheckable(True)
        self.TimingGroup.setChecked(True)
        timing_outer = QtWidgets.QVBoxLayout(self.TimingGroup)
        self.TimingBody = QtWidgets.QWidget()
        self.TimingBody.setVisible(True)
        self.TimingGroup.toggled.connect(self.TimingBody.setVisible)
        timing = QtWidgets.QGridLayout(self.TimingBody)
        timing.setContentsMargins(0, 0, 0, 0)

        def _spin(decimals, minimum, maximum, step, value, suffix, tip):
            box = (
                QtWidgets.QDoubleSpinBox() if decimals else QtWidgets.QSpinBox()
            )
            if decimals:
                box.setDecimals(decimals)
            box.setRange(minimum, maximum)
            box.setSingleStep(step)
            box.setValue(value)
            box.setSuffix(suffix)
            box.setToolTip(tip)
            box.valueChanged.connect(self._apply_timing)
            return box

        self.SwipeDurationSpin = _spin(
            3, 0.005, 0.500, 0.005, runtime.SWIPE_DURATION_SECONDS, " s",
            "Trajanje glajda od pocetne do ciljne tacke. Manje = brze.",
        )
        self.SwipeDistanceSpin = _spin(
            0, 20, 120, 5, runtime.SWIPE_DISTANCE_PX, " px",
            "Duzina putanje swipea. Veca distanca pri istom trajanju = veca "
            "brzina i sigurnije prelazi Android fling prag.",
        )
        self.SwipePreHoldSpin = _spin(
            3, 0.000, 0.100, 0.001, runtime.SWIPE_PRE_MOVE_HOLD_SECONDS, " s",
            "Pauza posle mouseDown pre prvog pokreta.",
        )
        self.SwipePostHoldSpin = _spin(
            3, 0.000, 0.100, 0.001, runtime.SWIPE_POST_MOVE_HOLD_SECONDS, " s",
            "Pause at the end before mouseUp. If swipe misses, raise this first.",
        )
        self.AutoTickSpin = _spin(
            0, 10, 200, 5, AUTO_TICK_INTERVAL_MS, " ms",
            "How often the auto loop checks if it can play. "
            "Lower = faster response when the game opens a move.",
        )
        self.SwipeProfileSpeedSpin = _spin(
            2, 0.50, 6.00, 0.25, runtime.SWIPE_PROFILE_SPEED, " x",
            "Recorded swipe playback speed: 2x plays the recording twice as fast "
            "(same path, faster cursor speed).",
        )

        for column, (label, box) in enumerate(
            (
                ("Duration", self.SwipeDurationSpin),
                ("Distance", self.SwipeDistanceSpin),
            )
        ):
            timing.addWidget(QtWidgets.QLabel(label), 0, column * 2)
            timing.addWidget(box, 0, column * 2 + 1)
        for column, (label, box) in enumerate(
            (
                ("Pre-hold", self.SwipePreHoldSpin),
                ("Post-hold", self.SwipePostHoldSpin),
            )
        ):
            timing.addWidget(QtWidgets.QLabel(label), 1, column * 2)
            timing.addWidget(box, 1, column * 2 + 1)
        timing.addWidget(QtWidgets.QLabel("Auto tick"), 2, 0)
        timing.addWidget(self.AutoTickSpin, 2, 1)
        timing.addWidget(QtWidgets.QLabel("Profile speed"), 2, 2)
        timing.addWidget(self.SwipeProfileSpeedSpin, 2, 3)

        self.SwipeRecordButton = QtWidgets.QPushButton("Record Swipe")
        self.SwipeRecordButton.setToolTip(
            "Record a real mouse flick: click, switch to BlueStacks and do "
            "one fast swipe. That path becomes the template for all 4 "
            "directions (rotated as needed)."
        )
        self.SwipeRecordButton.clicked.connect(self._record_swipe_clicked)
        timing.addWidget(self.SwipeRecordButton, 3, 0, 1, 2)
        self.SwipeUseProfileCheck = QtWidgets.QCheckBox("Use Recording")
        self.SwipeUseProfileCheck.setToolTip(
            "On: swipe replays the recording. Off: uses the spinboxes above "
            "(synthetic flick)."
        )
        self.SwipeUseProfileCheck.toggled.connect(self._apply_timing)
        timing.addWidget(self.SwipeUseProfileCheck, 3, 2, 1, 2)
        self.SwipeProfileStatus = QtWidgets.QLabel("No recording")
        self.SwipeProfileStatus.setStyleSheet("color:#6b7280;")
        timing.addWidget(self.SwipeProfileStatus, 4, 0, 1, 4)
        timing_outer.addWidget(self.TimingBody)
        # The Tajming group stays constructed but off-screen: its widgets are
        # the persistence backend for memory_gui_timing.json, so the tuned
        # values keep loading and applying as the defaults -- they just no
        # longer take up panel space.
        self.TimingGroup.hide()

        # Which search this match uses, so a wrong pick can be seen. Shown only
        # during a match (_update_lookahead_label).
        self.LookaheadLabel = QtWidgets.QLabel()
        self.LookaheadLabel.setStyleSheet("color:#6b7280;")
        self.LookaheadLabel.hide()
        settings_layout.addWidget(self.LookaheadLabel)

        actions = QtWidgets.QGridLayout()
        actions.setSpacing(8)
        self.BestMoveButton = QtWidgets.QPushButton("Best Move")
        self.BestMoveButton.clicked.connect(lambda: self._play("best_move"))
        self.ExtraMoveButton = QtWidgets.QPushButton("Extra move")
        self.ExtraMoveButton.clicked.connect(lambda: self._play("extra_move"))
        self.PointsButton = QtWidgets.QPushButton("Most Points")
        self.PointsButton.clicked.connect(lambda: self._play("highest_points"))
        self.SoloCrossButton = QtWidgets.QPushButton("Predji zastavicu")
        self.SoloCrossButton.setToolTip(
            "Solo Challenge: igra potez koji sigurno prelazi sledecu zastavicu.\n"
            "Pali se samo kad takav potez postoji i booster nije spreman."
        )
        self.SoloCrossButton.clicked.connect(lambda: self._play("solo_cross"))
        self.SoloCrossButton.setEnabled(False)
        self._solo_cross_state = None
        self._solo_cross_allowed = False
        self.AutoButton = QtWidgets.QPushButton("Auto")
        self.AutoButton.setCheckable(True)
        self.AutoButton.toggled.connect(self._auto_toggled)
        # One row of single moves, Auto full width under it: Auto is what runs
        # a match, so it gets the size and the colour.
        for index, button in enumerate(
            (
                self.BestMoveButton,
                self.ExtraMoveButton,
                self.PointsButton,
            )
        ):
            button.setMinimumHeight(34)
            actions.addWidget(button, 0, index)
        actions.addWidget(self.SoloCrossButton, 1, 0, 1, 3)
        actions.addWidget(self.AutoButton, 2, 0, 1, 3)
        layout.addWidget(section("Play"))
        layout.addLayout(actions)
        from autopilot_panel import AutopilotPanel
        self.AutopilotPanel = AutopilotPanel(self)
        layout.addWidget(self.AutopilotPanel)
        layout.addWidget(section("Settings"))
        layout.addWidget(settings_card)
        self.AutoButton.setObjectName("AutoButton")
        for button in (
            self.BestMoveButton,
            self.ExtraMoveButton,
            self.PointsButton,
            self.SoloCrossButton,
        ):
            button.setProperty("actionButton", True)

        # Move burners, set apart from the real buttons so they are not hit by
        # accident: after a concession or a challenge finished with moves to
        # spare, the moves only need spending. One click = one worst move; the
        # auto variant keeps playing worst moves until the moves run out (it
        # switches itself off when the match ends).
        layout.addSpacing(6)
        layout.addWidget(section("Burn leftover moves"))
        burners = QtWidgets.QGridLayout()
        burners.setSpacing(8)
        self.WorstMoveButton = QtWidgets.QPushButton("Least Points")
        self.WorstMoveButton.setToolTip(
            "Play one move with the fewest points: no extra moves, no "
            "booster, no perks. For burning leftover moves."
        )
        self.WorstMoveButton.clicked.connect(lambda: self._play("lowest_points"))
        self.WorstAutoButton = QtWidgets.QPushButton("Least Points Auto")
        self.WorstAutoButton.setToolTip(
            "Automatically plays moves with the fewest points until moves "
            "run out. Turns itself off when the match ends."
        )
        self.WorstAutoButton.setCheckable(True)
        self.WorstAutoButton.toggled.connect(self._worst_auto_toggled)
        for index, button in enumerate(
            (self.WorstMoveButton, self.WorstAutoButton)
        ):
            button.setMinimumHeight(34)
            burners.addWidget(button, 0, index)
        layout.addLayout(burners)
        self.WorstMoveButton.setProperty("actionButton", True)
        self.WorstAutoButton.setObjectName("WorstAutoButton")

        self.LogView = QtWidgets.QPlainTextEdit()
        self.LogView.setReadOnly(True)
        self.LogView.setMaximumBlockCount(400)
        self.LogView.setMinimumHeight(90)
        self.LogView.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.LogView.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding
        )
        layout.addWidget(self.LogView, 1)
        # Log view hidden; _log still writes to it, the status bar stays.
        self.LogView.hide()
        layout.addStretch(1)

        # Reader connection status at the bottom: device, attach steps and
        # errors, shown only while the reader is not attached -- the log is
        # hidden, so this is where a failing attach is visible at all.
        self.ReaderStatusGroup = QtWidgets.QGroupBox("Reader")
        reader_status_layout = QtWidgets.QVBoxLayout(self.ReaderStatusGroup)
        self.ReaderStatusLabel = QtWidgets.QLabel("-")
        self.ReaderStatusLabel.setWordWrap(True)
        self.ReaderStatusLabel.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.ReaderStatusLabel.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        reader_status_layout.addWidget(self.ReaderStatusLabel)
        layout.addWidget(self.ReaderStatusGroup)
        self._reader_status_lines = []
        self._reader_status("Reader not attached")

        # Scrollable so the window can be shorter than its content; otherwise
        # the layout's minimum height pushes the bottom buttons off screen.
        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("CentralScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setWidget(central)
        # Refill status stays visible under the scrolling controls.
        self.RefillGroup = QtWidgets.QGroupBox("Dopuna")
        refill_layout = QtWidgets.QVBoxLayout(self.RefillGroup)
        refill_layout.setSpacing(2)
        self.RefillUseLabel = QtWidgets.QLabel()
        self.RefillDataLabel = QtWidgets.QLabel()
        self.RefillHitLabel = QtWidgets.QLabel()
        for label in (self.RefillUseLabel, self.RefillDataLabel, self.RefillHitLabel):
            label.setWordWrap(True)
            label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
            refill_layout.addWidget(label)
        self.RefillLog = QtWidgets.QPlainTextEdit()
        self.RefillLog.setReadOnly(True)
        self.RefillLog.setMaximumBlockCount(300)
        self.RefillLog.setFixedHeight(64)
        self.RefillLog.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        refill_layout.addWidget(self.RefillLog)
        # Here, not under Settings: this panel takes height from the scrolling
        # controls and the toggle ended up below the fold.
        refill_layout.addWidget(self.ResearchCheck)
        # Master switch, this session only: off, nothing about the refill is
        # read, checked or used for a move (the exact planners included).
        self.RefillMasterCheck = QtWidgets.QCheckBox("Dopuna ukljucena")
        self.RefillMasterCheck.setChecked(True)
        self.RefillMasterCheck.setToolTip(
            "Iskljuceno: bot racuna poteze bez dopune, bez provere i bez citanja "
            "za nju. Vazi dok je prozor otvoren."
        )
        self.RefillMasterCheck.toggled.connect(self._on_refill_master_toggled)
        refill_layout.addWidget(self.RefillMasterCheck)
        window_body = QtWidgets.QWidget()
        window_layout = QtWidgets.QVBoxLayout(window_body)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(0)
        window_layout.addWidget(scroll, 1)
        window_layout.addWidget(self.RefillGroup)
        self.RefillGroup.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self.setCentralWidget(window_body)
        self._refresh_refill_panel()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().messageChanged.connect(
            lambda _message: self._refresh_conn_pill()
        )
        self.statusBar().showMessage("Reader not attached")
        self._set_actions_enabled(False)
        self._refresh_conn_pill()

    def _refresh_conn_pill(self):
        """Header pill: reader state in one word, colour-coded."""
        if self._reader_session is not None:
            text, name = (
                ("In match", "ConnPillOk")
                if self._match_active
                else ("Connected", "ConnPillOk")
            )
        elif self._attach_started_at is not None:
            text, name = "Connecting...", "ConnPillBusy"
        else:
            text, name = "Offline", "ConnPillIdle"
        self.ConnPill.setText("●  " + text)
        if self.ConnPill.objectName() != name:
            self.ConnPill.setObjectName(name)
            self.ConnPill.style().unpolish(self.ConnPill)
            self.ConnPill.style().polish(self.ConnPill)
        self.ConnPill.updateGeometry()

    # ------------------------------------------------------------ timing ---

    def _apply_timing(self, *_):
        """Push the tuning spinboxes into runtime and the auto timer.

        runtime.swipe() reads these globals at call time, so every change
        takes effect on the next move -- no restart.
        """
        runtime.SWIPE_DURATION_SECONDS = float(self.SwipeDurationSpin.value())
        runtime.SWIPE_DISTANCE_PX = int(self.SwipeDistanceSpin.value())
        runtime.SWIPE_PRE_MOVE_HOLD_SECONDS = float(self.SwipePreHoldSpin.value())
        runtime.SWIPE_POST_MOVE_HOLD_SECONDS = float(self.SwipePostHoldSpin.value())
        runtime.SWIPE_PROFILE_SPEED = float(self.SwipeProfileSpeedSpin.value())
        runtime.SWIPE_USE_PROFILE = (
            self.SwipeUseProfileCheck.isChecked() and runtime.SWIPE_PROFILE is not None
        )
        # Spinbox signals can fire while the UI is still being built, before
        # the auto timer exists.
        timer = getattr(self, "_auto_timer", None)
        if timer is not None:
            timer.setInterval(int(self.AutoTickSpin.value()))
        self._save_timing_settings()

    def _refresh_swipe_profile_status(self):
        recording = runtime.SWIPE_PROFILE
        if recording is None:
            self.SwipeProfileStatus.setText("No recording")
            self.SwipeUseProfileCheck.setChecked(False)
            self.SwipeUseProfileCheck.setEnabled(False)
        else:
            self.SwipeProfileStatus.setText("Recording: " + recording.summary())
            self.SwipeUseProfileCheck.setEnabled(True)

    def _record_swipe_clicked(self):
        if getattr(self, "_swipe_record_thread", None) is not None:
            return  # one recording at a time
        self.SwipeRecordButton.setEnabled(False)
        self.SwipeProfileStatus.setText("Switch to BlueStacks and do a swipe...")
        thread = QtCore.QThread(self)
        worker = _SwipeRecorderWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._swipe_recording_finished)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self._swipe_record_thread = thread
        self._swipe_record_worker = worker
        thread.start()

    def _swipe_recording_finished(self, recording):
        self._swipe_record_thread = None
        self._swipe_record_worker = None
        self.SwipeRecordButton.setEnabled(True)
        if recording is None:
            self.SwipeProfileStatus.setText("Recording failed / too short")
            self._log("Swipe recording failed — try a longer, faster flick.")
            return
        runtime.SWIPE_PROFILE = recording
        try:
            swipe_recorder.save_profile(recording)
        except OSError as exc:
            self._log(f"Recording not saved to disk: {exc}")
        self._refresh_swipe_profile_status()
        self.SwipeUseProfileCheck.setChecked(True)
        self._apply_timing()
        self._log(f"Swipe recorded: {recording.summary()}")

    def _load_timing_settings(self):
        try:
            payload = json.loads(TIMING_SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        for key, box in (
            ("swipe_duration", self.SwipeDurationSpin),
            ("swipe_distance_px", self.SwipeDistanceSpin),
            ("swipe_pre_hold", self.SwipePreHoldSpin),
            ("swipe_post_hold", self.SwipePostHoldSpin),
            ("swipe_profile_speed", self.SwipeProfileSpeedSpin),
            ("auto_tick_ms", self.AutoTickSpin),
        ):
            value = payload.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                box.setValue(type(box.value())(value))
        if payload.get("swipe_use_profile") and runtime.SWIPE_PROFILE is not None:
            self.SwipeUseProfileCheck.setChecked(True)

    def _save_timing_settings(self):
        payload = {
            "swipe_duration": self.SwipeDurationSpin.value(),
            "swipe_distance_px": self.SwipeDistanceSpin.value(),
            "swipe_pre_hold": self.SwipePreHoldSpin.value(),
            "swipe_post_hold": self.SwipePostHoldSpin.value(),
            "swipe_profile_speed": self.SwipeProfileSpeedSpin.value(),
            "auto_tick_ms": self.AutoTickSpin.value(),
            "swipe_use_profile": self.SwipeUseProfileCheck.isChecked(),
        }
        try:
            TIMING_SETTINGS_PATH.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError:
            # Tuning that cannot be persisted still applies to this session.
            pass

    def _set_actions_enabled(self, enabled: bool):
        # A worker holding a finished (or still computing) move that nobody
        # asked to play yet is not "busy": the buttons are how it gets played.
        plan = self._auto_plan
        holding = plan is not None and not plan.armed and not plan.executing
        busy = self._move_running and not holding
        for button in (
            self.BestMoveButton,
            self.ExtraMoveButton,
            self.PointsButton,
            self.WorstMoveButton,
        ):
            button.setEnabled(enabled and not busy)
        self.AutoButton.setEnabled(enabled)
        self.WorstAutoButton.setEnabled(enabled)
        self._solo_cross_allowed = enabled and not busy
        self._update_solo_cross_button()

    @staticmethod
    def _solo_cross_key(snapshot):
        """The board and score a search answered for; any change voids the answer."""
        state = (snapshot or {}).get("state") or {}
        return (repr((snapshot or {}).get("board")), repr((snapshot or {}).get("special_board")),
                repr([player.get("score") for player in state.get("players") or []]))

    def _on_solo_cross(self, key, found: bool):
        self._solo_cross_state = (key, bool(found))
        self._update_solo_cross_button()

    def _update_solo_cross_button(self):
        snapshot = self._snapshot
        state = (snapshot or {}).get("state") or {}
        me = self._current_player(state, state.get("players") or []) or {}
        known = self._solo_cross_state
        self.SoloCrossButton.setEnabled(bool(
            self._solo_cross_allowed
            and known is not None and known[1]
            and known[0] == self._solo_cross_key(snapshot)
            and not self._memory_booster_ready(state, me)
        ))

    def _set_calc_status(self, text: str):
        self.CalcLabel.setText(f"Computing: {text}")

    def _on_plan_computed(self, plan):
        if plan is not self._auto_plan or plan.cancelled:
            return
        if plan.armed:
            self._set_calc_status(
                f"done ({plan.action_label}) - playing as soon as the game allows"
            )
        else:
            self._set_calc_status(
                f"done ({plan.action_label}) - ready, click a button"
            )

    def _log(self, message: str):
        line = f"{time.strftime('%H:%M:%S')}  {message}"
        self._recent_log.append(line)
        self.LogView.appendPlainText(line)
        append_gui_log(message)

    # Lines kept in the reader status box: enough for device -> attach ->
    # failure -> retry, short enough to stay a status and not a second log.
    READER_STATUS_LINES = 6

    def _reader_status(self, message: str) -> None:
        """Add a line to the bottom reader box; shown only while not attached.

        A retry loop repeats the same few lines (attaching, device, the same
        error) every few seconds, so a line already in the box moves to the
        bottom with a counter instead of pushing the rest out.
        """
        stamp = time.strftime("%H:%M:%S")
        lines = self._reader_status_lines
        count = 1
        for index, (_when, text, seen) in enumerate(lines):
            if text == message:
                count = seen + 1
                del lines[index]
                break
        lines.append((stamp, message, count))
        del lines[: -self.READER_STATUS_LINES]
        self.ReaderStatusLabel.setText(
            "\n".join(
                f"{when}  {text}" + (f"  (x{count})" if count > 1 else "")
                for when, text, count in lines
            )
        )
        self.ReaderStatusGroup.setVisible(self._reader_session is None)

    def _on_reader_status_signal(self, message: str) -> None:
        self._log(message)
        self._reader_status(message)

    # ------------------------------------------------------ freeze watch ---

    def _freeze_watch_tick(self):
        """Notice when the agent stops talking mid-match, and write it down.

        A settled board sends nothing, so plain silence proves nothing; the
        agent's one-second heartbeat is what makes it meaningful. An agent
        build without heartbeats is left alone.
        """
        # A diagnostic must never be what takes the window down: PyQt aborts
        # the process on an exception escaping a timer slot.
        try:
            self._freeze_watch_step()
        except Exception as exc:
            append_freeze_log([f"freeze watchdog error: {type(exc).__name__}: {exc}"])

    def _freeze_watch_step(self):
        receiver = self._reader
        incident = self._freeze_incident
        now = time.monotonic()
        if receiver is None or self._reader_session is None:
            if incident is not None:
                self._close_freeze_incident("reader detached before agent responded", now)
            return
        last = receiver.last_message_at
        if receiver.last_heartbeat_at is None or last is None:
            return
        if incident is None:
            silent = now - last
            if self._match_active and silent >= FREEZE_SILENCE_SECONDS:
                self._open_freeze_incident(receiver, silent, now)
            elif not self._match_active and silent >= IDLE_AGENT_SILENCE_SECONDS:
                self._recover_silent_idle_agent(receiver, silent, now)
            return
        if last > incident["last_message_at"]:
            self._close_freeze_incident("agent se ponovo javio", now)

    def _recover_silent_idle_agent(self, receiver, silent, now):
        """The agent stopped talking between matches: attach again on our own.

        In the lobby the agent has nothing to say but its 5 s heartbeat, so
        this much silence is an agent that is gone -- stuck in a heap walk the
        game never returned from, or a session frida dropped without saying
        so. It will not report the next match, ever. The GUI used to sit on
        "cekam pocetak partije" until the user restarted everything; now it
        drops the session and re-attaches, which is the same thing the user
        did by hand, minus the game restart -- and if the plain attach fails,
        _attach_with_recovery escalates through frida-server and the game
        itself before giving up.
        """
        last_recovery = self._idle_recovery_at
        if (
            last_recovery is not None
            and now - last_recovery < IDLE_AGENT_RECOVERY_MIN_INTERVAL_SECONDS
        ):
            return
        self._idle_recovery_at = now
        append_freeze_log([
            f"=== AGENT SILENT {silent:.0f}s IN LOBBY — reattaching reader",
            f"last heartbeat: {json.dumps(receiver.last_heartbeat, ensure_ascii=False)}",
            f"last heap walk: {json.dumps(receiver.last_choose, ensure_ascii=False)}",
        ])
        self._log(
            f"Agent silent {silent:.0f}s in lobby — detaching reader and reattaching."
        )
        self._detach_reader(f"agent silent {silent:.0f}s in lobby")
        self._reader_auto_retry = AUTO_ATTACH_ON_START
        QtCore.QTimer.singleShot(2000, self._retry_attach)

    def _open_freeze_incident(self, receiver, silent, now):
        self._freeze_incident = {
            "opened_at": now,
            "last_message_at": receiver.last_message_at,
            "game_logic": (self._snapshot or {}).get("game_logic"),
        }
        snapshot = self._snapshot or {}
        state = snapshot.get("state") or {}
        rules = state.get("rules") or {}
        players = state.get("players") or []
        created = runtime.last_created_debug_run_dir()
        dump_age = (
            None if not self._dump_inflight or self._dump_started_at is None
            else now - self._dump_started_at
        )
        lines = [
            f"=== AGENT SILENT {silent:.1f}s IN MATCH (possible game freeze)",
            f"last heartbeat: {json.dumps(receiver.last_heartbeat, ensure_ascii=False)}",
            f"last heap walk: {json.dumps(receiver.last_choose, ensure_ascii=False)}",
            "last board: "
            f"captured_at={snapshot.get('captured_at')} reason={snapshot.get('reason')} "
            f"stable={snapshot.get('stable')} game_logic={snapshot.get('game_logic')} "
            f"state={state.get('game_state')} moves={state.get('moves')} "
            f"cascade={state.get('chain_reaction')} timer={state.get('remaining_time')} "
            f"mode={rules.get('title')} "
            f"abilities={[p.get('special_ability_type') for p in players]} "
            f"jelly={bool(snapshot.get('jelly'))} froggy={bool(snapshot.get('froggy'))}",
            f"dump in flight: {self._dump_inflight}"
            + (f" (waiting {dump_age:.1f}s)" if dump_age is not None else ""),
            f"auto={self._auto_action()} move_running={self._move_running} "
            f"last_run={Path(created).name if created else None}",
            "recent log lines:",
            *(f"    {line}" for line in self._recent_log),
        ]
        append_freeze_log(lines)
        self._log(
            f"Agent silent {silent:.0f}s mid-match — game is probably frozen. "
            f"Logged to {FREEZE_LOG_PATH}"
        )

    def _close_freeze_incident(self, how, now):
        incident = self._freeze_incident
        self._freeze_incident = None
        if incident is None:
            return
        lasted = now - incident["last_message_at"]
        append_freeze_log([
            f"=== {how} (silence total ~{lasted:.1f}s), "
            f"game_logic before={incident['game_logic']} "
            f"now={(self._snapshot or {}).get('game_logic')}",
        ])
        self._log(f"Freeze over: {how} after ~{lasted:.0f}s")

    # ------------------------------------------------------------ reader ---

    def _reader_clicked(self):
        if self._reader_session is not None:
            self._reader_auto_retry = False
            self._detach_reader("manually stopped")
            return
        # A click is also how a stopped auto-attach is resumed.
        self._reader_auto_retry = AUTO_ATTACH_ON_START
        self.ReaderButton.setEnabled(False)
        self.ReaderButton.setText("Attaching...")
        self._reader_status("Attaching to game...")
        if self._last_attach_error is None:
            self._log("Attaching to game...")
        self._attach_started_at = time.monotonic()
        # Each attempt watches only itself: retries run every few seconds while
        # the game is down, and the first attempt's watchdog used to fire in
        # the middle of a later one, call it hung and switch auto-retry off.
        self._attach_attempt = getattr(self, "_attach_attempt", 0) + 1
        attempt = self._attach_attempt
        QtCore.QTimer.singleShot(
            int(ATTACH_WATCHDOG_SECONDS * 1000),
            lambda: self._attach_watchdog(attempt),
        )
        # Read on the Qt thread; the worker below must not touch widgets.
        trace_enabled = self.DebugCheck.isChecked()

        def worker():
            try:
                adb = reader.find_adb()
                # No pinned port: BlueStacks moves the instance to the next
                # free one (5555 -> 5556 ...), so the reader identifies Pie64
                # by what it is, not by the port it happens to be on.
                # Autopilot pins its instance; the identity check still runs.
                serial = reader.discover_serial(adb, self._pinned_serial)
                self._reader_signals.status.emit(f"Uredjaj: {serial}")
                reader.ensure_frida_server(adb, serial)
                receiver = GuiBoardReader(
                    reader.DEFAULT_OUTPUT,
                    reader.DEFAULT_LATEST,
                    self._reader_signals,
                )
                device, session, script, pid = self._attach_with_recovery(
                    adb,
                    serial,
                    receiver,
                    spawn=False,
                    # The engine says when the move phase is open, so the
                    # board does not have to be proven settled by repetition:
                    # poll fast and take the minimum two samples. This is the
                    # difference between playing ~0.2 s and ~1 s after a board
                    # settles.
                    poll_seconds=0.1,
                    include_state=True,
                    stable_samples=2,
                    idle_seconds=READER_IDLE_SECONDS,
                    quiet_seconds=READER_QUIET_SECONDS,
                    ctor_hook=READER_CTOR_HOOK,
                    # Matches this GUI (or the one before it) saw end in the
                    # game process that is still running: the agent must not
                    # pick their leftover logic up as a match.
                    dead_logics=load_dead_logics(),
                )
            except Exception as exc:
                self._reader_signals.stopped.emit(str(exc))
                return
            # Set here, not on the attached signal: the agent's first
            # match_state can land before that signal is processed.
            self._adb_device = (adb, serial)
            self._reader_signals.adb_device.emit()
            self._reader_pid = int(pid)
            self._reader = receiver
            self._reader_session = session
            self._reader_script = script
            self._apply_trace_mode(
                trace_enabled, report=self._reader_signals.status.emit
            )
            # Whether the constructor hook took is worth one line in the log:
            # without it every board resolve pays the ~37 ms heap walk again,
            # and nothing else would show the difference.
            try:
                status = script.exports_sync.status()
                hook = status.get("ctorHook")
                if hook == "on":
                    self._reader_signals.status.emit(
                        "Constructor hook active — no heap walk needed"
                    )
                elif hook == "off" and not READER_CTOR_HOOK:
                    self._reader_signals.status.emit(
                        "Constructor hook disabled (by design) — using heap walk"
                    )
                else:
                    self._reader_signals.status.emit(
                        f"Constructor hook failed ({hook}: "
                        f"{status.get('ctorHookError')}) — using heap walk"
                    )
                # Leaving a match is only caught by the Dispose hook; when it
                # did not take, the exit falls back to the quiet timeout.
                dispose = status.get("disposeHook")
                if dispose is not None and dispose != "on":
                    self._reader_signals.status.emit(
                        f"Match-leave hook failed ({dispose}: "
                        f"{status.get('disposeHookError')}) — will detect "
                        "end via quiet board only"
                    )
                # A concede is only fast through the Conceded hook; without
                # it the match closes on the quiet timeout, and a stuck
                # reader after a concede is the first thing to check here.
                # Automatic concede recognition is off by the player's choice
                # (2026-09-15): the hook fired on ends that were not ends, and
                # the button is the exact signal. Only a hook that tried and
                # failed is worth a line.
                concede = status.get("concedeHook")
                if concede == "failed":
                    self._reader_signals.status.emit(
                        f"Concede hook failed ({status.get('concedeHookError')})"
                    )
            except Exception as exc:
                self._reader_signals.status.emit(f"Reader status not read: {exc}")
            # Attaching takes seconds (adb + frida + agent ready), so the button
            # state must follow this signal, not a fixed timer.
            self._reader_signals.attached.emit(int(pid))

        self._reader_thread = threading.Thread(target=worker, daemon=True)
        self._reader_thread.start()

    def _attach_watchdog(self, attempt=None):
        """Say so when an attach has hung, and give the button back.

        The worker thread cannot be interrupted -- it is blocked inside frida --
        so this does not cancel anything. It reports, and it makes the window
        usable again, which is the difference between "stuck" and "broken".
        """
        if self._reader_session is not None or self._attach_started_at is None:
            return
        if attempt is not None and attempt != getattr(self, "_attach_attempt", attempt):
            # A later attempt is running and has its own watchdog.
            return
        waited = time.monotonic() - self._attach_started_at
        self._attach_started_at = None
        # Retrying on top of a hung attach only adds a second stuck thread.
        self._reader_auto_retry = False
        self._log(
            f"Attach hanging for {waited:.0f}s. The game probably still holds the old "
            "agent from the previous session — try 'Restart Frida', and if that "
            "doesn't help restart BlueStacks."
        )
        self.statusBar().showMessage("Attach hanging — see log")
        self._reader_status(
            f"Attach hanging {waited:.0f}s — try 'Restart Frida', then BlueStacks"
        )
        self.ReaderButton.setEnabled(True)
        self.ReaderButton.setText("Attach Reader")

    def _attach_with_recovery(self, adb, serial, receiver, **kwargs):
        """Attach, and repair the usual breakage instead of asking the user to.

        The reader used to need "restart BlueStacks and the GUI" now and then,
        with no way to tell when. Two things actually break, and both are
        fixable from here:

        * frida-server holding sessions a killed GUI never closed -- restarting
          the server drops them;
        * the game process itself left with a stale agent or suspended threads
          -- a new process fixes that, and the emulator does not have to go.

        Only if both fail is BlueStacks genuinely the answer, and then it says
        so with the device state that led to the conclusion.
        """
        package = reader.DEFAULT_PACKAGE
        agent = reader.DEFAULT_AGENT
        attempts = (
            ("prvi pokusaj", None),
            ("posle restarta frida-servera", "frida"),
            ("posle restarta igre", "game"),
        )
        last_error = None
        for label, repair in attempts:
            if repair == "frida":
                self._reader_signals.status.emit(
                    "Attach failed — restarting frida-server and retrying..."
                )
                reader.restart_frida_server(adb, serial)
            elif repair == "game":
                self._reader_signals.status.emit(
                    "Still failing — restarting game (BlueStacks stays)..."
                )
                reader.restart_game(adb, serial, package)
                # A fresh process has no agent and no forwarded session.
                receiver.ready_event.clear()
                receiver.detached_event.clear()
            try:
                result = reader.attach_reader(
                    adb, serial, package, agent, receiver, **kwargs
                )
                if repair is not None:
                    self._reader_signals.status.emit(f"Succeeded {label}.")
                return result
            except Exception as exc:
                last_error = exc
                receiver.ready_event.clear()
                self._reader_signals.status.emit(f"Attach failed ({label}): {exc}")
        # Everything this GUI can do from the outside has been tried.
        report = {}
        try:
            report = reader.diagnose(adb, serial, package)
        except Exception:
            pass
        raise reader.ReaderError(
            f"{last_error}. Neither frida-server restart nor game restart helped — "
            "this needs a BlueStacks restart. Device state: "
            + ", ".join(f"{key}={value}" for key, value in report.items())
        )

    def _on_reader_attached(self, pid: int):
        self._attach_started_at = None
        self._last_attach_error = None
        self._log(f"Reader attached to PID {pid}")
        # Connected: the attach story is over, so the box goes and starts clean
        # for the next time something breaks.
        self._reader_status_lines.clear()
        self.ReaderStatusGroup.setVisible(False)
        # Whatever is on the panel predates this attach. The agent reports a
        # running match within a tick if there is one, so showing the previous
        # match until then only invites "why does it think I am playing?".
        if not self._match_active:
            self._clear_match_view()
        self._refresh_reader_button()

    def _end_match_clicked(self):
        """Predaja: close the match by hand, through the same edge as a real end.

        Not every exit is reported by the engine (a concede the hook misses,
        backing out of a solo match): the match then stays "u toku" on a board
        nobody is playing, with auto waiting on it. The agent does the closing
        so both sides agree: it marks the logic dead, sends match_state(False)
        and the GUI's _on_match_state resets and clears exactly as it does
        after a natural end; the idle tick then picks the next match up from
        the counter as usual.
        """
        script = self._reader_script
        if script is None:
            self._log("Reader not attached — no match to forfeit.")
            if self._match_active:
                self._on_match_state(False, "forfeit (no reader)", {})
            return
        self._stop_auto()
        self._log("Forfeit: closing match manually...")

        def ask():
            try:
                # "predaja (dugme)" is not a soft end for the agent, so the
                # logic is marked dead and reported back with its key -- the
                # GUI then handles it exactly like a natural end.
                detail = reader._export_call(
                    script.exports_sync, ("end_match", "endMatch"), "forfeit (button)"
                ) or {}
            except Exception as exc:
                self._reader_signals.status.emit(f"Forfeit did not go through agent: {exc}")
                # The agent did not answer; at least the GUI stops treating the
                # board as live so the reader button says what is going on.
                self._reader_signals.match_state.emit(False, "forfeit (no agent)", {})
                return
            if not detail.get("was_active"):
                self._reader_signals.status.emit(
                    "Agent already waiting for match start — nothing to forfeit, "
                    "next match will be picked up automatically."
                )
                # The GUI may still be showing a board the agent has already
                # let go of; bring it to the same idle state.
                if self._match_active:
                    self._reader_signals.match_state.emit(False, "forfeit (button)", {})

        # Never on the GUI thread: a synchronous RPC into the game.
        threading.Thread(target=ask, daemon=True).start()

    def _on_match_state(self, active: bool, reason: str, payload=None):
        was_active = self._match_active
        self._match_active = bool(active)
        payload = payload if isinstance(payload, dict) else {}
        # A final end (the engine's concede/dispose/finished state, and the
        # user's own Predaja button) is remembered per game process, so the
        # next attach hands it back to the agent and a restarted reader does
        # not take that match's corpse for a live one. The button used to be
        # left out: pressed on a running match (2026-09-15 10:28:46) plus a GUI
        # restart, the fresh agent refused the live match until the game was
        # restarted. Since then `wake` revives a dead-listed logic the engine
        # still calls open as soon as a move button or Auto is pressed, and the
        # player chose (2026-09-22) to treat a Predaja match as over for good.
        if (
            not active
            and payload.get("dead")
            and payload.get("logic_key")
            and self._reader_pid is not None
        ):
            remember_dead_logic(self._reader_pid, str(payload["logic_key"]))
        # Autopilot hears start/end first: on start it arms Auto (which turns
        # itself off at the end below), on end it heads back to the lobby.
        self.AutopilotPanel.on_match_state(bool(active))
        if not active:
            self._requested_action = None
            self._hide_lookahead_label()
            if self._auto_plan is not None:
                self._auto_plan.cancel()
        if active:
            self._log(f"Match started ({reason}) — reader reading board")
        else:
            self._log(f"Match ended ({reason}) — reader waiting for next")
            # The move burner is for this match's leftover moves only; the
            # next match must not open with worst moves.
            if self.WorstAutoButton.isChecked():
                self.WorstAutoButton.setChecked(False)
            # Auto goes off with the match too (player, 2026-09-20): left on, it
            # sat in "cekam pocetak partije" and opened the next match by
            # itself. Only when a match really ended under it -- Auto armed in
            # the lobby before the first match still waits for that match.
            if was_active and self.AutoButton.isChecked():
                self.AutoButton.setChecked(False)
            # Per-match strategy state belongs to the match that just ended.
            self._reset_match_state()
            self._clear_match_view()
        self._refresh_reader_button()

    def _clear_match_view(self):
        """Blank the panel between matches.

        The engine leaves the finished match's board on the heap, so the last
        snapshot stays a perfectly plausible-looking board -- with the mode,
        score and pieces of a match that is over. Left on screen in the lobby it
        reads as "the bot thinks I am playing", which is exactly the confusion
        this gate exists to remove.
        """
        self._snapshot = None
        self._snapshot_received_at = None
        for label in (
            self.StateLabel,
            self.ScoreLabel,
            self.MovesLabel,
            self.BoosterLabel,
            self.ModeLabel,
            self.PerksLabel,
            self.MutationsLabel,
            self.TurnLabel,
        ):
            label.setText("-")
        self.StatePanel.reset()
        self.FreshLabel.setText("no match")
        for row in self._cells:
            for cell in row:
                cell.setVisible(False)

    def _refresh_reader_button(self):
        attached = self._reader_session is not None
        self.ReaderButton.setEnabled(True)
        self.ReaderButton.setText("Detach Reader" if attached else "Attach Reader")
        self._set_actions_enabled(attached)
        self._refresh_conn_pill()
        if attached:
            self.statusBar().showMessage(
                "Reader active — match in progress"
                if self._match_active
                else "Reader active — waiting for match"
            )

    def _detach_reader(self, reason: str):
        script, session = self._reader_script, self._reader_session
        self._reader_script = self._reader_session = self._reader = None
        self._match_active = False
        self._hide_lookahead_label()
        self._stop_auto()
        # Off the GUI thread. Both calls talk to the agent over adb-forwarded
        # frida and can block for as long as the game takes to answer -- the
        # same synchronous-RPC-on-the-Qt-thread mistake that froze this window
        # for 174 s once already. The handles are dropped above, so nothing
        # here is needed for the GUI to carry on.
        def close():
            for handle, method in ((script, "unload"), (session, "detach")):
                if handle is not None:
                    try:
                        getattr(handle, method)()
                    except Exception:
                        pass

        closer = None
        if script is not None or session is not None:
            closer = threading.Thread(target=close, daemon=True)
            closer.start()
        self._log(f"Reader detached: {reason}")
        self._reader_status(f"Reader detached: {reason}")
        self._clear_match_view()
        self.statusBar().showMessage("Reader not attached")
        self._refresh_reader_button()
        return closer

    def _on_reader_stopped(self, message: str):
        self._requested_action = None
        if self._auto_plan is not None:
            self._auto_plan.cancel()
        self._reader_script = self._reader_session = self._reader = None
        self._match_active = False
        self._hide_lookahead_label()
        self._attach_started_at = None
        self._reader_status(f"Error: {message}")
        # Recovery already restarted the server and the game; retrying on a
        # timer would just restart the game again, forever. This one needs a
        # human and says so.
        if "restart BlueStacks" in message:
            self._reader_auto_retry = False
            self._log(f"Reader cannot attach: {message}")
            self.statusBar().showMessage("Restart BlueStacks — see log")
            self._refresh_reader_button()
            return
        # Retrying every few seconds while the game is not up yet would fill the
        # log with the same line; the first one already says what is wrong.
        repeated = message == self._last_attach_error
        self._last_attach_error = message
        if not repeated:
            self._log(f"Reader failed: {message}")
            if "libil2cpp" in message or "ready" in message:
                self._log(
                    "Tip: if the game crashed earlier, try 'Restart Frida'."
                )
        self.statusBar().showMessage("Reader not attached")
        self._refresh_reader_button()
        if self._reader_auto_retry:
            self.statusBar().showMessage(
                f"Reader not attached — retrying in {READER_RETRY_SECONDS:.0f}s"
            )
            QtCore.QTimer.singleShot(
                int(READER_RETRY_SECONDS * 1000), self._retry_attach
            )

    def _on_reader_detached(self, receiver, reason: str):
        """Frida dropped the live session: stop, clean up, and attach again.

        Nothing handled this before: the handles stayed set, `_match_active`
        stayed True, every tick started a dump that failed at once ("Ne mogu da
        zatrazim svezu tablu", ~40 lines/s), and the lobby watchdog never ran
        because a match was "active". Auto sat there until someone stepped in.
        """
        if receiver is not self._reader:
            # A session this GUI already let go of (its own detach, or one
            # replaced by a re-attach) reporting late.
            return
        if self._match_active:
            self._reset_match_state()
            self._clear_match_view()
        self._stop_auto()
        self._on_reader_stopped(f"Frida veza pukla ({reason})")

    def _retry_attach(self):
        """Try again, unless something already succeeded or was cancelled."""
        if not self._reader_auto_retry or self._reader_session is not None:
            return
        self._reader_clicked()

    def _restart_frida_clicked(self):
        self.RestartFridaButton.setEnabled(False)
        self._log("Restarting frida-server on device...")

        def worker():
            try:
                adb = reader.find_adb()
                serial = reader.discover_serial(adb)
                reader.adb_shell(adb, serial, "su -c 'pkill -9 frida-server || true'")
                time.sleep(1.5)
                reader.adb_shell(
                    adb,
                    serial,
                    "su -c 'chmod 755 /data/local/tmp/frida-server; "
                    "nohup /data/local/tmp/frida-server "
                    ">/data/local/tmp/frida-server.log 2>&1 &'",
                )
                deadline = time.monotonic() + 8.0
                while time.monotonic() < deadline:
                    pid = reader.adb_shell(
                        adb, serial, "su -c 'pidof frida-server || true'"
                    ).strip()
                    if pid:
                        self._reader_signals.status.emit(f"frida-server podignut, PID {pid}")
                        break
                    time.sleep(0.25)
                else:
                    self._reader_signals.status.emit("frida-server se nije podigao")
            except Exception as exc:
                self._reader_signals.status.emit(f"Restart nije uspeo: {exc}")
            finally:
                QtCore.QMetaObject.invokeMethod(
                    self.RestartFridaButton,
                    "setEnabled",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(bool, True),
                )

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------- kalibracija ---

    def _live_board_profile(self, state, board=None):
        """(profile, board_size) for the board that is actually being played.

        Both GUIs read the same `display_calibration.json`, so Supersize only
        ever needed the profile *name* to travel down this path -- the main GUI
        takes it from its dropdown, and here it is a fact rather than a setting
        to keep in sync. The dumped board decides, because that is the grid the
        simulator plans on; `rules.board_size` covers the frames before the
        first board arrives.
        """
        board_size = len(board) if board else (state.get("rules") or {}).get("board_size")
        if board_size is None:
            return board_profiles.DEFAULT_PROFILE, None
        return board_profiles.profile_for_board_size(board_size), board_size

    def _track_board_profile(self, state, board=None):
        profile, board_size = self._live_board_profile(state, board)
        changed = profile != self._board_profile
        self._board_profile = profile
        if changed and profile is not None:
            size = BOARD_PROFILES[profile]["boardSize"]
            self._log(f"Board {size}x{size}: switching to profile {profile}")
        if profile is None:
            if board_size != self._warned_board_size:
                self._warned_board_size = board_size
                self._log(
                    f"WARNING: engine reports board {board_size}x{board_size}, but "
                    "there is no profile for that size — moves would hit wrong cells."
                )
            return
        if profile in self._warned_uncalibrated:
            return
        if not board_profiles.has_relative_calibration(profile, PROJECT_ROOT):
            # The legacy absolute config would still load and still click, just
            # at whatever pixels were saved on another window size.
            self._warned_uncalibrated.add(profile)
            self._log(
                f"WARNING: profile {profile} "
                f"({BOARD_PROFILES[profile]['boardSize']}x"
                f"{BOARD_PROFILES[profile]['boardSize']}) is not calibrated on this "
                "screen — click Calibrate."
            )

    def _calibrate_clicked(self):
        # The two-click overlay lives in the main GUI; reusing it keeps a single
        # implementation of the click capture and its validation rules.
        from gui import _CalibrationOverlay

        # Calibrate the board that is actually on screen, not a fixed 7x7: with
        # the reader attached the engine has already said how big it is.
        profile = self._board_profile
        if profile is None:
            state = (self._snapshot or {}).get("state") or {}
            _, board_size = self._live_board_profile(state)
            QtWidgets.QMessageBox.warning(
                self,
                "Calibration not started",
                f"No profile for {board_size}x{board_size} board in "
                "board_profiles.py, nothing to calibrate.",
            )
            return
        board_size = BOARD_PROFILES[profile]["boardSize"]
        self._stop_auto()
        answer = QtWidgets.QMessageBox.information(
            self,
            "Screen Calibration",
            f"Open a {board_size}x{board_size} board in BlueStacks with no popups.\n\n"
            "After OK, click the center of the TOP-LEFT cell, then the BOTTOM-RIGHT cell.\n"
            "Old calibration stays until you confirm the new one.",
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
        )
        if answer != QtWidgets.QMessageBox.Ok:
            return
        try:
            window = find_bluestacks_window()
            if bool(getattr(window, "isMinimized", False)):
                window.restore()
            window.activate()
            client_rect = client_rect_for_window(window)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self, "Calibration not started", f"BlueStacks not available:\n{exc}"
            )
            return

        overlay = _CalibrationOverlay()
        self._calibration_overlay = overlay
        overlay.completed.connect(
            lambda first, second: self._finish_calibration(
                profile, client_rect, first, second
            )
        )
        overlay.cancelled.connect(lambda: self._log("Calibration cancelled"))
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    def _finish_calibration(self, profile, client_rect, first, second):
        self._calibration_overlay = None
        board_size = BOARD_PROFILES[profile]["boardSize"]
        try:
            config = validate_board_calibration(first, second, board_size, client_rect)
        except BoardCalibrationError as exc:
            QtWidgets.QMessageBox.warning(
                self, "Calibration rejected", f"Nothing was changed.\n\n{exc}"
            )
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Confirm calibration",
            f"Board: left={config['left']}, up={config['up']}\n"
            f"Cell: {config['squareSize']} px\n"
            f"Size: {config['width']} x {config['height']} px\n\n"
            "Save? The previous JSON gets a .bak copy.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            self._log("Calibration not saved; old one remains active")
            return
        try:
            save_board_calibration(profile, first, second, client_rect, PROJECT_ROOT)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._warned_uncalibrated.discard(profile)
        self._log(
            f"Calibration saved ({profile} {board_size}x{board_size}): "
            f"left={config['left']} up={config['up']} "
            f"cell={config['squareSize']}px"
        )

    def _launch_clicked(self):
        self.LaunchButton.setEnabled(False)
        self.LaunchButton.setText("Launching...")

        def worker():
            result = matchmasters_launcher.launch_match_masters(
                start_reader=False,  # this GUI attaches its own in-process reader
                progress=self._launcher_signals.progress.emit,
            )
            self._launcher_signals.done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_launch_done(self, result):
        self.LaunchButton.setEnabled(True)
        self.LaunchButton.setText("Launch Game")
        self._log(str(getattr(result, "message", result)))

    # ---------------------------------------------------------- snapshot ---

    @guarded_slot
    def _on_snapshot(self, snapshot):
        self._snapshot = snapshot
        self._update_solo_cross_button()
        try:
            from strategy_lab.live import observe_snapshot
            observe_snapshot(snapshot)
        except Exception:
            pass  # Strategy Lab diagnostics must not interrupt the reader.
        # Host-side arrival time, not the agent's `captured_at`: the emulator's
        # clock is its own, while what matters here is how long ago *this GUI*
        # last heard from the game.
        self._snapshot_received_at = time.monotonic()
        self._record_frame(snapshot)
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        me = self._current_player(state, players)
        if self._match_active:
            self._update_lookahead_label(state)

        # Once per change, not per snapshot: the engine dealt us a colour other
        # than the usual Blue, and every colour in this GUI is relabeled for it.
        swap_note = next(
            (
                warning
                for warning in snapshot.get("warnings") or ()
                if str(warning).startswith("player_colors_swapped")
            ),
            None,
        )
        if swap_note != getattr(self, "_player_color_swap_logged", None):
            self._player_color_swap_logged = swap_note
            if swap_note is not None:
                self._log(
                    "This match: our color is not engine-blue — colors are "
                    f"swapped ({swap_note.split(':', 1)[-1]})"
                )

        raw_state = state.get("game_state")
        self.StateLabel.setText(
            f"{GAME_STATE_LABELS.get(raw_state, raw_state)}  "
            f"(kaskada {state.get('chain_reaction')})"
        )
        self.MovesLabel.setText(
            f"{state.get('moves')}  (played this turn: {state.get('moves_made_this_turn')})"
        )
        if me is not None:
            multiplier = self._track_score_multiplier(snapshot)
            self.ScoreLabel.setText(
                f"{me.get('score')}  (this turn: {me.get('turn_score')})"
                + (f"  x{multiplier}" if multiplier > 1 else "")
                + (
                    f"   opponent: {self._opponent_score(state, players)}"
                    if len(players) > 1
                    else ""
                )
            )
            self.BoosterLabel.setText(
                f"{me.get('energy')}/{me.get('energy_to_ability')}"
            )
        self._track_match_reset(snapshot, state)
        self._refresh_refill_panel()
        self._track_turn_clock(state)
        self._refresh_booster_from_memory(me)
        self._track_ufo_eyes(state, me)
        self._track_mixy_code_spend(me, state)
        self._refresh_score_legend(snapshot)
        self._refresh_perks(me)
        self._refresh_mutations(snapshot)
        rules = state.get("rules") or {}
        self._track_board_profile(state, snapshot.get("board"))
        mode = self._effective_mode(state)
        rules_id = rules.get("id")
        if rules_id and mode is GameMode.NONE:
            handled_by = self._handled_outside_mode(rules_id)
            known = handled_by is not None or self._has_no_strategy_change(rules_id)
            if handled_by is not None:
                unmapped = f" (pravila: {handled_by})"
            else:
                unmapped = " (bez posebnih pravila)" if known else " (nemapiran)"
        else:
            known = True
            unmapped = ""
        self._log_ruleset_once(rules_id, mode, rules)
        self._handle_unmapped_mode(rules_id, mode, known, snapshot)
        lights_up = self._lights_up_request_state(snapshot, me)
        lit_column = None if lights_up is None else lights_up["column"]
        column_mania = self._column_mania_request_state(snapshot)
        if lights_up is not None:
            mode_suffix = f"   sija kolona {lit_column + 1} (x{lights_up['multiplier']})"
        elif column_mania is not None:
            ramp = " ".join(f"x{value}" for value in column_mania["multipliers"])
            mode_suffix = f"   kolone {ramp}"
        elif mode is GameMode.FLOOR_IS_LAVA:
            mode_suffix = "   " + self._floor_lava_status_text(snapshot)
        elif mode is GameMode.FUNKY_TILES:
            funky = board_source.funky_tile_cells(snapshot)
            mode_suffix = (
                "   funky NE CITA iz memorije"
                if funky is None
                else f"   funky iz memorije: {len(funky)} polja"
            )
        elif mode is GameMode.VEGAS_VIEWS:
            vegas = board_source.vegas_views_state(snapshot)
            mode_suffix = (
                "   vegas NE CITA iz memorije"
                if vegas is None
                else f"   vegas: {len(vegas['cells'])} polje x{vegas['multiplier']}"
            )
        else:
            mode_suffix = ""
        self.ModeLabel.setText(
            self._mode_label_text(state, rules_id, mode, unmapped, mode_suffix)
        )
        # Naslov moda, bedz tipa partije (Solo Challenge / Party /
        # Showdown / 1v1) i koje kartice uopste postoje za ovu partiju.
        self.StatePanel.update_match(rules, players, state, me)
        self.TurnLabel.setText(self._turn_label_text(state))
        self.FreshLabel.setText(
            f"{snapshot.get('signature')} / {snapshot.get('state_signature')} "
            f"({snapshot.get('captured_at', '')[11:19]})"
        )
        self._render_board(snapshot, lit_column=lit_column)
        self._render_cleo_odds(snapshot, rules)
        # Act on the board that just landed instead of waiting out the rest of
        # the tick interval. The tick itself keeps running as the safety net
        # for everything that is not driven by an arriving snapshot.
        #
        # The guard is not optional: a refresh inside the tick (or inside
        # _play's own freshness check) lands right here, and without it the
        # nested call would run the gates again and play a second time on the
        # same board.
        # Not only with Auto on: with Auto off the tick starts the speculative
        # computation of the best move on the board that just arrived.
        if not self._auto_dispatching:
            self._auto_dispatching = True
            try:
                self._auto_tick()
            finally:
                self._auto_dispatching = False

    def _render_board(self, snapshot, lit_column=None):
        board = snapshot.get("board") or []
        special = snapshot.get("special_board") or []
        size = len(board)
        for row in range(self._board_grid_size):
            for col in range(self._board_grid_size):
                cell = self._cells[row][col]
                # Supersize uses the whole grid; a 7x7 match must not leave a
                # dead 8th row and column standing next to the live board.
                inside = row < size and col < size
                cell.setVisible(inside)
                if not inside:
                    continue
                try:
                    color = int(board[row][col])
                    special_value = int(special[row][col])
                except (IndexError, TypeError, ValueError):
                    continue
                background, foreground, symbol = CELL_COLORS.get(
                    color, ("#20232b", "#6b7280", "?")
                )
                cell.setText(symbol if not special_value else f"{symbol}\n{special_value}")
                # Lights Up draws one column lit; outlining it here is the
                # whole support the mode gets -- the scoring never sees it.
                border = (
                    "2px solid #f59e0b" if col == lit_column else "2px solid transparent"
                )
                cell.setStyleSheet(
                    f"background:{background};color:{foreground};"
                    f"border-radius:8px;border:{border};"
                )

    _CLEO_DIRECTION_LABELS = {
        "up": ("↑", "gore"),
        "down": ("↓", "dole"),
        "left": ("←", "levo"),
        "right": ("→", "desno"),
    }

    @staticmethod
    def _color_chip(color, text=None):
        background, foreground, symbol = CELL_COLORS.get(
            color, ("#20232b", "#6b7280", "?")
        )
        return (
            f"<span style='background:{background};color:{foreground};"
            f"font-weight:bold;'>&nbsp;{text or symbol}&nbsp;</span>"
        )

    def _render_cleo_odds(self, snapshot, rules):
        """Per-Cleo, per-swipe extra-move odds; hidden when no Cleo is on board."""
        self._cleo_render_args = (snapshot, rules)
        board = snapshot.get("board") or []
        special = snapshot.get("special_board") or []
        allow_square = bool((rules or {}).get("is_square_match"))
        try:
            key = (
                tuple(tuple(int(v) for v in row) for row in board),
                tuple(tuple(int(v) for v in row) for row in special),
                allow_square,
            )
        except (TypeError, ValueError):
            key = None
        if key is not None and key == self._cleo_odds_key:
            return
        self._cleo_odds_key = key
        if key is None or not any(SPECIAL_CLEO_BUG in row for row in key[1]):
            # Keep the last Cleo verdict readable after the Cleo is gone.
            if self._cleo_tally:
                self.CleoOddsLabel.setText("No Cleo piece on the board.")
                self.CleoGroup.show()
            else:
                self.CleoGroup.hide()
            return
        try:
            # Only the profile read for exactly this layout: the use counter of
            # an older board would be wrong here.
            remembered_special, remembered_profile = self._cleo_profile
            odds_params = (
                {"profile": remembered_profile}
                if remembered_profile is not None and remembered_special == key[1]
                else None
            )
            if odds_params is None and remembered_profile is not None:
                # Memory values exist in this game but not yet for this layout
                # (mid-animation; read once the board rests). The PvP fallback
                # said 84% where the game's own values give 49% on the same
                # board (Solo, Cleo Cadabra figure, 2026-11-07 17:21), so show
                # nothing rather than a number that will drop.
                self.CleoOddsLabel.setText(
                    "Cekam vrednosti iz memorije (tabla se jos smiruje)..."
                )
                self.CleoGroup.show()
                return
            odds = cleo_swipe_odds(
                [list(row) for row in key[0]],
                [list(row) for row in key[1]],
                allow_square_matches=allow_square,
                odds_params=odds_params,
            )
        except Exception as error:  # a readout must never break snapshot handling
            self.CleoOddsLabel.setText(f"Calculation error: {error}")
            self.CleoGroup.show()
            return

        blocks = [
            "Procenti: vrednosti iz memorije igre"
            if odds_params is not None
            else "Procenti: PvP pretpostavka (jos nema vrednosti iz memorije)"
        ]
        for (row, col), swipes in odds:
            lines = [f"<b>Cleo</b> &nbsp;red {row + 1}, kolona {col + 1}"]
            if not swipes:
                lines.append("&nbsp;&nbsp;no swap with an ordinary piece")
            chances = [swipe.extra_probability for swipe in swipes]
            # Star the best swipe only when it actually beats another one.
            best = max(chances) if chances and max(chances) > min(chances) else -1.0
            order = {"up": 0, "right": 1, "down": 2, "left": 3}
            by_neighbour = {}
            for swipe in swipes:
                by_neighbour.setdefault(swipe.direction.value, []).append(swipe)
            indent = "&nbsp;" * 5
            for direction in sorted(by_neighbour, key=lambda value: order.get(value, 9)):
                pair = by_neighbour[direction]
                arrow, word = self._CLEO_DIRECTION_LABELS.get(direction, ("?", direction))
                partner_color = pair[0].partner_color
                name = COLOR_NAMES.get(partner_color, str(partner_color))
                lines.append(
                    f"&nbsp;&nbsp;{arrow} {word} {self._color_chip(partner_color, name)}"
                )
                # Cleo dragged first, then the neighbour dragged onto Cleo: the
                # two leave the empty cell in different places.
                for swipe in sorted(pair, key=lambda s: not s.drags_cleo):
                    percent = round(swipe.extra_probability * 100)
                    share = f"{len(swipe.extra_colors)}/{len(swipe.eligible_colors)}"
                    if percent >= 100:
                        tone = "#22c55e"
                    elif percent >= 50:
                        tone = "#eab308"
                    else:
                        tone = "#9ca3af"
                    how = "Cleo na figuru" if swipe.drags_cleo else "figura na Cleo"
                    chips = " ".join(
                        self._color_chip(color) for color in swipe.extra_colors
                    )
                    marker = " &#9733;" if swipe.extra_probability == best else ""
                    lines.append(
                        f"{indent}{how}: "
                        f"<span style='color:{tone};font-weight:bold;'>{percent}%</span>"
                        f" ({share}){marker}" + (f" &nbsp;{chips}" if chips else "")
                    )
            blocks.append("<br>".join(lines))
        self.CleoOddsLabel.setText("<br><br>".join(blocks))
        self.CleoGroup.show()

    @classmethod
    def _seconds_per_move(cls, rules, players):
        """Measured clock cost of one move on a timed board, None without a clock."""
        if not rules.get("is_timer"):
            return None
        if cls._strategy_mode(rules, players) == STRATEGY_VERSUS_2:
            return VERSUS_SECONDS_PER_MOVE
        return TIME_BOUND_SECONDS_PER_MOVE

    @staticmethod
    def _strategy_mode(rules, players):
        """Solo scoring vs. head-to-head, decided by MatchRulesModel.pvpMode.

        PVPMode is the only field that says what the match is: PvP=0 is a real
        1v1, Solo=1 and Rumble=2 are point races. ``rumblePlayersAmount`` is not
        a signal -- a plain versus match still carries the template's 50.
        """
        pvp_mode = rules.get("pvp_mode")
        if pvp_mode == PVP_MODE_PVP:
            return STRATEGY_VERSUS_2
        if pvp_mode in (PVP_MODE_SOLO, PVP_MODE_RUMBLE):
            return STRATEGY_SOLO_6
        return STRATEGY_VERSUS_2 if len(players) > 1 else STRATEGY_SOLO_6

    @classmethod
    def _memory_score_state(cls, state, players, me):
        """Feed the exact scores to the strategy, marked as memory-sourced.

        Without this the strategy sees no scores at all and plays "normal",
        never using the ahead/behind logic that versus modes depend on.
        """
        our_score = (me or {}).get("score")
        if our_score is None:
            return None
        opponent_score = cls._opponent_score(state, players)
        deficit = (
            None if opponent_score is None else int(opponent_score) - int(our_score)
        )
        state = state or {}
        me = me or {}

        def as_int(value):
            return None if value is None else int(value)

        # The debug layer reads its before/after meters out of `resolved`
        # (state_reader.json). Without it every observed_delta came back
        # with booster_charge_gained/kept_the_turn = null, so no prediction
        # was ever checked against what the game did -- even though memory
        # carries all three exactly.
        resolved = {
            "booster_charge": as_int(me.get("energy")),
            "booster_maximum": as_int(me.get("energy_to_ability")),
            "remaining_moves": as_int(state.get("moves")),
            "current_round": cls._contract_round(state),
            "total_rounds": as_int(state.get("rounds_total")),
            # Left as None this silently disabled the whole extra-move
            # verification: _kept_the_turn refuses to judge unless it knows
            # both reads happened on our turn, so every promised extra came
            # back "unknown" instead of confirmed or broken. Memory answers
            # it outright.
            "turn_owner": (
                None
                if me.get("is_my_turn") is None
                else ("us" if me.get("is_my_turn") else "them")
            ),
            "our_score": int(our_score),
            "opponent_score": None if opponent_score is None else int(opponent_score),
            "score_deficit": deficit,
            # The engine's own "the booster is ready" flag. The screen path
            # has to infer this from an ACTIVATE template, and on
            # 2026-08-17 03:51:30 that template scored 0.70 and was read as
            # "not ready" while memory had the meter at 7/7 -- so the bot
            # spent the turn on a move with no extra and left the booster
            # sitting there. abilityLocked is the one rule that makes a full
            # meter unusable, so it is honoured here.
            "booster_ready": cls._memory_booster_ready(state, me),
        }
        # Every field above that memory actually answered is stamped as
        # memory-sourced -- built from the dict itself, not a hand-kept list.
        # The 2026-08-23 sweep found turn_owner, booster_maximum,
        # current_round/total_rounds and opponent_score present in `resolved`
        # but missing from `sources`, so consumers that gate on
        # sources[field] == "memory" (memory_reader_booster_ready,
        # _resolved_state_source) could never see them as memory. A None value
        # stays unstamped on purpose: "memory has no answer" must leave the
        # screen fallback for that field alive.
        sources = {
            key: SCORE_SOURCE_MEMORY
            for key, value in resolved.items()
            if value is not None
        }
        # Legacy key: the runtime's score-source bookkeeping
        # (runtime.py:3269) tracks the effective score under "score", and the
        # score block itself is unconditionally memory here (our_score was
        # checked above), so the stamp is kept for debug-trail continuity.
        sources["score"] = SCORE_SOURCE_MEMORY
        resolved["sources"] = sources
        return {
            "score": {
                "accepted": True,
                "our_score": int(our_score),
                "opponent_score": None if opponent_score is None else int(opponent_score),
                "score_deficit": deficit,
                "confidence": 1.0,
                "source": SCORE_SOURCE_MEMORY,
            },
            "resolved": resolved,
        }

    @staticmethod
    def _memory_booster_ready(state, me) -> bool | None:
        """Whether the engine says the booster can be activated right now.

        `energy_full` is the engine's own answer; the charge/maximum comparison
        is the fallback for a snapshot that predates it. None means "memory does
        not know", which leaves the screen detection in charge.
        """
        me = me or {}
        rules = ((state or {}).get("rules")) or {}
        if rules.get("ability_locked"):
            return False
        ready = me.get("energy_full")
        if ready is not None:
            return bool(ready)
        charge, maximum = me.get("energy"), me.get("energy_to_ability")
        if charge is None or not maximum:
            return None
        return int(charge) >= int(maximum)

    # SpecialAbilityType.MixyMeow. Mixy's colour code only exists while that
    # booster is played, and memory says which booster it is.
    ABILITY_MIXY_MEOW = 59
    # Phase 0 is the converted-board move right after activation, phase 1 the
    # charging stretch that follows -- and the dealt code stays live through
    # both (see _memory_mixy_state). Any other value is a game update.
    MIXY_CODE_PHASES = (0, 1)

    def _memory_mixy_state(self, me):
        """Mixy state straight from the engine, never from the suitcase.

        Two failure modes forced this to memory. Non-Mixy: on 2026-08-17
        02:00-02:03 the screen reader saw "3 Mixy color tokens" at 0.98
        confidence during a Froggy Fu (ability 63) game, so every simulation
        began by repainting 18 tiles. Real Mixy: the suitcase is only drawn a
        few seconds at a time, so the screen path saw the code on roughly one
        scan in four and leaned on a 90s latch.

        ``MixyMeow.activeColors`` is the currently dealt code, and the code
        stays live through BOTH phases. Phase 0 covers the converted-board
        move immediately after activation; phase 1 is the charging stretch --
        but the 2026-08-26 00:35-00:45 snapshot timeline shows phase-1
        matches of a code colour flipping ``didRandomizeAfterMatch``,
        re-dealing ``activeColors`` and refunding the spent move (the
        ``moves`` counter bounced 5->6 at 00:36:46 as the code went 2;6 ->
        7;6), which is also what the player sees: the suitcase stays on the
        "Your Turn" bar at 5/7 charge and a code match still grants the extra
        move. The refund is NOT unconditional, though: the re-deal does not
        always follow a phase-1 match, and a colour matched again while the
        same code is still dealt gives nothing back (06:39:59 the same day:
        colour 5 repeated on the un-redealt [2,7] code -- no conversion, no
        refund, turn spent). ``spent_colors`` carries exactly those dead
        colours to the ranking. The earlier
        phase gate (only phase 0 active, added 2026-08-24 after seeing codes
        populated at 3/7 and 7/7) misread those live codes as stale lists and
        made the Extra move action answer "none" while a purple/orange code
        match was sitting on the board (2026-08-26 00:36:37-42). Unknown
        phases still mean an engine update and stay inactive.

        None (screen fallback) only when memory cannot say: an agent build
        from before the enum-list support dumps the field as a "<List...>"
        marker instead of numbers.
        """
        me = me or {}
        ability = me.get("special_ability_type")
        if ability is None or int(ability) != self.ABILITY_MIXY_MEOW:
            return MixyMeowState(
                active=False,
                code_colors=(),
                confidence=1.0,
                source="memory",
                reason=f"booster nije Mixy Meow (specialAbilityType={ability})",
            )
        fields = me.get("special_ability_fields")
        if not isinstance(fields, dict):
            return None  # agent bez ability polja: ekran ostaje nadlezan
        raw_phase = fields.get("<Phase>k__BackingField")
        try:
            phase = int(raw_phase)
        except (TypeError, ValueError):
            # Do not revive the old false positive when an older agent has the
            # colour list but not Mixy's phase. Let the screen fallback decide.
            return None
        raw = fields.get("activeColors")
        if raw is None:
            # The engine has not dealt a code yet (pre-activation frames read
            # exactly this), which is a real answer, not a missing one.
            return MixyMeowState(
                active=False,
                code_colors=(),
                confidence=1.0,
                source="memory",
                reason="Mixy kod jos nije dodeljen (activeColors je prazan)",
            )
        if not isinstance(raw, list):
            return None  # stari agent: "<List...>" marker, ekran odlucuje
        code_colors = []
        for value in raw:
            color = board_source.slot_color_to_board(value)
            if color is None or color == EMPTY:
                return None  # nepoznata SlotColor vrednost: ne pogadjaj
            code_colors.append(int(color))
        if phase not in self.MIXY_CODE_PHASES:
            return MixyMeowState(
                active=False,
                code_colors=(),
                confidence=1.0,
                source="memory",
                reason=f"Mixy kod postoji, ali faza je nepoznata (Phase={phase})",
            )
        # Colours already matched on this exact dealt code are dead until the
        # code re-deals; hand them to the ranking so it stops promising the
        # refund/conversion for a repeat (see _track_mixy_code_spend).
        spent_colors = []
        if tuple(raw) == self._mixy_spent_code:
            for value in self._mixy_spent_colors:
                spent = board_source.slot_color_to_board(value)
                if spent is not None and spent != EMPTY:
                    spent_colors.append(int(spent))
        engine_uses_left = self._mixy_engine_uses_left(me)
        state = MixyMeowState(
            active=bool(code_colors),
            code_colors=tuple(code_colors),
            spent_colors=tuple(spent_colors),
            uses_this_activation=self._mixy_uses_this_activation,
            max_uses=self._mixy_max_uses,
            engine_uses_left=engine_uses_left,
            confidence=1.0,
            source="memory",
            reason=(
                "kod iz MixyMeow.activeColors"
                if engine_uses_left is None
                else f"kod iz MixyMeow.activeColors, engine UsesLeft={engine_uses_left}"
            ),
        )
        if code_colors and tuple(code_colors) != self._mixy_code_reported:
            self._mixy_code_reported = tuple(code_colors)
            self._log(f"Mixy code from memory: {code_colors}")
        return state

    def _track_mixy_code_spend(self, me, state=None) -> None:
        """Watch which colour of the dealt Mixy code was already matched.

        The engine flags a code match with a short-lived transient in the
        ability fields: ``SourceColors`` holds the colours being repainted and
        ``TargetColor`` the matched code colour (idle frames read ``[]``/1).
        The 06:39 game on 2026-08-26 showed why this matters: the code stayed
        [2,7] after colour 2 was matched (no re-deal followed a phase-1
        match), the bot replayed colour 2 six seconds later as a promised
        extra, and the game gave nothing back -- no conversion, no refund.
        A colour is spent for as long as that exact ``activeColors`` list
        stays dealt; any re-deal clears the set.

        That set is now only half the answer: it says which colour of a live
        code is dead, while ``_track_mixy_activation_uses`` (driven from here
        on the same frame) says whether the code is live at all.
        """
        me = me or {}
        ability = me.get("special_ability_type")
        fields = me.get("special_ability_fields")
        if (
            ability is None
            or int(ability) != self.ABILITY_MIXY_MEOW
            or not isinstance(fields, dict)
        ):
            self._mixy_spent_code = None
            self._mixy_spent_colors.clear()
            self._mixy_spend_armed = True
            self._mixy_uses_this_activation = 0
            self._mixy_max_uses = 0
            self._mixy_prev_phase = None
            self._mixy_prev_energy = None
            self._mixy_transient_live = False
            self._mixy_prev_code = None
            self._mixy_last_use_at = 0.0
            self._mixy_activated_at = 0.0
            self._mixy_activation_count = 0
            self._mixy_turn_key = None
            return
        # `Use` indexes the per-activation lists by the activations *this
        # turn* (SpecialAbility.ActivatesThisTurn, read right before
        # set_UsesLeft in the decompiled Use), so the count restarts with the
        # turn. Party/Solo have one turn per match; versus has several.
        state = state if isinstance(state, dict) else {}
        turn_key = (state.get("turns"), state.get("current_round"))
        if turn_key != self._mixy_turn_key:
            self._mixy_turn_key = turn_key
            self._mixy_activation_count = 0
        raw = fields.get("activeColors")
        code = tuple(raw) if isinstance(raw, list) else None
        source = fields.get("SourceColors")
        transient_live = isinstance(source, list) and bool(source)
        self._track_mixy_activation_uses(me, fields, transient_live, code)
        self._sync_mixy_uses_from_engine(me, code)
        if code != self._mixy_spent_code:
            self._mixy_spent_code = code
            self._mixy_spent_colors.clear()
            # The engine re-deals ``activeColors`` BEFORE clearing the match
            # transient (2026-08-27 18:57:09.434 UTC frame: new code [7,6,3]
            # still carrying SourceColors=[6,2]/TargetColor=3 from the old
            # [6,2,3] code), and that stale transient stays readable for
            # SEVERAL reads after the re-deal (21:25:48 the same day: the
            # skip-one-frame version re-recorded spent=3 on fresh code
            # (2,3,6) one read later and the whole code went dead unplayed).
            # The leftover target belongs to the previous code, so the spend
            # tracker disarms here and stays disarmed until the transient is
            # seen cleared once -- only a transient that appears after that
            # belongs to the current code.
            self._mixy_spend_armed = False
            return
        if not self._mixy_spend_armed:
            if not transient_live:
                self._mixy_spend_armed = True
            return
        target = fields.get("TargetColor")
        if (
            code
            and transient_live
            and isinstance(target, int)
            and target in code
            and target not in self._mixy_spent_colors
        ):
            self._mixy_spent_colors.add(target)
            board_color = board_source.slot_color_to_board(target)
            self._log(
                f"Mixy: boja {board_color if board_color is not None else target} "
                "iz koda je pogodjena — ponovni pogodak ne vraca potez dok se "
                "kod ne promeni"
            )

    # Fallback when the engine does not expose the cap in the ability fields.
    # Every build measured so far reports 2, paired with a
    # `colorsToPickByActivation` of "3,2" -- a three-colour code for use #1 and
    # a two-colour code for use #2.
    MIXY_DEFAULT_MAX_USES = 2

    @staticmethod
    def _mixy_engine_uses_left(me) -> int | None:
        """``MixyMeow.UsesLeft`` as the agent read it on this snapshot, or None.

        Present only on manual dumps from an agent build that runs the getter
        (``special_ability_engine``); a plain poll or an older agent leaves it
        out, and then the inferred counter stands.
        """
        engine = (me or {}).get("special_ability_engine")
        if not isinstance(engine, dict):
            return None
        raw = engine.get("uses_left")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return int(raw)

    def _sync_mixy_uses_from_engine(self, me, code) -> None:
        """Let the engine's own ``UsesLeft`` overrule the inferred use count.

        ``MixyMeow::Use`` writes ``UsesLeft`` on every activation and
        ``FoundTargetColor`` takes one off per credited match (libil2cpp.so,
        decoded 2026-09-13), so with a dealt code on the board
        ``max_uses - UsesLeft`` is exactly what the transient counting tries to
        reconstruct. Without a dealt code the key may simply not exist yet
        (the getter returns 0 for a missing key too), so nothing is concluded.
        """
        uses_left = self._mixy_engine_uses_left(me)
        if uses_left is None or not code:
            return
        cap = self._mixy_max_uses or self.MIXY_DEFAULT_MAX_USES
        engine_uses = max(0, min(cap, cap - uses_left))
        if engine_uses != self._mixy_uses_this_activation:
            self._log(
                f"Mixy: engine kaze UsesLeft={uses_left} — brojac upotreba "
                f"{self._mixy_uses_this_activation} -> {engine_uses}"
            )
            self._mixy_uses_this_activation = engine_uses

    def _mixy_max_uses_from(self, me, fields) -> int:
        """The code-use cap for the *current* activation, 0 never (2 fallback).

        `maxUsesByActivation` is a list indexed by the activation number this
        turn, clamped to its last entry -- the same way the engine sizes the
        code from `colorsToPickByActivation` ("3,2": three colours on the first
        activation, two after). Every arena measured up to 2026-09-12 carried a
        single entry (2), so the first entry was the whole answer; the Party
        Color Climb arena (2026-09-13 03:13-03:15) carries [2, 1]: two uses on
        the first activation, ONE on every later one. Reading entry 0 there
        promised a second code match that the engine never credits, and the
        03:14:02 code move spent the last move on it (board changed 3 cells,
        no transient, no refund).

        The list arrives in the ability fields and as a comma string in
        `special_ability_params`; either is authoritative, and a build that
        stops reporting it falls back to the measured 2 rather than to
        "unlimited".
        """
        raw = fields.get("maxUsesByActivation")
        caps: list[int] = []
        if isinstance(raw, list):
            for value in raw:
                try:
                    caps.append(int(value))
                except (TypeError, ValueError):
                    continue
        if not caps:
            params = me.get("special_ability_params")
            text = params.get("maxUsesByActivation") if isinstance(params, dict) else None
            if isinstance(text, str):
                for part in text.split(","):
                    try:
                        caps.append(int(part.strip()))
                    except ValueError:
                        continue
        if not caps:
            return self.MIXY_DEFAULT_MAX_USES
        # Activation #1 reads entry 0; with no activation seen yet (attached
        # mid-match) the first entry stands, which is the optimistic reading
        # and the same one the old code always used.
        index = min(max(0, self._mixy_activation_count - 1), len(caps) - 1)
        cap = caps[index]
        return cap if cap > 0 else self.MIXY_DEFAULT_MAX_USES

    # A re-deal this soon after an activation is the activation's own fresh
    # code (measured ~2 s after the meter empties), not a spent use.
    MIXY_REDEAL_AFTER_ACTIVATION_SECONDS = 8.0
    # A re-deal this soon after a counted transient edge belongs to that same
    # use. Measured 2026-09-13 (02:40-02:43 local): the transient appears,
    # the refund lands 1.5-2 s later and the re-deal follows 1.5-5 s after
    # the transient (00:41:16.3 -> 00:41:21.3 UTC was the slowest). Use #2
    # never re-deals and use #1 is the first use after an activation, so a
    # generous window costs nothing: the only re-deal it can hide is the one
    # that belongs to the edge already counted.
    MIXY_REDEAL_SAME_USE_SECONDS = 15.0

    def _track_mixy_activation_uses(self, me, fields, transient_live, code=None) -> None:
        """Count the code matches this booster activation has already spent.

        `maxUsesByActivation` (2 everywhere it has been read) is the real end
        of a code, and it survives the re-deal: the engine deals a fresh
        `activeColors` after use #1 and leaves the list standing after use #2,
        so "the code changed" says nothing about whether it can still be
        cashed. Measured over the 2026-08-25 21:00 - 2026-08-28 05:00
        snapshots: 105 activations, use #1 re-dealt 82 times of 94, use #2 did
        not re-deal 68 times of 78, and no activation ever reached a use #3.

        A use is counted on the RISING edge of the match transient. That edge
        is immune to the stale transient the engine carries across a re-deal
        (it re-deals `activeColors` before clearing SourceColors, so the
        transient never goes false and back true in between). A missed edge
        used to under-count, which is exactly the phantom the user asked to
        rule out (2026-09-13): the drawn code looks live one use longer than
        it is. So a re-deal is a second, independent signal of a use: the
        engine only re-deals `activeColors` on activation and on a credited
        code match (`FoundTargetColor` -> `RandomizeActiveColors`), so a code
        that changes outside the activation window, with no transient edge
        counted in the last few seconds, is a use whose transient the poll
        missed. Use #2 never re-deals, so its missed edge is still not
        recoverable here; the runtime's refund watch covers that case by
        declaring a code dead after one proven broken refund.

        The engine's own counter (`MixyMeow.UsesLeft`, kept as a string in
        `BoardModel.extraData`) would settle all of this per poll, but the
        agent's extraData read comes back empty on the played board -- the
        same gap the jelly zone hit -- so until the agent is fixed this stays
        an inference.

        The activation itself is spotted two ways, because either reading can
        be missed between snapshots: Mixy's own phase falling back to 0, and
        the charge meter emptying.
        """
        now = time.monotonic()
        try:
            phase = int(fields.get("<Phase>k__BackingField"))
        except (TypeError, ValueError):
            phase = None
        try:
            energy = int(me.get("energy"))
        except (TypeError, ValueError):
            energy = None
        activated = (
            phase == 0
            and self._mixy_prev_phase is not None
            and self._mixy_prev_phase != 0
        ) or (
            energy == 0
            and self._mixy_prev_energy is not None
            and self._mixy_prev_energy > 0
        )
        if activated and self._mixy_uses_this_activation:
            self._log(
                "Mixy: buster aktiviran — brojac upotreba koda resetovan "
                f"(bilo {self._mixy_uses_this_activation})"
            )
        if activated:
            self._mixy_uses_this_activation = 0
            self._mixy_activated_at = now
            self._mixy_activation_count += 1
        # The cap depends on which activation this is, so it is read after
        # the activation edge above has been counted.
        previous_cap = self._mixy_max_uses
        self._mixy_max_uses = self._mixy_max_uses_from(me, fields)
        if activated and self._mixy_max_uses != previous_cap and previous_cap:
            self._log(
                f"Mixy: aktivacija #{self._mixy_activation_count} ove ture — "
                f"kod ima {self._mixy_max_uses} upotrebu/e (bilo {previous_cap})"
            )
        counted_use = False
        if transient_live and not self._mixy_transient_live:
            counted_use = True
        elif (
            code is not None
            and self._mixy_prev_code is not None
            and code != self._mixy_prev_code
            and not activated
            and now - self._mixy_activated_at > self.MIXY_REDEAL_AFTER_ACTIVATION_SECONDS
            and now - self._mixy_last_use_at > self.MIXY_REDEAL_SAME_USE_SECONDS
        ):
            counted_use = True
            self._log(
                "Mixy: code changed without a seen hit "
                f"({list(self._mixy_prev_code)} -> {list(code)}) — counting as a use"
            )
        if counted_use:
            self._mixy_uses_this_activation += 1
            self._mixy_last_use_at = now
            if (
                self._mixy_max_uses
                and self._mixy_uses_this_activation >= self._mixy_max_uses
            ):
                self._log(
                    "Mixy: potrosene sve upotrebe koda za ovu aktivaciju "
                    f"({self._mixy_uses_this_activation}/{self._mixy_max_uses}) "
                    "— kod je ispisan ali mrtav do sledece aktivacije"
                )
        self._mixy_transient_live = bool(transient_live)
        self._mixy_prev_code = code
        if phase is not None:
            self._mixy_prev_phase = phase
        if energy is not None:
            self._mixy_prev_energy = energy

    def _track_ufo_eyes(self, state, me) -> None:
        """Keep the UFO ledger current and say in the log when eyes are armed."""
        tracker = self._ufo_tracker
        before = tracker.eyes
        tracker.observe(state, me or {})
        self.UfoEyesLabel.setText(self._ufo_eyes_status(tracker, me))
        if tracker.eyes == before:
            return
        # Both directions are worth a line: the log then shows when eyes were
        # armed and when they went, next to the moves they fired on.
        self._log(f"UFO: {tracker.reason}")

    @staticmethod
    def _ufo_eyes_status(tracker, me) -> str:
        """The state-panel line: armed eyes now, and where the number came from.

        "iz igre" while the count is still the one the engine's getters gave on
        the last manual dump; once the ledger changed it on its own (an
        activation, a fire) it reads "procena" until the next dump confirms, so
        a wrong guess is visible instead of looking like a reading.
        """
        if not tracker.booster_is_ufo(me):
            return "-"
        source = "iz igre" if tracker.eyes_from_engine else "procena"
        return f"{tracker.eyes} naoruzano  ({source})"

    def _memory_ufo_state(self, me):
        """The armed eyes, counted from the engine instead of the rail strip.

        The screen count is not consulted at all any more: over the 2026-08-17
        15:21-15:53 session it disagreed with the engine on all 12 logged UFO
        moves (four false 1-eye reads at 0.82-0.98 confidence, eight missed
        abductions), and the 15:53:32 false positive wiped every orange tile in
        simulation and counted a fantasy match-4 as an extra move.
        """
        return self._ufo_tracker.state(me or {})

    @staticmethod
    def _board_has_mushroom(snapshot):
        return any(
            int(value) == SPECIAL_MUSHROOM
            for row in (snapshot.get("special_board") or [])
            for value in row
        )

    def _logged_ability_used(self, me, snapshot) -> bool:
        """_ability_used_this_move, written to the log in the modes it changes.

        move.json does not carry the flag, and on 2026-09-18 two Floor Is Lava
        moves right after a booster (22:13:02, 22:14:13) were planned with
        eruptions the engine then skipped -- with no record of what the planner
        had been told. One line per planned move, only where it matters.
        """
        used = self._ability_used_this_move(me)
        if self._effective_mode(snapshot.get("state")) in (
            GameMode.FLOOR_IS_LAVA, GameMode.VERTICAL_RUSH,
        ):
            self._log(
                "Buster/perk u ovom potezu: "
                + ("DA — mod ne vazi za ovaj potez" if used else "ne")
                + f"  (energija {(me or {}).get('energy')})"
            )
        return used

    @staticmethod
    def _ability_used_this_move(me) -> bool:
        """Whether this move already spent an ability, as the engine sees it.

        Nine board models -- Floor Is Lava and Vertical Rush among the ones the
        bot plays -- open their hook with exactly these two checks and return
        without applying the mode's rule (docs/game_mode_logic_from_code.md).
        The booster (special ability) always counts; a perk counts only when it
        is one of the two that cost no move, which is what
        `PlayerControl.NoFreeMoveBoardAbilityUsedThisMove` resolves to.

        An older snapshot without the fields reads as False, i.e. unchanged
        behaviour rather than a guess.
        """
        me = me or {}
        if bool(me.get("is_ability_used_this_move")):
            return True
        if not me.get("is_board_ability_used_this_move"):
            return False
        used = me.get("board_ability_used_this_move")
        if used is None:
            return False
        return int(used) in FREE_MOVE_BOARD_ABILITIES

    @staticmethod
    def _energized_colors(me):
        raw = (me or {}).get("energy_colors") or []
        colors = []
        for value in raw:
            color = board_source.slot_color_to_board(value)
            if color is not None and color != BLUE and color not in colors:
                colors.append(color)
        return normalize_energized_colors(colors)

    @classmethod
    def _charge_colors(cls, me, rules, mutation_colors=None):
        """Non-blue colours that fill the booster meter this match.

        PlayerControl.energyColors is the engine's own list; bothColorsChargeEnergy
        is added on top because the rule is stated on the match, not the player,
        and the game describes it as red joining blue. A Mutation Lab
        ColorChargesEnergy pick is a third source saying the same thing.
        """
        colors = list(cls._energized_colors(me))
        if (rules or {}).get("both_colors_charge_energy") and RED not in colors:
            colors.append(RED)
        for color in mutation_colors or ():
            if color not in colors:
                colors.append(color)
        return normalize_energized_colors(colors)

    @staticmethod
    def _charge_scale(me, snapshot) -> dict:
        """booster_charge / booster_maximum / engine_charge_weights for the request.

        With per-colour charge in the engine table (Color Crystals 2026-11-12:
        green 1, orange 2, purple 3, yellow 4 into a 70-point meter) the meter
        and the weights go on the BOOSTER_MAX_CHARGE scale together, so a full
        meter is still 7 and the charge stays priced against points as in
        every other mode. Without it (all ones), nothing changes.
        """
        charge = me.get("energy")
        maximum = me.get("energy_to_ability") or BOOSTER_MAX_CHARGE
        out = {"booster_charge": charge, "booster_maximum": maximum}
        weights = board_source.charging_weights(snapshot)
        if not weights or all(value == 1 for value in weights.values()):
            return out
        try:
            scale = BOOSTER_MAX_CHARGE / float(maximum)
        except (TypeError, ValueError, ZeroDivisionError):
            return out
        out["booster_maximum"] = BOOSTER_MAX_CHARGE
        out["booster_charge"] = None if charge is None else float(charge) * scale
        out["engine_charge_weights"] = {color: value * scale for color, value in weights.items()}
        return out

    @staticmethod
    def _engine_charge_colors(me, snapshot):
        """The engine's *complete* charge table, or None when it cannot say.

        Two sources, both straight from the engine. MatchRulesModel's
        colorComboEnergy/_colorEnergyOverride when the agent dumps them, else
        PlayerControl.energyColors. A non-empty energyColors is a full
        replacement, not extras on top of blue: across all 183 recorded
        Energized snapshots (2026-08-24) the list holds exactly the mode's two
        colors and never blue, and live play confirms blue does not fill the
        booster there -- while every other recorded mode reports []. None keeps
        the blue-charges default.
        """
        colors = board_source.charging_colors(snapshot)
        if colors:
            return colors
        listed = []
        for value in (me or {}).get("energy_colors") or ():
            color = board_source.slot_color_to_board(value)
            if color not in (None, EMPTY) and color not in listed:
                listed.append(color)
        return tuple(sorted(listed)) or None

    @staticmethod
    def _score_legend_from_snapshot(snapshot):
        """Per-colour point values, straight out of SlotModel.score.

        This is the same legend the main GUI reads off the screen with learned
        templates. Only plain tiles vote, because specials and lotus-boosted
        cells carry summed values, and only colours with a clear majority are
        reported. Blue and red are left out on purpose: the main GUI's legend
        covers exactly these four colours.
        """
        board = snapshot.get("board") or []
        votes = {}
        for slot in snapshot.get("slots") or []:
            if int(slot.get("value", 0)) != 0:  # Normal tiles only
                continue
            try:
                color = int(board[int(slot["y"])][int(slot["x"])])
                score = int(slot["score"])
            except (IndexError, KeyError, TypeError, ValueError):
                continue
            if color not in (GREEN, YELLOW, PURPLE, ORANGE):
                continue
            votes.setdefault(color, {}).setdefault(score, 0)
            votes[color][score] += 1

        legend = {}
        for color, counted in votes.items():
            score, count = max(counted.items(), key=lambda item: item[1])
            if count >= 2:
                legend[color] = float(score)
        return legend or None

    def _refresh_score_legend(self, snapshot):
        legend = self._score_legend_from_snapshot(snapshot)
        self._score_legend = legend
        if legend is None:
            self.LegendLabel.setText("-")
            return
        names = COLOR_NAMES
        self.LegendLabel.setText(
            "  ".join(
                f"{names[color]} {int(value)}"
                for color, value in sorted(legend.items())
                if color in names
            )
        )

    def _refresh_perks(self, me):
        """Show the perks the engine says we brought, in list order.

        BoardAbilities order is taken as slot order (first entry = slot 1),
        which is what the click coordinates assume. Before anything is pressed
        that assumption is verified against the on-screen slot strip, see
        ``_selected_perks_for_request``.
        """
        abilities = (me or {}).get("board_abilities")
        if not abilities:
            self._perk_keys = ()
            self._perk_types = ()
            self.PerksLabel.setText("-")
            return
        names = []
        keys = []
        types = []
        for ability in abilities:
            raw_type = ability.get("type")
            names.append(
                ability.get("name")
                or BOARD_ABILITY_NAMES.get(
                    raw_type if raw_type is None else int(raw_type), f"#{raw_type}"
                )
            )
            key = PERK_LABEL_TO_KEY.get(_normalized_label(ability.get("name")))
            if key is None:
                key = BOARD_ABILITY_TO_PERK.get(
                    int(raw_type) if raw_type is not None else -1
                )
            keys.append(key)
            types.append(None if raw_type is None else int(raw_type))
        self._perk_keys = tuple(keys)
        self._perk_types = tuple(types)
        self._note_used_board_ability(me)
        labels = [
            f"{name} (iskoriscen)"
            if slot_number in self._used_perk_slots
            else (name if key else f"{name} (nemapiran)")
            for slot_number, (name, key) in enumerate(zip(names, keys), start=1)
        ]
        self.PerksLabel.setText(", ".join(labels))

    def _note_used_board_ability(self, me):
        """Mark a perk spent the moment the engine says it was spent.

        The executor only clears the slot when it can read "used" off the
        on-screen slot strip, and for Energy Boost that read never comes: the
        perk stays visually available while it is armed. Debug run
        2026-08-21 17-06-38 has the swipe landing (`board_changed` on all eight
        verify attempts) with `perk_used` never true, so the executor reported
        `effect_not_confirmed`, the slot was never cleared, and the bot went on
        offering an Energy Boost it no longer had for two more moves.

        `PlayerModel` says it outright, and the agent already carries both
        fields, so the screen does not have to be right about this.
        """
        me = me or {}
        if not me.get("is_board_ability_used_this_move"):
            return
        used = me.get("board_ability_used_this_move")
        if used is None:
            return
        for index, ability_type in enumerate(self._perk_types):
            slot_number = index + 1
            if ability_type == int(used) and slot_number not in self._used_perk_slots:
                self._used_perk_slots.add(slot_number)
                self._used_perk_slot_sources[slot_number] = "engine"
                pending = self._perk_pending_confirmation
                if pending is not None and pending[0] == slot_number:
                    self._perk_pending_confirmation = None
                else:
                    # Not the bot's own perk (played by hand): the refill check
                    # must see it, or the perk and the next swipe read as one
                    # wrong move (Color Climb 2026-11-12 01:28:53, Mini Cleo by
                    # hand, 01:28:58 "PROMASAJ").
                    keys = getattr(self, "_perk_keys", ()) or ()
                    self._note_refill_input("activate_perk", {
                        "action": "activate_perk", "manual": True,
                        "perk": keys[index] if index < len(keys) else None})
                self._log(
                    f"Perk u slotu {slot_number} je iskoriscen (iz memorije)."
                )
                break

    def _party_perk_slots(self, rules) -> bool:
        """Party renders the slot strip wider, so detection needs to know."""
        return (rules or {}).get("rumble_type") == RUMBLE_TYPE_PARTY

    def _selected_perks_for_request(self, rules, board_profile):
        """The (slot1, slot2) perk tuple the runtime may spend this move.

        Slots are fixed for the whole match, so the memory list is the
        authority on which perk sits where -- a template misread must not veto
        a perk. The on-screen strip is read for the one thing memory does not
        carry: whether a slot is already spent. That read costs a screenshot,
        so it happens once per match; afterwards a spent slot is known from the
        perk the bot itself played.
        """
        empty = (runtime.PERK_NONE, runtime.PERK_NONE)
        if not self.PerksCheck.isChecked():
            return empty
        keys = [
            key if index + 1 not in self._used_perk_slots else None
            for index, key in enumerate(self._perk_keys[:2])
        ]
        keys += [None] * (2 - len(keys))
        if not any(keys):
            return empty

        # No screen read (removed 2026-09-18, memory only): a slot is spent
        # when the engine says so (_note_used_board_ability) or when the bot
        # played it. Known gap: a perk spent *before* this GUI attached to a
        # running match is not visible -- PlayerModel's board_abilities list
        # does not shrink and the agent does not read a per-perk "used" yet.
        if self._perk_confirmation_pending():
            return empty
        return tuple(key or runtime.PERK_NONE for key in keys)

    def _perk_confirmation_pending(self) -> bool:
        pending = self._perk_pending_confirmation
        if pending is None:
            return False
        if pending[1] != self._turn_clock_key:
            # A new turn: whatever the click did, it is settled now and the
            # slot's state comes from memory again.
            self._perk_pending_confirmation = None
            return False
        return True

    def _perk_slot_status(self, *, low_on_time=False, burning_moves=False):
        """Per-slot perk view from memory, independent of selected_perks.

        Goes into the request so the runtime can say why a slot it received
        as PERK_NONE was not offered, and so the final-handover audit counts
        only perks memory confirms as equipped and unspent.
        """
        status = []
        pending = self._perk_pending_confirmation
        for index, key in enumerate(self._perk_keys[:2]):
            slot_number = index + 1
            available = bool(key) and slot_number not in self._used_perk_slots
            if not key:
                reason = "unmapped"
            elif slot_number in self._used_perk_slots:
                reason = f"used_{self._used_perk_slot_sources.get(slot_number, 'bot')}"
            elif not self.PerksCheck.isChecked():
                reason = "perks_disabled"
            elif burning_moves:
                reason = "burning_moves"
            elif low_on_time:
                reason = f"low_turn_time<={LOW_TURN_TIME_SECONDS:.0f}s"
            elif pending is not None and pending[1] == self._turn_clock_key:
                reason = f"pending_confirmation_slot_{pending[0]}"
            else:
                reason = "available"
            status.append({
                "slot": slot_number,
                "perk": key,
                "available": available,
                "source": "memory",
                "reason": reason,
            })
        return tuple(status)

    def _refresh_booster_from_memory(self, me):
        if not me:
            return
        ability = me.get("special_ability_type")
        if ability is None:
            self.BoosterNameLabel.setText("-")
            return
        engine_name = me.get("special_ability_name")
        name = engine_name or SPECIAL_ABILITY_NAMES.get(int(ability), f"#{ability}")
        # Name first (the live model carries the in-game name), engine type as
        # the fallback for boosters whose model name is missing.
        action = BOOSTER_LABEL_TO_ACTION.get(_normalized_label(engine_name))
        if action is None:
            action = ABILITY_TO_BOOSTER_ACTION.get(int(ability))
        previous = self._booster_action
        self._booster_action = action or BOOSTER_ACTION_NONE
        if action is None:
            # No targeting policy for this booster: activate it without aiming,
            # rather than aiming it with another booster's logic.
            self.BoosterNameLabel.setText(f"game: {name} (no targeting)")
        else:
            self.BoosterNameLabel.setText(f"game: {name} -> {action}")
        if self._booster_action != previous:
            self._log(f"Booster from memory: {name} -> {self._booster_action}")

    @staticmethod
    def _current_player(state, players):
        """Us -- not whoever happens to be on turn.

        PlayerClientControl.Type marks the local side. Falling back to the
        player on turn would hand the opponent's score, booster meter and
        charging colour to the strategy on their half of a versus match.
        """
        for player in players:
            if player.get("player_type") == PLAYER_TYPE_LOCAL:
                return player
        index = state.get("current_player_index")
        for player in players:
            if player.get("index") == index:
                return player
        return players[0] if players else None

    @staticmethod
    def _contract_round(state):
        """The engine's round index, converted to the runtime's 1-based one.

        ``GameLogic.CurrentRound`` is 0-BASED: the first played round reads 0,
        and ``current_round + rounds == rounds_total`` holds in every recorded
        frame (5571 versus frames, rounds_total 2-5, 2026-08-24 - 2026-08-28).
        The value only reaches ``rounds_total`` on the handful of terminal
        post-match frames.

        ``MoveRequest.current_round`` and ``compute_is_final_round`` are
        documented 1-based, and that mismatch made ``is_final_round`` False for
        every playable frame of every versus match: the final-round points-only
        switch, the "no opponent turn follows" handover rules and the
        last-chance perk window were all dead, while
        ``compute_moves_left_in_match`` added a phantom round's worth of moves
        to the charge horizon on the very round where charge cannot carry over.
        """
        raw = (state or {}).get("current_round")
        try:
            return int(raw) + 1
        except (TypeError, ValueError):
            return None

    @classmethod
    def _opponent_score(cls, state, players):
        me = cls._current_player(state, players)
        my_index = (me or {}).get("index")
        for player in players:
            if player.get("index") != my_index:
                return player.get("score")
        return None

    # --------------------------------------------------- unmapped modes ---

    @staticmethod
    def _rule_flags_on(rules) -> list[str]:
        """Every MatchRulesModel flag this match has turned on.

        Both halves of the snapshot are read: the named fields the bot's code
        uses, and `engine_fields`, which is the agent's sweep of *every*
        instance field on MatchRulesModel. The sweep is what makes this answer
        complete -- a rule nobody thought to name still shows up here. The two
        halves overlap (`specials_auto_explode` / `specialsAutoExplode`), so
        names are deduplicated on their letters and the readable one wins.
        """
        rules = rules or {}
        engine_fields = rules.get("engine_fields")
        engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
        by_key: dict[str, str] = {}
        # Named fields first so their spelling is the one that survives.
        for source in (rules, engine_fields):
            for name, value in source.items():
                if value is not True or name in RULE_FLAGS_NOT_WORTH_REPORTING:
                    continue
                key = re.sub(r"[^a-z0-9]+", "", str(name).lower())
                by_key.setdefault(key, str(name))
        for names in RULE_FLAGS_NOTABLE_WHEN_OFF:
            values = [
                source.get(name)
                for name in names
                for source in (rules, engine_fields)
                if source.get(name) is not None
            ]
            if values and not any(values):
                by_key[f"off:{names[0]}"] = f"!{names[-1]}"
        return sorted(by_key.values())

    def _lookahead_for_state(self, state) -> tuple[tuple[int, int, int], str]:
        """(candidates, depth, beam) for this match, and what to call the match.

        Infinite Moves stays light even on a Solo Challenge board: no move is
        ever spent, so the bot plays many more of them.
        """
        rules = state.get("rules") or {}
        if self._unlimited_moves(rules):
            return FAST_LOOKAHEAD_PARAMS, "Infinite Moves"
        if self._is_solo_challenge(state):
            return SOLO_LOOKAHEAD_PARAMS, "Solo Challenge"
        if self._strategy_mode(rules, state.get("players") or []) == STRATEGY_VERSUS_2:
            return VERSUS_LOOKAHEAD_PARAMS, "Versus"
        return FAST_LOOKAHEAD_PARAMS, "trka na vreme"

    def _update_lookahead_label(self, state) -> None:
        params, match_kind = self._lookahead_for_state(state)
        text = f"Lookahead: {'/'.join(map(str, params))} ({match_kind})"
        if text != getattr(self, "_lookahead_logged", None):
            self._lookahead_logged = text
            self._log(text)
        self.LookaheadLabel.setText(text)
        self.LookaheadLabel.show()

    def _hide_lookahead_label(self) -> None:
        self._lookahead_logged = None
        self.LookaheadLabel.hide()

    # A per-turn clock at or above this is "all the time in the world" --
    # solo challenges run 1500s, while raced modes (Showdown, Master League)
    # run ~30-90s. Anything in between is unheard of, so the exact value is
    # uncritical.
    DEEP_LOOKAHEAD_MIN_TIME_PER_TURN = 300.0

    @classmethod
    def _relaxed_turn_clock(cls, rules) -> bool:
        """Whether the match's per-turn clock leaves room to think ~1s a move.

        No timer at all is a yes. A timer with an unknown budget is a no --
        assuming pressure costs a little depth, assuming leisure costs the
        match.
        """
        rules = rules or {}
        engine_fields = rules.get("engine_fields")
        engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
        is_timer = rules.get("is_timer")
        if is_timer is None:
            is_timer = engine_fields.get("isTimer")
        if not is_timer:
            return True
        time_per_turn = engine_fields.get("timePerTurn")
        try:
            return float(time_per_turn) >= cls.DEEP_LOOKAHEAD_MIN_TIME_PER_TURN
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _unlimited_moves(rules) -> bool:
        """Infinite Moves ruleset: a valid swap does not spend a move.

        The engine states it as reduceMoveOnValidSwap=false (see
        RULE_FLAGS_NOTABLE_WHEN_OFF); absent evidence means the normal
        one-swap-one-move game.
        """
        rules = rules or {}
        if free_swap.spends_moves_on_match_only(rules):
            # Swap Freely: the free swaps are the non-matching ones; a match
            # still spends a move, so this is not Infinite Moves.
            return False
        engine_fields = rules.get("engine_fields")
        engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
        for source in (rules, engine_fields):
            for name in ("reduce_move_on_valid_swap", "reduceMoveOnValidSwap"):
                value = source.get(name)
                if value is not None:
                    return not value
        return False

    @classmethod
    def _unmapped_rule_summary(cls, rules) -> str:
        """One line naming what the engine says about a ruleset."""
        rules = rules or {}
        parts = [f"board_model={rules.get('board_model_name')}"]
        flags = cls._rule_flags_on(rules)
        if flags:
            parts.append("flagovi=" + ",".join(flags))
        for key in ("moves_per_turn", "turns_per_game", "colors_count", "board_size"):
            if rules.get(key) is not None:
                parts.append(f"{key}={rules[key]}")
        # The engine's charge tables, raw and as the bot reads them, so the
        # first matches after they started arriving (2026-09-22) show whether
        # anything but blue fills the booster.
        tables = {
            key: rules[key]
            for key in ("color_combo_energy", "color_energy_override")
            if rules.get(key)
        }
        if tables:
            charge = board_source.charging_colors({"state": {"rules": rules}})
            parts.append(f"energija={tables} -> punjenje={charge}")
        return "  ".join(parts)

    def _log_ruleset_once(self, rules_id, mode, rules) -> None:
        """Say what this match actually runs, mapped or not, once per ruleset.

        The mode label alone hides the rest of the ruleset, and a mapped mode
        can still carry flags of its own (a board-model arena with
        specialsAutoExplode on, say). Logging the engine's own answer means the
        log always shows what was in force, instead of what the mode name
        suggests.
        """
        if not rules_id or str(rules_id) in self._ruleset_logged:
            return
        self._ruleset_logged.add(str(rules_id))
        self._log(
            f"Pravila '{rules_id}' -> {mode.value}: "
            f"{self._unmapped_rule_summary(rules)}"
        )

    @staticmethod
    def _safe_dir_name(rules_id) -> str:
        return re.sub(r"[^a-z0-9._-]+", "_", str(rules_id or "unknown").lower()) or "unknown"

    def _handle_unmapped_mode(self, rules_id, mode, known: bool, snapshot) -> None:
        """Warn once, then keep recording, when a match uses an unknown ruleset.

        ``known`` covers the rulesets that deliberately play as GameMode.NONE
        because the snapshot already carries everything they change; those are
        not a gap and are left alone.
        """
        if not rules_id or known or mode is not GameMode.NONE:
            return
        rules_id = str(rules_id)
        rules = ((snapshot.get("state") or {}).get("rules")) or {}

        if rules_id not in self._unmapped_warned:
            self._unmapped_warned.add(rules_id)
            summary = self._unmapped_rule_summary(rules)
            self._log(
                f"PAZNJA: mod '{rules_id}' nije mapiran — bot igra bez pravila "
                f"ovog moda. Engine javlja: {summary}"
            )
            self._log(f"Saving snapshots to {self._unmapped_dir(rules_id)}")
            self._show_unmapped_warning(rules_id, summary)

        self._save_unmapped_snapshot(rules_id, snapshot)

    def _unmapped_dir(self, rules_id) -> Path:
        return UNMAPPED_MODE_DIR / self._safe_dir_name(rules_id)

    def _show_unmapped_warning(self, rules_id: str, summary: str) -> None:
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("Unmapped mode")
        box.setText(f"Mode '{rules_id}' is not supported.")
        box.setInformativeText(
            "Bot plays as if there are no special rules, so its move evaluation "
            "may be wrong.\n\n"
            f"Engine reports: {summary}\n\n"
            f"Snapshots are saved to:\n{self._unmapped_dir(rules_id)}"
        )
        # Non-modal on purpose: auto-play must keep running behind it.
        box.setModal(False)
        box.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self._unmapped_box = box
        box.show()

    def _save_unmapped_snapshot(self, rules_id: str, snapshot) -> None:
        saved = self._unmapped_saved.get(rules_id, 0)
        if saved >= UNMAPPED_MODE_MAX_SNAPSHOTS:
            return
        # One file per distinct board state; the reader polls far faster than
        # the board changes, so without this the folder fills with duplicates.
        signature = (
            snapshot.get("state_signature"),
            snapshot.get("signature"),
        )
        if (rules_id, signature) in self._unmapped_signatures:
            return
        self._unmapped_signatures.add((rules_id, signature))

        target = self._unmapped_dir(rules_id)
        try:
            target.mkdir(parents=True, exist_ok=True)
            path = target / f"{saved:03d}_{time.strftime('%H%M%S')}.json"
            path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False, default=str),
                encoding="utf8",
            )
        except OSError as error:
            # Recording is a bonus; never let it break the match.
            self._log(f"Cannot save snapshot for unmapped mode: {error}")
            self._unmapped_saved[rules_id] = UNMAPPED_MODE_MAX_SNAPSHOTS
            return

        self._unmapped_saved[rules_id] = saved + 1
        if saved + 1 == UNMAPPED_MODE_MAX_SNAPSHOTS:
            self._log(
                f"Snimljeno {UNMAPPED_MODE_MAX_SNAPSHOTS} snapshotova za "
                f"'{rules_id}' — dosta za analizu, prestajem."
            )

    @staticmethod
    def _handled_outside_mode(rules_id) -> str | None:
        """Where a ruleset's rules come from when the mode entry is not it."""
        normalized = str(rules_id or "").strip().lower()
        for known, source in RULES_ID_HANDLED_OUTSIDE_MODE.items():
            if normalized == known or normalized.startswith(known):
                return source
        return None

    @staticmethod
    def _has_no_strategy_change(rules_id) -> bool:
        """True for a known ruleset whose rules the snapshot already covers."""
        normalized = str(rules_id or "").strip().lower()
        return any(
            normalized == known or normalized.startswith(known)
            for known in RULES_ID_NO_STRATEGY_CHANGE
        )

    @staticmethod
    def _effective_mode(state) -> GameMode:
        rules = ((state or {}).get("rules")) or {}
        rules_id = str(rules.get("id") or "").strip().lower()
        # A missing id used to end the lookup here. It no longer can: the board
        # model number is filled in by the engine even when the id is not, and
        # it is the more reliable of the two.
        if rules_id:
            mapped = RULES_ID_TO_MODE.get(rules_id)
            if mapped is not None:
                return mapped
            for prefix, mode in RULES_ID_TO_MODE.items():
                if rules_id.startswith(prefix):
                    return mode
        # The board model number is the engine's own answer and needs no
        # capture, so it settles every arena whose id has not been seen yet.
        board_model = rules.get("board_model_name")
        if board_model is not None:
            try:
                mapped = BOARD_MODEL_TO_MODE.get(int(board_model))
            except (TypeError, ValueError):
                mapped = None
            if mapped is not None:
                return mapped
        # The named field and the engine sweep are both valid sources: an older
        # agent build only fills the first, a newer one fills both.
        engine_fields = rules.get("engine_fields")
        engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
        for flag, mode in RULE_FLAG_TO_MODE:
            if rules.get(flag) or engine_fields.get(flag):
                return mode
        return GameMode.NONE

    @staticmethod
    def _active_mutation_types(snapshot) -> set[int]:
        return active_mutation_types((snapshot or {}).get("active_mutations"))

    @classmethod
    def _mutation_charge_colors(cls, snapshot) -> list[int]:
        """Colours a ColorChargesEnergy mutation adds to the booster meter."""
        colors: list[int] = []
        for mutation in (snapshot or {}).get("active_mutations") or []:
            if not isinstance(mutation, dict):
                continue
            config = mutation.get("config")
            config = config if isinstance(config, dict) else {}
            if not config.get("isActivated"):
                continue
            if mutation.get("type") != MUTATION_COLOR_CHARGES_ENERGY:
                continue
            color = board_source.slot_color_to_board(config.get("color"))
            if color is not None and color != BLUE and color not in colors:
                colors.append(color)
        return colors

    def _refresh_mutations(self, snapshot):
        """Spell out the Mutation Lab picks the bot believes are in force.

        The enum numbering is reconstructed, not shipped, so this line exists to
        be compared against the game's own mutation list: a name that does not
        match what the screen says means the pin is wrong, and a bare "tip N"
        means that member is unknown here and is being ignored by the
        simulation. Spent instant picks stay in the engine's list with
        `isActivated` false and are left out, same as everywhere else.
        """
        entries = []
        for mutation in (snapshot or {}).get("active_mutations") or []:
            if not isinstance(mutation, dict):
                continue
            config = mutation.get("config")
            config = config if isinstance(config, dict) else {}
            if not config.get("isActivated"):
                continue
            try:
                mutation_type = int(mutation["type"])
            except (KeyError, TypeError, ValueError):
                continue
            name = MUTATION_TYPE_NAMES.get(mutation_type)
            text = f"{mutation_type} {name}" if name else f"tip {mutation_type} (?)"
            color = board_source.slot_color_to_board(config.get("color"))
            color_name = COLOR_NAMES.get(color)
            if color_name:
                text += f" [{color_name}]"
            # durationType 1 is the permanent badge the game prints; anything
            # else is a pick that expires, which is worth seeing tick away.
            if config.get("durationType") != 1:
                left = config.get("durationAmountLeft")
                text += f" ({left} preostalo)" if left else " (privremena)"
            entries.append(text)
        self.MutationsLabel.setText("  |  ".join(entries) if entries else "-")

    def _track_turn_clock(self, state):
        """Time the start of our turn, so the remaining time can be inferred.

        The agent dumps ``rules.timePerTurn`` but no live countdown (the state's
        ``remaining_time`` is a placeholder the engine sweep never filled), so
        the clock is started here the moment a new turn of ours appears and read
        back against the monotonic clock. It errs on the late side -- the engine
        starts counting a touch before the snapshot arrives -- which is the safe
        direction for a "do not start a perk now" gate.
        """
        state = state or {}
        players = state.get("players") or []
        me = self._current_player(state, players) or {}
        mine = me.get("is_my_turn")
        if players and mine is False:
            self._turn_clock_key = None
            self._turn_started_at = None
            return
        key = self._turn_key(state)
        if key != self._turn_clock_key:
            self._turn_clock_key = key
            self._turn_started_at = time.monotonic()

    def turn_time_left(self, state):
        """Seconds left in our turn, or None when nothing limits it.

        None covers "this mode has no timer", "the clock is paused" and "the
        turn's start was never seen", and all three mean the same thing to the
        caller: nothing to hold back for.

        The engine's own countdown is the answer whenever it is there. It is
        read at the moment the snapshot is built, though, so the time the
        snapshot spent travelling and sitting here is subtracted -- otherwise a
        board that arrived two seconds ago would report a turn two seconds
        longer than the one actually being played.
        """
        state = state or {}
        if state.get("timer_paused"):
            # Popups and reconnects stop the clock. A frozen countdown must not
            # read as time running out.
            return None
        engine_value = state.get("remaining_time")
        if (
            isinstance(engine_value, (int, float))
            and engine_value <= 0
            and state.get("game_state") in GAME_STATES_CLOCK_NOT_STARTED
        ):
            # Before the first turn starts the engine reports 0, not the
            # budget: 2026-09-21 21:20:42 UTC read 0 at game_state -3 and the
            # full 1500 s only at -5, five seconds later. Read as "time is
            # up" it logged "Ostalo 0.0s" and, since plans are prepared from
            # -2 on, could strip the perk and booster from the first move.
            return None
        if isinstance(engine_value, (int, float)):
            age = self.snapshot_age_seconds()
            return max(0.0, float(engine_value) - (age or 0.0))
        rules = state.get("rules") or {}
        if not rules.get("is_timer"):
            return None
        try:
            budget = float(rules.get("time_per_turn"))
        except (TypeError, ValueError):
            return None
        if budget <= 0 or self._turn_started_at is None:
            return None
        return budget - (time.monotonic() - self._turn_started_at)

    @classmethod
    def _later_round_follows(cls, state) -> bool:
        """A multi-round match with at least one more round after this one."""
        try:
            total = int((state or {}).get("rounds_total"))
            current = int(cls._contract_round(state))
        except (TypeError, ValueError):
            return False
        return total > 1 and current < total

    def _low_on_turn_time(self, state) -> bool:
        left = self.turn_time_left(state)
        if left is None or left > LOW_TURN_TIME_SECONDS:
            return False
        if self._low_time_logged_for != self._turn_clock_key:
            self._low_time_logged_for = self._turn_clock_key
            objective = (
                "playing normally"
                if self._later_round_follows(state)
                else "playing for most points"
            )
            self._log(
                f"{max(0.0, left):.1f}s left in turn — {objective}, "
                "no perks and no booster (stays full for next turn)."
            )
        return True

    def _turn_label_text(self, state) -> str:
        """The turn owner and, when a clock is running, the seconds left on it."""
        state = state or {}
        players = state.get("players") or []
        me = self._current_player(state, players) or {}
        mine = me.get("is_my_turn")
        if players and mine is False:
            return "opponent's turn"
        owner = "my turn" if mine else "turn: ?"
        if state.get("timer_paused"):
            return f"{owner}  (timer paused)"
        left = self.turn_time_left(state)
        if left is None:
            return f"{owner}  (bez tajmera)"
        return f"{owner}  {left:.1f}s"

    def _reset_match_state(self):
        """Drop everything that belonged to the match that just ended.

        Reached from two directions: a new board object in the snapshot, and
        the agent reporting the match over. The second one is what makes the
        reader safe to leave attached across matches -- without it the next
        match would inherit this one's spent perk slots.
        """
        if self._auto_plan is not None:
            self._auto_plan.cancel()
        self._square_live.reset()
        self._exact_reader.reset()
        self._free_swap_guard.reset()
        self._research.reset()
        self._research_signature = None
        self._refill_monitor.reset()
        self._refill_tally = RefillTally()
        self.RefillLog.clear()
        self._refresh_refill_panel()
        self._clear_move_failures()
        # The score tracker and the telemetry's open move belong to the match
        # that ended: left alone, the next match's first move was closed with
        # the old match's meters (a large negative score delta). The screen GUI
        # only reset these on "Nova partija", which this window never calls.
        runtime.reset_runtime_score_tracking()
        runtime.reset_floor_lava_state()
        runtime.reset_bounty_state()
        # A failed kept-turn verdict belongs to the match that produced it.
        runtime.reset_mixy_deferral_watch()
        # A new match restocks the perk slots.
        self._used_perk_slots.clear()
        self._used_perk_slot_sources.clear()
        self._perk_pending_confirmation = None
        self._mixy_code_reported = None
        self._mixy_spent_code = None
        self._mixy_spent_colors.clear()
        self._mixy_spend_armed = True
        self._mixy_uses_this_activation = 0
        self._mixy_max_uses = 0
        self._mixy_prev_phase = None
        self._mixy_prev_energy = None
        self._mixy_transient_live = False
        self._mixy_prev_code = None
        self._mixy_last_use_at = 0.0
        self._mixy_activated_at = 0.0
        self._mixy_activation_count = 0
        self._mixy_turn_key = None
        # The jelly zone belongs to the board that carried it.
        self._jelly_zone_tracker.reset()
        self._jelly_zone_reported = []
        self._color_climb_reported = None
        self._last_board_object = None
        self._last_moves_made = None
        # The played-signature latch belongs to the match it was played in; a
        # carried-over latch could silently swallow the new match's first move.
        self._last_played_signature = None
        self._last_played_at = None
        self._lights_up_play_column = None
        self._lights_up_stale_column = None

    def _track_match_reset(self, snapshot, state):
        """Clear per-match strategy state the engine has just reset.

        The screen GUI has "Reset"/"Nova partija" buttons for this; here the
        snapshot says it outright, so nothing has to be pressed. Two levels:

        * a new board object is a new match -- The Floor Is Lava's marks and
          Bullseye's growing target both start over;
        * `moves_made_this_turn` going back to zero is a new turn, and Floor Is
          Lava's ruleset sets `resetGroundOnTurnEnd`, so the ground goes with
          it. Without this the marks carried into the next match and the bot
          planned eruptions on columns whose ground was whole.
        """
        board_object = snapshot.get("board_object")
        made = state.get("moves_made_this_turn")
        try:
            made = int(made)
        except (TypeError, ValueError):
            made = None
        new_match = (
            board_object is not None and board_object != self._last_board_object
        )
        new_turn = (
            made is not None
            and self._last_moves_made is not None
            and made < self._last_moves_made
        )
        if new_match:
            self._reset_match_state()
        elif new_turn:
            runtime.reset_floor_lava_state()
        self._last_board_object = board_object
        self._last_moves_made = made

    # SpecialAbilityType.FroggyFu.
    ABILITY_FROGGY_FU = 63

    def _froggy_gather_region(self, me):
        """Froggy Fu's gather radius and shape, off its own tuning params.

        `FroggyFu.ReadConfig` reads both out of
        ``SpecialAbility.Config.additionalParams``, which the agent already
        ships as `special_ability_params`. Only read when the played booster
        really is Froggy Fu -- another booster's params carry no gather keys,
        and a stray value there must not be handed to the lotus scoring.

        Activation is left at the first one: `GetValueForActivation` clamps,
        and the radius list is usually flat. Any real radius beats the
        whole-board count it replaces.
        """
        me = me or {}
        ability = me.get("special_ability_type")
        if ability is None or int(ability) != self.ABILITY_FROGGY_FU:
            return None
        region = froggy_gather_config_from_params(me.get("special_ability_params"))
        if region and region != self._froggy_region_reported:
            self._froggy_region_reported = region
            radius, chebyshev = region
            self._log(
                f"Froggy Fu zona: poluprecnik {radius}, "
                f"{'kvadrat' if chebyshev else 'romb'}"
            )
        return region

    def _hot_color_state(self, snapshot):
        """The hot colour pair from HotColorBoard, or None to keep the badge read.

        The screen reader only ever sees the colour that is live *now*. The
        board model also carries the one that takes over at the end of this
        move, which is what the lookahead needs -- scoring the next ply with
        today's hot colour is known to be wrong, because `onMoveEnd` rotates it.
        """
        if self._effective_mode(snapshot.get("state")) is not GameMode.HOT_COLOR:
            return None
        state = board_source.hot_color_state(snapshot)
        if state and state != self._hot_color_reported:
            self._hot_color_reported = dict(state)
            self._log(
                "Hot Color iz memorije: sada boja "
                f"{state.get('current')} ({state.get('value')}x), "
                f"sledeca {state.get('next')} ({state.get('next_value')}x)"
            )
        return state

    def _funky_tile_cells(self, snapshot):
        """The Funky Tiles cells from memory, or () -- never a screen read.

        Logged when the set changes, and logged loudly when the mode is Funky
        Tiles but the agent sent no grid: then the bot plays the mode blind and
        that has to be visible rather than silent.
        """
        if self._effective_mode(snapshot.get("state")) is not GameMode.FUNKY_TILES:
            return ()
        cells = board_source.funky_tile_cells(snapshot)
        reported = None if cells is None else [list(cell) for cell in cells]
        if reported != getattr(self, "_funky_reported", "unset"):
            self._funky_reported = reported
            if cells is None:
                self._log("Funky Tiles: agent NOT sending cell_types — playing without funky cells")
            else:
                self._log(
                    "Funky Tiles iz memorije: "
                    + (", ".join(f"({r + 1},{c + 1})" for r, c in cells) or "nema polja")
                )
        return cells or ()

    def _vegas_views_state(self, snapshot):
        """The Vegas tile from memory, or None -- logged when it changes."""
        if self._effective_mode(snapshot.get("state")) is not GameMode.VEGAS_VIEWS:
            return None
        state = board_source.vegas_views_state(snapshot)
        reported = None if state is None else (state["cells"], state["multiplier"])
        if reported != getattr(self, "_vegas_reported", "unset"):
            self._vegas_reported = reported
            if state is None:
                self._log("Vegas Views: agent NOT sending cell_types — playing without Vegas cells")
            else:
                tiles = ", ".join(f"({r + 1},{c + 1})" for r, c in state["cells"])
                self._log(
                    f"Vegas Views iz memorije: {tiles or 'nema polja'}"
                    f" x{state['multiplier']} ({state['multiplier_source']})"
                )
        return state

    def _floor_lava_status_text(self, snapshot):
        """Where the lava marks come from right now, for the mode row.

        Says outright whether the engine's counter is being read, so a reader
        that silently stopped working shows up on screen instead of in a lost
        match.
        """
        counts = board_source.floor_lava_column_counts(snapshot)
        marked = sorted(col for col, count in counts.items() if count >= 1)
        fields = snapshot.get("board_fields")
        view = fields.get("lava_view") if isinstance(fields, dict) else None
        view = view if isinstance(view, dict) else {}
        # Which board the counter came from: the view's own FloorIsLavaBoard
        # (LavaBackground._board) when the agent found one that is not the
        # played board, otherwise the played board.
        from_view = view.get("same_board") is False and view.get("columns") is not None
        source = "display board" if from_view else "match board"
        if marked:
            return (
                f"lava iz memorije ({source}): kolone "
                + ", ".join(str(col + 1) for col in marked)
            )
        if counts:
            return f"lava iz memorije ({source}): nema oznacenih"
        tally = runtime.floor_lava_state()
        own = ", ".join(str(col + 1) for col in tally) if tally else "nema"
        return f"lava NE CITA iz memorije — botov brojac: {own}"

    def _floor_lava_columns(self, snapshot):
        """Columns already matched once, from the engine's lava counter.

        None means "unknown", which leaves the bot on its own move-by-move
        tally; a tuple -- empty included -- is the engine's word and replaces
        it.

        History, because it cost two months: from 2026-08-19 on
        `ColumnsEruptionDictionary` read `{}` in every poll while the ground on
        screen was visibly broken, so an empty read was treated as "unknown"
        and the bot played off its own tally, which drifts (a swipe that did
        not land was still committed; eruptions promised on cold columns). On
        2026-09-18 the empty reads turned out to be the agent's: it asked for
        `count` before `_count`, got null, and Number(null) is 0. With that
        fixed the dictionary arrives with one entry per column.
        """
        if self._effective_mode(snapshot.get("state")) is not GameMode.FLOOR_IS_LAVA:
            return None
        counts = board_source.floor_lava_column_counts(snapshot)
        marked = tuple(sorted(col for col, count in counts.items() if count >= 1))
        if not marked:
            # The engine keeps one entry per column for the whole match (0 =
            # whole ground, 1 = broken), so a counter that arrives *with keys*
            # and no column at 1 is the engine saying nothing is marked. A
            # counter with no keys at all is a read that failed -- that was the
            # agent's `count`/`_count` bug, fixed 2026-09-18 -- and stays
            # "unknown".
            if counts:
                self._floor_lava_reported = []
                return ()
            return None
        if list(marked) != self._floor_lava_reported:
            self._floor_lava_reported = list(marked)
            self._log(
                "Lava: brojac iz igre javlja kolone "
                + ", ".join(str(col + 1) for col in marked)
            )
        return marked

    def _jelly_debug(self, snapshot):
        """The raw evidence behind the jelly zone, for the Debug record only.

        Ticking Debug is meant to be the whole procedure: the agent switches to
        trace mode, which is also what turns on the engine-decoded read, and
        everything the two legs saw lands in the move's ``move.json`` next to
        the cells the bot actually played with. Nothing here feeds the
        strategy -- it exists so a wrong zone can be pinned on the read, the
        parse or the (x, y) mapping after the fact.
        """
        if not self.DebugCheck.isChecked():
            return None
        jelly = snapshot.get("jelly")
        extra = snapshot.get("board_extra_data")
        state = board_source.jelly_zone_state(snapshot)
        cached = self._jelly_zone_tracker.cached
        if jelly is None and not extra and state is None and cached is None:
            return None
        return {
            "agent": jelly,
            "board_extra_data": extra,
            # What the host would serve when this snapshot says nothing: the
            # last non-empty read. Cells matching host_cache but a null
            # host_parsed means the move ran on the cache.
            "host_cache": None
            if cached is None
            else {
                "cells": [list(cell) for cell in cached["cells"]],
                "target_color": cached["target_color"],
                "verified": cached["verified"],
            },
            "host_parsed": None
            if state is None
            else {
                "cells": [list(cell) for cell in state["cells"]],
                "key": state["key"],
                "verified": state["verified"],
                "target_color": state["target_color"],
                "phase": state["phase"],
                "uses_left": state["uses_left"],
            },
        }

    # SpecialAbilityType.UFOBeamSE, whose eye count also comes from the
    # manual-dump getters (see UfoAbductionTracker._sync_from_engine).
    ABILITY_UFO_SE = 49

    def _needs_engine_read(self, snapshot) -> bool:
        """This board's engine-only values were not read on this snapshot.

        Three things are only read by the engine's own getters, which the agent
        runs on a manual dump and never on the plain poll: the jelly zone
        (``all_infected``), Mixy's ``UsesLeft`` and the UFO eye count
        (``special_ability_engine``). The host keeps the last values between
        dumps -- the jelly tracker serves its cache, the Mixy and UFO counters
        fall back to inference -- and all of them change with the board. So in
        a match that has any of them, a move is not planned off a poll.

        Until 2026-09-14 the timed-turn clock made the GUI dump every 0.4 s,
        which hid this. Once that stopped, a whole turn was played on a jelly
        zone read before its first move (six "jelly conversion" plans in a
        row, and an Extra move that was no extra move). The dump this asks for
        replaces the poll as the current snapshot, and the agent does not
        resend an unchanged board, so it is one dump per board.
        """
        snapshot = snapshot or {}
        # A manual dump has run the getters. If one failed there, another dump
        # will not fix it, and waiting on it would stop play for good.
        if snapshot.get("reason") == "manual_rpc":
            return False
        jelly = snapshot.get("jelly")
        if isinstance(jelly, dict) and jelly.get("keys"):
            return True
        state = snapshot.get("state") or {}
        me = self._current_player(state, state.get("players") or []) or {}
        try:
            ability = int(me.get("special_ability_type"))
        except (TypeError, ValueError):
            return False
        return ability in (self.ABILITY_MIXY_MEOW, self.ABILITY_UFO_SE)

    def _jelly_zone_cells(self, snapshot):
        """The jelly's infected area, straight out of BoardModel.extraData.

        None means "memory did not say", and the caller falls back to the pixel
        detector -- an agent build without ``board_extra_data``, or a poll that
        skipped the engine-decoded read, must not read as "the area is empty".
        An empty tuple means memory said there is no jelly right now (the
        engine's decoded list came back empty: the zone was consumed and the
        booster has not been thrown again), and the detector is skipped just
        as it is for a non-empty read: JellySE owns these cells, so there is
        nothing left for saturation heuristics to add.

        Between reads the last zone is served from ``_jelly_zone_tracker``;
        the tracker's docstring says what ends that.

        Two hard rules since 2026-09-18:

        * no JellySE booster in the match, no jelly zone -- the zone is never
          even looked for, so nothing else that lives in the shared extraData
          (The Floor Is Lava's "columns" was read as a 7-cell zone that night)
          can ever be mistaken for one;
        * this never returns None. There is no pixel detector behind the
          memory GUI any more: what memory does not say is "no zone".
        """
        if not board_source.jelly_booster_in_match(snapshot):
            if self._jelly_zone_tracker.cached is not None:
                self._jelly_zone_tracker.reset()
            self._jelly_zone_reported = []
            return ()
        cells, source = self._jelly_zone_tracker.update(snapshot)
        if cells is None:
            cells = ()
        if source == "memory":
            if list(cells) != self._jelly_zone_reported:
                self._jelly_zone_reported = list(cells)
                cached = self._jelly_zone_tracker.cached or {}
                color = cached.get("target_color")
                suffix = "" if color is None else f", boja {color}"
                self._log(f"Jelly: zone from memory, {len(cells)} cells{suffix}")
        elif source == "cleared":
            self._jelly_zone_reported = []
            self._log("Jelly: memory reports zone is gone (consumed)")
        elif source == "cache":
            cached = self._jelly_zone_tracker.cached
            if cached and not cached["served_logged"]:
                cached["served_logged"] = True
                self._log(
                    f"Jelly: zone from cache (memory silent), "
                    f"{len(cached['cells'])} cells"
                )
        return cells

    def _lights_up_column(self, snapshot):
        """The lit column in Lights Up, for the readout only.

        Recognition, not strategy: the number is shown in the mode label and
        the column is outlined on the board, and nothing downstream reads it.
        The engine moves the column at the end of every move, so a changed
        value is logged once per change rather than per poll.

        None means the snapshot cannot say -- an agent build that does not
        sweep the board fields, or any other mode.
        """
        rules = ((snapshot.get("state") or {}).get("rules")) or {}
        rules_id = str(rules.get("id") or "").strip().lower()
        board_model = rules.get("board_model_name")
        try:
            is_lights_up = int(board_model) == LIGHTS_UP_BOARD_MODEL
        except (TypeError, ValueError):
            is_lights_up = False
        if not is_lights_up and not rules_id.startswith("lights-up"):
            return None
        state = board_source.lights_up_state(snapshot)
        if state is None:
            return None
        column = int(state["column"])
        if column != self._lights_up_reported:
            self._lights_up_reported = column
            how = (
                "nasumicno"
                if state.get("random_change", True)
                else "redom"
            )
            self._log(f"Lights Up: lit column {column + 1} (changes {how})")
        return column

    def _track_score_multiplier(self, snapshot) -> int:
        """Our live score multiplier, logged whenever the game moves it.

        Two board models are built entirely out of this one number, and both
        write the same field, so one reader covers them:

        * ``moves-multiplier`` (34) raises it by one on every move played --
          measured walking 1..14 in step with the move counter.
        * ``multiplier-madness`` (22) raises it by one per destroyed combo of
          the mode's own colour, which is *not* once per move: three of the
          recorded steps landed inside a single move's cascades. The engine
          also takes one back off the opponent on the same event.

        Plain modes read x1 forever, which is why this is not gated on the mode
        -- there is nothing to gate, and Lights Up already used the same field.
        """
        state = board_source.score_multiplier_state(snapshot)
        if state is None:
            return 1
        multiplier = int(state.get("ours") or 1)
        if multiplier != self._score_multiplier_reported:
            previous = self._score_multiplier_reported
            self._score_multiplier_reported = multiplier
            if previous is not None and multiplier != 1:
                label = state.get("mode") or "mnozilac"
                opponent = state.get("opponent")
                self._log(
                    f"{label}: mnozilac x{previous} -> x{multiplier}"
                    + (f" (protivnik x{opponent})" if opponent else "")
                )
        return max(1, multiplier)

    def _lights_up_request_state(self, snapshot, me) -> dict | None:
        """The lit column plus the multiplier it already built, for the scorer.

        Both halves have to travel together: a multiplier point is worth all
        the base points still to come *divided by* the multiplier already
        standing, so without the second number the bot would keep paying an
        opening-move price for a point at x17.
        """
        column = self._lights_up_column(snapshot)
        if column is None:
            return None
        try:
            multiplier = int((me or {}).get("score_multiplier") or 1)
        except (TypeError, ValueError):
            multiplier = 1
        multiplier = max(1, multiplier)
        # Log every step the game takes. This is the only record of what the
        # rule actually paid, and it is what a later prediction check would be
        # measured against -- the model says one point per combo touching the
        # lit column, and a jump of three says three combos touched it.
        if multiplier != self._lights_up_multiplier_reported:
            if self._lights_up_multiplier_reported is not None:
                # The column the paying action was planned on: by the time
                # the step is read the lit column has often moved on already.
                played = self._lights_up_play_column
                where = (
                    f"odigrano na koloni {played + 1}, sad sija {column + 1}"
                    if played is not None and played != column
                    else f"kolona {column + 1}"
                )
                self._log(
                    f"Lights Up: mnozilac x{self._lights_up_multiplier_reported}"
                    f" -> x{multiplier} ({where})"
                )
            self._lights_up_multiplier_reported = multiplier
        return {"column": column, "multiplier": multiplier}

    def _lights_up_scored_state(self, snapshot, me) -> dict | None:
        """The Lights Up state a move is priced on, minus a column going dark.

        The lit column moves only after the swap's cascades finish animating,
        0.1-0.8 s after memory already reports a settled board that accepts
        input (2026-09-18 23:09 match: 21:10:16.15 -> 16.23, 21:11:03.87 ->
        04.38, 21:11:48.56 -> 49.05 UTC). Three back-to-back swaps in that
        match were priced on the old column. Waiting for the move costs turn
        time the player will not give up, so while the column our swap was
        played on is still showing, the move is priced on points alone: the
        next column is a fresh random one, not this.
        """
        state = self._lights_up_request_state(snapshot, me)
        # What the action is played on, raw: the next swap's staleness check
        # compares against the column actually showing, not the priced one.
        self._lights_up_play_column = None if state is None else state["column"]
        stale = self._lights_up_stale_column
        if state is None or stale is None:
            return state
        if state["column"] != stale:
            self._lights_up_stale_column = None
            return state
        return dict(state, column=None)

    def _color_climb_request_state(self, snapshot, me) -> dict | None:
        """Our two multiplier colours in Color Climb, for the scorer.

        RainbowMultiplierBoard deals each player two of the four non-charge
        colours at game start and raises that player's ScoreMultiplier by one
        per destroyed combo in either of them. The pair is the whole mode: with
        it the scorer counts multiplier combos, prefers those colours for the
        extra move, the lotus trigger, the Mixy code and the sweep, and the
        booster gate lets an ordinary extra in them go before an immediate
        activation. Without it (None) the mode scores like a plain board.
        """
        if self._effective_mode(snapshot.get("state")) is not GameMode.COLOR_CLIMB:
            return None
        seat = (me or {}).get("index")
        state = board_source.color_climb_state(
            snapshot, seat=seat if isinstance(seat, int) else None
        )
        if state is None:
            return None
        colors = tuple(state.get("colors") or ())
        if colors and colors != self._color_climb_reported:
            self._color_climb_reported = colors
            names = " i ".join(
                ENERGIZED_COLOR_LABELS.get(color, str(color)).lower() for color in colors
            )
            theirs = " i ".join(
                ENERGIZED_COLOR_LABELS.get(color, str(color)).lower()
                for color in state.get("opponent_colors") or ()
            )
            self._log(
                f"Color Climb: nase boje {names}"
                + (f" (protivnik {theirs})" if theirs else "")
                + f", mnozilac x{state.get('multiplier', 1)}"
            )
        return {"colors": colors, "multiplier": int(state.get("multiplier") or 1)}

    def _score_multiplier_request_state(self, snapshot) -> dict | None:
        """The player's live score multiplier, for the two boards made of it.

        A multiplier point is worth all the base points still to come divided
        by the multiplier already standing, so the scorer cannot price one
        without this number -- it would keep paying an opening-move price for a
        point at x22 (the highest the recorded match reached).
        """
        state = board_source.score_multiplier_state(snapshot)
        if state is None:
            return None
        return {"multiplier": int(state.get("ours") or 1),
                "opponent_multiplier": state.get("opponent")}

    def _column_mania_request_state(self, snapshot) -> dict | None:
        """The live per-column multipliers in Column Mania, for the scorer.

        Column Mania is the only mode whose points are pure board state: a
        cleared cell is worth its column's ``CellModel.scoreMultiplier``, every
        column opens at x1, and ``onMoveEnd`` raises each column the move
        cleared something in. The pending list the board accumulates during a
        move (``colsToIncrease``) is not enough on its own -- it only says what
        the current move will add, never what the columns already stand at, so
        the multipliers themselves have to be read.

        None means the snapshot cannot say -- another mode, or an agent build
        without ``cell_multipliers`` -- and the mode then scores like a plain
        board rather than on a guessed ramp.
        """
        rules = ((snapshot.get("state") or {}).get("rules")) or {}
        rules_id = str(rules.get("id") or "").strip().lower()
        board_model = rules.get("board_model_name")
        try:
            is_column_mania = int(board_model) == COLUMN_MANIA_BOARD_MODEL
        except (TypeError, ValueError):
            is_column_mania = False
        if not is_column_mania and not rules_id.startswith("column-mania"):
            return None
        state = board_source.column_mania_state(snapshot)
        if state is None:
            return None
        multipliers = tuple(int(value) for value in state["multipliers"])
        if multipliers != self._column_mania_reported:
            self._column_mania_reported = multipliers
            ramp = " ".join(f"x{value}" for value in multipliers)
            pending = state.get("pending_columns") or ()
            suffix = (
                ""
                if not pending
                else " (u toku: " + ", ".join(str(col + 1) for col in pending) + ")"
            )
            self._log(f"Column Mania: columns {ramp}{suffix}")
        return {
            "multipliers": list(multipliers),
            "pending_columns": list(state.get("pending_columns") or ()),
        }

    @staticmethod
    def _ability_temp_special_cells(snapshot) -> tuple:
        """(row, col) of the specials a booster laid down for this turn only."""
        special = (snapshot or {}).get("special_board") or []
        cells = []
        for slot in (snapshot or {}).get("slots") or ():
            try:
                row, col = int(slot["y"]), int(slot["x"])
                if int(slot.get("status") or 0) & 1 and special[row][col]:
                    cells.append((row, col))
            except (IndexError, KeyError, TypeError, ValueError):
                continue
        return tuple(cells)

    @staticmethod
    def _every_match_is_special(rules) -> bool:
        rules = rules or {}
        engine_fields = rules.get("engine_fields")
        engine_fields = engine_fields if isinstance(engine_fields, dict) else {}
        return bool(
            rules.get("every_match_is_special")
            or rules.get("everyMatchIsSpecial")
            or engine_fields.get("everyMatchIsSpecial")
            or engine_fields.get("every_match_is_special")
        )

    @staticmethod
    def _mode_label_text(state, rules_id, mode, unmapped="", extra="") -> str:
        return f"{rules_id} -> {mode.value}{unmapped}{extra}"

    # -------------------------------------------------------------- move ---

    def snapshot_age_seconds(self) -> float | None:
        """How long ago this GUI last received a board, or None if never."""
        if self._snapshot_received_at is None:
            return None
        return max(0.0, time.monotonic() - self._snapshot_received_at)

    def _request_dump(self) -> bool:
        """Ask the agent for a board without ever blocking the caller.

        The RPC send is the part that hangs. Frida's synchronous export call has
        no timeout, so one request the agent does not answer blocks whichever
        thread sent it -- and when that is the Qt thread, it takes the auto tick,
        the turn clock and every arriving snapshot down with it. That is exactly
        what 2026-08-21 15:27 looked like: a settled board, our turn, six moves
        left, and 174 s of complete silence that ended the moment the pending
        dump finally came back.

        So the call goes to a throwaway thread and callers only ever wait on the
        receiver's event. One request is in flight at a time; asking again while
        the agent is still thinking would just pile up blocked threads.
        """
        receiver, script = self._reader, self._reader_script
        if receiver is None or script is None:
            return False
        with self._dump_lock:
            if self._dump_inflight:
                return True
            self._dump_inflight = True
        receiver.snapshot_event.clear()
        started = time.monotonic()
        self._dump_started_at = started

        def worker():
            try:
                reader._export_call(script.exports_sync, ("dump_board", "dumpboard"))
            except Exception as exc:
                self._reader_signals.status.emit(
                    f"Ne mogu da zatrazim svezu tablu: {exc}"
                )
            finally:
                waited = time.monotonic() - started
                with self._dump_lock:
                    self._dump_inflight = False
                if waited >= SLOW_DUMP_WARN_SECONDS:
                    append_freeze_log([
                        f"slow dump: agent responded after {waited:.1f}s, "
                        f"heartbeat={json.dumps(receiver.last_heartbeat, ensure_ascii=False)}"
                    ])
                    self._reader_signals.status.emit(
                        f"Game delayed {waited:.1f}s delivering the board "
                        "(reader was blocked, auto was stalled)."
                    )

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _refresh_snapshot_now(self, timeout: float = 1.5) -> bool:
        """Ask the agent for the board right now, and take the answer.

        The reply is read straight off the receiver, which the Frida thread
        writes -- not through the Qt signal, which would need this thread to
        return to the event loop first and would deadlock the wait.
        """
        receiver = self._reader
        if receiver is None:
            return False
        # Only a board that arrives during this call counts. With a dump
        # already in flight _request_dump returns True without clearing the
        # event, which may have been set seconds ago; the old board then went
        # through _on_snapshot again and was stamped as received just now.
        previous = receiver.last_snapshot
        if not self._request_dump():
            return False
        deadline = time.monotonic() + timeout
        while receiver.last_snapshot is previous:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            receiver.snapshot_event.wait(min(0.05, remaining))
        snapshot = receiver.last_snapshot
        if snapshot is None:
            return False
        self._on_snapshot(copy.deepcopy(snapshot))
        return True

    def _memory_current_score_state(self):
        """The resolved state of the newest snapshot, for the pre-click check.

        Called from the move worker thread: it only reads the receiver's last
        snapshot (the agent pushes one on every change, the booster flag
        included), no RPC and no widgets. None leaves the plan's own state.
        """
        receiver = self._reader
        snapshot = receiver.last_snapshot if receiver is not None else None
        if not snapshot:
            return None
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        return self._memory_score_state(
            state, players, self._current_player(state, players)
        )

    def _memory_board_frame(self):
        """A fresh ``(board, special_board)`` for perk verification.

        Called from the move worker thread, so it deliberately does *not* go
        through ``_on_snapshot``: it asks the agent for a dump and reads the
        answer straight off the receiver, touching no widgets. Returning None
        just means the executor gets an invalid frame and keeps polling.
        """
        receiver = self._reader
        if receiver is None:
            return None
        try:
            if not self._request_dump():
                return None
            if not receiver.snapshot_event.wait(PERK_FRAME_TIMEOUT_SECONDS):
                return None
            snapshot = receiver.last_snapshot
        except Exception:
            return None
        if not snapshot:
            return None
        board = snapshot.get("board")
        special_board = snapshot.get("special_board")
        if not board:
            return None
        # Third element: the engine's own "a perk was consumed this move"
        # flag, so the executor's perk_used check is answered by memory
        # instead of staying "unknown" forever (Energy Boost's verification
        # requires it -- see _capture_perk_execution_frame in runtime.py and
        # the 2026-08-21 17-06-38 effect_not_confirmed incident). None when
        # the snapshot carries no players, so the executor keeps treating it
        # as unknown rather than as "not used".
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        me = self._current_player(state, players)
        perk_used = (
            None if me is None else bool(me.get("is_board_ability_used_this_move"))
        )
        return copy.deepcopy(board), copy.deepcopy(special_board), perk_used

    def _snapshot_is_current(self) -> bool:
        """Refuse to compute a move from a board that is no longer the game's.

        The last snapshot stays in memory after the reader stops, and nothing
        about it looks stale -- so a click would compute a perfectly good move
        for a board that is minutes old and swipe it into a board that has moved
        on. That is the "bot played an impossible move" failure, and it is the
        worst one: the move is legal on screen only by accident.

        Age alone cannot decide this: the agent sends a snapshot when the board
        or the game state *changes*, so a quiet game legitimately goes seconds
        without one (2026-08-17 03:57 refused a perfectly good board at 6.5s).
        So an old snapshot is not rejected, it is refreshed on the spot -- and
        only a game that does not answer that request counts as stale.
        """
        if self._reader_session is None:
            self._log(
                "Reader not attached — board is stale, not computing move. "
                "Attach reader and try again."
            )
            return False
        age = self.snapshot_age_seconds()
        if age is not None and age <= board_source.DEFAULT_MEMORY_MAX_AGE_SECONDS:
            return True
        if self._refresh_snapshot_now():
            return True
        shown = "unknown" if age is None else f"{age:.1f}s"
        self._log(
            f"Game not sending fresh board ({shown}) — not computing move. "
            "Check reader/game."
        )
        return False

    _ACTION_LABELS = {
        "best_move": "Best Move",
        "highest_points": "Most Points",
        "extra_move": "Extra Move",
        "lowest_points": "Least Points",
        "solo_cross": "Predji zastavicu",
    }

    def _auto_action(self):
        """The action the auto loop plays, or None while no auto is on.

        Two auto buttons, one loop: "Auto" plays the best move, "Najmanje
        poena auto" burns moves. They are mutually exclusive (see the toggle
        handlers), so at most one answers here.
        """
        if self.AutoButton.isChecked():
            return "best_move"
        if self.WorstAutoButton.isChecked():
            return "lowest_points"
        return None

    def _stop_auto(self):
        """Switch off whichever auto is running."""
        if self.AutoButton.isChecked():
            self.AutoButton.setChecked(False)
        if self.WorstAutoButton.isChecked():
            self.WorstAutoButton.setChecked(False)

    def _play(self, action: str, *, prepare_ahead: bool = False,
              armed: bool = True):
        """Compute a move and play it.

        ``prepare_ahead`` runs the search speculatively and holds the result
        until the board is ready; ``armed`` says whether the held move may be
        played at all. A move button is a request to play *now*: it arms a
        held plan for the same action, or queues its own action behind a
        plan for a different one. Either way nothing is played before the
        computation finishes, so a click during a cascade is safe.
        """
        if not prepare_ahead:
            # A click: remember it until it is played, and treat this board as
            # unplayed even if it is the one the previous move was played on
            # (a swallowed swipe looks exactly like that).
            self._requested_action = action
            self._requested_at = time.monotonic()
            self._last_played_signature = None
        if self._move_running:
            if prepare_ahead and not armed:
                return
            plan = self._auto_plan
            if plan is None or plan.executing:
                return
            snapshot = self._snapshot
            if (plan.action == action and not plan.cancelled
                    and snapshot is not None
                    and plan.key == self._auto_plan_key(snapshot)):
                plan.arm()
                self._update_auto_plan()
                self._set_actions_enabled(self._reader_session is not None)
                self._set_calc_status(
                    f"done ({plan.action_label}) - playing once the board settles"
                    if plan.computed
                    else f"computing ({plan.action_label}) - playing when done"
                )
                self.statusBar().showMessage(f"{plan.action_label}: playing when done")
                return
            # Another action (or a stale board) holds the worker: drop it; the
            # standing request restarts on the requested action as soon as the
            # worker is free.
            plan.cancel()
            self._set_calc_status(
                f"cancelling ({plan.action_label}), computing {self._ACTION_LABELS[action]}"
            )
            return
        if not prepare_ahead:
            prepare_ahead = True
            armed = True
        # Asking for a move is the user saying a match is on screen. The idle
        # path refuses to guess that (a finished match is indistinguishable
        # from a running one on the heap), so this is where a match already in
        # progress at attach time gets picked up.
        self._wake_agent()
        snapshot = self._snapshot
        if snapshot is None:
            self._log("No snapshot from memory.")
            return
        # The refresh inside lands in _on_snapshot, which dispatches the auto
        # tick -- and from a timer tick nothing else guards it, so the nested
        # tick would run the gates again and start a second worker on the
        # same board before this one has even built its request.
        was_dispatching = self._auto_dispatching
        self._auto_dispatching = True
        try:
            current = self._snapshot_is_current()
        finally:
            self._auto_dispatching = was_dispatching
        if not current:
            return
        snapshot = self._snapshot
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        me = self._current_player(state, players) or {}
        rules = state.get("rules") or {}
        board_profile, board_size = self._live_board_profile(
            state, snapshot.get("board")
        )
        if board_profile is None:
            # No geometry for this size: a swipe would land on the wrong cells,
            # which is worse than not playing.
            self._log(
                f"Board is {board_size}x{board_size} but there is no "
                "calibration for that size — not playing."
            )
            return

        # Same three actions the main GUI exposes, with its exact semantics:
        # "Best Move" is highest_points with future value, "Most Points"
        # is the points_only objective, "Extra move" is the extra-only gate.
        # The last seconds of a turn (LOW_TURN_TIME_SECONDS) never spend the
        # booster or a perk: the booster it would spend is the one the next
        # turn should open with. Playing for points only, whatever was asked,
        # is the LAST round's rule (player, 2026-09-19): while another round
        # follows, the blue a late move banks still carries over and the board
        # it leaves still goes to the opponent, so the normal ranking -- blue
        # tier, versus handover pricing -- keeps deciding the move.
        bonus_time = float(
            rules.get("extra_move_bonus_time")
            or (rules.get("engine_fields") or {}).get("extraMoveBonusTime")
            or 0.0
        )
        solo_challenge = self._is_solo_challenge(state)
        timer_enabled = rules.get("is_timer")
        if timer_enabled is None:
            timer_enabled = (rules.get("engine_fields") or {}).get("isTimer")
        use_turn_clock = not solo_challenge or bool(timer_enabled)
        low_on_time = use_turn_clock and self._low_on_turn_time(state)
        # "Least Points" is the odd one out: it exists to throw moves away,
        # so the low-clock rule (play for points) must not turn it around.
        burning_moves = action == "lowest_points"
        low_clock_points_only = (
            low_on_time and not burning_moves and action != "solo_cross"
            and not self._later_round_follows(state)
            and bonus_time <= 0
        )
        # Only the objective changes; `action` itself stays what was asked,
        # because it is also the plan's identity (AutoPlan.action).
        profile = {
            "best_move": ("highest_points", "Best Move", True, False, False),
            "highest_points": ("points_only", "Most Points", True, True, False),
            "extra_move": ("extra_move", "Extra move", False, False, True),
            "lowest_points": ("lowest_points", "Least Points", False, True, False),
            "solo_cross": ("highest_points", "Predji zastavicu", True, False, False),
        }["highest_points" if low_clock_points_only else action]
        engine_action, display_label, include_future_value, points_only, extra_only = profile
        if low_clock_points_only:
            display_label = f"{display_label} (end of turn)"
        # ColorPointsIncrease needs nothing here: the engine writes the boosted
        # value into SlotModel.score, which the score legend already reads.
        mutation_types = self._active_mutation_types(snapshot)
        # No booster at all on a low clock -- targeted or one-click. The
        # one-click kind used to be allowed (it is cheaper than the swipe),
        # but its effect lands in a turn that is over and the next turn then
        # starts with an empty meter; the player wants it full instead.
        # A move burner never touches the booster or a perk either.
        hold_booster = low_on_time or burning_moves
        # Resolved before the request so a screen read of the slot strip cannot
        # race the worker thread that is about to repoint the same geometry.
        selected_perks = (
            (runtime.PERK_NONE, runtime.PERK_NONE)
            if low_on_time or burning_moves
            else self._selected_perks_for_request(rules, board_profile)
        )
        # True Solo Challenge: played alone AND with real time to think. "Alone"
        # is the players list (a live versus opponent always rides in it), but
        # alone is not enough -- Showdown and Master League are also played solo
        # on my own board while racing a short clock (measured 2026-08-26:
        # master-league timePerTurn=65s vs mighty-mushrooms solo timePerTurn=1500s).
        # pvpMode deliberately does NOT gate this (solo reports 1 or 2).
        turn_time_left = self.turn_time_left(state) if use_turn_clock else None
        # Timed solo race (Showdown / Party / Rumble: my own board, short
        # clock), last round, clock inside the deadline: the booster goes
        # first (BOOSTER_CLOCK_DEADLINE_SECONDS). Below the low-clock line
        # hold_booster wins, so the 8 s rule itself is unchanged.
        booster_clock_deadline = bool(
            not hold_booster
            and not solo_challenge
            and rules.get("is_timer")
            and turn_time_left is not None
            and turn_time_left <= BOOSTER_CLOCK_DEADLINE_SECONDS
            and (
                (len(players) <= 1 and not self._later_round_follows(state))
                or (self._strategy_mode(rules, players) == STRATEGY_VERSUS_2
                    and state.get("moves") == 1)
            )
        )
        (lookahead_candidates, lookahead_depth, lookahead_beam), _kind = (
            self._lookahead_for_state(state)
        )
        strategy_mode = self._strategy_mode(rules, players)
        opponent_booster, opponent_colors, opponent_moves = None, (), None
        if (strategy_mode == STRATEGY_VERSUS_2 and len(players) == 2
                and me.get("player_type") == PLAYER_TYPE_LOCAL):
            opponent = next(player for player in players if player is not me)
            energy = opponent.get("energy")
            capacity = opponent.get("energy_to_ability")
            if type(energy) is int and type(capacity) is int and 0 <= energy <= capacity and capacity > 0:
                opponent_booster = BoosterState(energy, capacity, "memory")
            opponent_colors = tuple(sorted({
                color for value in opponent.get("energy_colors") or ()
                if (color := board_source.slot_color_to_board(value)) not in (None, EMPTY)
            }))
            if rules.get("both_colors_charge_energy"):
                opponent_colors = tuple(sorted(set(opponent_colors) | {BLUE, RED}))
            moves_per_turn = rules.get("moves_per_turn")
            if type(moves_per_turn) is int and moves_per_turn > 0:
                opponent_moves = moves_per_turn

        request = CheckBestMoveRequest(
            mode=self._effective_mode(state),
            special_piece_mode=recognition.SPECIAL_PIECE_MODE_AUTO,
            selected_profile=board_profile,
            # The board comes from memory, so the screen templates are never
            # used. The request default (OFF) reloaded all of them whenever the
            # tile size changed, and a minimized BlueStacks (2 px tiles) turned
            # that into 450 cv::resize failures in 14 s (2026-09-18 21:38).
            ml_recognition_mode=ML_RECOGNITION_ONLY,
            # The engine's own rules, instead of checkboxes the user would have
            # to keep in sync with the mode they are playing.
            allow_square_matches=bool(rules.get("is_square_match")),
            specials_explode_immediately=bool(rules.get("specials_auto_explode"))
            or MUTATION_SPECIALS_AUTO_EXPLODE in mutation_types,
            score_rally_values=(
                dict(self._score_legend)
                if getattr(self, "_score_legend", None)
                else None
            ),
            selected_perks=selected_perks,
            perk_slot_status=self._perk_slot_status(
                low_on_time=low_on_time, burning_moves=burning_moves
            ),
            # Not now: this request is often built speculatively, long before
            # the click that plays it. The runtime reads the cursor right
            # before the first click instead.
            cursor_return_position=None,
            booster_action_mode=self._booster_action,
            force_no_booster=hold_booster,
            booster_clock_deadline=booster_clock_deadline,
            refill_input_started=self._note_refill_input,
            activate_booster_immediately=(
                self.BoosterImmediateCheck.isChecked() and not hold_booster
            ),
            # Booster rush only in the true Solo Challenge. Showdown, Party and
            # the other timed solo boards are point races and play points
            # first, the lotus included (player, 2026-11-07: "prebaci na poene").
            showdown_booster_rush=self.BlueRushCheck.isChecked() and solo_challenge,
            # Blue-hoarding policies (disco blue-first) only in the true Solo
            # Challenge; Showdown/Party/Master-League solo boards play points.
            solo_challenge=solo_challenge,
            solo_goal_state=(
                goal_from_snapshot(snapshot, (self._exact_reader.static or {}).get("rules"))
                if solo_challenge else None
            ),
            solo_cross_only=action == "solo_cross",
            solo_cross_report=(
                functools.partial(self._move_signals.solo_cross.emit, self._solo_cross_key(snapshot))
                if solo_challenge else None
            ),
            single_player_board=(
                None
                if state.get("is_singleplayer_board") is None
                else bool(state.get("is_singleplayer_board"))
            ),
            mixy_meow_state=self._memory_mixy_state(me),
            ufo_state=self._memory_ufo_state(me),
            **self._charge_scale(me, snapshot),
            remaining_moves=state.get("moves"),
            # Turn clock for the time-bound turn rule (TIME_BOUND_TURNS): the
            # seconds left and the measured wall time per move on this board.
            turn_time_left=turn_time_left,
            seconds_per_move=self._seconds_per_move(rules, players),
            total_rounds=state.get("rounds_total"),
            current_round=self._contract_round(state),
            turns_left_in_match=state.get("turns"),
            opponent_booster=opponent_booster,
            opponent_charge_colors=opponent_colors,
            opponent_next_turn_moves=opponent_moves,
            round_source="memory",
            action=engine_action,
            display_label=display_label,
            include_future_value=include_future_value,
            extra_move_only=extra_only,
            points_only=points_only,
            worst_move=burning_moves,
            lookahead_candidates=lookahead_candidates,
            lookahead_depth=lookahead_depth,
            lookahead_beam_width=lookahead_beam,
            # The snapshot is the board; no pixel scan, no score/booster OCR.
            pre_scanned_board=copy.deepcopy(snapshot.get("board")),
            pre_scanned_special_board=copy.deepcopy(snapshot.get("special_board")),
            # Mutation Lab hands out several of these as *mutations* rather
            # than rules, and then the rule field stays false for the whole
            # match -- a Vertical Matches Destroy Color pick was played on
            # 2026-08-19 with the bot simulating plain matches throughout.
            vertical_matches_destroy_color=bool(
                rules.get("vertical_match_destroy_color")
            )
            or MUTATION_VERTICAL_MATCH_DESTROY_COLOR in mutation_types,
            # Its unrestricted twin: every direct match takes its whole colour
            # off the board, not only the ones with a vertical run.
            matches_destroy_color=MUTATION_MATCHES_DESTROY_COLOR in mutation_types,
            # Energized: the extra charging colours the engine reports for us,
            # blue excluded because blue always charges. bothColorsChargeEnergy
            # ("Both Red & Blue pieces charge your booster") is folded in here:
            # it is the same statement -- one more non-blue charge colour.
            energized_colors=self._charge_colors(
                me, rules, self._mutation_charge_colors(snapshot)
            ),
            # The engine's own charge table; when present it replaces the
            # blue+energized model outright. Energized's energyColors never
            # lists blue, and blue really does not charge there -- the
            # energized_colors above then only serve as the fallback.
            engine_charge_colors=self._engine_charge_colors(me, snapshot),
            # MatchRulesModel.allSpecialsLightning.
            all_specials_lightning=bool(rules.get("all_specials_lightning")),
            extra_move_enabled=rules.get("extra_move_enabled"),
            extra_move_bonus_time=bonus_time,
            special_combo_score_multiplier=rules.get("special_combo_score_multiplier"),
            # This modifier can coexist with Candy World and other named board
            # modes, so it travels independently of the single mode enum.
            every_match_is_special=self._every_match_is_special(rules)
            or MUTATION_MATCHES_CREATE_SPECIALS in mutation_types,
            # The booster's temporary specials (SlotModel.status & 1): EndTurn
            # turns the leftovers into plain pieces before the opponent moves.
            ability_temp_special_cells=self._ability_temp_special_cells(snapshot),
            # MatchRulesModel.destroyRowOnHorizontalMatch / ...ColumnOnVertical.
            line_destruction=(
                bool(rules.get("destroy_row_on_horizontal_match"))
                or MUTATION_DESTROY_ROW_ON_HORIZONTAL_MATCH in mutation_types,
                bool(rules.get("destroy_column_on_vertical_match"))
                or MUTATION_DESTROY_COLUMN_ON_VERTICAL_MATCH in mutation_types,
            ),
            screen_state_read=self._memory_score_state(state, players, me),
            # Multiplier mushrooms apply in any mode, so the board decides:
            # a mushroom piece on it means the multipliers are live.
            mushroom_multipliers=self._board_has_mushroom(snapshot),
            # The Floor Is Lava: the engine's own per-column counter, so the
            # bot never has to infer which columns are one match from erupting.
            floor_lava_columns=self._floor_lava_columns(snapshot),
            # The jelly overlay has no slot of its own; JellySE stores the
            # infected cells on the board's extraData, so memory names them
            # exactly instead of the screen path inferring them from a washed
            # out saturation drop.
            jelly_zone_cells=self._jelly_zone_cells(snapshot),
            # Funky Tiles: the marked cells, off CellModel.cellType.
            funky_tile_cells=self._funky_tile_cells(snapshot),
            # Vegas Views: the tile and its multiplier, off CellModel.cellType
            # and the board's extraData.
            vegas_views_state=self._vegas_views_state(snapshot),
            # Debug-only: the keys, the engine's own points and the raw
            # dictionary, written to move.json so a jelly match is checkable
            # afterwards with nothing running but the game.
            jelly_debug=self._jelly_debug(snapshot),
            # Lights Up: which column is lit and what the multiplier already
            # is, so a combo that touches it is priced by what it actually
            # buys for the rest of the match.
            lights_up_state=self._lights_up_scored_state(snapshot, me),
            # Column Mania: the live per-column multipliers, so a move is
            # scored on what its cells are actually worth instead of a ramp.
            column_mania_state=self._column_mania_request_state(snapshot),
            score_multiplier_state=self._score_multiplier_request_state(snapshot),
            # Color Climb: the two colours whose combos raise our multiplier.
            color_climb_state=self._color_climb_request_state(snapshot, me),
            # HotColorBoard carries the next move's colour too, so the
            # lookahead stops scoring future plies with today's hot colour.
            hot_color_state=self._hot_color_state(snapshot),
            # Froggy Fu only ever pulls pieces inside its gather region, so the
            # lotus bonus stops counting the whole board.
            froggy_gather_region=self._froggy_gather_region(me),
            # PlayerModel.isAbilityUsedThisMove: a move that also spends the
            # booster gets no Floor Is Lava mark and no Vertical Rush
            # multiplier change, because the board model returns first.
            ability_used_this_move=self._logged_ability_used(me, snapshot),
            booster_used_this_move=bool((me or {}).get("is_ability_used_this_move")),
            strategy_mode=strategy_mode,
            # MatchRulesModel.pvpMode decides how many tiles a Sweep SE broom
            # repaints: Solo none, PvP 0-1, Rumble 2-3.
            sweep_paint_pvp_mode=rules.get("pvp_mode"),
            board_source=BOARD_SOURCE_MEMORY,
            # Perk verification polls the board between clicks; from memory
            # that costs milliseconds instead of a full screen scan each time.
            board_frame_provider=self._memory_board_frame,
            fresh_screen_state_provider=self._memory_current_score_state,
            # Every match is recorded, always. The move/candidates/observed-delta
            # JSON is what the scoring weights are calibrated from, and a match
            # played with it off is simply lost -- which is what happened to the
            # 2026-08-23 14:47 Purple Gem match: the checkbox does not persist, so
            # the restart that picked up the gem fix also silently stopped the
            # recording. The checkbox now buys only the expensive extras.
            debug_enabled=True,
            debug_images_enabled=self.DebugCheck.isChecked(),
            allow_perk_activation=any(
                perk != runtime.PERK_NONE for perk in selected_perks
            ),
            manual_recognition_stability_enabled=False,
        )
        signature = snapshot.get("signature")
        if prepare_ahead:
            plan = AutoPlan(
                self._auto_plan_key(snapshot), armed=armed, action=action,
                on_computed=self._move_signals.computed.emit,
            )
            plan.action_label = display_label
            self._auto_plan = plan
            request = replace(
                request, wait_for_board=plan.wait_until_ready,
                claim_execution=plan.claim_execution,
                planning_is_cancelled=plan.is_cancelled,
            )
            self._update_auto_plan()
        # A previous action's recording window must not swallow this one's
        # frames -- with moves every ~5 s the windows used to overlap, and the
        # new action's frames landed in the previous run's file.
        self._frame_sink = None
        self._frames_since_action = []
        self._action_started_at = time.monotonic()
        self._move_running = True
        self._set_actions_enabled(True)
        if prepare_ahead and not armed:
            self._set_calc_status(
                f"computing ahead ({display_label}) for board {signature}"
            )
            self.statusBar().showMessage(f"Computing ahead: {display_label}")
        else:
            self._set_calc_status(f"computing ({display_label}) - playing when done")
            self.statusBar().showMessage(
                "Auto: computing during animation..." if self._auto_action() is not None
                else f"{request.display_label}..."
            )

        # Swap Freely: rearrange the board with free swaps before the paid
        # move. Only the ordinary "Best Move" plays them, never on a low clock.
        free_ctx = None
        if (action == "best_move" and not low_on_time
                and free_swap.free_swaps_active(rules)):
            free_ctx = {
                "board": copy.deepcopy(snapshot.get("board")),
                "special": copy.deepcopy(snapshot.get("special_board")),
                "moves": state.get("moves"), "turn": state.get("current_turn"),
                "square": bool(rules.get("is_square_match")),
                "values": free_swap.color_values_from_snapshot(snapshot, self._score_legend),
                "multiplier_colors": (request.color_climb_state or {}).get("colors") or (),
                "extra": rules.get("extra_move_enabled"),
                "time_left": turn_time_left,
                "seconds_per_move": self._seconds_per_move(rules, players),
            }
        # Outside the Solo Challenge: ranked during the animation, the exact
        # refill only re-checks the top moves once the board is at rest.
        fast_refill = self._fast_refill(state)
        solo_goal = SoloGoalState.from_payload(request.solo_goal_state)
        active_solo_goal = solo_goal is not None and not solo_goal.complete
        square_live = (
            self._square_live
            if self._refill_on and not fast_refill and self._exact_plan_enabled(rules)
            and not active_solo_goal
            and square_solo_live.eligible(rules)
            and self._reader_script is not None and action == "best_move"
            else None
        )
        script = self._reader_script
        refill_on = self._refill_on
        # Solo Challenge, exact refill on, Teleport equipped, unspent and
        # perks enabled: it goes on this move, the exact plans pick its pair.
        teleport_pair_wanted = (
            refill_on and not fast_refill and action == "best_move"
            and not active_solo_goal
            and self._is_solo_challenge(state)
            and any(entry.get("perk") == runtime.PERK_TELEPORT and entry.get("reason") == "available"
                    for entry in self._perk_slot_status())
        )

        def worker():
            nonlocal request
            free_final = None
            if free_ctx is not None:
                try:
                    swap, note, free_final = self._free_swap_step(free_ctx)
                except Exception as exc:
                    swap, note = None, f"preskacem ({type(exc).__name__}: {exc})"
                if note:
                    self._reader_signals.status.emit(f"Slobodne zamene: {note}")
                if swap is not None:
                    try:
                        result = runtime.run_free_swap_request(request, swap, note)
                        if not getattr(result, "planning_cancelled", False):
                            self._free_swap_guard.played(free_ctx["board"], free_ctx["moves"], swap)
                    except BaseException as exc:
                        traceback.print_exc()
                        self._move_signals.done.emit(None, f"{type(exc).__name__}: {exc}")
                        return
                    self._move_signals.done.emit(result, signature or "")
                    return
                if free_final is not None:
                    request = replace(request, engine_plan_move=free_final)
            if square_live is not None and free_final is None:
                request = self._with_square_plan(
                    request, square_live, script, snapshot, turn_time_left
                )
            cleo_profile = None
            if script is not None:
                cleo_profile = square_solo_live.cleo_odds_profile(self._exact_reader, script, snapshot)
            self._remember_cleo_profile(snapshot, cleo_profile)
            session, no_refill = None, "potez se ne racuna iz memorije"
            late = None
            if not refill_on:
                no_refill = "iskljuceno prekidacem"
            elif fast_refill and script is not None:
                late = {"session": None, "reason": "bot nije stigao do izbora poteza"}
                planned_board = request.pre_scanned_board

                def late_exact_refill():
                    late["session"], late["reason"] = self._late_exact_refill(
                        script, snapshot, planned_board)
                    return late["session"]

                def exact_refill_skip(reason):
                    late["reason"] = reason

                request = replace(request, late_exact_refill=late_exact_refill,
                                  exact_refill_skip=exact_refill_skip)
            elif script is not None:
                session, no_refill = square_solo_live.exact_refill_session(
                    self._exact_reader, script, snapshot, request.pre_scanned_board,
                    **({"validate_solo_state": True} if solo_challenge else {}),
                )
                if teleport_pair_wanted and session is not None:
                    try:
                        chosen = square_solo_live.teleport_exact_pair(self._exact_reader, script, snapshot)
                    except Exception as exc:  # The bot's own Teleport pick stays.
                        chosen = {"pair": None, "note": f"greska {type(exc).__name__}: {exc}"}
                    self._reader_signals.status.emit(f"Teleport (tacna dopuna): {chosen['note']}")
                    if chosen["pair"] is not None:
                        request = replace(request, teleport_exact_pair=chosen["pair"])
            if late is not None:
                usage = {"reported": False}
            else:
                request, usage = self._report_when_computed(request, session, no_refill)
            try:
                with exact_refill_active(session), cleo_odds_active(
                    {"profile": cleo_profile} if cleo_profile else None
                ):
                    result = run_check_best_move_request(request)
                if late is not None:
                    session, no_refill = late["session"], late["reason"]
                if not usage["reported"] and not getattr(result, "planning_cancelled", False):
                    self._report_exact_refill(session, no_refill)
            except BaseException as exc:
                # BaseException, not Exception: a SystemExit here (a stray
                # exit() deep in a helper) used to end the thread without
                # `done`, leaving _move_running True and Auto hung for good.
                # The full traceback goes to the console log, and the raising
                # line into the GUI message: the bare cv::resize text of
                # 2026-09-18 never said which call failed.
                traceback.print_exc()
                frames = traceback.extract_tb(exc.__traceback__)
                where = (
                    f" [{Path(frames[-1].filename).name}:{frames[-1].lineno}]"
                    if frames else ""
                )
                message = " ".join(str(exc).split())
                self._move_signals.done.emit(
                    None, f"{type(exc).__name__}: {message}{where}"
                )
                return
            self._move_signals.done.emit(result, signature or "")

        threading.Thread(target=worker, daemon=True).start()

    def _on_research_toggled(self, checked: bool) -> None:
        self._research_on = checked
        if checked:
            # A new folder: the analyzer compares neighbouring files, and moves
            # missed while the toggle was off would look like wrong predictions.
            self._research.reset()
            self._research_signature = None

    def _record_research(self, script, snapshot) -> None:
        """Watcher thread: the move never waits for this, with the toggle on or off."""
        try:
            self._research.record(script, snapshot, enabled=lambda: self._research_on,
                                  resting_trigger=True, input_marker=lambda: self._refill_input,
                                  single_profile=self._fast_refill(snapshot.get("state") or {}))
        except Exception as exc:
            self._reader_signals.status.emit(f"Istrazivanje: snimak preskocen ({exc})")

    def _on_board_captured(self, entry, missed_board) -> None:
        if self._refill_on:
            self._refill_monitor.send(entry, missed_board)

    def _note_refill_input(self, action, detail=None) -> None:
        # (count, action, detail): detail is the bot's own swipe or perk
        # (runtime.refill_input_detail), saved with every board so a refill
        # miss can be replayed with the move that was really played.
        self._refill_input = (self._refill_input[0] + 1, action, detail)
        if action != "move":
            # The exact Solo planner predicted its swap; a booster or perk the
            # bot plays instead is not a model miss. Color Crush 2026-11-10
            # 06:10:44: the UFO read as one and the planner went off for the
            # rest of the match.
            square_live = getattr(self, "_square_live", None)
            if square_live is not None:
                square_live.expectation = None

    def _on_refill_master_toggled(self, checked: bool) -> None:
        self._refill_on = checked
        # The check process compares neighbouring boards; boards skipped while
        # off must not read as one long wrong move.
        self._refill_monitor.reset()
        self._log(f"Dopuna: {'ukljucena' if checked else 'iskljucena'}")
        self._refresh_refill_panel()

    def _is_solo_challenge(self, state) -> bool:
        return (bool(state.get("is_singleplayer_board"))
                and len(state.get("players") or []) <= 1
                and self._relaxed_turn_clock(state.get("rules") or {}))

    def _apply_adb_swipe(self) -> None:
        """UI thread: start or stop the BlueStacks touch swipe."""
        previous, runtime.ADB_TOUCH = runtime.ADB_TOUCH, None
        if previous is not None:
            previous.close()
        device = getattr(self, "_adb_device", None)
        if not self.AdbSwipeCheck.isChecked():
            self._log("Swipe: misem")
            return
        if device is None:
            self._log("Swipe kroz BlueStacks: ceka vezu sa igrom, do tad misem")
            return
        import adb_touch
        runtime.ADB_TOUCH = adb_touch.AdbTouch(*device)
        self._log(f"Swipe kroz BlueStacks: ukljucen ({device[1]})")

    def _full_exact_refill(self, state) -> bool:
        """Timed races overlap preliminary ranking with the animation."""
        if self._is_solo_challenge(state):
            return True
        rules = state.get("rules") or {}
        if rules.get("pvp_mode") == PVP_MODE_RUMBLE:
            return False
        if FULL_EXACT_REFILL_EVERYWHERE:
            return True
        players = state.get("players") or []
        return (len(players) == 2
                and self._strategy_mode(rules, players) == STRATEGY_VERSUS_2)

    def _fast_refill(self, state) -> bool:
        """Refill on outside the full exact modes: the clock comes first."""
        return self._refill_on and not self._full_exact_refill(state)

    def _wait_resting_snapshot(self, planned, timeout=LATE_REFILL_SETTLE_SECONDS):
        """The newest snapshot, given up to ``timeout`` to come to rest on the planned board.

        The fast plan is ready when the game opens its move phase, but the
        newest dump could still be one the agent had not yet called stable:
        the refill then gave up with "tabla jos nije mirna" and the move went
        without it (7 swipes in the 2026-11-11/12 log, e.g. 23:17:11, 23:17:25).
        """
        deadline = time.monotonic() + timeout
        while True:
            latest = self._snapshot
            if latest is None or not _same_planned_board(latest, planned):
                return latest
            state = latest.get("state") or {}
            if (latest.get("stable", True) and not state.get("chain_reaction")
                    and state.get("game_state") in (None, square_solo_live.WAITING_FOR_INPUT)):
                return latest
            if time.monotonic() >= deadline:
                return latest
            self._request_dump()
            time.sleep(0.03)

    def _late_exact_refill(self, script, planned, board):
        """Worker thread, once the board is ready: (session, reason) for the
        settled board the fast plan was computed on, or None if it changed."""
        latest = self._wait_resting_snapshot(planned)
        if latest is None or not _same_planned_board(latest, planned):
            return None, "tabla se promenila pre provere"
        state = latest.get("state") or {}
        strategy = self._strategy_mode(state.get("rules") or {}, state.get("players") or [])
        max_plies = (VERSUS_REFILL_FOLLOWED_PLIES if strategy == STRATEGY_VERSUS_2
                     else FAST_REFILL_FOLLOWED_PLIES)
        profile = self._research.matching_profile(script, latest, self._refill_input)
        if profile is None:
            # The watcher's read is lost when Auto plays first (research off):
            # read the resting profile here and hand the same board to the
            # refill check (ResearchRecorder.capture_resting).
            profile, reason = square_solo_live._resting_profile(self._exact_reader, script, latest)
            if profile is None:
                return None, reason
            if self._refill_on:
                try:
                    self._research.capture_resting(latest, profile, self._refill_input)
                except Exception as exc:  # The check never costs the move.
                    print(f"refill check: resting capture failed: {type(exc).__name__}: {exc}")
        return square_solo_live.exact_refill_session(
            self._exact_reader, script, latest, board, max_plies=max_plies, resting_profile=profile)

    def _prepares_ahead(self, state) -> bool:
        """May the move be computed before the engine opens its input phase?

        Not while the exact refill is on, in any mode: the RNG is only read at
        rest, and the finished plan has the same key as the settled board, so a
        move computed early was played without knowing what falls.

        Except in Showdown and Party (_full_exact_refill is False): there the
        clock matters more than the drop, and waiting for rest put the bot
        behind the others in Showdown (player, 2026-11-07). The move there is
        computed during the animation without the exact refill.
        """
        return not self._refill_on or not self._full_exact_refill(state)

    def _waits_for_settled_board(self, snapshot) -> bool:
        """The same rule for the computation that runs with Auto off."""
        settled = bool(snapshot.get("stable")) and self._engine_move_phase_open(snapshot)
        return not settled and not (self._prepares_ahead(snapshot.get("state") or {})
                                    and not self._cleo_needs_rest(snapshot))

    def _cleo_needs_rest(self, snapshot) -> bool:
        """A Cleo figure's odds come from memory read at rest (use counter,
        Solo prevent list, booster amounts). Planned mid-animation the ranking
        fell back to PvP values: 84% where the game's own gave 49% on the same
        board (2026-11-07 17:21). So a board with Cleo is planned once settled.
        """
        return self._reader_script is not None and any(
            SPECIAL_CLEO_BUG in row for row in snapshot.get("special_board") or ())

    @staticmethod
    def _exact_plan_enabled(rules) -> bool:
        return bool((SQUARE_SOLO_EXACT_PLAN and rules.get("id") == "square-match")
                    or (COLOR_CRUSH_SOLO_EXACT_PLAN and rules.get("id") == "color-crush")
                    or (RAINBOW_EXACT_PLAN and rules.get("id") == "rainbow"))

    def _remember_cleo_profile(self, snapshot, profile):
        """Give the odds readout the values the ranking is using for this board.

        Runs on the move worker. Snapshots only arrive when the board changes,
        and by then this profile would be stale, so the panel is told directly.
        """
        try:
            special = tuple(tuple(int(v) for v in row) for row in snapshot.get("special_board") or ())
        except (TypeError, ValueError):
            special = None
        self._cleo_profile = (special, profile)
        if profile is not None:
            self._move_signals.cleo_values.emit()

    def _redraw_cleo_odds(self):
        """UI thread: draw the panel again with the values just read."""
        if self._cleo_render_args is None:
            return
        self._cleo_odds_key = None
        self._render_cleo_odds(*self._cleo_render_args)

    def _report_when_computed(self, request, session, reason):
        """Report the moment the search is done, not when the held move is played.

        With Auto off the worker holds a finished move until a click, and a
        cancelled search never gets here, so it reports nothing at all.
        """
        usage = {"reported": False}
        wait = request.wait_for_board
        if wait is None:
            return request, usage

        def report_then_wait():
            # A board still moving is usually re-planned once it settles (the
            # wait cancels this search): reported now it counted a move that
            # was never played as "without the refill" (Hot Color 2026-11-12
            # 00:55:21, after a booster; the move played at 00:55:26 had it).
            # Such a search reports only if its move is really played.
            if not (session is None and reason in UNSETTLED_REFILL_REASONS):
                usage["reported"] = True
                self._report_exact_refill(session, reason)
            return wait()

        return replace(request, wait_for_board=report_then_wait), usage

    def _report_exact_refill(self, session, reason) -> None:
        """Worker thread: did this move's ranking actually see the drop?"""
        # engine_refill.APPROXIMATE_REFILL: a drop guessed from the live RNG
        # where the exact port stops counts as working, and says so.
        used = (getattr(session, "successful", 0) or 0) + (getattr(session, "approximated", 0) or 0)
        # A reason already given (booster, perk...) stands: the session there
        # only read the board for the refill check (runtime, before a booster).
        if reason:
            pass
        elif session is not None and session.failure and not used:
            reason = f"dopuna nije uspela: {session.failure}"
        elif session is not None and not session.simulations:
            reason = "bot nije rangirao poteze na ovoj tabli"
        elif session is not None and not used:
            reason = "kandidati imaju nepredvidiv ili neprenet efekat"
        approximate = (getattr(session, "approximation", None)
                       if session is not None and getattr(session, "approximated", 0) else None)
        self._reader_signals.refill.emit({"usage": {
            "active": session is not None and not reason, "reason": reason,
            "approximate": approximate}})

    def _on_refill_answer(self, answer) -> None:
        if not self._refill_on:
            return  # An answer still on its way when the master went off.
        line = self._refill_tally.add(answer)
        if answer.get("usage"):
            self._log(self._refill_tally.usage_text())
        if line is not None:
            self.RefillLog.appendPlainText(f"{time.strftime('%H:%M:%S')}  {line}")
            self._log(f"Dopuna: {line}; {self._refill_tally.hit_text()}; {self._refill_tally.usage_text()}")
        self._refresh_refill_panel()

    def _refresh_refill_panel(self) -> None:
        if not self._refill_on:
            self.RefillUseLabel.setText("Dopuna: ISKLJUCENA prekidacem")
            self.RefillDataLabel.setText("Podaci: ne citaju se")
            self.RefillHitLabel.setText("Pogadja: provera je iskljucena")
            return
        self.RefillUseLabel.setText(self._refill_tally.usage_text())
        self.RefillDataLabel.setText(self._refill_tally.data_text())
        self.RefillHitLabel.setText(self._refill_tally.hit_text())

    def _watch_research_board(self, *_) -> None:
        """Read each new resting board, whoever played the move before it.

        Runs with the toggle off too: the refill check needs the boards, the
        toggle only decides whether they are saved.
        """
        snapshot = self._snapshot
        script = self._reader_script
        if (not (self._refill_on or self._research_on) or self._research_busy
                or snapshot is None or script is None):
            return
        state = snapshot.get("state") or {}
        signature = snapshot.get("signature")
        if (signature is None or signature == self._research_signature
                or state.get("game_state") != -5 or state.get("chain_reaction")):
            return
        self._research_signature = signature
        self._research_busy = True

        def worker():
            try:
                self._record_research(script, snapshot)
            finally:
                self._research_done_signature = signature
                self._research_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _free_swap_step(self, ctx):
        """Worker thread: (free swap to play, status note, paid swap to promote).

        The plan is kept between swaps and continued while every board is the
        one it expects; any other board is planned again.
        """
        guard = self._free_swap_guard
        board = ctx["board"]
        reason = guard.observe(board, ctx["moves"], ctx["turn"])
        if reason:
            return None, f"iskljucene ({reason})", None
        budget = min(
            guard.allowed(),
            free_swap.affordable_free_swaps(ctx["time_left"], ctx["moves"], ctx["seconds_per_move"]),
        )
        swap = guard.next_swap(board, max_swaps=budget)
        if swap is not None:
            left = len(guard._plan_rest)
            return swap, f"plan: jos {left} zamena do poteza vrednog {guard.plan.value:.0f}", None
        final = guard.final_move(board)
        if final is not None:
            return None, f"plan gotov, igram potez vredan {guard.plan.value:.0f}", final
        if budget <= 0:
            return None, "nema vremena/limit, igram obican potez", None
        time_left = ctx["time_left"]
        plan = free_swap.plan_free_swaps(
            board, ctx["special"], allow_square_matches=ctx["square"],
            color_values=ctx["values"], extra_move_enabled=ctx["extra"],
            multiplier_colors=ctx["multiplier_colors"],
            max_swaps=budget,
            time_budget=free_swap.TIME_BUDGET_SECONDS if time_left is None or time_left > 60 else 1.0,
        )
        if not plan.swaps:
            return None, plan.note or "bez boljeg plana, igram obican potez", None
        guard.keep(board, plan)
        return (plan.swaps[0],
                f"novi plan: {len(plan.swaps)} zamena, potez {plan.baseline:.0f} -> {plan.value:.0f}",
                None)

    def _with_square_plan(self, request, square_live, script, snapshot, turn_time_left):
        """Worker thread: put the exact-refill planner's swap into the request.

        Any failure leaves the request as it was -- the bot then plays its own
        ranking, exactly as without the planner.
        """
        report = self._reader_signals.status.emit
        try:
            outcome = square_live.plan(script, snapshot, turn_time_left=turn_time_left)
        except Exception as exc:
            report(f"Exact Solo planer: preskacem ({type(exc).__name__}: {exc})")
            return request
        for line in outcome["log"]:
            report(f"Exact Solo planer: {line}")
        if outcome["move"] is None:
            report(f"Exact Solo planer: {outcome['note']}")
            return request
        move = outcome["move"]
        return replace(request, engine_plan_move=(move["start"], move["target"]))

    @guarded_slot
    def _on_move_done(self, result, signature_or_error):
        self._move_running = False
        prepared = self._auto_plan is not None
        self._auto_plan = None
        self._set_actions_enabled(self._reader_session is not None)
        if result is not None and (result.planning_cancelled or (prepared and result.waiting_for_board)):
            # A discarded computation never played this board and must not set
            # the duplicate-swipe latch or spend perk/UFO bookkeeping.
            requested = self._requested_action
            if not self._match_active:
                # The match ended under the plan: nothing is recomputed, the
                # reader is waiting for the next match. Saying "racunam
                # ponovo" here read as a stuck reader (2026-09-15 09:45).
                self._set_calc_status("match ended - waiting for next")
                self.statusBar().showMessage("Reader active — waiting for match")
                return
            if requested is not None and self._auto_action() is None:
                self._set_calc_status(
                    f"recomputing ({self._ACTION_LABELS[requested]}) - "
                    "playing when the game allows"
                )
            else:
                self._set_calc_status(
                    "cancelled (board changed or wasn't ready) - recomputing"
                )
            self.statusBar().showMessage("Waiting for new board / recomputing")
            # The tick restarts the standing request (or the speculative plan).
            QtCore.QTimer.singleShot(0, self._auto_tick)
            return
        self._requested_action = None
        if result is None:
            self._set_calc_status(f"error: {signature_or_error}")
            self._note_move_failure(signature_or_error)
            if "Calibration" in signature_or_error or "kalibris" in signature_or_error:
                # Board geometry is per BlueStacks layout and has nothing to do
                # with the memory snapshot; Auto would just keep failing.
                self._stop_auto()
                self._log("Click 'Calibrate' — swipe doesn't know where the board is.")
            self.statusBar().showMessage("Move error")
            return
        self._clear_move_failures()
        self._last_played_signature = signature_or_error or None
        self._last_played_at = time.monotonic()
        # Only a swap moves the lit column (a booster or perk does not), and
        # it moves it only once the cascades are over.
        if (result.turn_consumed and not result.booster_attempt
                and result.perk_attempted_slot is None
                and self._lights_up_play_column is not None):
            self._lights_up_stale_column = self._lights_up_play_column
        if result.clear_used_perk_slot is not None:
            self._used_perk_slots.add(int(result.clear_used_perk_slot))
            self._used_perk_slot_sources.setdefault(int(result.clear_used_perk_slot), "bot")
            self._perk_pending_confirmation = None
        elif result.clear_used_perk_key is not None:
            for index, key in enumerate(self._perk_keys[:2]):
                if key == result.clear_used_perk_key:
                    self._used_perk_slots.add(index + 1)
                    self._used_perk_slot_sources.setdefault(index + 1, "bot")
                    break
            self._perk_pending_confirmation = None
        elif getattr(result, "perk_attempted_slot", None) is not None:
            self._perk_pending_confirmation = (
                int(result.perk_attempted_slot), self._turn_clock_key
            )
            self._log(
                f"Perk u slotu {result.perk_attempted_slot}: potrosnja nije "
                "potvrdjena; drugi perk ceka potvrdu iz memorije ili novi red."
            )
        if result.turn_consumed and not result.booster_attempt:
            self._ufo_tracker.on_move_played(result.ufo_abductions)
        note = "  [booster]" if result.booster_attempt else ""
        self._log(f"{result.best_move_text}  |  {result.score_text}{note}")
        latest_run = self._latest_debug_run()
        if latest_run is not None:
            # A promised extra that never arrived is read out of the observed
            # delta, which the always-on JSON run carries; only the frame trace
            # needs the checkbox.
            self._report_broken_promise(latest_run)
            if self.DebugCheck.isChecked():
                self._log(f"Debug recording (full, with images): {latest_run}")
                self._start_frame_capture(latest_run)
        self.statusBar().showMessage(result.best_move_text)
        self._set_calc_status(f"played: {result.best_move_text}")
        # With Auto on this plays the next board; with Auto off it starts
        # computing the next board so the next click has a move waiting.
        QtCore.QTimer.singleShot(0, self._auto_tick)

    def _report_broken_promise(self, run_path):
        """Say it in the log when the previous move's extra never arrived.

        This run closes the previous one's observed delta, and that delta now
        carries the move counter from memory on both ends -- so a promised
        extra that the game did not grant is a fact, not an impression.
        """
        try:
            move = json.loads(
                (Path(run_path) / "move.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return
        previous = move.get("previous_run")
        delta_path = Path(run_path).parent / str(previous) / "observed_delta.json"
        if not previous or not delta_path.exists():
            return
        try:
            check = json.loads(delta_path.read_text(encoding="utf-8")).get(
                "prediction_check"
            ) or {}
        except (OSError, ValueError):
            return
        try:
            cleo_check = json.loads(delta_path.read_text(encoding="utf-8")).get(
                "cleo_check"
            )
        except (OSError, ValueError):
            cleo_check = None
        if cleo_check and previous not in self._cleo_checked_runs:
            self._cleo_checked_runs.add(previous)
            name = COLOR_NAMES.get(cleo_check.get("actual_color"), "?")
            predicted = cleo_check.get("predicted_extra_for_actual_color")
            kept = cleo_check.get("observed_kept_the_turn")
            verdict = str(cleo_check.get("verdict", "nepoznato"))
            reason = cleo_check.get("reason") or ""
            self._cleo_tally[verdict] = self._cleo_tally.get(verdict, 0) + 1
            line = (
                f"color {name}, simulation "
                f"{'extra' if predicted else 'no extra' if predicted is False else '?'}, "
                f"game {'kept the turn' if kept else 'lost the turn' if kept is False else '?'}"
                f" -> {verdict.upper()}" + (f" ({reason})" if reason else "")
            )
            self._log(f"Cleo ({previous}): {line}")
            self.CleoVerdictLabel.setText(
                f"Last Cleo: {line}<br>This session: correct "
                f"{self._cleo_tally.get('pogodio', 0)}, incorrect "
                f"{self._cleo_tally.get('promasio', 0)}, unknown "
                f"{self._cleo_tally.get('nepoznato', 0)}"
            )
            self.CleoVerdictLabel.show()
            self.CleoGroup.show()
        promised = float(check.get("predicted_extra_moves") or 0.0)
        if promised >= 1.0 and check.get("observed_kept_the_turn") is False:
            # The counter is credited only after the animations settle
            # (measured 2026-08-26 02:57: every read <=3 s after the move was
            # one short, every read >=8 s was restored). A verdict taken
            # sooner is a race, not a broken promise -- stay quiet about it.
            gap = self._run_stamp_gap_seconds(previous, Path(run_path).name)
            if gap is not None and gap < 8.0:
                return
            self._log(
                f"PAZNJA: prethodni potez ({previous}) je obecao extra, "
                "a igra ga nije dala."
            )

    @staticmethod
    def _run_stamp_gap_seconds(previous_name, current_name):
        """Seconds between two run-directory names, or None if unparseable."""
        def parse(name):
            try:
                stamp, millis = str(name).rsplit("_", 1)
                base = datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S")
                return base.timestamp() + int(millis) / 1000.0
            except (ValueError, TypeError):
                return None

        before, after = parse(previous_name), parse(current_name)
        if before is None or after is None:
            return None
        return after - before

    # ------------------------------------------------- memorijski kadrovi ---

    # Recording stops when the board has actually come to rest -- two settled
    # frames in a row that repeat the same board, and only after the action
    # moved something -- with a time and count cap for when rest never comes.
    # A fixed window alone was wrong in both directions: it cut long cascades
    # short and it stayed open into the next action.
    FRAME_CAPTURE_SECONDS = 12.0
    # Sized to the capture window rather than left far above it, so the two
    # limits say the same thing: 12 s at 30 ms is 400 frames, ~9 MB of trace on
    # a cascade that never settles. A normal cascade quiets after 1-2 s.
    FRAME_CAPTURE_LIMIT = 400
    # Quiet is a *duration*, not a frame count: at 30 ms two identical frames
    # are 60 ms, which a cascade can easily stand still for between two clears,
    # and the recording would stop in the middle of the very thing it is there
    # to catch. Derived from the poll interval so the two cannot drift apart.
    FRAME_CAPTURE_QUIET_MS = 200
    FRAME_CAPTURE_QUIET_FRAMES = max(2, -(-FRAME_CAPTURE_QUIET_MS // TRACE_POLL_MS))

    def _start_frame_capture(self, run_path):
        """Record every memory frame this action produces into its run folder.

        The settled board alone cannot say what a special or a booster did --
        by the time it arrives the refill has covered the cleared cells. The
        agent's trace mode pushes the frames in between, and each one carries
        the full board plus score, energy and the move counter, so the effect
        can be read off afterwards instead of inferred.
        """
        self._frame_sink = {
            "path": Path(run_path) / MEMORY_FRAMES_FILENAME,
            "until": time.monotonic() + self.FRAME_CAPTURE_SECONDS,
            "written": 0,
            "quiet": 0,
            "moved": False,
            "last_signature": None,
        }
        for frame in self._frames_since_action:
            self._write_frame(frame)
        self._frames_since_action = []

    def _write_frame(self, frame):
        sink = self._frame_sink
        if sink is None:
            return
        try:
            with sink["path"].open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(frame) + "\n")
        except OSError as exc:
            self._frame_sink = None
            self._log(f"Frame recording failed: {exc}")
            return
        sink["written"] += 1

        changed = (
            sink["last_signature"] is not None
            and frame.get("signature") != sink["last_signature"]
        )
        sink["moved"] = sink["moved"] or changed
        sink["last_signature"] = frame.get("signature")
        # Quiet means: settled and identical to the frame before it. Frames
        # taken while the swipe is still travelling are not quiet in that sense
        # because nothing has moved yet, hence the `moved` guard.
        sink["quiet"] = 0 if changed or not frame.get("stable") else sink["quiet"] + 1
        if sink["written"] >= self.FRAME_CAPTURE_LIMIT or (
            sink["moved"] and sink["quiet"] >= self.FRAME_CAPTURE_QUIET_FRAMES
        ):
            self._frame_sink = None

    @staticmethod
    def _compact_frame(snapshot):
        state = snapshot.get("state") or {}
        players = state.get("players") or []
        return {
            "captured_at": snapshot.get("captured_at"),
            "reason": snapshot.get("reason"),
            "stable": bool(snapshot.get("stable")),
            "signature": snapshot.get("signature"),
            "board": snapshot.get("board"),
            "special_board": snapshot.get("special_board"),
            "game_state": state.get("game_state"),
            "chain_reaction": state.get("chain_reaction"),
            "moves": state.get("moves"),
            "moves_made_this_turn": state.get("moves_made_this_turn"),
            "accumulated_move_score": state.get("accumulated_move_score"),
            "accumulated_turn_score": state.get("accumulated_turn_score"),
            "players": [
                {
                    "index": player.get("index"),
                    "score": player.get("score"),
                    "turn_score": player.get("turn_score"),
                    "energy": player.get("energy"),
                    "energy_to_ability": player.get("energy_to_ability"),
                    "active_special_ability_type": player.get(
                        "active_special_ability_type"
                    ),
                    "is_my_turn": player.get("is_my_turn"),
                }
                for player in players
            ],
            # Raw slots are what proves which piece cleared: value/status/colour
            # per cell, not just the adapted board.
            "slots": snapshot.get("slots"),
            # Froggy Fu's recorded gather (`attractionMoveData`): one entry per
            # swap the pull performed. The animation plays those out one step at
            # a time, so no frame ever shows the board the pull settles into --
            # replaying this list is the only way to reconstruct it.
            "froggy": snapshot.get("froggy"),
        }

    def _record_frame(self, snapshot):
        if not self.DebugCheck.isChecked():
            self._frame_sink = None
            self._frames_since_action = []
            return
        frame = self._compact_frame(snapshot)
        if self._frame_sink is not None:
            if time.monotonic() > self._frame_sink["until"]:
                self._frame_sink = None
            else:
                self._write_frame(frame)
                return
        # Between actions: keep the recent frames so the ones that arrive while
        # the swipe is still running are not lost before the run folder exists.
        self._frames_since_action.append(frame)
        del self._frames_since_action[: -self.FRAME_CAPTURE_LIMIT]

    def _apply_trace_mode(self, enabled=None, *, report=None):
        """Push the trace setting to the agent.

        The attach worker calls this off the Qt thread, so it passes the
        checkbox state read beforehand and a thread-safe `report` (the status
        signal): touching DebugCheck or the log widget from that thread is a
        cross-thread Qt call that can crash the window.
        """
        script = self._reader_script
        if script is None:
            return
        if enabled is None:
            enabled = self.DebugCheck.isChecked()
        report = report or self._log
        try:
            reader.set_trace(script, enabled, TRACE_POLL_MS if enabled else None)
        except Exception as exc:
            report(f"Trace mod nije prihvacen: {type(exc).__name__}: {exc}")
            return
        report(
            f"Trace mod ukljucen ({TRACE_POLL_MS} ms, snima i kaskade)"
            if enabled
            else "Trace mod iskljucen"
        )

    @staticmethod
    def _latest_debug_run():
        # The worker that just finished created the run, and runtime remembers
        # it. The directory scan below stats every run folder (15k+ of them,
        # ~0.65 s warm and seconds while the emulator loads a level) on the Qt
        # thread after every move -- it stays only as the fallback.
        created = runtime.last_created_debug_run_dir()
        if created is not None and Path(created).is_dir():
            return Path(created)
        runs = PROJECT_ROOT / "Debug" / "runs"
        try:
            directories = [path for path in runs.iterdir() if path.is_dir()]
        except OSError:
            return None
        if not directories:
            return None
        return max(directories, key=lambda path: path.stat().st_mtime)

    # -------------------------------------------------------------- auto ---

    def _auto_toggled(self, checked: bool):
        self.AutoButton.setText("Auto (running)" if checked else "Auto")
        self._log("Auto enabled" if checked else "Auto disabled")
        if checked and self.WorstAutoButton.isChecked():
            # One loop, one objective: the burner steps aside.
            self.WorstAutoButton.setChecked(False)
        self._auto_switched(checked)

    def _worst_auto_toggled(self, checked: bool):
        self.WorstAutoButton.setText(
            "Least Points Auto (running)" if checked else "Least Points Auto"
        )
        self._log(
            "Least points auto enabled — burning moves"
            if checked
            else "Least points auto disabled"
        )
        if checked and self.AutoButton.isChecked():
            self.AutoButton.setChecked(False)
        self._auto_switched(checked)

    def _auto_switched(self, checked: bool):
        """Shared tail of both auto toggles."""
        plan = self._auto_plan
        if checked:
            self._requested_action = None
            if plan is not None and not plan.executing and plan.action != self._auto_action():
                # A plan for the other objective (Auto's best move held while
                # the burner starts, or the other way round) must not be armed
                # by the tick; drop it and let the tick start the right one.
                plan.cancel()
            self._wake_agent()
            QtCore.QTimer.singleShot(0, self._auto_tick)
        elif plan is not None and not plan.executing:
            # The computation is still good; it just must not play on its own.
            plan.disarm()
            self._set_actions_enabled(self._reader_session is not None)

    def closeEvent(self, event):
        self.AutopilotPanel.stop()
        self._refill_monitor.close()
        if runtime.ADB_TOUCH is not None:
            runtime.ADB_TOUCH.close()
            runtime.ADB_TOUCH = None
        if self._auto_plan is not None:
            self._auto_plan.cancel()
        # Closing the window used to leave the agent inside the game until
        # frida-server noticed the dead connection. Unload it explicitly and
        # give the unload a moment to finish: the closing thread is a daemon
        # and process exit would otherwise kill it mid-RPC.
        self._reader_auto_retry = False
        if self._reader_script is not None or self._reader_session is not None:
            closer = self._detach_reader("prozor zatvoren")
            if closer is not None:
                closer.join(timeout=3.0)
        super().closeEvent(event)

    def _auto_plan_key(self, snapshot):
        state = (snapshot or {}).get("state") or {}
        left = self.turn_time_left(state)
        # Crossing a timing-policy boundary invalidates the old calculation,
        # but a clock that covers every move left has no boundary to cross: on
        # a 1500 s solo clock this restarted the search every 6.5 s for nothing.
        clock_budget = None if left is None else max(0, int(left / TIME_BOUND_SECONDS_PER_MOVE))
        if clock_budget is not None and clock_budget > (state.get("moves") or 0) + CLOCK_KEY_MOVE_MARGIN:
            clock_budget = None
        return snapshot_plan_key(snapshot, (
            self.BoosterImmediateCheck.isChecked(), self.BlueRushCheck.isChecked(),
            self.PerksCheck.isChecked(), sorted(self._used_perk_slots),
            self._booster_action, self._board_profile, self._score_legend,
            clock_budget, self._low_on_turn_time(state),
        ))

    def _update_auto_plan(self):
        plan = self._auto_plan
        if plan is None or plan.executing:
            return
        snapshot = self._snapshot
        if (self._reader_session is None
                or not self._match_active or snapshot is None):
            plan.cancel()
            return
        state = snapshot.get("state") or {}
        age = self.snapshot_age_seconds()
        fresh = age is not None and age <= board_source.DEFAULT_MEMORY_MAX_AGE_SECONDS
        # The turn countdown is deliberately NOT part of `ready`. This runs on
        # every 50 ms tick, and on a quiet board the agent sends nothing new,
        # so a plan started on a fresh snapshot saw `ready` flip back to False
        # 0.4 s later -- while the worker was still computing (~0.6-1 s on the
        # deep tier). Nobody asked for a fresh board in that branch, the worker
        # sat in wait_until_ready for the full 15 s, cancelled, and the next
        # attempt fell into the same hole. Started mid-animation it worked only
        # because the settled board arrived on its own and woke the wait
        # (2026-09-07). The clock was fresh when the plan started and the
        # timing policy is in the plan key; a stale clock just asks for a dump
        # so a crossed policy boundary is caught by the key comparison.
        engine_stale = self._needs_engine_read(snapshot)
        # Auto's swipe also waits for the refill/research read of this board;
        # the search itself runs meanwhile (it reads its own profile).
        ready = (fresh and bool(snapshot.get("stable"))
                 and self._engine_move_phase_open(snapshot)
                 and not engine_stale
                 and snapshot.get("signature") != self._last_played_signature
                 and not (self._auto_action() is not None
                          and self._waits_for_board_record(snapshot)))
        key = self._auto_plan_key(snapshot)
        if key != plan.key and not plan.is_cancelled():
            self._log("Racunanje ponisteno: " + ", ".join(plan_key_difference(plan.key, key)))
        plan.update(key, ready)
        if (not fresh or not snapshot.get("stable")
                or not self._turn_countdown_is_fresh(state)
                or engine_stale):
            self._request_dump()

    def _wake_agent(self):
        """Ask the agent to check whether a match is running right now.

        Only ever from a deliberate action (a move button, switching auto on).
        On its own the agent waits for the match counter to rise, because
        anything softer replays the previous match off the heap.
        """
        script = self._reader_script
        if script is None or self._match_active:
            return

        def ask():
            try:
                detail = script.exports_sync.wake() or {}
            except Exception as exc:
                self._reader_signals.status.emit(f"Match check failed: {exc}")
                return
            if detail.get("match_active"):
                if detail.get("revived"):
                    self._reader_signals.status.emit(
                        "Partija je bila obelezena kao predata, a igra kaze da "
                        "traje — nastavljam da je citam."
                    )
                return
            # Say what the engine actually looked like, rather than leaving the
            # user with a button that silently does nothing.
            self._reader_signals.status.emit(
                "Ne vidim partiju: "
                f"GameCount={detail.get('game_count')} "
                f"nadjen={detail.get('found')} "
                f"stanje={detail.get('state')} (sirovo {detail.get('state_raw')}) "
                f"tabla={detail.get('has_board')} "
                f"simulacija={detail.get('simulation')} "
                f"{detail.get('resolve_error') or ''}".strip()
            )

        # Never on the GUI thread: this is a synchronous RPC into the game.
        threading.Thread(target=ask, daemon=True).start()

    def _note_move_failure(self, error: str) -> None:
        """Log a failed computation and hold the next attempt back.

        Nothing used to hold it: the next tick (25-50 ms) asked again on the
        same board and failed the same way, 450 times in 14 s on 2026-09-18
        21:38. The pause doubles from 0.5 s up to MOVE_ERROR_MAX_BACKOFF, and a
        repeat of the same error is logged at 1, 2, 4, 8... occurrences only.
        """
        text = (error or "").strip()
        if text == self._move_error_text:
            self._move_error_count += 1
        else:
            self._move_error_text = text
            self._move_error_count = 1
        count = self._move_error_count
        delay = min(MOVE_ERROR_MAX_BACKOFF, MOVE_ERROR_FIRST_BACKOFF * 2 ** (count - 1))
        self._move_retry_not_before = time.monotonic() + delay
        if count & (count - 1) == 0:
            repeat = f" (ponovljeno {count}x, sledeci pokusaj za {delay:.1f}s)" if count > 1 else ""
            self._log(f"Move failed: {text}{repeat}")

    def _clear_move_failures(self) -> None:
        self._move_error_count = 0
        self._move_error_text = None
        self._move_retry_not_before = 0.0

    def _move_retry_wait(self) -> float:
        """Seconds still to wait after a failed computation, 0 when free."""
        return max(0.0, self._move_retry_not_before - time.monotonic())

    def _auto_progress(self):
        """Auto got somewhere: the stall clock starts over from here."""
        self._auto_progress_at = time.monotonic()
        self._auto_stall_reason = None
        self._move_stuck_logged = False

    def _auto_blocked(self, reason: str):
        """Say why auto is standing still, once it has stood still long enough.

        Each gate in the tick is a bare `return` -- right for one tick, and over
        minutes indistinguishable from a dead loop. The turn clock keeps running
        either way, so the reason has to be readable while it happens.
        """
        now = time.monotonic()
        if self._auto_progress_at is None:
            self._auto_progress_at = now
            return
        standing = now - self._auto_progress_at
        if standing < AUTO_STALL_LOG_SECONDS:
            return
        if (
            reason == self._auto_stall_reason
            and now - self._auto_stall_logged_at < AUTO_STALL_LOG_SECONDS
        ):
            return
        self._auto_stall_reason = reason
        self._auto_stall_logged_at = now
        self._log(f"Auto stalled {standing:.0f}s: {reason}")

    @guarded_slot
    def _auto_tick(self):
        snapshot = self._snapshot
        self._update_auto_plan()
        if snapshot is not None:
            # Repainted on every tick, not only when a board arrives: the
            # countdown is a clock, and a clock that only moves when the game
            # happens to resend its state is not one.
            self.TurnLabel.setText(
                self._turn_label_text(snapshot.get("state") or {})
            )
        auto_action = self._auto_action()
        if auto_action is None:
            self._auto_progress_at = None
            self._expire_requested_action()
            self._precompute_tick()
            return
        if self._move_running:
            plan = self._auto_plan
            if (plan is not None and not plan.armed and not plan.cancelled
                    and plan.action == auto_action):
                # Computed (or computing) with Auto off; Auto now owns it.
                plan.arm()
                self._update_auto_plan()
                self._set_actions_enabled(self._reader_session is not None)
                self._set_calc_status(
                    f"Auto taking over ({plan.action_label}) - playing once the board settles"
                )
                return
            if plan is not None and not plan.armed and not plan.executing:
                plan.cancel()
                return
            running = time.monotonic() - self._action_started_at
            if running >= MOVE_STUCK_WARN_SECONDS and not self._move_stuck_logged:
                self._move_stuck_logged = True
                self._log(
                    f"Potez traje vec {running:.0f}s — auto ceka njega. "
                    "Ako ovo stoji, citac/igra ne odgovaraju."
                )
            return
        if self._reader_session is None:
            self._auto_blocked("citac nije prikacen")
            return
        # Attached but between matches: the engine leaves the finished match's
        # board on the heap, so a snapshot from the lobby looks perfectly
        # playable. Asking for a fresh dump here would also pay ~114 ms per
        # tick for a board nobody is playing on.
        if not self._match_active:
            self._auto_blocked("cekam pocetak partije")
            return
        if snapshot is None:
            self._auto_blocked("nema table")
            return
        if self._move_retry_wait() > 0.0:
            self._auto_blocked(
                f"pauza posle greske u potezu ({self._move_error_count}x): "
                f"{self._move_error_text}"
            )
            return
        # An attached reader that stopped delivering leaves a board that looks
        # fine and is not. A quiet game sends nothing either, so ask for a board
        # instead of assuming the worst; a short wait keeps the loop responsive
        # and the next tick acts on whatever arrives. Silent on purpose: auto
        # polls, so this is a "not yet" rather than something to report.
        age = self.snapshot_age_seconds()
        if age is None or age > board_source.DEFAULT_MEMORY_MAX_AGE_SECONDS:
            self._request_dump()
            self._auto_blocked(
                f"tabla je stara {age:.0f}s, igra ne salje svezu"
                if age is not None
                else "tabla jos nije stigla"
            )
            return
        state = snapshot.get("state") or {}
        # Whose turn it is comes first: during the opponent's move there is
        # nothing to wait for except them.
        if self._opponent_is_playing(state):
            # The turn passed after our last swap; the column has moved on.
            self._lights_up_stale_column = None
            self._auto_progress()
            return
        # Start the same planner before the engine opens its input phase. One
        # worker owns runtime globals; changed snapshots cancel its result and
        # the latest snapshot starts as soon as that worker finishes.
        if (snapshot.get("signature") != self._last_played_signature
                and state.get("moves")
                and snapshot.get("board") and snapshot.get("special_board")
                and runtime.board_scan_block_reason(snapshot.get("board")) is None
                and runtime.board_zero_count(snapshot["board"]) == 0
                and (not snapshot.get("stable") or not self._engine_move_phase_open(snapshot))
                and state.get("game_state") in GAME_STATES_CAN_PREPARE
                and self._prepares_ahead(state)
                and not self._cleo_needs_rest(snapshot)):
            self._play(auto_action, prepare_ahead=True)
            return
        if not self._engine_move_phase_open(snapshot):
            self._auto_blocked(
                f"igra ne prima potez (stanje {state.get('game_state')}, "
                f"kaskada {state.get('chain_reaction')}, "
                f"potezi {state.get('moves')})"
            )
            return
        if snapshot.get("signature") == self._last_played_signature:
            played_ago = (
                None
                if self._last_played_at is None
                else time.monotonic() - self._last_played_at
            )
            # A stable board still identical this long after the move means the
            # game swallowed the drag. Clear the latch and fall through: the
            # remaining gates re-check this same tick and the move is planned
            # again on the unchanged board. Without this the gate blocked until
            # the match clock ran out (2026-08-24 06:37, four moves lost).
            if (
                played_ago is not None
                and played_ago >= SWIPE_RETRY_SECONDS
                and snapshot.get("stable")
            ):
                self._log(
                    f"Tabla ista {played_ago:.0f}s posle poteza — swipe nije "
                    "prosao, igram ponovo."
                )
                self._last_played_signature = None
            else:
                self._auto_blocked(
                    "tabla se nije promenila od proslog poteza — swipe "
                    "verovatno nije prosao"
                )
                return
        # The settled board is non-negotiable: an unsettled snapshot can still
        # gain cascade matches, and a move planned on it is a move on a board
        # that no longer exists.
        #
        # Asking for a dump is what breaks the tie, and it is not busywork: the
        # agent deduplicates by signature, so a settle that lands back on an
        # already-sent arrangement used to be dropped and the last word stayed
        # "still moving" forever. The agent now counts `stable` as a change too;
        # the request here is what recovers a host that is already holding one
        # of those stuck boards.
        if not snapshot.get("stable"):
            self._request_dump()
            self._auto_blocked(
                "citac jos nije potvrdio da je tabla smirena "
                "(igra kaze da potez moze) — trazim svezu tablu"
            )
            return
        if self._needs_engine_read(snapshot):
            self._request_dump()
            self._auto_blocked("waiting for fresh dump (jelly zone / Mixy / UFO counters)")
            return
        # A board this old is still fine to plan on -- it cannot change while
        # we are on turn -- but it is not fine to read a clock off. Ask for a
        # fresh one and decide on the next tick.
        if not self._turn_countdown_is_fresh(state):
            self._request_dump()
            self._auto_blocked("cekam svezu tablu zbog tajmera poteza")
            return
        # The board record is not awaited here: the plan computes while it is
        # read and only the swipe waits for it (_update_auto_plan's `ready`).
        self._auto_progress()
        self._play(auto_action, prepare_ahead=True)

    def _waits_for_board_record(self, snapshot) -> bool:
        """Auto holds the swipe until this board is read for the refill check.

        Only the swipe: the move is computed in the meantime, the record and
        the search each read their own resting profile.

        Auto plays within a second of the board settling, which kept moving the
        RNG under the recorder: 2 of 3 boards were lost in Auto and none with it
        off (Debug/research 20261103_013829). The wait is capped, a read that
        never finishes must not cost the move.
        """
        if not (self._refill_on or self._research_on) or self._reader_script is None:
            return False
        # Outside the Solo Challenge the swipe does not wait for the refill
        # check's record (only for the research recording, when that is on).
        if not self._research_on and not self._is_solo_challenge(snapshot.get("state") or {}):
            return False
        signature = snapshot.get("signature")
        if signature == self._research_done_signature:
            return False
        if signature != self._record_wait_signature:
            self._record_wait_signature = signature
            self._record_wait_started = time.monotonic()
        return time.monotonic() - self._record_wait_started < BOARD_RECORD_WAIT_SECONDS

    def _expire_requested_action(self):
        """Drop a button press the game never let through in time."""
        requested = self._requested_action
        if requested is None:
            return
        plan = self._auto_plan
        if (self._move_running and plan is not None and plan.armed
                and not plan.cancelled and not plan.computed
                and plan.action == requested):
            # Still thinking about the clicked move (a Solo challenge search
            # can take well over the timeout): that is not the game refusing
            # the move. The clock for the game starts once the move is known,
            # so the click is never dropped mid-search and always plays.
            self._requested_at = time.monotonic()
            return
        waited = time.monotonic() - self._requested_at
        if waited < REQUESTED_ACTION_TIMEOUT_SECONDS:
            return
        self._requested_action = None
        if plan is not None and plan.armed and not plan.executing:
            # The computation goes on as the speculative plan; only the
            # permission to play it expires with the click.
            plan.disarm()
            self._set_actions_enabled(self._reader_session is not None)
        self._log(
            f"{self._ACTION_LABELS[requested]}: game did not allow move "
            f"{waited:.0f}s after click — request cancelled."
        )
        self._set_calc_status(
            f"request cancelled ({self._ACTION_LABELS[requested]}) - "
            f"game did not allow move for {REQUESTED_ACTION_TIMEOUT_SECONDS:.0f}s"
        )

    def _precompute_tick(self):
        """Auto off: still compute the best move for every new board.

        The result is held by the worker, unarmed, until a move button arms
        it (then it plays as soon as the board is ready) or the board changes
        (then it is dropped and this starts over on the new one). Same gates
        as Auto's speculative branch, minus everything about *playing*.
        """
        if self._move_running or self._reader_session is None:
            return
        if not self._match_active:
            return
        if self._move_retry_wait() > 0.0:
            return
        snapshot = self._snapshot
        if snapshot is None:
            return
        requested = self._requested_action
        waiting = (
            f"waiting for game to allow ({self._ACTION_LABELS[requested]})"
            if requested is not None else None
        )
        age = self.snapshot_age_seconds()
        if age is None or age > board_source.DEFAULT_MEMORY_MAX_AGE_SECONDS:
            # A standing request must not wait on a game that has gone quiet:
            # ask for a board (one request in flight at a time) and retry.
            if waiting is not None:
                self._request_dump()
                self._set_calc_status(f"{waiting} - refreshing board")
            return
        state = snapshot.get("state") or {}
        if self._opponent_is_playing(state):
            if waiting is not None:
                self._set_calc_status(f"{waiting} - opponent is playing")
            return
        if not (snapshot.get("signature") != self._last_played_signature
                and state.get("moves")
                and snapshot.get("board") and snapshot.get("special_board")
                and runtime.board_scan_block_reason(snapshot.get("board")) is None
                and runtime.board_zero_count(snapshot["board"]) == 0
                and state.get("game_state") in GAME_STATES_CAN_PREPARE
                and not self._waits_for_settled_board(snapshot)):
            if waiting is not None:
                self._set_calc_status(
                    f"{waiting} - state {state.get('game_state')}, "
                    f"moves {state.get('moves')}"
                )
            return
        if requested is not None:
            self._play(requested, prepare_ahead=True, armed=True)
        else:
            self._play("best_move", prepare_ahead=True, armed=False)

    def _turn_countdown_is_fresh(self, state) -> bool:
        """Whether this snapshot is new enough to time the turn by.

        Only ever false in timed modes. The agent resends on *change*, and our
        own turn does not change while the bot is thinking, so the same board
        that is perfectly good for planning a move can be seconds stale for the
        clock printed on it.
        """
        state = state or {}
        if not isinstance(state.get("remaining_time"), (int, float)):
            return True
        age = self.snapshot_age_seconds()
        return age is None or age <= TIMED_TURN_SNAPSHOT_MAX_AGE_SECONDS

    def _opponent_is_playing(self, state) -> bool:
        """Whether the other side is on turn, per PlayerClientControl.IsMyTurn.

        Auto waits this out rather than looking for a gap to swipe into: a drag
        sent while the opponent is moving is either swallowed or -- worse --
        lands on our own next turn as a move nobody chose, on a board that has
        meanwhile changed.
        """
        state = state or {}
        players = state.get("players") or []
        me = self._current_player(state, players) or {}
        if not players or me.get("is_my_turn") is not False:
            return False
        key = self._turn_key(state)
        if self._opponent_turn_logged_for != key:
            self._opponent_turn_logged_for = key
            self._log("Opponent's turn — waiting for them to play.")
        return True

    @staticmethod
    def _turn_key(state):
        state = state or {}
        return (
            state.get("current_turn"),
            state.get("current_round"),
            state.get("current_player_index"),
        )

    def _engine_move_phase_open(self, snapshot) -> bool:
        """The engine's own answer to "can a move be played right now".

        Our turn, the move phase, no cascade in flight, moves left. No motion
        tracking needed -- but this is only half the gate: the caller still
        waits for the agent to call the board settled.
        """
        state = (snapshot or {}).get("state") or {}
        players = state.get("players") or []
        me = self._current_player(state, players) or {}
        if state.get("game_state") != GAME_STATE_MOVE_PLAYING:
            return False
        if players and me.get("is_my_turn") is False:
            return False
        if state.get("chain_reaction"):
            return False
        return bool(state.get("moves"))


def main() -> int:
    application = QtWidgets.QApplication(sys.argv)
    apply_theme(application)
    window = MemoryWindow()
    window.show()
    return application.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
