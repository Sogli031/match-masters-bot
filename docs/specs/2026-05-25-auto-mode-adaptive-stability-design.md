# Auto Mode Adaptive Stability - Design

Status: **Draft for user review**
Date: 2026-05-25

## 1. Goal and Scope

Make auto mode wait for a stable board before every automatic move, including
after each played move, without turning the bot into a slow fixed-delay loop.

The change is intentionally auto-only:

1. Auto mode should not play from the first scan after a move.
2. Auto mode should normally require 2 matching clean scans before playing.
3. Auto mode should require 3 matching clean scans after suspicious evidence:
   visual motion, visual hash jump, unrecognized cells, or a changed board after
   a played move.
4. Auto mode should keep the current fast scan cadence and reuse the stable
   `pre_scanned_board` when it starts the existing highest-points move worker.

### Non-goals

- No move-ranking changes.
- No ML model or training changes.
- No manual `Check Best Move` behavior changes.
- No broad runtime majority-vote layer for manual recognition.
- No fixed long sleep before every move.
- No changes to perk, booster, or scoring policy.

## 2. Existing Runtime Anchors

Current auto mode already has the right structure:

- `gui.Ui_MainWindow.auto_tick()` starts an async auto scan when the timer fires.
- `gui.Ui_MainWindow._handle_auto_scan_finished(...)` sends the scan into
  `runtime.AutoMoveStability`.
- `runtime.AutoMoveStability.observe(...)` rejects unrecognized cells, high
  motion, visual hash jumps, and repeated already-played board signatures.
- When stable, auto starts the existing highest-points worker with
  `pre_scanned_board` and `pre_scanned_special_board`.
- When the worker finishes, `_handle_check_best_move_finished(...)` calls
  `auto_stability.mark_played(...)` and applies a short post-move cooldown.

The weak point is the current tuning: `AUTO_STABLE_REQUIRED_SCANS` is `1`, so a
single clean-looking scan can trigger a move.

## 3. Considered Approaches

### Option A: Static 2-scan gate

Set `AUTO_STABLE_REQUIRED_SCANS = 2` and slightly increase the cooldown.

Pros:
- Minimal implementation.
- Safer than the current 1-scan fast path.

Cons:
- Treats every situation the same.
- A board that just changed after a move may still be accepted too early if two
  quick scans happen during a transient but consistent animation state.

Verdict: acceptable as a small patch, but not conservative enough after moves.

### Option B: Adaptive 2-or-3 scan stability gate

Use 2 scans for normal stable boards, but raise the requirement to 3 after
motion, visual instability, unrecognized cells, or post-move board change.

Pros:
- Preserves the fast path for ordinary stable boards.
- Adds extra caution exactly where early play is most likely.
- Fits the existing `AutoMoveStability` state machine.
- Keeps the existing async scan and `pre_scanned_board` flow.

Cons:
- Slightly more state than a constant change.
- Needs tests around when the requirement rises and when it resets.

Recommendation: implement Option B.

### Option C: Full multi-frame majority runtime

Implement the broader recognition majority layer from
`2026-05-25-recognition-runtime-stability-majority-design.md`.

Pros:
- Stronger for manual and auto recognition.
- Can produce richer debug evidence.

Cons:
- Larger scope than this auto-mode fix.
- Touches manual `Check Best Move`, recognition retry behavior, and debug
  output.

Verdict: keep as a later project if live evidence still shows unstable boards
after the auto-only gate.

## 4. Proposed Design

### 4.1 Constants

Replace the single auto stable-scan default with two explicit constants:

```python
AUTO_STABLE_REQUIRED_SCANS = 2
AUTO_SUSPICIOUS_STABLE_REQUIRED_SCANS = 3
```

Keep `AUTO_SCAN_INTERVAL_MS` fast. A `25 ms` timer is acceptable because the
gate is based on repeated observations, not on blocking sleeps.

Increase `AUTO_POST_MOVE_COOLDOWN_SECONDS` modestly from `0.06` to `0.12`
seconds. This is only a small buffer before the next scan cycle; it must not be
the main stability mechanism.

### 4.2 AutoMoveStability state

Extend `AutoMoveStability` with an adaptive required-scan state:

- `base_required_scans`: normal requirement, initially `2`.
- `suspicious_required_scans`: cautious requirement, initially `3`.
- `current_required_scans`: active requirement used by `observe(...)`.
- `suspicious_until_stable`: true after instability or post-move change until a
  board reaches the cautious requirement.

`required_scans` should remain available for existing code/tests, but it should
represent the currently active requirement.

### 4.3 When to require 3 scans

Raise the active requirement to 3 when any of these happen:

- `observe(...)` sees unrecognized cells.
- `observe(...)` sees motion above the existing threshold.
- `observe(...)` sees a visual hash jump for the same board signature.
- `observe(...)` is waiting for the played board to change and then observes a
  different signature.
- `mark_played(...)` is called after an auto move.

The post-move rule matters most: after a move, the first changed board is
usually near cascades or animations, so auto should not play after just two
quick scans.

### 4.4 When to return to 2 scans

Return to the normal 2-scan requirement only after a board has passed the
current cautious requirement and auto is allowed to play.

This prevents a pattern where one suspicious scan raises the requirement, one
apparently clean scan lowers it, and the next scan plays too early.

### 4.5 Existing play flow stays the same

When the gate passes:

1. `_handle_auto_scan_finished(...)` keeps setting `Auto: igra`.
2. It still calls `start_check_best_move(...)` with action
   `auto_highest_points`.
3. It still passes the stable `pre_scanned_board`,
   `pre_scanned_special_board`, and `AUTO_LATEST_BOARD_FILENAME`.
4. `run_check_best_move_request(...)` still bypasses extra board capture when a
   pre-scanned board is provided.

The auto button continues to behave like `Najvise poena`, only gated by safer
stability.

### 4.6 Status text

Keep the current compact statuses:

- `Auto: ceka tablu`
- `Auto: skeniram`
- `Auto: ceka animaciju`
- `Auto: ceka promenu`
- `Auto: stabilno x/y`
- `Auto: igra`
- `Auto: cooldown`

The only visible change should be that `y` can be `2` or `3` depending on the
active stability requirement.

## 5. Interfaces and Contracts

### Runtime contract

`AutoMoveStability.observe(board, special_board, visual_hash=None,
motion_score=0.0)` keeps returning `True` only when auto is allowed to play.

The class must continue to expose:

- `stable_count`
- `required_scans`
- `waiting_for_change`
- `wait_reason`
- `last_signature`
- `last_motion_score`
- `last_hash_distance`

Existing callers should not need to know whether the current requirement is
base or suspicious.

### GUI contract

`gui.py` should only consume the existing `AutoMoveStability` surface. It should
not duplicate stability rules in the UI layer.

## 6. Error Handling

- If auto scan fails, preserve the existing `Auto: ERROR` behavior.
- If cells are unrecognized, do not play. Show `Auto: ceka animaciju` and keep
  scanning.
- If the board has not changed after the last played signature, do not play.
  Show `Auto: ceka promenu`.
- If the visual image is unavailable, fall back to board-signature stability but
  still require repeated scans.

## 7. Testing Strategy

Unit tests in `tests/test_move_debug.py` should cover:

- Default auto timing now uses `2` normal scans and `3` suspicious scans.
- A fresh stable board plays after 2 matching clean observations.
- After `mark_played(...)`, the unchanged played board is blocked.
- After the board changes post-move, auto requires 3 matching clean scans.
- Unrecognized cells raise the next stable requirement to 3.
- High motion raises the next stable requirement to 3.
- Visual hash jumps raise the next stable requirement to 3.
- `_handle_auto_scan_finished(...)` still passes the stable pre-scanned board to
  `start_check_best_move(...)`.

Verification commands:

```powershell
python -m pytest tests/test_move_debug.py -q
python -m pytest -q
python -m py_compile runtime.py gui.py
```

Live verification:

1. Run `python test.py` with BlueStacks open on a stable board.
2. Turn on auto mode and confirm it shows `Auto: stabilno 1/2` before the first
   play.
3. After a move, confirm auto does not immediately play from the first changed
   board and can show `Auto: stabilno 1/3` or `2/3`.
4. Confirm the move that finally plays still matches the existing
   highest-points flow.

## 8. Rollout Notes

This is a conservative runtime tuning change. It should be implemented before a
broader recognition majority project because it is smaller, easier to test, and
directly targets premature auto moves.

If live play still shows early moves after this change, the next step is the
broader bounded multi-frame majority design, not another fixed delay increase.

## 9. Failure-Mode Check

### Failure mode: repeated wrong frames look stable

Two or three scans can still agree on a wrong board if recognition is
consistently wrong. Mitigation: this design keeps unrecognized cells, motion,
and visual hash jumps as blockers, but it does not claim to solve consistent
misclassification. That remains a recognition/model issue.

Severity: minor for this scope, documented as a non-goal.

### Failure mode: cautious mode never returns to fast mode

If suspicious state is not cleared after a successful play, auto would always
require 3 scans and feel slower than necessary. Mitigation: reset the active
requirement to the base value only when a board has passed the current gate and
is about to play.

Severity: significant, addressed in the state design and tests.

### Failure mode: cooldown is treated as stability

A longer cooldown alone could hide symptoms without proving the board is
stable. Mitigation: cooldown remains short and secondary; repeated observations
are the real gate.

Severity: significant, addressed by keeping cooldown modest and requiring
2-or-3 matching scans.
