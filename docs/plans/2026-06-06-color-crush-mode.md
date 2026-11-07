# Color Crush Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class `Color Crush Mode` support to the Match Masters playable bot.
**Architecture:** Extend the existing `GameMode` enum and mode option lists. Reuse the existing Color Crush simulation context, but force it on for `Color Crush Mode`. Reuse existing Score Rally color-value plumbing for scoring and add effective booster charge calculation for Color Crush mode.
**Tech Stack:** Python 3, pytest, PyQt5 UI tests, existing `move_strategy.py`, `runtime.py`, `recognition.py`, `gui.py`, `tests/test_move_strategy.py`, `tests/test_move_debug.py`.
**Assumptions:**
- Assumes green/orange/purple/yellow charge defaults from the screenshot are 1/2/3/4 - will NOT auto-read changing live values from pixels.
- Assumes the existing Score Rally UI remains the manual override - will NOT create a new mode-specific settings panel.
- Assumes this checkout is not a Git worktree - will NOT create commits or run Git branch operations.

---

## File Structure

- `move_strategy.py`: add `GameMode.COLOR_CRUSH`, default color-charge values, red exclusion from Color Crush clearing, and effective booster-charge helpers.
- `runtime.py`: expose the mode in `GAME_MODE_OPTIONS`, force Color Crush simulation for the mode, and use default color-charge values when custom values are absent.
- `recognition.py`: expose the mode in `GAME_MODE_OPTIONS` and avoid special target detection for this mode.
- `gui.py`: update tooltip text to mention red/blue exclusion.
- `tests/test_move_strategy.py`: add engine tests for normalization, red exclusion, default charge values, and booster-fill prioritization.
- `tests/test_move_debug.py`: add UI/runtime tests for dropdown visibility and automatic runtime mode behavior.

## Tasks

### Task 1: Mode Contract and Color Crush Rules

**Does NOT cover:** runtime request wiring or GUI behavior.

- [ ] Write failing tests proving `Color Crush Mode` normalizes, red matches do not whole-color crush, and default charge values are 4/3/1/2 for yellow/purple/green/orange.
- [ ] Implement `GameMode.COLOR_CRUSH`, `COLOR_CRUSH_MODE`, `COLOR_CRUSH_DEFAULT_SCORE_VALUES`, and red exclusion.
- [ ] Run focused tests:
  `python -m pytest tests/test_move_strategy.py::test_color_crush_mode_normalizes_and_has_default_values tests/test_move_strategy.py::test_color_crush_excludes_red_matches -q`

### Task 2: Booster Priority Uses Color Charge

**Does NOT cover:** live detection of charge values from screenshots.

- [ ] Write a failing test where Color Crush mode with a near-ready booster prefers a green/orange/purple/yellow charge-fill move over a higher raw score move.
- [ ] Add effective booster-charge cells to priority context without changing normal blue-only behavior outside Color Crush mode.
- [ ] Run focused test:
  `python -m pytest tests/test_move_strategy.py::test_prioritize_ranked_moves_color_crush_uses_weighted_color_charge_for_booster_fill -q`

### Task 3: Runtime and UI Wiring

**Does NOT cover:** creating a separate UI settings panel.

- [ ] Write failing tests proving `Color Crush Mode` appears in the UI mode list and `run_check_best_move_request(...)` passes `color_crush=True` plus default values to ranking when custom Score Rally is not supplied.
- [ ] Add the mode to runtime and recognition option lists, force the runtime flag for the mode, and update the tooltip.
- [ ] Run focused tests:
  `python -m pytest tests/test_move_debug.py::test_main_window_has_current_score_extra_move_and_auto_action_buttons tests/test_move_debug.py::test_run_check_best_move_request_color_crush_mode_forces_crush_defaults -q`

### Task 4: Verification

- [ ] Run:
  `python -m pytest tests/test_move_strategy.py tests/test_move_debug.py -q`
- [ ] Run:
  `python -m py_compile move_strategy.py runtime.py recognition.py gui.py tests/test_move_strategy.py tests/test_move_debug.py`
- [ ] Run stub scan on modified production files:
  `rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" move_strategy.py runtime.py recognition.py gui.py`

## Expected Final Behavior

- `Color Crush Mode` is selectable.
- In that mode, a yellow/purple/green/orange match clears all same-color pieces and red/blue matches do not.
- If custom Score Rally values are off, defaults are yellow=4, purple=3, green=1, orange/brown=2.
- Booster-fill ranking uses those effective charge values for Color Crush mode and keeps existing blue-only behavior in other modes.

