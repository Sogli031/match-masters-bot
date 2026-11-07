# Fireworks Directional Tiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add color-bound directional Fireworks tile classes and use their direction in recognition and strategy.
**Architecture:** `move_strategy.py` owns the new special ids and directional effect cells. `recognition.py` maps Fireworks templates to those ids while preserving detected color. `dataset_classes.py` exposes `<color>_firework_<direction>` labels for dataset review and training. `runtime.py` only adds readable debug labels.
**Tech Stack:** Python, OpenCV template matching, pytest.
**Assumptions:**
- Assumes Fireworks rockets should keep color in the dataset class name - will NOT work correctly if labels are color-agnostic and scoring needs the original tile color.
- Assumes generic `up_firework.png` is available for up-direction template loading - will NOT detect new live up variants until matching templates are added.

---

## Files

- Modify `move_strategy.py` for constants, intent names, Fireworks rocket checks, and directional effect cells.
- Modify `recognition.py` for Fireworks template-to-direction mapping.
- Modify `dataset_classes.py` for reviewable class names.
- Modify `runtime.py` for debug labels.
- Modify `tests/test_dataset_classes.py`, `tests/test_special_detection.py`, and `tests/test_move_strategy.py` for regression coverage.
- Update `data/recognition_dataset/classes.json` to reflect the canonical class taxonomy.

## Tasks

### Task 1: Dataset Classes

- [x] Add failing tests that `yellow_firework_up`, `orange_firework_left`, `purple_firework_down`, and `green_firework_right` exist, decode to the new special ids, and round-trip through `classify`.
- [x] Add the four `firework_*` suffixes to color-bound dataset classes.
- [x] Update `data/recognition_dataset/classes.json`.
- [x] Verify with `python -m pytest tests\test_dataset_classes.py -q`.

### Task 2: Strategy Direction Effects

- [x] Add failing tests proving directional Fireworks specials clear only their arrow path, not the full row or column.
- [x] Add failing tests proving the new Fireworks specials still suppress adjacent special-special swap activation in Fireworks mode.
- [x] Add the new special constants and directional effect cells.
- [x] Verify with `python -m pytest tests\test_move_strategy.py -q -k "firework"`.

### Task 3: Recognition Mapping

- [x] Add failing tests proving Fireworks template specs map row-left, row-right, column-up, and column-down filenames to directional special ids.
- [x] Update the live Fireworks fixture expectation from horizontal/vertical to directional ids.
- [x] Map live and generic Fireworks templates to directional ids.
- [x] Verify with `python -m pytest tests\test_special_detection.py -q -k "fireworks"`.

### Task 4: Runtime Labels and Final Verification

- [x] Add Fireworks labels in runtime debug maps.
- [x] Run targeted tests:

```powershell
python -m pytest tests\test_dataset_classes.py tests\test_special_detection.py tests\test_move_strategy.py -q
```

- [x] Compile changed modules:

```powershell
python -m py_compile move_strategy.py recognition.py runtime.py dataset_classes.py test.py
```

- [x] Stub scan production files:

```powershell
rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" move_strategy.py recognition.py runtime.py dataset_classes.py
```

## Expected Final Behavior

The review/training class list includes color plus direction names such as
`yellow_firework_up`. Fireworks mode recognition writes directional special
codes. Strategy uses those codes to clear only the arrow direction, and the auto
move logic still treats them as Fireworks rockets for special-swap gating.
