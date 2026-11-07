# Magic Wand Booster Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Magic Wand as a ready-booster action that clicks one chosen board color and models full-color removal.
**Architecture:** Add a pure strategy evaluator in `move_strategy.py`, wire a new `BOOSTER_ACTION_MAGIC_WAND` through `runtime.py` and the existing GUI combo, and write debug output as `magic_wand_target`. Reuse the existing High Voltage click helper shape without changing High Voltage scoring.
**Tech Stack:** Python 3, PyQt5, pytest, existing `runtime.py`, `gui.py`, `move_strategy.py`, and `test.py` facade.
**Assumptions:**
- Assumes the board already contains recognized color and special-board state; this will not train recognition or add labels.
- Assumes Magic Wand removes one full selected color; this will not implement multi-color or repeated picks.
- Assumes the existing booster readiness gates stay authoritative; this will not activate Wand before the existing booster policy chooses `activate_booster`.

---

## Files

- `move_strategy.py`: add Magic Wand target evaluation and chooser.
- `runtime.py`: add action constant, normalization, debug serialization, and activation branch.
- `gui.py`: no direct code expected beyond consuming `BOOSTER_ACTION_OPTIONS`.
- `tests/test_move_strategy.py`: pure strategy target tests.
- `tests/test_booster_activation.py`: normalization and click helper tests.
- `tests/test_move_debug.py`: UI option, serialization, debug, and runtime branch tests.

## Tasks

- [ ] Add failing tests for Magic Wand target choice and scoring.
- [ ] Add failing tests for `booster_action_mode` normalization and GUI options.
- [ ] Add failing tests for runtime Magic Wand activation and debug serialization.
- [ ] Implement the pure Magic Wand evaluator by reusing clear/drop/cascade scoring.
- [ ] Wire the new booster action through runtime constants, debug output, and activation branch.
- [ ] Run focused pytest commands, compile key files, and run the relevant broader tests.

## Verification Commands

```powershell
python -m pytest tests/test_move_strategy.py -q
python -m pytest tests/test_booster_activation.py -q
python -m pytest tests/test_move_debug.py -q
python -m py_compile move_strategy.py runtime.py gui.py test.py
python -m pytest -q
```

## Stop Conditions

- Stop before changing ML model, dataset classes, or recognition thresholds.
- Stop before changing High Voltage target selection.
- Stop if Magic Wand requires more than one color pick.
