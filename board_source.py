"""Board-source selection and read-only IL2CPP snapshot adaptation.

The Frida host reader owns ``Debug/memory_board/latest.json``.  This module
only reads that file; it never attaches to the game and never writes process
memory.  Keeping the adapter separate lets the GUI switch sources without
coupling the existing ML recognition pipeline to Frida.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from move_strategy import (
    BLOCKED,
    BLUE,
    CHEST,
    DISCO_BALL,
    EMPTY,
    GREEN,
    ORANGE,
    PURPLE,
    RED,
    RED_BLUE_TILE_COLORS,
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
    SPECIAL_ZANY_ZAPPER_1,
    SPECIAL_ZANY_ZAPPER_2,
    VINNIE_SE_HEART_COLORS,
    WHITE,
    YELLOW,
    PURPLE,
    PURPLE_GEM_MIN_RECOGNIZED_VALUE,
    make_purple_gem_special,
    make_vinnie_se_heart_special,
)


BOARD_SOURCE_ML = "ml"
BOARD_SOURCE_MEMORY = "memory"
BOARD_SOURCE_AUTO = "auto"
BOARD_SOURCE_OPTIONS = (
    ("Tabla: ML", BOARD_SOURCE_ML),
    ("Tabla: Memorija", BOARD_SOURCE_MEMORY),
    ("Tabla: Auto (memorija -> ML)", BOARD_SOURCE_AUTO),
)

DEFAULT_MEMORY_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent / "Debug" / "memory_board" / "latest.json"
)
DEFAULT_MEMORY_MAX_AGE_SECONDS = 5.0


class MemoryBoardUnavailable(RuntimeError):
    """The memory reader has no recent, valid board snapshot."""


@dataclass(frozen=True)
class BoardSourceResult:
    board: list[list[int]]
    special_board: list[list[int]]
    source: str
    snapshot: dict | None = None
    warnings: tuple[str, ...] = ()
    fallback_reason: str | None = None


_SLOT_COLOR_TO_BOARD = {
    0: EMPTY,  # SlotColor.Empty
    1: EMPTY,  # SlotColor.None
    2: RED,
    3: GREEN,
    4: BLUE,
    5: YELLOW,
    6: ORANGE,
    7: PURPLE,
    8: WHITE,
    12: DISCO_BALL,  # SlotColor.All
}

_SIMPLE_VALUE_TO_SPECIAL = {
    0: 0,  # Normal
    1: 0,  # Empty
    4: SPECIAL_VERTICAL,  # Column
    5: SPECIAL_HORIZONTAL,  # Row
    6: SPECIAL_BOMB,
    8: SPECIAL_CROSSHAIR,
    16: SPECIAL_MODE_TARGET,  # BoardSpecial -- see _board_special_special()
    18: SPECIAL_COLOR_CRYSTAL,
    19: SPECIAL_MUSHROOM,
    24: SPECIAL_JOOJOO_SKULL,
    25: SPECIAL_BILLIE_DRONE,
    26: SPECIAL_DISCO_BALL,  # ColorBombPiece
    28: SPECIAL_DISCO_BALL,  # BroccoBoogiePiece -- the disco the bot models
    29: SPECIAL_ALL_ABOARD_BANDIT,
    31: SPECIAL_SPRAY_SE,
    32: SPECIAL_CLEO_BUG,
    33: SPECIAL_KNIGHT,
    38: SPECIAL_SWEEP_SE_BROOM,
    39: SPECIAL_CROSSHAIR,
    40: SPECIAL_FROGGY_LOTUS,
}

# Every SlotValue the adapter has a model for: the table above plus the values
# handled by a branch of their own (7 lightning/fireworks, 17 Zany Zapper,
# 20 chest, 23 heart).
_KNOWN_SLOT_VALUES = frozenset(_SIMPLE_VALUE_TO_SPECIAL) | {7, 17, 20, 23}

_FIREWORK_STATUS_TO_SPECIAL = {
    2: SPECIAL_FIREWORK_UP,
    4: SPECIAL_FIREWORK_RIGHT,
    8: SPECIAL_FIREWORK_DOWN,
    16: SPECIAL_FIREWORK_LEFT,
}

# Snapshot schema versions this adapter knows how to read. Checked only when
# the snapshot carries the field at all: older dumps and hand-built test
# payloads omit it, and refusing those would break replays for nothing. A
# *present but unknown* version is the agent and the adapter drifting apart --
# exactly the mismatch that used to pass unnoticed (agent said 2, the JSON
# schema said 1, nobody checked either). 1 and 2 stay accepted because
# recorded jsonl replays carry them; 3 is the first version with enum tables.
SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})

# Every member of the engine enums whose numbers appear in this codebase, as
# dumped live from the IL2CPP metadata (data/il2cpp_symbols.json, 2026-08-21).
# The agent reads the same tables at attach and ships them in the snapshot;
# _verify_enum_tables compares the two. The point is the *insertion* case: a
# game update that adds a member mid-enum shifts every later value, the shifted
# numbers are all still "known", so unknown_slot_value can never fire -- the
# reader keeps working perfectly and reports a lotus as a pirate chest.
PINNED_ENUM_VALUES = {
    "SlotValueType": {
        "Normal": 0, "Empty": 1, "MergeSwapPiece": 2,
        "ClassicSpecials_Start": 3, "Column": 4, "Row": 5, "Bomb": 6,
        "Fireworks": 7, "Crosshair": 8, "ClassicSpecials_End": 9,
        "ClassicMerges_Start": 10, "Cross": 11, "Star": 12,
        "FourthOfJuly": 13, "ClassicMerges_End": 14,
        "BoardSpecials_Start": 15, "BoardSpecial": 16, "ZanyZapperPiece": 17,
        "ColorCrystalPiece": 18, "MultiplierMushroomPiece": 19,
        "PirateChestPiece": 20, "BoardSpecials_End": 21,
        "BoosterPieces_Start": 22, "CupidHeart": 23, "MonkeyJoojooPiece": 24,
        "BillieBoomPiece": 25, "ColorBombPiece": 26, "PaintbrushPiece": 27,
        "BroccoBoogiePiece": 28, "AllAboardSEBandit": 29,
        "SpecialDeliverySEPiece": 30, "FoxyRoxySEPiece": 31,
        "CleoCadabraPiece": 32, "ChessKnightsPiece": 33, "BeehivePiece": 34,
        "YinYangPiece": 35, "StarMeteorsPiece": 36, "MagicBeansPiece": 37,
        "SweepItSEPiece": 38, "CrossAttackSEPiece": 39, "LotusPiece": 40,
        "BoosterPieces_End": 41,
    },
    "SlotColor": {
        "Empty": 0, "None": 1, "Red": 2, "Green": 3, "Blue": 4, "Yellow": 5,
        "Orange": 6, "Purple": 7, "White": 8, "All": 12,
    },
    "BoardModelName": {
        "None": 0, "BoardModel": 1, "CandyWorldBoard": 2,
        "CrystalCaveBoard": 3, "DustvilleDuelBoard": 4, "RocketRiotBoard": 5,
        "FrozenFeudBoard": 6, "JungleRumbleBoard": 7, "PlunderPiratesBoard": 8,
        "FireworksFestivalBoard": 9, "VegasViewsBoard": 10, "RainbowBoard": 11,
        "FunkyTilesBoard": 12, "BullseyeBoard": 13, "ExtraMovesBoard": 14,
        "BuriedTreasureBoard": 15, "ColorBombBoard": 16, "DigDownBoard": 17,
        "LightsabersBoard": 18, "CrazyColumnsBoard": 19, "StockMarketBoard": 20,
        "HotColorBoard": 21, "MultiplierMadnessBoard": 22,
        "VerticalRushBoard": 23, "MultiplierByRoundBoard": 24,
        "SwitcherooBoard": 25, "EnergizedBoard": 26, "MatchLineBoard": 27,
        "ColorCrushBoard": 28, "MultiplierMushroomsBoard": 29,
        "MightyMushroomsBoard": 30, "NuclearBoard": 31, "ColumnManiaBoard": 32,
        "ZanyZappersBoard": 33, "EveryMoveIncreaseScoreMultiplierBoard": 34,
        "RainbowMultiplierBoard": 35, "FloorIsLavaBoard": 36,
        "LightsUpBoard": 37,
    },
    "SpecialAbilityType": {
        "None": 0, "Hammer": 1, "DoubleScore": 2, "Magic": 3,
        "ExplodeSpecials": 4, "Nuke": 5, "SpecialDelivery": 6,
        "CrossAttack": 8, "Teleport": 9, "Grind": 10, "TransformSwap": 11,
        "DualRockets": 12, "SmallBoom": 13, "CreateSpecials": 14,
        "Painter": 15, "AutoMatcher": 16, "RubberDucky": 17, "B52Bomber": 18,
        "UFOBeam": 19, "MemoryGame": 20, "BlazingBoard": 21,
        "BalloonBlast": 22, "TapTime": 23, "Infection": 24, "Lightsabers": 25,
        "AllAboard": 26, "DoctorColor": 27, "CrazyClovers": 28,
        "RainbowExplosion": 29, "ReplayExplosions": 30, "JeevesBot": 31,
        "QueenCobra": 32, "ElMagneto": 33, "MrAppleberry": 34,
        "WoollyWorkout": 35, "FoxyRoxy": 36, "ColonelMcQuack": 37,
        "Cupid": 38, "SweepIt": 39, "MonkeyJoojoo": 40, "BillieBoom": 41,
        "ColorBombs": 42, "Paintbrushes": 43, "BroccoBoogie": 44,
        "DoctorColorSE": 45, "AllAboardSE": 46, "CupidSE": 47,
        "ElMagnetoSE": 48, "UFOBeamSE": 49, "SpecialDeliverySE": 50,
        "Zebra": 51, "FoxyRoxySE": 52, "CleoCadabra": 53,
        "CheckmateCharles": 54, "Beehive": 55, "YinYang": 56,
        "StarMeteors": 57, "MagicBeans": 58, "MixyMeow": 59, "JellySE": 60,
        "SweepItSE": 61, "CrossAttackSE": 62, "FroggyFu": 63,
    },
}

# The members whose numbers the bot's own logic branches on. A shift here means
# the bot is *actively misreading the board or the mode*, so the only honest
# reaction is to stop -- MemoryBoardUnavailable, with the exact member and both
# numbers, so the fix is a table update rather than an investigation. A shift
# anywhere else in PINNED_ENUM_VALUES, or a brand-new member, is a warning:
# real information, but not proof that anything the bot plays on is wrong.
CRITICAL_ENUM_MEMBERS = {
    # _SIMPLE_VALUE_TO_SPECIAL, _KNOWN_SLOT_VALUES and the branch cases in
    # _slot_special/_adapt_slots.
    "SlotValueType": frozenset({
        "Normal", "Empty", "Column", "Row", "Bomb", "Fireworks", "Crosshair",
        "BoardSpecial", "ZanyZapperPiece", "ColorCrystalPiece",
        "MultiplierMushroomPiece", "PirateChestPiece", "CupidHeart",
        "MonkeyJoojooPiece", "BillieBoomPiece", "ColorBombPiece",
        "BroccoBoogiePiece", "AllAboardSEBandit", "FoxyRoxySEPiece",
        "CleoCadabraPiece", "ChessKnightsPiece", "SweepItSEPiece",
        "CrossAttackSEPiece", "LotusPiece",
    }),
    # _SLOT_COLOR_TO_BOARD covers every one of these.
    "SlotColor": frozenset({
        "Empty", "None", "Red", "Green", "Blue", "Yellow", "Orange", "Purple",
        "White", "All",
    }),
    # memory_gui.BOARD_MODEL_TO_MODE plus SCORE_MULTIPLIER_BOARD_MODELS here.
    "BoardModelName": frozenset({
        "CandyWorldBoard", "CrystalCaveBoard", "DustvilleDuelBoard",
        "FrozenFeudBoard", "JungleRumbleBoard", "PlunderPiratesBoard",
        "FireworksFestivalBoard", "VegasViewsBoard", "FunkyTilesBoard",
        "BullseyeBoard", "ExtraMovesBoard", "BuriedTreasureBoard",
        "ColorBombBoard", "DigDownBoard", "LightsabersBoard",
        "CrazyColumnsBoard", "StockMarketBoard", "HotColorBoard",
        "MultiplierMadnessBoard", "VerticalRushBoard", "EnergizedBoard",
        "MatchLineBoard", "ColorCrushBoard", "MultiplierMushroomsBoard",
        "MightyMushroomsBoard", "ColumnManiaBoard", "ZanyZappersBoard",
        "EveryMoveIncreaseScoreMultiplierBoard", "RainbowMultiplierBoard",
        "FloorIsLavaBoard", "LightsUpBoard",
    }),
    # The boosters the GUI/simulator special-case by number (UFO 49, Mixy 59,
    # jelly 60, sweep 61, cross-attack 62, Froggy 63).
    "SpecialAbilityType": frozenset({
        "UFOBeamSE", "MixyMeow", "JellySE", "SweepItSE", "CrossAttackSE",
        "FroggyFu",
    }),
}


def _check_schema_version(snapshot: dict) -> None:
    raw = snapshot.get("schema_version")
    if raw is None:
        return
    try:
        version = int(raw)
    except (TypeError, ValueError):
        raise MemoryBoardUnavailable(
            f"snapshot ima neispravan schema_version: {raw!r}"
        ) from None
    if version not in SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS))
        raise MemoryBoardUnavailable(
            f"Agent salje schema_version {version}, adapter podrzava {supported}; "
            "uskladi agenta (tools/build_board_agent.ps1) i bota"
        )


def _verify_enum_tables(snapshot: dict) -> tuple[str, ...]:
    """Warnings from comparing the agent's live enum tables against the pin.

    A mismatch on a CRITICAL member raises instead: silence there is the exact
    failure this check exists for -- the game updated, every value after the
    insertion shifted, and the reader keeps "working" on a wrong board model.
    A snapshot with no tables at all (schema_version 2 agent) passes with a
    warning on v3 only, so replays and old builds keep loading.
    """
    enums = snapshot.get("enums")
    if not isinstance(enums, dict):
        try:
            version = int(snapshot.get("schema_version"))
        except (TypeError, ValueError):
            version = None
        if version is not None and version >= 3:
            return ("enum_tables_missing",)
        return ()
    errors: list[str] = []
    warnings: list[str] = []
    for enum_name, pinned in PINNED_ENUM_VALUES.items():
        table = enums.get(enum_name)
        if not isinstance(table, dict):
            warnings.append(f"enum_table_missing:{enum_name}")
            continue
        critical = CRITICAL_ENUM_MEMBERS.get(enum_name, frozenset())
        for member, expected in pinned.items():
            raw = table.get(member)
            try:
                got = None if raw is None else int(raw)
            except (TypeError, ValueError):
                got = None
            if got == expected:
                continue
            if got is None:
                message = f"{enum_name}.{member}: ocekivano {expected}, igra ga vise nema"
            else:
                message = f"{enum_name}.{member}: ocekivano {expected}, igra kaze {got}"
            if member in critical:
                errors.append(message)
            else:
                warnings.append(f"enum_drift:{message}")
        for member, value in table.items():
            if member not in pinned:
                warnings.append(f"new_enum_member:{enum_name}.{member}={value}")
    if errors:
        raise MemoryBoardUnavailable(
            "Enum igre se ne poklapa sa botom (update igre?): " + "; ".join(errors)
        )
    return tuple(warnings)


# The engine deals each player a SlotColor per match (PlayerControl.slotType):
# the local player usually draws Blue(4) and the opponent Red(2), and the whole
# strategy layer leans on that -- BLUE charges our booster, RED the opponent's
# (VERSUS_OPPONENT_BOOSTER_COLOR). The deal is not guaranteed: a versus match
# on 2026-08-26 handed the local player Red(2), the game still drew those tiles
# as the blue stars (the art is player-relative, the enum value is not), and the
# fixed table below labelled our own charge colour R -- so the panel disagreed
# with the screen and "juri plave" chased the tiles that charge the opponent.
#
# The permutation is rebuilt from every snapshot's state.players before its
# slots are read: whatever engine colour is ours reads as BLUE, the opponent's
# as RED, and the two displaced colours take the freed labels so the mapping
# stays a bijection. Every colour that reaches the bot -- slots, hot colour,
# charge tables, mutation configs -- goes through slot_color_to_board, so one
# table keeps the board, the panel and the strategy telling the same story.
# No players in the snapshot (solo boards, old agent builds) means an empty
# permutation, which is exactly the old fixed behaviour.
_MY_SLOT_COLOR = 4  # SlotColor.Blue -- what the bot's BLUE constant assumes
_OPPONENT_SLOT_COLOR = 2  # SlotColor.Red
_PLAYER_TYPE_LOCAL = 0  # PlayerClientControl.PlayerType
_player_color_swap: dict[int, int] = {}


def _player_color_swap_for(state: object) -> dict[int, int]:
    players = state.get("players") if isinstance(state, dict) else None
    if not isinstance(players, list):
        return {}
    me = next(
        (
            p for p in players
            if isinstance(p, dict) and p.get("player_type") == _PLAYER_TYPE_LOCAL
        ),
        None,
    )
    if me is None:
        return {}
    my_index = me.get("index")
    opponent = next(
        (
            p for p in players
            if isinstance(p, dict) and p.get("index") != my_index
        ),
        None,
    )

    def _valid(raw: object) -> int | None:
        # Only a real, non-empty piece colour may take part in the relabeling.
        if not isinstance(raw, int) or isinstance(raw, bool):
            return None
        return raw if _SLOT_COLOR_TO_BOARD.get(raw) not in (None, EMPTY) else None

    mine = _valid(me.get("slot_type"))
    theirs = _valid((opponent or {}).get("slot_type"))
    swap: dict[int, int] = {}
    if mine is not None and mine != _MY_SLOT_COLOR:
        swap[mine] = _MY_SLOT_COLOR
    if theirs is not None and theirs != mine and theirs != _OPPONENT_SLOT_COLOR:
        swap[theirs] = _OPPONENT_SLOT_COLOR
    # The displaced engine colours inherit the freed labels, in the same order
    # they were displaced, so the permutation stays a bijection.
    freed = [source for source in swap if source not in swap.values()]
    for shadowed in [target for target in swap.values() if target not in swap]:
        swap[shadowed] = freed.pop(0)
    return swap


def slot_color_to_board(value: object) -> int | None:
    """IL2CPP ``SlotColor`` code -> the bot's colour code, or None if unknown.

    Player-relative: the permutation set by the last adapted snapshot maps the
    local player's dealt colour onto BLUE and the opponent's onto RED.
    """
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    return _SLOT_COLOR_TO_BOARD.get(_player_color_swap.get(raw, raw))


def normalize_board_source(value: object) -> str:
    candidate = str(value or "").strip().lower()
    aliases = {
        "ml": BOARD_SOURCE_ML,
        "memory": BOARD_SOURCE_MEMORY,
        "memorija": BOARD_SOURCE_MEMORY,
        "auto": BOARD_SOURCE_AUTO,
    }
    return aliases.get(candidate, BOARD_SOURCE_ML)


def configured_memory_snapshot_path() -> Path:
    override = os.environ.get("MATCHMASTERS_MEMORY_BOARD_PATH")
    return Path(override).expanduser() if override else DEFAULT_MEMORY_SNAPSHOT_PATH


def _last_json_object(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MemoryBoardUnavailable(
            f"Memorijski reader nije pokrenut: nema {path}"
        ) from exc
    except OSError as exc:
        raise MemoryBoardUnavailable(f"Ne mogu da procitam {path}: {exc}") from exc

    if not text.strip():
        raise MemoryBoardUnavailable(f"Memorijski snapshot je prazan: {path}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as document_error:
        # JSONL is one compact object per line. Pretty-printed latest.json is
        # parsed as a complete document above and must not be mistaken for it.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise MemoryBoardUnavailable(
                f"Neispravan memorijski JSON: {document_error}"
            ) from exc
    if not isinstance(payload, dict):
        raise MemoryBoardUnavailable("Memorijski snapshot mora biti JSON objekat")
    return payload


# Board sizes the bot has screen geometry for (see board_profiles.BOARD_PROFILES).
# The simulator itself works off len(board), so the limit is calibration: a size
# with no profile has no cell centres to swipe, and reading it would only produce
# a board nobody can play.
SUPPORTED_MEMORY_BOARD_SIZES = (7, 8)


def _supported_size(size: int, what: str) -> int:
    if size not in SUPPORTED_MEMORY_BOARD_SIZES:
        raise MemoryBoardUnavailable(
            f"{what} je {size}x{size}; podrzano je "
            + " ili ".join(f"{value}x{value}" for value in SUPPORTED_MEMORY_BOARD_SIZES)
        )
    return size


def _validated_grid(value: object, name: str) -> list[list[int]]:
    if not isinstance(value, list):
        raise MemoryBoardUnavailable(f"{name} nije kvadratna tabla")
    size = _supported_size(len(value), name)
    result = []
    for row in value:
        if not isinstance(row, list) or len(row) != size:
            raise MemoryBoardUnavailable(f"{name} nije {size}x{size}")
        try:
            result.append([int(cell) for cell in row])
        except (TypeError, ValueError) as exc:
            raise MemoryBoardUnavailable(f"{name} sadrzi nebrojanu vrednost") from exc
    return result


def _board_special_special(slot: dict) -> int:
    """The bot's special for a ``SlotValue.BoardSpecial`` (16) piece.

    Most board models use it for a plain collectible target. Candy World's candy
    carries a *second* colour in ``SlotModel.color2`` (blue + red on the
    2026-08-17 capture) and plays as whichever of the two it is matched with:
    matched blue it charges the booster, matched red it does not. That is the
    Red and Blue tile the engine layer already models, so the pair is what
    decides -- not the board model, which the adapter does not see.
    """
    colors = {
        slot_color_to_board(slot.get("color")),
        slot_color_to_board(slot.get("color2")),
    }
    if colors == set(RED_BLUE_TILE_COLORS):
        return SPECIAL_RED_BLUE_TILE
    gem = _purple_gem_special(slot)
    if gem is not None:
        return gem
    return SPECIAL_MODE_TARGET


def _purple_gem_special(slot: dict) -> int | None:
    """The Purple Gem's *printed* value, or None when this is a flat target.

    Purple Gem mode's gems ride on ``SlotValue.BoardSpecial`` like every other
    collectible, but the number printed on them -- what the mode actually
    counts -- is carried in ``SlotModel.score``. The adapter used to drop it and
    return the flat ``SPECIAL_MODE_TARGET``, so on the memory path a gem printed
    19 scored exactly the same as one printed 5: ``mode_target_value`` returns 1
    for a flat target, and Purple Gem weights ``mode_target`` at 1.0. The screen
    path never had this bug (``recognition._resolve_prediction_values`` reads the
    digits), so it only ever bit the memory path -- every logged Purple Gem move
    (Debug/runs 2026-08-20_01-32..01-34) ranked gems as interchangeable.

    ``board_source`` has no game-mode context, so the gem is identified by what
    only it looks like: a purple collectible carrying a score. Across all 537
    recorded runs with memory frames, ``BoardSpecial`` appears in Purple Gem mode
    alone, always ``color`` 7 (purple) with ``score`` 5..19 -- and the other
    collectible modes target green (Green Leaf), orange (Bounty) or a red/blue
    pair (Candy World, handled above), so none of them can reach this branch.

The number is passed with ``exact=True``: the screen path's 22 ceiling
    exists only because its classes stop there, and memory has no such limit.
    The 2026-08-22 match had 342 of 805 gem readings above 22, up to 42, so
    clamping them all to 25 would have ranked a gem printed 42 below a pair of
    13s.
    """
    if slot_color_to_board(slot.get("color")) is not PURPLE:
        return None
    try:
        value = int(slot.get("score", 0))
    except (TypeError, ValueError):
        return None
    if value < PURPLE_GEM_MIN_RECOGNIZED_VALUE:
        return None
    return make_purple_gem_special(value, exact=True)


def _heart_special(slot: dict, warnings: list[str]) -> int:
    """The bot's special for a ``SlotValue`` 23 heart.

    Vinnie's SE hearts carry a colour *pair*: the matched colour in
    ``SlotModel.color`` and the second one in ``color2``.  Both colours come off
    the board when the heart fires, and other hearts survive it -- which is what
    ``SPECIAL_VINNIE_SE_HEART_*`` models.  The 2026-08-19 captures show every
    heart in play is such a pair, so collapsing them onto the single-colour
    ``SPECIAL_HEART`` erased the second colour (and with it any blue the move
    would have charged the booster with).

    A heart carrying no second colour -- ``SlotColor.None``, or the same colour
    twice -- is the plain one-colour heart the bot already modelled.
    """
    first = slot_color_to_board(slot.get("color"))
    second = slot_color_to_board(slot.get("color2"))
    if second not in VINNIE_SE_HEART_COLORS or first == second:
        return SPECIAL_HEART
    if first not in VINNIE_SE_HEART_COLORS:
        warnings.append(
            f"heart_color_pair@{slot.get('x')},{slot.get('y')}:"
            f"{slot.get('color')}+{slot.get('color2')}"
        )
        return SPECIAL_HEART
    return make_vinnie_se_heart_special(first, second)


def _slot_special(slot: dict, warnings: list[str], fireworks_festival: bool = False) -> int:
    value = int(slot.get("value", 0))
    if value == 16:  # BoardSpecial: a candy carries its second colour in color2.
        if fireworks_festival:
            flags = int(slot.get("status", 0)) & 30
            return _FIREWORK_STATUS_TO_SPECIAL.get(flags, SPECIAL_MODE_TARGET)
        return _board_special_special(slot)
    if value == 23:  # Heart: a Vinnie SE heart carries its pair in color2.
        return _heart_special(slot, warnings)
    if value == 7:
        # Live Funky Tiles and Candy World captures on 2026-08-17 prove that
        # an ordinary Lightning is SlotValue 7 with status 0.  The old adapter
        # treated every 7 as a directional firework and consequently erased
        # every Lightning from the memory board with
        # ``firework_without_single_direction``.
        status = int(slot.get("status", 0))
        if status in (0, 1):
            return SPECIAL_LIGHTNING

        # Directional Fireworks use one SlotStatusType direction flag.  Keep
        # this narrower variant for captured/non-zero statuses instead of
        # allowing it to swallow the plain Lightning representation again.
        directions = [
            special for flag, special in _FIREWORK_STATUS_TO_SPECIAL.items() if status & flag
        ]
        if len(directions) == 1:
            return directions[0]
        warnings.append(
            f"firework_without_single_direction@{slot.get('x')},{slot.get('y')}:{status}"
        )
        return 0
    if value == 17:  # Zany Zapper uses hit points for its remaining stage.
        return SPECIAL_ZANY_ZAPPER_2 if int(slot.get("hitPoints", 0)) >= 2 else SPECIAL_ZANY_ZAPPER_1
    special = _SIMPLE_VALUE_TO_SPECIAL.get(value)
    if special is None:
        warnings.append(f"unknown_slot_value@{slot.get('x')},{slot.get('y')}:{value}")
        return 0
    return special


def _slots_board_size(slots: list, rows: object, columns: object) -> int:
    """Board size a dump describes: the agent's rows/columns, else the count.

    The agent walks every cell, so the slot count is the board area -- but the
    dump carries the dimensions too, and a mismatch between them means a partial
    read, which must not quietly become a smaller board.
    """
    if rows is not None and columns is not None:
        try:
            row_count, column_count = int(rows), int(columns)
        except (TypeError, ValueError) as exc:
            raise MemoryBoardUnavailable("snapshot ima neispravne rows/columns") from exc
        if row_count != column_count:
            raise MemoryBoardUnavailable(
                f"tabla nije kvadratna: {column_count}x{row_count}"
            )
        size = _supported_size(row_count, "tabla iz memorije")
    else:
        size = _supported_size(int(round(len(slots) ** 0.5)), "tabla iz memorije")
    if len(slots) != size * size:
        raise MemoryBoardUnavailable(
            f"Memorijski snapshot ima {len(slots)}/{size * size} polja"
        )
    return size


def _adapt_slots(
    slots: object,
    rows: object = None,
    columns: object = None,
    fireworks_festival: bool = False,
) -> tuple[list[list[int]], list[list[int]], tuple[str, ...]]:
    if not isinstance(slots, list):
        raise MemoryBoardUnavailable("Memorijski snapshot nema slots listu")
    size = _slots_board_size(slots, rows, columns)
    board = [[EMPTY for _ in range(size)] for _ in range(size)]
    special_board = [[0 for _ in range(size)] for _ in range(size)]
    seen: set[tuple[int, int]] = set()
    warnings: list[str] = []

    for slot in slots:
        if not isinstance(slot, dict):
            raise MemoryBoardUnavailable("slots sadrzi stavku koja nije objekat")
        try:
            x = int(slot["x"])
            y = int(slot["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryBoardUnavailable("slot nema ispravne x/y koordinate") from exc
        if not (0 <= x < size and 0 <= y < size):
            raise MemoryBoardUnavailable(
                f"slot je van {size}x{size} table: x={x}, y={y}"
            )
        if (x, y) in seen:
            raise MemoryBoardUnavailable(f"dupliran slot: x={x}, y={y}")
        seen.add((x, y))

        raw_color = int(slot.get("color", 0))
        color = slot_color_to_board(raw_color)
        if color is None:
            warnings.append(f"unknown_slot_color@{x},{y}:{raw_color}")
            color = EMPTY
        value = int(slot.get("value", 0))
        special = _slot_special(slot, warnings, fireworks_festival)
        if value == 1:
            color = EMPTY
        elif value == 20:  # PirateChestPiece
            color = CHEST
            special = SPECIAL_MODE_TARGET
        elif value == 40:  # Froggy lotus -- SlotModel.movable is false 557/557
            color = BLOCKED
        elif value == 25:
            # Billie's drone. BLOCKED because the engine reports
            # canBeMatched == false, so no match may run through it -- but it is
            # movable == true in 41/41 recorded snapshots, unlike the lotus it
            # used to share this branch with. Anything modelling board movement
            # (the Sweep SE gather) has to keep moving it.
            color = BLOCKED
        elif value in (26, 28, 31, 32, 38):  # color-agnostic board pieces
            # 28 is BroccoBoogiePiece: free-swap, clears the colour of its swap
            # partner, gives no energy on the swap. That is exactly the "disco"
            # the screen path recognises and the simulator models (measured
            # 2026-08-10), so the memory path must read it the same way.
            color = DISCO_BALL
        elif value not in _KNOWN_SLOT_VALUES and slot.get("canBeMatched") is False:
            # A piece the bot does not model yet, which the engine itself says
            # cannot take part in a match (Laser Matches' lightsaber piece,
            # SlotValue 28). Handing it to the simulator as its base colour
            # invents matches that the game rejects: Debug/runs
            # 2026-08-17_01-42-10 planned 4-4-4 down column 0 straight through
            # one, and the swipe did nothing. Blocked is the honest model --
            # no match runs through it until the piece is understood.
            color = BLOCKED
            warnings.append(f"unmatchable_slot_value@{x},{y}:{value}")

        # IL2CPP is x,y; every bot grid is row,col, therefore row=y/col=x.
        board[y][x] = color
        special_board[y][x] = special

    # The count was checked against the size up front and duplicates raise
    # above, so this can only trip if one of those rails is ever loosened.
    if len(seen) != size * size:
        raise MemoryBoardUnavailable(
            f"Memorijski snapshot ima {len(seen)}/{size * size} polja"
        )
    return board, special_board, tuple(warnings)


def adapt_memory_snapshot_payload(
    payload: dict,
) -> tuple[list[list[int]], list[list[int]], tuple[str, ...]]:
    """Validate one agent payload and convert IL2CPP x,y into bot row,col."""
    if not isinstance(payload, dict):
        raise MemoryBoardUnavailable("Memorijski snapshot mora biti JSON objekat")
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    # The two update rails, before any slot is read: a schema the adapter does
    # not know, or a bot-critical enum value the game has moved, both raise --
    # a board read through either would be wrong in ways no later check sees.
    _check_schema_version(snapshot)
    enum_warnings = _verify_enum_tables(snapshot)
    # Player-relative colours, before any slot is read: whatever engine colour
    # this match dealt the local player must land on BLUE. Module-level on
    # purpose -- the GUI maps mutation/config colours through
    # slot_color_to_board long after this returns, and both readings must use
    # the same match's permutation.
    global _player_color_swap
    swap = _player_color_swap_for(snapshot.get("state"))
    if swap != _player_color_swap:
        _player_color_swap = swap
    if swap:
        enum_warnings = enum_warnings + (
            "player_colors_swapped:"
            + ",".join(f"{source}->{target}" for source, target in sorted(swap.items())),
        )
    # Live agent payloads contain both the raw SlotModel fields and its initial
    # derived grids. The host adapter owns the complete SlotValue mapping, so
    # raw slots must win; otherwise a newly supported special remains erased by
    # the older derived special_board bundled in the agent.
    if isinstance(snapshot.get("slots"), list):
        rules = (snapshot.get("state") or {}).get("rules") or {}
        fireworks_festival = (rules.get("board_model_name") in (9, "FireworksFestivalBoard")
                              or str(rules.get("id") or "").startswith("fireworks-festival"))
        board, special_board, warnings = _adapt_slots(
            snapshot["slots"], snapshot.get("rows"), snapshot.get("columns"), fireworks_festival
        )
    elif "board" in snapshot and "special_board" in snapshot:
        board = _validated_grid(snapshot["board"], "board")
        special_board = _validated_grid(snapshot["special_board"], "special_board")
        warnings = tuple(str(item) for item in snapshot.get("warnings", ()) if item)
    else:
        board, special_board, warnings = _adapt_slots(snapshot.get("slots"))
    return board, special_board, warnings + enum_warnings


# FloorIsLavaBoard.ColumnsEruptionDictionary: engine column x -> how many
# matches that column has taken since it last erupted. Captured 2026-08-19 on
# "the-floor-is-lava" (boardModelName 36), whose whole mode state is this one
# field -- the pieces themselves carry nothing.
# HotColorBoard keeps both the live hot colour and the one that takes over at
# the end of this move, each with its own bonus. Field names as dumped from the
# live IL2CPP metadata 2026-08-21 (offsets 0x79/0x7a/0x7c/0x80).
HOT_COLOR_FIELDS = {
    "current": "currHotColor",
    "value": "currHotColorsBonus",
    "next": "nextHotColor",
    "next_value": "nextHotColorsBonus",
}


def hot_color_state(snapshot: object) -> dict | None:
    """The mode's current and upcoming hot colour, from the board model.

    ``HotColorBoard.GetMatchStampContribution`` is
    ``Math.Max(0, currHotColorsBonus - 1)`` on top of the tile's own single
    stamp, so the bonus field *is* the tile's total value -- the same 3/4/5 the
    screen reader gets off the badge.

    ``onMoveEnd`` then does ``curr = next; next = GetRandomColor(exclude: curr)``,
    which is what makes the "next" pair worth reading: it is the value table the
    move *after* this one will be scored with, and it is known now.

    None means the snapshot cannot say, which leaves the screen reading in
    charge. A half-known state still returns what it knows, so a missing "next"
    never costs the caller the current colour.
    """
    if not isinstance(snapshot, dict):
        return None
    fields = snapshot.get("board_fields")
    if not isinstance(fields, dict):
        return None
    state: dict[str, int] = {}
    for key, field in HOT_COLOR_FIELDS.items():
        raw = fields.get(field)
        if raw is None:
            continue
        if key in ("current", "next"):
            color = slot_color_to_board(raw)
            if color is not None:
                state[key] = int(color)
            continue
        try:
            state[key] = int(raw)
        except (TypeError, ValueError):
            continue
    return state or None


# Match3Engine.GameState as the engine numbers it live (in-match states are
# negative; see GAME_STATE_LABELS in memory_gui.py): -5 is MovePlaying, the
# only state in which the engine accepts a swipe. -6/-7 are the move being
# processed/ended, -3/-4 the turn machinery, positive values a finished match.
GAME_STATE_MOVE_PLAYING = -5


def move_ready_state(snapshot: object) -> bool | None:
    """True when the engine is waiting for a move (GameState MovePlaying),
    False for any other readable state, None when the snapshot cannot say.

    None must stay distinct from False: an agent build without the state block
    has to read as "unknown" so the caller keeps its existing settle gates,
    not as "the engine is busy" which would deadlock auto.
    """
    if not isinstance(snapshot, dict):
        return None
    state = snapshot.get("state")
    if not isinstance(state, dict):
        return None
    raw = state.get("game_state")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw) == GAME_STATE_MOVE_PLAYING


def charging_colors(snapshot: object) -> tuple[int, ...] | None:
    """Which bot colors charge the booster this match, straight off the rules.

    ``MatchRulesModel.colorComboEnergy`` is the engine's charge table
    (SlotColor -> energy per cleared tile) and ``_colorEnergyOverride`` the
    mode's override; the override wins when it names any color. Both arrive as
    {slot_color_string: int}. multiplier-mushrooms (2026-08-24) charged a
    non-blue color while the simulator credited blue, which is exactly the
    misplay this read exists to prevent.

    None means the snapshot cannot say (old agent build, or empty tables) --
    the caller then keeps the blue-charges default rather than concluding that
    nothing charges.
    """
    if not isinstance(snapshot, dict):
        return None
    state = snapshot.get("state")
    rules = state.get("rules") if isinstance(state, dict) else None
    if not isinstance(rules, dict):
        return None

    def _colors(table: object) -> tuple[int, ...]:
        if not isinstance(table, dict):
            return ()
        colors: list[int] = []
        for raw_key, raw_value in table.items():
            try:
                slot_color = int(raw_key)
                energy = int(raw_value)
            except (TypeError, ValueError):
                continue
            if energy <= 0:
                continue
            color = slot_color_to_board(slot_color)
            if color in (None, EMPTY):
                continue
            if color not in colors:
                colors.append(color)
        return tuple(sorted(colors))

    override = _colors(rules.get("color_energy_override"))
    base = override or _colors(rules.get("color_combo_energy"))
    # The tables only reached the host on 2026-09-22 (the reader allowlist
    # dropped them), so no recording shows real values yet. A table naming
    # every colour of the board singles nothing out, and trusting it would
    # credit every match as charge in every mode; None keeps the blue default
    # the bot has always played with.
    try:
        colors_count = int(rules.get("colors_count") or 0)
    except (TypeError, ValueError):
        colors_count = 0
    if base and len(base) >= max(colors_count, 6):
        return None
    return base or None


def charging_weights(snapshot: object) -> dict[int, int] | None:
    """Energy one cleared tile of each charging bot colour adds, off the same tables.

    The values ``charging_colors`` keeps only the keys of: Color Crystals
    (2026-11-12) charges green 1, orange 2, purple 3, yellow 4 into a 70-point
    meter. None exactly when ``charging_colors`` is None.
    """
    colors = charging_colors(snapshot)
    if not colors:
        return None
    rules = ((snapshot or {}).get("state") or {}).get("rules") or {} if isinstance(snapshot, dict) else {}

    def _table(table: object) -> dict[int, int]:
        out: dict[int, int] = {}
        if not isinstance(table, dict):
            return out
        for raw_key, raw_value in table.items():
            try:
                energy = int(raw_value)
                color = slot_color_to_board(int(raw_key))
            except (TypeError, ValueError):
                continue
            if energy > 0 and color not in (None, EMPTY) and color in colors:
                out[color] = max(out.get(color, 0), energy)
        return out

    weights = _table(rules.get("color_energy_override")) or _table(rules.get("color_combo_energy"))
    return weights or None


# Match3Engine.CellType.Funky. Funky Tiles keeps its marked cells nowhere but in
# CellModel.cellType -- the markers are drawn over the board and have no slot --
# and the agent sends that grid as `cell_types` ([row][col], like `board`).
CELL_TYPE_FUNKY = 3
# Match3Engine.CellType.Vegas. VegasViewsBoard keeps its one tile the same way.
CELL_TYPE_VEGAS = 2
# VegasViewsBoard.get_ScoreMultiplier (rva 0x579928c) reads an override off
# ``extraData`` and falls back to 2 only when the key is missing. The live mode
# card says "Match Vegas Tiles to earn triple score", so the server sends 3;
# without a readable override this is what the bot assumes, not the code's 2.
VEGAS_DEFAULT_MULTIPLIER = 3
VEGAS_MULTIPLIER_KEY_HINTS = ("scoremultiplier", "score_multiplier")


def funky_tile_cells(snapshot: object) -> tuple[tuple[int, int], ...] | None:
    """The Funky Tiles cells as (row, col), straight off ``CellModel.cellType``.

    None means the snapshot does not carry the grid (an older agent, another
    mode, or a read that failed); an empty tuple means the engine has no funky
    cell on the board right now.
    """
    return _cell_type_cells(snapshot, CELL_TYPE_FUNKY)


def vegas_views_state(snapshot: object) -> dict | None:
    """The Vegas tile(s) and the score multiplier they apply.

    ``cells`` comes off ``CellModel.cellType`` like the Funky cells; None means
    the grid was not sent, which is "unknown", never "no tile". The multiplier
    is the board's ``extraData`` override when one is readable, otherwise
    VEGAS_DEFAULT_MULTIPLIER, and ``multiplier_source`` says which.
    """
    cells = _cell_type_cells(snapshot, CELL_TYPE_VEGAS)
    if cells is None:
        return None
    multiplier = None
    for key, value in _board_extra_data(snapshot).items():
        if not _matches_hint(key, VEGAS_MULTIPLIER_KEY_HINTS):
            continue
        try:
            parsed = int(str(value).strip())
        except ValueError:
            continue
        if parsed >= 1:
            multiplier = parsed
            break
    return {
        "cells": cells,
        "multiplier": multiplier or VEGAS_DEFAULT_MULTIPLIER,
        "multiplier_source": "extraData" if multiplier else "default",
    }


def _cell_type_cells(snapshot: object, cell_type: int) -> tuple[tuple[int, int], ...] | None:
    if not isinstance(snapshot, dict):
        return None
    grid = snapshot.get("cell_types")
    if not isinstance(grid, list) or not grid:
        return None
    cells: list[tuple[int, int]] = []
    for row_index, row in enumerate(grid):
        if not isinstance(row, list):
            return None
        for col_index, value in enumerate(row):
            try:
                if int(value) == cell_type:
                    cells.append((row_index, col_index))
            except (TypeError, ValueError):
                return None
    return tuple(cells)


FLOOR_LAVA_ERUPTION_FIELD = "ColumnsEruptionDictionary"

def floor_lava_counts_are_authoritative(snapshot: object) -> bool:
    """Whether this snapshot's lava counter can be taken at its word.

    The engine keeps an entry for every column through the whole match (0 =
    ground whole, 1 = broken), so a counter that arrives with keys is a real
    reading even when no column is at 1. One with no keys is a failed read:
    until 2026-09-18 the agent asked for `count` before `_count`, got null,
    turned that into 0 and reported every dictionary as `{}`.
    """
    return bool(floor_lava_column_counts(snapshot))


def floor_lava_column_counts(snapshot: object) -> dict[int, int]:
    """The engine's per-column lava counter, keyed by bot column index.

    Slots map straight across (row=y, col=x, see _adapt_slots), so an engine x
    is already a bot column. Keys outside the board and negative counts are
    dropped rather than guessed at: an agent build that cannot read the
    dictionary reports a type marker, and that has to read as "unknown", not as
    "no column is marked".
    """
    if not isinstance(snapshot, dict):
        return {}
    fields = snapshot.get("board_fields")
    raw = fields.get(FLOOR_LAVA_ERUPTION_FIELD) if isinstance(fields, dict) else None
    if not isinstance(raw, dict):
        return {}
    size = snapshot.get("columns")
    try:
        size = int(size)
    except (TypeError, ValueError):
        size = 0
    counts: dict[int, int] = {}
    for key, value in raw.items():
        try:
            column = int(key)
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count < 0 or column < 0 or (size > 0 and column >= size):
            continue
        counts[column] = count
    return counts


# JellySE keeps no field for its infected area. ``get_AllInfected`` walks
# player -> logic -> board -> ``extraData`` and deserialises a string kept under
# a key the engine formats per ability type and player index, so the key text is
# not knowable offline -- but the value shape is: DeserializePoints strips
# ``[ ] { } " :`` and splits on commas, i.e. the payload is a plain list of
# ``x,y`` pairs. Entries are therefore classified by what they contain, and the
# key name is only used to confirm a guess, never to find one.
JELLY_ALL_INFECTED_KEY_HINTS = ("allinfected", "all_infected")
JELLY_SOURCE_KEY_HINTS = ("sourcecell", "source_cell")
JELLY_TARGET_COLOR_KEY_HINTS = ("targetcolor", "target_color")
JELLY_PHASE_KEY_HINTS = ("phase",)
JELLY_USES_LEFT_KEY_HINTS = ("usesleft", "uses_left")
# extraData keys that belong to a board model, never to the jelly.
# FloorIsLavaBoard.UpdateColumnsInExtraData writes "columns" and
# "resetGroundOnTurnEnd".
NON_JELLY_EXTRA_DATA_KEYS = frozenset({"columns", "resetGroundOnTurnEnd"})
# Below this the "area" is one stray pair of numbers from some other mode's
# bookkeeping, not a jelly.
JELLY_ZONE_MIN_CELLS = 3


def _board_extra_data(snapshot: object) -> dict[str, str]:
    if not isinstance(snapshot, dict):
        return {}
    raw = snapshot.get("board_extra_data")
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): value if isinstance(value, str) else ""
        for key, value in raw.items()
    }


def _matches_hint(key: str, hints) -> bool:
    folded = key.lower().replace(" ", "")
    return any(hint in folded for hint in hints)


def _serialized_points(value: str, size: int) -> tuple[tuple[int, int], ...]:
    """``x,y`` pairs inside a serialized point list, as (row, col) cells.

    Every integer in the payload is taken in order and paired up, which is what
    the engine's own reader does after it has thrown the punctuation away. A
    payload with an odd count, or one point outside the board, is rejected
    whole: half-read coordinates would repaint the wrong cells, and an empty
    tuple already means "no jelly here".
    """
    numbers = [int(match) for match in re.findall(r"-?\d+", value or "")]
    if not numbers or len(numbers) % 2 or size <= 0:
        return ()
    cells: list[tuple[int, int]] = []
    for index in range(0, len(numbers), 2):
        x, y = numbers[index], numbers[index + 1]
        if not (0 <= x < size and 0 <= y < size):
            return ()
        # Engine points are (x, y) and slots map row=y, col=x (see _adapt_slots).
        cells.append((y, x))
    return tuple(sorted(set(cells)))


def _single_int(value: str) -> int | None:
    numbers = re.findall(r"-?\d+", value or "")
    if len(numbers) != 1:
        return None
    return int(numbers[0])


def jelly_zone_state(snapshot: object) -> dict | None:
    """The jelly's infected area and its state, out of ``BoardModel.extraData``.

    Three answers, and the caller must keep them apart:

    * ``None`` -- memory did not say. An agent build that predates
      ``board_extra_data``, a poll that skipped the engine-decoded read, or a
      dictionary that carries no jelly key at all. The caller keeps whatever
      it had (its screen detector, its last read) rather than concluding the
      board is clean.
    * a state with empty ``cells`` -- memory said "no jelly right now". The
      engine's own deserialiser ran and came back with an empty list (a manual
      dump between one zone being consumed and the next booster throw), or the
      engine-named key sits in the dictionary with nothing in it. This is a
      positive reading and it must overwrite anything cached: a jelly that was
      converted two moves ago is gone, and a zone kept past that point makes
      the bot play conversions that no longer exist (reported 2026-09-12).
    * a state with ``cells`` -- the area; ``target_color`` is the colour the
      area is already committed to (the engine picks it on activation), or
      None.
    """
    if not isinstance(snapshot, dict):
        return None
    try:
        size = int(snapshot.get("columns"))
    except (TypeError, ValueError):
        return None
    extra = _board_extra_data(snapshot)
    jelly = snapshot.get("jelly")
    jelly = jelly if isinstance(jelly, dict) else {}
    keys = jelly.get("keys") if isinstance(jelly.get("keys"), dict) else {}
    named_key = keys.get("all_infected")
    # Best evidence first: on a manual dump the agent runs the engine's own
    # deserialiser, so the cells arrive decoded and no format is being assumed.
    # A list -- empty included -- is the engine speaking; null is the shallow
    # poll that never asked.
    engine_raw = jelly.get("all_infected")
    if isinstance(engine_raw, list):
        engine_cells = _engine_points(engine_raw, size)
        if engine_cells or not engine_raw:
            return _jelly_state_from(engine_cells, named_key, extra, keys, True)
    if not extra:
        return None
    # Next best: the engine named the key, so only the payload is parsed here.
    if isinstance(named_key, str) and named_key in extra:
        cells = _serialized_points(extra[named_key], size)
        if len(cells) >= JELLY_ZONE_MIN_CELLS:
            return _jelly_state_from(cells, named_key, extra, keys, False)
        if not re.search(r"\d", extra[named_key] or ""):
            # The engine's own key with no coordinates behind it: the jelly
            # wrote "nothing here", not "not readable".
            return _jelly_state_from((), named_key, extra, keys, False)
    best_key = None
    best_cells: tuple[tuple[int, int], ...] = ()
    # Guessing a zone from an unnamed key's *content* is only safe when the
    # agent resolved a jelly in this match. extraData is shared: The Floor Is
    # Lava keeps its counter there as "columns": "0,1|1,1|..." -- seven x,value
    # pairs that parse as seven cells. Once the agent's dictionary reader was
    # fixed (2026-09-18) that read as a jelly zone in a match with no jelly and
    # `jelly_before_booster_gate` held the booster back.
    jelly_present = bool(jelly)
    for key, value in extra.items():
        if _matches_hint(key, JELLY_SOURCE_KEY_HINTS):
            continue
        if key in NON_JELLY_EXTRA_DATA_KEYS:
            continue
        if not jelly_present and not _matches_hint(key, JELLY_ALL_INFECTED_KEY_HINTS):
            continue
        cells = _serialized_points(value, size)
        if len(cells) < JELLY_ZONE_MIN_CELLS:
            continue
        named = _matches_hint(key, JELLY_ALL_INFECTED_KEY_HINTS)
        if named:
            best_key, best_cells = key, cells
            break
        if len(cells) > len(best_cells):
            best_key, best_cells = key, cells
    if not best_cells:
        # extraData was read (it has entries), it holds no jelly key, the agent
        # resolved no jelly and nobody brought one: that is memory saying "no
        # jelly", not memory staying silent. Without this the caller falls back
        # to the pixel detector, which on 2026-09-18 22:15 painted a six-cell
        # "zone" over a perk effect in a SweepIt match and held the booster
        # behind jelly_before_booster_gate.
        if not jelly_present and not _anyone_brought_jelly(snapshot):
            return _jelly_state_from((), None, extra, keys, False)
        return None
    return _jelly_state_from(best_cells, best_key, extra, keys, False)


JELLY_SE_ABILITY_TYPE = 60


def jelly_booster_in_match(snapshot: object) -> bool:
    """Whether any player in this match plays JellySE (SpecialAbilityType 60).

    The gate in front of everything jelly: a zone can only exist where that
    booster does. A snapshot that does not name the players' boosters answers
    False -- the memory GUI has no other source, and a guess here is how a
    lava counter became a jelly zone on 2026-09-18.
    """
    if not isinstance(snapshot, dict):
        return False
    state = snapshot.get("state")
    players = state.get("players") if isinstance(state, dict) else None
    if not isinstance(players, list):
        return False
    for player in players:
        try:
            if int(player.get("special_ability_type")) == JELLY_SE_ABILITY_TYPE:
                return True
        except (AttributeError, TypeError, ValueError):
            continue
    return False


def _anyone_brought_jelly(snapshot: dict) -> bool:
    return jelly_booster_in_match(snapshot)


def _engine_points(raw: object, size: int) -> tuple[tuple[int, int], ...]:
    """``[[x, y], ...]`` as the engine's deserialiser returned it."""
    if not isinstance(raw, list) or size <= 0:
        return ()
    cells: list[tuple[int, int]] = []
    for point in raw:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return ()
        try:
            x, y = int(point[0]), int(point[1])
        except (TypeError, ValueError):
            return ()
        if not (0 <= x < size and 0 <= y < size):
            return ()
        cells.append((y, x))
    return tuple(sorted(set(cells)))


def _jelly_state_from(cells, key, extra, keys, verified) -> dict:
    """The area plus whatever else the dictionary says about this jelly.

    A key the engine named is used outright; otherwise the name is matched by
    hint, which is a guess and stays one until a live match confirms it.
    """
    state: dict = {
        "cells": tuple(cells),
        "key": key,
        "verified": bool(verified),
        "target_color": None,
        "phase": None,
        "uses_left": None,
    }
    readers = (
        ("target_color", JELLY_TARGET_COLOR_KEY_HINTS),
        ("uses_left", JELLY_USES_LEFT_KEY_HINTS),
        ("phase", JELLY_PHASE_KEY_HINTS),
    )
    for label, hints in readers:
        named = keys.get(label) if isinstance(keys, dict) else None
        value = None
        if isinstance(named, str) and named in extra:
            value = _single_int(extra[named])
        else:
            for candidate, raw in extra.items():
                if _matches_hint(candidate, hints):
                    value = _single_int(raw)
                    break
        if label == "target_color":
            state[label] = None if value is None else slot_color_to_board(value)
        else:
            state[label] = value
    return state


# A cached zone older than this is not served any more. The agent decodes the
# zone on every manual dump, and the GUI asks for one before each move, so a
# live jelly refreshes the cache many times a minute; a cache this old means
# the reads stopped coming, and a zone nobody has confirmed since is a guess.
JELLY_ZONE_CACHE_MAX_AGE_S = 30.0


class JellyZoneTracker:
    """The jelly zone the bot plays with, across snapshots that may not say.

    The agent decodes the zone only on some snapshots (the engine-decoded read
    runs on manual dumps; the plain poll leaves ``all_infected`` null), while a
    move can start from any snapshot in between. The zone itself only changes
    when the jelly spreads, repaints or is consumed, so the last read is kept
    and served for the silent snapshots.

    What ends the cache, in order of how often it happens:

    * a read that says "no jelly" (``jelly_zone_state`` with empty cells) --
      the engine reports an empty list the moment the zone is consumed and
      keeps reporting it until the next booster throw. Before this the cache
      only ever grew or was replaced, so once a match had seen a jelly the bot
      assumed one for the rest of it (first throw paints two zones, later
      throws one each, and between them there is none);
    * the match boundary (``reset``);
    * age: ``JELLY_ZONE_CACHE_MAX_AGE_S`` without a confirming read.

    ``update`` returns ``(cells, source)``: cells ``None`` means memory did not
    say and nothing is cached (the caller falls back to its screen detector);
    an empty tuple means "no jelly"; ``source`` is ``"memory"``, ``"cache"``,
    ``"cleared"`` (this read emptied a cache), ``"none"`` (memory said no
    jelly, nothing was cached) or ``"unknown"``.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self.cached: dict | None = None

    def reset(self) -> None:
        self.cached = None

    def update(self, snapshot: object) -> tuple[tuple[tuple[int, int], ...] | None, str]:
        state = jelly_zone_state(snapshot)
        if state is not None:
            cells = tuple(state.get("cells") or ())
            if cells:
                self.cached = {
                    "cells": cells,
                    "target_color": state.get("target_color"),
                    "verified": bool(state.get("verified")),
                    "read_at": self._clock(),
                    "served_logged": False,
                }
                return cells, "memory"
            had_cache = self.cached is not None
            self.cached = None
            return (), "cleared" if had_cache else "none"
        cached = self.cached
        if cached is None:
            return None, "unknown"
        if self._clock() - cached["read_at"] > JELLY_ZONE_CACHE_MAX_AGE_S:
            self.cached = None
            return None, "unknown"
        return cached["cells"], "cache"


# Boards whose whole mode state is the players' score multiplier. Decoded from
# libil2cpp.so 2026-08-23 and confirmed against 1285 recorded snapshots.
#
#   34  EveryMoveIncreaseScoreMultiplierBoard ("moves-multiplier")
#       `AfterPerformedSwap` (rva 0x577ee8c) reads the current player's
#       ScoreMultiplier, checks it against a cap, and writes back +1 -- one per
#       move played. Measured: the multiplier walks 1,2,3,...,14 in step with
#       `moves_made_this_turn` over a whole recorded match.
#   22  MultiplierMadnessBoard ("multiplier-madness")
#       `BeforeCombosDestroy` (rva 0x5790184) only raises it for combos of the
#       mode's own colour (`get_MultiplierColors`), by +1, again against a cap,
#       and then reaches for `GetCurrentOpponent().ScoreMultiplier` to take one
#       back off the opponent. `onGameStart` sets both sides to 1. Measured: it
#       stayed at 1 for all 843 snapshots of the recorded match, so that match
#       never matched the multiplier colour.
#
# Both write the same place -- `PlayerModel.scoreMultiplier`, which
# `PlayerControl.get_ScoreMultiplier` (rva 0x57e0d64) reads at model+0x50 --
# so one reader covers both, and Lights Up on top of them.
SCORE_MULTIPLIER_BOARD_MODELS = {
    22: "multiplier-madness",
    34: "moves-multiplier",
    35: "color-climb",
}


def score_multiplier_state(snapshot: object) -> dict | None:
    """Both sides' live score multiplier, off ``PlayerModel.scoreMultiplier``.

    Returns ``None`` when the snapshot carries no players at all (an agent
    build without the state block). A plain match reads x1 on both sides, which
    is a real answer rather than a missing one -- the field exists in every
    mode, it is simply never raised.
    """
    if not isinstance(snapshot, dict):
        return None
    state = snapshot.get("state")
    if not isinstance(state, dict):
        return None
    players = state.get("players")
    if not isinstance(players, (list, tuple)) or not players:
        return None

    def _multiplier(player: object) -> int | None:
        if not isinstance(player, dict):
            return None
        raw = player.get("score_multiplier")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        return max(1, int(raw))

    current = state.get("current_player_index")
    ours = None
    opponent = None
    for index, player in enumerate(players):
        value = _multiplier(player)
        if value is None:
            continue
        seat = player.get("index") if isinstance(player, dict) else None
        is_ours = seat == current if (seat is not None and current is not None) else index == 0
        if is_ours and ours is None:
            ours = value
        elif not is_ours and opponent is None:
            opponent = value
    if ours is None and opponent is None:
        return None
    rules = state.get("rules")
    board_model = rules.get("board_model_name") if isinstance(rules, dict) else None
    try:
        mode = SCORE_MULTIPLIER_BOARD_MODELS.get(int(board_model))
    except (TypeError, ValueError):
        mode = None
    return {
        "ours": ours if ours is not None else 1,
        "opponent": opponent,
        # Which of the two multiplier boards this is, when it is one of them.
        # None means the field was read from a mode that never raises it.
        "mode": mode,
    }


# Color Climb (RainbowMultiplierBoard, 35). The board's only field is
# ``availableColors`` (offset 0x80): ``onGameStart`` fills it with the four
# non-charge colours in a fresh random order, then hands player 0 the first two
# and player 1 the last two (``SetBoardUniquePlayerColors``, decoded from
# libil2cpp.so 2026-09-13, rva 0x57950d0). The list never changes after that,
# which the 420 recorded frames confirm: it reorders exactly once, on the
# frame where every player's multiplier goes 0 -> 1.
COLOR_CLIMB_BOARD_MODEL = 35
COLOR_CLIMB_COLORS_FIELD = "availableColors"
COLOR_CLIMB_COLORS_PER_PLAYER = 2


# PlayerClientControl.Type of the local side (memory_gui.PLAYER_TYPE_LOCAL).
_PLAYER_TYPE_LOCAL = 0


def _player_multiplier(player: object) -> int | None:
    if not isinstance(player, dict):
        return None
    raw = player.get("score_multiplier")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return int(raw)


def color_climb_state(snapshot: object, seat: int | None = None) -> dict | None:
    """Our two multiplier colours in Color Climb, plus both live multipliers.

    Returns ``None`` when the snapshot cannot say: no ``board_fields`` sweep,
    no ``availableColors`` list, or a board that has not started yet (every
    multiplier still 0 -- the pre-shuffle order is not a dealt pair). Colours
    are bot colour codes; ``seat`` is which pair we were dealt.

    The seat is *ours*, not whoever is on turn: the pair is fixed for the
    match, and reading the current player's pair would hand us the opponent's
    colours on their half of a versus match (the 2026-08-25 versus recording
    flips ``current_player_index`` 0/1 every turn). The caller may pass the
    seat it already resolved; otherwise the local ``player_type`` decides,
    then the player on turn, then seat 0.
    """
    if not isinstance(snapshot, dict):
        return None
    fields = snapshot.get("board_fields")
    if not isinstance(fields, dict):
        return None
    raw = fields.get(COLOR_CLIMB_COLORS_FIELD)
    if not isinstance(raw, (list, tuple)) or len(raw) < 2 * COLOR_CLIMB_COLORS_PER_PLAYER:
        return None
    try:
        codes = [int(value) for value in raw]
    except (TypeError, ValueError):
        return None
    state = snapshot.get("state")
    state = state if isinstance(state, dict) else {}
    players = state.get("players")
    players = [p for p in (players if isinstance(players, (list, tuple)) else []) if isinstance(p, dict)]
    multipliers = [m for m in (_player_multiplier(p) for p in players) if m is not None]
    if multipliers and max(multipliers) <= 0:
        # onGameStart has not run: the list is still the constructor's order.
        return None
    if not (isinstance(seat, int) and not isinstance(seat, bool)):
        seat = None
        for player in players:
            if player.get("player_type") == _PLAYER_TYPE_LOCAL and isinstance(player.get("index"), int):
                seat = int(player["index"])
                break
        if seat is None:
            current = state.get("current_player_index")
            if isinstance(current, int) and not isinstance(current, bool):
                seat = current
        if seat is None:
            seat = 0
    first = codes[:COLOR_CLIMB_COLORS_PER_PLAYER]
    last = codes[-COLOR_CLIMB_COLORS_PER_PLAYER:]
    ours_raw, theirs_raw = (first, last) if seat == 0 else (last, first)

    def _to_board(values):
        colors = []
        for value in values:
            color = slot_color_to_board(value)
            if color is not None and color not in colors:
                colors.append(color)
        return tuple(colors)

    ours = _to_board(ours_raw)
    if len(ours) != COLOR_CLIMB_COLORS_PER_PLAYER:
        return None
    multiplier = None
    opponent = None
    for index, player in enumerate(players):
        value = _player_multiplier(player)
        if value is None:
            continue
        player_seat = player.get("index") if isinstance(player.get("index"), int) else index
        if player_seat == seat and multiplier is None:
            multiplier = value
        elif player_seat != seat and opponent is None:
            opponent = value
    return {
        "colors": ours,
        "opponent_colors": _to_board(theirs_raw),
        "seat": seat,
        "multiplier": max(1, multiplier if multiplier is not None else 1),
        "opponent_multiplier": None if opponent is None else max(1, opponent),
    }


LIGHTS_UP_COLUMN_FIELD = "CurrentActiveColumn"
LIGHTS_UP_RANDOM_FIELD = "RandomColumnChange"


def lights_up_state(snapshot: object) -> dict | None:
    """Which column is lit in Lights Up, straight off ``LightsUpBoard``.

    The mode's entire state is two fields (IL2CPP metadata 2026-08-21, offsets
    0x7c/0x80): ``CurrentActiveColumn`` is the column the game draws lit, and
    ``RandomColumnChange`` says how ``onMoveEnd`` moves it -- a fresh
    ``RandomWrapper::Range`` that is re-rolled until it differs from the
    current one when true, a plain +1 with wrap when false.

    Engine x is already a bot column (``_adapt_slots`` maps row=y, col=x), so
    the number needs no translation, only a range check: a column outside the
    board means the field was not read, not that column -1 is lit.

    Read-only, and deliberately so -- this is what the readout shows, and
    nothing scores off it.
    """
    if not isinstance(snapshot, dict):
        return None
    fields = snapshot.get("board_fields")
    if not isinstance(fields, dict):
        return None
    raw = fields.get(LIGHTS_UP_COLUMN_FIELD)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return None
    try:
        column = int(raw)
    except (TypeError, ValueError):
        return None
    try:
        size = int(snapshot.get("columns"))
    except (TypeError, ValueError):
        size = 0
    if column < 0 or (size > 0 and column >= size):
        return None
    state: dict[str, object] = {"column": column}
    random_change = fields.get(LIGHTS_UP_RANDOM_FIELD)
    if isinstance(random_change, bool):
        state["random_change"] = random_change
    return state


COLUMN_MANIA_PENDING_FIELD = "colsToIncrease"


def column_mania_state(snapshot: object) -> dict | None:
    """Per-column score multipliers in Column Mania, off ``ColumnManiaBoard``.

    The compiled hooks (IL2CPP 2026-08-21, rva 0x5778ba8/0x5778c3c/0x577935c)
    spell the whole mode out.  ``onGameStart`` writes multiplier 1 into every
    cell.  ``AfterPerformedSwap`` appends the distinct column of every slot in
    ``combosToDestroy`` to ``colsToIncrease``, so the list grows across the
    cascades of one move.  ``onMoveEnd`` walks the columns, and for each one in
    that list raises the whole column to ``min(current + 1, MaxMultiplier)``,
    then clears the list.  ``MaxMultiplier`` comes off ``extraData`` and falls
    back to 99, i.e. in practice there is no cap.

    Note the two halves are read from different places: the standing multiplier
    is per cell (``cell_multipliers``, added to the agent for this mode), while
    ``colsToIncrease`` is the not-yet-applied delta for the move in flight.  A
    reader that only had the second one could not score, because it never sees
    the moves played before it attached.
    """
    if not isinstance(snapshot, dict):
        return None
    raw = snapshot.get("cell_multipliers")
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    multipliers: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        multiplier = int(value)
        if multiplier < 1:
            return None
        multipliers.append(multiplier)
    try:
        size = int(snapshot.get("columns"))
    except (TypeError, ValueError):
        size = 0
    if size > 0 and len(multipliers) != size:
        return None
    pending_columns: list[int] = []
    fields = snapshot.get("board_fields")
    if isinstance(fields, dict):
        pending = fields.get(COLUMN_MANIA_PENDING_FIELD)
        if isinstance(pending, (list, tuple)):
            pending_columns = sorted(
                {
                    int(column)
                    for column in pending
                    if not isinstance(column, bool)
                    and isinstance(column, (int, float))
                    and 0 <= int(column) < len(multipliers)
                }
            )
    return {"multipliers": multipliers, "pending_columns": pending_columns}


def load_memory_board_snapshot(
    path: str | os.PathLike | None = None,
    *,
    max_age_seconds: float | None = DEFAULT_MEMORY_MAX_AGE_SECONDS,
) -> BoardSourceResult:
    snapshot_path = Path(path) if path is not None else configured_memory_snapshot_path()
    if max_age_seconds is not None:
        try:
            age = max(0.0, time.time() - snapshot_path.stat().st_mtime)
        except FileNotFoundError as exc:
            raise MemoryBoardUnavailable(
                f"Memorijski reader nije pokrenut: nema {snapshot_path}"
            ) from exc
        if age > float(max_age_seconds):
            raise MemoryBoardUnavailable(
                f"Memorijski snapshot je zastareo ({age:.1f}s > {max_age_seconds:.1f}s)"
            )

    payload = _last_json_object(snapshot_path)
    snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), dict) else payload
    board, special_board, warnings = adapt_memory_snapshot_payload(snapshot)
    return BoardSourceResult(
        board=board,
        special_board=special_board,
        source=BOARD_SOURCE_MEMORY,
        snapshot=snapshot,
        warnings=warnings,
    )


def read_selected_board(
    source: object,
    ml_reader: Callable[[], tuple[list[list[int]], list[list[int]]]],
    *,
    memory_path: str | os.PathLike | None = None,
    max_memory_age_seconds: float | None = DEFAULT_MEMORY_MAX_AGE_SECONDS,
) -> BoardSourceResult:
    selected = normalize_board_source(source)
    if selected == BOARD_SOURCE_ML:
        board, special_board = ml_reader()
        return BoardSourceResult(board, special_board, BOARD_SOURCE_ML)
    try:
        return load_memory_board_snapshot(
            memory_path,
            max_age_seconds=max_memory_age_seconds,
        )
    except MemoryBoardUnavailable as exc:
        if selected == BOARD_SOURCE_MEMORY:
            raise
        board, special_board = ml_reader()
        return BoardSourceResult(
            board,
            special_board,
            BOARD_SOURCE_ML,
            fallback_reason=str(exc),
        )
