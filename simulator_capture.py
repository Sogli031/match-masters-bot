"""Portable capture ingestion. Loading evidence does not certify simulator support."""
from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path


def load_capture(directory: str | Path) -> dict:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Nepodrzana verzija capture paketa")
    if not {"profile.json", "simulator_input.json"} <= manifest.get("files", {}).keys():
        raise ValueError("Manifest nema obavezne fajlove")
    for name, digest in manifest["files"].items():
        path = (directory / name).resolve()
        if path.parent != directory.resolve():
            raise ValueError("Neispravna putanja u manifestu")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Capture checksum mismatch: {name}")
    profile = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
    return {"manifest": manifest, "profile": profile,
            "simulator_input": json.loads((directory / "simulator_input.json").read_text(encoding="utf-8"))}


def decode_dictionary(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise ValueError("Dictionary nije procitan")
    result = {}
    for item in raw["entries"]:
        key = item["key"]
        if key in result:
            raise ValueError("Dupliran dictionary kljuc")
        result[key] = item["value"]
    return result


def resolve_square_overrides(profile):
    """The Square Match Solo view of resolve_refill_overrides (its first evidence)."""
    rules = profile["rules"]
    if rules.get("id") != "square-match" or rules.get("pvpMode") != 1:
        return {"resolved": False, "reason": "Resolver obuhvata samo Square Match Solo"}
    return resolve_refill_overrides(profile)


def threshold_hypotheses(profile):
    """Candidate prevention thresholds for the not-yet-ported adaptive branch.

    The four Range(0,100) rolls per hole are drawn whatever the thresholds
    are (verified for the last-round branch), so trying these against a
    recorded transition tells which one the engine used. Evidence, not a port.
    """
    rules = profile.get("rules") or {}
    spawn = ((profile.get("config") or {}).get("spawnEngine")) or {}
    square = bool((profile.get("spawning") or {}).get("<SquareMatchesAvailable>k__BackingField"))

    def make(match, combo, special, sq):
        return {"match": match, "combo": combo, "special_combo": special, "square": sq if square else -1}

    out = {"poslednja runda (100)": make(100, 100, 100, 100), "bez sprecavanja (-1)": make(-1, -1, -1, -1)}
    override = rules.get("refillLogicOverride")
    if isinstance(override, dict) and "preventMatchChance" in override:
        out["refillLogicOverride"] = make(override.get("preventMatchChance"), override.get("preventComboChance"),
                                          override.get("preventSpecialComboChance"),
                                          override.get("preventSquareMatchChance"))
    if spawn.get("preventMatchBaselineChance") is not None:
        out["spawn baseline"] = make(spawn["preventMatchBaselineChance"], spawn.get("preventComboBaselineChance"),
                                     spawn.get("preventComboBaselineChance"), spawn["preventMatchBaselineChance"])
    if spawn.get("preventMatchMinimumChance") is not None:
        out["spawn minimum"] = make(spawn["preventMatchMinimumChance"], spawn.get("preventComboMinimumChance"),
                                    spawn.get("preventComboMinimumChance"), spawn["preventMatchMinimumChance"])
    return {name: t for name, t in out.items() if all(isinstance(v, int) for v in t.values())}


def versus_adaptive_thresholds(profile):
    """FillAllEmptySlots 0x5a08978-0x5a08e58 for a two-player Versus turn.

    GetScoreDifference adds the current player's remaining moves times the
    configured move estimate. The final spawnBonus correction is taken from
    the two PlayerModel values, not inferred from the visible score.
    """
    rules, state = profile["rules"], profile["state"]
    spawn = (profile.get("config") or {}).get("spawnEngine") or {}
    players = profile.get("players") or []
    if rules.get("pvpMode") != 0 or len(players) != 2 or spawn.get("rubberBanding") is not True:
        return None
    moves, turns, index = state.get("moves"), state.get("<Turns>k__BackingField"), state.get("currentPlayerIndex")
    required = (spawn.get("maxDifferenceForPrevent"), spawn.get("preventMatchBaselineChance"),
                spawn.get("preventComboBaselineChance"), spawn.get("preventComboMinimumChance"),
                spawn.get("preventMatchMinimumChance"), spawn.get("moveScoreEstimate"), moves, turns, index)
    if any(type(value) is not int for value in required) or moves < 0 or turns <= 0 or required[0] <= 0:
        return None
    models = [player.get("model") or {} for player in players]
    if any(type(model.get(key)) is not int for model in models for key in ("index", "score", "spawnBonus")):
        return None
    current = next((model for model in models if model["index"] == index), None)
    opponent = next((model for model in models if model["index"] != index), None)
    if current is None or opponent is None:
        return None
    maximum, match_base, combo_base, combo_min, match_min, estimate = required[:6]
    score_difference = current["score"] - opponent["score"] + moves * estimate
    difference = max(-maximum, min(maximum, score_difference))
    ratio = Fraction(difference, maximum)
    match_slope = 100 - match_base if score_difference > 0 else match_base
    combo_slope = (100 - combo_base if (moves > 0) == (score_difference > 0) else combo_base)
    match = round(match_base + ratio * match_slope)
    combo = round(combo_base + ratio * combo_slope)
    bonus_difference = current["spawnBonus"] - opponent["spawnBonus"]
    override = rules.get("refillLogicOverride") or {}
    special_override = override.get("preventSpecialComboChance", 0)
    square_override = override.get("preventSquareMatchChance", 0)
    if type(special_override) is not int or type(square_override) is not int:
        return None
    return {"match": min(100, max(match_min, match - bonus_difference)),
            "combo": min(100, max(combo_min, combo + bonus_difference)),
            "special_combo": max(0, special_override),
            "square": square_override if square_override >= 1 and
            (profile.get("spawning") or {}).get("<SquareMatchesAvailable>k__BackingField") else -1}


def resolve_refill_overrides(profile):
    """Resolve fixed thresholds and the supported two-player adaptive branch.

    The branch test (Rounds == RoundsTotal, 0x5a08bdc) reads only the round
    counters and refillLogicOverride, nothing mode-specific. In Versus the
    counters decrease, so equality identifies the first round. It was verified
    on Square Match Solo; other modes are checked by tools/verify_refill.py.
    Thresholds are not guarantees about the final board: the engine has
    bounded retries/fallbacks and a separate weighted color pool.
    """
    rules, state = profile["rules"], profile["state"]
    if rules.get("disableMatchPrevention") is not False:
        return {"resolved": False, "reason": "Nije potvrdjeno disableMatchPrevention=false za ovu konfiguraciju",
                "threshold_hypotheses": threshold_hypotheses(profile)}
    count = len(profile["players"])
    if not count:
        raise ValueError("Nema igraca za racunanje rundi")
    turns, total = state["<Turns>k__BackingField"], state["<TurnsTotal>k__BackingField"]
    if not isinstance(turns, int) or not isinstance(total, int):
        raise ValueError("Brojaci rundi nisu procitani")
    last_round = math.ceil(turns / count) == math.ceil(total / count)
    override = rules.get("refillLogicOverride")
    if isinstance(override, dict) and "disableFirstRoundLogic" not in override:
        raise ValueError("refillLogicOverride nije dekodiran")
    fixed = last_round and (override is None or override["disableFirstRoundLogic"] is False)
    prevention = ({"match": 100, "combo": 100, "special_combo": 100,
                   "square": 100 if profile["spawning"]["<SquareMatchesAvailable>k__BackingField"] else -1}
                  if fixed else None)
    # FillAllEmptySlots 0x5a08c70/0x5a08d00 uses positive overrides in
    # place of the adaptive match/combo formula. The two remaining fields
    # are clamped to >=0 and >=1 respectively (zero square means disabled).
    explicit = (not fixed and isinstance(override, dict)
                and override.get("preventMatchChance", 0) > 0
                and override.get("preventComboChance", 0) > 0)
    if explicit:
        prevention = {"match": override["preventMatchChance"],
                      "combo": override["preventComboChance"],
                      "special_combo": max(0, override["preventSpecialComboChance"]),
                      "square": override["preventSquareMatchChance"]
                      if override["preventSquareMatchChance"] >= 1 else -1}
        fixed = True
    adaptive_used = False
    if not fixed:
        adaptive = versus_adaptive_thresholds(profile)
        if adaptive is not None:
            prevention = adaptive
            fixed = True
            adaptive_used = True
    return {"resolved": fixed, "last_round": last_round,
            "branch": ("FillAllEmptySlots explicit positive overrides" if explicit else
                       "FillAllEmptySlots Versus adaptive formula" if adaptive_used else
                       "FillAllEmptySlots 0x5a08bdc -> 0x5a08d8c" if fixed else "adaptive formula not yet ported"),
            "prevention_thresholds": prevention,
            "prevention_test": "RandomWrapper.Range(0,100) <= threshold",
            "raw_refill_override": override,
            "color_score_engine": decode_dictionary(rules.get("_colorScoreOverride")),
            "color_energy_engine": decode_dictionary(rules.get("_colorEnergyOverride")),
            "rule_gem_weights": decode_dictionary(rules.get("_gemWeights")),
            "effective_initial_spawn": profile["spawning"]["initialSpawnParams"],
            "initial_spawn_overrides": rules.get("initialSpawnParamsOverrides"),
            "game_colors_engine": profile["spawning"]["gameColors"],
            "base_color_weights": decode_dictionary(profile["spawning"]["baseColorWeights"]),
            "current_color_weights": decode_dictionary(profile["spawning"]["colorWeights"]),
            "weights_randomizer": rules.get("weightsRandomizer"),
            "max_booster_uses_per_turn": rules.get("maxBoosterUsesPerTurn"),
            "threshold_hypotheses": None if fixed else threshold_hypotheses(profile),
            "note": "Resolved thresholds/configuration, not a complete refill implementation."}


def capture_mode(profile):
    """The match's GameMode, from the rules read out of memory.

    Same lookup as the live Memory GUI (rules id, then board model, then rule
    flags), so a capture and the live bot name the mode alike.
    """
    import move_strategy as ms
    from memory_gui import MemoryWindow

    rules = profile.get("rules") or {}
    live_rules = {"id": rules.get("id"), "board_model_name": rules.get("boardModelName"), "engine_fields": rules}
    return MemoryWindow._effective_mode({"rules": live_rules})


MUTATION_SPECIALS_AUTO_EXPLODE = 6
MUTATION_MATCHES_CREATE_SPECIALS = 7
MUTATION_DESTROY_ROW_ON_HORIZONTAL_MATCH = 22
MUTATION_DESTROY_COLUMN_ON_VERTICAL_MATCH = 23
MUTATION_MATCHES_DESTROY_COLOR = 25
MUTATION_VERTICAL_MATCH_DESTROY_COLOR = 30


def active_mutation_types(mutations) -> set[int]:
    """Mutation Lab: which mutation types are in force right now.

    `GameLogic.mutationsActivatedList` holds every mutation the player has
    picked, spent ones included -- the instant picks stay in the list with
    `isActivated` false once they have fired. Only the still-active ones may
    change how a move is scored, which is what that flag separates.
    """
    types: set[int] = set()
    for mutation in mutations or []:
        if not isinstance(mutation, dict):
            continue
        config = mutation.get("config")
        config = config if isinstance(config, dict) else {}
        if not config.get("isActivated"):
            continue
        try:
            types.add(int(mutation["type"]))
        except (KeyError, TypeError, ValueError):
            continue
    return types


def lab_move(capture: dict, *, thresholds=None) -> dict:
    """Strategy Lab state from load_capture(), carrying the ported refill.

    ``thresholds`` stands in for the unported adaptive prevention formula
    (see threshold_hypotheses). Raises engine_refill.UnsupportedRefill
    outside the ported branches.
    """
    from engine_refill import EngineRefill, UnsupportedRefill

    profile, data = capture["profile"], capture["simulator_input"]
    rules = profile["rules"]
    extra = decode_dictionary(rules.get("_extraData")) or {}
    local = next(p["model"] for p in profile["players"] if p.get("player_type") == 0)
    # Empty is a real answer (a mode without a colour score override); only a
    # missing value falls back to the profile, which research records lack.
    score_values = data.get("score_rally_values")
    if score_values is None:
        score_values = prepare_input(profile)["score_rally_values"]
    model = EngineRefill.from_profile(profile, thresholds=thresholds)
    model.billie = data.get("billie")
    if data.get("mixy_player"):
        from engine_mixy import MixyPassive
        from engine_refill import color_maps
        model.mixy = MixyPassive.from_player(data["mixy_player"], color_maps(profile)[1])
    # A mutation leaves the rule field false for the whole match, so a replay that
    # reads only the rules plays a different game (10 of 36 on 20261104_145643).
    mutations = active_mutation_types(data.get("active_mutations"))
    # Funky Tiles (FunkyTilesBoard, model 12): the funky cells are a board-cell
    # layer (CellModel.cellType 3), not slots. A recording without the grid
    # replays another board, so it is not checkable rather than a miss.
    funky_cells = None
    if rules.get("boardModelName") == FUNKY_TILES_BOARD:
        grid = data.get("cell_types")
        if not isinstance(grid, list) or not grid:
            raise UnsupportedRefill("Funky Tiles: cell types missing from recording")
        funky_cells = [(r, c) for r, row in enumerate(grid) for c, v in enumerate(row)
                       if int(v) == FUNKY_CELL_TYPE]
    return {"mode": capture_mode(profile).value, "rules_id": rules.get("id"),
            "funky_cells": funky_cells,
            "floor_lava_columns": data.get("floor_lava_columns"),
            "board": data["board"], "special_board": data["special_board"],
            "allow_square_matches": bool(extra.get("allowSquareMatches")
                                         or profile["spawning"].get("<SquareMatchesAvailable>k__BackingField")),
            # GameLogic.IsSingleplayerBoard: one player on the board. Showdown is
            # pvpMode 2 with one player, and Color Crush wiped its reds there
            # (Debug/refill_misses 20261107_1632-1633, 8 false misses).
            "single_player_board": rules.get("pvpMode") == 1 or len(profile.get("players") or []) == 1,
            "froggy_params": data.get("froggy_params"),
            "jelly_zone_cells": data.get("jelly_zone_cells"),
            "jelly_uses_left": data.get("jelly_uses_left"),
            "all_specials_lightning": bool(rules.get("allSpecialsLightning")),
            "every_match_is_special": bool(rules.get("everyMatchIsSpecial"))
            or MUTATION_MATCHES_CREATE_SPECIALS in mutations,
            "specials_explode_immediately": bool(rules.get("specialsAutoExplode"))
            or MUTATION_SPECIALS_AUTO_EXPLODE in mutations,
            "vertical_matches_destroy_color": bool(rules.get("verticalMatchDestroyColor"))
            or MUTATION_VERTICAL_MATCH_DESTROY_COLOR in mutations,
            "matches_destroy_color": MUTATION_MATCHES_DESTROY_COLOR in mutations,
            "line_destruction": (bool(rules.get("destroyRowOnHorizontalMatch"))
                                 or MUTATION_DESTROY_ROW_ON_HORIZONTAL_MATCH in mutations,
                                 bool(rules.get("destroyColumnOnVerticalMatch"))
                                 or MUTATION_DESTROY_COLUMN_ON_VERTICAL_MATCH in mutations),
            "score": local["score"],
            "score_values": {int(k): v for k, v in score_values.items()},
            "solo_targets": profile["rules"].get("soloTargets") or [],
            "turn_state": {"remaining_moves": profile["state"]["moves"]},
            "booster_state": {"current": local["energy"], "maximum": booster_cost(profile)
                              if booster_cost(profile) is not None else data.get("booster_cost")},
            "booster_type": local.get("specialAbilityType"),
            "perks": {int(k): v for k, v in (decode_dictionary(local.get("boardAbilities")) or {}).items()},
            # Perk buttons follow the player's board_abilities order (slot 1, 2).
            "perk_slots": {ability.get("<Type>k__BackingField"): slot for slot, ability in enumerate(
                next(p for p in profile["players"] if p.get("player_type") == 0).get("board_abilities") or [], 1)},
            "engine_refill": model}


FUNKY_TILES_BOARD = 12
FUNKY_CELL_TYPE = 3     # board_source.CELL_TYPE_FUNKY


def booster_cost(profile):
    player = next(p for p in profile["players"] if p.get("player_type") == 0)
    return ((player.get("ability") or {}).get("<Config>k__BackingField") or {}).get("cost")


def prepare_input(profile: dict) -> dict:
    import board_source

    raw_board = profile["board"]
    players = [{"index": p["model"].get("index"), "slot_type": p["model"].get("slotType"),
                "player_type": p.get("player_type")} for p in profile["players"] if p.get("model")]
    snapshot = {"rows": raw_board["rows"], "columns": raw_board["columns"],
                "slots": raw_board["slots"], "state": {"players": players}}
    board, special, warnings = board_source.adapt_memory_snapshot_payload(snapshot)
    local = [p for p in players if p["player_type"] == 0]
    score = decode_dictionary(profile["rules"].get("_colorScoreOverride"))
    return {"schema_version": 1, "rules_id": profile["rules"].get("id"),
            "pvp_mode": profile["rules"].get("pvpMode"),
            "board": board, "special_board": special,
            "local_player_index": local[0]["index"] if len(local) == 1 else None,
            "board_warnings": list(warnings), "source": "profile.json",
            "score_rally_values": {str(board_source.slot_color_to_board(k)): v for k, v in (score or {}).items()},
            "resolved_overrides": resolve_refill_overrides(profile),
            "configuration_captured": True,
            "full_simulation_ready": False,
            "limitations": ["Paket cuva podatke; kompletan engine dopune i svih modova jos nije portovan.",
                            "Jedan snapshot ne sadrzi svaku buducu promenu parametara ili serversku rotaciju."]}
