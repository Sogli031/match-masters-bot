# Auto Mode Adaptive Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-optimized:subagent-driven-development (recommended) or superpowers-optimized:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make auto mode wait for 2 normal matching clean scans, or 3 matching clean scans after suspicious/post-move evidence, before it plays another automatic highest-points move.
**Architecture:** Keep auto stabilization inside `runtime.AutoMoveStability`; keep `gui.py` as a consumer of the existing `observe(...)`, `required_scans`, `stable_count`, `wait_reason`, and `waiting_for_change` surface. Auto mode continues to scan asynchronously and continues to pass the stable `pre_scanned_board` into the existing highest-points worker. Manual `Check Best Move`, move ranking, ML training/runtime model behavior, perk behavior, booster behavior, and scoring policy remain unchanged.
**Tech Stack:** Python 3, PyQt5 GUI, pytest, PIL test images, existing Match Masters runtime modules.
**Assumptions:**
- Assumes auto mode currently routes through `gui.Ui_MainWindow._handle_auto_scan_finished(...)` and `runtime.AutoMoveStability.observe(...)` — will NOT work if auto moves are triggered from a separate path.
- Assumes `AutoMoveStability.required_scans` is the display-facing active requirement — will NOT work if UI status starts reading another field.
- Assumes this checkout remains non-Git as described by `project-map.md` — do not add commit steps or run Git commands unless the user explicitly changes that workflow.

---

## Approved Scope

Implement the approved Option B from `docs/specs/2026-05-25-auto-mode-adaptive-stability-design.md`:

- Normal stable board: auto may play after 2 matching clean observations.
- Suspicious/post-move board: auto may play only after 3 matching clean observations.
- Suspicious means unrecognized cells, motion above threshold, visual hash jump, or the first changed board after an auto-played signature.
- `mark_played(...)` must make the next changed board use the 3-scan requirement.
- After a cautious 3-scan gate succeeds, the active requirement returns to 2 for the next ordinary board.
- Keep the current fast timer cadence; no blocking fixed delay loop.
- Keep `pre_scanned_board` reuse so the check worker does not rescan the board.

## Non-Goals

- Do not change move ranking or strategy weights.
- Do not change ML model files, ML training, or ML confidence thresholds.
- Do not change manual `Check Best Move`.
- Do not implement the broader recognition majority-vote layer.
- Do not change perk, booster, score OCR, or debug-run schema behavior.
- Do not add new UI controls.

## File Structure

- Modify `runtime.py`: auto timing constants and `AutoMoveStability` adaptive state.
- Modify `tests/test_move_debug.py`: regression tests for adaptive stability and existing GUI auto handoff.
- No planned changes to `gui.py`: GUI should keep using `AutoMoveStability.required_scans` for `Auto: stabilno x/y` and should keep passing `pre_scanned_board`.
- No planned changes to model, dataset, recognition, ranking, or debug writer files.

## Stop Conditions

Stop and ask the user before proceeding if:

- Implementing the plan requires changing manual `Check Best Move`.
- Implementing the plan requires changing move ranking, ML recognition contracts, or debug output schema.
- Tests show that `gui.py` no longer uses the stable pre-scanned board.
- The full pytest suite fails outside the touched auto-stability surface.

## Expected Final Behavior

- Auto status can show `Auto: stabilno 1/2`, `Auto: stabilno 1/3`, or `Auto: stabilno 2/3`.
- A stable board from a fresh auto start plays after the second matching clean scan.
- After an auto move finishes, unchanged board signatures are blocked as `Auto: ceka promenu`.
- Once the board changes after a played signature, auto requires three matching clean scans before playing.
- If motion, visual jump, or unrecognized cells appear, auto waits and requires three matching clean scans before the next play.
- The move that finally plays still uses the existing highest-points worker with the stable `pre_scanned_board`.

---

### Task 1: Lock Timing Defaults And Normal 2-Scan Gate

**Files:**
- Modify: `runtime.py`
- Modify: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** This task does not implement suspicious escalation to 3 scans. It only locks the new constants and normal stable-board behavior.

- [x] **Step 1: Replace the timing defaults test**

Replace `test_auto_move_timing_uses_current_fast_play_defaults` in `tests/test_move_debug.py` with:

```python
def test_auto_move_timing_uses_adaptive_stability_defaults():
    assert bot.AUTO_STABLE_REQUIRED_SCANS == 2
    assert bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS == 3
    assert bot.AUTO_SCAN_INTERVAL_MS == 25
    assert bot.AUTO_SCAN_INTERVAL_MS * bot.AUTO_STABLE_REQUIRED_SCANS == 50
    assert bot.AUTO_POST_MOVE_COOLDOWN_SECONDS == 0.12
```

- [x] **Step 2: Add a normal fresh-board gate assertion**

Add this test near the existing `AutoMoveStability` tests in `tests/test_move_debug.py`:

```python
def test_auto_move_stability_default_requires_two_clean_observations():
    stability = bot.AutoMoveStability()
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]

    assert stability.required_scans == 2
    assert stability.observe(board, special_board, visual_hash=123, motion_score=0.0) is False
    assert stability.wait_reason == "stable"
    assert stability.stable_count == 1
    assert stability.required_scans == 2

    assert stability.observe(board, special_board, visual_hash=123, motion_score=0.0) is True
    assert stability.stable_count == 2
    assert stability.required_scans == 2
```

- [x] **Step 3: Run focused tests to verify failure**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: FAIL because `AUTO_STABLE_REQUIRED_SCANS` is still `1`, `AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS` does not exist, and cooldown is still `0.06`.

- [x] **Step 4: Update timing constants in `runtime.py`**

Change the auto constants near the top of `runtime.py` to:

```python
AUTO_SCAN_INTERVAL_MS = 25
AUTO_STABLE_REQUIRED_SCANS = 2
AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS = 3
AUTO_POST_MOVE_COOLDOWN_SECONDS = 0.12
```

Update `AutoMoveStability.__init__` to accept the suspicious requirement while preserving existing tests that pass `required_scans=...`:

```python
class AutoMoveStability:
    def __init__(
        self,
        required_scans=AUTO_STABLE_REQUIRED_SCANS,
        suspicious_required_scans=AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS,
        motion_threshold=AUTO_MOTION_THRESHOLD,
        hash_max_distance=AUTO_VISUAL_HASH_MAX_DISTANCE,
    ):
        self.base_required_scans = required_scans
        self.suspicious_required_scans = max(suspicious_required_scans, required_scans)
        self.required_scans = required_scans
        self.motion_threshold = motion_threshold
        self.hash_max_distance = hash_max_distance
        self.reset()
```

In `reset(...)`, set the active requirement back to the base value:

```python
    def reset(self):
        self.last_signature = None
        self.last_visual_hash = None
        self.last_hash_distance = None
        self.last_motion_score = 0.0
        self.stable_count = 0
        self.played_signature = None
        self.waiting_for_change = False
        self.wait_reason = None
        self.previous_image = None
        self.required_scans = self.base_required_scans
        self.suspicious_until_stable = False
```

- [x] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: Existing tests may still fail where they encode the old post-move or GUI 1-scan assumptions; the new timing and fresh-board tests should pass.

---

### Task 2: Add Suspicious 3-Scan Gate In AutoMoveStability

**Files:**
- Modify: `runtime.py`
- Modify: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** This task does not change GUI worker startup, manual check behavior, ranking, ML recognition, or debug output.

- [x] **Step 1: Replace the post-move stability test**

Replace `test_auto_move_stability_requires_repeated_board_and_change_after_play` in `tests/test_move_debug.py` with:

```python
def test_auto_move_stability_requires_three_clean_observations_after_played_board_changes():
    stability = bot.AutoMoveStability()
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    changed_board = [[1, 2], [4, 3]]
    signature = bot.auto_board_signature(board, special_board)

    assert stability.observe(board, special_board, visual_hash=10, motion_score=0.0) is False
    assert stability.observe(board, special_board, visual_hash=10, motion_score=0.0) is True
    assert stability.required_scans == bot.AUTO_STABLE_REQUIRED_SCANS

    stability.mark_played(signature)
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(board, special_board, visual_hash=10, motion_score=0.0) is False
    assert stability.waiting_for_change is True
    assert stability.wait_reason == "change"

    assert stability.observe(changed_board, special_board, visual_hash=11, motion_score=0.0) is False
    assert stability.waiting_for_change is False
    assert stability.stable_count == 1
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(changed_board, special_board, visual_hash=11, motion_score=0.0) is False
    assert stability.stable_count == 2
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(changed_board, special_board, visual_hash=11, motion_score=0.0) is True
    assert stability.stable_count == 3
    assert stability.required_scans == bot.AUTO_STABLE_REQUIRED_SCANS
```

- [x] **Step 2: Extend unrecognized-cell test**

Update `test_auto_move_stability_ignores_unrecognized_cells` in `tests/test_move_debug.py` to:

```python
def test_auto_move_stability_ignores_unrecognized_cells_and_requires_cautious_recovery():
    stability = bot.AutoMoveStability()
    board = [[1, 0], [3, 4]]
    clean_board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]

    assert stability.observe(board, special_board, visual_hash=1, motion_score=0.0) is False
    assert stability.stable_count == 0
    assert stability.last_signature is None
    assert stability.wait_reason == "unrecognized"
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(clean_board, special_board, visual_hash=2, motion_score=0.0) is False
    assert stability.observe(clean_board, special_board, visual_hash=2, motion_score=0.0) is False
    assert stability.observe(clean_board, special_board, visual_hash=2, motion_score=0.0) is True
    assert stability.required_scans == bot.AUTO_STABLE_REQUIRED_SCANS
```

- [x] **Step 3: Replace motion and visual tests**

Replace `test_auto_move_stability_waits_for_low_motion_before_counting` with:

```python
def test_auto_move_stability_waits_for_low_motion_then_requires_three_clean_observations():
    stability = bot.AutoMoveStability()
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]

    assert (
        stability.observe(
            board,
            special_board,
            visual_hash=123,
            motion_score=bot.AUTO_MOTION_THRESHOLD + 0.1,
        )
        is False
    )
    assert stability.stable_count == 0
    assert stability.wait_reason == "motion"
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(board, special_board, visual_hash=123, motion_score=0.0) is False
    assert stability.stable_count == 1
    assert stability.observe(board, special_board, visual_hash=123, motion_score=0.0) is False
    assert stability.stable_count == 2
    assert stability.observe(board, special_board, visual_hash=123, motion_score=0.0) is True
    assert stability.required_scans == bot.AUTO_STABLE_REQUIRED_SCANS
```

Replace `test_auto_move_stability_resets_when_visual_hash_jumps_on_same_signature` with:

```python
def test_auto_move_stability_resets_when_visual_hash_jumps_and_requires_three_clean_observations():
    stability = bot.AutoMoveStability(hash_max_distance=2)
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]

    assert stability.observe(board, special_board, visual_hash=0b0000, motion_score=0.0) is False
    assert stability.observe(board, special_board, visual_hash=0b1111, motion_score=0.0) is False

    assert stability.wait_reason == "visual"
    assert stability.stable_count == 1
    assert stability.required_scans == bot.AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS

    assert stability.observe(board, special_board, visual_hash=0b1111, motion_score=0.0) is False
    assert stability.stable_count == 2
    assert stability.observe(board, special_board, visual_hash=0b1111, motion_score=0.0) is True
    assert stability.required_scans == bot.AUTO_STABLE_REQUIRED_SCANS
```

- [x] **Step 4: Run focused tests to verify failure**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: FAIL because suspicious observations do not yet raise the active requirement to 3 and successful cautious stabilization does not yet return the requirement to 2.

- [x] **Step 5: Implement adaptive state helpers in `runtime.py`**

Add these methods inside `AutoMoveStability`, between `reset(...)` and `observe(...)`:

```python
    def _require_suspicious_stability(self):
        self.required_scans = self.suspicious_required_scans
        self.suspicious_until_stable = True

    def _clear_suspicious_stability_if_ready(self):
        if self.suspicious_until_stable:
            self.required_scans = self.base_required_scans
            self.suspicious_until_stable = False
```

Then update `observe(...)` so every suspicious path calls `_require_suspicious_stability()` before returning. The full method should read:

```python
    def observe(self, board, special_board, visual_hash=None, motion_score=0.0):
        self.wait_reason = None
        self.last_hash_distance = None
        self.last_motion_score = float(motion_score or 0.0)

        if board_has_unrecognized_cells(board):
            self.last_signature = None
            self.last_visual_hash = None
            self.stable_count = 0
            self.wait_reason = "unrecognized"
            self._require_suspicious_stability()
            return False

        signature = auto_board_signature(board, special_board)
        if self.last_motion_score > self.motion_threshold:
            self.last_signature = signature
            self.last_visual_hash = visual_hash
            self.stable_count = 0
            self.wait_reason = "motion"
            self._require_suspicious_stability()
            return False

        if (
            signature == self.last_signature
            and self.last_visual_hash is not None
            and visual_hash is not None
        ):
            self.last_hash_distance = auto_visual_hash_distance(self.last_visual_hash, visual_hash)
            if self.last_hash_distance is not None and self.last_hash_distance > self.hash_max_distance:
                self.last_visual_hash = visual_hash
                self.stable_count = 1
                self.wait_reason = "visual"
                self._require_suspicious_stability()
                return False

        if self.waiting_for_change and signature == self.played_signature:
            self.wait_reason = "change"
            return False

        if self.waiting_for_change and signature != self.played_signature:
            self._require_suspicious_stability()
            self.waiting_for_change = False
            self.played_signature = None
            self.last_signature = None
            self.last_visual_hash = None
            self.stable_count = 0

        if signature == self.last_signature:
            self.stable_count += 1
        else:
            self.last_signature = signature
            self.stable_count = 1
        self.last_visual_hash = visual_hash

        self.wait_reason = "stable"
        if self.stable_count >= self.required_scans:
            self._clear_suspicious_stability_if_ready()
            return True
        return False
```

Update `mark_played(...)` so post-move recovery is cautious:

```python
    def mark_played(self, signature=None):
        self.played_signature = signature if signature is not None else self.last_signature
        self.waiting_for_change = self.played_signature is not None
        self.last_signature = None
        self.last_visual_hash = None
        self.last_hash_distance = None
        self.stable_count = 0
        if self.waiting_for_change:
            self._require_suspicious_stability()
```

- [x] **Step 6: Run focused tests**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: PASS for the updated `AutoMoveStability` behavior. If GUI auto tests fail because they still force `required_scans=1`, continue to Task 3.

---

### Task 3: Preserve GUI Pre-Scanned Auto Handoff With 2-Scan Gate

**Files:**
- Modify: `tests/test_move_debug.py`
- Modify: `gui.py` only if the test proves current GUI behavior is broken.

**Security flag:** `none`

**Does NOT cover:** This task does not add UI controls or move stability logic into `gui.py`; the GUI must continue to delegate stability decisions to `AutoMoveStability`.

- [x] **Step 1: Replace the GUI auto handoff test**

Replace `test_auto_tick_passes_stable_scan_to_background_check_worker` in `tests/test_move_debug.py` with:

```python
def test_auto_tick_passes_stable_scan_to_background_check_worker_after_two_clean_observations(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    ui.AutoButton.setChecked(True)
    ui.SpecialPieceBox.setCurrentIndex(ui.SpecialPieceBox.findData(bot.SPECIAL_PIECE_MODE_AUTO))
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    board_image = Image.new("RGB", (20, 20), "black")
    captured_calls = []

    monkeypatch.setattr(ui, "start_check_best_move", lambda **kwargs: captured_calls.append(kwargs) or True)

    ui._handle_auto_scan_finished(bot.AutoScanResult(board, special_board, board_image))

    assert captured_calls == []
    assert ui.AutoStatus.text() == "Auto: stabilno 1/2"

    ui._handle_auto_scan_finished(bot.AutoScanResult(board, special_board, board_image))

    assert captured_calls == [
        {
            "include_future_value": True,
            "action": "auto_highest_points",
            "display_label": "Auto",
            "pre_scanned_board": board,
            "pre_scanned_special_board": special_board,
            "pre_scanned_board_path": bot.AUTO_LATEST_BOARD_FILENAME,
            "lookahead_candidates": bot.LIVE_LOOKAHEAD_CANDIDATES,
            "lookahead_depth": bot.LIVE_LOOKAHEAD_DEPTH,
            "lookahead_beam_width": bot.LIVE_LOOKAHEAD_BEAM_WIDTH,
            "auto_signature": ui.auto_stability.last_signature,
        }
    ]
```

- [x] **Step 2: Update the motion GUI test to assert cautious display**

Replace `test_auto_tick_waits_for_animation_when_motion_is_high` with:

```python
def test_auto_tick_waits_for_animation_when_motion_is_high_and_then_displays_cautious_count(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = QtWidgets.QMainWindow()
    ui = bot.Ui_MainWindow()
    ui.setupUi(window)
    ui.AutoButton.setChecked(True)
    board = [[1, 2], [3, 4]]
    special_board = [[0, 0], [0, 0]]
    previous_image = Image.new("RGB", (20, 20), "black")
    moving_image = Image.new("RGB", (20, 20), "white")
    stable_image = Image.new("RGB", (20, 20), "white")
    captured_calls = []

    ui.auto_stability.previous_image = previous_image
    monkeypatch.setattr(ui, "start_check_best_move", lambda **kwargs: captured_calls.append(kwargs))

    ui._handle_auto_scan_finished(bot.AutoScanResult(board, special_board, moving_image))

    assert captured_calls == []
    assert ui.AutoStatus.text() == "Auto: ceka animaciju"

    ui._handle_auto_scan_finished(bot.AutoScanResult(board, special_board, stable_image))

    assert captured_calls == []
    assert ui.AutoStatus.text() == "Auto: stabilno 1/3"
```

- [x] **Step 3: Run focused tests to verify current GUI behavior**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: PASS if `gui.py` already displays the active `required_scans` and keeps `pre_scanned_board` flow. If it fails, the failure should point to status text or stable board handoff only.

- [x] **Step 4: Change `gui.py` only if required**

If Step 3 fails because `gui.py` does not display the active requirement, keep the status block in `_handle_auto_scan_finished(...)` shaped like this:

```python
        if not should_play:
            if self.auto_stability.wait_reason in {"unrecognized", "motion", "visual"}:
                self.AutoStatus.setText("Auto: ceka animaciju")
            elif self.auto_stability.waiting_for_change:
                self.AutoStatus.setText("Auto: ceka promenu")
            else:
                self.AutoStatus.setText(
                    f"Auto: stabilno {self.auto_stability.stable_count}/"
                    f"{self.auto_stability.required_scans}"
                )
            return
```

If Step 3 fails because `pre_scanned_board` is not passed, keep the worker call shaped like this:

```python
        started = self.start_check_best_move(
            include_future_value=True,
            action="auto_highest_points",
            display_label="Auto",
            pre_scanned_board=game_board,
            pre_scanned_special_board=special_game_board,
            pre_scanned_board_path=AUTO_LATEST_BOARD_FILENAME,
            lookahead_candidates=LIVE_LOOKAHEAD_CANDIDATES,
            lookahead_depth=LIVE_LOOKAHEAD_DEPTH,
            lookahead_beam_width=LIVE_LOOKAHEAD_BEAM_WIDTH,
            auto_signature=signature,
        )
```

- [x] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: PASS.

---

### Task 4: Full Verification And Scope Audit

**Files:**
- Verify: `runtime.py`
- Verify: `gui.py`
- Verify: `tests/test_move_debug.py`

**Security flag:** `none`

**Does NOT cover:** This task does not introduce new behavior. It verifies the completed auto-only adaptive stability change and checks that unrelated systems were not touched.

- [x] **Step 1: Run py_compile**

Run:

```powershell
python -m py_compile runtime.py gui.py
```

Expected: PASS with no output.

- [x] **Step 2: Run focused test file**

Run:

```powershell
python -m pytest tests/test_move_debug.py -q
```

Expected: PASS.

- [x] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: PASS.

- [x] **Step 4: Scope audit**

Run this non-Git audit command:

```powershell
Get-Item runtime.py, gui.py, tests/test_move_debug.py, docs/specs/2026-05-25-auto-mode-adaptive-stability-design.md, docs/plans/2026-05-25-auto-mode-adaptive-stability.md | Select-Object FullName, LastWriteTime
```

Expected: the inspected files are limited to the auto-stability plan, spec, runtime, optional GUI status/handoff surface, and tests. There should be no evidence that ranking, ML model, dataset, perk, booster, score OCR, or debug writer files were edited for this task.

- [x] **Step 5: Final report contents**

Report:

- The constants now in use: `AUTO_STABLE_REQUIRED_SCANS = 2`, `AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS = 3`, `AUTO_POST_MOVE_COOLDOWN_SECONDS = 0.12`.
- Whether `gui.py` required changes or was already compatible.
- The exact verification commands and their pass/fail results.
- If live BlueStacks verification was not run, state that clearly and provide the manual live checks from the spec.
