# Booster Action Selector - Design

Status: **Approved**
Date: 2026-05-25

## 1. Goal and Scope

Separate piece recognition from booster action behavior.

The old `SpecialPieceBox` existed because template matching could miss
booster-specific pieces unless the user told the bot which booster was active.
The current ML recognition path can classify the board directly, so the main UI
should no longer ask the user which figures to recognize.

The new behavior should be:

1. Recognize all supported piece types automatically.
2. Keep the selected ML recognition mode as the recognition source control.
3. Repurpose the booster selector so it means "what action is needed after
   pressing Activate".
4. In the first pass, support only:
   - no special post-activate action
   - High Voltage post-activate tile click

### Non-goals

- No new ML model training.
- No new piece taxonomy.
- No recognition threshold tuning.
- No new High Voltage scoring policy.
- No new booster-specific flows except preserving the existing High Voltage
  flow.
- No broad UI redesign.
- No removal of debug fields needed by existing tests or saved-run analysis.

## 2. Existing Runtime Anchors

The current code uses one value, `special_piece_mode`, for two different
concerns:

- Recognition filtering in `recognition.update_board_2(...)`:
  `auto` runs the broad special-piece detectors; named values such as `hearts`,
  `knights`, `cleo`, and `billie` restrict old template detectors.
- Runtime booster behavior in `runtime.run_check_best_move_request(...)`:
  `high_voltage` means the selected booster must use the existing
  `Activate -> delay -> board tile click` flow.

This is why the UI still shows labels such as `Booster: Srca` even though those
entries are mainly recognition filters. With ML-first / ML-only recognition,
that coupling is now misleading.

The useful existing pieces are:

- `MLRecognitionModeBox` controls `ML off`, `ML shadow`, `ML hybrid`,
  `ML first`, and `ML only`.
- `recognition.SPECIAL_PIECE_MODE_AUTO` already means "try all known piece
  detectors" in the non-ML path.
- `runtime.activate_high_voltage_booster(...)` already performs the live
  `Activate -> delay -> tile click -> restore cursor` sequence.
- `move_strategy.choose_high_voltage_target(...)` already chooses the best
  High Voltage target using the current score-first policy.

## 3. Approved Direction

The user approved this direction:

1. Hide/remove manual figure selection from the main UI.
2. Recognize all figures automatically.
3. Keep only a simple booster action selector in the first pass:
   - `Bez posebne akcije`
   - `High Voltage`

## 4. Considered Approaches

### Option A: Rename the existing combo only

Keep `SpecialPieceBox`, keep all old entries, and only change labels.

Pros:
- Smallest code diff.
- Minimal test migration.

Cons:
- Still exposes figure-recognition choices the user no longer needs.
- Keeps mixing recognition policy and booster action policy.
- Makes future action boosters harder to reason about.

Verdict: reject.

### Option B: Split recognition mode and booster action mode

Keep ML recognition mode as the recognition control. Force the piece-recognition
mode to `auto` from the main flow, and introduce a small booster action selector
for post-activate behavior.

Pros:
- Matches how the bot now works: ML recognizes board pieces, runtime decides
  what to do after Activate.
- Preserves the existing High Voltage implementation.
- Keeps the first pass small and testable.
- Creates a clean place for future action boosters.

Cons:
- Requires migrating GUI state and request naming carefully.
- Existing debug output may still carry `special_piece_mode` unless renamed in a
  later cleanup.

Recommendation: implement Option B.

### Option C: Fully remove old special-piece modes

Delete old named piece modes and all template-specific recognition filters.

Pros:
- Cleanest long-term concept model.
- Less UI and normalization clutter.

Cons:
- Too much scope for this change.
- Risky while `ML off`, `ML shadow`, `ML hybrid`, and `ML first` still preserve
  template fallback behavior.
- Would force a larger test rewrite unrelated to booster selection.

Verdict: defer. Keep old recognition constants internally for compatibility and
fallback paths.

## 5. Proposed Design

### 5.1 Recognition mode

Main move requests should use automatic piece recognition:

```python
special_piece_mode = SPECIAL_PIECE_MODE_AUTO
```

This applies to manual `Najvise poena`, `Extra move`, and auto-mode scans. The
ML recognition mode remains independently controlled by `MLRecognitionModeBox`.

If ML is set to `ML only`, the existing strict behavior remains: complete ML
coverage is required and template fallback is skipped. If ML is unavailable or
incomplete, the bot blocks through the existing ML-only path rather than asking
the user to choose a piece type.

If ML is set to a mode that can use template fallback, `auto` keeps the fallback
as broad as possible instead of filtering to one old booster family.

### 5.2 Booster action mode

Add a small runtime-facing booster action value:

```python
BOOSTER_ACTION_NONE = "none"
BOOSTER_ACTION_HIGH_VOLTAGE = "high_voltage"
```

The UI selector should display:

- `Bez posebne akcije`
- `High Voltage`

The selected value should be saved in `gui_state.json` as `booster_action_mode`.

For backwards compatibility, when loading older state:

- `special_piece_mode = "high_voltage"` maps to
  `booster_action_mode = "high_voltage"`.
- Any other old `special_piece_mode` maps to `booster_action_mode = "none"`.
- Missing `booster_action_mode` defaults to `"none"`.

### 5.3 Request and runtime contract

`CheckBestMoveRequest` should gain:

```python
booster_action_mode: str = BOOSTER_ACTION_NONE
```

Existing `special_piece_mode` can remain for compatibility in the first pass,
but the GUI should pass `SPECIAL_PIECE_MODE_AUTO` for recognition and pass the
new booster action value separately.

Runtime decisions become:

- If selected action is not `activate_booster`, play the selected move as today.
- If selected action is `activate_booster` and
  `booster_action_mode == "high_voltage"`, run the existing High Voltage target
  chooser and click flow.
- If selected action is `activate_booster` and
  `booster_action_mode == "none"`, run the existing plain
  `click_booster_activate(...)` path.

The booster-ready latch should key by `booster_action_mode`, not by the old
piece-recognition mode. This preserves the current safety behavior where a
latched active booster is cleared when the selected booster behavior changes.

### 5.4 Debug output

For this first pass, debug output may keep the existing `special_piece_mode`
field, but it should also include `booster_action_mode`.

Recommended debug meaning:

- `special_piece_mode`: recognition-side piece mode, expected to be `auto` from
  the main UI flow.
- `booster_action_mode`: post-activate behavior selected by the user.

High Voltage debug payloads remain unchanged except that they are gated by
`booster_action_mode`.

### 5.5 UI text and layout

Replace the main visible `Booster: ...` figure list with the two action options.

The UI should not add instructional text. The selector label can stay compact;
the important change is that the options no longer list piece families such as
`Srca`, `Konji`, `Cleo`, or `Billie`.

`Booster odmah` remains separate and unchanged. It controls when to activate a
ready booster; the new booster action selector controls what to do after
activation.

## 6. Error Handling

- Invalid `booster_action_mode` values normalize to `"none"`.
- Invalid old `special_piece_mode` values still normalize through the existing
  recognition fallback, which returns `auto`.
- If High Voltage is selected but no valid target exists, keep the existing
  behavior: do not click a tile and return a no-action result.
- If the plain booster action is selected, never run High Voltage target
  evaluation.

## 7. Testing Strategy

Focused tests should cover:

- GUI options are exactly `Bez posebne akcije` and `High Voltage`.
- GUI state saves `booster_action_mode`.
- Old state with `special_piece_mode = "high_voltage"` loads as
  `booster_action_mode = "high_voltage"`.
- Old state with other figure modes loads as `booster_action_mode = "none"`.
- `build_check_best_move_request(...)` passes
  `special_piece_mode = auto` and the selected `booster_action_mode`.
- Auto-scan requests use automatic piece recognition.
- Runtime uses High Voltage flow only when `booster_action_mode` is
  `high_voltage`.
- Runtime uses plain `click_booster_activate(...)` when
  `booster_action_mode` is `none`.
- Booster latch clears when `booster_action_mode` changes.
- Debug `move.json` includes `booster_action_mode`.

Verification commands:

```powershell
python -m pytest tests/test_booster_activation.py -q
python -m pytest tests/test_move_debug.py -q
python -m pytest tests/test_special_detection.py -q
python -m pytest -q
python -m py_compile recognition.py runtime.py gui.py test.py
```

Manual live verification:

1. Run `python test.py`.
2. Select `ML only`.
3. Confirm the old figure family choices are not visible in the main booster
   selector.
4. With `Bez posebne akcije`, a ready booster only clicks Activate.
5. With `High Voltage`, a ready booster clicks Activate, waits, then clicks the
   selected target tile.
6. Confirm normal move selection still uses ML-recognized pieces without manual
   figure selection.

## 8. Rollout Notes

This should be implemented as a compatibility-preserving migration rather than
a deletion pass. The old `SPECIAL_PIECE_MODE_*` constants and template fallback
branches can stay for now because they still protect `ML off`, `ML shadow`,
`ML hybrid`, and `ML first` behavior.

A later cleanup can rename `special_piece_mode` to a clearer recognition-only
name or remove old manual figure filters after live evidence shows they are no
longer needed.

## 9. Failure-Mode Check

### Failure mode: ML misses a class that old manual filtering could still help

If the user is in `ML only`, the bot should block instead of falling back. If
the user uses `ML first` or `ML hybrid`, automatic recognition still allows the
template fallback to try all supported families. The design deliberately keeps
old recognition constants internally, so this does not remove the fallback code.

Severity: minor for this scope, handled by keeping compatibility paths.

### Failure mode: old GUI state silently loses High Voltage behavior

If old `gui_state.json` stored `special_piece_mode = "high_voltage"` and the new
UI defaulted to plain booster, the bot would stop doing the post-activate tile
click. The migration must map old High Voltage state into
`booster_action_mode = "high_voltage"`.

Severity: significant, addressed by the migration rule and tests.

### Failure mode: booster latch remains tied to recognition mode

If the latch still keys by `special_piece_mode`, changing from plain booster to
High Voltage could reuse stale active-booster detection. The latch should be
keyed by `booster_action_mode` after this change.

Severity: significant, addressed by the runtime contract and tests.

### Failure mode: `Booster odmah` is confused with booster action type

`Booster odmah` decides when to spend a ready booster. The new selector decides
what to do after Activate. Keeping both controls separate avoids changing the
existing extra-move-before-booster policy.

Severity: minor, documented in UI contract.
