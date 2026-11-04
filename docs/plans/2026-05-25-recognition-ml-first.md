# Recognition ML First Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `ML first` runtime mode that uses ML per cell when safe and falls back to template recognition otherwise.

**Architecture:** Extend the existing ML mode constants and GUI option list. Reuse `recognition.apply_ml_recognition_overlay(...)` for both `hybrid` and `first`, with mode-specific merge policy. Extend `ml_recognition_runtime.build_ml_debug_payload(...)` so debug shows template, ML, and final values per cell.

**Tech Stack:** Python 3, PyQt5, PIL, NumPy, pytest.

**Assumptions:**
- Assumes the existing `off/shadow/hybrid` ML runtime path is present - will NOT recreate the training pipeline.
- Assumes template recognition still runs to provide fallback and debug comparison - will NOT remove template logic.
- Assumes `first` remains manually selected - will NOT make ML the default.

---

## File Structure

- `ml_recognition_runtime.py`: add the `first` mode constant and include final board/special values in debug payload.
- `recognition.py`: add mode-specific overlay behavior. `first` accepts safe ML cells over any template cell; rejected ML cells keep template fallback.
- `gui.py`: add the `ML first` option and persist/load it through the existing state path.
- `runtime.py`: no structural change expected; it already carries normalized mode and writes `ml_recognition.json`.
- `test.py`: facade automatically forwards module constants; no direct edit expected.
- `tests/test_ml_recognition_runtime.py`: mode normalization and debug payload assertions.
- `tests/test_recognition_ml_overlay.py`: per-cell `first` acceptance/fallback behavior.
- `tests/test_move_debug.py`: GUI option/request/debug integration.

## Tasks

### Task 1: Tests First

**Files:**
- Modify: `tests/test_ml_recognition_runtime.py`
- Modify: `tests/test_recognition_ml_overlay.py`
- Modify: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** Real ONNX accuracy or retraining.

- [x] Add failing tests for mode normalization, GUI options, `first` replacing template specials, fallback on low confidence/disabled thresholds, strict risky-special minimum, final debug fields, and request propagation.
- [x] Run:

```powershell
python -m pytest tests/test_ml_recognition_runtime.py tests/test_recognition_ml_overlay.py tests/test_move_debug.py -q
```

Expected: FAIL because `ML_RECOGNITION_FIRST` and final debug fields do not exist yet.

Observed: FAIL during test collection because `ML_RECOGNITION_FIRST` was not exported yet.

### Task 2: Implement Mode and Merge

**Files:**
- Modify: `ml_recognition_runtime.py`
- Modify: `recognition.py`
- Modify: `gui.py`

**Security flag:** `none`

**Does NOT cover:** Changing template thresholds or model metadata.

- [x] Add `ML_RECOGNITION_FIRST = "first"` to recognized modes.
- [x] Add `"ML first"` to `ML_RECOGNITION_OPTIONS`.
- [x] Make `apply_ml_recognition_overlay(...)` evaluate `first` with the shared confidence gates but without `hybrid` baseline-protection gates.
- [x] Add final board/special values to `build_ml_debug_payload(...)`.
- [x] Run the targeted tests again and expect PASS.

Observed: `127 passed in 4.25s`.

### Task 3: Verification

**Files:**
- All touched files.

**Security flag:** `none`

**Does NOT cover:** Live BlueStacks gameplay; that still needs a manual run.

- [x] Run targeted tests:

```powershell
python -m pytest tests/test_ml_recognition_runtime.py tests/test_recognition_ml_overlay.py tests/test_move_debug.py -q
```

- [x] Run full suite:

```powershell
python -m pytest -q
```

Expected: PASS.

Observed: targeted suite `127 passed in 4.25s`; full suite `549 passed in 36.81s`.
