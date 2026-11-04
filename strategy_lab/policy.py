"""Pure selection over observable native candidates; shared by replay and live.

Utilities are NOT game points. Unsupported action families cause an explicit
fallback, rather than being silently removed from a policy's search space.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

POLICY_VERSION = "1"
VARIANTS = ("existing", "direct", "extra", "charge")
FEATURES = ("score", "cleared_cells", "direct_extra_moves", "blue_cells")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def format_key(context):
    if context.get("is_solo_challenge") or context.get("solo_challenge"):
        return "solo_challenge"
    return {"versus_2": "versus", "solo_6": "solo_unclassified"}.get(context.get("mode"), "unknown")


def identity(move):
    """Equipped slots stay in the key after consumption; available slots do not.

    'default' is retained as unknown, never interpreted as an empty booster.
    The ability id is taken from the existing native observer when available.
    """
    context = move.get("strategy_context") or {}
    slots = move.get("perk_slot_status") or []
    equipped = [s.get("perk") or "none" for s in sorted(slots, key=lambda s: s.get("slot", 0))]
    if len(equipped) != 2:
        equipped = list(move.get("selected_perks") or ["unknown", "unknown"])
    ability = (move.get("ufo") or {}).get("ability_type")
    goal = context.get("solo_goal") or "score"
    if isinstance(goal, dict):
        goal = {k:v for k,v in goal.items() if k not in ("score", "multiplier")}
    return {
        "format": format_key(context), "mode": str(move.get("mode", "unknown")),
        "goal": goal,
        "setup": {"booster": ability if ability is not None else move.get("active_booster", "unknown"),
                  "booster_action": move.get("booster_action_mode", "unknown"),
                  "special_piece_mode": move.get("special_piece_mode", "unknown"), "perks": equipped},
        "flags": {**{k: move.get(k) for k in (
            "allow_square_matches", "specials_explode_immediately", "color_crush",
            "energized_colors", "engine_charge_colors", "mushroom_multipliers",
            "vertical_matches_destroy_color", "matches_destroy_color", "all_specials_lightning",
            "every_match_is_special", "line_destruction")},
            "single_player_board":move.get("single_player_board",context.get("mode")=="solo_6")},
    }


def action_key(action):
    return canonical({"kind": action.get("kind", "swap"), "start": action.get("start"),
                      "target": action.get("target"), "direction": action.get("direction")})


def observable(move):
    """A whitelist: no outcomes, seed, future frames or observed delta."""
    return {"identity": identity(move), "board": move.get("board"),
            "special_board": move.get("special_board"),
            "booster_ready": (move.get("booster_detection") or {}).get("active"),
            "available_perks": list(move.get("selected_perks") or ()),
            "turn": move.get("turn_state") or {},
            "selected_action": move.get("selected_action"),
            "manual_action": move.get("action"),
            "mixy_active": bool((move.get("mixy_meow") or {}).get("active")),
            "ufo_eyes": (move.get("ufo") or {}).get("eyes", 0)}


def native_action(evaluation):
    """Preserve native execution orientation, including special combinations."""
    import move_strategy as ms
    start, direction = ms.oriented_swipe(evaluation)
    dr, dc = ms.DIRECTION_STEPS[ms.Direction(direction)]
    return {"kind": "swap", "start": list(start), "target": [start[0] + dr, start[1] + dc],
            "direction": str(direction), **{k: float(getattr(evaluation, k, 0)) for k in FEATURES},
            "uncertain": any(e.get("type") == "uncertain_refill_boundary"
                             for e in getattr(evaluation, "intent_events", ())) }


def recorded_action(payload):
    if not payload or payload.get("start") is None:
        return None
    values = {k: float(payload.get(k) or 0) for k in FEATURES}
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("non-finite candidate")
    return {"kind": "swap", "start": list(payload["start"]), "target": list(payload["target"]),
            "direction": payload["direction"], **values,
            "uncertain": any(e.get("type") == "uncertain_refill_boundary"
                             for e in payload.get("intent_events", ())) }


@dataclass(frozen=True)
class Choice:
    action: dict | None
    reason: str
    fallback: bool = False


def support_reason(state):
    from .simulation import PREFIX_MODES, ORDINARY_SPECIALS
    if state["identity"]["mode"] not in PREFIX_MODES:
        return "incomplete_mode: no certified prefix transition"
    if state["identity"]["format"] == "unknown":
        return "unknown_format"
    if state["identity"]["setup"]["booster"] in ("default", "unknown", None):
        return "unknown_equipped_booster"
    if any(v not in ORDINARY_SPECIALS for row in state.get("special_board") or [] for v in row):
        return "random_or_equipment_special: transition not modeled"
    import move_strategy as ms
    if ms.find_matches(state.get("board"),
                       allow_square_matches=bool(state["identity"]["flags"].get("allow_square_matches")),
                       special_board=state.get("special_board")):
        return "unsettled_board: existing matches need a fresh native scan"
    if state.get("manual_action") not in ("auto", "best", "highest_points", None):
        return "manual_action_preserved"
    if state.get("selected_action") != "move":
        return "native_booster_or_perk_action_preserved"
    if state.get("booster_ready") is not False:
        return "booster_ready_or_unknown: alternative activation effect not modeled"
    if any(p not in ("none", None) for p in state.get("available_perks", ())):
        return "available_perk: alternative perk effects not modeled"
    if state.get("mixy_active") or state.get("ufo_eyes"):
        return "passive_booster_effect_not_modeled"
    return None


def choose_action(state, legal_actions, variant, baseline, expected_identity=None):
    """No gates run after this selector; the runtime executes its native object.

    'legal_actions' here is the native observable candidate pool. This version
    supports swap-only decision states, not equipment ranking or full matches.
    """
    if variant not in VARIANTS:
        return Choice(baseline, "unknown_profile", True)
    if variant == "existing":
        return Choice(baseline, "existing_strategy")
    if expected_identity is not None and canonical(expected_identity) != canonical(state["identity"]):
        return Choice(baseline, "profile_identity_mismatch", True)
    reason = support_reason(state)
    if reason:
        return Choice(baseline, reason, True)
    candidates = [a for a in legal_actions if a is not None]
    if not candidates:
        return Choice(baseline, "no_native_candidates", True)
    def utility(a):
        if variant == "direct":
            return a["cleared_cells"]
        if variant == "extra":
            return a["cleared_cells"] + 15 * min(1, a["direct_extra_moves"])
        return a["cleared_cells"] + 4 * a["blue_cells"] + 8 * min(1, a["direct_extra_moves"])
    winner = min(candidates, key=lambda a: (-utility(a), action_key(a)))
    return Choice(winner, f"{variant}: native cleared tiles / guaranteed extra / charge utility; not game points")
