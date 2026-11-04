# Vinnie Valentine SE Hearts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Vinnie Valentine SE two-color hearts with explicit ordinary-vs-SE recognition selection.
**Architecture:** Encode each SE heart color pair in `special_board`, keep the primary color in `board`, and make match/clear logic decode the pair. Recognition loads optional pair templates and obeys the selected special-piece mode. GUI persists and passes that selected mode into runtime requests.
**Tech Stack:** Python, PyQt5, NumPy/OpenCV, pytest.
**Assumptions:** SE heart templates will be added later under `assets/general/vinnie_se_heart_<color1>_<color2>.png` — live SE detection will not work until at least one real template exists. Vinnie insertion count is unknown — this plan only handles the board after insertion.

---

## Files

- `move_strategy.py`: SE heart special constants, helpers, match expansion, clearing behavior.
- `recognition.py`: SE mode constant, optional SE template loading, detector gating.
- `runtime.py`: debug labels and imports for SE helpers.
- `gui.py`: special-piece mode combo, state persistence, request propagation.
- `dataset_classes.py`: dataset taxonomy for SE heart pair classes.
- `tests/test_move_strategy.py`: SE matching and clearing tests.
- `tests/test_special_detection.py`: recognition mode and SE template gating tests.
- `tests/test_move_debug.py`: GUI propagation/debug serialization tests.
- `tests/test_dataset_classes.py`: SE dataset class tests.

## Tasks

### Task 1: SE Heart Strategy Semantics

**Files:** `move_strategy.py`, `tests/test_move_strategy.py`
**Security flag:** `none`
**Does NOT cover:** recognition templates or GUI selection.

- [x] Add failing tests for `make_vinnie_se_heart_special(RED, YELLOW)`, match-as-red, match-as-yellow, clearing both colors, and two-heart combo clearing up to four colors.
- [x] Run: `python -m pytest tests\test_move_strategy.py -k "vinnie_se_heart or kindred" -q`
- [x] Implement SE heart constants/helpers, pass `special_board` into match scanning, and clear SE heart color pairs in `_special_effect_cells`.
- [x] Re-run the same command until green.

### Task 2: Recognition Mode And Optional Templates

**Files:** `recognition.py`, `tests/test_special_detection.py`
**Security flag:** `none`
**Does NOT cover:** creating real image assets.

- [x] Add failing tests proving `SPECIAL_PIECE_MODE_HEARTS` calls only ordinary detector, `SPECIAL_PIECE_MODE_VINNIE_SE_HEARTS` calls only SE detector, and `normalize_special_piece_mode()` accepts SE aliases.
- [x] Run: `python -m pytest tests\test_special_detection.py -k "vinnie_se or hearts_mode_only" -q`
- [x] Implement SE mode, optional `load_vinnie_se_heart_templates()`, `find_vinnie_se_heart_candidates()`, and update `update_board_2()` gating.
- [x] Re-run the same command until green.

### Task 3: GUI Selector Propagation

**Files:** `gui.py`, `tests/test_move_debug.py`
**Security flag:** `none`
**Does NOT cover:** changing move/action-mode semantics.

- [x] Add failing tests for a new `SpecialPieceModeBox`, persisted `special_piece_mode`, and `_build_check_best_move_request().special_piece_mode`.
- [x] Run: `python -m pytest tests\test_move_debug.py -k "special_piece_mode" -q`
- [x] Add the combo box using `SPECIAL_PIECE_MODE_OPTIONS`, load/save state, and send the selected value to runtime.
- [x] Re-run the same command until green.

### Task 4: Debug And Dataset Serialization

**Files:** `runtime.py`, `dataset_classes.py`, `tests/test_move_debug.py`, `tests/test_dataset_classes.py`
**Security flag:** `none`
**Does NOT cover:** ML retraining or manifest migration.

- [x] Add failing tests for SE debug labels and dataset class names such as `yellow_red_vinnie_se_heart`.
- [x] Run: `python -m pytest tests\test_dataset_classes.py tests\test_move_debug.py -k "vinnie_se" -q`
- [x] Implement helper-aware labels/classification/decoding.
- [x] Re-run the same command until green.

### Task 5: Verification

**Files:** changed files above.
**Security flag:** `none`
**Does NOT cover:** live BlueStacks smoke or ML model retraining.

- [x] Run: `python -m pytest tests\test_move_strategy.py tests\test_special_detection.py tests\test_move_debug.py tests\test_dataset_classes.py -q`
- [x] Run: `python -m py_compile move_strategy.py recognition.py runtime.py gui.py dataset_classes.py test.py`
- [x] Run: `rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" move_strategy.py recognition.py runtime.py gui.py dataset_classes.py`
- [x] Expected: tests and compile pass; stub scan has no output.
