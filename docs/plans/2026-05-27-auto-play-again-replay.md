# Auto Play Again Replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in replay toggle that lets existing `Auto` click `PLAY AGAIN` after a match ends and continue into the next match.
**Architecture:** Keep `gui.py` as the auto-loop controller. Add replay detection and click helpers in `runtime.py`, using the current board crop and active board-profile coordinates. Persist the new GUI checkbox through the existing `gui_state.json` payload.
**Tech Stack:** Python, PyQt5, PIL, OpenCV/NumPy, pytest.
**Assumptions:** Assumes the finished-match screen places `PLAY AGAIN` in the lower-left/middle area of the board crop and `CLOSE` to the right. It will not work if the game moves `PLAY AGAIN` outside that crop or uses a button shape/color outside the supported red/orange/yellow and blue backgrounds.

---

## File Structure

- `runtime.py`: replay detection dataclass, image detector, click helper, replay cooldown constant.
- `gui.py`: new checkbox, GUI persistence, auto-loop replay branch, transient reset helper.
- `tests/test_move_debug.py`: focused regression tests for detection, GUI toggle persistence, and auto-loop behavior.

## Tasks

### Task 1: Add replay detection tests

**Files:**
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** Live BlueStacks screenshots; this task uses deterministic synthetic crops.

- [ ] Write failing tests for red/orange, yellow, and blue play-again button crops, and for a close-only crop outside the play-again region.
- [ ] Run: `python -m pytest tests\test_move_debug.py -q -k "play_again or replay"`
- [ ] Expected: FAIL because replay helpers do not exist yet.

### Task 2: Implement replay detection and click helper

**Files:**
- Modify: `runtime.py`

**Security flag:** `none`

**Does NOT cover:** OCR; detection is shape/color based and scoped to the known button area.

- [ ] Add `AUTO_POST_PLAY_AGAIN_COOLDOWN_SECONDS`.
- [ ] Add `PlayAgainDetection`.
- [ ] Add `detect_play_again_button(image)`.
- [ ] Add `click_play_again_button(detection, return_position=None)`.
- [ ] Run the focused replay detector tests.

### Task 3: Add GUI toggle and auto-loop branch

**Files:**
- Modify: `gui.py`
- Test: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** Changing auto move selection; replay only runs before normal board play.

- [ ] Write failing GUI tests for default-off toggle, persisted state, no-click when disabled, and click/reset/cooldown when enabled.
- [ ] Add `AutoReplayCheck` next to `Auto`.
- [ ] Save and load `auto_replay`.
- [ ] Add a transient reset helper reused by manual reset and replay.
- [ ] In `_handle_auto_scan_finished`, detect finished-match screen before board-stability handling. Click only when `AutoReplayCheck` is enabled.
- [ ] Run focused GUI replay tests.

### Task 4: Verification

**Files:**
- Verify: `runtime.py`
- Verify: `gui.py`
- Verify: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** Live BlueStacks smoke, unless a live game is open and the user explicitly asks for it.

- [ ] Run: `python -m pytest tests\test_move_debug.py -q -k "play_again or replay or auto"`
- [ ] Run: `python -m pytest tests\test_move_debug.py tests\test_perks.py -q`
- [ ] Run: `python -m py_compile gui.py runtime.py test.py`
- [ ] Run stub scan: `rg -n "TODO|FIXME|placeholder|NotImplementedError|raise NotImplementedError" gui.py runtime.py tests\test_move_debug.py`
