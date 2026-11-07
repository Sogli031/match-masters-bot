# Recognition Runtime ML Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in runtime ML recognition path that consumes `models/recognition_model.onnx` plus `models/recognition_model.metadata.json`, while keeping template/color recognition as the safe fallback.

**Architecture:** Add a focused `ml_recognition_runtime.py` module for ONNX loading, preprocessing, batched inference, confidence thresholds, and debug payloads. Keep the existing `recognition.update_board_2(...)` pipeline as the baseline, then apply ML only through explicit modes: `off`, `shadow`, and `hybrid`. Thread the selected mode through `gui.py -> runtime.CheckBestMoveRequest -> recognition.py`, and write per-run ML diagnostics under `Debug/runs/<run_id>/ml_recognition.json`.

**Tech Stack:** Python 3, PyQt5, PIL, NumPy, `onnxruntime` when available, pytest.

**Assumptions:**
- Assumes Sub-project B artifacts may exist at `models/recognition_model.onnx` and `models/recognition_model.metadata.json` - will NOT work as ML inference when both files are absent, but must still return template recognition.
- Assumes `onnxruntime` may fail to import on this Windows environment - will NOT crash gameplay; ML becomes unavailable and template output is returned.
- Assumes `update_board_2(...)` remains the single board recognition entry point - will NOT cover alternate screenshot recognizers outside the existing live runtime.
- Assumes the user wants explicit manual control in the GUI - will NOT silently enable ML from old `ml_mode` booleans.
- Assumes current class taxonomy in `dataset_classes.py` remains authoritative - will NOT accept metadata classes that cannot be decoded into runtime board values.

---

## Approved Design Summary

Implement Sub-project C from `docs/specs/2026-05-25-recognition-runtime-ml-path-design.md`.

Approved runtime modes:

- `off`: current template/color behavior only.
- `shadow`: run ML and write diagnostics, but return template/color output unchanged.
- `hybrid`: start from template/color output and overlay ML cells only when all confidence and safety gates pass.

Approved fallback rule: any missing model, missing metadata, unavailable `onnxruntime`, bad metadata, inference exception, class threshold over `1.0`, or rejected prediction returns the template/color result for that cell.

Approved debug rule: training reports show validation percentages, while live `ml_recognition.json` shows per-cell confidence percentages, thresholds, accept/reject reasons, and template-vs-ML comparison for every debug run where ML ran.

## Scope

In scope:

- Add inverse class decoding in `dataset_classes.py`.
- Add ML runtime inference and diagnostics in `ml_recognition_runtime.py`.
- Add conservative ML overlay helpers in `recognition.py`.
- Call ML finalization from all `update_board_2(...)` return paths.
- Thread `ml_recognition_mode` through GUI state, request dataclass, runtime, and debug outputs.
- Replace old tests that asserted no ML control exists.

Out of scope:

- Retraining pipeline changes.
- Dataset manifest mutation.
- Move strategy scoring changes.
- Template asset changes.
- Automatic online learning.
- Enabling ML by default without explicit GUI state.

## File Structure

- `dataset_classes.py`: keeps canonical taxonomy and gains `decode_class(class_name) -> tuple[int, int]`.
- `ml_recognition_runtime.py`: new module for mode normalization, metadata validation, ONNX session loading, board crop preprocessing, batched inference, and debug payload building.
- `recognition.py`: owns the live overlay decision because it already has active game mode, board geometry, baseline board, and screenshot image.
- `runtime.py`: carries selected mode in `CheckBestMoveRequest`, sets recognition mode for each request, preserves non-numeric diagnostics safely, and writes `ml_recognition.json`.
- `gui.py`: displays mode control, persists `ml_recognition_mode`, and passes the mode into requests.
- `test.py`: facade should expose new module symbols only if tests or callers need them.
- `tests/test_dataset_classes.py`: inverse mapping coverage.
- `tests/test_ml_recognition_runtime.py`: ML module coverage with fake ONNX sessions.
- `tests/test_recognition_ml_overlay.py`: overlay gate coverage without live screenshots.
- `tests/test_move_debug.py`: GUI/request/debug integration.
- `tests/test_special_detection.py`: migrate template-only ML-switch assertion to explicit ML-mode assertion.

## Preflight

- [ ] Run baseline targeted tests before edits.

Run: `python -m pytest tests/test_dataset_classes.py tests/test_move_debug.py tests/test_special_detection.py -q`

Expected: PASS for existing tests that are already present. If `tests/test_dataset_classes.py` does not exist yet, run `python -m pytest tests/test_move_debug.py tests/test_special_detection.py -q` instead and record that dataset-class tests start in Task 1.

---

### Task 1: Add Inverse Dataset Class Decoding

**Files:**
- Modify: `dataset_classes.py`
- Test: `tests/test_dataset_classes.py`

**Security flag:** `none`

**Does NOT cover:** This task only maps class names to runtime `(color, special)` values. It does not load ONNX, apply thresholds, change recognition output, or touch GUI.

- [x] **Step 1: Write failing tests**

Add or extend `tests/test_dataset_classes.py` with:

```python
import pytest

from dataset_classes import classify, decode_class
from move_strategy import (
    BLOCKED,
    BLUE,
    GREEN,
    RED,
    DISCO_BALL,
    SPECIAL_BILLIE_DRONE,
    SPECIAL_BOMB,
    SPECIAL_CLEO_BUG,
    SPECIAL_DISCO_BALL,
    SPECIAL_HEART,
    SPECIAL_HORIZONTAL,
    SPECIAL_LIGHTNING,
    SPECIAL_MODE_TARGET,
    SPECIAL_VERTICAL,
)


@pytest.mark.parametrize(
    ("color", "special"),
    [
        (RED, 0),
        (GREEN, SPECIAL_HORIZONTAL),
        (BLUE, SPECIAL_VERTICAL),
        (RED, SPECIAL_BOMB),
        (GREEN, SPECIAL_LIGHTNING),
        (BLUE, SPECIAL_HEART),
    ],
)
def test_decode_class_round_trips_color_bound_classes(color, special):
    assert decode_class(classify(color, special)) == (color, special)


@pytest.mark.parametrize(
    ("class_name", "expected"),
    [
        ("blocked", (BLOCKED, 0)),
        ("empty", (0, 0)),
        ("disco_ball", (DISCO_BALL, SPECIAL_DISCO_BALL)),
        ("cleo_bug", (1, SPECIAL_CLEO_BUG)),
        ("billie_drone", (BLOCKED, SPECIAL_BILLIE_DRONE)),
        ("mode_target", (1, SPECIAL_MODE_TARGET)),
    ],
)
def test_decode_class_handles_color_agnostic_classes(class_name, expected):
    assert decode_class(class_name) == expected


def test_decode_class_rejects_unknown_class():
    with pytest.raises(ValueError, match="Unknown dataset class"):
        decode_class("not_a_real_tile")


def test_decode_class_rejects_unknown_suffix():
    with pytest.raises(ValueError, match="Unknown dataset class"):
        decode_class("red_not_a_suffix")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dataset_classes.py -q`

Expected: FAIL with `ImportError` or `AttributeError` for missing `decode_class`.

- [x] **Step 3: Implement focused change**

In `dataset_classes.py`, add:

```python
from move_strategy import DISCO_BALL

_NAME_TO_COLOR = {name: code for code, name in _COLOR_NAMES.items()}
_SUFFIX_TO_SPECIAL = {suffix: code for code, suffix in _COLOR_BOUND_SUFFIXES.items()}
_CLASS_TO_COLOR_SPECIAL = {
    "blocked": (BLOCKED, 0),
    "empty": (0, 0),
    "disco_ball": (DISCO_BALL, SPECIAL_DISCO_BALL),
    "cleo_bug": (1, SPECIAL_CLEO_BUG),
    "billie_drone": (BLOCKED, SPECIAL_BILLIE_DRONE),
    "mode_target": (1, SPECIAL_MODE_TARGET),
}


def decode_class(class_name: str) -> tuple[int, int]:
    """Map a canonical dataset class back to runtime board/special values."""
    if class_name in _CLASS_TO_COLOR_SPECIAL:
        return _CLASS_TO_COLOR_SPECIAL[class_name]

    for color_name, color_code in _NAME_TO_COLOR.items():
        prefix = f"{color_name}_"
        if not class_name.startswith(prefix):
            continue
        suffix = class_name[len(prefix):]
        special = _SUFFIX_TO_SPECIAL.get(suffix)
        if special is None:
            break
        return color_code, special

    raise ValueError(f"Unknown dataset class: {class_name}")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dataset_classes.py -q`

Expected: PASS.

- [x] **Step 5: Broader verification**

Run: `python -m pytest tests/test_recognition_dataset.py tests/test_train_recognition_model.py tests/test_dataset_classes.py -q`

Expected: PASS. This proves the new inverse mapping did not break Sub-project A/B dataset/training tests.

---

### Task 2: Add ML Runtime Module With Lazy ONNX Fallback

**Files:**
- Create: `ml_recognition_runtime.py`
- Test: `tests/test_ml_recognition_runtime.py`

**Security flag:** `none`

**Does NOT cover:** This task predicts classes and builds diagnostics. It does not alter live board output, write debug files, or add GUI controls.

- [x] **Step 1: Write failing tests**

Create `tests/test_ml_recognition_runtime.py` with tests shaped like:

```python
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from ml_recognition_runtime import (
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_SHADOW,
    build_ml_debug_payload,
    normalize_ml_recognition_mode,
    predict_board_tiles,
)


class FakeSession:
    def __init__(self, logits):
        self.logits = np.asarray(logits, dtype=np.float32)
        self.last_batch = None

    def get_inputs(self):
        return [SimpleNamespace(name="input")]

    def run(self, _outputs, feeds):
        self.last_batch = feeds["input"]
        return [self.logits]


def write_metadata(path: Path, classes, thresholds=None):
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_version": "test-model",
                "input": {
                    "name": "input",
                    "shape": [1, 3, 64, 64],
                    "channels": "RGB",
                    "preprocessing": {
                        "resize_to": [64, 64],
                        "scale": 1.0 / 255.0,
                        "mean": [0.0, 0.0, 0.0],
                        "std": [1.0, 1.0, 1.0],
                    },
                },
                "output": {"name": "logits", "post_softmax": False},
                "classes": classes,
                "thresholds_per_class": thresholds or {},
                "fallback_threshold_default": 0.9,
            }
        ),
        encoding="utf-8",
    )


def test_normalize_ml_recognition_mode_accepts_known_values():
    assert normalize_ml_recognition_mode("off") == ML_RECOGNITION_OFF
    assert normalize_ml_recognition_mode("shadow") == ML_RECOGNITION_SHADOW
    assert normalize_ml_recognition_mode("hybrid") == ML_RECOGNITION_HYBRID
    assert normalize_ml_recognition_mode("bad-value") == ML_RECOGNITION_OFF
    assert normalize_ml_recognition_mode(True) == ML_RECOGNITION_OFF


def test_predict_board_tiles_off_does_not_load_model(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    result = predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_OFF,
        model_path=tmp_path / "missing.onnx",
        metadata_path=tmp_path / "missing.json",
    )
    assert result.available is False
    assert result.mode == ML_RECOGNITION_OFF
    assert result.predictions == []
    assert result.load_error == "ml_recognition_off"


def test_missing_model_returns_unavailable_without_exception(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    meta = tmp_path / "recognition_model.metadata.json"
    write_metadata(meta, ["red_normal"], {"red_normal": 0.5})

    result = predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=tmp_path / "missing.onnx",
        metadata_path=meta,
    )

    assert result.available is False
    assert "missing" in result.load_error.lower()


def test_fake_session_predicts_batch_and_thresholds(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    model = tmp_path / "recognition_model.onnx"
    model.write_bytes(b"fake")
    meta = tmp_path / "recognition_model.metadata.json"
    write_metadata(meta, ["red_normal", "blue_normal"], {"blue_normal": 0.5})
    fake_session = FakeSession([[0.0, 6.0]] * 49)

    result = predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=model,
        metadata_path=meta,
        session_factory=lambda _model_path: fake_session,
    )

    assert result.available is True
    assert len(result.predictions) == 49
    assert result.predictions[0].predicted_class == "blue_normal"
    assert result.predictions[0].threshold == 0.5
    assert fake_session.last_batch.shape == (49, 3, 64, 64)


def test_threshold_over_one_is_carried_to_prediction(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    model = tmp_path / "recognition_model.onnx"
    model.write_bytes(b"fake")
    meta = tmp_path / "recognition_model.metadata.json"
    write_metadata(meta, ["blue_normal"], {"blue_normal": 1.01})
    fake_session = FakeSession([[5.0]] * 49)

    result = predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_HYBRID,
        model_path=model,
        metadata_path=meta,
        session_factory=lambda _model_path: fake_session,
    )

    assert result.predictions[0].threshold == 1.01


def test_session_cache_reuses_session_until_model_or_metadata_mtime_changes(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    model = tmp_path / "recognition_model.onnx"
    model.write_bytes(b"fake")
    meta = tmp_path / "recognition_model.metadata.json"
    write_metadata(meta, ["red_normal"], {"red_normal": 0.5})
    created = []

    def factory(_model_path):
        created.append(FakeSession([[5.0]] * 49))
        return created[-1]

    predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=model,
        metadata_path=meta,
        session_factory=factory,
    )
    predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=model,
        metadata_path=meta,
        session_factory=factory,
    )
    assert len(created) == 1

    future = time.time() + 2.0
    os.utime(meta, (future, future))
    predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=model,
        metadata_path=meta,
        session_factory=factory,
    )
    assert len(created) == 2


def test_build_ml_debug_payload_contains_template_comparison(tmp_path):
    image = Image.new("RGB", (140, 140), "red")
    model = tmp_path / "recognition_model.onnx"
    model.write_bytes(b"fake")
    meta = tmp_path / "recognition_model.metadata.json"
    write_metadata(meta, ["red_normal"], {"red_normal": 0.5})
    fake_session = FakeSession([[5.0]] * 49)
    result = predict_board_tiles(
        image,
        board_length=7,
        square_size=20,
        mode=ML_RECOGNITION_SHADOW,
        model_path=model,
        metadata_path=meta,
        session_factory=lambda _model_path: fake_session,
    )

    board = [[1 for _ in range(7)] for _ in range(7)]
    special = [[0 for _ in range(7)] for _ in range(7)]
    payload = build_ml_debug_payload(result, board, special)

    assert payload["mode"] == ML_RECOGNITION_SHADOW
    assert payload["model_version"] == "test-model"
    assert payload["summary"]["predictions"] == 49
    assert payload["cells"][0]["template_board"] == 1
    assert "confidence" in payload["cells"][0]
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ml_recognition_runtime.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'ml_recognition_runtime'`.

- [x] **Step 3: Implement focused change**

Create `ml_recognition_runtime.py` with:

```python
from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from dataset_classes import decode_class

ML_RECOGNITION_OFF = "off"
ML_RECOGNITION_SHADOW = "shadow"
ML_RECOGNITION_HYBRID = "hybrid"
ML_RECOGNITION_MODES = {
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_SHADOW,
    ML_RECOGNITION_HYBRID,
}

DEFAULT_MODEL_PATH = Path("models") / "recognition_model.onnx"
DEFAULT_METADATA_PATH = Path("models") / "recognition_model.metadata.json"
_SESSION_CACHE = {}


@dataclass(frozen=True)
class TilePrediction:
    row: int
    col: int
    predicted_class: str
    confidence: float
    threshold: float
    board_value: int
    special_value: int
    accepted: bool = False
    reason: str = "not_evaluated"


@dataclass(frozen=True)
class RecognitionMlResult:
    available: bool
    mode: str
    model_version: str | None
    predictions: list[TilePrediction]
    load_error: str | None = None
    inference_ms: float = 0.0


def normalize_ml_recognition_mode(value) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ML_RECOGNITION_MODES:
            return normalized
    return ML_RECOGNITION_OFF


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def _load_metadata(metadata_path: Path) -> dict:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    classes = payload.get("classes")
    if not isinstance(classes, list) or not classes:
        raise ValueError("metadata classes must be a non-empty list")
    for class_name in classes:
        decode_class(class_name)
    return payload


def _default_session_factory(model_path: Path):
    import onnxruntime  # type: ignore

    return onnxruntime.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])


def _session_cache_key(model_path: Path, metadata_path: Path, session_factory) -> tuple:
    factory_key = "default" if session_factory is None else id(session_factory)
    return (
        str(model_path.resolve()),
        model_path.stat().st_mtime_ns,
        str(metadata_path.resolve()),
        metadata_path.stat().st_mtime_ns,
        factory_key,
    )


def _get_session(model_path: Path, metadata_path: Path, session_factory):
    key = _session_cache_key(model_path, metadata_path, session_factory)
    cached = _SESSION_CACHE.get(key)
    if cached is not None:
        return cached
    factory = session_factory or _default_session_factory
    session = factory(model_path)
    _SESSION_CACHE.clear()
    _SESSION_CACHE[key] = session
    return session


def _preprocess_cells(image: Image.Image, board_length: int, square_size: int, metadata: dict) -> np.ndarray:
    prep = metadata.get("input", {}).get("preprocessing", {})
    resize_to = prep.get("resize_to", [64, 64])
    scale = float(prep.get("scale", 1.0 / 255.0))
    mean = np.asarray(prep.get("mean", [0.0, 0.0, 0.0]), dtype=np.float32)
    std = np.asarray(prep.get("std", [1.0, 1.0, 1.0]), dtype=np.float32)

    cells = []
    rgb = image.convert("RGB")
    for row in range(board_length):
        for col in range(board_length):
            left = col * square_size
            top = row * square_size
            crop = rgb.crop((left, top, left + square_size, top + square_size))
            crop = crop.resize(tuple(resize_to), Image.BILINEAR)
            arr = np.asarray(crop, dtype=np.float32) * scale
            arr = (arr - mean) / std
            cells.append(np.transpose(arr, (2, 0, 1)))
    return np.stack(cells).astype(np.float32)


def predict_board_tiles(
    img_color: Image.Image,
    board_length: int,
    square_size: int,
    mode: str,
    model_path: Path = DEFAULT_MODEL_PATH,
    metadata_path: Path = DEFAULT_METADATA_PATH,
    session_factory: Callable[[Path], object] | None = None,
) -> RecognitionMlResult:
    normalized_mode = normalize_ml_recognition_mode(mode)
    if normalized_mode == ML_RECOGNITION_OFF:
        return RecognitionMlResult(False, normalized_mode, None, [], "ml_recognition_off", 0.0)

    start = time.perf_counter()
    model_path = Path(model_path)
    metadata_path = Path(metadata_path)
    try:
        if not model_path.exists():
            raise FileNotFoundError(f"missing model: {model_path}")
        if not metadata_path.exists():
            raise FileNotFoundError(f"missing metadata: {metadata_path}")
        metadata = _load_metadata(metadata_path)
        session = _get_session(model_path, metadata_path, session_factory)
        input_name = session.get_inputs()[0].name
        batch = _preprocess_cells(img_color, board_length, square_size, metadata)
        logits = np.asarray(session.run(None, {input_name: batch})[0], dtype=np.float32)
        probs = _softmax(logits)
        classes = list(metadata["classes"])
        thresholds = metadata.get("thresholds_per_class", {})
        fallback_threshold = float(metadata.get("fallback_threshold_default", 0.9))
        predictions = []
        for index, row_col in enumerate((divmod(n, board_length) for n in range(board_length * board_length))):
            class_index = int(np.argmax(probs[index]))
            class_name = classes[class_index]
            board_value, special_value = decode_class(class_name)
            row, col = row_col
            predictions.append(
                TilePrediction(
                    row=row,
                    col=col,
                    predicted_class=class_name,
                    confidence=float(probs[index, class_index]),
                    threshold=float(thresholds.get(class_name, fallback_threshold)),
                    board_value=board_value,
                    special_value=special_value,
                )
            )
        elapsed = (time.perf_counter() - start) * 1000.0
        return RecognitionMlResult(True, normalized_mode, metadata.get("model_version"), predictions, None, elapsed)
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return RecognitionMlResult(False, normalized_mode, None, [], str(exc), elapsed)


def build_ml_debug_payload(result: RecognitionMlResult, template_board, template_special_board) -> dict:
    accepted = sum(1 for prediction in result.predictions if prediction.accepted)
    cells = []
    for prediction in result.predictions:
        cells.append(
            {
                "row": prediction.row,
                "col": prediction.col,
                "template_board": template_board[prediction.row][prediction.col],
                "template_special": template_special_board[prediction.row][prediction.col],
                "ml_class": prediction.predicted_class,
                "confidence": round(prediction.confidence, 6),
                "threshold": prediction.threshold,
                "accepted": prediction.accepted,
                "reason": prediction.reason,
                "ml_board": prediction.board_value,
                "ml_special": prediction.special_value,
            }
        )
    return {
        "mode": result.mode,
        "available": result.available,
        "model_version": result.model_version,
        "summary": {
            "predictions": len(result.predictions),
            "accepted": accepted,
            "rejected": len(result.predictions) - accepted,
            "unavailable_reason": result.load_error,
            "inference_ms": round(result.inference_ms, 1),
        },
        "cells": cells,
    }
```

Keep the fake `session_factory` path available so unit tests do not require real `onnxruntime`.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ml_recognition_runtime.py -q`

Expected: PASS.

- [x] **Step 5: Optional real ONNX smoke**

Run: `python -c "import onnxruntime; print(onnxruntime.__version__)"`

Expected: Either prints a version or fails. Failure is acceptable for runtime fallback, but record it in the implementation notes.

---

### Task 3: Add Recognition Overlay Gates

**Files:**
- Modify: `recognition.py`
- Test: `tests/test_recognition_ml_overlay.py`

**Security flag:** `none`

**Does NOT cover:** This task decides how ML predictions overlay an already recognized board. It does not call ONNX from `update_board_2(...)`, does not write files, and does not add GUI controls.

- [x] **Step 1: Write failing tests**

Create `tests/test_recognition_ml_overlay.py`:

```python
from dataclasses import replace

import recognition as bot
from ml_recognition_runtime import (
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_SHADOW,
    RecognitionMlResult,
    TilePrediction,
)
from move_strategy import BLUE, RED, SPECIAL_BOMB


def result_with(*predictions, mode=ML_RECOGNITION_HYBRID, available=True):
    return RecognitionMlResult(
        available=available,
        mode=mode,
        model_version="test-model",
        predictions=list(predictions),
    )


def prediction(**overrides):
    base = TilePrediction(
        row=0,
        col=0,
        predicted_class="red_normal",
        confidence=0.99,
        threshold=0.5,
        board_value=RED,
        special_value=0,
    )
    return replace(base, **overrides)


def test_shadow_mode_leaves_board_unchanged_and_records_rejection():
    board = [[BLUE]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(board_value=RED), mode=ML_RECOGNITION_SHADOW),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[BLUE]]
    assert special == [[0]]
    assert applied.predictions[0].accepted is False
    assert applied.predictions[0].reason == "shadow_mode"


def test_hybrid_fills_zero_cell_when_confidence_passes():
    board = [[0]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(board_value=RED, special_value=0)),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[RED]]
    assert special == [[0]]
    assert applied.predictions[0].accepted is True
    assert applied.predictions[0].reason == "confidence_pass"


def test_hybrid_rejects_empty_prediction():
    board = [[BLUE]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(predicted_class="empty", board_value=0, special_value=0)),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[BLUE]]
    assert applied.predictions[0].reason == "empty_rejected"


def test_hybrid_rejects_threshold_over_one():
    board = [[BLUE]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(threshold=1.01, board_value=RED)),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[BLUE]]
    assert applied.predictions[0].reason == "threshold_disabled"


def test_hybrid_rejects_low_confidence():
    board = [[BLUE]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(confidence=0.49, threshold=0.5, board_value=RED)),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[BLUE]]
    assert applied.predictions[0].reason == "confidence_below_threshold"


def test_hybrid_corrects_normal_color_when_confidence_passes():
    board = [[BLUE]]
    special = [[0]]
    bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(board_value=RED, special_value=0)),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[RED]]
    assert special == [[0]]


def test_hybrid_accepts_same_color_special_when_confidence_passes():
    board = [[RED]]
    special = [[0]]
    bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(
            prediction(
                predicted_class="red_bomb",
                board_value=RED,
                special_value=SPECIAL_BOMB,
            )
        ),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[RED]]
    assert special == [[SPECIAL_BOMB]]


def test_unavailable_ml_leaves_board_unchanged():
    board = [[BLUE]]
    special = [[0]]
    applied = bot.apply_ml_recognition_overlay(
        board,
        special,
        result_with(prediction(board_value=RED), available=False),
        active_game_mode=bot.GameMode.NONE,
    )

    assert board == [[BLUE]]
    assert applied.predictions == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_ml_overlay.py -q`

Expected: FAIL with `AttributeError` for missing `apply_ml_recognition_overlay`.

- [x] **Step 3: Implement focused change**

In `recognition.py`, import:

```python
from dataclasses import replace

from ml_recognition_runtime import (
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_SHADOW,
    RecognitionMlResult,
    normalize_ml_recognition_mode,
)
```

Add module state and helper:

```python
ml_recognition_mode = ML_RECOGNITION_OFF


def set_ml_recognition_mode(mode) -> str:
    global ml_recognition_mode
    ml_recognition_mode = normalize_ml_recognition_mode(mode)
    return ml_recognition_mode


def _is_mode_specific_baseline(special_value: int) -> bool:
    return special_value == SPECIAL_MODE_TARGET


def _accepted_prediction(prediction, reason: str):
    return replace(prediction, accepted=True, reason=reason)


def _rejected_prediction(prediction, reason: str):
    return replace(prediction, accepted=False, reason=reason)


def apply_ml_recognition_overlay(board, special_board, ml_result: RecognitionMlResult, active_game_mode=None):
    if not ml_result.available:
        return ml_result

    decisions = []
    if ml_result.mode == ML_RECOGNITION_SHADOW:
        return replace(
            ml_result,
            predictions=[_rejected_prediction(prediction, "shadow_mode") for prediction in ml_result.predictions],
        )

    if ml_result.mode != ML_RECOGNITION_HYBRID:
        return ml_result

    for prediction in ml_result.predictions:
        current_board = board[prediction.row][prediction.col]
        current_special = special_board[prediction.row][prediction.col]
        if prediction.predicted_class == "empty":
            decisions.append(_rejected_prediction(prediction, "empty_rejected"))
            continue
        if prediction.threshold > 1.0:
            decisions.append(_rejected_prediction(prediction, "threshold_disabled"))
            continue
        if prediction.confidence < prediction.threshold:
            decisions.append(_rejected_prediction(prediction, "confidence_below_threshold"))
            continue
        if _is_mode_specific_baseline(current_special) and prediction.special_value == 0:
            decisions.append(_rejected_prediction(prediction, "mode_specific_baseline"))
            continue

        board[prediction.row][prediction.col] = prediction.board_value
        special_board[prediction.row][prediction.col] = prediction.special_value
        decisions.append(_accepted_prediction(prediction, "confidence_pass"))

    return replace(ml_result, predictions=decisions)
```

If `SPECIAL_MODE_TARGET` is not imported in `recognition.py`, import it from `move_strategy` with the existing constants.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_ml_overlay.py -q`

Expected: PASS.

- [x] **Step 5: Broader verification**

Run: `python -m pytest tests/test_recognition_ml_overlay.py tests/test_special_detection.py -q`

Expected: PASS except for the old no-ML-switch test, which Task 7 migrates if it still exists.

---

### Task 4: Call ML From `update_board_2(...)` Without Breaking Template Fallback

**Files:**
- Modify: `recognition.py`
- Test: `tests/test_recognition_ml_overlay.py`

**Security flag:** `none`

**Does NOT cover:** This task connects ML finalization to board recognition and diagnostics. It does not write `ml_recognition.json`, add request fields, or add GUI controls.

- [x] **Step 1: Write failing tests**

Extend `tests/test_recognition_ml_overlay.py`:

```python
from PIL import Image


def test_finalize_board_with_ml_off_records_mode_without_calling_predictor(monkeypatch):
    called = []
    monkeypatch.setattr(bot, "ml_recognition_mode", bot.ML_RECOGNITION_OFF)
    monkeypatch.setattr(
        bot.ml_recognition_runtime,
        "predict_board_tiles",
        lambda *args, **kwargs: called.append(True),
    )
    board = [[1]]
    special = [[0]]
    diag = {}

    bot._finalize_board_with_ml(
        Image.new("RGB", (84, 84), "red"),
        board,
        special,
        bot.GameMode.NONE,
        diag,
    )

    assert called == []
    assert diag["ml_recognition_mode"] == bot.ML_RECOGNITION_OFF
    assert diag["ml_available"] is False


def test_finalize_board_with_ml_shadow_keeps_board_and_sets_debug_payload(monkeypatch):
    monkeypatch.setattr(bot, "ml_recognition_mode", bot.ML_RECOGNITION_SHADOW)
    board = [[1]]
    special = [[0]]
    diag = {}

    monkeypatch.setattr(
        bot.ml_recognition_runtime,
        "predict_board_tiles",
        lambda *args, **kwargs: result_with(prediction(board_value=2), mode=bot.ML_RECOGNITION_SHADOW),
    )

    bot._finalize_board_with_ml(
        Image.new("RGB", (84, 84), "red"),
        board,
        special,
        bot.GameMode.NONE,
        diag,
    )

    assert board == [[1]]
    assert diag["ml_available"] is True
    assert diag["ml_predictions"] == 1
    assert diag["ml_accepted"] == 0
    assert diag["ml_debug_payload"]["summary"]["predictions"] == 1


def test_finalize_board_with_ml_hybrid_applies_overlay(monkeypatch):
    monkeypatch.setattr(bot, "ml_recognition_mode", bot.ML_RECOGNITION_HYBRID)
    board = [[0]]
    special = [[0]]
    diag = {}

    monkeypatch.setattr(
        bot.ml_recognition_runtime,
        "predict_board_tiles",
        lambda *args, **kwargs: result_with(prediction(board_value=2), mode=bot.ML_RECOGNITION_HYBRID),
    )

    bot._finalize_board_with_ml(
        Image.new("RGB", (84, 84), "red"),
        board,
        special,
        bot.GameMode.NONE,
        diag,
    )

    assert board == [[2]]
    assert diag["ml_accepted"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recognition_ml_overlay.py -q`

Expected: FAIL with `AttributeError` for missing `_finalize_board_with_ml`.

- [x] **Step 3: Implement focused change**

In `recognition.py`, import the module itself so tests can monkeypatch it:

```python
import ml_recognition_runtime
```

Add:

```python
def _set_ml_diag_off(_diag, mode):
    if _diag is None:
        return
    _diag["ml_recognition_mode"] = mode
    _diag["ml_available"] = False
    _diag["ml_predictions"] = 0
    _diag["ml_accepted"] = 0
    _diag["ml_rejected"] = 0


def _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag=None):
    mode = normalize_ml_recognition_mode(ml_recognition_mode)
    if mode == ML_RECOGNITION_OFF:
        _set_ml_diag_off(_diag, mode)
        return board, special_board

    template_board = [row[:] for row in board]
    template_special_board = [row[:] for row in special_board]
    ml_result = ml_recognition_runtime.predict_board_tiles(
        img_color,
        board_length=board_length,
        square_size=squareSize,
        mode=mode,
    )
    applied_result = apply_ml_recognition_overlay(board, special_board, ml_result, active_game_mode)
    accepted = sum(1 for prediction in applied_result.predictions if prediction.accepted)
    rejected = len(applied_result.predictions) - accepted
    if _diag is not None:
        _diag["ml_recognition_mode"] = mode
        _diag["ml_available"] = applied_result.available
        _diag["ml_model_version"] = applied_result.model_version
        _diag["ml_inference_ms"] = applied_result.inference_ms
        _diag["ml_predictions"] = len(applied_result.predictions)
        _diag["ml_accepted"] = accepted
        _diag["ml_rejected"] = rejected
        _diag["ml_unavailable_reason"] = applied_result.load_error
        _diag["ml_debug_payload"] = ml_recognition_runtime.build_ml_debug_payload(
            applied_result,
            template_board,
            template_special_board,
        )
    return board, special_board
```

Then replace every `return board, special_board` inside `update_board_2(...)` with:

```python
return _finalize_board_with_ml(img_color, board, special_board, active_game_mode, _diag)
```

This includes the early `GameMode.NONE and check_fill(board)` return, the mode-specific `check_fill(board)` return, and the final return after color fallback.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recognition_ml_overlay.py -q`

Expected: PASS.

- [x] **Step 5: Regression verification**

Run: `python -m pytest tests/test_special_detection.py -q`

Expected: PASS after Task 7 migrates the old no-ML-switch assertion.

---

### Task 5: Thread ML Mode Through Runtime and Write Debug JSON

**Files:**
- Modify: `runtime.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** This task does not add the GUI control. Tests can construct `CheckBestMoveRequest(ml_recognition_mode="shadow")` directly.

- [x] **Step 1: Write failing tests**

Add focused tests to `tests/test_move_debug.py`:

```python
def test_check_best_move_request_defaults_ml_recognition_mode_off():
    request = bot.CheckBestMoveRequest(
        mode=bot.normalize_game_mode(None),
        special_piece_mode=bot.SPECIAL_PIECE_MODE_AUTO,
        selected_profile="regular",
        allow_square_matches=True,
        specials_explode_immediately=False,
        score_rally_values=None,
        selected_perks=(bot.PERK_NONE, bot.PERK_NONE),
        cursor_return_position=(10, 20),
    )

    assert request.ml_recognition_mode == bot.ML_RECOGNITION_OFF


def test_recognition_attempt_summary_drops_ml_debug_payload_and_rounds_numbers():
    payload = {"mode": "shadow"}
    summary = bot._recognition_attempt_summary(
        {
            "screenshot_ms": 1.234,
            "ml_recognition_mode": "shadow",
            "ml_available": True,
            "ml_debug_payload": payload,
        }
    )

    assert summary["screenshot_ms"] == 1.2
    assert summary["ml_recognition_mode"] == "shadow"
    assert summary["ml_available"] is True
    assert "ml_debug_payload" not in summary


def test_write_ml_recognition_debug_payload(tmp_path):
    run_dir = tmp_path / "run"
    payload = {"mode": "shadow", "summary": {"predictions": 1}, "cells": []}

    bot.write_ml_recognition_debug_payload(run_dir, payload)

    saved = json.loads((run_dir / "ml_recognition.json").read_text(encoding="utf-8"))
    assert saved == payload
```

Add one runtime integration test near existing `run_check_best_move_request` tests:

```python
def test_run_check_best_move_sets_ml_mode_and_writes_debug_payload(monkeypatch, tmp_path):
    run_dir = tmp_path / "run"
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    source_board = tmp_path / "source.png"
    Image.new("RGB", (20, 20), "red").save(source_board)
    score_path = tmp_path / "score.png"
    Image.new("RGB", (10, 10), "white").save(score_path)

    evaluation = MoveEvaluation(
        score=10.0,
        start=(0, 0),
        direction="right",
        immediate_score=10.0,
        special_score=0.0,
        potential_score=0.0,
        mode_score=0.0,
        blue_score=0.0,
        cascade_count=0.0,
        board_potential=0.0,
        lookahead_bonus=0.0,
        explanation="test",
    )

    def fake_update(game_board, game_special, **kwargs):
        game_board[:] = [row[:] for row in board]
        game_special[:] = [row[:] for row in special_board]
        kwargs["_diag"].update(
            {
                "screenshot_ms": 1.0,
                "ml_recognition_mode": "shadow",
                "ml_available": True,
                "ml_predictions": 4,
                "ml_accepted": 0,
                "ml_rejected": 4,
                "ml_debug_payload": {"mode": "shadow", "summary": {"predictions": 4}, "cells": []},
            }
        )
        return game_board, game_special

    monkeypatch.setattr(bot, "create_debug_run_dir", lambda: run_dir)
    monkeypatch.setattr(bot, "find_previous_debug_run", lambda _run_dir: None)
    monkeypatch.setattr(bot, "score_region_from_board", lambda: (0, 0, 10, 10))
    monkeypatch.setattr(bot, "capture_score_region", lambda *args, **kwargs: score_path)
    monkeypatch.setattr(bot, "update_board_2", fake_update)
    monkeypatch.setattr(bot, "rank_moves", lambda *args, **kwargs: [evaluation])
    monkeypatch.setattr(bot, "prioritize_ranked_moves", lambda ranked, **kwargs: ranked)
    monkeypatch.setattr(bot, "detect_booster_activate", lambda _path: {"active": False, "score": 0.0})
    monkeypatch.setattr(bot, "rank_perk_actions", lambda *args, **kwargs: [])
    monkeypatch.setattr(bot, "write_move_debug_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(bot, "play_best_move_with_cursor_restore", lambda *args, **kwargs: True)

    bot.run_check_best_move_request(
        bot.CheckBestMoveRequest(
            mode=bot.normalize_game_mode(None),
            special_piece_mode=bot.SPECIAL_PIECE_MODE_AUTO,
            selected_profile="regular",
            allow_square_matches=True,
            specials_explode_immediately=False,
            score_rally_values=None,
            selected_perks=(bot.PERK_NONE, bot.PERK_NONE),
            cursor_return_position=(10, 20),
            debug_enabled=True,
            ml_recognition_mode="shadow",
        )
    )

    assert bot.ml_recognition_mode == bot.ML_RECOGNITION_SHADOW
    saved = json.loads((run_dir / "ml_recognition.json").read_text(encoding="utf-8"))
    assert saved["mode"] == "shadow"
    timings = json.loads((run_dir / "timings.json").read_text(encoding="utf-8"))
    attempt = timings["recognition_breakdown"]["attempts"][0]
    assert attempt["ml_predictions"] == 4
    assert "ml_debug_payload" not in attempt
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: FAIL for missing `ml_recognition_mode`, `_recognition_attempt_summary`, `write_ml_recognition_debug_payload`, or ML debug file output.

- [x] **Step 3: Implement focused change**

In `runtime.py`:

1. Import ML constants if needed:

```python
from ml_recognition_runtime import ML_RECOGNITION_OFF, normalize_ml_recognition_mode
```

2. Add field:

```python
ml_recognition_mode: str = ML_RECOGNITION_OFF
```

to `CheckBestMoveRequest`.

3. Add helpers:

```python
ML_RECOGNITION_DEBUG_FILENAME = "ml_recognition.json"


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


def write_ml_recognition_debug_payload(run_dir, payload):
    if payload is None:
        return
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / ML_RECOGNITION_DEBUG_FILENAME).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
```

4. In `run_check_best_move_request(...)`, after `debug_enabled = request.debug_enabled`, add:

```python
recognition.set_ml_recognition_mode(request.ml_recognition_mode)
```

5. Replace:

```python
_attempts_diag.append({k: round(v, 1) for k, v in _attempt_diag.items()})
```

with:

```python
_attempts_diag.append(_recognition_attempt_summary(_attempt_diag))
```

6. Track the latest debug payload:

```python
_ml_debug_payload = None
...
_ml_debug_payload = _attempt_diag.get("ml_debug_payload")
```

7. After `write_move_debug_report(...)` succeeds in the `if debug_enabled:` block, call:

```python
write_ml_recognition_debug_payload(debug_run_dir, _ml_debug_payload)
```

8. Pre-scanned boards do not rescan, so they do not produce a new ML payload. Leave `ml_recognition.json` absent for pre-scanned requests unless the future caller supplies one explicitly.

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS after Task 6 and Task 7 complete any GUI/test migrations. If GUI tests still fail because the control is absent, continue to Task 6 and rerun.

- [x] **Step 5: Targeted runtime verification**

Run: `python -m pytest tests/test_move_debug.py -k "ml_recognition or debug_payload or debug_disabled" -q`

Expected: PASS.

---

### Task 6: Add GUI Mode Control and State Persistence

**Files:**
- Modify: `gui.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** This task exposes and persists the mode. It does not alter overlay rules, ONNX inference, or move strategy.

- [x] **Step 1: Write failing tests**

Modify the existing GUI setup/state tests in `tests/test_move_debug.py`.

Replace assertions that no ML control exists with:

```python
def _ml_mode_values(ui):
    return [ui.MLRecognitionModeBox.itemData(index) for index in range(ui.MLRecognitionModeBox.count())]
```

In `test_main_window_layout_has_expected_controls` or the local equivalent, assert:

```python
assert ui.MLRecognitionModeBox.count() == 3
assert _ml_mode_values(ui) == [
    bot.ML_RECOGNITION_OFF,
    bot.ML_RECOGNITION_SHADOW,
    bot.ML_RECOGNITION_HYBRID,
]
assert ui.MLRecognitionModeBox.currentData() == bot.ML_RECOGNITION_OFF
assert ui.gui_state_payload()["ml_recognition_mode"] == bot.ML_RECOGNITION_OFF
```

Replace legacy load test with:

```python
def test_load_gui_state_persists_ml_recognition_mode_and_ignores_legacy_bool(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state_path = tmp_path / "gui_state.json"
    state_path.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "None",
                "board_profile": "regular",
                "special_piece_mode": "none",
                "debug_mode": True,
                "ml_mode": True,
                "ml_recognition_mode": bot.ML_RECOGNITION_SHADOW,
                "booster_charge": 3,
                "remaining_moves": 2,
                "auto_state": False,
                "showdown_mode": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot, "GUI_STATE_PATH", state_path)

    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    ui.load_gui_state()

    assert ui.DebugModeCheck.isChecked() is True
    assert ui.MLRecognitionModeBox.currentData() == bot.ML_RECOGNITION_SHADOW
    assert ui.BoosterChargeSpin.value() == 3
    assert ui.RemainingMovesSpin.value() == 2


def test_load_gui_state_invalid_ml_recognition_mode_falls_back_to_off(monkeypatch, tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    state_path = tmp_path / "gui_state.json"
    state_path.write_text(json.dumps({"ml_recognition_mode": "invalid"}), encoding="utf-8")
    monkeypatch.setattr(bot, "GUI_STATE_PATH", state_path)

    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    ui.MLRecognitionModeBox.setCurrentIndex(2)
    ui.load_gui_state()

    assert ui.MLRecognitionModeBox.currentData() == bot.ML_RECOGNITION_OFF
```

Extend request-building tests:

```python
def test_build_check_best_move_request_includes_ml_recognition_mode(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    monkeypatch.setattr(bot.pyautogui, "position", lambda: (10, 20))
    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    bot._set_combo_data(ui.MLRecognitionModeBox, bot.ML_RECOGNITION_HYBRID)

    request = ui._build_check_best_move_request()

    assert request.ml_recognition_mode == bot.ML_RECOGNITION_HYBRID
```

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_move_debug.py -k "ml_recognition or main_window_layout or load_gui_state or build_check_best_move_request" -q`

Expected: FAIL for missing `MLRecognitionModeBox` or missing payload key.

- [x] **Step 3: Implement focused change**

In `gui.py`:

1. Import constants:

```python
from ml_recognition_runtime import (
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_SHADOW,
    normalize_ml_recognition_mode,
)
```

2. Add options near other GUI constants:

```python
ML_RECOGNITION_OPTIONS = (
    ("ML off", ML_RECOGNITION_OFF),
    ("ML shadow", ML_RECOGNITION_SHADOW),
    ("ML hybrid", ML_RECOGNITION_HYBRID),
)
```

3. In `setupUi(...)`, add a combo box near `DebugModeCheck`:

```python
self.MLRecognitionModeBox = QtWidgets.QComboBox(self.centralwidget)
self.MLRecognitionModeBox.setGeometry(QtCore.QRect(10, 405, 130, 25))
self.MLRecognitionModeBox.setFont(status_font)
self.MLRecognitionModeBox.setObjectName("MLRecognitionModeBox")
for _label, value in ML_RECOGNITION_OPTIONS:
    self.MLRecognitionModeBox.addItem("")
    self.MLRecognitionModeBox.setItemData(self.MLRecognitionModeBox.count() - 1, value)
```

Adjust nearby y positions if needed so controls do not overlap. Keep the existing compact desktop UI style.

4. In `retranslateUi(...)`:

```python
for index, (label, _value) in enumerate(ML_RECOGNITION_OPTIONS):
    self.MLRecognitionModeBox.setItemText(index, _translate("MainWindow", label))
```

5. In `gui_state_payload(...)`:

```python
"ml_recognition_mode": self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_OFF,
```

6. In `load_gui_state(...)`:

```python
ml_mode = normalize_ml_recognition_mode(payload.get("ml_recognition_mode"))
_set_combo_data(self.MLRecognitionModeBox, ml_mode)
```

Do not read legacy `ml_mode` as an enable signal.

7. In `_build_check_best_move_request(...)`:

```python
ml_recognition_mode=self.MLRecognitionModeBox.currentData() or ML_RECOGNITION_OFF,
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_move_debug.py -k "ml_recognition or main_window_layout or load_gui_state or build_check_best_move_request" -q`

Expected: PASS.

- [x] **Step 5: Full GUI/debug test file**

Run: `python -m pytest tests/test_move_debug.py -q`

Expected: PASS.

---

### Task 7: Migrate Old No-ML Assertions and Run Full Verification

**Files:**
- Modify: `tests/test_special_detection.py`
- Modify: `tests/test_move_debug.py`
- Modify: `test.py` only if facade exports are missing

**Security flag:** `none`

**Does NOT cover:** This task does not add new runtime behavior. It aligns tests and public facade exposure with the approved ML modes.

- [x] **Step 1: Replace old special-detection assertion**

In `tests/test_special_detection.py`, replace:

```python
def test_recognition_runtime_exposes_no_ml_switch():
    assert not hasattr(bot, "USE_" + "ML_RECOGNITION")
```

with:

```python
def test_recognition_runtime_exposes_explicit_ml_modes_without_legacy_boolean():
    assert bot.normalize_ml_recognition_mode("off") == bot.ML_RECOGNITION_OFF
    assert bot.normalize_ml_recognition_mode("shadow") == bot.ML_RECOGNITION_SHADOW
    assert bot.normalize_ml_recognition_mode("hybrid") == bot.ML_RECOGNITION_HYBRID
    assert not hasattr(bot, "USE_" + "ML_RECOGNITION")
```

- [x] **Step 2: Remove old no-control helper**

In `tests/test_move_debug.py`, remove `_assert_no_model_checkbox(...)` and replace call sites with ML mode assertions from Task 6. Keep the assertion that legacy boolean `ml_mode` is not trusted.

- [x] **Step 3: Ensure facade exposure**

If tests import through `import test as bot` and cannot see ML runtime symbols, update `test.py`:

```python
import ml_recognition_runtime

_FORWARD_MODULES = (gui, runtime, recognition, capture, screen_state_reader, ml_recognition_runtime)
```

Only add this if missing facade exposure causes test failures. Do not duplicate constants in `test.py`.

- [x] **Step 4: Run targeted suite**

Run: `python -m pytest tests/test_dataset_classes.py tests/test_ml_recognition_runtime.py tests/test_recognition_ml_overlay.py tests/test_special_detection.py tests/test_move_debug.py -q`

Expected: PASS.

- [x] **Step 5: Active reference sweep**

Run: `rg -n "USE_ML_RECOGNITION|MlModeCheck|\\bml_mode\\b" *.py tests`

Expected:

- No `USE_ML_RECOGNITION`.
- No `MlModeCheck`.
- `ml_mode` may appear only in tests as a legacy JSON key proving it is ignored. If it appears in production code, remove it.

- [x] **Step 6: Stub scan on touched production files**

Run: `rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" dataset_classes.py ml_recognition_runtime.py recognition.py runtime.py gui.py test.py`

Expected: no matches in touched production code.

- [x] **Step 7: Full regression suite**

Run: `python -m pytest -q`

Expected: PASS.

## Stop Conditions

Stop and ask the user before proceeding if:

- `onnxruntime` import crashes Python instead of raising a normal exception.
- Full pytest failures appear outside files touched by this plan and the cause is not obvious.
- Adding the GUI control would overlap existing controls without a clear compact placement.
- Model metadata contains a class that `decode_class(...)` cannot map.
- Runtime ML adds more than `50 ms` inference time after the first lazy load in local debug evidence.

## Expected Final Behavior

- Bot starts with `ML off` unless `gui_state.json` explicitly contains a valid `ml_recognition_mode`.
- `ML off` preserves current template/color behavior.
- `ML shadow` runs ML and writes diagnostics without changing the returned board.
- `ML hybrid` overlays only accepted high-confidence ML predictions and falls back per cell otherwise.
- New debug runs can contain `ml_recognition.json` with per-cell confidence, threshold, accept/reject reason, and template comparison.
- `timings.json` includes ML summary fields without embedding the full per-cell payload.
- Old boolean `ml_mode` cannot silently enable ML.
- Full pytest suite passes.
