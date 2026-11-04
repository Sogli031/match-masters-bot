# Recognition Runtime ML Path - Design

_Sub-project C of the "ML recognition revival" initiative._

Status: **Draft for user review**
Date: 2026-05-25
Predecessors:
- Sub-project A - [docs/specs/2026-05-24-recognition-dataset-builder-design.md](2026-05-24-recognition-dataset-builder-design.md)
- Sub-project B - [docs/specs/2026-05-24-recognition-cnn-training-design.md](2026-05-24-recognition-cnn-training-design.md)

## 1. Goal and Scope

Add a runtime recognition path that can consume `models/recognition_model.onnx` and
`models/recognition_model.metadata.json` during live play, while keeping the existing
template/color recognizer as the safe fallback.

The runtime path must:

1. Load the ONNX model and sidecar metadata lazily.
2. Slice the live board screenshot into per-cell crops using the active board profile.
3. Run batched per-cell inference.
4. Decode model classes back into `(board[row][col], special_board[row][col])`.
5. Accept ML predictions only when the per-class confidence threshold is met.
6. Fall back to the current template/color result when ML is unavailable, low-confidence,
   disabled, or explicitly blocked by threshold `1.01`.
7. Write debug diagnostics that show what ML predicted, what was accepted, and what
   remained template-based.

### Non-goals

- No retraining changes. Sub-project B already owns `train_recognition_model.py`.
- No dataset UI changes. Sub-project A owns `dataset_cli` and review flows.
- No ML-only runtime as the default.
- No removal of template/color recognition.
- No move-strategy changes.
- No automatic online learning during live play.
- No hidden behavior switch. The selected ML mode must be visible in GUI state and debug
  diagnostics.

## 2. Existing Runtime Anchors

Current recognition entry point:

- `recognition.update_board_2(board, special_board, screenshot_path=None, write_screenshot=True, _diag=None)`

Current live call path:

- `gui.Ui_MainWindow._build_check_best_move_request(...)`
- `runtime.CheckBestMoveRequest`
- `runtime.run_check_best_move_request(...)`
- `recognition.update_board_2(...)`

Current debug artifacts:

- `Debug/runs/<run_id>/board.png`
- `Debug/runs/<run_id>/move.json`
- `Debug/runs/<run_id>/timings.json`

Important existing tests currently assert that no ML switch exists. Those tests were
correct for the template-only cleanup, but Sub-project C intentionally changes that
contract. They must be replaced with tests for explicit ML modes and safe fallback.

## 3. Considered Approaches

### Option A: Shadow-only ML

Run ONNX beside the template recognizer and only write diagnostics. Do not affect the
returned board.

Pros:
- Lowest gameplay risk.
- Good for collecting disagreement evidence.

Cons:
- Does not fix live recognition mistakes by itself.
- User still has to inspect debug output manually.

### Option B: Feature-flagged hybrid ML overlay (recommended)

Keep template/color recognition as the baseline. Add explicit modes:

- `off`: current behavior.
- `shadow`: run ML and write diagnostics, but return the template result.
- `hybrid`: return the template result except where ML passes confidence and safety gates.

Pros:
- Safe default.
- Allows live improvement without deleting proven template logic.
- Gives a clean debugging path: compare `shadow` and `hybrid`.
- Works even when ONNX runtime is missing.

Cons:
- Slightly more code than ML-only.
- Requires per-cell merge rules.

### Option C: ML-only recognizer

Replace `update_board_2` output with model predictions.

Pros:
- Simple data flow.
- Easier to reason about model accuracy in isolation.

Cons:
- High risk for low-support classes.
- Current model has many classes with zero or low validation support.
- Breaks useful hand-written detectors for mode-specific pieces.

**Decision:** Use Option B.

## 4. Runtime Modes

Add a small mode enum or normalized string API:

```python
ML_RECOGNITION_OFF = "off"
ML_RECOGNITION_SHADOW = "shadow"
ML_RECOGNITION_HYBRID = "hybrid"
```

Default: `off`.

Reason: the previous runtime was deliberately cleaned back to template-only. The new ML
path should be opt-in until live debug evidence shows it is stable enough for the user's
board profile and current game modes.

GUI behavior:

- Add a compact combo box or segmented control near `Debug mode`.
- Labels:
  - `ML off`
  - `ML shadow`
  - `ML hybrid`
- Persist as `ml_recognition_mode` in `gui_state.json`.
- Load legacy keys defensively:
  - Ignore old boolean `ml_mode`.
  - If `ml_recognition_mode` is invalid, fall back to `off`.

Request/runtime behavior:

- Add `ml_recognition_mode: str = "off"` to `CheckBestMoveRequest`.
- GUI passes the selected mode into the request.
- Runtime applies the request mode before calling `update_board_2`.
- Auto pre-scan must use the same selected mode as manual move checks.

## 5. ML Runtime Module

Create a new module, proposed name: `ml_recognition_runtime.py`.

Public surface:

```python
@dataclass(frozen=True)
class TilePrediction:
    row: int
    col: int
    predicted_class: str
    confidence: float
    threshold: float
    accepted: bool
    reason: str
    board_value: int
    special_value: int


@dataclass(frozen=True)
class RecognitionMlResult:
    available: bool
    mode: str
    model_version: str | None
    predictions: list[TilePrediction]
    load_error: str | None = None
    inference_ms: float = 0.0


def predict_board_tiles(
    img_color: PIL.Image.Image,
    board_length: int,
    square_size: int,
    mode: str,
    model_path: Path = Path("models/recognition_model.onnx"),
    metadata_path: Path = Path("models/recognition_model.metadata.json"),
) -> RecognitionMlResult:
    ...
```

Implementation rules:

- Import `onnxruntime` lazily inside the module, not at top-level import of `recognition.py`.
- Cache the `InferenceSession` and metadata by `(model_path, metadata_path, mtime)`.
- If the model or metadata changes after retraining, reload on the next request.
- Use metadata preprocessing:
  - RGB
  - resize to `64x64`
  - scale by `1/255`
  - apply metadata mean/std if present
- Run all cells in one batch: 49 cells for 7x7, 64 cells for 8x8.
- Convert logits to softmax confidence.
- Use `thresholds_per_class[class]` from metadata, defaulting to `fallback_threshold_default`
  or `0.9` when absent.
- Threshold `1.01` means "never accept this class in hybrid mode".

## 6. Class Decoding

`dataset_classes.classify(color, special)` already maps runtime board values to class
strings. Sub-project C needs the inverse mapping.

Add to `dataset_classes.py`:

```python
def decode_class(class_name: str) -> tuple[int, int]:
    ...
```

Rules:

- `blocked` -> `(BLOCKED, 0)`.
- `empty` -> `(0, 0)`, but `hybrid` should not accept `empty` for live board cells in
  the first implementation. It can be reported in diagnostics only.
- `disco_ball` -> `(DISCO_BALL, SPECIAL_DISCO_BALL)`.
- `cleo_bug` -> `(1, SPECIAL_CLEO_BUG)` because the existing detector writes color `1`.
- `billie_drone` -> `(BLOCKED, SPECIAL_BILLIE_DRONE)`.
- `mode_target` -> `(1, SPECIAL_MODE_TARGET)` unless implementation evidence shows the
  current mode-specific branch expects a different color.
- `<color>_<suffix>` -> color code from `_COLOR_NAMES` and special code from
  `_COLOR_BOUND_SUFFIXES`.
- Unknown classes raise `ValueError` during metadata validation, causing ML mode to
  degrade to unavailable instead of crashing gameplay.

The exact color for color-agnostic special classes must be pinned by tests against current
`recognition.py` behavior before implementation is marked done.

## 7. Merge Rules in `update_board_2`

Keep the current template/color pipeline as baseline.

Proposed order:

1. Capture screenshot once in `update_board_2` as today.
2. Run existing template/special/mode/color logic to produce `board` and `special_board`.
3. If ML mode is `off`, return current baseline.
4. If ML mode is `shadow`, run ML and write diagnostics, but return baseline unchanged.
5. If ML mode is `hybrid`, run ML and overlay accepted cells.

Hybrid acceptance gates:

- Reject if ML is unavailable.
- Reject if `predicted_class == "empty"`.
- Reject if confidence `< threshold`.
- Reject if threshold `> 1.0`.
- Reject if `decode_class()` fails.
- Reject if the active game mode produced a mode-specific target and the ML class is a
  generic normal gem for the same cell.
- Accept if the baseline cell is `0` and ML passes all gates.
- Accept if the baseline cell is a normal gem and ML predicts a same-color special with
  passing confidence.
- Accept if both baseline and ML are normal gems and ML confidence passes; this lets the
  CNN fix color mistakes.
- For color-agnostic specials (`disco_ball`, `cleo_bug`, `billie_drone`, `mode_target`),
  accept only at threshold `>= 0.9` in the first implementation, even if metadata contains
  a lower threshold.

This keeps the first runtime version conservative. More aggressive override rules can be
added later after live debug comparisons.

## 8. Diagnostics

Add recognition diagnostics into `_diag`, which already feeds `timings.json`:

```json
{
  "ml_recognition_mode": "hybrid",
  "ml_available": true,
  "ml_model_version": "2026-05-25T02:04:35",
  "ml_inference_ms": 12.4,
  "ml_predictions": 49,
  "ml_accepted": 4,
  "ml_rejected": 45,
  "ml_unavailable_reason": null
}
```

When debug is enabled, also write:

```text
Debug/runs/<run_id>/ml_recognition.json
```

Payload:

```json
{
  "mode": "hybrid",
  "model_version": "2026-05-25T02:04:35",
  "summary": {
    "accepted": 4,
    "rejected": 45,
    "unavailable_reason": null
  },
  "cells": [
    {
      "row": 0,
      "col": 0,
      "template_board": 1,
      "template_special": 0,
      "ml_class": "red_normal",
      "confidence": 0.997,
      "threshold": 0.5,
      "accepted": true,
      "reason": "confidence_pass"
    }
  ]
}
```

This is the main answer to "I want to see the whole system and percentages": the training
report shows validation accuracy per class, while `ml_recognition.json` shows the actual
live per-cell confidences and accept/reject reasons for every debug run.

## 9. Error Handling

ML mode must never make live recognition crash.

Fallback cases:

| Case | Runtime behavior |
|---|---|
| Missing `models/recognition_model.onnx` | ML unavailable, template result returned |
| Missing metadata | ML unavailable, template result returned |
| `onnxruntime` import fails | ML unavailable, template result returned |
| Metadata schema mismatch | ML unavailable, template result returned |
| Unknown class in metadata | ML unavailable, template result returned |
| Inference raises | ML unavailable for that attempt, template result returned |
| Threshold `1.01` | Class is never accepted in `hybrid` |
| Invalid GUI mode | Normalize to `off` |

Warnings should be printed at most once per process for repeated unavailable states.
Debug diagnostics should still record the unavailable reason per run.

## 10. Performance Constraints

The live move click is already sensitive to recognition latency, especially when retrying
after zero cells. Runtime ML must be measured separately.

Targets:

- `ml_inference_ms <= 50 ms` on CPU for 49 or 64 cells after first lazy load.
- First-load session setup may be slower, but it must be visible in diagnostics.
- Batch inference must be used. Per-cell ONNX calls are not acceptable.

If `hybrid` adds too much latency, the mode can remain `shadow` or `off` while collecting
diagnostics.

## 11. Tests

Add tests before implementation.

### `tests/test_dataset_classes.py`

- `decode_class(classify(color, special)) == (color, special)` for supported color-bound
  classes.
- `decode_class("blocked")`.
- `decode_class("disco_ball")`.
- `decode_class("billie_drone")`.
- Unknown class raises `ValueError`.

### `tests/test_ml_recognition_runtime.py`

- Missing model returns unavailable result, no exception.
- Metadata class order and thresholds are loaded.
- Threshold `1.01` rejects the class.
- Softmax decoding returns expected class and confidence from fake logits.
- Session cache reloads when model/metadata mtime changes.
- Batch shape is `(board_length * board_length, 3, 64, 64)`.

Use a fake ONNX session object in most tests. One optional smoke test may use real
`onnxruntime` and should skip when unavailable.

### `tests/test_recognition_ml_overlay.py`

- `off` mode returns template baseline unchanged.
- `shadow` mode returns template baseline unchanged and records ML diagnostics.
- `hybrid` fills a baseline `0` cell when ML passes threshold.
- `hybrid` rejects `empty`.
- `hybrid` rejects threshold `1.01`.
- `hybrid` can correct a normal color when confidence passes.
- ML unavailable in `hybrid` returns template baseline unchanged.

### `tests/test_move_debug.py`

- GUI exposes the ML mode control.
- `gui_state_payload()` includes `ml_recognition_mode`.
- `load_gui_state()` persists valid modes and ignores invalid/legacy values safely.
- `CheckBestMoveRequest` carries the selected mode.
- `timings.json` includes ML diagnostics when mode is not `off`.
- `ml_recognition.json` is written in debug mode when ML ran.

### Existing test migration

Replace:

- `test_recognition_runtime_exposes_no_ml_switch`
- assertions that `("ml" + "_mode") not in ui.gui_state_payload()`
- `_assert_no_model_checkbox(...)`

With explicit tests for the new control and fallback behavior.

## 12. Manual Acceptance Flow

After implementation, a safe manual rollout should be:

1. Start the bot with `Debug mode` enabled.
2. Set ML mode to `shadow`.
3. Play one full game.
4. Inspect the newest `Debug/runs/<run_id>/ml_recognition.json` files:
   - compare template vs ML class
   - check confidence percentages
   - check rejected classes and threshold reasons
5. If shadow disagreements look reasonable, switch to `hybrid`.
6. Play another game.
7. Review `move.json`, `timings.json`, and `ml_recognition.json`.
8. If bad examples appear, append/review them into `data/recognition_dataset`, retrain,
   then continue with `shadow` before returning to `hybrid`.

## 13. Failure Modes and Mitigations

| Failure mode | Severity | Mitigation |
|---|---:|---|
| Bad model corrupts live board | High | Default `off`, `shadow` mode, conservative `hybrid` gates, template fallback |
| Low-support class looks 100% accurate but has too few examples | High | Keep per-class `low_support` report, threshold gates, manual debug review |
| `onnxruntime` breaks import or crashes | High | Lazy import, exception boundary, template fallback, optional real-ORT tests |
| ML hides template regressions | Medium | `shadow` diagnostics and per-cell template-vs-ML JSON |
| Runtime slows down move click | Medium | Batch inference, timing fields, keep `off` and `shadow` available |
| Mode-specific targets get overwritten | Medium | Conservative merge rule blocks generic ML override of mode-specific baseline |
| Retrained model is not picked up | Medium | Cache keyed by file mtime |
| Legacy GUI state enables unexpected ML | Medium | Ignore legacy `ml_mode`; only accept explicit `ml_recognition_mode` values |

## 14. Implementation Boundaries

Expected files to touch:

- `dataset_classes.py`
- `ml_recognition_runtime.py`
- `recognition.py`
- `runtime.py`
- `gui.py`
- `test.py` facade only if needed for compatibility exports
- tests listed in section 11

Expected files not to touch:

- `move_strategy.py`
- `board_profiles.py`
- `train_recognition_model.py`
- `recognition_model.py`
- `recognition_dataset.py`
- `recognition_metrics.py`
- `recognition_onnx_export.py`
- `data/recognition_dataset/manifest.json`
- files under `models/` except as user-generated training artifacts

## 15. Open Questions for User Approval

1. Should the GUI default remain `ML off` after implementation, or should it default to
   `ML shadow` so every debug game gathers comparison data?
2. Should `hybrid` be allowed to correct normal gem colors immediately, or should the
   first version only fill `0` cells and detected specials?
3. Is `ML hybrid` acceptable as a manual toggle only, or should auto mode force `shadow`
   until we have reviewed at least one complete game?

Recommended answers:

1. Default `ML off` for safety.
2. Allow normal-gem color correction only above threshold, because this is the main value
   of the CNN.
3. Manual toggle only; auto should obey the selected mode.
