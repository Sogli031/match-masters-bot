# Recognition Runtime Stability & Majority Vote - Design

_Sub-project D of the "ML recognition revival" initiative._

Status: **Draft for user review**
Date: 2026-05-25
Predecessors:
- Sub-project A - [docs/specs/2026-05-24-recognition-dataset-builder-design.md](2026-05-24-recognition-dataset-builder-design.md)
- Sub-project B - [docs/specs/2026-05-24-recognition-cnn-training-design.md](2026-05-24-recognition-cnn-training-design.md)
- Sub-project C - [docs/specs/2026-05-25-recognition-runtime-ml-path-design.md](2026-05-25-recognition-runtime-ml-path-design.md)

## 1. Goal and Scope

Add a runtime guard that handles transient tile animations by waiting briefly
and combining 2-3 recognition frames before the bot chooses a move.

The training goal stays narrow: train the CNN to recognize stable, normal tile
states accurately. Runtime animation handling belongs in this project, not in
the dataset or model training loop.

The runtime guard must:

1. Keep the first clean recognition result fast.
2. Detect suspicious frames: unrecognized cells, low-confidence ML output, high
   visual motion, or disagreement between consecutive frames.
3. Capture up to 3 frames with short spacing when the first frame is suspicious.
4. Choose a board by per-cell majority when at least 2 frames agree.
5. Refuse to play when the frames do not converge safely.
6. Write debug evidence showing each frame, its diagnostics, and the final
   decision.

### Non-goals

- No retraining changes.
- No dataset review changes.
- No attempt to synthesize animation crops or augment scale/deformation in
  `recognition_dataset.py`.
- No move-ranking changes.
- No ML-only runtime requirement. This must work with template-only, shadow ML,
  and hybrid ML modes.
- No repeated screenshots when `CheckBestMoveRequest.pre_scanned_board` is
  already provided by the auto-play stability path. Pre-scanned boards are
  treated as already sampled.
- No indefinite waiting. The runtime gets a bounded number of frames and then
  either returns a safe board or stops/defers.

## 2. Existing Runtime Anchors

Current manual/live recognition path:

- `runtime.run_check_best_move_request(...)`
- `recognition.update_board_2(board, special_board, screenshot_path=..., _diag=...)`
- `recognition._finalize_board_with_ml(...)`
- `ml_recognition_runtime.predict_board_tiles(...)`
- `recognition.apply_ml_recognition_overlay(...)`

Current retry behavior:

- `run_check_best_move_request` retries up to 3 times only when `game_board`
  still contains `0` cells.
- Retry sleep is `100 ms`.
- `timings.json` records `recognition_breakdown.retry_count`,
  `retry_sleep_ms`, and `attempts`.

Current auto-play stability path:

- `runtime.AutoMoveStability` already requires repeated stable boards.
- It rejects unrecognized cells, high motion, visual hash jumps, and repeated
  already-played signatures.
- `gui.Ui_MainWindow._handle_auto_scan_finished(...)` shows statuses such as
  `Auto: ceka animaciju`, `Auto: stabilno 1/2`, and `Auto: igra`.

This project should reuse those concepts instead of inventing a separate
animation model.

## 3. Considered Approaches

### Option A: Train on animation frames

Collect mid-animation crops for every class and add them to the training set.

Pros:
- Improves model tolerance when it sees similar animation states later.

Cons:
- Requires broad class coverage to avoid bias.
- Rare specials would still be under-covered.
- Blurs the clean class boundary if examples are sparse or ambiguous.
- Does not help template-only recognition.

Verdict: useful later as supplemental data, but not the primary fix.

### Option B: Fixed delay before every scan

Sleep for a fixed interval before recognizing every board.

Pros:
- Very simple.
- Avoids many animation frames.

Cons:
- Slows every move, even when the board is already stable.
- Does not prove the board actually became stable.
- Can still fire during long or chained animations.

Verdict: too blunt for live play.

### Option C: Bounded multi-frame stability and majority vote (recommended)

Recognize once immediately. If the result is clean, use it. If suspicious,
capture 1-2 more frames, then accept only if frames converge by majority and
quality gates pass.

Pros:
- Fast path remains fast.
- Handles animation as a runtime timing problem.
- Works with template, shadow ML, and hybrid ML.
- Produces debug evidence that explains why the bot waited or refused.

Cons:
- More code than the current zero-only retry loop.
- Needs careful diagnostics to avoid hiding recognition bugs.
- Adds up to ~200 ms delay only on suspicious frames.

Recommendation: implement Option C after stable-board CNN training is complete.

## 4. Proposed Runtime Design

### 4.1 Frame sample

Introduce a small data object in `runtime.py`:

```python
@dataclass
class RecognitionFrameSample:
    index: int
    board: list[list[int]]
    special_board: list[list[int]]
    board_image_path: Path | None
    diag: dict
    visual_hash: int | None
    motion_score: float | None
    zero_count: int
    accepted_ml: int
    rejected_ml: int
    suspicious_reasons: list[str]
```

The sample is runtime-only. It must not change `recognition.py` model
contracts unless a small helper is needed to expose existing diagnostics.

### 4.2 Suspicion gates

A frame is suspicious when any of these are true:

- `zero_count > 0`
- ML mode is `hybrid` or `shadow`, `ml_available=True`, and at least 3 cells are
  rejected for `confidence_below_threshold`
- ML mode is `hybrid`, `ml_available=True`, and a low-confidence ML prediction
  disagrees with the template result on a non-zero cell
- motion score exceeds the same threshold family used by `AutoMoveStability`
- visual hash changes too much between same-signature frames
- two consecutive frames produce different non-zero board signatures

Initial defaults:

- `max_frames = 3`
- `min_majority = 2`
- `frame_delay_ms = 100`
- `max_total_wait_ms = 250`
- `require_no_zeros_for_play = True`

These constants should live near the existing auto-stability constants in
`runtime.py`.

### 4.3 Fast path

If frame 1 has:

- no zero cells,
- no high-motion evidence,
- no ML confidence warning that matches the suspicion gates above,
- and no debug-level error from `update_board_2`,

then return frame 1 exactly as today.

This avoids slowing normal stable boards.

### 4.4 Majority aggregation

When frame 1 is suspicious:

1. Wait `frame_delay_ms`.
2. Capture frame 2 and recognize it.
3. If frame 1 and frame 2 are identical, accept the shared board.
4. If they differ, capture frame 3.
5. For each cell, choose `(board_value, special_value)` only when at least
   `min_majority` frames agree.
6. If any cell has no majority or resolves to `0`, mark the whole result unsafe.

Special-piece cells should be stricter than normal cells:

- accept a special only when the same `(board_value, special_value)` wins;
- do not mix a special from one frame with a color from another frame;
- do not downgrade a special to normal unless the normal value wins by majority
  and no frame has high-confidence special evidence for that cell.

### 4.5 Safe refusal

If frames do not converge:

- Manual `Check Best Move`: print a clear message and avoid choosing a move from
  an unsafe board.
- Auto mode: keep status as `Auto: ceka animaciju` or a more specific future
  status, then scan again on the next tick.

Do not fall back to ranking a partially recognized board with zeros.

### 4.6 Interaction with ML modes

Mode behavior:

- `off`: majority operates on template/color output only.
- `shadow`: majority operates on template/color output, but stores ML
  predictions per frame for diagnostics.
- `hybrid`: majority operates on the post-overlay board returned by
  `apply_ml_recognition_overlay`, while diagnostics still record template vs ML
  decisions.

ML confidence should be a trigger for extra frames, not a replacement for
majority. A single high-confidence ML frame should not override unstable frame
evidence unless the existing hybrid gates would already accept that cell and
the majority result is safe.

### 4.7 Interaction with pre-scanned auto boards

When `CheckBestMoveRequest.pre_scanned_board` and
`pre_scanned_special_board` are provided:

- do not capture extra frames inside `run_check_best_move_request`;
- use the pre-scanned board as the source of truth;
- keep existing behavior that avoids rescanning a stable auto board;
- future auto-scan worker work may reuse the same majority helper before it
  passes `pre_scanned_board` to `CheckBestMoveRequest`.

This preserves the existing auto fast path and avoids double work.

## 5. Debug Output

Extend `timings.json` under `recognition_breakdown`:

```json
{
  "frame_majority": {
    "enabled": true,
    "frames_captured": 3,
    "frame_delay_ms": 100,
    "decision": "accepted_majority",
    "unsafe_reason": null,
    "final_source": "majority"
  }
}
```

Each frame should include:

- `index`
- `zero_count`
- `signature_hash` or equivalent compact signature summary
- `motion_score`
- `suspicious_reasons`
- existing recognition attempt summary
- ML accepted/rejected counts when available

When debug is enabled, preserve frame images as:

- `board.png` for the final accepted/last observed board, matching current
  expectations
- `recognition_frames/frame_1.png`
- `recognition_frames/frame_2.png`
- `recognition_frames/frame_3.png`

Do not break existing consumers of `Debug/runs/<timestamp>/board.png`.

## 6. Testing Strategy

Unit tests:

- `RecognitionFrameSample` quality flags mark zero-cell frames as suspicious.
- first clean frame returns immediately without sleeping.
- two identical clean frames after a suspicious first frame are accepted.
- three frames resolve per-cell majority for normal cells.
- special cells require matching `(board_value, special_value)`.
- no-majority cells make the result unsafe.
- `pre_scanned_board` bypasses multi-frame capture.

Runtime tests:

- existing zero retry behavior is replaced or preserved through the new helper.
- `recognition_breakdown.frame_majority` is written in debug output.
- manual unsafe result does not call move ranking on a zero/unsafe board.
- auto mode keeps waiting instead of playing when majority is unsafe.

Regression fixtures:

- Synthetic boards are enough for majority logic.
- Real `Debug/runs` artifacts should be used only for integration confidence
  after the model is trained.

Verification commands for a future implementation plan:

```powershell
python -m pytest tests/test_move_debug.py tests/test_ml_recognition_runtime.py tests/test_recognition_ml_overlay.py -q
python -m pytest -q
python -m py_compile runtime.py gui.py recognition.py ml_recognition_runtime.py
```

Live verification after training:

1. Start BlueStacks with Match Masters on a stable board.
2. Run `python test.py`.
3. Enable debug.
4. Run manual `Check Best Move` while the board is stable; verify only one frame
   is captured.
5. Run during/after a visible animation; verify 2-3 frames are captured and
   debug explains the wait/majority decision.
6. Confirm auto mode shows waiting status and does not play from unstable frames.

## 7. Rollout Notes

Recommended rollout order:

1. Finish clean stable-board training and validate per-class reports.
2. Enable ML path in `shadow` mode and collect disagreement/debug evidence.
3. Implement this majority/stability runtime layer behind constants/defaults.
4. Verify manual `Check Best Move` first.
5. Verify auto mode only after manual behavior is stable.
6. Consider collecting animation examples later only for classes still failing
   after runtime waiting.

The default should be conservative: if the bot is unsure, wait or refuse rather
than play a move from a board captured mid-animation.

## 8. Failure-Mode Check

### Failure mode: majority locks onto a repeated wrong frame

If two frames are captured during the same long animation state, majority may
accept a wrong board. Mitigation: include motion score and visual-hash gates;
do not accept majority while motion is above threshold.

Severity: significant, addressed by suspicion gates.

### Failure mode: specials disappear or appear between frames

A special tile may animate differently enough that one frame sees normal and
another sees special. Mitigation: require exact `(board_value, special_value)`
agreement for specials and reject mixed evidence when no clear majority exists.

Severity: significant, addressed by stricter special aggregation.

### Failure mode: extra frame capture slows normal gameplay

If every board waits for 3 frames, play becomes sluggish. Mitigation: fast path
returns on the first clean frame; additional frames are only for suspicious
results.

Severity: significant, addressed by fast-path requirement.

### Failure mode: debug output becomes too large

Saving three frame images for every debug run may add disk churn. Mitigation:
only save `recognition_frames/` when debug is enabled and more than one frame
was captured, or when the final decision is unsafe.

Severity: minor, documented rollout constraint.

## 9. Default Implementation Decisions

These defaults remove ambiguity for a future implementation plan. They can be
changed later only if training metrics or live debug evidence justify it.

1. ML confidence trigger: do not retry for a single low-confidence prediction.
   Retry only when at least 3 cells are rejected for
   `confidence_below_threshold`, or when hybrid ML disagrees with a non-zero
   template result on a low-confidence cell.
2. Manual unsafe result: return a structured unsafe recognition result from the
   future helper and stop before move ranking. The UI/console should show a
   clear "wait and scan again" message.
3. Auto mode: keep `AutoMoveStability` as the outer gate, but let the auto-scan
   worker reuse the same frame-majority helper before it creates
   `pre_scanned_board`. `run_check_best_move_request` must still bypass extra
   capture when `pre_scanned_board` is provided.
