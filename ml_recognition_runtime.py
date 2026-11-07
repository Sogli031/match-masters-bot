from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from dataset_classes import PURPLE_GEM_CLASSES, RETIRED_DATASET_CLASSES, decode_class

ML_RECOGNITION_OFF = "off"
ML_RECOGNITION_SHADOW = "shadow"
ML_RECOGNITION_HYBRID = "hybrid"
ML_RECOGNITION_FIRST = "first"
ML_RECOGNITION_ONLY = "only"
ML_RECOGNITION_MODES = {
    ML_RECOGNITION_OFF,
    ML_RECOGNITION_SHADOW,
    ML_RECOGNITION_HYBRID,
    ML_RECOGNITION_FIRST,
    ML_RECOGNITION_ONLY,
}

DEFAULT_MODEL_PATH = Path("models") / "recognition_model.onnx"
DEFAULT_METADATA_PATH = Path("models") / "recognition_model.metadata.json"

_SESSION_CACHE = {}
_SESSION_FAILURE_CACHE = {}
MAX_METADATA_THRESHOLD = 1.01


@dataclass(frozen=True)
class TilePrediction:
    row: int
    col: int
    predicted_class: str
    confidence: float
    threshold: float
    board_value: int
    special_value: int
    normal_color_family_confidence: float | None = None
    mode_target_family_confidence: float | None = None
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
    if not all(isinstance(class_name, str) for class_name in classes):
        raise ValueError("metadata classes must contain strings")

    active_classes = [
        class_name for class_name in classes if class_name not in RETIRED_DATASET_CLASSES
    ]
    if not active_classes:
        raise ValueError("metadata classes must include at least one active class")
    for class_name in active_classes:
        decode_class(class_name)

    preprocessing = payload.get("input", {}).get("preprocessing", {})
    resize_to = preprocessing.get("resize_to")
    if (
        not isinstance(resize_to, list)
        or len(resize_to) != 2
        or not all(isinstance(value, int) and value > 0 for value in resize_to)
    ):
        raise ValueError("metadata input.preprocessing.resize_to must be two positive integers")

    thresholds = payload.get("thresholds_per_class", {})
    if not isinstance(thresholds, dict):
        raise ValueError("metadata thresholds_per_class must be an object")
    for class_name, threshold in thresholds.items():
        if class_name not in classes:
            raise ValueError(f"threshold references unknown class: {class_name}")
        _validate_metadata_threshold(threshold, f"thresholds_per_class.{class_name}")

    _validate_metadata_threshold(
        payload.get("fallback_threshold_default", 0.9),
        "fallback_threshold_default",
    )
    return payload


def _mask_retired_class_logits(logits: np.ndarray, classes: list[str]) -> np.ndarray:
    retired_indices = [
        index
        for index, class_name in enumerate(classes)
        if class_name in RETIRED_DATASET_CLASSES
    ]
    if not retired_indices:
        return logits
    masked = logits.copy()
    masked[:, retired_indices] = -np.inf
    return masked


def _validate_metadata_threshold(value, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metadata {field_name} threshold must be numeric")
    threshold = float(value)
    if not math.isfinite(threshold):
        raise ValueError(f"metadata {field_name} threshold must be finite")
    if threshold < 0.0 or threshold > MAX_METADATA_THRESHOLD:
        raise ValueError(
            f"metadata {field_name} threshold must be between 0.0 and {MAX_METADATA_THRESHOLD}"
        )
    return threshold


def _default_session_factory(model_path: Path):
    import onnxruntime  # type: ignore

    return onnxruntime.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])


def prewarm_onnxruntime(importer=__import__) -> str | None:
    if any(
        name == "PyQt5" or name.startswith("PyQt5.")
        for name in sys.modules
    ):
        return "skipped_after_pyqt_loaded"
    try:
        onnxruntime = importer("onnxruntime")
        onnxruntime.get_available_providers()
    except Exception as exc:
        return str(exc)
    return None


def _session_cache_identity(model_path: Path, metadata_path: Path, session_factory) -> tuple:
    factory_key = "default" if session_factory is None else id(session_factory)
    return (
        str(model_path.resolve()),
        str(metadata_path.resolve()),
        factory_key,
    )


def _session_cache_key(model_path: Path, metadata_path: Path, session_factory) -> tuple:
    return (
        *_session_cache_identity(model_path, metadata_path, session_factory),
        model_path.stat().st_mtime_ns,
        metadata_path.stat().st_mtime_ns,
    )


def _get_session(model_path: Path, metadata_path: Path, session_factory):
    key = _session_cache_key(model_path, metadata_path, session_factory)
    cached = _SESSION_CACHE.get(key)
    if cached is not None:
        return cached

    factory = session_factory or _default_session_factory
    session = factory(model_path)
    identity = _session_cache_identity(model_path, metadata_path, session_factory)
    for cached_key in list(_SESSION_CACHE):
        if cached_key[:3] == identity:
            del _SESSION_CACHE[cached_key]
    _SESSION_CACHE[key] = session
    return session


def _clear_stale_session_failures(identity: tuple, keep_key: tuple):
    for cached_key in list(_SESSION_FAILURE_CACHE):
        if cached_key[:3] == identity and cached_key != keep_key:
            del _SESSION_FAILURE_CACHE[cached_key]


def _preprocess_cells(image: Image.Image, board_length: int, square_size: int, metadata: dict) -> np.ndarray:
    preprocessing = metadata["input"]["preprocessing"]
    resize_to = tuple(preprocessing["resize_to"])
    scale = float(preprocessing.get("scale", 1.0 / 255.0))
    mean = np.asarray(preprocessing.get("mean", [0.0, 0.0, 0.0]), dtype=np.float32)
    std = np.asarray(preprocessing.get("std", [1.0, 1.0, 1.0]), dtype=np.float32)
    if mean.shape != (3,) or std.shape != (3,):
        raise ValueError("metadata preprocessing mean/std must have three values")

    cells = []
    rgb = image.convert("RGB")
    for row in range(board_length):
        for col in range(board_length):
            left = col * square_size
            top = row * square_size
            crop = rgb.crop((left, top, left + square_size, top + square_size))
            crop = crop.resize(resize_to, Image.BILINEAR)
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
        session_key = _session_cache_key(model_path, metadata_path, session_factory)
        identity = _session_cache_identity(model_path, metadata_path, session_factory)
        _clear_stale_session_failures(identity, session_key)
        cached_session_failure = _SESSION_FAILURE_CACHE.get(session_key)
        if cached_session_failure is not None:
            elapsed = (time.perf_counter() - start) * 1000.0
            return RecognitionMlResult(
                False,
                normalized_mode,
                None,
                [],
                cached_session_failure,
                elapsed,
            )

        try:
            session = _get_session(model_path, metadata_path, session_factory)
        except Exception as exc:
            _SESSION_FAILURE_CACHE[session_key] = str(exc)
            elapsed = (time.perf_counter() - start) * 1000.0
            return RecognitionMlResult(False, normalized_mode, None, [], str(exc), elapsed)

        _SESSION_FAILURE_CACHE.pop(session_key, None)
        input_name = session.get_inputs()[0].name
        batch = _preprocess_cells(img_color, board_length, square_size, metadata)
        outputs = session.run(None, {input_name: batch})
        logits = np.asarray(outputs[0], dtype=np.float32)
        if logits.ndim != 2:
            raise ValueError("model output must be a 2D logits array")

        expected_cells = board_length * board_length
        classes = list(metadata["classes"])
        if logits.shape != (expected_cells, len(classes)):
            raise ValueError(
                f"model output shape {logits.shape} does not match {(expected_cells, len(classes))}"
            )

        probs = _softmax(_mask_retired_class_logits(logits, classes))
        thresholds = metadata.get("thresholds_per_class", {})
        fallback_threshold = float(metadata.get("fallback_threshold_default", 0.9))
        class_indices = {class_name: index for index, class_name in enumerate(classes)}
        # Purple Gem prints a growing number on the gem. Above the trained range
        # the model spreads its probability over several numbered gem classes,
        # so no single class clears its threshold. The number never reaches the
        # board engine (every gem is just SPECIAL_MODE_TARGET), so keep the
        # family total: it says "this is a gem" without saying which number.
        mode_target_family_indices = [
            class_indices[class_name]
            for class_name in (*PURPLE_GEM_CLASSES, "mode_target")
            if class_name in class_indices
        ]
        predictions = []
        for index in range(expected_cells):
            class_index = int(np.argmax(probs[index]))
            class_name = classes[class_index]
            board_value, special_value = decode_class(class_name)
            normal_color_family_confidence = None
            if class_name.endswith("_normal"):
                color_name = class_name.removesuffix("_normal")
                family_names = (
                    class_name,
                    f"{color_name}_hot_color_3",
                    f"{color_name}_hot_color_4",
                    f"{color_name}_hot_color_5",
                )
                normal_color_family_confidence = sum(
                    float(probs[index, class_indices[family_name]])
                    for family_name in family_names
                    if family_name in class_indices
                )
            mode_target_family_confidence = None
            if mode_target_family_indices:
                mode_target_family_confidence = float(
                    probs[index, mode_target_family_indices].sum()
                )
            row, col = divmod(index, board_length)
            predictions.append(
                TilePrediction(
                    row=row,
                    col=col,
                    predicted_class=class_name,
                    confidence=float(probs[index, class_index]),
                    threshold=float(thresholds.get(class_name, fallback_threshold)),
                    board_value=board_value,
                    special_value=special_value,
                    normal_color_family_confidence=normal_color_family_confidence,
                    mode_target_family_confidence=mode_target_family_confidence,
                )
            )

        elapsed = (time.perf_counter() - start) * 1000.0
        return RecognitionMlResult(
            True,
            normalized_mode,
            metadata.get("model_version"),
            predictions,
            None,
            elapsed,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - start) * 1000.0
        return RecognitionMlResult(False, normalized_mode, None, [], str(exc), elapsed)


def build_ml_debug_payload(
    result: RecognitionMlResult,
    template_board,
    template_special_board,
    final_board=None,
    final_special_board=None,
) -> dict:
    accepted = sum(1 for prediction in result.predictions if prediction.accepted)
    final_board = template_board if final_board is None else final_board
    final_special_board = (
        template_special_board if final_special_board is None else final_special_board
    )
    cells = []
    for prediction in result.predictions:
        cells.append(
            {
                "row": prediction.row,
                "col": prediction.col,
                "template_board": template_board[prediction.row][prediction.col],
                "template_special": template_special_board[prediction.row][prediction.col],
                "final_board": final_board[prediction.row][prediction.col],
                "final_special": final_special_board[prediction.row][prediction.col],
                "ml_class": prediction.predicted_class,
                "ml_board": prediction.board_value,
                "ml_special": prediction.special_value,
                "confidence": round(prediction.confidence, 6),
                "normal_color_family_confidence": (
                    round(prediction.normal_color_family_confidence, 6)
                    if prediction.normal_color_family_confidence is not None
                    else None
                ),
                "mode_target_family_confidence": (
                    round(prediction.mode_target_family_confidence, 6)
                    if prediction.mode_target_family_confidence is not None
                    else None
                ),
                "threshold": prediction.threshold,
                "accepted": prediction.accepted,
                "reason": prediction.reason,
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
