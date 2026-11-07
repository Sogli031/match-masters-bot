"""Naucene korekcije rangiranja, iz odigranih partija (Debug/runs).

Dva fajla, oba opciona -- kada ih nema, sve ovde vraca neutralne vrednosti i
`move_strategy` se ponasa isto kao pre:

* ``data/learned_weights.json`` (pise ``tools/fit_weights.py``)
    - realizacija plavih: koliko punjenja metra stvarno donese jedna predvidjena
      plava celija, odvojeno za direktne (u samom mecu) i posredne (kaskade,
      specijali) -- mnozilac na ``blue_cells`` pre cenovnika u
      ``_weighted_priority``;
    - realizacija extra poteza: u kom procentu je obecan extra stvarno zadrzao
      potez, po vrsti (direktan / pouzdana kaskada / nepouzdana kaskada);
    - skala buducnosti: koliko ``lookahead_bonus`` + ``board_potential`` zaista
      vredi na sledecem potezu.
* ``models/move_value_model.json`` (pise ``tools/train_value_model.py``)
    - gradient-boosted stabla nad osobinama kandidata, konteksta i table;
      predvidjaju *rezidual*: koliko je stvarna vrednost poteza (poeni + punjenje
      + zadrzan potez, u jedinicama simulatora) odstupila od onoga sto
      heuristicka ocena ``score`` obecava. Na kraju rangiranja se dodaje
      ``blend * rezidual`` -- kandidati koje heuristika sistematski precenjuje
      padaju, potcenjeni rastu, prosek je nula.

Iskljucivanje bez brisanja fajlova: promenljiva okruzenja
``MEMORY_GUI_LEARNED_VALUE=0``. Sve funkcije su otporne na greske: model koji
ne moze da se ucita ili osobina koja fali nikada ne obara potez.
"""

from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
LEARNED_WEIGHTS_PATH = PROJECT_ROOT / "data" / "learned_weights.json"
VALUE_MODEL_PATH = PROJECT_ROOT / "models" / "move_value_model.json"
RANKING_SCHEMA_VERSION = 2


def _file_hash(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


# Code identity belongs to this imported version, not a later edit on disk.
_CODE_HASHES = {name: _file_hash(PROJECT_ROOT / name) for name in
                ("move_strategy.py", "learned_value.py", "runtime.py")}


def ranking_provenance() -> dict:
    _ensure_loaded()
    return {"schema_version": RANKING_SCHEMA_VERSION, "code": dict(_CODE_HASHES),
            "weights_sha256": _weights.sha256, "model_sha256": _model.sha256,
            "env_mode": _env_mode()}

CTX_SOLO_RACE = "solo_race"
CTX_SOLO_CHALLENGE = "solo_challenge"
CTX_VERSUS = "versus_2"
CONTEXTS = (CTX_SOLO_RACE, CTX_SOLO_CHALLENGE, CTX_VERSUS)

# Mnozioci van ovog opsega su znak lose merenja, ne znanja; stegnu se.
MULTIPLIER_MIN = 0.25
MULTIPLIER_MAX = 2.0
MIN_SAMPLES = 40
# Koliko rezidual sme da pomeri rangiranje: apsolutna granica u jedinicama
# simulatora, da jedan cudan list stabla ne preokrene celu listu.
RESIDUAL_CLAMP = 60.0

_PHASES = {"unknown": 0.0, "early": 1.0, "mid": 2.0, "late": 3.0, "final": 4.0}

CANDIDATE_FIELDS = (
    "score",
    "instant_score",
    "special_bonus",
    "created_special_value",
    "blue_cells",
    "direct_blue_cells",
    "blue_potential",
    "wasted_blue_cells",
    "extra_moves",
    "direct_extra_moves",
    "ufo_predicted_extra_moves",
    "cascade_count",
    "cleared_cells",
    "activated_specials",
    "board_potential",
    "lookahead_bonus",
    "mode_targets",
    "multiplier_mushrooms",
    "chest_drops",
    "jelly_charge_cells",
    "jelly_converted_tiles",
    "froggy_lotus_charge_cells",
    "mixy_converted_tiles",
    "setup_value",
    "booster_fill_bonus",
    "blue_waste_penalty",
    "extra_preservation_penalty",
    "direct_match_cells",
    "direct_effect_cells",
    "direct_effect_blue_cells",
    "predictable_special_activated",
    "cleo_scenario_count",
    "cleo_extra_move_probability",
)
CONTEXT_FIELDS = (
    "ctx_solo_race",
    "ctx_solo_challenge",
    "ctx_versus",
    "charge",
    "charge_max",
    "charge_room",
    "fills_meter",
    "remaining_moves",
    "moves_known",
    "current_round",
    "total_rounds",
    "final_round",
    "score_deficit",
    "has_opponent",
    "phase",
)
BOARD_FIELDS = (
    "color_1",
    "color_2",
    "color_3",
    "color_4",
    "color_5",
    "color_6",
    "blocked",
    "other_tiles",
    "specials",
    "rows",
    "cols",
    "cells",
)
FEATURE_NAMES = (
    CANDIDATE_FIELDS
    + ("effect_direct", "effect_special", "effect_cascade")
    + ("created_special_count", "created_special_survivors")
    + CONTEXT_FIELDS
    + BOARD_FIELDS
)


def _num(value, default=0.0) -> float:
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(number) or math.isinf(number):
        return float(default)
    return number


def _get(source, key, default=None):
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def context_label(mode, solo_challenge: bool) -> str:
    mode = str(mode or "")
    if mode == "solo_6":
        return CTX_SOLO_CHALLENGE if solo_challenge else CTX_SOLO_RACE
    if mode == "versus_2":
        return CTX_VERSUS
    return "unknown"


def candidate_features(candidate) -> list[float]:
    """Osobine jednog kandidata; radi i nad MoveEvaluation i nad dict-om iz
    candidates.json, sa istim redosledom (CANDIDATE_FIELDS + izvedene)."""
    values = [_num(_get(candidate, name, 0.0)) for name in CANDIDATE_FIELDS]
    sources = _get(candidate, "effect_source_counts", None) or {}
    values.append(_num(_get(sources, "direct_match", 0.0)))
    values.append(_num(_get(sources, "special", 0.0)))
    values.append(_num(_get(sources, "cascade", 0.0)))
    created = _get(candidate, "created_special_values", None) or []
    try:
        created_list = list(created)
    except TypeError:
        created_list = []
    values.append(float(len(created_list)))
    values.append(float(sum(1 for item in created_list if _get(item, "survives", False))))
    return values


def context_features(
    ctx: str,
    charge=None,
    charge_max=None,
    remaining_moves=None,
    current_round=None,
    total_rounds=None,
    score_deficit=None,
    phase: str = "unknown",
    blue_cells: float = 0.0,
) -> list[float]:
    charge_value = _num(charge, -1.0)
    max_value = _num(charge_max, -1.0)
    room = max_value - charge_value if charge_value >= 0 and max_value > 0 else -1.0
    fills = 1.0 if room >= 0 and _num(blue_cells) >= room > 0 else 0.0
    round_value = _num(current_round, -1.0)
    total_value = _num(total_rounds, -1.0)
    final_round = (
        1.0 if round_value >= 0 and total_value > 0 and round_value >= total_value - 1 else 0.0
    )
    return [
        1.0 if ctx == CTX_SOLO_RACE else 0.0,
        1.0 if ctx == CTX_SOLO_CHALLENGE else 0.0,
        1.0 if ctx == CTX_VERSUS else 0.0,
        charge_value,
        max_value,
        room,
        fills,
        _num(remaining_moves, -1.0),
        0.0 if remaining_moves is None else 1.0,
        round_value,
        total_value,
        final_round,
        _num(score_deficit, 0.0),
        0.0 if score_deficit is None else 1.0,
        _PHASES.get(str(phase), 0.0),
    ]


def board_features(board, special_board=None) -> list[float]:
    counts = [0.0] * 6
    blocked = 0.0
    other = 0.0
    specials = 0.0
    rows = 0
    cols = 0
    cells = 0
    # Tabla je u igri numpy niz, u snimku lista listi; `board or ()` bi na
    # nizu pukao (istinitost niza je dvosmislena), pa se proverava samo None.
    if board is None:
        board = ()
    if special_board is None:
        special_board = ()
    try:
        for row_index, row in enumerate(board):
            rows = row_index + 1
            for col_index, value in enumerate(row):
                cols = max(cols, col_index + 1)
                cells += 1
                try:
                    color = int(value)
                except (TypeError, ValueError):
                    other += 1
                    continue
                if 1 <= color <= 6:
                    counts[color - 1] += 1
                elif color < 0:
                    blocked += 1
                else:
                    other += 1
        for row in special_board:
            for value in row:
                if _num(value) != 0:
                    specials += 1
    except TypeError:
        pass
    return counts + [blocked, other, specials, float(rows), float(cols), float(cells)]


def features(candidate, ctx: str, board=None, special_board=None, **context) -> list[float]:
    values = candidate_features(candidate)
    context.setdefault("blue_cells", _num(_get(candidate, "blue_cells", 0.0)))
    values += context_features(ctx, **context)
    values += board_features(board, special_board)
    return values


# ---------------------------------------------------------------------------
# Ucitani fajlovi


def _env_mode() -> str:
    """``all`` (podrazumevano), ``weights`` (samo kalibracija, bez modela --
    koristi offline rekonstrukcija prioriteta) ili ``off``."""
    raw = (os.environ.get("MEMORY_GUI_LEARNED_VALUE") or "").strip().lower()
    if raw in {"0", "false", "off", "no"}:
        return "off"
    if raw in {"weights", "weights-only", "calibration"}:
        return "weights"
    return "all"


def _enabled_by_env() -> bool:
    return _env_mode() != "off"


def _read_json(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class LearnedWeights:
    def __init__(self, data: dict | None):
        self.data = data or {}
        self.enabled = bool(self.data) and bool(self.data.get("enabled", True))
        self.sha256 = hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest()

    def _context(self, ctx: str) -> dict:
        contexts = self.data.get("contexts") or {}
        block = contexts.get(ctx)
        if not isinstance(block, dict):
            block = self.data.get("pooled") or {}
        return block if isinstance(block, dict) else {}

    @staticmethod
    def _clamped(value, samples, default=1.0) -> float:
        if value is None or _num(samples) < MIN_SAMPLES:
            return default
        return min(MULTIPLIER_MAX, max(MULTIPLIER_MIN, _num(value, default)))

    def blue_multipliers(self, ctx: str) -> tuple[float, float]:
        if not self.enabled or not (self.data.get("apply") or {}).get("blue", True):
            return 1.0, 1.0
        block = self._context(ctx).get("blue_realization") or {}
        # A known direct match is a physical count, not a regression estimate.
        # Legacy fits had worse MAE and erased exact-fill bonuses (3 -> 2.97).
        validation = block.get("validation") or {}
        if validation.get("accepted") is not True:
            return 1.0, 1.0
        indirect = self._clamped(block.get("indirect"), block.get("indirect_samples"))
        return 1.0, indirect

    def extra_rates(self, ctx: str) -> dict:
        """Verovatnoca da obecani extra stvarno zadrzi potez, po vrsti.
        Podrazumevano: direktan i pouzdana kaskada 1.0, nepouzdana 0.0."""
        default = {"direct": 1.0, "cascade_reliable": 1.0, "cascade_unreliable": 0.0}
        if not self.enabled or not (self.data.get("apply") or {}).get("extra", True):
            return default
        block = self._context(ctx).get("extra_realization") or {}
        if _num(block.get("samples")) < MIN_SAMPLES:
            return default
        result = dict(default)
        # Sta vredi obecanje = koliko cesce zadrzi potez od poteza bez obecanja.
        baseline = _num(block.get("none"), 0.0)
        for kind in result:
            rate = block.get(kind)
            count = _num(block.get(kind + "_samples"), 0.0)
            if rate is None or count < MIN_SAMPLES:
                continue
            lift = (_num(rate) - baseline) / max(1e-6, 1.0 - baseline)
            result[kind] = min(1.0, max(0.0, lift))
        return result

    def future_scale(self, ctx: str) -> float:
        if not self.enabled or not (self.data.get("apply") or {}).get("future", True):
            return 1.0
        block = self._context(ctx).get("future_realization") or {}
        if (block.get("validation") or {}).get("accepted") is True:
            # Future value may legitimately be zero; charge's minimum is not
            # an appropriate lower bound for this independent quantity.
            return min(MULTIPLIER_MAX, max(0.0, _num(block.get("scale"), 0.25)))
        return self._clamped(block.get("scale"), block.get("samples"))


class ValueModel:
    def __init__(self, data: dict | None):
        self.data = data or {}
        self.sha256 = hashlib.sha256(json.dumps(self.data, sort_keys=True).encode()).hexdigest()
        self.trees = self.data.get("trees") or []
        self.feature_names = tuple(self.data.get("feature_names") or ())
        self.enabled = (
            bool(self.trees)
            and bool(self.data.get("enabled", True))
            and self.feature_names == FEATURE_NAMES
        )
        self.blend = min(1.0, max(0.0, _num(self.data.get("blend"), 0.5)))
        # Konteksti na kojima je model proveren; None/odsutno = svi (stari fajlovi).
        contexts = self.data.get("contexts")
        self.contexts = frozenset(contexts) if contexts else None
        self.init = _num(self.data.get("init"), 0.0)
        self.learning_rate = _num(self.data.get("learning_rate"), 0.1)
        # Stabla predvidjaju rezidual u jedinicama stvarne vrednosti; prioritet
        # je na ~2x vecoj skali (linearna osnova a + b * prioritet), pa se
        # rezidual mnozi sa 1/b pre dodavanja na prioritet.
        self.residual_scale = _num(self.data.get("residual_scale"), 1.0)

    def raw(self, row: list[float]) -> float:
        total = self.init
        for tree in self.trees:
            left = tree["left"]
            right = tree["right"]
            feature = tree["feature"]
            threshold = tree["threshold"]
            value = tree["value"]
            node = 0
            while left[node] >= 0:
                node = left[node] if row[feature[node]] <= threshold[node] else right[node]
            total += self.learning_rate * value[node]
        return total

    def residual(self, row: list[float]) -> float:
        if not self.enabled:
            return 0.0
        try:
            value = self.raw(row) * self.residual_scale
        except (IndexError, KeyError, TypeError):
            return 0.0
        return min(RESIDUAL_CLAMP, max(-RESIDUAL_CLAMP, value))


_weights = LearnedWeights(None)
_model = ValueModel(None)
_loaded = False
# Poslednji rezidual i konacni prioritet po kandidatu, da Debug
# (candidates.json) moze da ih upise; prioritet sluzi i za proveru offline
# rekonstrukcije (tools/rebuild_evaluation.py).
last_residuals: dict[tuple, float] = {}
last_applied_residuals: dict[tuple, float] = {}
last_priorities: dict[tuple, float] = {}


def begin_decision() -> None:
    """Do not attach a previous board's coordinate-matched score to this run."""
    last_priorities.clear()
    last_residuals.clear()
    last_applied_residuals.clear()


def remember_priority(evaluation, priority: float) -> None:
    key = candidate_key(evaluation)
    if key is not None:
        last_priorities[key] = float(priority)


def reload() -> None:
    global _weights, _model, _loaded
    mode = _env_mode()
    if mode == "off":
        _weights = LearnedWeights(None)
        _model = ValueModel(None)
    else:
        _weights = LearnedWeights(_read_json(LEARNED_WEIGHTS_PATH))
        _model = ValueModel(_read_json(VALUE_MODEL_PATH) if mode == "all" else None)
    _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        reload()


def weights() -> LearnedWeights:
    _ensure_loaded()
    return _weights


def model() -> ValueModel:
    _ensure_loaded()
    return _model


def is_active() -> bool:
    _ensure_loaded()
    return _weights.enabled or _model.enabled


def status() -> dict:
    _ensure_loaded()
    return {
        "env_enabled": _enabled_by_env(),
        "weights": {
            "path": str(LEARNED_WEIGHTS_PATH),
            "enabled": _weights.enabled,
            "fitted_at": _weights.data.get("fitted_at"),
        },
        "model": {
            "path": str(VALUE_MODEL_PATH),
            "enabled": _model.enabled,
            "trained_at": _model.data.get("trained_at"),
            "trees": len(_model.trees),
            "blend": _model.blend,
        },
    }


def candidate_key(evaluation) -> tuple | None:
    candidate = _get(evaluation, "candidate", None)
    if candidate is None:
        return None
    try:
        direction = _get(candidate, "direction", None)
        direction = getattr(direction, "value", direction)
        board = tuple(tuple(int(v) for v in row) for row in candidate.board)
        specials = tuple(tuple(int(v) for v in row) for row in candidate.special_board)
        return (tuple(candidate.start), tuple(candidate.target), str(direction), board, specials)
    except (AttributeError, TypeError):
        return None


def residual_adjustment(
    evaluation,
    ctx: str,
    *,
    charge=None,
    charge_max=None,
    remaining_moves=None,
    current_round=None,
    total_rounds=None,
    score_deficit=None,
    phase: str = "unknown",
) -> float:
    """``blend * rezidual`` za jedan kandidat, 0.0 kada model nije ucitan."""
    _ensure_loaded()
    if not _model.enabled:
        return 0.0
    if _model.contexts is not None and ctx not in _model.contexts:
        return 0.0
    candidate = _get(evaluation, "candidate", None)
    try:
        row = features(
            evaluation,
            ctx,
            _get(candidate, "board", None),
            _get(candidate, "special_board", None),
            charge=charge,
            charge_max=charge_max,
            remaining_moves=remaining_moves,
            current_round=current_round,
            total_rounds=total_rounds,
            score_deficit=score_deficit,
            phase=phase,
        )
        value = _model.residual(row)
    except Exception:
        return 0.0
    key = candidate_key(evaluation)
    if key is not None:
        last_residuals[key] = value
    return _model.blend * value
